"""Audio hashing utilities for duplicate detection."""

import hashlib
from pathlib import Path
from typing import Dict, Optional, Union

import imagehash
import numpy as np
from PIL import Image
from pydub import AudioSegment


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
        Compute perceptual hash of audio content.

        Args:
            file_path: Path to audio file
            algorithm: Hash algorithm - 'perceptual' (default) or 'exact'

        Returns:
            Hash string representation
        """
        if algorithm == "exact":
            return AudioHasher.compute_file_hash(file_path)

        try:
            # Load audio file
            audio = AudioSegment.from_file(str(file_path))

            # Convert to mono and standardize sample rate
            audio = audio.set_channels(1).set_frame_rate(22050)

            # Get raw audio samples
            samples = np.array(audio.get_array_of_samples())

            # Normalize samples to 0-255 range for image hashing
            if len(samples) > 0:
                samples = samples.astype(np.float32)
                samples = samples - samples.min()
                if samples.max() > 0:
                    samples = samples / samples.max() * 255
                samples = samples.astype(np.uint8)

                # Reshape to 2D for image hashing
                # Create spectrogram-like representation
                # Use fixed size for consistent hashing
                target_size = 2048
                if len(samples) > target_size:
                    # Downsample
                    indices = np.linspace(0, len(samples) - 1, target_size, dtype=int)
                    samples = samples[indices]
                elif len(samples) < target_size:
                    # Pad with zeros
                    samples = np.pad(
                        samples, (0, target_size - len(samples)), mode="constant"
                    )

                # Reshape to square-ish image for perceptual hashing
                img_array = samples[: 64 * 32].reshape(64, 32)
                img = Image.fromarray(img_array, mode="L")

                # Use average hash (fast and reasonably accurate)
                return str(imagehash.average_hash(img, hash_size=16))
            else:
                return "0" * 64  # Empty audio

        except Exception as e:
            raise ValueError(f"Failed to hash audio file {file_path}: {e}") from e

    @staticmethod
    def get_audio_metadata(file_path: Path) -> Dict[str, Optional[Union[float, int]]]:
        """Extract basic audio metadata for pre-filtering."""
        try:
            audio = AudioSegment.from_file(str(file_path))
            return {
                "duration": len(audio) / 1000.0,  # Duration in seconds
                "channels": audio.channels,
                "sample_rate": audio.frame_rate,
                "bitrate": getattr(audio, "bitrate", None),
            }
        except Exception:
            return {
                "duration": None,
                "channels": None,
                "sample_rate": None,
                "bitrate": None,
            }
