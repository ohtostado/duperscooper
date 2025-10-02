"""CLI interface for duperscooper."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from colorama import Fore, Style, init

try:
    from shtab import FILE
except ImportError:
    # shtab not installed - tab completion won't work but that's okay
    FILE = None  # type: ignore

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


def _calculate_track_group_avg_match(file_list: List[tuple], hasher: Any) -> float:
    """Calculate average match percentage for a track group."""
    if len(file_list) <= 1:
        return 100.0

    # Get enriched file info with similarities
    _, _, enriched_files = DuplicateManager.identify_highest_quality(file_list, hasher)

    # Extract similarities
    # (enriched_files format: (path, size, info, score, similarity))
    similarities = [
        float(entry[4]) for entry in enriched_files
    ]  # entry[4] is similarity
    return float(sum(similarities) / len(similarities)) if similarities else 0.0


def format_output_text(duplicates: Dict[str, List[tuple]]) -> None:
    """Format and print duplicates in text format with quality info."""
    if not duplicates:
        print("No duplicates found.")
        return

    from .hasher import AudioHasher

    hasher = AudioHasher()

    # Sort groups by average match percentage descending
    sorted_groups = sorted(
        duplicates.items(),
        key=lambda item: _calculate_track_group_avg_match(item[1], hasher),
        reverse=True,
    )

    print(
        f"{Fore.CYAN}{Style.BRIGHT}Found {len(sorted_groups)} group(s) "
        f"of duplicate files:{Style.RESET_ALL}\n"
    )

    for idx, (hash_val, file_list) in enumerate(sorted_groups, 1):
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

        # Sort duplicates by quality ascending (worst first),
        # then similarity descending. Shows deletion candidates first.
        duplicate_entries.sort(key=lambda x: (x[3], -x[4]))

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

    # Sort groups by average match percentage descending
    sorted_groups = sorted(
        duplicates.items(),
        key=lambda item: _calculate_track_group_avg_match(item[1], hasher),
        reverse=True,
    )

    output = []
    for hash_val, file_list in sorted_groups:
        # Identify highest quality file and get enriched file info
        best_file, best_fp, enriched_files = DuplicateManager.identify_highest_quality(
            file_list, hasher
        )

        # Separate best from duplicates
        best_entry = None
        duplicate_entries = []
        for entry in enriched_files:
            if entry[0] == best_file:
                best_entry = entry
            else:
                duplicate_entries.append(entry)

        # Sort duplicates by quality ascending, then similarity descending
        duplicate_entries.sort(key=lambda x: (x[3], -x[4]))

        # Reassemble with best first
        sorted_files = [best_entry] + duplicate_entries if best_entry else []

        files_data = []
        for (
            file_path,
            _fingerprint,
            metadata,
            quality_score,
            similarity,
        ) in sorted_files:
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


def _get_album_match_percentage(album: Any, best_album: Any, hasher: Any) -> float:
    """Get match percentage for an album compared to the best album."""
    if album == best_album:
        return 100.0
    elif album.match_method == "MusicBrainz Album ID":
        return 100.0
    else:
        # Calculate fingerprint similarity to best album
        sim: float = (
            hasher.similarity_percentage(
                best_album.fingerprints[0], album.fingerprints[0]
            )
            if best_album.fingerprints and album.fingerprints
            else 0.0
        )
        return sim


def format_album_output_text(
    duplicate_groups: List[List], hasher: Any, finder: Any
) -> None:
    """Format and print duplicate albums in text format."""
    if not duplicate_groups:
        print("No duplicate albums found.")
        return

    print(
        f"{Fore.CYAN}{Style.BRIGHT}Found {len(duplicate_groups)} group(s) "
        f"of duplicate albums:{Style.RESET_ALL}\n"
    )

    for idx, group in enumerate(duplicate_groups, 1):
        # Get matched album info for the group
        matched_album, matched_artist = finder.get_matched_album_info(group)

        print(
            f"{Fore.CYAN}{Style.BRIGHT}Group {idx}: "
            f"{matched_album} by {matched_artist}{Style.RESET_ALL}"
        )

        # Find best quality album as reference
        best_album = max(group, key=lambda a: a.avg_quality_score)

        # Separate best from duplicates
        duplicates = [a for a in group if a != best_album]

        # Sort duplicates by quality ascending (worst first),
        # then match percentage descending
        sorted_duplicates = sorted(
            duplicates,
            key=lambda a: (
                a.avg_quality_score,
                -_get_album_match_percentage(a, best_album, hasher),
            ),
        )

        # Best album first, then sorted duplicates
        sorted_albums = [best_album] + sorted_duplicates

        for album in sorted_albums:
            is_best = album == best_album
            marker = (
                f"{Fore.LIGHTGREEN_EX}{Style.BRIGHT}[Best]{Style.RESET_ALL} "
                if is_best
                else "  "
            )

            # Format size
            size_mb = album.total_size / (1024 * 1024)
            if size_mb >= 1024:
                size_str = f"{size_mb / 1024:.1f} GB"
            else:
                size_str = f"{size_mb:.1f} MB"

            # Print album info
            print(
                f"{marker}{album.path} {Style.DIM}"
                f"({album.track_count} tracks, {size_str}){Style.RESET_ALL}"
            )
            print(f"    Quality: {album.quality_info}")

            # Match method
            if album.match_method:
                print(f"    Matched by: {album.match_method}")

            # Get match percentage
            match_pct = _get_album_match_percentage(album, best_album, hasher)
            match_color = get_similarity_color(match_pct)
            if album.is_partial_match and album.overlap_percentage is not None:
                # Show partial match info
                print(
                    f"    Match: {match_color}{match_pct:.1f}%{Style.RESET_ALL} "
                    f"{Style.DIM}(Partial: {album.overlap_percentage:.1f}% overlap)"
                    f"{Style.RESET_ALL}"
                )
            else:
                print(f"    Match: {match_color}{match_pct:.1f}%{Style.RESET_ALL}")

            if album.musicbrainz_albumid:
                print(f"    MusicBrainz ID: {album.musicbrainz_albumid}")
            if album.album_name or album.artist_name:
                artist = album.artist_name or "Unknown"
                album_name = album.album_name or "Unknown"
                print(f"    Metadata: {artist} - {album_name}")

            print()


def format_album_output_json(
    duplicate_groups: List[List], hasher: Any, finder: Any
) -> None:
    """Format and print duplicate albums in JSON format."""

    output = []
    for group in duplicate_groups:
        # Get matched album info
        matched_album, matched_artist = finder.get_matched_album_info(group)

        albums_data = []
        # Find best quality album as reference
        best_album = max(group, key=lambda a: a.avg_quality_score)

        # Separate best from duplicates
        duplicates = [a for a in group if a != best_album]

        # Sort duplicates by quality ascending, then match % descending
        sorted_duplicates = sorted(
            duplicates,
            key=lambda a: (
                a.avg_quality_score,
                -_get_album_match_percentage(a, best_album, hasher),
            ),
        )

        # Best album first, then sorted duplicates
        sorted_albums = [best_album] + sorted_duplicates

        for album in sorted_albums:
            is_best = album == best_album

            # Get match percentage
            match_pct = _get_album_match_percentage(album, best_album, hasher)

            album_data = {
                "path": str(album.path),
                "track_count": album.track_count,
                "total_size": album.total_size,
                "quality_info": album.quality_info,
                "quality_score": album.avg_quality_score,
                "match_percentage": match_pct,
                "match_method": album.match_method,
                "is_best": is_best,
                "musicbrainz_albumid": album.musicbrainz_albumid,
                "album_name": album.album_name,
                "artist_name": album.artist_name,
                "has_mixed_mb_ids": album.has_mixed_mb_ids,
                "is_partial_match": album.is_partial_match,
                "overlap_percentage": album.overlap_percentage,
            }
            albums_data.append(album_data)

        output.append(
            {
                "matched_album": matched_album,
                "matched_artist": matched_artist,
                "albums": albums_data,
            }
        )

    print(json.dumps(output, indent=2))


def format_album_output_csv(
    duplicate_groups: List[List], hasher: Any, finder: Any
) -> None:
    """Format and print duplicate albums in CSV format."""

    print(
        "group_id,matched_album,matched_artist,album_path,track_count,"
        "total_size_bytes,total_size,quality_info,quality_score,match_percentage,"
        "match_method,is_best,musicbrainz_albumid,album_name,artist_name,"
        "has_mixed_mb_ids,is_partial_match,overlap_percentage"
    )

    for idx, group in enumerate(duplicate_groups, 1):
        # Get matched album info
        matched_album, matched_artist = finder.get_matched_album_info(group)

        # Find best quality album as reference
        best_album = max(group, key=lambda a: a.avg_quality_score)

        # Separate best from duplicates
        duplicates = [a for a in group if a != best_album]

        # Sort duplicates by quality ascending, then match % descending
        sorted_duplicates = sorted(
            duplicates,
            key=lambda a: (
                a.avg_quality_score,
                -_get_album_match_percentage(a, best_album, hasher),
            ),
        )

        # Best album first, then sorted duplicates
        sorted_albums = [best_album] + sorted_duplicates

        for album in sorted_albums:
            is_best = album == best_album

            # Get match percentage
            match_pct = _get_album_match_percentage(album, best_album, hasher)

            size_mb = album.total_size / (1024 * 1024)
            if size_mb >= 1024:
                size_str = f"{size_mb / 1024:.1f}GB"
            else:
                size_str = f"{size_mb:.1f}MB"

            is_best_str = "true" if is_best else "false"
            has_mixed = "true" if album.has_mixed_mb_ids else "false"
            is_partial_str = "true" if album.is_partial_match else "false"
            overlap_str = (
                f"{album.overlap_percentage:.1f}"
                if album.overlap_percentage is not None
                else ""
            )

            print(
                f"{idx},{matched_album},{matched_artist},{album.path},"
                f"{album.track_count},{album.total_size},{size_str},"
                f"{album.quality_info},{album.avg_quality_score:.1f},"
                f"{match_pct:.1f},{album.match_method or ''},"
                f"{is_best_str},{album.musicbrainz_albumid or ''},"
                f"{album.album_name or ''},{album.artist_name or ''},"
                f"{has_mixed},{is_partial_str},{overlap_str}"
            )


def format_output_csv(duplicates: Dict[str, List[tuple]]) -> None:
    """Format and print duplicates in CSV format with quality info."""
    from .hasher import AudioHasher

    hasher = AudioHasher()

    # Sort groups by average match percentage descending
    sorted_groups = sorted(
        duplicates.items(),
        key=lambda item: _calculate_track_group_avg_match(item[1], hasher),
        reverse=True,
    )

    print(
        "group_id,hash,file_path,file_size,file_size_bytes,"
        "audio_info,quality_score,similarity_to_best,is_best"
    )

    for idx, (hash_val, file_list) in enumerate(sorted_groups, 1):
        # Identify highest quality file and get enriched file info
        best_file, best_fp, enriched_files = DuplicateManager.identify_highest_quality(
            file_list, hasher
        )

        # Separate best from duplicates
        best_entry = None
        duplicate_entries = []
        for entry in enriched_files:
            if entry[0] == best_file:
                best_entry = entry
            else:
                duplicate_entries.append(entry)

        # Sort duplicates by quality ascending, then similarity descending
        duplicate_entries.sort(key=lambda x: (x[3], -x[4]))

        # Reassemble with best first
        sorted_files = [best_entry] + duplicate_entries if best_entry else []

        for (
            file_path,
            _fingerprint,
            metadata,
            quality_score,
            similarity,
        ) in sorted_files:
            info = DuplicateManager.get_file_info(file_path)
            audio_info = AudioHasher.format_audio_info(metadata)
            is_best = "true" if file_path == best_file else "false"

            print(
                f"{idx},{hash_val},{info['path']},{info['size']},"
                f"{info['size_bytes']},{audio_info},{quality_score:.1f},"
                f"{similarity:.1f},{is_best}"
            )


def get_parser() -> argparse.ArgumentParser:
    """
    Get the argument parser for duperscooper.

    This function is used by tab completion tools (e.g., shtab) to generate
    completion scripts.

    Returns:
        ArgumentParser configured with all duperscooper options
    """
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

    paths_arg = parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Paths to search for duplicate audio files (files or directories)",
    )
    # Enable file/directory completion for tab completion (shtab)
    if FILE is not None:
        paths_arg.complete = FILE  # type: ignore

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
        "--album-mode",
        action="store_true",
        help="Find duplicate albums instead of individual files",
    )

    parser.add_argument(
        "--album-match-strategy",
        choices=["auto", "musicbrainz", "fingerprint"],
        default="auto",
        help="Album matching strategy: 'auto' uses MusicBrainz IDs with "
        "fingerprint fallback, 'musicbrainz' uses only MB IDs, "
        "'fingerprint' uses only perceptual matching (default: auto)",
    )

    parser.add_argument(
        "--allow-partial-albums",
        action="store_true",
        help="Match albums with different track counts "
        "(e.g., missing tracks, bonus editions)",
    )

    parser.add_argument(
        "--min-album-overlap",
        type=float,
        default=70.0,
        help="Minimum percentage of tracks that must match for partial albums "
        "(default: 70.0)",
    )

    parser.add_argument(
        "--delete-duplicate-albums",
        action="store_true",
        help="Interactively delete duplicate albums after finding them "
        "(requires --album-mode)",
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    return parser


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = get_parser()
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

    # Validate album-mode-specific options
    if args.delete_duplicate_albums and not args.album_mode:
        print("Error: --delete-duplicate-albums requires --album-mode", file=sys.stderr)
        return 1

    # Album mode
    if args.album_mode:
        return run_album_mode(args)

    # File mode (original behavior)
    return run_file_mode(args)


def run_file_mode(args: argparse.Namespace) -> int:
    """Run duplicate file detection (original behavior)."""
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


def run_album_mode(args: argparse.Namespace) -> int:
    """Run duplicate album detection."""
    from .album import AlbumDuplicateFinder, AlbumScanner
    from .hasher import AudioHasher

    # Initialize components
    hasher = AudioHasher(
        use_cache=not args.no_cache,
        update_cache=args.update_cache,
        cache_backend=args.cache_backend,
    )
    scanner = AlbumScanner(hasher, verbose=not args.no_progress)
    finder = AlbumDuplicateFinder(
        hasher,
        verbose=not args.no_progress,
        allow_partial=args.allow_partial_albums,
        min_overlap=args.min_album_overlap,
    )

    try:
        # Scan for albums
        albums = scanner.scan_albums(args.paths, max_workers=args.workers)

        # Find duplicate albums
        duplicate_groups = finder.find_duplicates(
            albums, strategy=args.album_match_strategy
        )

    except KeyboardInterrupt:
        print("\nOperation cancelled by user.", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Handle delete mode (placeholder for Phase 4)
    if args.delete_duplicate_albums:
        print("Album deletion not yet implemented (Phase 4)", file=sys.stderr)
        return 1

    # Print cache statistics (text mode only)
    if args.output == "text" and not args.no_progress:
        # Track-level cache stats
        cache_stats = hasher.get_cache_stats()
        print(
            f"\nTrack fingerprint cache: {cache_stats['hits']} hits, "
            f"{cache_stats['misses']} misses, {cache_stats['size']} entries"
        )

        # Album-level cache stats
        print(
            f"Album metadata cache: {scanner.album_cache_hits} hits, "
            f"{scanner.album_cache_misses} misses"
        )

    # Format and output results
    if args.output == "json":
        format_album_output_json(duplicate_groups, hasher, finder)
    elif args.output == "csv":
        format_album_output_csv(duplicate_groups, hasher, finder)
    else:
        format_album_output_text(duplicate_groups, hasher, finder)

    # Exit with non-zero if duplicates found (for scripting)
    return 0 if not duplicate_groups else 2


if __name__ == "__main__":
    sys.exit(main())
