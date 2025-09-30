"""Audio hashing utilities for duplicate detection."""

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union


class AudioHasher:
    """Handles audio file hashing for duplicate detection."""

    SUPPORTED_FORMATS = {".mp3", ".flac", ".wav", ".ogg", ".m4a", ".aac", ".wma"}

    def __init__(
        self,
        cache_path: Optional[Path] = None,
        use_cache: bool = True,
        update_cache: bool = False,
    ):
        """
        Initialize audio hasher with optional cache.

        Args:
            cache_path: Path to cache file
                (default: $XDG_CONFIG_HOME/duperscooper/hashes.json)
            use_cache: Whether to use cache (default: True)
            update_cache: Force regeneration of cached hashes (default: False)
        """
        if cache_path is None:
            xdg_config = Path.home() / ".config"
            cache_dir = xdg_config / "duperscooper"
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_path = cache_dir / "hashes.json"

        self.cache_path = cache_path
        self.use_cache = use_cache
        self.update_cache = update_cache
        self.cache: Dict[str, str] = self._load_cache() if use_cache else {}
        self.cache_hits = 0
        self.cache_misses = 0
        self.cache_updates = 0

    def _load_cache(self) -> Dict[str, str]:
        """Load cache from disk."""
        if self.cache_path.exists():
            try:
                with open(self.cache_path) as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
                    return {}
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def save_cache(self) -> None:
        """Save cache to disk."""
        if not self.use_cache:
            return
        try:
            with open(self.cache_path, "w") as f:
                json.dump(self.cache, f)
        except OSError:
            pass  # Silent failure for cache writes

    def clear_cache(self) -> bool:
        """
        Delete the cache file.

        Returns:
            True if cache was deleted, False if it didn't exist or couldn't be deleted
        """
        try:
            if self.cache_path.exists():
                self.cache_path.unlink()
                self.cache.clear()
                return True
            return False
        except OSError:
            return False

    @staticmethod
    def is_audio_file(file_path: Path) -> bool:
        """Check if file has supported audio extension."""
        return file_path.suffix.lower() in AudioHasher.SUPPORTED_FORMATS

    @staticmethod
    def compute_file_hash(file_path: Path) -> str:
        """Compute SHA256 hash of file content (fast, exact match only)."""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()

    @staticmethod
    def _call_fpcalc(file_path: Path, raw: bool = False) -> Tuple[int, str]:
        """
        Call fpcalc binary directly to generate Chromaprint fingerprint.

        Python 3.13 removed modules that audioread depends on, so we bypass
        it and call fpcalc directly.

        Args:
            file_path: Path to audio file
            raw: If True, get raw (uncompressed) fingerprint for fuzzy matching

        Returns:
            Tuple of (duration_seconds, fingerprint_string)
        """
        try:
            cmd = ["fpcalc"]
            if raw:
                cmd.append("-raw")
            cmd.append(str(file_path))

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )

            # Parse fpcalc output
            duration = 0
            fingerprint = ""
            for line in result.stdout.strip().split("\n"):
                if line.startswith("DURATION="):
                    duration = int(line.split("=")[1])
                elif line.startswith("FINGERPRINT="):
                    fingerprint = line.split("=")[1]

            if not fingerprint:
                raise ValueError("fpcalc did not return a fingerprint")

            return (duration, fingerprint)

        except subprocess.TimeoutExpired as e:
            raise ValueError(f"fpcalc timed out processing {file_path}") from e
        except subprocess.CalledProcessError as e:
            raise ValueError(f"fpcalc failed for {file_path}: {e.stderr}") from e
        except FileNotFoundError as e:
            raise ValueError(
                "fpcalc not found. Install with: sudo apt install libchromaprint-tools"
            ) from e

    @staticmethod
    def parse_raw_fingerprint(raw_fp_str: str) -> List[int]:
        """Parse raw fingerprint string into list of integers."""
        return [int(x) for x in raw_fp_str.split(",")]

    @staticmethod
    def hamming_distance(fp1: List[int], fp2: List[int]) -> Tuple[int, int]:
        """
        Calculate Hamming distance between two raw fingerprints.

        Returns:
            Tuple of (different_bits, total_bits)
        """
        # Pad shorter fingerprint with zeros
        max_len = max(len(fp1), len(fp2))
        fp1_padded = fp1 + [0] * (max_len - len(fp1))
        fp2_padded = fp2 + [0] * (max_len - len(fp2))

        different_bits = 0
        total_bits = max_len * 32  # Each integer is 32 bits

        for a, b in zip(fp1_padded, fp2_padded):
            xor = a ^ b
            different_bits += bin(xor).count("1")

        return different_bits, total_bits

    @staticmethod
    def similarity_percentage(fp1: List[int], fp2: List[int]) -> float:
        """
        Calculate similarity percentage between two raw fingerprints.

        Returns:
            Similarity as percentage (0-100)
        """
        diff_bits, total_bits = AudioHasher.hamming_distance(fp1, fp2)
        if total_bits == 0:
            return 0.0
        return (1 - diff_bits / total_bits) * 100

    def compute_raw_fingerprint(self, file_path: Path) -> List[int]:
        """
        Compute raw Chromaprint fingerprint for fuzzy matching.

        Returns list of integers representing the raw fingerprint,
        suitable for similarity comparison using Hamming distance.

        Args:
            file_path: Path to audio file

        Returns:
            List of integers representing raw fingerprint

        Raises:
            ValueError: If fingerprinting fails
        """
        try:
            duration, raw_fp_str = AudioHasher._call_fpcalc(file_path, raw=True)
            return AudioHasher.parse_raw_fingerprint(raw_fp_str)
        except Exception as e:
            raise ValueError(
                f"Failed to fingerprint audio file {file_path}: {e}"
            ) from e

    def compute_audio_hash(
        self, file_path: Path, algorithm: str = "perceptual"
    ) -> Union[str, List[int]]:
        """
        Compute audio fingerprint using Chromaprint.

        For 'perceptual' algorithm, returns raw fingerprint (list of integers)
        for fuzzy similarity matching across different bitrates and formats.

        For 'exact' algorithm, returns SHA256 hash for byte-identical matching.

        Args:
            file_path: Path to audio file
            algorithm: Hash algorithm - 'perceptual' (default) or 'exact'

        Returns:
            For perceptual: List[int] (raw fingerprint)
            For exact: str (SHA256 hash)

        Raises:
            ValueError: If fingerprinting fails
        """
        if algorithm == "exact":
            return AudioHasher.compute_file_hash(file_path)

        # Check cache using file hash as key
        file_hash = AudioHasher.compute_file_hash(file_path)

        # If update_cache mode and file exists in cache, regenerate
        if self.use_cache and self.update_cache and file_hash in self.cache:
            self.cache_updates += 1
            # Fall through to recompute hash
        elif self.use_cache and file_hash in self.cache:
            # Normal cache hit - return cached raw fingerprint
            self.cache_hits += 1
            cached_value = self.cache[file_hash]
            # Cache stores comma-separated string, parse it
            return AudioHasher.parse_raw_fingerprint(cached_value)
        elif self.use_cache:
            # Cache miss
            self.cache_misses += 1

        try:
            # Get raw fingerprint for fuzzy matching
            raw_fingerprint = self.compute_raw_fingerprint(file_path)

            # Store in cache as comma-separated string
            if self.use_cache:
                self.cache[file_hash] = ",".join(str(x) for x in raw_fingerprint)

            return raw_fingerprint

        except Exception as e:
            raise ValueError(f"Failed to hash audio file {file_path}: {e}") from e

    @staticmethod
    def get_audio_metadata(file_path: Path) -> Dict[str, Optional[Union[float, int]]]:
        """
        Extract basic audio metadata.

        Note: This function is currently not implemented to avoid
        Python 3.13 compatibility issues with pydub/audioop.
        Metadata extraction may be added in future versions.
        """
        return {
            "duration": None,
            "channels": None,
            "sample_rate": None,
            "bitrate": None,
        }
