"""Data models for scan results and duplicate groups."""

import json
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class DuplicateFile:
    """Represents a single file in a duplicate group."""

    path: str
    size_bytes: int
    audio_info: str
    quality_score: float
    similarity_to_best: float
    is_best: bool
    recommended_action: str  # "keep" or "delete"
    selected_for_deletion: bool = False  # User selection

    @property
    def size_mb(self) -> float:
        """File size in MB."""
        return self.size_bytes / (1024 * 1024)


@dataclass
class DuplicateGroup:
    """Represents a group of duplicate files."""

    group_id: int
    hash_value: str
    files: List[DuplicateFile]

    @property
    def best_file(self) -> Optional[DuplicateFile]:
        """Get the best quality file in this group."""
        for file in self.files:
            if file.is_best:
                return file
        return None

    @property
    def total_size_mb(self) -> float:
        """Total size of all files in this group."""
        return sum(f.size_mb for f in self.files)

    @property
    def potential_savings_mb(self) -> float:
        """Potential space savings if duplicates deleted."""
        return sum(f.size_mb for f in self.files if f.selected_for_deletion)


@dataclass
class AlbumDuplicate:
    """Represents a single album in a duplicate group."""

    path: str
    track_count: int
    total_size_bytes: int
    quality_info: str
    quality_score: float
    match_percentage: float
    match_method: str
    is_best: bool
    recommended_action: str
    musicbrainz_albumid: Optional[str] = None
    album_name: Optional[str] = None
    artist_name: Optional[str] = None
    selected_for_deletion: bool = False

    @property
    def size_mb(self) -> float:
        """Album size in MB."""
        return self.total_size_bytes / (1024 * 1024)


@dataclass
class AlbumDuplicateGroup:
    """Represents a group of duplicate albums."""

    group_id: int
    matched_album: Optional[str]
    matched_artist: Optional[str]
    albums: List[AlbumDuplicate]

    @property
    def best_album(self) -> Optional[AlbumDuplicate]:
        """Get the best quality album in this group."""
        for album in self.albums:
            if album.is_best:
                return album
        return None

    @property
    def total_size_mb(self) -> float:
        """Total size of all albums in this group."""
        return sum(a.size_mb for a in self.albums)

    @property
    def potential_savings_mb(self) -> float:
        """Potential space savings if duplicates deleted."""
        return sum(a.size_mb for a in self.albums if a.selected_for_deletion)


class ScanResults:
    """Container for all scan results."""

    def __init__(self):
        self.mode: str = "track"  # "track" or "album"
        self.track_groups: List[DuplicateGroup] = []
        self.album_groups: List[AlbumDuplicateGroup] = []

    @classmethod
    def from_json(cls, json_data: str) -> "ScanResults":
        """Load results from JSON string."""
        results = cls()
        data = json.loads(json_data)

        # Detect mode based on structure
        if isinstance(data, list) and len(data) > 0:
            first_item = data[0]

            if "files" in first_item:
                # Track mode
                results.mode = "track"
                for idx, group in enumerate(data, 1):
                    files = [
                        DuplicateFile(
                            path=f["path"],
                            size_bytes=f["size_bytes"],
                            audio_info=f["audio_info"],
                            quality_score=f["quality_score"],
                            similarity_to_best=f["similarity_to_best"],
                            is_best=f["is_best"],
                            recommended_action=f["recommended_action"],
                            selected_for_deletion=(
                                f["recommended_action"] == "delete"
                            ),  # Pre-select
                        )
                        for f in group["files"]
                    ]
                    results.track_groups.append(
                        DuplicateGroup(
                            group_id=idx,
                            hash_value=group["hash"],
                            files=files,
                        )
                    )

            elif "albums" in first_item:
                # Album mode
                results.mode = "album"
                for idx, group in enumerate(data, 1):
                    albums = [
                        AlbumDuplicate(
                            path=a["path"],
                            track_count=a["track_count"],
                            # CLI outputs "total_size", model uses "total_size_bytes"
                            total_size_bytes=a.get("total_size_bytes")
                            or a.get("total_size", 0),
                            quality_info=a["quality_info"],
                            quality_score=a["quality_score"],
                            match_percentage=a["match_percentage"],
                            match_method=a["match_method"],
                            is_best=a["is_best"],
                            recommended_action=a["recommended_action"],
                            musicbrainz_albumid=a.get("musicbrainz_albumid"),
                            album_name=a.get("album_name"),
                            artist_name=a.get("artist_name"),
                            selected_for_deletion=(a["recommended_action"] == "delete"),
                        )
                        for a in group["albums"]
                    ]
                    results.album_groups.append(
                        AlbumDuplicateGroup(
                            group_id=idx,
                            matched_album=group.get("matched_album"),
                            matched_artist=group.get("matched_artist"),
                            albums=albums,
                        )
                    )

        return results

    @classmethod
    def from_file(cls, filepath: str) -> "ScanResults":
        """Load results from JSON file."""
        with open(filepath) as f:
            return cls.from_json(f.read())

    @property
    def total_groups(self) -> int:
        """Total number of duplicate groups."""
        if self.mode == "track":
            return len(self.track_groups)
        else:
            return len(self.album_groups)

    @property
    def total_duplicates(self) -> int:
        """Total number of duplicate items (excluding best)."""
        if self.mode == "track":
            return sum(len(g.files) - 1 for g in self.track_groups)  # -1 for best file
        else:
            return sum(len(g.albums) - 1 for g in self.album_groups)

    @property
    def total_size_mb(self) -> float:
        """Total size of all items."""
        if self.mode == "track":
            return sum(g.total_size_mb for g in self.track_groups)
        else:
            return sum(g.total_size_mb for g in self.album_groups)

    @property
    def potential_savings_mb(self) -> float:
        """Potential space savings if selected items deleted."""
        if self.mode == "track":
            return sum(g.potential_savings_mb for g in self.track_groups)
        else:
            return sum(g.potential_savings_mb for g in self.album_groups)
