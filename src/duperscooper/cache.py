"""Cache backend implementations for audio fingerprint storage."""

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, Optional, Protocol


class CacheBackend(Protocol):
    """Protocol for cache backend implementations."""

    def get(self, key: str) -> Optional[str]:
        """Get value from cache by key."""
        ...

    def set(self, key: str, value: str) -> None:
        """Set value in cache with key."""
        ...

    def get_stats(self) -> Dict[str, int]:
        """Get cache statistics (hits, misses, size)."""
        ...

    def clear(self) -> bool:
        """Clear all cache entries."""
        ...

    def close(self) -> None:
        """Close cache connections and cleanup."""
        ...


class SQLiteCacheBackend:
    """
    Thread-safe SQLite cache backend for audio fingerprints.

    Uses WAL mode for concurrent reads and atomic writes.
    Each thread gets its own connection via thread-local storage.
    """

    def __init__(self, db_path: Path):
        """
        Initialize SQLite cache backend.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._local = threading.local()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

        # Ensure parent directory exists
        db_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize database schema
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local database connection."""
        if not hasattr(self._local, "conn"):
            conn: sqlite3.Connection = sqlite3.connect(str(self.db_path), timeout=30.0)
            # Enable WAL mode for concurrent access
            conn.execute("PRAGMA journal_mode=WAL")
            # Enable foreign keys
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return self._local.conn  # type: ignore[no-any-return]

    def _init_db(self) -> None:
        """Initialize database schema."""
        conn = self._get_connection()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fingerprint_cache (
                file_hash TEXT PRIMARY KEY,
                fingerprint TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                last_accessed INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_last_accessed
            ON fingerprint_cache(last_accessed)
            """
        )
        conn.commit()

    def get(self, key: str) -> Optional[str]:
        """
        Get fingerprint from cache.

        Args:
            key: File hash (SHA256)

        Returns:
            Cached fingerprint string or None if not found
        """
        conn = self._get_connection()
        cursor = conn.execute(
            """
            SELECT fingerprint FROM fingerprint_cache
            WHERE file_hash = ?
            """,
            (key,),
        )
        row = cursor.fetchone()

        if row:
            # Update last_accessed timestamp
            conn.execute(
                """
                UPDATE fingerprint_cache
                SET last_accessed = ?
                WHERE file_hash = ?
                """,
                (int(time.time()), key),
            )
            conn.commit()

            with self._lock:
                self._hits += 1
            return str(row[0])
        else:
            with self._lock:
                self._misses += 1
            return None

    def set(self, key: str, value: str) -> None:
        """
        Store fingerprint in cache.

        Args:
            key: File hash (SHA256)
            value: Fingerprint string (comma-separated integers)
        """
        conn = self._get_connection()
        now = int(time.time())
        conn.execute(
            """
            INSERT OR REPLACE INTO fingerprint_cache
            (file_hash, fingerprint, created_at, last_accessed)
            VALUES (?, ?, ?, ?)
            """,
            (key, value, now, now),
        )
        conn.commit()

    def get_stats(self) -> Dict[str, int]:
        """
        Get cache statistics.

        Returns:
            Dictionary with hits, misses, and size
        """
        conn = self._get_connection()
        cursor = conn.execute("SELECT COUNT(*) FROM fingerprint_cache")
        size = cursor.fetchone()[0]

        with self._lock:
            return {"hits": self._hits, "misses": self._misses, "size": size}

    def clear(self) -> bool:
        """
        Clear all cache entries.

        Returns:
            True if successful
        """
        try:
            conn = self._get_connection()
            conn.execute("DELETE FROM fingerprint_cache")
            conn.commit()
            with self._lock:
                self._hits = 0
                self._misses = 0
            return True
        except sqlite3.Error:
            return False

    def close(self) -> None:
        """Close database connection for current thread."""
        if hasattr(self._local, "conn"):
            self._local.conn.close()
            delattr(self._local, "conn")

    def cleanup_old(self, max_age_days: int = 90) -> int:
        """
        Remove cache entries older than specified days.

        Args:
            max_age_days: Maximum age in days

        Returns:
            Number of entries removed
        """
        conn = self._get_connection()
        cutoff = int(time.time()) - (max_age_days * 86400)
        cursor = conn.execute(
            "DELETE FROM fingerprint_cache WHERE last_accessed < ?",
            (cutoff,),
        )
        conn.commit()
        return cursor.rowcount


class JSONCacheBackend:
    """
    Legacy JSON cache backend (fallback option).

    Not thread-safe - sequential operations only.
    """

    def __init__(self, json_path: Path):
        """
        Initialize JSON cache backend.

        Args:
            json_path: Path to JSON cache file
        """
        self.json_path = json_path
        self._cache: Dict[str, str] = {}
        self._hits = 0
        self._misses = 0
        self._modified = False

        # Load existing cache
        if json_path.exists():
            try:
                with open(json_path) as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self._cache = data
            except (json.JSONDecodeError, OSError):
                self._cache = {}

    def get(self, key: str) -> Optional[str]:
        """Get fingerprint from cache."""
        value = self._cache.get(key)
        if value:
            self._hits += 1
            return value
        else:
            self._misses += 1
            return None

    def set(self, key: str, value: str) -> None:
        """Store fingerprint in cache."""
        self._cache[key] = value
        self._modified = True

    def get_stats(self) -> Dict[str, int]:
        """Get cache statistics."""
        return {"hits": self._hits, "misses": self._misses, "size": len(self._cache)}

    def clear(self) -> bool:
        """Clear all cache entries."""
        try:
            self._cache.clear()
            if self.json_path.exists():
                self.json_path.unlink()
            self._hits = 0
            self._misses = 0
            self._modified = False
            return True
        except OSError:
            return False

    def close(self) -> None:
        """Save cache to disk if modified."""
        if self._modified:
            try:
                self.json_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.json_path, "w") as f:
                    json.dump(self._cache, f)
            except OSError:
                pass  # Silent failure for cache writes


def migrate_json_to_sqlite(json_path: Path, db_path: Path) -> int:
    """
    Migrate existing JSON cache to SQLite.

    Args:
        json_path: Path to existing JSON cache
        db_path: Path to SQLite database

    Returns:
        Number of entries migrated
    """
    if not json_path.exists():
        return 0

    try:
        # Load JSON cache
        with open(json_path) as f:
            data = json.load(f)
            if not isinstance(data, dict):
                return 0

        # Create SQLite cache and migrate
        sqlite_cache = SQLiteCacheBackend(db_path)
        count = 0
        for key, value in data.items():
            sqlite_cache.set(key, value)
            count += 1

        sqlite_cache.close()
        return count

    except (json.JSONDecodeError, OSError):
        return 0
