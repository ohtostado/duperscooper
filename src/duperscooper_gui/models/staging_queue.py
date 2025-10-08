"""Staging queue for managing items before deletion."""

from dataclasses import dataclass
from typing import List, Literal


@dataclass
class StagingItem:
    """Represents an item in the staging queue."""

    path: str
    mode: Literal["track", "album"]
    size_bytes: int = 0
    quality_info: str = ""
    album_name: str = ""
    artist_name: str = ""


class StagingQueue:
    """
    Manages the staging queue for items waiting to be deleted.

    Items are added to the queue when user clicks "Stage for Deletion" in
    Results tab. Files remain in their original location until "Delete All"
    is clicked in Staging tab.
    """

    _instance = None

    def __new__(cls):
        """Singleton pattern - only one queue per application."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.items: List[StagingItem] = []
        return cls._instance

    def add_items(self, items: List[StagingItem]) -> None:
        """Add items to the staging queue (prevents duplicates by path)."""
        # Get existing paths
        existing_paths = {item.path for item in self.items}

        # Add only new items
        for item in items:
            if item.path not in existing_paths:
                self.items.append(item)
                existing_paths.add(item.path)

    def remove_items(self, paths: List[str]) -> None:
        """Remove items from the staging queue by path."""
        paths_set = set(paths)
        self.items = [item for item in self.items if item.path not in paths_set]

    def clear(self) -> None:
        """Clear all items from the staging queue."""
        self.items = []

    def get_all(self) -> List[StagingItem]:
        """Get all items in the staging queue."""
        return self.items.copy()

    def get_total_size(self) -> int:
        """Get total size of all queued items in bytes."""
        return sum(item.size_bytes for item in self.items)

    def get_count(self) -> int:
        """Get number of items in queue."""
        return len(self.items)

    def has_items(self) -> bool:
        """Check if queue has any items."""
        return len(self.items) > 0
