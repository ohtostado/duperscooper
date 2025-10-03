"""Staging folder management for safe deletion with restoration capability."""

import hashlib
import json
import shutil
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import __version__


class StagingManager:
    """
    Manages staging folder for safe deletion with UUID-based flat structure.

    Files are moved to .deletedByDuperscooper/TIMESTAMP/ with UUID prefixes
    to avoid name collisions. Each batch has a manifest.json tracking all
    deletions for restoration.
    """

    def __init__(
        self, scan_path: Path, command: str = "", store_fingerprints: bool = False
    ):
        """
        Initialize staging manager for a scan path.

        Args:
            scan_path: Path being scanned (determines staging location)
            command: Command that triggered deletion (for manifest)
            store_fingerprints: Whether to store compressed audio fingerprints
        """
        self.scan_path = scan_path.resolve()
        self.staging_base = self._get_staging_base(self.scan_path)
        self.batch_id = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.batch_dir = self.staging_base / self.batch_id
        self.command = command
        self.store_fingerprints = store_fingerprints
        self.created_timestamp = datetime.now().isoformat()
        self.manifest: Dict[str, Any] = {
            "_duperscooper_manifest": {
                "format_version": "1.0",
                "created_by": "duperscooper",
                "created_at": self.created_timestamp,
                "created_with_version": __version__,
                "manifest_location": str(self.batch_dir / "manifest.json"),
            },
            "deletion_batch": {
                "id": f"batch_{self.batch_id}",
                "timestamp": self.created_timestamp,
                "duperscooper_version": __version__,
                "command": command,
                "deleted_items": [],
                "total_items_deleted": 0,
                "total_tracks_deleted": 0,
                "space_freed_bytes": 0,
            },
        }

    def stage_album(
        self,
        album: Any,
        reason: str,
        duplicate_of: Optional[str] = None,
        similarity: Optional[float] = None,
    ) -> None:
        """
        Stage an album for deletion by moving to staging folder.

        Args:
            album: Album object to stage
            reason: Reason for deletion (e.g., "worst_quality_duplicate")
            duplicate_of: Path to the album this is a duplicate of
            similarity: Similarity percentage to the kept album
        """
        # Generate UUID for this album
        album_uuid = uuid.uuid4().hex[:8]

        # Create batch directory if needed
        self.batch_dir.mkdir(parents=True, exist_ok=True)

        # Move tracks with UUID prefix
        tracks_data = []
        for idx, track_path_str in enumerate(album.tracks, 1):
            track_path = Path(track_path_str)

            if not track_path.exists():
                continue  # Skip if already moved/deleted

            # Compute SHA256 hash before moving (required)
            sha256 = self._compute_sha256(track_path)

            # Get compressed fingerprint before moving (optional, if enabled)
            fingerprint = None
            if self.store_fingerprints:
                fingerprint = self._get_compressed_fingerprint(track_path)

            # Generate staged filename: UUID-tracknum-originalname
            staged_filename = f"{album_uuid}-{idx:02d}-{track_path.name}"
            staged_path = self.batch_dir / staged_filename

            # Move file to staging
            shutil.move(str(track_path), str(staged_path))

            # Build track entry
            track_entry = {
                "original_path": str(track_path),
                "staged_filename": staged_filename,
                "size_bytes": staged_path.stat().st_size,
                "sha256": sha256,
            }

            # Add fingerprint if available
            if fingerprint:
                track_entry["fingerprint_compressed"] = fingerprint

            tracks_data.append(track_entry)

        # Remove empty album directory
        try:
            album.path.rmdir()
        except OSError:
            # Directory not empty (might have non-audio files)
            # Leave it for now, user can clean up manually
            pass

        # Update manifest
        self.manifest["deletion_batch"]["deleted_items"].append(
            {
                "id": album_uuid,
                "type": "album",
                "original_path": str(album.path),
                "album_name": album.album_name,
                "artist_name": album.artist_name,
                "track_count": album.track_count,
                "total_size_bytes": album.total_size,
                "quality_info": album.quality_info,
                "quality_score": album.avg_quality_score,
                "deletion_reason": reason,
                "duplicate_of": duplicate_of,
                "similarity": similarity,
                "musicbrainz_albumid": album.musicbrainz_albumid,
                "has_metadata": bool(
                    album.musicbrainz_albumid
                    or (album.album_name and album.artist_name)
                ),
                "tracks": tracks_data,
            }
        )

        self.manifest["deletion_batch"]["total_items_deleted"] += 1
        self.manifest["deletion_batch"]["total_tracks_deleted"] += len(tracks_data)
        self.manifest["deletion_batch"]["space_freed_bytes"] += album.total_size

    @staticmethod
    def _compute_sha256(file_path: Path) -> str:
        """
        Compute SHA256 hash of a file.

        Args:
            file_path: Path to file

        Returns:
            Hexadecimal SHA256 hash string
        """
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            # Read in 64KB chunks to handle large files efficiently
            for chunk in iter(lambda: f.read(65536), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()

    @staticmethod
    def _get_compressed_fingerprint(file_path: Path) -> Optional[str]:
        """
        Get compressed Chromaprint fingerprint from fpcalc.

        Args:
            file_path: Path to audio file

        Returns:
            Base64-encoded compressed fingerprint, or None if fpcalc fails
        """
        try:
            result = subprocess.run(
                ["fpcalc", "-json", str(file_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                fp = data.get("fingerprint")
                return fp if isinstance(fp, str) else None
        except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
            pass
        return None

    def finalize(self) -> Dict[str, Any]:
        """
        Write manifest and finish staging.

        Returns:
            Manifest dictionary with deletion statistics
        """
        if self.manifest["deletion_batch"]["total_items_deleted"] == 0:
            # Nothing was staged, don't create empty batch
            return self.manifest

        manifest_path = self.batch_dir / "manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(self.manifest, f, indent=2)

        # Make manifest read-only to prevent accidental modification
        manifest_path.chmod(0o444)

        return self.manifest

    def _get_staging_base(self, scan_path: Path) -> Path:
        """
        Get staging base directory for scan path.

        Creates .deletedByDuperscooper in same directory as scan path
        to avoid slow cross-filesystem moves.

        Args:
            scan_path: Path being scanned

        Returns:
            Path to .deletedByDuperscooper directory
        """
        # Use the scan path's parent directory for staging
        # This ensures it's on the same filesystem
        if scan_path.is_dir():
            root = scan_path.parent
        else:
            # If scan_path is a file, use its parent's parent
            root = scan_path.parent.parent

        return root / ".deletedByDuperscooper"

    @staticmethod
    def format_size(size_bytes: int) -> str:
        """Format byte size as human readable string."""
        size: float = float(size_bytes)
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"

    @staticmethod
    def list_batches(staging_base: Optional[Path] = None) -> List[Dict[str, Any]]:
        """
        List all deletion batches in staging.

        Args:
            staging_base: Base staging directory (if None, searches common locations)

        Returns:
            List of batch info dictionaries
        """
        batches = []

        # If no staging base provided, search common locations
        search_paths = []
        if staging_base:
            search_paths = [staging_base]
        else:
            # Search common mount points and current directory
            for root in [
                Path.cwd(),
                Path.home(),
                Path("/music"),
                Path("/media"),
                Path("/mnt"),
            ]:
                staging_dir = root / ".deletedByDuperscooper"
                if staging_dir.exists():
                    search_paths.append(staging_dir)

        for base in search_paths:
            if not base.exists():
                continue

            for batch_dir in sorted(base.iterdir()):
                if not batch_dir.is_dir():
                    continue

                manifest_path = batch_dir / "manifest.json"
                if not manifest_path.exists():
                    continue

                try:
                    with open(manifest_path) as f:
                        manifest = json.load(f)

                    batch_info = manifest["deletion_batch"]
                    batch_info["staging_path"] = str(batch_dir)
                    batches.append(batch_info)
                except (json.JSONDecodeError, KeyError):
                    # Invalid manifest, skip
                    continue

        return batches

    @staticmethod
    def restore_batch(
        batch_timestamp: str,
        staging_base: Optional[Path] = None,
        restore_to: Optional[Path] = None,
    ) -> int:
        """
        Restore all items from a deletion batch.

        Args:
            batch_timestamp: Timestamp of batch to restore (e.g., "2025-10-02_15-30-45")
            staging_base: Base staging directory (if None, searches for batch)
            restore_to: Custom restoration root path (if None, uses original paths)

        Returns:
            Number of items restored

        Raises:
            FileNotFoundError: If batch not found
            ValueError: If manifest is invalid

        Note:
            If restore_to is provided, files are restored to:
              restore_to/<original_relative_path>
            This is useful when original locations are unavailable.
        """
        # Find batch
        batch_dir = None
        if staging_base:
            batch_dir = staging_base / batch_timestamp
        else:
            # Search for batch in all staging locations
            batches = StagingManager.list_batches()
            for batch in batches:
                if batch_timestamp in batch["staging_path"]:
                    batch_dir = Path(batch["staging_path"])
                    break

        if not batch_dir or not batch_dir.exists():
            raise FileNotFoundError(f"Batch not found: {batch_timestamp}")

        manifest_path = batch_dir / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"Manifest not found: {manifest_path}")

        with open(manifest_path) as f:
            manifest = json.load(f)

        restored_count = 0
        for item in manifest["deletion_batch"]["deleted_items"]:
            if item["type"] == "album":
                StagingManager._restore_album(item, batch_dir, restore_to)
                restored_count += 1

        # Remove batch directory after successful restoration
        shutil.rmtree(batch_dir)

        return restored_count

    @staticmethod
    def _restore_album(
        item: Dict[str, Any], batch_dir: Path, restore_to: Optional[Path] = None
    ) -> None:
        """
        Restore album by recreating directory and moving tracks back.

        Verifies SHA256 hash of each track before moving to ensure integrity.

        Args:
            item: Album item from manifest
            batch_dir: Directory containing staged files
            restore_to: Custom restoration root (if None, uses original paths)

        Raises:
            ValueError: If SHA256 hash verification fails for any track

        Note:
            If restore_to is provided, album is restored to:
              restore_to/<album_directory_name>/
            Otherwise restored to original path from manifest.
        """
        if restore_to:
            # Restore to custom location: restore_to/<album_dir_name>/
            original_path = Path(item["original_path"])
            album_dir_name = original_path.name
            restore_path = restore_to / album_dir_name
            restore_path.mkdir(parents=True, exist_ok=True)
        else:
            # Restore to original location
            restore_path = Path(item["original_path"])
            restore_path.mkdir(parents=True, exist_ok=True)

        for track in item["tracks"]:
            staged_file = batch_dir / track["staged_filename"]

            if restore_to:
                # Use just the filename in the custom location
                original_file_path = Path(track["original_path"])
                original_file = restore_path / original_file_path.name
            else:
                # Use original path
                original_file = Path(track["original_path"])

            if staged_file.exists():
                # Verify SHA256 hash if present in manifest
                if "sha256" in track:
                    computed_hash = StagingManager._compute_sha256(staged_file)
                    expected_hash = track["sha256"]
                    if computed_hash != expected_hash:
                        raise ValueError(
                            f"SHA256 mismatch for {staged_file.name}\n"
                            f"Expected: {expected_hash}\n"
                            f"Computed: {computed_hash}\n"
                            f"File may be corrupted or tampered with"
                        )

                # Hash verified or not present, move file
                shutil.move(str(staged_file), str(original_file))

    @staticmethod
    def empty_batches(
        staging_base: Optional[Path] = None,
        older_than_days: Optional[int] = None,
        keep_last: Optional[int] = None,
    ) -> int:
        """
        Permanently delete staging batches.

        Args:
            staging_base: Base staging directory (if None, searches all)
            older_than_days: Only delete batches older than N days
            keep_last: Keep the N most recent batches

        Returns:
            Number of batches deleted
        """
        batches = StagingManager.list_batches(staging_base)

        if not batches:
            return 0

        # Sort by timestamp (newest first)
        batches.sort(key=lambda b: b["timestamp"], reverse=True)

        deleted_count = 0
        for idx, batch in enumerate(batches):
            staging_path = Path(batch["staging_path"])

            # Apply filters
            if keep_last and idx < keep_last:
                continue  # Keep this batch

            if older_than_days:
                batch_time = datetime.fromisoformat(batch["timestamp"])
                age_days = (datetime.now() - batch_time).days
                if age_days < older_than_days:
                    continue  # Too recent

            # Delete batch
            if staging_path.exists():
                shutil.rmtree(staging_path)
                deleted_count += 1

        return deleted_count

    @staticmethod
    def find_manifests(paths: List[Path]) -> List[Dict[str, Any]]:
        """
        Recursively find all duperscooper manifest.json files in given paths.

        Args:
            paths: List of paths to search recursively

        Returns:
            List of manifest info dictionaries with metadata
        """
        manifests = []

        for search_path in paths:
            if not search_path.exists():
                continue

            # Recursively find all manifest.json files
            for manifest_path in search_path.rglob("manifest.json"):
                try:
                    with open(manifest_path) as f:
                        data = json.load(f)

                    # Check if this is a duperscooper manifest
                    if "_duperscooper_manifest" not in data:
                        continue

                    manifest_info = data["_duperscooper_manifest"]
                    deletion_batch = data.get("deletion_batch", {})

                    manifests.append(
                        {
                            "manifest_path": str(manifest_path),
                            "manifest_dir": str(manifest_path.parent),
                            "created_at": manifest_info.get("created_at", "unknown"),
                            "created_with_version": manifest_info.get(
                                "created_with_version", "unknown"
                            ),
                            "format_version": manifest_info.get(
                                "format_version", "1.0"
                            ),
                            "original_location": manifest_info.get(
                                "manifest_location", str(manifest_path)
                            ),
                            "batch_id": deletion_batch.get("id", "unknown"),
                            "total_items": deletion_batch.get("total_items_deleted", 0),
                            "space_freed_bytes": deletion_batch.get(
                                "space_freed_bytes", 0
                            ),
                            "command": deletion_batch.get("command", ""),
                        }
                    )
                except (json.JSONDecodeError, KeyError, OSError):
                    # Skip invalid or inaccessible manifests
                    continue

        # Sort by creation time (newest first)
        manifests.sort(key=lambda m: m["created_at"], reverse=True)

        return manifests

    @staticmethod
    def restore_from_manifest(
        manifest_path: Path, restore_to: Optional[Path] = None
    ) -> int:
        """
        Restore files from a specific manifest file.

        Args:
            manifest_path: Path to manifest.json file
            restore_to: Custom restoration root path (if None, uses original paths)

        Returns:
            Number of items restored

        Raises:
            FileNotFoundError: If manifest doesn't exist
            ValueError: If manifest is invalid or not a duperscooper manifest
        """
        if not manifest_path.exists():
            raise FileNotFoundError(f"Manifest not found: {manifest_path}")

        with open(manifest_path) as f:
            manifest = json.load(f)

        # Validate this is a duperscooper manifest
        if "_duperscooper_manifest" not in manifest:
            raise ValueError(
                f"Not a duperscooper manifest: {manifest_path}\n"
                "Missing '_duperscooper_manifest' identifier block"
            )

        batch_dir = manifest_path.parent
        restored_count = 0

        for item in manifest["deletion_batch"]["deleted_items"]:
            if item["type"] == "album":
                StagingManager._restore_album(item, batch_dir, restore_to)
                restored_count += 1

        # Remove manifest directory after successful restoration
        shutil.rmtree(batch_dir)

        return restored_count
