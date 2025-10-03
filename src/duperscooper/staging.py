"""Staging folder management for safe deletion with restoration capability."""

import json
import shutil
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

    def __init__(self, scan_path: Path, command: str = ""):
        """
        Initialize staging manager for a scan path.

        Args:
            scan_path: Path being scanned (determines staging location)
            command: Command that triggered deletion (for manifest)
        """
        self.scan_path = scan_path.resolve()
        self.staging_base = self._get_staging_base(self.scan_path)
        self.batch_id = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.batch_dir = self.staging_base / self.batch_id
        self.command = command
        self.manifest: Dict[str, Any] = {
            "deletion_batch": {
                "id": f"batch_{self.batch_id}",
                "timestamp": datetime.now().isoformat(),
                "duperscooper_version": __version__,
                "command": command,
                "deleted_items": [],
                "total_items_deleted": 0,
                "total_tracks_deleted": 0,
                "space_freed_bytes": 0,
            }
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

            # Generate staged filename: UUID-tracknum-originalname
            staged_filename = f"{album_uuid}-{idx:02d}-{track_path.name}"
            staged_path = self.batch_dir / staged_filename

            # Move file to staging
            shutil.move(str(track_path), str(staged_path))

            tracks_data.append(
                {
                    "original_path": str(track_path),
                    "staged_filename": staged_filename,
                    "size_bytes": staged_path.stat().st_size,
                }
            )

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
    def restore_batch(batch_timestamp: str, staging_base: Optional[Path] = None) -> int:
        """
        Restore all items from a deletion batch.

        Args:
            batch_timestamp: Timestamp of batch to restore (e.g., "2025-10-02_15-30-45")
            staging_base: Base staging directory (if None, searches for batch)

        Returns:
            Number of items restored

        Raises:
            FileNotFoundError: If batch not found
            ValueError: If manifest is invalid
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
                StagingManager._restore_album(item, batch_dir)
                restored_count += 1

        # Remove batch directory after successful restoration
        shutil.rmtree(batch_dir)

        return restored_count

    @staticmethod
    def _restore_album(item: Dict[str, Any], batch_dir: Path) -> None:
        """Restore album by recreating directory and moving tracks back."""
        original_path = Path(item["original_path"])
        original_path.mkdir(parents=True, exist_ok=True)

        for track in item["tracks"]:
            staged_file = batch_dir / track["staged_filename"]
            original_file = Path(track["original_path"])

            if staged_file.exists():
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
