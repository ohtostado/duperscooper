"""Album detection and metadata extraction for duplicate album finding."""

import json
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

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


class AlbumDuplicateFinder:
    """Find duplicate albums using various matching strategies."""

    def __init__(self, hasher: AudioHasher, verbose: bool = False):
        """
        Initialize album duplicate finder.

        Args:
            hasher: AudioHasher instance for fingerprint comparison
            verbose: Enable verbose output
        """
        self.hasher = hasher
        self.verbose = verbose

    def find_duplicates(
        self, albums: List[Album], strategy: str = "auto"
    ) -> List[List[Album]]:
        """
        Find duplicate albums using specified matching strategy.

        Args:
            albums: List of Album objects to check for duplicates
            strategy: Matching strategy - "musicbrainz", "fingerprint", or "auto"

        Returns:
            List of duplicate groups (each group is a list of Album objects)
        """
        if strategy == "musicbrainz":
            return self._match_by_musicbrainz(albums)
        elif strategy == "fingerprint":
            return self._match_by_fingerprints(albums)
        elif strategy == "auto":
            # Auto: Establish canonical albums from MB IDs/metadata,
            # then match untagged albums against them via fingerprints
            return self._match_canonical(albums)
        else:
            raise ValueError(
                f"Unknown strategy: {strategy}. "
                "Use 'musicbrainz', 'fingerprint', or 'auto'"
            )

    def _match_canonical(self, albums: List[Album]) -> List[List[Album]]:
        """
        Match albums using canonical approach.

        1. Establish canonical albums from MusicBrainz IDs or metadata tags
        2. Match untagged albums against canonical versions via fingerprints
        3. Merge groups that share the same canonical album

        Args:
            albums: List of Album objects

        Returns:
            List of duplicate groups with canonical album identification
        """
        # Separate canonical and untagged albums
        canonical_albums = []
        untagged_albums = []

        for album in albums:
            # Canonical if has MB ID OR both album and artist names
            if album.musicbrainz_albumid or (album.album_name and album.artist_name):
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
        canonical_fp_groups = self._match_by_fingerprints(canonical_albums)

        # Merge canonical groups that share MB IDs
        merged_canonical = self._merge_groups_by_musicbrainz(canonical_fp_groups)

        # Now match each untagged album against canonical groups
        groups_dict: Dict[int, List[Album]] = {}
        for idx, group in enumerate(merged_canonical):
            groups_dict[idx] = list(group)

        # Match untagged albums against canonical groups
        for untagged in untagged_albums:
            best_match_idx = None
            best_similarity = 0.0

            # Compare against each canonical group
            for idx, canonical_group in groups_dict.items():
                # Compare against first album in canonical group (representative)
                canonical_rep = canonical_group[0]

                # Must have same track count
                if untagged.track_count != canonical_rep.track_count:
                    continue

                # Calculate similarity
                similarity = self.album_similarity(untagged, canonical_rep)

                if similarity >= 98.0 and similarity > best_similarity:
                    best_similarity = similarity
                    best_match_idx = idx

            # Add to best matching canonical group
            if best_match_idx is not None:
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

    def _match_by_musicbrainz(self, albums: List[Album]) -> List[List[Album]]:
        """
        Group albums by MusicBrainz album ID.

        Args:
            albums: List of Album objects

        Returns:
            List of duplicate groups with same MB ID and track count
        """
        # Group by MusicBrainz ID
        mb_groups: Dict[str, List[Album]] = defaultdict(list)

        for album in albums:
            if album.musicbrainz_albumid and not album.has_mixed_mb_ids:
                mb_groups[album.musicbrainz_albumid].append(album)

        # Filter to only groups with duplicates (2+ albums with same track count)
        duplicate_groups = []
        for _mb_id, group in mb_groups.items():
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

    def _match_by_fingerprints(self, albums: List[Album]) -> List[List[Album]]:
        """
        Group albums by perceptual fingerprint similarity.

        Uses track-by-track comparison with Union-Find algorithm.

        Args:
            albums: List of Album objects

        Returns:
            List of duplicate groups with similar fingerprints
        """
        if not albums:
            return []

        # Group by track count first (only compare albums with same number of tracks)
        by_track_count: Dict[int, List[Album]] = defaultdict(list)
        for album in albums:
            by_track_count[album.track_count].append(album)

        duplicate_groups = []

        for _track_count, albums_with_count in by_track_count.items():
            if len(albums_with_count) < 2:
                continue

            # Union-Find for grouping similar albums
            uf_groups = self._union_find_similar_albums(albums_with_count)

            # Only include groups with 2+ albums
            for group in uf_groups:
                if len(group) >= 2:
                    duplicate_groups.append(group)

        if self.verbose and duplicate_groups:
            count = len(duplicate_groups)
            print(f"Found {count} duplicate groups via fingerprint matching")

        return duplicate_groups

    def _union_find_similar_albums(self, albums: List[Album]) -> List[List[Album]]:
        """
        Group similar albums using Union-Find algorithm.

        Args:
            albums: List of albums with same track count

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
            for j in range(i + 1, len(albums)):
                similarity = self.album_similarity(albums[i], albums[j])
                # Use 98% threshold for album similarity
                if similarity >= 98.0:
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

        Args:
            album1: First album
            album2: Second album

        Returns:
            Similarity percentage (0-100)
        """
        if album1.track_count != album2.track_count:
            return 0.0

        if not album1.fingerprints or not album2.fingerprints:
            return 0.0

        # Compare each track pair
        similarities = []
        for fp1, fp2 in zip(album1.fingerprints, album2.fingerprints):
            track_similarity = self.hasher.similarity_percentage(fp1, fp2)
            similarities.append(track_similarity)

        # Return average similarity across all tracks
        return sum(similarities) / len(similarities) if similarities else 0.0

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
                # Map 98-100% similarity to +5-10% confidence boost
                boost = (avg_similarity - 98.0) / 2.0 * 10.0
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
