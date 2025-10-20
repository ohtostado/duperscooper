#!/usr/bin/env python3
"""
Migrate existing cache and scan results to include disc metadata.

This script:
1. Adds disc columns to the album_cache database (if needed)
2. Re-extracts disc metadata for all cached albums
3. Updates scan-results.json with disc information
"""

import json
import sqlite3
import subprocess
from pathlib import Path
from typing import Optional, Tuple


def extract_disc_tags(
    track_path: Path,
) -> Tuple[Optional[int], Optional[str], Optional[int]]:
    """
    Extract disc metadata from audio file.

    Returns:
        Tuple of (disc_number, disc_subtitle, total_discs)
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
                str(track_path),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            return (None, None, None)

        data = json.loads(result.stdout)
        tags = data.get("format", {}).get("tags", {})

        disc_number = None
        disc_subtitle = None
        total_discs = None

        for key, value in tags.items():
            key_upper = key.upper()
            if key_upper == "DISC":
                # Parse disc number (may be "1/2" or just "1")
                try:
                    disc_str = str(value).split("/")[0]
                    disc_number = int(disc_str)
                except (ValueError, IndexError):
                    pass
            elif key_upper == "DISCSUBTITLE":
                disc_subtitle = value
            elif key_upper == "TOTALDISCS":
                try:
                    total_discs = int(value)
                except ValueError:
                    pass

        return (disc_number, disc_subtitle, total_discs)
    except Exception:
        return (None, None, None)


def migrate_database(db_path: Path) -> None:
    """Add disc columns to database and update existing albums."""
    print(f"Migrating database: {db_path}")

    conn = sqlite3.connect(db_path)

    # Check if columns already exist
    cursor = conn.execute("PRAGMA table_info(album_cache)")
    columns = {row[1] for row in cursor.fetchall()}

    if "disc_number" not in columns:
        print("  Adding disc_number column...")
        conn.execute("ALTER TABLE album_cache ADD COLUMN disc_number INTEGER")

    if "disc_subtitle" not in columns:
        print("  Adding disc_subtitle column...")
        conn.execute("ALTER TABLE album_cache ADD COLUMN disc_subtitle TEXT")

    if "total_discs" not in columns:
        print("  Adding total_discs column...")
        conn.execute("ALTER TABLE album_cache ADD COLUMN total_discs INTEGER")

    conn.commit()

    # Get all cached albums
    cursor = conn.execute("SELECT album_path FROM album_cache")
    album_paths = [row[0] for row in cursor.fetchall()]

    print(f"  Updating {len(album_paths)} cached albums...")
    updated = 0
    failed = 0

    for album_path in album_paths:
        album_dir = Path(album_path)
        if not album_dir.exists():
            failed += 1
            continue

        # Find first audio file
        audio_files = list(album_dir.glob("*.flac")) + list(
            album_dir.glob("*.mp3")
        )
        if not audio_files:
            failed += 1
            continue

        # Extract disc metadata
        disc_number, disc_subtitle, total_discs = extract_disc_tags(
            audio_files[0]
        )

        # Update database
        conn.execute(
            """
            UPDATE album_cache
            SET disc_number = ?, disc_subtitle = ?, total_discs = ?
            WHERE album_path = ?
            """,
            (disc_number, disc_subtitle, total_discs, album_path),
        )
        updated += 1

        if updated % 100 == 0:
            print(f"    Progress: {updated}/{len(album_paths)}")
            conn.commit()

    conn.commit()
    conn.close()
    print(f"  ✓ Updated {updated} albums, {failed} failed")


def migrate_scan_results(json_path: Path) -> None:
    """Add disc metadata to scan results JSON."""
    print(f"Migrating scan results: {json_path}")

    with open(json_path) as f:
        data = json.load(f)

    mode = data.get("export_metadata", {}).get("mode")
    if mode != "album":
        print("  Skipping: not in album mode")
        return

    total_items = 0
    updated_items = 0

    for group in data.get("groups", []):
        for item in group.get("items", []):
            total_items += 1
            path = item.get("path")
            if not path:
                continue

            album_dir = Path(path)
            if not album_dir.exists():
                continue

            # Find first audio file
            audio_files = list(album_dir.glob("*.flac")) + list(
                album_dir.glob("*.mp3")
            )
            if not audio_files:
                continue

            # Extract and add disc metadata
            disc_number, disc_subtitle, total_discs = extract_disc_tags(
                audio_files[0]
            )

            item["disc_number"] = disc_number
            item["disc_subtitle"] = disc_subtitle
            item["total_discs"] = total_discs
            updated_items += 1

    # Write updated JSON
    output_path = json_path.with_suffix(".migrated.json")
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(
        f"  ✓ Updated {updated_items}/{total_items} items"
    )
    print(f"  ✓ Saved to: {output_path}")


def main():
    """Run migration."""
    # Migrate database
    db_path = (
        Path.home() / ".config" / "duperscooper" / "hashes.db"
    )
    if db_path.exists():
        migrate_database(db_path)
    else:
        print(f"Database not found: {db_path}")

    # Migrate scan results if provided
    import sys

    if len(sys.argv) > 1:
        json_path = Path(sys.argv[1])
        if json_path.exists():
            migrate_scan_results(json_path)
        else:
            print(f"Scan results not found: {json_path}")
    else:
        print("\nTo migrate scan results, run:")
        print("  python migrate_disc_metadata.py /path/to/scan-results.json")


if __name__ == "__main__":
    main()
