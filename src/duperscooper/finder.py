"""Core duplicate audio file finding logic."""

import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Union

from colorama import Fore, Style

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
        cache_backend: str = "sqlite",
        max_workers: int = 8,
    ):
        """
        Initialize duplicate finder.

        Args:
            min_size: Minimum file size in bytes to consider
            algorithm: Hash algorithm - 'perceptual' or 'exact'
            verbose: Enable verbose output
            cache_path: Path to hash cache file/database
                (default: $XDG_CONFIG_HOME/duperscooper/hashes.{db,json})
            use_cache: Whether to use cache (default: True)
            update_cache: Force regeneration of cached hashes (default: False)
            similarity_threshold: Minimum similarity % for perceptual matching
                (default: 98.0)
            cache_backend: Cache backend type: 'sqlite' or 'json' (default: 'sqlite')
            max_workers: Maximum number of worker threads for parallel fingerprinting
                (default: 8)
        """
        self.min_size = min_size
        self.algorithm = algorithm
        self.verbose = verbose
        self.similarity_threshold = similarity_threshold
        self.max_workers = max_workers
        self.hasher = AudioHasher(
            cache_path=cache_path,
            use_cache=use_cache,
            update_cache=update_cache,
            cache_backend=cache_backend,
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
                        print(
                            f"\r{Fore.CYAN}Found {count} files...{Style.RESET_ALL}",
                            end="",
                            flush=True,
                        )
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
                            print(
                                f"\r{Fore.CYAN}Found {count} files...{Style.RESET_ALL}",
                                end="",
                                flush=True,
                            )

        # Print final accurate count
        if self.verbose and count > 0:
            print(
                f"\r{Fore.CYAN}Found {count} files...{Fore.GREEN}done{Style.RESET_ALL}",
                flush=True,
            )

        return audio_files

    def find_duplicates(self, paths: List[Path]) -> Dict[str, List[tuple]]:
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
            workers_info = (
                f" (using {self.max_workers} worker threads)"
                if self.max_workers > 1
                else ""
            )
            print(f"Computing {mode} fingerprints{workers_info}...")

        # Compute fingerprints for all files (parallel or sequential)
        file_fingerprints: List[tuple] = []  # (file_path, fingerprint)
        total_files = len(audio_files)

        if self.max_workers > 1:
            # Parallel fingerprinting with ThreadPoolExecutor
            file_fingerprints = self._fingerprint_parallel(audio_files)
        else:
            # Sequential fingerprinting (original behavior)
            file_fingerprints = self._fingerprint_sequential(audio_files)

        # Print completion
        if self.verbose and total_files > 0:
            print(
                f"\r{Fore.CYAN}Fingerprinted {total_files}/{total_files} files "
                f"(100.0%)...{Fore.GREEN}done{Style.RESET_ALL}",
                flush=True,
            )

        # Cache is auto-saved by backend (no manual save needed)

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
                stats = self.hasher.get_cache_stats()
                if self.hasher.update_cache:
                    print(
                        f"Cache: {stats['hits']} hits, "
                        f"{stats['misses']} misses, "
                        f"{self.hasher.cache_updates} updated"
                    )
                else:
                    print(f"Cache: {stats['hits']} hits, {stats['misses']} misses")
            if self.error_count > 0:
                print(f"Encountered {self.error_count} error(s) during processing")

        return duplicates

    def _fingerprint_sequential(self, audio_files: List[Path]) -> List[tuple]:
        """
        Compute fingerprints sequentially (single-threaded).

        Args:
            audio_files: List of audio file paths

        Returns:
            List of (file_path, fingerprint) tuples
        """
        file_fingerprints: List[tuple] = []
        total_files = len(audio_files)

        for idx, file_path in enumerate(audio_files, 1):
            try:
                fingerprint = self.hasher.compute_audio_hash(file_path, self.algorithm)
                file_fingerprints.append((file_path, fingerprint))

                # Show progress every 10 files or on last file
                if self.verbose and (idx % 10 == 0 or idx == total_files):
                    percent = (idx / total_files) * 100
                    print(
                        f"\r{Fore.CYAN}Fingerprinted {idx}/{total_files} files "
                        f"({percent:.1f}%)...{Style.RESET_ALL}",
                        end="",
                        flush=True,
                    )
            except Exception as e:
                self._log_error(f"Error fingerprinting {file_path}: {e}")

        return file_fingerprints

    def _fingerprint_parallel(self, audio_files: List[Path]) -> List[tuple]:
        """
        Compute fingerprints in parallel using ThreadPoolExecutor.

        Args:
            audio_files: List of audio file paths

        Returns:
            List of (file_path, fingerprint) tuples
        """
        file_fingerprints: List[tuple] = []
        total_files = len(audio_files)
        completed = 0
        lock = threading.Lock()

        # Time tracking for ETA
        start_time = time.time()
        last_update_time = start_time

        def fingerprint_file(file_path: Path) -> Optional[tuple]:
            """Fingerprint a single file."""
            try:
                fingerprint = self.hasher.compute_audio_hash(file_path, self.algorithm)
                return (file_path, fingerprint)
            except Exception as e:
                self._log_error(f"Error fingerprinting {file_path}: {e}")
                return None

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_file = {
                executor.submit(fingerprint_file, file_path): file_path
                for file_path in audio_files
            }

            # Process results as they complete
            for future in as_completed(future_to_file):
                result = future.result()
                if result is not None:
                    with lock:
                        file_fingerprints.append(result)
                        completed += 1

                        # Update progress and show ETA
                        current_time = time.time()
                        if self.verbose and (
                            completed % 10 == 0
                            or completed == total_files
                            or current_time - last_update_time >= 1.0
                        ):
                            percent = (completed / total_files) * 100
                            elapsed = current_time - start_time

                            # Calculate ETA
                            if completed > 0 and completed < total_files:
                                avg_time_per_file = elapsed / completed
                                remaining_files = total_files - completed
                                eta_seconds = avg_time_per_file * remaining_files
                                eta_str = self._format_time(eta_seconds)
                                elapsed_str = self._format_time(elapsed)
                                print(
                                    f"\r{Fore.CYAN}Fingerprinted "
                                    f"{completed}/{total_files} files "
                                    f"({percent:.1f}%) - Elapsed: {elapsed_str} "
                                    f"- ETA: {eta_str}{Style.RESET_ALL}",
                                    end="",
                                    flush=True,
                                )
                            else:
                                print(
                                    f"\r{Fore.CYAN}Fingerprinted "
                                    f"{completed}/{total_files} files "
                                    f"({percent:.1f}%)...{Style.RESET_ALL}",
                                    end="",
                                    flush=True,
                                )

                            last_update_time = current_time
                else:
                    with lock:
                        completed += 1

        return file_fingerprints

    def _format_time(self, seconds: float) -> str:
        """
        Format time duration as human-readable string.

        Args:
            seconds: Duration in seconds

        Returns:
            Formatted string (e.g., "2m 30s", "45s", "1h 5m")
        """
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{minutes}m {secs}s"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}h {minutes}m"

    def _group_exact_duplicates(
        self, file_fingerprints: List[tuple]
    ) -> Dict[str, List[tuple]]:
        """
        Group files by exact hash match.

        Returns:
            Dict mapping hash to list of (file_path, hash) tuples
        """
        hash_to_files: Dict[str, List[tuple]] = defaultdict(list)
        for file_path, file_hash in file_fingerprints:
            hash_to_files[file_hash].append((file_path, file_hash))

        # Filter to only duplicates
        return {
            hash_val: file_list
            for hash_val, file_list in hash_to_files.items()
            if len(file_list) > 1
        }

    def _group_fuzzy_duplicates(
        self, file_fingerprints: List[tuple]
    ) -> Dict[str, List[tuple]]:
        """
        Group files by fuzzy similarity using Union-Find algorithm.

        Files with similarity >= threshold are grouped together.

        Returns:
            Dict mapping group_id to list of (file_path, fingerprint) tuples
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
                        f"\r{Fore.CYAN}Compared {comparisons}/{total_comparisons} "
                        f"pairs ({pct:.1f}%)...{Style.RESET_ALL}",
                        end="",
                        flush=True,
                    )

        if self.verbose and total_comparisons > 0:
            print(
                f"\r{Fore.CYAN}Compared {total_comparisons}/{total_comparisons} pairs "
                f"(100.0%)...{Fore.GREEN}done{Style.RESET_ALL}",
                flush=True,
            )

        # Group files by their root parent, preserving fingerprints
        groups: Dict[int, ListType[tuple]] = defaultdict(list)
        for i, (file_path, fingerprint) in enumerate(file_fingerprints):
            root = find(i)
            groups[root].append((file_path, fingerprint))

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
    def identify_highest_quality(
        file_list: List[tuple], hasher: "AudioHasher"
    ) -> tuple:
        """
        Identify the highest quality file in a duplicate group.

        Args:
            file_list: List of (file_path, fingerprint) tuples
            hasher: AudioHasher instance for metadata extraction

        Returns:
            Tuple of (best_file_path, best_fingerprint, all_files_with_metadata)
            where all_files_with_metadata is a list of:
            (file_path, fingerprint, metadata, quality_score, similarity_to_best)
        """
        # Get metadata and quality scores for all files
        files_with_scores = []
        for file_path, fingerprint in file_list:
            metadata = hasher.get_audio_metadata(file_path)
            quality_score = hasher.calculate_quality_score(metadata)
            files_with_scores.append((file_path, fingerprint, metadata, quality_score))

        # Sort by quality score (highest first)
        files_with_scores.sort(key=lambda x: x[3], reverse=True)

        # Best file is the first one
        best_file, best_fp, best_meta, best_score = files_with_scores[0]

        # Calculate similarity to best file for all others
        enriched_files = []
        for file_path, fingerprint, metadata, quality_score in files_with_scores:
            if file_path == best_file:
                # Best file has 100% similarity to itself
                similarity = 100.0
            else:
                # Calculate similarity to best file's fingerprint
                similarity = hasher.similarity_percentage(fingerprint, best_fp)

            enriched_files.append(
                (file_path, fingerprint, metadata, quality_score, similarity)
            )

        return (best_file, best_fp, enriched_files)

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
    def interactive_delete(
        duplicates: Dict[str, List[tuple]], hasher: "AudioHasher"
    ) -> int:
        """
        Interactively delete duplicate files with quality information.

        Args:
            duplicates: Dictionary mapping hash to duplicate file tuples
            hasher: AudioHasher instance for metadata extraction

        Returns:
            Number of files deleted
        """
        deleted_count = 0

        for idx, (hash_val, file_list) in enumerate(duplicates.items(), 1):
            print(
                f"\n{Fore.CYAN}{Style.BRIGHT}--- Duplicate Group "
                f"{idx}/{len(duplicates)} ---{Style.RESET_ALL}"
            )
            print(f"{Style.DIM}Hash: {hash_val[:16]}...{Style.RESET_ALL}")

            # Identify highest quality file and get enriched file info
            best_file, best_fp, enriched_files = (
                DuplicateManager.identify_highest_quality(file_list, hasher)
            )

            # Display all files in group with quality info
            # Separate best file from duplicates for sorting
            best_entry = None
            duplicate_entries = []
            for entry in enriched_files:
                file_path_entry = entry[0]
                if file_path_entry == best_file:
                    best_entry = entry
                else:
                    duplicate_entries.append(entry)

            # Sort duplicates by similarity descending (best matches first)
            duplicate_entries.sort(key=lambda x: x[4], reverse=True)

            # Combine back together for display with proper indices
            display_entries = []
            if best_entry:
                display_entries.append(best_entry)
            display_entries.extend(duplicate_entries)

            files_for_deletion = []
            for i, (
                file_path,
                _fingerprint,
                metadata,
                _quality_score,
                similarity,
            ) in enumerate(display_entries):
                info = DuplicateManager.get_file_info(file_path)
                audio_info = hasher.format_audio_info(metadata)

                if file_path == best_file:
                    print(
                        f"  [{i}] {Fore.LIGHTGREEN_EX}{Style.BRIGHT}[Best]"
                        f"{Style.RESET_ALL} {info['path']} "
                        f"{Style.DIM}({info['size']}){Style.RESET_ALL} - "
                        f"{Fore.LIGHTGREEN_EX}{audio_info}{Style.RESET_ALL}"
                    )
                else:
                    # Use similarity color coding
                    sim_color = (
                        Fore.GREEN
                        if similarity >= 99.0
                        else Fore.YELLOW if similarity >= 95.0 else Fore.LIGHTRED_EX
                    )
                    print(
                        f"  [{i}] {info['path']} {Style.DIM}({info['size']})"
                        f"{Style.RESET_ALL} - {audio_info} {sim_color}"
                        f"[{similarity:.1f}% match]{Style.RESET_ALL}"
                    )
                files_for_deletion.append(file_path)

            # Ask user what to do
            print(f"\n{Style.BRIGHT}Options:{Style.RESET_ALL}")
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
                        if 0 <= index < len(files_for_deletion):
                            file_to_delete = files_for_deletion[index]
                            try:
                                file_to_delete.unlink()
                                print(
                                    f"  {Fore.GREEN}✓ Deleted:{Style.RESET_ALL} "
                                    f"{file_to_delete}"
                                )
                                deleted_count += 1
                            except OSError as e:
                                print(
                                    f"  {Fore.RED}✗ Failed to delete {file_to_delete}: "
                                    f"{e}{Style.RESET_ALL}"
                                )
                        else:
                            print(
                                f"  {Fore.RED}✗ Invalid index: {index}{Style.RESET_ALL}"
                            )
                except ValueError:
                    print(
                        f"  {Fore.RED}✗ Invalid input. Please enter numbers "
                        f"separated by spaces.{Style.RESET_ALL}"
                    )

        return deleted_count
