"""Album detection and metadata extraction for duplicate album finding."""

import json
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

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
    match_method: Optional[str] = None  # How this album was matched to its group
    # Partial matching info (set when album is part of partial match)
    is_partial_match: bool = False  # True if matched with different track count
    overlap_percentage: Optional[float] = (
        None  # % of tracks present (for partial matches)
    )
    missing_track_indices: Optional[List[int]] = None  # Indices of missing tracks


class AlbumScanner:
    """Scans directories to identify albums and extract metadata."""

    def __init__(
        self, hasher: AudioHasher, verbose: bool = False, simple_progress: bool = False
    ):
        """
        Initialize album scanner.

        Args:
            hasher: AudioHasher instance for fingerprinting
            verbose: Enable verbose output
            simple_progress: Use simple parseable progress instead of tqdm
        """
        self.hasher = hasher
        self.verbose = verbose
        self.simple_progress = simple_progress
        self.album_cache_hits = 0
        self.album_cache_misses = 0

    def scan_albums(
        self,
        paths: List[Path],
        max_workers: int = 8,
        progress_callback: Optional[Callable[[str, int], None]] = None,
        should_stop: Optional[Callable[[], bool]] = None,
        should_stop_dir_scan: Optional[Callable[[], bool]] = None,
        on_metadata_start: Optional[Callable[[], None]] = None,
    ) -> List[Album]:
        """
        Discover all albums in given paths.

        Args:
            paths: List of paths to search for albums
            max_workers: Number of worker threads for parallel fingerprinting
            progress_callback: Optional callback function(message, percentage)
                for real-time progress updates
            should_stop: Optional callback that returns True if scan should stop
                (applies to metadata extraction and duplicate finding)
            should_stop_dir_scan: Optional callback for directory scanning only
                If not provided, falls back to should_stop
            on_metadata_start: Optional callback invoked when metadata extraction
                phase starts (after directory discovery completes)

        Returns:
            List of Album objects
        """
        if self.verbose:
            print("Discovering album directories...", flush=True)

        # Use separate callback for directory scanning if provided
        dir_scan_callback = (
            should_stop_dir_scan if should_stop_dir_scan else should_stop
        )

        # Find all directories containing audio files
        # Pass a wrapper callback that reports directory discovery progress
        if progress_callback:

            def dir_callback(message: str) -> None:
                # Directory discovery is roughly 10% of total work
                progress_callback(message, 0)

            album_dirs = self._find_album_directories(
                paths, dir_callback, dir_scan_callback
            )
        else:
            album_dirs = self._find_album_directories(
                paths, should_stop=dir_scan_callback
            )

        # Note: We don't check should_stop here because it might be stop_and_process
        # The caller will handle checking _should_stop vs _stop_and_process

        if self.verbose:
            print(f"Found {len(album_dirs)} album directories", flush=True)

        # Report total count to callback
        if progress_callback:
            progress_callback(
                f"Found {len(album_dirs)} albums, now scanning metadata...", 0
            )

        # Invoke metadata start callback (for GUI to update button state)
        if on_metadata_start:
            on_metadata_start()

        # Extract metadata and fingerprints for each album
        albums = []
        total_albums = len(album_dirs)

        if self.verbose and self.simple_progress:
            # Simple parseable progress for GUI/scripts
            iterator = album_dirs
        elif self.verbose:
            # Fancy progress with tqdm
            from tqdm import tqdm

            iterator = tqdm(
                album_dirs,
                desc="Scanning albums",
                unit="album",
                disable=False,
            )
        else:
            iterator = album_dirs

        for idx, album_dir in enumerate(iterator, 1):
            # Check for stop request before processing each album
            if should_stop and should_stop():
                print(
                    f"DEBUG: Stop detected in scan_albums metadata extraction "
                    f"at {idx}/{total_albums} albums"
                )
                break

            try:
                album = self.extract_album_metadata(album_dir, should_stop)
                if album is None:
                    # Stopped during metadata extraction
                    break
                albums.append(album)

                # Output simple progress
                if self.verbose and self.simple_progress:
                    percent = (idx / total_albums) * 100
                    msg = f"PROGRESS: Scanning albums {idx}/{total_albums} ({percent:.1f}%)"  # noqa: E501
                    print(msg, flush=True)

                # Invoke progress callback if provided
                if progress_callback:
                    percent = int((idx / total_albums) * 100)
                    # Include cache stats for debugging
                    total_processed = self.album_cache_hits + self.album_cache_misses
                    if total_processed > 0:
                        hit_rate = self.album_cache_hits / total_processed * 100
                        msg = (
                            f"Scanned {idx}/{total_albums} albums "
                            f"(cache: {hit_rate:.0f}% hits)"
                        )
                    else:
                        msg = f"Scanned {idx}/{total_albums} albums"
                    progress_callback(msg, percent)

            except Exception as e:
                if self.verbose:
                    if self.simple_progress:
                        print(f"ERROR: {album_dir}: {e}", flush=True)
                    else:
                        # tqdm.write prints without disrupting progress bar
                        from tqdm import tqdm

                        tqdm.write(f"Error processing {album_dir}: {e}")

        if self.verbose:
            print(f"Successfully processed {len(albums)} albums", flush=True)
            total = max(self.album_cache_hits + self.album_cache_misses, 1)
            hit_pct = self.album_cache_hits / total * 100
            print(
                f"Album cache: {self.album_cache_hits} hits, "
                f"{self.album_cache_misses} misses ({hit_pct:.1f}% hit rate)",
                flush=True,
            )

        # Report cache stats via callback
        if progress_callback and (self.album_cache_hits + self.album_cache_misses) > 0:
            hit_rate = (
                self.album_cache_hits
                / (self.album_cache_hits + self.album_cache_misses)
                * 100
            )
            progress_callback(
                f"Scan complete - Album cache: {self.album_cache_hits} hits, "
                f"{self.album_cache_misses} misses ({hit_rate:.1f}% hit rate)",
                100,
            )

        return albums

    def _find_album_directories(
        self,
        paths: List[Path],
        progress_callback: Optional[Callable[[str], None]] = None,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> List[Path]:
        """
        Find all directories that contain audio files.

        Args:
            paths: List of paths to search
            progress_callback: Optional callback for progress updates during traversal
            should_stop: Optional callback that returns True if scan should stop

        Returns:
            List of directory paths containing audio files
        """
        album_dirs = set()
        files_checked = 0
        stopped = False

        for path in paths:
            if not path.exists():
                continue

            # Check for stop request
            if should_stop and should_stop():
                stopped = True
                break

            if path.is_file():
                # If single file, use its parent directory
                if self.hasher.is_audio_file(path):
                    album_dirs.add(path.parent)
            elif path.is_dir():
                # Recursively find all directories with audio files
                for file_path in path.rglob("*"):
                    # Check for stop request every 100 files
                    if files_checked % 100 == 0 and should_stop and should_stop():
                        print(
                            f"DEBUG: Stop detected in _find_album_directories "
                            f"at {files_checked} files"
                        )
                        stopped = True
                        break

                    if file_path.is_file():
                        files_checked += 1
                        # Report progress every 100 files (for testing/debugging)
                        # TODO: Change to 1000 for production to reduce spam
                        if progress_callback and files_checked % 100 == 0:
                            progress_callback(
                                f"Finding albums... (checked {files_checked} files, "
                                f"found {len(album_dirs)} albums so far)"
                            )
                        if self.hasher.is_audio_file(file_path):
                            album_dirs.add(file_path.parent)

                # Check if we stopped during the inner loop
                if stopped:
                    break
        return sorted(album_dirs)

    def extract_album_metadata(
        self, album_path: Path, should_stop: Optional[Callable[[], bool]] = None
    ) -> Optional[Album]:
        """
        Extract metadata from all tracks in an album directory.

        Args:
            album_path: Path to album directory
            should_stop: Optional callback to check if processing should stop

        Returns:
            Album object with metadata and fingerprints, or None if stopped
        """
        # Try to get album from cache
        cache_backend = getattr(self.hasher, "_cache", None)
        cached_album = None
        if cache_backend:
            cached_album = cache_backend.get_album(str(album_path))

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

        # Check if cache is valid by comparing track list
        if cached_album:
            cached_track_paths = [t[0] for t in cached_album["tracks"]]
            current_track_paths = [str(t) for t in tracks]

            if cached_track_paths == current_track_paths:
                # Album metadata is cached, but still need to get fingerprints
                # Get fingerprints from track-level cache
                import time

                t_start = time.time()
                cached_fingerprints: List[List[int]] = []
                all_tracks_cached = True  # Track if all fingerprints were cached

                for i, track in enumerate(tracks):
                    # Check for stop before fingerprinting each track
                    if should_stop and should_stop():
                        print(
                            f"DEBUG: Stop detected in extract_album_metadata "
                            f"(cached) at track {i+1}/{len(tracks)}"
                        )
                        return None
                    t1 = time.time()
                    fingerprint = self.hasher.compute_audio_hash(track, "perceptual")
                    t2 = time.time()
                    elapsed = t2 - t1

                    # If fingerprinting took >0.01s, it was a cache miss
                    if elapsed > 0.01:
                        all_tracks_cached = False

                    print(f"DEBUG: Track {i+1}/{len(tracks)} hash took {elapsed:.3f}s")
                    assert isinstance(fingerprint, list)
                    cached_fingerprints.append(fingerprint)
                total_time = time.time() - t_start
                ntracks = len(tracks)
                msg = f"DEBUG: Total fingerprints: {total_time:.3f}s for {ntracks}"
                print(msg)

                # Only count as cache hit if ALL tracks were cached
                if all_tracks_cached:
                    self.album_cache_hits += 1
                else:
                    self.album_cache_misses += 1

                return Album(
                    path=album_path,
                    tracks=tracks,
                    track_count=cached_album["track_count"],
                    musicbrainz_albumid=cached_album["musicbrainz_albumid"],
                    album_name=cached_album["album_name"],
                    artist_name=cached_album["artist_name"],
                    total_size=cached_album["total_size"],
                    avg_quality_score=cached_album["avg_quality_score"],
                    fingerprints=cached_fingerprints,
                    has_mixed_mb_ids=cached_album["has_mixed_mb_ids"],
                    quality_info=cached_album["quality_info"],
                )

        # Cache miss or invalid, extract metadata
        self.album_cache_misses += 1

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
        track_hashes = []

        for i, track in enumerate(tracks):
            # Check for stop before fingerprinting each track
            if should_stop and should_stop():
                print(
                    f"DEBUG: Stop detected in extract_album_metadata "
                    f"(uncached) at track {i+1}/{len(tracks)}"
                )
                return None

            # Get fingerprint from cache or compute
            fingerprint = self.hasher.compute_audio_hash(track, "perceptual")
            # Type is List[int] because algorithm is "perceptual"
            assert isinstance(fingerprint, list)
            fingerprints.append(fingerprint)

            # Get file size
            total_size += track.stat().st_size

            # Get file hash for cache storage
            file_hash = self.hasher.compute_file_hash(track)
            track_hashes.append((str(track), file_hash))

            # Get quality metadata (using fast cached version)
            try:
                metadata = self.hasher.get_audio_metadata_cached(track)
                quality_score = self.hasher.calculate_quality_score(metadata)
                quality_scores.append(quality_score)
            except Exception:
                quality_scores.append(0.0)

        # Calculate average quality score
        avg_quality_score = (
            sum(quality_scores) / len(quality_scores) if quality_scores else 0.0
        )

        # Format quality info (using fast cached version)
        try:
            first_metadata = self.hasher.get_audio_metadata_cached(tracks[0])
            quality_info = self.hasher.format_audio_info(first_metadata)
        except Exception:
            quality_info = "Unknown"

        # Store in cache
        if cache_backend:
            album_data = {
                "track_count": len(tracks),
                "musicbrainz_albumid": musicbrainz_albumid,
                "album_name": album_name,
                "artist_name": artist_name,
                "total_size": total_size,
                "avg_quality_score": avg_quality_score,
                "quality_info": quality_info,
                "has_mixed_mb_ids": has_mixed_mb_ids,
                "directory_mtime": int(album_path.stat().st_mtime),
            }
            cache_backend.set_album(str(album_path), album_data, track_hashes)

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


class AlbumDuplicateFinder:
    """Find duplicate albums using various matching strategies."""

    def __init__(
        self,
        hasher: AudioHasher,
        verbose: bool = False,
        allow_partial: bool = False,
        min_overlap: float = 70.0,
        similarity_threshold: float = 97.0,
    ):
        """
        Initialize album duplicate finder.

        Args:
            hasher: AudioHasher instance for fingerprint comparison
            verbose: Enable verbose output
            allow_partial: Allow matching albums with different track counts
            min_overlap: Minimum % of tracks that must match for partial albums
            similarity_threshold: Minimum similarity % for fingerprint matching
        """
        self.hasher = hasher
        self.verbose = verbose
        self.allow_partial = allow_partial
        self.min_overlap = min_overlap
        self.similarity_threshold = similarity_threshold

    def find_duplicates(
        self,
        albums: List[Album],
        strategy: str = "auto",
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> List[List[Album]]:
        """
        Find duplicate albums using specified matching strategy.

        Args:
            albums: List of Album objects to check for duplicates
            strategy: Matching strategy - "musicbrainz", "fingerprint", or "auto"
            should_stop: Optional callback to check if processing should stop

        Returns:
            List of duplicate groups (each group is a list of Album objects)
        """
        print(
            f"DEBUG: find_duplicates called with {len(albums)} albums, "
            f"should_stop={'present' if should_stop else 'None'}"
        )
        duplicate_groups = []

        if strategy == "musicbrainz":
            duplicate_groups = self._match_by_musicbrainz(albums, should_stop)
        elif strategy == "fingerprint":
            duplicate_groups = self._match_by_fingerprints(albums, should_stop)
        elif strategy == "auto":
            # Auto: Establish canonical albums from MB IDs/metadata,
            # then match untagged albums against them via fingerprints
            duplicate_groups = self._match_canonical(albums, should_stop)
        else:
            raise ValueError(
                f"Unknown strategy: {strategy}. "
                "Use 'musicbrainz', 'fingerprint', or 'auto'"
            )

        # Check for stop before annotating
        if should_stop and should_stop():
            return duplicate_groups

        # Annotate partial matches if enabled
        if self.allow_partial:
            for group in duplicate_groups:
                if should_stop and should_stop():
                    return duplicate_groups
                self._annotate_partial_matches(group)

        return duplicate_groups

    def _match_canonical(
        self, albums: List[Album], should_stop: Optional[Callable[[], bool]] = None
    ) -> List[List[Album]]:
        """
        Match albums using canonical approach.

        1. Establish canonical albums from MusicBrainz IDs or metadata tags
        2. Match untagged albums against canonical versions via fingerprints
        3. Merge groups that share the same canonical album

        Args:
            albums: List of Album objects
            should_stop: Optional callback to check if processing should stop

        Returns:
            List of duplicate groups with canonical album identification
        """
        # Separate canonical and untagged albums
        canonical_albums = []
        untagged_albums = []

        for album in albums:
            if should_stop and should_stop():
                return []
            # Canonical if has MB ID OR both album and artist names
            if album.musicbrainz_albumid:
                album.match_method = "MusicBrainz Album ID"
                canonical_albums.append(album)
            elif album.album_name and album.artist_name:
                album.match_method = "ID3 Album/Artist Tags"
                canonical_albums.append(album)
            else:
                untagged_albums.append(album)

        if self.verbose:
            print(
                f"Found {len(canonical_albums)} canonical albums, "
                f"{len(untagged_albums)} untagged"
            )

        # Do fingerprint matching on canonical albums to catch same album
        # with different/missing MB IDs
        canonical_fp_groups = self._match_by_fingerprints(canonical_albums, should_stop)

        # Merge canonical groups that share MB IDs (preserves match_method)
        merged_canonical = self._merge_groups_by_musicbrainz(canonical_fp_groups)

        # Now match each untagged album against canonical groups
        groups_dict: Dict[int, List[Album]] = {}
        for idx, group in enumerate(merged_canonical):
            groups_dict[idx] = list(group)

        # Match untagged albums against canonical groups
        for untagged in untagged_albums:
            if should_stop and should_stop():
                break
            best_match_idx = None
            best_similarity = 0.0

            # Compare against each canonical group
            for idx, canonical_group in groups_dict.items():
                if should_stop and should_stop():
                    break
                # Compare against first album in canonical group (representative)
                canonical_rep = canonical_group[0]

                # Skip if track counts differ and partial matching is disabled
                if (
                    not self.allow_partial
                    and untagged.track_count != canonical_rep.track_count
                ):
                    continue

                # Calculate similarity (handles both exact and partial matching)
                similarity = self.album_similarity(untagged, canonical_rep)

                if similarity >= 97.0 and similarity > best_similarity:
                    best_similarity = similarity
                    best_match_idx = idx

            # Add to best matching canonical group
            if best_match_idx is not None:
                untagged.match_method = "Acoustic Fingerprint"
                groups_dict[best_match_idx].append(untagged)
            # If no match, create new group with just this untagged album
            # (won't show as duplicate since groups need 2+ albums)

        # Filter to only groups with 2+ albums
        duplicate_groups = [group for group in groups_dict.values() if len(group) >= 2]

        if self.verbose and duplicate_groups:
            print(
                f"Found {len(duplicate_groups)} duplicate groups (canonical matching)"
            )

        return duplicate_groups

    def _merge_groups_by_musicbrainz(
        self, groups: List[List[Album]]
    ) -> List[List[Album]]:
        """
        Merge fingerprint-based groups that share MusicBrainz IDs.

        If albums in different groups have the same MusicBrainz ID and track count,
        merge those groups together.

        Args:
            groups: List of fingerprint-matched groups

        Returns:
            List of merged groups
        """
        if not groups:
            return []

        # Create mapping of (mb_id, track_count) -> group indices
        mb_to_groups: Dict[Tuple[str, int], List[int]] = defaultdict(list)

        for idx, group in enumerate(groups):
            # Get all unique MB IDs in this group
            mb_ids = set()
            track_counts = set()
            for album in group:
                if album.musicbrainz_albumid and not album.has_mixed_mb_ids:
                    mb_ids.add(album.musicbrainz_albumid)
                track_counts.add(album.track_count)

            # If group has consistent MB ID and track count, track it
            if len(mb_ids) == 1 and len(track_counts) == 1:
                mb_id = list(mb_ids)[0]
                track_count = list(track_counts)[0]
                mb_to_groups[(mb_id, track_count)].append(idx)

        # Determine which groups to merge
        groups_to_merge: Dict[int, int] = {}  # group_idx -> canonical_group_idx
        for (_mb_id, _track_count), group_indices in mb_to_groups.items():
            if len(group_indices) > 1:
                # Merge all these groups into the first one
                canonical = group_indices[0]
                for idx in group_indices[1:]:
                    groups_to_merge[idx] = canonical

        # Perform merging
        merged_groups_dict: Dict[int, List[Album]] = {}
        for idx, group in enumerate(groups):
            if idx in groups_to_merge:
                # This group should be merged into another
                canonical = groups_to_merge[idx]
                if canonical not in merged_groups_dict:
                    merged_groups_dict[canonical] = list(groups[canonical])
                merged_groups_dict[canonical].extend(group)
            elif idx not in merged_groups_dict:
                # This group is standalone or is the canonical for merged groups
                merged_groups_dict[idx] = list(group)

        merged_groups = list(merged_groups_dict.values())

        if self.verbose and groups_to_merge:
            print(
                f"Merged {len(groups_to_merge)} groups using MusicBrainz IDs "
                f"({len(groups)} -> {len(merged_groups)} groups)"
            )

        return merged_groups

    def _match_by_musicbrainz(
        self, albums: List[Album], should_stop: Optional[Callable[[], bool]] = None
    ) -> List[List[Album]]:
        """
        Group albums by MusicBrainz album ID.

        Args:
            albums: List of Album objects
            should_stop: Optional callback to check if processing should stop

        Returns:
            List of duplicate groups with same MB ID and track count
        """
        # Group by MusicBrainz ID
        mb_groups: Dict[str, List[Album]] = defaultdict(list)

        for album in albums:
            if should_stop and should_stop():
                return []
            if album.musicbrainz_albumid and not album.has_mixed_mb_ids:
                mb_groups[album.musicbrainz_albumid].append(album)

        # Filter to only groups with duplicates (2+ albums with same track count)
        duplicate_groups: List[List[Album]] = []
        for _mb_id, group in mb_groups.items():
            if should_stop and should_stop():
                return duplicate_groups
            if len(group) < 2:
                continue

            # Group by track count within MB ID group
            by_track_count: Dict[int, List[Album]] = defaultdict(list)
            for album in group:
                by_track_count[album.track_count].append(album)

            # Only include groups with matching track counts
            for _track_count, albums_with_count in by_track_count.items():
                if len(albums_with_count) >= 2:
                    duplicate_groups.append(albums_with_count)

        if self.verbose and duplicate_groups:
            print(f"Found {len(duplicate_groups)} duplicate groups via MusicBrainz IDs")

        return duplicate_groups

    def _match_by_fingerprints(
        self, albums: List[Album], should_stop: Optional[Callable[[], bool]] = None
    ) -> List[List[Album]]:
        """
        Group albums by perceptual fingerprint similarity.

        Uses track-by-track comparison with Union-Find algorithm.

        Args:
            albums: List of Album objects
            should_stop: Optional callback to check if processing should stop

        Returns:
            List of duplicate groups with similar fingerprints
        """
        if not albums:
            return []

        duplicate_groups: List[List[Album]] = []

        if self.allow_partial:
            # Partial matching enabled: compare albums across different track counts
            # Group by approximate track count (within 50% tolerance)
            # to reduce comparisons
            by_track_count_range: Dict[int, List[Album]] = defaultdict(list)
            for album in albums:
                if should_stop and should_stop():
                    return duplicate_groups
                # Use track count bucket (rounded down to nearest 5)
                bucket = (album.track_count // 5) * 5
                by_track_count_range[bucket].append(album)

            # Also check adjacent buckets for edge cases
            for bucket, bucket_albums in by_track_count_range.items():
                if should_stop and should_stop():
                    return duplicate_groups
                # Combine with adjacent buckets
                combined_albums = list(bucket_albums)
                for adjacent in [bucket - 5, bucket + 5]:
                    if adjacent in by_track_count_range:
                        combined_albums.extend(by_track_count_range[adjacent])

                # Remove duplicates while preserving order
                seen = set()
                unique_albums = []
                for album in combined_albums:
                    if album.path not in seen:
                        seen.add(album.path)
                        unique_albums.append(album)

                if len(unique_albums) < 2:
                    continue

                # Union-Find for grouping similar albums
                uf_groups = self._union_find_similar_albums(unique_albums, should_stop)

                # Only include groups with 2+ albums
                for group in uf_groups:
                    if should_stop and should_stop():
                        return duplicate_groups
                    if len(group) >= 2:
                        # Check if already added (due to bucket overlap)
                        group_paths = {a.path for a in group}
                        is_duplicate = False
                        for existing_group in duplicate_groups:
                            existing_paths = {a.path for a in existing_group}
                            if group_paths == existing_paths:
                                is_duplicate = True
                                break
                        if not is_duplicate:
                            duplicate_groups.append(group)
        else:
            # Standard matching: only compare albums with same track count
            by_track_count: Dict[int, List[Album]] = defaultdict(list)
            for album in albums:
                if should_stop and should_stop():
                    return duplicate_groups
                by_track_count[album.track_count].append(album)

            for _track_count, albums_with_count in by_track_count.items():
                if should_stop and should_stop():
                    return duplicate_groups
                if len(albums_with_count) < 2:
                    continue

                # Union-Find for grouping similar albums
                uf_groups = self._union_find_similar_albums(
                    albums_with_count, should_stop
                )

                # Only include groups with 2+ albums
                for group in uf_groups:
                    if should_stop and should_stop():
                        return duplicate_groups
                    if len(group) >= 2:
                        duplicate_groups.append(group)

        if self.verbose and duplicate_groups:
            count = len(duplicate_groups)
            mode = "partial" if self.allow_partial else "exact"
            print(f"Found {count} duplicate groups via fingerprint matching ({mode})")

        return duplicate_groups

    def _union_find_similar_albums(
        self, albums: List[Album], should_stop: Optional[Callable[[], bool]] = None
    ) -> List[List[Album]]:
        """
        Group similar albums using Union-Find algorithm.

        Args:
            albums: List of albums with same track count
            should_stop: Optional callback to check if processing should stop

        Returns:
            List of album groups
        """
        uf_parent = {i: i for i in range(len(albums))}

        def find(x: int) -> int:
            if uf_parent[x] != x:
                uf_parent[x] = find(uf_parent[x])
            return uf_parent[x]

        def union(x: int, y: int) -> None:
            root_x = find(x)
            root_y = find(y)
            if root_x != root_y:
                uf_parent[root_y] = root_x

        # Compare all pairs
        for i in range(len(albums)):
            if should_stop and should_stop():
                print(f"DEBUG: Stop detected in _union_find_similar_albums at i={i}")
                break
            for j in range(i + 1, len(albums)):
                if should_stop and should_stop():
                    print(
                        f"DEBUG: Stop detected in _union_find_similar_albums at "
                        f"i={i}, j={j}"
                    )
                    break
                # If both albums have same MusicBrainz ID, they're definitely duplicates
                if (
                    albums[i].musicbrainz_albumid
                    and albums[j].musicbrainz_albumid
                    and albums[i].musicbrainz_albumid == albums[j].musicbrainz_albumid
                    and not albums[i].has_mixed_mb_ids
                    and not albums[j].has_mixed_mb_ids
                ):
                    union(i, j)
                else:
                    # Otherwise use fingerprint similarity with configurable threshold
                    similarity = self.album_similarity(albums[i], albums[j])
                    if similarity >= self.similarity_threshold:
                        union(i, j)

        # Extract groups
        groups: Dict[int, List[Album]] = defaultdict(list)
        for i, album in enumerate(albums):
            root = find(i)
            groups[root].append(album)

        return list(groups.values())

    def album_similarity(self, album1: Album, album2: Album) -> float:
        """
        Calculate similarity percentage between two albums.

        Compares all tracks pairwise and returns average similarity.
        If track counts differ and partial matching is enabled, uses
        overlap-based matching.

        Args:
            album1: First album
            album2: Second album

        Returns:
            Similarity percentage (0-100)
        """
        if not album1.fingerprints or not album2.fingerprints:
            return 0.0

        # Different track counts: use partial matching if enabled
        if album1.track_count != album2.track_count:
            if self.allow_partial:
                overlap_pct, avg_sim, _ = self.partial_album_similarity(album1, album2)
                # Only consider match if overlap meets threshold
                if overlap_pct >= self.min_overlap:
                    # Return combined score: weighted average of overlap and similarity
                    # Higher weight on average similarity for quality of match
                    return overlap_pct * 0.3 + avg_sim * 0.7
                return 0.0
            else:
                # Partial matching disabled, different track counts = no match
                return 0.0

        # Same track count: use position-based matching (existing logic)
        similarities = []
        for fp1, fp2 in zip(album1.fingerprints, album2.fingerprints):
            track_similarity = self.hasher.similarity_percentage(fp1, fp2)
            similarities.append(track_similarity)

        # Return average similarity across all tracks
        return sum(similarities) / len(similarities) if similarities else 0.0

    def partial_album_similarity(
        self, album1: Album, album2: Album, min_track_similarity: float = 97.0
    ) -> Tuple[float, float, Dict[int, Tuple[int, float]]]:
        """
        Calculate similarity between albums with different track counts.

        Uses best-effort matching: for each track in the smaller album,
        finds the best matching track in the larger album.

        Args:
            album1: First album
            album2: Second album
            min_track_similarity: Minimum similarity for a track to be
                considered matching

        Returns:
            Tuple of (overlap_percentage, avg_similarity, track_mapping)
            - overlap_percentage: What % of smaller album's tracks are in larger (0-100)
            - avg_similarity: Average similarity of matched tracks (0-100)
            - track_mapping: Dict mapping small_idx -> (large_idx, similarity)
        """
        if not album1.fingerprints or not album2.fingerprints:
            return (0.0, 0.0, {})

        # Determine smaller and larger albums
        if album1.track_count <= album2.track_count:
            smaller, larger = album1, album2
        else:
            smaller, larger = album2, album1

        matches = []
        track_mapping: Dict[int, Tuple[int, float]] = {}

        # For each track in smaller album, find best match in larger album
        for small_idx, fp_small in enumerate(smaller.fingerprints):
            best_match_sim = 0.0
            best_match_idx = -1

            for large_idx, fp_large in enumerate(larger.fingerprints):
                similarity = self.hasher.similarity_percentage(fp_small, fp_large)
                if similarity > best_match_sim:
                    best_match_sim = similarity
                    best_match_idx = large_idx

            # Only count as match if similarity meets threshold
            if best_match_sim >= min_track_similarity:
                matches.append(best_match_sim)
                track_mapping[small_idx] = (best_match_idx, best_match_sim)

        # Calculate overlap percentage: what % of smaller album is present
        overlap_pct = (len(matches) / smaller.track_count * 100.0) if matches else 0.0

        # Calculate average similarity of matched tracks
        avg_sim = (sum(matches) / len(matches)) if matches else 0.0

        return (overlap_pct, avg_sim, track_mapping)

    def _annotate_partial_matches(self, group: List[Album]) -> None:
        """
        Annotate albums in a group with partial match information.

        Sets is_partial_match, overlap_percentage, and missing_track_indices
        for albums that have different track counts than the majority.

        Args:
            group: List of albums in a duplicate group
        """
        if not self.allow_partial:
            return

        # Find most common track count (reference)
        from collections import Counter

        track_counts = [a.track_count for a in group]
        most_common_count = Counter(track_counts).most_common(1)[0][0]

        # Find a reference album with the most common track count
        reference_album = None
        for album in group:
            if album.track_count == most_common_count:
                reference_album = album
                break

        if not reference_album:
            return

        # Annotate albums with different track counts
        for album in group:
            if album.track_count != most_common_count:
                # This is a partial match
                album.is_partial_match = True

                # Calculate overlap and missing tracks
                overlap_pct, _, track_mapping = self.partial_album_similarity(
                    album, reference_album
                )
                # Calculate overlap relative to reference album, not smaller album
                # (e.g., 7 matched out of 9 reference tracks = 77.8%, not 100%)
                num_matched = len(track_mapping)
                album.overlap_percentage = (
                    num_matched / reference_album.track_count * 100.0
                    if reference_album.track_count > 0
                    else 0.0
                )

                # Determine which tracks are missing
                if album.track_count < reference_album.track_count:
                    # This album is missing tracks
                    matched_indices = set(track_mapping.keys())
                    all_indices = set(range(album.track_count))
                    missing_in_small = list(all_indices - matched_indices)
                    album.missing_track_indices = missing_in_small
                else:
                    # Reference album is smaller, no missing tracks to report
                    album.missing_track_indices = []

    def get_matched_album_info(self, group: List[Album]) -> Tuple[str, str]:
        """
        Determine the matched album name and artist for a duplicate group.

        Uses canonical album (with MusicBrainz ID or complete metadata) if
        available, otherwise uses most common names.

        Args:
            group: List of duplicate albums

        Returns:
            Tuple of (album_name, artist_name), or ("Unknown", "Unknown")
        """
        # Prioritize canonical albums (MB ID first, then complete metadata)
        canonical = None

        # First try: Album with MusicBrainz ID
        for album in group:
            if album.musicbrainz_albumid and not album.has_mixed_mb_ids:
                canonical = album
                break

        # Second try: Album with both album and artist names
        if not canonical:
            for album in group:
                if album.album_name and album.artist_name:
                    canonical = album
                    break

        # If we found a canonical album, use its metadata
        if canonical:
            return (
                canonical.album_name or "Unknown",
                canonical.artist_name or "Unknown",
            )

        # Fallback: Use most common names
        from collections import Counter

        album_names = [a.album_name for a in group if a.album_name]
        artist_names = [a.artist_name for a in group if a.artist_name]

        album_name = (
            Counter(album_names).most_common(1)[0][0] if album_names else "Unknown"
        )
        artist_name = (
            Counter(artist_names).most_common(1)[0][0] if artist_names else "Unknown"
        )

        return (album_name, artist_name)

    def calculate_confidence(self, album: Album, group: List[Album]) -> float:
        """
        Calculate confidence that an album belongs to the matched group.

        Confidence based on:
        - MusicBrainz ID match: 100%
        - Album/artist name match + track count: 90-95%
        - Fingerprint similarity only: 80-90%

        Args:
            album: Album to calculate confidence for
            group: Full duplicate group

        Returns:
            Confidence percentage (0-100)
        """
        # If all albums in group have same MB ID, confidence is 100%
        mb_ids = [a.musicbrainz_albumid for a in group if a.musicbrainz_albumid]
        if mb_ids and album.musicbrainz_albumid:
            if all(mb == album.musicbrainz_albumid for mb in mb_ids):
                return 100.0

        # Get matched album/artist for the group
        matched_album, matched_artist = self.get_matched_album_info(group)

        # Start with base confidence from metadata match
        confidence = 80.0

        # Boost if album name matches
        if album.album_name and album.album_name == matched_album:
            confidence += 5.0

        # Boost if artist name matches
        if album.artist_name and album.artist_name == matched_artist:
            confidence += 5.0

        # Boost based on average fingerprint similarity to other albums
        if len(group) > 1:
            similarities = []
            for other in group:
                if other != album:
                    sim = self.album_similarity(album, other)
                    similarities.append(sim)
            if similarities:
                avg_similarity = sum(similarities) / len(similarities)
                # Map 97-100% similarity to +0-10% confidence boost
                boost = (avg_similarity - 97.0) / 3.0 * 10.0
                confidence += min(10.0, max(0.0, boost))

        return min(100.0, confidence)

    def _get_ungrouped_albums(
        self, all_albums: List[Album], groups: List[List[Album]]
    ) -> List[Album]:
        """
        Get albums that are not in any duplicate group.

        Args:
            all_albums: All albums
            groups: List of duplicate groups

        Returns:
            List of albums not in any group
        """
        grouped: Set[Path] = set()
        for group in groups:
            for album in group:
                grouped.add(album.path)

        return [album for album in all_albums if album.path not in grouped]
