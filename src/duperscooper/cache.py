"""Cache backend implementations for audio fingerprint storage."""

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Tuple


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
        """Get thread-local database connection with retry logic."""
        if not hasattr(self._local, "conn"):
            import time

            max_retries = 5
            retry_delay = 0.1  # Start with 100ms

            for attempt in range(max_retries):
                try:
                    conn: sqlite3.Connection = sqlite3.connect(
                        str(self.db_path), timeout=30.0
                    )
                    # Enable WAL mode for concurrent access
                    conn.execute("PRAGMA journal_mode=WAL")
                    # Enable foreign keys
                    conn.execute("PRAGMA foreign_keys=ON")
                    # Increase cache size for better performance
                    conn.execute("PRAGMA cache_size=-64000")  # 64MB cache
                    self._local.conn = conn
                    break
                except sqlite3.OperationalError as e:
                    if attempt < max_retries - 1:
                        # Exponential backoff
                        time.sleep(retry_delay)
                        retry_delay *= 2
                    else:
                        raise RuntimeError(
                            f"unable to open database file "
                            f"after {max_retries} attempts: {e}"
                        ) from e

        return self._local.conn  # type: ignore[no-any-return]

    def _init_db(self) -> None:
        """Initialize database schema."""
        conn = self._get_connection()

        # Track fingerprint cache
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fingerprint_cache (
                file_hash TEXT PRIMARY KEY,
                fingerprint TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                last_accessed INTEGER NOT NULL,
                metadata TEXT,
                file_mtime INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_last_accessed
            ON fingerprint_cache(last_accessed)
            """
        )

        # Migrate existing schema if needed (add new columns)
        try:
            conn.execute("ALTER TABLE fingerprint_cache ADD COLUMN metadata TEXT")
        except sqlite3.OperationalError:
            pass  # Column already exists
        try:
            conn.execute("ALTER TABLE fingerprint_cache ADD COLUMN file_mtime INTEGER")
        except sqlite3.OperationalError:
            pass  # Column already exists

        # Album cache for duplicate detection
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS album_cache (
                album_path TEXT PRIMARY KEY,
                track_count INTEGER NOT NULL,
                musicbrainz_albumid TEXT,
                album_name TEXT,
                artist_name TEXT,
                total_size INTEGER NOT NULL,
                avg_quality_score REAL NOT NULL,
                quality_info TEXT NOT NULL,
                has_mixed_mb_ids INTEGER NOT NULL,
                disc_number INTEGER,
                disc_subtitle TEXT,
                total_discs INTEGER,
                directory_mtime INTEGER NOT NULL,
                created_at INTEGER NOT NULL,
                last_accessed INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_album_last_accessed
            ON album_cache(last_accessed)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_album_mb_id
            ON album_cache(musicbrainz_albumid)
            WHERE musicbrainz_albumid IS NOT NULL
            """
        )

        # Album tracks (for change detection)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS album_tracks (
                album_path TEXT NOT NULL,
                track_path TEXT NOT NULL,
                track_index INTEGER NOT NULL,
                file_hash TEXT NOT NULL,
                PRIMARY KEY (album_path, track_index),
                FOREIGN KEY (album_path) REFERENCES album_cache(album_path)
                    ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_album_tracks_path
            ON album_tracks(album_path)
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
        Clear all cache entries (fingerprints and albums).

        Returns:
            True if successful
        """
        try:
            conn = self._get_connection()
            conn.execute("DELETE FROM fingerprint_cache")
            conn.execute("DELETE FROM album_tracks")
            conn.execute("DELETE FROM album_cache")
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

    def get_by_path(
        self, file_path: str, file_mtime: int
    ) -> Optional[Tuple[str, Optional[str]]]:
        """
        Get fingerprint and metadata from cache using file path and mtime.

        This is faster than get() because it doesn't require computing SHA256.

        Args:
            file_path: Path to audio file
            file_mtime: File modification time (from st_mtime)

        Returns:
            Tuple of (fingerprint, metadata_json) or None if not found or stale
        """

        # Use filepath+mtime as key
        cache_key = f"{file_path}:{file_mtime}"

        # Try the old file_hash based cache first for backwards compatibility
        # This allows gradual migration without cache invalidation
        conn = self._get_connection()
        cursor = conn.execute(
            """
            SELECT fingerprint, metadata FROM fingerprint_cache
            WHERE file_hash = ?
            """,
            (cache_key,),
        )
        row = cursor.fetchone()

        if row:
            # Update last_accessed
            conn.execute(
                """
                UPDATE fingerprint_cache
                SET last_accessed = ?
                WHERE file_hash = ?
                """,
                (int(time.time()), cache_key),
            )
            conn.commit()
            with self._lock:
                self._hits += 1
            return (str(row[0]), row[1])  # (fingerprint, metadata_json)

        with self._lock:
            self._misses += 1
        return None

    def set_by_path(
        self,
        file_path: str,
        file_mtime: int,
        value: str,
        metadata: Optional[str] = None,
    ) -> None:
        """
        Set fingerprint and metadata in cache using file path and mtime.

        Args:
            file_path: Path to audio file
            file_mtime: File modification time (from st_mtime)
            value: Fingerprint value to cache
            metadata: Optional JSON string of metadata to cache
        """
        # Use filepath+mtime as key
        cache_key = f"{file_path}:{file_mtime}"

        conn = self._get_connection()
        now = int(time.time())
        conn.execute(
            """
            INSERT OR REPLACE INTO fingerprint_cache
            (file_hash, fingerprint, created_at, last_accessed, metadata, file_mtime)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (cache_key, value, now, now, metadata, file_mtime),
        )
        conn.commit()

    def get_album(self, album_path: str) -> Optional[Dict[str, Any]]:
        """
        Get album from cache.

        Args:
            album_path: Path to album directory

        Returns:
            Album data dict or None if not cached or stale
        """
        conn = self._get_connection()
        cursor = conn.execute(
            """
            SELECT track_count, musicbrainz_albumid, album_name, artist_name,
                   total_size, avg_quality_score, quality_info, has_mixed_mb_ids,
                   disc_number, disc_subtitle, total_discs, directory_mtime
            FROM album_cache
            WHERE album_path = ?
            """,
            (album_path,),
        )
        row = cursor.fetchone()

        if not row:
            return None

        # Check if directory has been modified
        from pathlib import Path

        try:
            current_mtime = int(Path(album_path).stat().st_mtime)
            if current_mtime != row[11]:
                # Directory modified, cache is stale
                return None
        except (OSError, FileNotFoundError):
            return None

        # Update last_accessed
        conn.execute(
            """
            UPDATE album_cache
            SET last_accessed = ?
            WHERE album_path = ?
            """,
            (int(time.time()), album_path),
        )
        conn.commit()

        # Get track list
        cursor = conn.execute(
            """
            SELECT track_path, file_hash
            FROM album_tracks
            WHERE album_path = ?
            ORDER BY track_index
            """,
            (album_path,),
        )
        tracks = [(row[0], row[1]) for row in cursor.fetchall()]

        return {
            "track_count": row[0],
            "musicbrainz_albumid": row[1],
            "album_name": row[2],
            "artist_name": row[3],
            "total_size": row[4],
            "avg_quality_score": row[5],
            "quality_info": row[6],
            "has_mixed_mb_ids": bool(row[7]),
            "disc_number": row[8],
            "disc_subtitle": row[9],
            "total_discs": row[10],
            "directory_mtime": row[11],
            "tracks": tracks,
        }

    def set_album(
        self, album_path: str, album_data: Dict[str, Any], tracks: List[Tuple[str, str]]
    ) -> None:
        """
        Store album in cache.

        Args:
            album_path: Path to album directory
            album_data: Album metadata dict
            tracks: List of (track_path, file_hash) tuples
        """
        conn = self._get_connection()
        now = int(time.time())

        # Insert or replace album
        conn.execute(
            """
            INSERT OR REPLACE INTO album_cache (
                album_path, track_count, musicbrainz_albumid, album_name,
                artist_name, total_size, avg_quality_score, quality_info,
                has_mixed_mb_ids, disc_number, disc_subtitle, total_discs,
                directory_mtime, created_at, last_accessed
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                album_path,
                album_data["track_count"],
                album_data.get("musicbrainz_albumid"),
                album_data.get("album_name"),
                album_data.get("artist_name"),
                album_data["total_size"],
                album_data["avg_quality_score"],
                album_data["quality_info"],
                int(album_data.get("has_mixed_mb_ids", False)),
                album_data.get("disc_number"),
                album_data.get("disc_subtitle"),
                album_data.get("total_discs"),
                album_data["directory_mtime"],
                now,
                now,
            ),
        )

        # Delete old tracks
        conn.execute("DELETE FROM album_tracks WHERE album_path = ?", (album_path,))

        # Insert tracks
        for idx, (track_path, file_hash) in enumerate(tracks):
            conn.execute(
                """
                INSERT INTO album_tracks (
                    album_path, track_path, track_index, file_hash
                )
                VALUES (?, ?, ?, ?)
                """,
                (album_path, track_path, idx, file_hash),
            )

        conn.commit()

    def clear_albums(self) -> bool:
        """
        Clear all album cache entries.

        Returns:
            True if successful
        """
        try:
            conn = self._get_connection()
            conn.execute("DELETE FROM album_tracks")
            conn.execute("DELETE FROM album_cache")
            conn.commit()
            return True
        except sqlite3.Error:
            return False

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
