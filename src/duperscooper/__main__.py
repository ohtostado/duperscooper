"""CLI interface for duperscooper."""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List

from colorama import Fore, Style, init

from . import __version__
from .finder import DuplicateFinder, DuplicateManager

# Initialize colorama for cross-platform color support
init(autoreset=True)


def get_similarity_color(similarity: float) -> str:
    """
    Get color for similarity percentage based on value.

    Args:
        similarity: Similarity percentage (0-100)

    Returns:
        Colorama color code
    """
    if similarity >= 99.0:
        color: str = Fore.GREEN
        return color
    elif similarity >= 95.0:
        color = Fore.YELLOW
        return color
    else:
        color = Fore.LIGHTRED_EX  # Orange-ish on most terminals
        return color


def format_output_text(duplicates: Dict[str, List[tuple]]) -> None:
    """Format and print duplicates in text format with quality info."""
    if not duplicates:
        print("No duplicates found.")
        return

    from .hasher import AudioHasher

    print(
        f"{Fore.CYAN}{Style.BRIGHT}Found {len(duplicates)} group(s) "
        f"of duplicate files:{Style.RESET_ALL}\n"
    )

    hasher = AudioHasher()

    for idx, (hash_val, file_list) in enumerate(duplicates.items(), 1):
        print(
            f"{Fore.CYAN}{Style.BRIGHT}Group {idx}{Style.RESET_ALL} "
            f"{Style.DIM}(Hash: {hash_val[:16]}...){Style.RESET_ALL}"
        )

        # Identify highest quality file and get enriched file info
        best_file, best_fp, enriched_files = DuplicateManager.identify_highest_quality(
            file_list, hasher
        )

        # Print files with quality info
        # Separate best file from duplicates for sorting
        best_entry = None
        duplicate_entries = []
        for entry in enriched_files:
            file_path = entry[0]
            if file_path == best_file:
                best_entry = entry
            else:
                duplicate_entries.append(entry)

        # Sort duplicates by similarity descending (best matches first)
        duplicate_entries.sort(key=lambda x: x[4], reverse=True)  # x[4] is similarity

        # Print best file first
        if best_entry:
            file_path, _fingerprint, metadata, _quality_score, similarity = best_entry
            info = DuplicateManager.get_file_info(file_path)
            audio_info = AudioHasher.format_audio_info(metadata)
            print(
                f"  {Fore.LIGHTGREEN_EX}{Style.BRIGHT}[Best]{Style.RESET_ALL} "
                f"{info['path']} {Style.DIM}({info['size']}){Style.RESET_ALL} - "
                f"{Fore.LIGHTGREEN_EX}{audio_info}{Style.RESET_ALL}"
            )

        # Print duplicates with proper tree characters
        for idx, (
            file_path,
            _fingerprint,
            metadata,
            _quality_score,
            similarity,
        ) in enumerate(duplicate_entries):
            info = DuplicateManager.get_file_info(file_path)
            audio_info = AudioHasher.format_audio_info(metadata)
            sim_color = get_similarity_color(similarity)

            # Use └─ for last item, ├─ for others
            tree_char = "└─" if idx == len(duplicate_entries) - 1 else "├─"

            print(
                f"    {tree_char} {info['path']} {Style.DIM}({info['size']})"
                f"{Style.RESET_ALL} - {audio_info} {sim_color}"
                f"[{similarity:.1f}% match]{Style.RESET_ALL}"
            )
        print()


def format_output_json(duplicates: Dict[str, List[tuple]]) -> None:
    """Format and print duplicates in JSON format with quality info."""
    from .hasher import AudioHasher

    hasher = AudioHasher()
    output = []

    for hash_val, file_list in duplicates.items():
        # Identify highest quality file and get enriched file info
        best_file, best_fp, enriched_files = DuplicateManager.identify_highest_quality(
            file_list, hasher
        )

        files_data = []
        for (
            file_path,
            _fingerprint,
            metadata,
            quality_score,
            similarity,
        ) in enriched_files:
            file_info = DuplicateManager.get_file_info(file_path)
            file_info["audio_info"] = AudioHasher.format_audio_info(metadata)
            file_info["quality_score"] = quality_score
            file_info["similarity_to_best"] = similarity
            file_info["is_best"] = file_path == best_file
            files_data.append(file_info)

        group = {
            "hash": hash_val,
            "files": files_data,
        }
        output.append(group)

    print(json.dumps(output, indent=2))


def format_output_csv(duplicates: Dict[str, List[tuple]]) -> None:
    """Format and print duplicates in CSV format with quality info."""
    from .hasher import AudioHasher

    hasher = AudioHasher()

    print(
        "group_id,hash,file_path,file_size,file_size_bytes,"
        "audio_info,quality_score,similarity_to_best,is_best"
    )

    for idx, (hash_val, file_list) in enumerate(duplicates.items(), 1):
        # Identify highest quality file and get enriched file info
        best_file, best_fp, enriched_files = DuplicateManager.identify_highest_quality(
            file_list, hasher
        )

        for (
            file_path,
            _fingerprint,
            metadata,
            quality_score,
            similarity,
        ) in enriched_files:
            info = DuplicateManager.get_file_info(file_path)
            audio_info = AudioHasher.format_audio_info(metadata)
            is_best = "true" if file_path == best_file else "false"

            print(
                f"{idx},{hash_val},{info['path']},{info['size']},"
                f"{info['size_bytes']},{audio_info},{quality_score:.1f},"
                f"{similarity:.1f},{is_best}"
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
        "--cache-backend",
        choices=["sqlite", "json"],
        default="sqlite",
        help="Cache backend type (default: sqlite)",
    )

    parser.add_argument(
        "-w",
        "--workers",
        type=int,
        default=8,
        metavar="N",
        help="Number of worker threads for parallel fingerprinting "
        "(default: 8, use 1 for sequential)",
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
        cache_backend=args.cache_backend,
        max_workers=args.workers,
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
                deleted = DuplicateManager.interactive_delete(duplicates, finder.hasher)
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
