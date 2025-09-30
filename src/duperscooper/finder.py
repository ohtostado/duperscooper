"""Core duplicate audio file finding logic."""

import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Union

from .hasher import AudioHasher


class DuplicateFinder:
    """Finds duplicate audio files in given paths."""

    def __init__(
        self,
        min_size: int = 0,
        algorithm: str = "perceptual",
        verbose: bool = False,
        cache_path: Optional[Path] = None,
        use_cache: bool = True,
        update_cache: bool = False,
        similarity_threshold: float = 98.0,
    ):
        """
        Initialize duplicate finder.

        Args:
            min_size: Minimum file size in bytes to consider
            algorithm: Hash algorithm - 'perceptual' or 'exact'
            verbose: Enable verbose output
            cache_path: Path to hash cache file
                (default: $XDG_CONFIG_HOME/duperscooper/hashes.json)
            use_cache: Whether to use cache (default: True)
            update_cache: Force regeneration of cached hashes (default: False)
            similarity_threshold: Minimum similarity % for perceptual matching
                (default: 98.0)
        """
        self.min_size = min_size
        self.algorithm = algorithm
        self.verbose = verbose
        self.similarity_threshold = similarity_threshold
        self.hasher = AudioHasher(
            cache_path=cache_path, use_cache=use_cache, update_cache=update_cache
        )
        self.error_count = 0

    def find_audio_files(self, paths: List[Path]) -> List[Path]:
        """
        Recursively find all audio files in given paths.

        Args:
            paths: List of file or directory paths to search

        Returns:
            List of audio file paths
        """
        audio_files: List[Path] = []
        count = 0

        for path in paths:
            if not path.exists():
                self._log_error(f"Path does not exist: {path}")
                continue

            if path.is_file():
                if self.hasher.is_audio_file(path) and self._meets_size_requirement(
                    path
                ):
                    audio_files.append(path)
                    count += 1
                    if self.verbose and count % 100 == 0:
                        print(f"\rFound {count} files...", end="", flush=True)
            elif path.is_dir():
                for file_path in path.rglob("*"):
                    if (
                        file_path.is_file()
                        and self.hasher.is_audio_file(file_path)
                        and self._meets_size_requirement(file_path)
                    ):
                        audio_files.append(file_path)
                        count += 1
                        if self.verbose and count % 100 == 0:
                            print(f"\rFound {count} files...", end="", flush=True)

        # Print final accurate count
        if self.verbose and count > 0:
            print(f"\rFound {count} files...done", flush=True)

        return audio_files

    def find_duplicates(self, paths: List[Path]) -> Dict[str, List[Path]]:
        """
        Find duplicate audio files in given paths.

        For perceptual algorithm, uses fuzzy matching with similarity threshold.
        For exact algorithm, uses byte-identical hash matching.

        Args:
            paths: List of file or directory paths to search

        Returns:
            Dictionary mapping group ID to list of duplicate file paths
        """
        if self.verbose:
            print(f"Searching for audio files in {len(paths)} path(s)...")

        audio_files = self.find_audio_files(paths)

        if self.verbose:
            mode = (
                f"perceptual (≥{self.similarity_threshold}% similar)"
                if self.algorithm == "perceptual"
                else "exact"
            )
            print(f"Computing {mode} fingerprints...")

        # Compute fingerprints for all files
        file_fingerprints: List[tuple] = []  # (file_path, fingerprint)
        total_files = len(audio_files)

        for idx, file_path in enumerate(audio_files, 1):
            try:
                fingerprint = self.hasher.compute_audio_hash(file_path, self.algorithm)
                file_fingerprints.append((file_path, fingerprint))

                # Show progress every 10 files or on last file
                if self.verbose and (idx % 10 == 0 or idx == total_files):
                    percent = (idx / total_files) * 100
                    print(
                        f"\rFingerprinted {idx}/{total_files} files "
                        f"({percent:.1f}%)...",
                        end="",
                        flush=True,
                    )
            except Exception as e:
                self._log_error(f"Error fingerprinting {file_path}: {e}")

        # Print completion
        if self.verbose and total_files > 0:
            print(
                f"\rFingerprinted {total_files}/{total_files} files (100.0%)...done",
                flush=True,
            )

        # Save cache to disk
        self.hasher.save_cache()

        # Group duplicates based on algorithm
        if self.algorithm == "exact":
            duplicates = self._group_exact_duplicates(file_fingerprints)
        else:  # perceptual
            duplicates = self._group_fuzzy_duplicates(file_fingerprints)

        if self.verbose:
            redundant = sum(len(files) - 1 for files in duplicates.values())
            print(
                f"\nFound {len(duplicates)} group(s) of duplicates "
                f"({redundant} redundant file(s))"
            )
            if self.algorithm == "perceptual" and self.hasher.use_cache:
                if self.hasher.update_cache:
                    print(
                        f"Cache: {self.hasher.cache_hits} hits, "
                        f"{self.hasher.cache_misses} misses, "
                        f"{self.hasher.cache_updates} updated"
                    )
                else:
                    print(
                        f"Cache: {self.hasher.cache_hits} hits, "
                        f"{self.hasher.cache_misses} misses"
                    )
            if self.error_count > 0:
                print(f"Encountered {self.error_count} error(s) during processing")

        return duplicates

    def _group_exact_duplicates(
        self, file_fingerprints: List[tuple]
    ) -> Dict[str, List[Path]]:
        """Group files by exact hash match."""
        hash_to_files: Dict[str, List[Path]] = defaultdict(list)
        for file_path, file_hash in file_fingerprints:
            hash_to_files[file_hash].append(file_path)

        # Filter to only duplicates
        return {
            hash_val: file_list
            for hash_val, file_list in hash_to_files.items()
            if len(file_list) > 1
        }

    def _group_fuzzy_duplicates(
        self, file_fingerprints: List[tuple]
    ) -> Dict[str, List[Path]]:
        """
        Group files by fuzzy similarity using Union-Find algorithm.

        Files with similarity >= threshold are grouped together.
        """
        from typing import List as ListType

        if self.verbose:
            print(
                f"Comparing fingerprints (threshold: {self.similarity_threshold}%)..."
            )

        n = len(file_fingerprints)
        if n == 0:
            return {}

        # Union-Find data structure
        parent = list(range(n))

        def find(x: int) -> int:
            if parent[x] != x:
                parent[x] = find(parent[x])
            return parent[x]

        def union(x: int, y: int) -> None:
            px, py = find(x), find(y)
            if px != py:
                parent[px] = py

        # Compare all pairs
        comparisons = 0
        total_comparisons = (n * (n - 1)) // 2

        for i in range(n):
            for j in range(i + 1, n):
                _, fp1 = file_fingerprints[i]
                _, fp2 = file_fingerprints[j]

                similarity = AudioHasher.similarity_percentage(fp1, fp2)
                if similarity >= self.similarity_threshold:
                    union(i, j)

                comparisons += 1
                if self.verbose and comparisons % 100 == 0:
                    pct = (comparisons / total_comparisons) * 100
                    print(
                        f"\rCompared {comparisons}/{total_comparisons} pairs "
                        f"({pct:.1f}%)...",
                        end="",
                        flush=True,
                    )

        if self.verbose and total_comparisons > 0:
            print(
                f"\rCompared {total_comparisons}/{total_comparisons} pairs "
                f"(100.0%)...done",
                flush=True,
            )

        # Group files by their root parent
        groups: Dict[int, ListType[Path]] = defaultdict(list)
        for i, (file_path, _) in enumerate(file_fingerprints):
            root = find(i)
            groups[root].append(file_path)

        # Filter to only groups with multiple files, convert to string keys
        duplicates = {
            f"group_{root}": file_list
            for root, file_list in groups.items()
            if len(file_list) > 1
        }

        return duplicates

    def _meets_size_requirement(self, file_path: Path) -> bool:
        """Check if file meets minimum size requirement."""
        try:
            return file_path.stat().st_size >= self.min_size
        except OSError:
            return False

    def _log_error(self, message: str) -> None:
        """Log error message to stderr."""
        print(f"ERROR: {message}", file=sys.stderr)
        self.error_count += 1


class DuplicateManager:
    """Manages duplicate file operations like deletion."""

    @staticmethod
    def format_file_size(size_bytes: Union[int, float]) -> str:
        """Format file size in human-readable format."""
        size_float = float(size_bytes)
        for unit in ["B", "KB", "MB", "GB"]:
            if size_float < 1024.0:
                return f"{size_float:.1f} {unit}"
            size_float /= 1024.0
        return f"{size_float:.1f} TB"

    @staticmethod
    def get_file_info(file_path: Path) -> Dict[str, Union[str, int]]:
        """Get file information for display."""
        try:
            stat = file_path.stat()
            return {
                "path": str(file_path.absolute()),
                "size": DuplicateManager.format_file_size(stat.st_size),
                "size_bytes": stat.st_size,
            }
        except OSError as e:
            return {
                "path": str(file_path.absolute()),
                "size": f"Error: {e}",
                "size_bytes": 0,
            }

    @staticmethod
    def interactive_delete(duplicates: Dict[str, List[Path]]) -> int:
        """
        Interactively delete duplicate files.

        Args:
            duplicates: Dictionary mapping hash to duplicate file paths

        Returns:
            Number of files deleted
        """
        deleted_count = 0

        for idx, (hash_val, file_list) in enumerate(duplicates.items(), 1):
            print(f"\n--- Duplicate Group {idx}/{len(duplicates)} ---")
            print(f"Hash: {hash_val[:16]}...")

            # Display all files in group
            for i, file_path in enumerate(file_list):
                info = DuplicateManager.get_file_info(file_path)
                print(f"  [{i}] {info['path']} ({info['size']})")

            # Ask user what to do
            print("\nOptions:")
            print("  - Enter file number(s) to delete (space-separated)")
            print("  - Press Enter to skip this group")
            print("  - Type 'q' to quit")

            choice = input("Your choice: ").strip().lower()

            if choice == "q":
                break
            elif choice == "":
                continue
            else:
                # Parse selected indices
                try:
                    indices = [int(x) for x in choice.split()]
                    for index in indices:
                        if 0 <= index < len(file_list):
                            file_to_delete = file_list[index]
                            try:
                                file_to_delete.unlink()
                                print(f"  ✓ Deleted: {file_to_delete}")
                                deleted_count += 1
                            except OSError as e:
                                print(f"  ✗ Failed to delete {file_to_delete}: {e}")
                        else:
                            print(f"  ✗ Invalid index: {index}")
                except ValueError:
                    print(
                        "  ✗ Invalid input. Please enter numbers separated by spaces."
                    )

        return deleted_count
