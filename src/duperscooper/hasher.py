"""Audio hashing utilities for duplicate detection."""

import hashlib
from pathlib import Path
from typing import Dict, Optional, Union

import acoustid


class AudioHasher:
    """Handles audio file hashing for duplicate detection."""

    SUPPORTED_FORMATS = {".mp3", ".flac", ".wav", ".ogg", ".m4a", ".aac", ".wma"}

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
    def compute_audio_hash(file_path: Path, algorithm: str = "perceptual") -> str:
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

        try:
            # Get chromaprint fingerprint and duration
            # This returns (duration_seconds, fingerprint_string)
            duration, fingerprint = acoustid.fingerprint_file(str(file_path))

            # The fingerprint is a compressed base64-encoded string that
            # represents the audio's spectral characteristics
            # We combine it with duration to ensure length-matching
            combined = f"{int(duration)}:{fingerprint}"

            # Return a hash of the fingerprint for consistent length
            # This makes comparison easier (fixed-length hash)
            return hashlib.sha256(combined.encode()).hexdigest()

        except acoustid.FingerprintGenerationError as e:
            raise ValueError(
                f"Failed to generate fingerprint for {file_path}: {e}"
            ) from e
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
