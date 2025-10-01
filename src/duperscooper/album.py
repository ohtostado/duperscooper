"""Album detection and metadata extraction for duplicate album finding."""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from .hasher import AudioHasher


@dataclass
class Album:
    """Represents an album with metadata and fingerprints."""

    path: Path  # Album directory path
    tracks: List[Path]  # Audio files in album (sorted by name)
    track_count: int  # Number of tracks
    musicbrainz_albumid: Optional[str]  # MB album ID (if consistent across all tracks)
    album_name: Optional[str]  # Album title from tags
    artist_name: Optional[str]  # Artist from tags
    total_size: int  # Sum of file sizes in bytes
    avg_quality_score: float  # Average quality of tracks
    fingerprints: List[List[int]]  # Perceptual fingerprints for each track
    has_mixed_mb_ids: bool  # Flag if tracks have inconsistent MB IDs
    quality_info: str  # e.g., "FLAC 44.1kHz 16bit (avg)"


class AlbumScanner:
    """Scans directories to identify albums and extract metadata."""

    def __init__(self, hasher: AudioHasher, verbose: bool = False):
        """
        Initialize album scanner.

        Args:
            hasher: AudioHasher instance for fingerprinting
            verbose: Enable verbose output
        """
        self.hasher = hasher
        self.verbose = verbose

    def scan_albums(self, paths: List[Path], max_workers: int = 8) -> List[Album]:
        """
        Discover all albums in given paths.

        Args:
            paths: List of paths to search for albums
            max_workers: Number of worker threads for parallel fingerprinting

        Returns:
            List of Album objects
        """
        if self.verbose:
            print("Discovering album directories...")

        # Find all directories containing audio files
        album_dirs = self._find_album_directories(paths)

        if self.verbose:
            print(f"Found {len(album_dirs)} album directories")

        # Extract metadata and fingerprints for each album
        albums = []
        for idx, album_dir in enumerate(album_dirs, 1):
            if self.verbose and idx % 100 == 0:
                print(f"Processing album {idx}/{len(album_dirs)}...")

            try:
                album = self.extract_album_metadata(album_dir)
                albums.append(album)
            except Exception as e:
                if self.verbose:
                    print(f"Error processing {album_dir}: {e}")

        if self.verbose:
            print(f"Successfully processed {len(albums)} albums")

        return albums

    def _find_album_directories(self, paths: List[Path]) -> List[Path]:
        """
        Find all directories that contain audio files.

        Args:
            paths: List of paths to search

        Returns:
            List of directory paths containing audio files
        """
        album_dirs = set()

        for path in paths:
            if not path.exists():
                continue

            if path.is_file():
                # If single file, use its parent directory
                if self.hasher.is_audio_file(path):
                    album_dirs.add(path.parent)
            elif path.is_dir():
                # Recursively find all directories with audio files
                for file_path in path.rglob("*"):
                    if file_path.is_file() and self.hasher.is_audio_file(file_path):
                        album_dirs.add(file_path.parent)

        return sorted(album_dirs)

    def extract_album_metadata(self, album_path: Path) -> Album:
        """
        Extract metadata from all tracks in an album directory.

        Args:
            album_path: Path to album directory

        Returns:
            Album object with metadata and fingerprints
        """
        # Find all audio files in directory (non-recursive)
        tracks = sorted(
            [
                f
                for f in album_path.iterdir()
                if f.is_file() and self.hasher.is_audio_file(f)
            ]
        )

        if not tracks:
            raise ValueError(f"No audio files found in {album_path}")

        # Extract MusicBrainz album IDs from all tracks
        mb_ids = []
        for track in tracks:
            mb_id = self.get_musicbrainz_albumid(track)
            if mb_id:
                mb_ids.append(mb_id)

        # Check for consistency
        unique_mb_ids = set(mb_ids)
        has_mixed_mb_ids = len(unique_mb_ids) > 1
        musicbrainz_albumid = None

        if len(unique_mb_ids) == 1:
            # All tracks have same MB ID
            musicbrainz_albumid = unique_mb_ids.pop()
        elif has_mixed_mb_ids and self.verbose:
            print(f"Warning: {album_path} has mixed MusicBrainz IDs: {unique_mb_ids}")

        # Extract album/artist names from first track as fallback
        album_name, artist_name = self.get_album_tags(tracks[0])

        # Get fingerprints for all tracks
        fingerprints: List[List[int]] = []
        total_size = 0
        quality_scores = []

        for track in tracks:
            # Get fingerprint from cache or compute
            fingerprint = self.hasher.compute_audio_hash(track, "perceptual")
            # Type is List[int] because algorithm is "perceptual"
            assert isinstance(fingerprint, list)
            fingerprints.append(fingerprint)

            # Get file size
            total_size += track.stat().st_size

            # Get quality metadata
            try:
                metadata = self.hasher.get_audio_metadata(track)
                quality_score = self.hasher.calculate_quality_score(metadata)
                quality_scores.append(quality_score)
            except Exception:
                quality_scores.append(0.0)

        # Calculate average quality score
        avg_quality_score = (
            sum(quality_scores) / len(quality_scores) if quality_scores else 0.0
        )

        # Format quality info
        try:
            first_metadata = self.hasher.get_audio_metadata(tracks[0])
            quality_info = self.hasher.format_audio_info(first_metadata) + " (avg)"
        except Exception:
            quality_info = "Unknown"

        return Album(
            path=album_path,
            tracks=tracks,
            track_count=len(tracks),
            musicbrainz_albumid=musicbrainz_albumid,
            album_name=album_name,
            artist_name=artist_name,
            total_size=total_size,
            avg_quality_score=avg_quality_score,
            fingerprints=fingerprints,
            has_mixed_mb_ids=has_mixed_mb_ids,
            quality_info=quality_info,
        )

    def get_musicbrainz_albumid(self, file_path: Path) -> Optional[str]:
        """
        Extract MusicBrainz album ID from audio file metadata.

        Args:
            file_path: Path to audio file

        Returns:
            MusicBrainz album ID or None if not found
        """
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "quiet",
                    "-print_format",
                    "json",
                    "-show_format",
                    str(file_path),
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0:
                return None

            data = json.loads(result.stdout)
            tags = data.get("format", {}).get("tags", {})

            # Try common MusicBrainz tag names (case variations)
            for key in tags:
                if key.upper() == "MUSICBRAINZ_ALBUMID":
                    return str(tags[key])

            return None
        except Exception:
            return None

    def get_album_tags(self, file_path: Path) -> Tuple[Optional[str], Optional[str]]:
        """
        Extract album name and artist from metadata.

        Args:
            file_path: Path to audio file

        Returns:
            Tuple of (album_name, artist_name), either may be None
        """
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "quiet",
                    "-print_format",
                    "json",
                    "-show_format",
                    str(file_path),
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0:
                return (None, None)

            data = json.loads(result.stdout)
            tags = data.get("format", {}).get("tags", {})

            # Extract album and artist
            album_name = None
            artist_name = None

            for key, value in tags.items():
                key_upper = key.upper()
                if key_upper in ("ALBUM", "ALBUM_TITLE"):
                    album_name = value
                elif key_upper in ("ARTIST", "ALBUM_ARTIST", "ALBUMARTIST"):
                    artist_name = value

            return (album_name, artist_name)
        except Exception:
            return (None, None)
