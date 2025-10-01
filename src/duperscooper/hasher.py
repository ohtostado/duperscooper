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
    def get_audio_metadata(
        file_path: Path,
    ) -> Dict[str, Optional[Union[str, int, float]]]:
        """
        Extract audio metadata using ffprobe.

        Returns:
            Dictionary with codec, sample_rate, bit_depth, bitrate, channels
        """
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "quiet",
                    "-print_format",
                    "json",
                    "-show_format",
                    "-show_streams",
                    str(file_path),
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )

            import json as json_module

            data = json_module.loads(result.stdout)

            # Get audio stream (first audio stream found)
            audio_stream = None
            for stream in data.get("streams", []):
                if stream.get("codec_type") == "audio":
                    audio_stream = stream
                    break

            if not audio_stream:
                return {
                    "codec": None,
                    "sample_rate": None,
                    "bit_depth": None,
                    "bitrate": None,
                    "channels": None,
                }

            # Extract metadata
            codec = audio_stream.get("codec_name", "").upper()
            sample_rate = audio_stream.get("sample_rate")
            if sample_rate:
                sample_rate = int(sample_rate)

            # Bit depth (for lossless formats)
            bit_depth = audio_stream.get("bits_per_raw_sample")
            if bit_depth:
                bit_depth = int(bit_depth)

            # Bitrate (prefer stream bitrate, fall back to format bitrate)
            bitrate = audio_stream.get("bit_rate")
            if not bitrate:
                bitrate = data.get("format", {}).get("bit_rate")
            if bitrate:
                bitrate = int(bitrate)

            channels = audio_stream.get("channels")
            if channels:
                channels = int(channels)

            return {
                "codec": codec,
                "sample_rate": sample_rate,
                "bit_depth": bit_depth,
                "bitrate": bitrate,
                "channels": channels,
            }

        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, Exception):
            return {
                "codec": None,
                "sample_rate": None,
                "bit_depth": None,
                "bitrate": None,
                "channels": None,
            }

    @staticmethod
    def calculate_quality_score(
        metadata: Dict[str, Optional[Union[str, int, float]]]
    ) -> float:
        """
        Calculate quality score for audio file.

        Lossless formats (FLAC, WAV, etc.) always score higher than lossy.
        Within each category, higher sample rates and bit depths score better.

        Returns:
            Quality score (higher = better quality)
        """
        codec_val = metadata.get("codec")
        codec = codec_val.upper() if isinstance(codec_val, str) else ""
        sample_rate_val = metadata.get("sample_rate", 0)
        sample_rate = (
            int(sample_rate_val)
            if isinstance(sample_rate_val, (int, float)) and sample_rate_val
            else 0
        )
        bit_depth_val = metadata.get("bit_depth", 0)
        bit_depth = (
            int(bit_depth_val)
            if isinstance(bit_depth_val, (int, float)) and bit_depth_val
            else 0
        )
        bitrate_val = metadata.get("bitrate", 0)
        bitrate = (
            int(bitrate_val)
            if isinstance(bitrate_val, (int, float)) and bitrate_val
            else 0
        )

        # Lossless formats get base score of 10000
        lossless_codecs = {"FLAC", "WAV", "ALAC", "APE", "WV", "TTA"}

        if codec in lossless_codecs:
            # Score = 10000 + (bit_depth * 100) + (sample_rate / 1000)
            # Example: 24bit 96kHz = 10000 + 2400 + 96 = 12496
            score = 10000.0
            if bit_depth:
                score += bit_depth * 100
            if sample_rate:
                score += sample_rate / 1000
            return score
        else:
            # Lossy formats: score = bitrate in kbps
            # Convert from bps to kbps
            if bitrate:
                return bitrate / 1000.0
            return 0.0

    @staticmethod
    def format_audio_info(metadata: Dict[str, Optional[Union[str, int, float]]]) -> str:
        """
        Format audio metadata into human-readable string.

        Returns strings like:
        - "FLAC 44.1kHz 16bit"
        - "MP3 CBR 320kbps"
        - "MP3 VBR 245kbps"
        """
        codec_val = metadata.get("codec", "Unknown")
        codec = str(codec_val) if codec_val else "Unknown"
        sample_rate_val = metadata.get("sample_rate")
        bit_depth_val = metadata.get("bit_depth")
        bitrate_val = metadata.get("bitrate")

        lossless_codecs = {"FLAC", "WAV", "ALAC", "APE", "WV", "TTA"}

        if codec.upper() in lossless_codecs:
            # Lossless format
            parts = [codec]
            if isinstance(sample_rate_val, (int, float)) and sample_rate_val:
                parts.append(f"{sample_rate_val / 1000:.1f}kHz")
            if isinstance(bit_depth_val, (int, float)) and bit_depth_val:
                parts.append(f"{int(bit_depth_val)}bit")
            return " ".join(parts)
        else:
            # Lossy format
            parts = [codec]
            # Determine CBR vs VBR (heuristic: if bitrate ends in 000, likely CBR)
            if isinstance(bitrate_val, (int, float)) and bitrate_val:
                kbps = int(bitrate_val / 1000)
                # Common CBR bitrates: 64, 96, 128, 160, 192, 256, 320
                common_cbr = {64, 96, 128, 160, 192, 256, 320}
                if kbps in common_cbr:
                    parts.append(f"CBR {kbps}kbps")
                else:
                    parts.append(f"VBR {kbps}kbps")
            return " ".join(parts)
