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
  %(prog)s ~/Music --min-size 1048576 --output json
  %(prog)s /music --delete-duplicates
        """,
    )

    parser.add_argument(
        "paths",
        nargs="+",
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
        default=0,
        metavar="BYTES",
        help="Minimum file size in bytes to consider (default: 0)",
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
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose output with progress information",
    )

    parser.add_argument(
        "--delete-duplicates",
        action="store_true",
        help="Interactively delete duplicate files after finding them",
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

    # Create finder and search for duplicates
    finder = DuplicateFinder(
        min_size=args.min_size,
        algorithm=args.algorithm,
        verbose=args.verbose,
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
