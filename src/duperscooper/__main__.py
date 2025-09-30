"""CLI interface for duperscooper."""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List

from . import __version__
from .finder import DuplicateFinder, DuplicateManager


def format_output_text(duplicates: Dict[str, List[Path]]) -> None:
    """Format and print duplicates in text format."""
    if not duplicates:
        print("No duplicates found.")
        return

    print(f"Found {len(duplicates)} group(s) of duplicate files:\n")

    for idx, (hash_val, file_list) in enumerate(duplicates.items(), 1):
        print(f"Group {idx} (Hash: {hash_val[:16]}...):")
        for file_path in file_list:
            info = DuplicateManager.get_file_info(file_path)
            print(f"  - {info['path']} ({info['size']})")
        print()


def format_output_json(duplicates: Dict[str, List[Path]]) -> None:
    """Format and print duplicates in JSON format."""
    output = []
    for hash_val, file_list in duplicates.items():
        group = {
            "hash": hash_val,
            "files": [
                DuplicateManager.get_file_info(file_path) for file_path in file_list
            ],
        }
        output.append(group)

    print(json.dumps(output, indent=2))


def format_output_csv(duplicates: Dict[str, List[Path]]) -> None:
    """Format and print duplicates in CSV format."""
    print("group_id,hash,file_path,file_size,file_size_bytes")

    for idx, (hash_val, file_list) in enumerate(duplicates.items(), 1):
        for file_path in file_list:
            info = DuplicateManager.get_file_info(file_path)
            print(
                f"{idx},{hash_val},{info['path']},{info['size']},{info['size_bytes']}"
            )


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        prog="duperscooper",
        description="Find duplicate audio files recursively in given paths.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s /path/to/music
  %(prog)s /music /downloads --algorithm exact
  %(prog)s ~/Music --min-size 0 --output json
  %(prog)s /music --delete-duplicates --no-progress
        """,
    )

    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Paths to search for duplicate audio files (files or directories)",
    )

    parser.add_argument(
        "-o",
        "--output",
        choices=["text", "json", "csv"],
        default="text",
        help="Output format (default: text)",
    )

    parser.add_argument(
        "--min-size",
        type=int,
        default=1048576,
        metavar="BYTES",
        help="Minimum file size in bytes to consider (default: 1048576 = 1MB)",
    )

    parser.add_argument(
        "-a",
        "--algorithm",
        choices=["perceptual", "exact"],
        default="perceptual",
        help="Hash algorithm: 'perceptual' for similar audio detection, "
        "'exact' for byte-identical files (default: perceptual)",
    )

    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable progress output (progress shown by default)",
    )

    parser.add_argument(
        "--delete-duplicates",
        action="store_true",
        help="Interactively delete duplicate files after finding them",
    )

    parser.add_argument(
        "--similarity-threshold",
        type=float,
        default=98.0,
        metavar="PERCENT",
        help="Minimum similarity percentage for perceptual matching (default: 98.0)",
    )

    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable cache (compute all hashes from scratch)",
    )

    parser.add_argument(
        "--update-cache",
        action="store_true",
        help="Force regeneration of cached hashes for found files",
    )

    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Clear the hash cache and exit",
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    return parser.parse_args()


def main() -> int:
    """Main entry point for CLI."""
    args = parse_args()

    # Handle --clear-cache option
    if args.clear_cache:
        from .hasher import AudioHasher

        hasher = AudioHasher()
        if hasher.clear_cache():
            print(f"Cache cleared: {hasher.cache_path}")
            return 0
        else:
            print(f"No cache to clear (or failed to delete): {hasher.cache_path}")
            return 1

    # Require paths unless --clear-cache
    if not args.paths:
        print("Error: the following arguments are required: paths", file=sys.stderr)
        return 1

    # Create finder and search for duplicates
    finder = DuplicateFinder(
        min_size=args.min_size,
        algorithm=args.algorithm,
        verbose=not args.no_progress,
        use_cache=not args.no_cache,
        update_cache=args.update_cache,
        similarity_threshold=args.similarity_threshold,
    )

    try:
        duplicates = finder.find_duplicates(args.paths)
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Handle delete mode
    if args.delete_duplicates:
        if duplicates:
            try:
                deleted = DuplicateManager.interactive_delete(duplicates)
                print(f"\nDeleted {deleted} file(s).")
            except KeyboardInterrupt:
                print("\nDeletion cancelled by user.", file=sys.stderr)
                return 130
        else:
            print("No duplicates to delete.")
        return 0

    # Format and output results
    if args.output == "json":
        format_output_json(duplicates)
    elif args.output == "csv":
        format_output_csv(duplicates)
    else:
        format_output_text(duplicates)

    # Exit with non-zero if duplicates found (for scripting)
    return 0 if not duplicates else 2


if __name__ == "__main__":
    sys.exit(main())
