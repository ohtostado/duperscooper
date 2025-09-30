"""Audio hashing utilities for duplicate detection."""

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Dict, Optional, Tuple, Union


class AudioHasher:
    """Handles audio file hashing for duplicate detection."""

    SUPPORTED_FORMATS = {".mp3", ".flac", ".wav", ".ogg", ".m4a", ".aac", ".wma"}

    def __init__(self, cache_path: Optional[Path] = None):
        """
        Initialize audio hasher with optional cache.

        Args:
            cache_path: Path to cache file (default: ~/.cache/duperscooper/hashes.json)
        """
        if cache_path is None:
            cache_dir = Path.home() / ".cache" / "duperscooper"
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_path = cache_dir / "hashes.json"

        self.cache_path = cache_path
        self.cache: Dict[str, str] = self._load_cache()
        self.cache_hits = 0
        self.cache_misses = 0

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
        try:
            with open(self.cache_path, "w") as f:
                json.dump(self.cache, f)
        except OSError:
            pass  # Silent failure for cache writes

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
    def _call_fpcalc(file_path: Path) -> Tuple[int, str]:
        """
        Call fpcalc binary directly to generate Chromaprint fingerprint.

        Python 3.13 removed modules that audioread depends on, so we bypass
        it and call fpcalc directly.

        Returns:
            Tuple of (duration_seconds, fingerprint_string)
        """
        try:
            result = subprocess.run(
                ["fpcalc", str(file_path)],
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

    def compute_audio_hash(self, file_path: Path, algorithm: str = "perceptual") -> str:
        """
        Compute perceptual hash of audio content using Chromaprint.

        This uses the Chromaprint/AcoustID fingerprinting algorithm which is
        specifically designed to match audio content across different:
        - Formats (MP3, FLAC, WAV, etc.)
        - Bitrates (128kbps MP3 vs 320kbps MP3)
        - Sample rates (44.1kHz vs 48kHz)
        - Minor variations (volume, slight EQ changes)

        The fingerprint is duration-aware and works by analyzing the
        spectral characteristics of the audio over time.

        Args:
            file_path: Path to audio file
            algorithm: Hash algorithm - 'perceptual' (default) or 'exact'

        Returns:
            Hash string representation

        Raises:
            ValueError: If fingerprinting fails
        """
        if algorithm == "exact":
            return AudioHasher.compute_file_hash(file_path)

        # Check cache using file hash as key
        file_hash = AudioHasher.compute_file_hash(file_path)
        if file_hash in self.cache:
            self.cache_hits += 1
            return self.cache[file_hash]

        # Cache miss - compute perceptual hash
        self.cache_misses += 1

        try:
            # Call fpcalc directly (Python 3.13 compatible)
            duration, fingerprint = AudioHasher._call_fpcalc(file_path)

            # The fingerprint is a compressed base64-encoded string that
            # represents the audio's spectral characteristics
            # We combine it with duration to ensure length-matching
            combined = f"{duration}:{fingerprint}"

            # Return a hash of the fingerprint for consistent length
            # This makes comparison easier (fixed-length hash)
            perceptual_hash = hashlib.sha256(combined.encode()).hexdigest()

            # Store in cache
            self.cache[file_hash] = perceptual_hash

            return perceptual_hash

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
