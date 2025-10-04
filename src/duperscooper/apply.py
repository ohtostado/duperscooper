"""Apply deletion rules to scan results without re-scanning."""

import csv
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Literal, Tuple

from .rules import RuleEngine
from .staging import StagingManager


class ScanResultLoader:
    """Load and parse scan results from JSON or CSV format."""

    @staticmethod
    def load_json(path: Path) -> Tuple[Literal["track", "album"], List[Dict[str, Any]]]:
        """
        Load scan results from JSON file.

        Args:
            path: Path to JSON file (from --output json)

        Returns:
            Tuple of (mode, duplicate_groups)
            - mode: "track" or "album"
            - duplicate_groups: List of duplicate groups

        Raises:
            ValueError: If JSON format is invalid
        """
        with open(path) as f:
            data = json.load(f)

        if not isinstance(data, list) or not data:
            raise ValueError("JSON must be a non-empty list of duplicate groups")

        # Detect mode based on structure
        first_group = data[0]

        if "files" in first_group:
            # Track mode: {"hash": "...", "files": [...]}
            mode: Literal["track", "album"] = "track"
            # Validate structure
            for group in data:
                if "hash" not in group or "files" not in group:
                    raise ValueError(
                        "Track mode JSON must have 'hash' and 'files' fields"
                    )
                if not isinstance(group["files"], list):
                    raise ValueError("'files' must be a list")

        elif "albums" in first_group:
            # Album mode: {"matched_album": "...", "matched_artist": "...", "albums"}
            mode = "album"
            # Validate structure
            for group in data:
                if "albums" not in group:
                    raise ValueError("Album mode JSON must have 'albums' field")
                if not isinstance(group["albums"], list):
                    raise ValueError("'albums' must be a list")

        else:
            raise ValueError(
                "Unknown JSON format. Expected track mode (with 'files') "
                "or album mode (with 'albums')"
            )

        return mode, data

    @staticmethod
    def load_csv(path: Path) -> Tuple[Literal["track", "album"], List[Dict[str, Any]]]:
        """
        Load scan results from CSV file.

        Args:
            path: Path to CSV file (from --output csv)

        Returns:
            Tuple of (mode, duplicate_groups)

        Raises:
            ValueError: If CSV format is invalid
        """
        with open(path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        if not rows:
            raise ValueError("CSV file is empty")

        # Detect mode based on columns
        first_row = rows[0]

        if "group_id" in first_row and "file_path" in first_row:
            # Track mode CSV
            mode: Literal["track", "album"] = "track"
            groups = ScanResultLoader._reconstruct_track_groups_from_csv(rows)

        elif "group_id" in first_row and "album_path" in first_row:
            # Album mode CSV
            mode = "album"
            groups = ScanResultLoader._reconstruct_album_groups_from_csv(rows)

        else:
            raise ValueError("Unknown CSV format. Missing required columns.")

        return mode, groups

    @staticmethod
    def _reconstruct_track_groups_from_csv(
        rows: List[Dict[str, str]]
    ) -> List[Dict[str, Any]]:
        """Reconstruct track duplicate groups from CSV rows."""
        groups_dict: Dict[str, List[Dict[str, Any]]] = {}

        for row in rows:
            group_id = row["group_id"]
            if group_id not in groups_dict:
                groups_dict[group_id] = []

            # Convert CSV row to file entry
            file_entry = {
                "path": row["file_path"],
                "size": int(row["size_bytes"]),
                "audio_info": row.get("audio_info", ""),
                "quality_score": float(row.get("quality_score", 0)),
                "similarity_to_best": float(row.get("similarity_to_best", 0)),
                "is_best": row.get("is_best", "False") == "True",
            }
            groups_dict[group_id].append(file_entry)

        # Convert to list of groups
        return [{"hash": gid, "files": files} for gid, files in groups_dict.items()]

    @staticmethod
    def _reconstruct_album_groups_from_csv(
        rows: List[Dict[str, str]]
    ) -> List[Dict[str, Any]]:
        """Reconstruct album duplicate groups from CSV rows."""
        groups_dict: Dict[str, Dict[str, Any]] = {}

        for row in rows:
            group_id = row["group_id"]
            if group_id not in groups_dict:
                groups_dict[group_id] = {
                    "matched_album": row.get("matched_album", ""),
                    "matched_artist": row.get("matched_artist", ""),
                    "albums": [],
                }

            # Convert CSV row to album entry
            album_entry = {
                "path": row["album_path"],
                "track_count": int(row.get("track_count", 0)),
                "total_size": int(row.get("total_size_bytes", 0)),
                "quality_info": row.get("quality_info", ""),
                "quality_score": float(row.get("quality_score", 0)),
                "match_percentage": float(row.get("match_percentage", 0)),
                "match_method": row.get("match_method", ""),
                "is_best": row.get("is_best", "False") == "True",
                "musicbrainz_albumid": row.get("musicbrainz_albumid", ""),
                "album_name": row.get("album_name", ""),
                "artist_name": row.get("artist_name", ""),
                "has_mixed_mb_ids": row.get("has_mixed_mb_ids", "False") == "True",
                "is_partial_match": row.get("is_partial_match", "False") == "True",
                "overlap_percentage": float(row.get("overlap_percentage", 0)),
            }
            groups_dict[group_id]["albums"].append(album_entry)

        return list(groups_dict.values())

    @staticmethod
    def extract_fields(
        item: Dict[str, Any], mode: Literal["track", "album"]
    ) -> Dict[str, Any]:
        """
        Extract rule-relevant fields from file/album data.

        This parses audio_info strings and derives additional fields
        for rule evaluation.

        Args:
            item: File or album entry from scan results
            mode: "track" or "album"

        Returns:
            Dictionary with extracted fields
        """
        extracted = item.copy()

        # Derive is_lossless from quality_score
        quality_score = item.get("quality_score", 0)
        extracted["is_lossless"] = quality_score >= 10000

        # Parse audio_info to extract format, codec, bitrate, etc.
        # Albums use "quality_info" instead of "audio_info"
        audio_info = item.get("audio_info", "") or item.get("quality_info", "")

        if audio_info:
            # Extract format (first word before space)
            format_match = re.match(r"^([A-Z0-9]+)", audio_info)
            if format_match:
                extracted["format"] = format_match.group(1)
            else:
                extracted["format"] = "UNKNOWN"

            # Extract codec (same as format for most cases)
            extracted["codec"] = extracted["format"]

            # Extract bitrate for lossy files (e.g., "MP3 CBR 320kbps")
            bitrate_match = re.search(r"(\d+)kbps", audio_info)
            if bitrate_match:
                extracted["bitrate"] = int(bitrate_match.group(1))
            else:
                extracted["bitrate"] = 0

            # Extract sample rate (e.g., "44.1kHz")
            sample_rate_match = re.search(r"([\d.]+)kHz", audio_info)
            if sample_rate_match:
                sample_rate_khz = float(sample_rate_match.group(1))
                extracted["sample_rate"] = int(sample_rate_khz * 1000)
            else:
                extracted["sample_rate"] = 0

            # Extract bit depth (e.g., "16bit")
            bit_depth_match = re.search(r"(\d+)bit", audio_info)
            if bit_depth_match:
                extracted["bit_depth"] = int(bit_depth_match.group(1))
            else:
                extracted["bit_depth"] = 0

        else:
            # Defaults if no audio_info
            extracted["format"] = "UNKNOWN"
            extracted["codec"] = "UNKNOWN"
            extracted["bitrate"] = 0
            extracted["sample_rate"] = 0
            extracted["bit_depth"] = 0

        # Extract file size (may be under different keys)
        if "size" in item:
            extracted["file_size"] = item["size"]
        elif "total_size" in item:
            extracted["file_size"] = item["total_size"]
        else:
            extracted["file_size"] = 0

        return extracted


class ApplyEngine:
    """Apply deletion rules to scan results and execute deletions."""

    @staticmethod
    def apply_rules(
        mode: Literal["track", "album"],
        duplicate_groups: List[Dict[str, Any]],
        rule_engine: RuleEngine,
    ) -> List[Dict[str, Any]]:
        """
        Apply rules to scan results and mark items for keep/delete.

        Args:
            mode: "track" or "album"
            duplicate_groups: Loaded scan results
            rule_engine: RuleEngine with rules configured

        Returns:
            Annotated duplicate groups with "action" field added to each item
        """
        annotated_groups = []

        for group in duplicate_groups:
            if mode == "track":
                items_key = "files"
            else:  # album
                items_key = "albums"

            annotated_items = []
            for item in group[items_key]:
                # Extract fields for rule evaluation
                extracted = ScanResultLoader.extract_fields(item, mode)

                # Evaluate rules
                action = rule_engine.evaluate(extracted)

                # Add action to item
                item_with_action = item.copy()
                item_with_action["action"] = action
                annotated_items.append(item_with_action)

            # Create annotated group
            annotated_group = group.copy()
            annotated_group[items_key] = annotated_items
            annotated_groups.append(annotated_group)

        return annotated_groups

    @staticmethod
    def generate_report(
        mode: Literal["track", "album"], annotated_groups: List[Dict[str, Any]]
    ) -> str:
        """
        Generate a text report showing what will be kept/deleted.

        Args:
            mode: "track" or "album"
            annotated_groups: Groups with "action" annotations

        Returns:
            Formatted report string
        """
        lines = []
        lines.append("=" * 70)
        lines.append("DELETION PLAN")
        lines.append("=" * 70)

        keep_count = 0
        delete_count = 0
        bytes_to_free = 0

        if mode == "track":
            items_key = "files"
            path_key = "path"
            size_key = "size"
        else:  # album
            items_key = "albums"
            path_key = "path"
            size_key = "total_size"

        for group_idx, group in enumerate(annotated_groups, 1):
            lines.append(f"\nGroup {group_idx}:")

            for item in group[items_key]:
                action = item.get("action", "keep")
                path = item.get(path_key, "")
                audio_info = item.get("audio_info", "") or item.get("quality_info", "")
                is_best = item.get("is_best", False)
                size = item.get(size_key, 0)

                marker = "[BEST] " if is_best else "       "
                action_str = "DELETE" if action == "delete" else "KEEP  "

                lines.append(f"  {marker}{action_str}: {path}")
                if audio_info:
                    lines.append(f"           {audio_info}")

                if action == "delete":
                    delete_count += 1
                    bytes_to_free += size
                else:
                    keep_count += 1

        # Summary
        lines.append("\n" + "=" * 70)
        lines.append("SUMMARY")
        lines.append("=" * 70)
        lines.append(f"Items to keep:   {keep_count}")
        lines.append(f"Items to delete: {delete_count}")
        lines.append(f"Space to free:   {ApplyEngine._format_size(bytes_to_free)}")
        lines.append("=" * 70)

        return "\n".join(lines)

    @staticmethod
    def execute_deletions(
        mode: Literal["track", "album"],
        annotated_groups: List[Dict[str, Any]],
        staging_manager: StagingManager,
    ) -> int:
        """
        Execute deletions by staging marked items.

        Args:
            mode: "track" or "album"
            annotated_groups: Groups with "action" annotations
            staging_manager: StagingManager for staging deletions

        Returns:
            Number of items staged for deletion
        """
        staged_count = 0

        if mode == "track":
            items_key = "files"
            path_key = "path"
        else:  # album
            items_key = "albums"
            path_key = "path"

        for group in annotated_groups:
            for item in group[items_key]:
                if item.get("action") == "delete":
                    path = Path(item[path_key])

                    if mode == "track":
                        # For tracks, we need to implement track staging
                        # This is a placeholder - proper implementation would call
                        # staging_manager.stage_track() or similar
                        # For now, we'll skip this and implement in a future commit
                        pass
                    else:  # album
                        # Stage entire album
                        # Convert path to Album-like object (staging expects Album type)
                        # For now, create a minimal mock - proper implementation TBD
                        from types import SimpleNamespace

                        album_obj = SimpleNamespace(path=path)
                        staging_manager.stage_album(
                            album_obj, reason="apply-rules deletion"
                        )
                        staged_count += 1

        return staged_count

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """Format size in bytes as human-readable string."""
        size_float = float(size_bytes)
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size_float < 1024.0:
                return f"{size_float:.1f} {unit}"
            size_float /= 1024.0
        return f"{size_float:.1f} PB"
