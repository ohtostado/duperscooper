"""Tests for cache backend implementations."""

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from duperscooper.cache import (
    JSONCacheBackend,
    SQLiteCacheBackend,
    migrate_json_to_sqlite,
)


class TestSQLiteCacheBackend:
    """Tests for SQLite cache backend."""

    def test_init_creates_database(self):
        """Test that initialization creates database file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            cache = SQLiteCacheBackend(db_path)

            assert db_path.exists()
            cache.close()

    def test_set_and_get(self):
        """Test storing and retrieving values."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            cache = SQLiteCacheBackend(db_path)

            cache.set("key1", "value1")
            cache.set("key2", "value2")

            assert cache.get("key1") == "value1"
            assert cache.get("key2") == "value2"
            cache.close()

    def test_get_nonexistent(self):
        """Test getting a nonexistent key returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            cache = SQLiteCacheBackend(db_path)

            assert cache.get("nonexistent") is None
            cache.close()

    def test_get_stats(self):
        """Test cache statistics tracking."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            cache = SQLiteCacheBackend(db_path)

            # Initial stats
            stats = cache.get_stats()
            assert stats["hits"] == 0
            assert stats["misses"] == 0
            assert stats["size"] == 0

            # Add some data
            cache.set("key1", "value1")
            cache.set("key2", "value2")

            # Miss
            cache.get("nonexistent")
            stats = cache.get_stats()
            assert stats["hits"] == 0
            assert stats["misses"] == 1
            assert stats["size"] == 2

            # Hit
            cache.get("key1")
            stats = cache.get_stats()
            assert stats["hits"] == 1
            assert stats["misses"] == 1
            assert stats["size"] == 2

            cache.close()

    def test_clear(self):
        """Test clearing all cache entries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            cache = SQLiteCacheBackend(db_path)

            cache.set("key1", "value1")
            cache.set("key2", "value2")

            stats = cache.get_stats()
            assert stats["size"] == 2

            result = cache.clear()
            assert result is True

            stats = cache.get_stats()
            assert stats["size"] == 0
            assert stats["hits"] == 0
            assert stats["misses"] == 0

            cache.close()

    def test_persistence(self):
        """Test that data persists across backend instances."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            # First instance
            cache1 = SQLiteCacheBackend(db_path)
            cache1.set("key1", "value1")
            cache1.close()

            # Second instance
            cache2 = SQLiteCacheBackend(db_path)
            assert cache2.get("key1") == "value1"
            cache2.close()

    def test_cleanup_old(self):
        """Test removing old cache entries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            cache = SQLiteCacheBackend(db_path)

            # Add entries and manually set old timestamps
            cache.set("key1", "value1")
            cache.set("key2", "value2")

            # Manually update timestamps to be old
            conn = cache._get_connection()
            conn.execute(
                "UPDATE fingerprint_cache SET last_accessed = ?",
                (0,),  # Very old timestamp
            )
            conn.commit()

            # Clean up entries older than 90 days
            removed = cache.cleanup_old(max_age_days=90)
            assert removed == 2

            stats = cache.get_stats()
            assert stats["size"] == 0

            cache.close()


class TestJSONCacheBackend:
    """Tests for JSON cache backend."""

    def test_set_and_get(self):
        """Test storing and retrieving values."""
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "test.json"
            cache = JSONCacheBackend(json_path)

            cache.set("key1", "value1")
            cache.set("key2", "value2")

            assert cache.get("key1") == "value1"
            assert cache.get("key2") == "value2"
            cache.close()

    def test_get_nonexistent(self):
        """Test getting a nonexistent key returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "test.json"
            cache = JSONCacheBackend(json_path)

            assert cache.get("nonexistent") is None
            cache.close()

    def test_get_stats(self):
        """Test cache statistics tracking."""
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "test.json"
            cache = JSONCacheBackend(json_path)

            # Initial stats
            stats = cache.get_stats()
            assert stats["hits"] == 0
            assert stats["misses"] == 0
            assert stats["size"] == 0

            # Add data and check stats
            cache.set("key1", "value1")
            cache.get("nonexistent")  # Miss
            cache.get("key1")  # Hit

            stats = cache.get_stats()
            assert stats["hits"] == 1
            assert stats["misses"] == 1
            assert stats["size"] == 1

            cache.close()

    def test_clear(self):
        """Test clearing all cache entries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "test.json"
            cache = JSONCacheBackend(json_path)

            cache.set("key1", "value1")
            cache.set("key2", "value2")
            cache.close()

            # Reopen to save
            cache = JSONCacheBackend(json_path)
            assert cache.get_stats()["size"] == 2

            result = cache.clear()
            assert result is True
            assert not json_path.exists()

            cache.close()

    def test_persistence(self):
        """Test that data persists across backend instances."""
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "test.json"

            # First instance
            cache1 = JSONCacheBackend(json_path)
            cache1.set("key1", "value1")
            cache1.close()

            # Second instance
            cache2 = JSONCacheBackend(json_path)
            assert cache2.get("key1") == "value1"
            cache2.close()

    def test_load_existing(self):
        """Test loading existing JSON cache file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "test.json"

            # Create JSON file manually
            with open(json_path, "w") as f:
                json.dump({"key1": "value1", "key2": "value2"}, f)

            # Load with backend
            cache = JSONCacheBackend(json_path)
            assert cache.get("key1") == "value1"
            assert cache.get("key2") == "value2"
            cache.close()


class TestMigration:
    """Tests for JSON to SQLite migration."""

    def test_migrate_json_to_sqlite(self):
        """Test migrating data from JSON to SQLite."""
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "hashes.json"
            db_path = Path(tmpdir) / "hashes.db"

            # Create JSON cache with data
            json_cache = JSONCacheBackend(json_path)
            json_cache.set("key1", "value1")
            json_cache.set("key2", "value2")
            json_cache.set("key3", "value3")
            json_cache.close()

            # Migrate to SQLite
            migrated = migrate_json_to_sqlite(json_path, db_path)
            assert migrated == 3

            # Verify SQLite has the data
            sqlite_cache = SQLiteCacheBackend(db_path)
            assert sqlite_cache.get("key1") == "value1"
            assert sqlite_cache.get("key2") == "value2"
            assert sqlite_cache.get("key3") == "value3"

            stats = sqlite_cache.get_stats()
            assert stats["size"] == 3

            sqlite_cache.close()

    def test_migrate_nonexistent_json(self):
        """Test migrating when JSON file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "nonexistent.json"
            db_path = Path(tmpdir) / "hashes.db"

            migrated = migrate_json_to_sqlite(json_path, db_path)
            assert migrated == 0

    def test_migrate_empty_json(self):
        """Test migrating empty JSON cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "hashes.json"
            db_path = Path(tmpdir) / "hashes.db"

            # Create empty JSON cache
            json_cache = JSONCacheBackend(json_path)
            json_cache.close()

            # Migrate to SQLite
            migrated = migrate_json_to_sqlite(json_path, db_path)
            assert migrated == 0

            # Verify SQLite exists but is empty
            sqlite_cache = SQLiteCacheBackend(db_path)
            stats = sqlite_cache.get_stats()
            assert stats["size"] == 0

            sqlite_cache.close()
