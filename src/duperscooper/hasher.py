"""Audio hashing utilities for duplicate detection."""

import hashlib
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from .cache import (
    CacheBackend,
    JSONCacheBackend,
    SQLiteCacheBackend,
    migrate_json_to_sqlite,
)


class AudioHasher:
    """Handles audio file hashing for duplicate detection."""

    SUPPORTED_FORMATS = {".mp3", ".flac", ".wav", ".ogg", ".m4a", ".aac", ".wma"}

    def __init__(
        self,
        cache_path: Optional[Path] = None,
        use_cache: bool = True,
        update_cache: bool = False,
        cache_backend: str = "sqlite",
    ):
        """
        Initialize audio hasher with optional cache.

        Args:
            cache_path: Path to cache file/database
                (default: $XDG_CONFIG_HOME/duperscooper/hashes.{db,json})
            use_cache: Whether to use cache (default: True)
            update_cache: Force regeneration of cached hashes (default: False)
            cache_backend: Cache backend type: 'sqlite' or 'json' (default: 'sqlite')
        """
        if cache_path is None:
            xdg_config = Path.home() / ".config"
            cache_dir = xdg_config / "duperscooper"
            cache_dir.mkdir(parents=True, exist_ok=True)

            # Determine cache file based on backend
            if cache_backend == "sqlite":
                cache_path = cache_dir / "hashes.db"
            else:
                cache_path = cache_dir / "hashes.json"

        self.cache_path = cache_path
        self.use_cache = use_cache
        self.update_cache = update_cache
        self.cache_backend_type = cache_backend
        self.cache_updates = 0

        # Initialize cache backend
        if use_cache:
            self._cache: Optional[CacheBackend] = self._init_cache_backend(
                cache_path, cache_backend
            )
        else:
            self._cache = None

    def _init_cache_backend(self, cache_path: Path, backend_type: str) -> CacheBackend:
        """
        Initialize cache backend with optional migration.

        Args:
            cache_path: Path to cache file/database
            backend_type: 'sqlite' or 'json'

        Returns:
            Initialized cache backend
        """
        if backend_type == "sqlite":
            # Check for existing JSON cache to migrate
            json_path = cache_path.parent / "hashes.json"
            if json_path.exists() and not cache_path.exists():
                migrated = migrate_json_to_sqlite(json_path, cache_path)
                if migrated > 0:
                    # Rename JSON file as backup
                    json_path.rename(json_path.with_suffix(".json.bak"))

            return SQLiteCacheBackend(cache_path)
        else:
            return JSONCacheBackend(cache_path)

    def get_cache_stats(self) -> Dict[str, int]:
        """
        Get cache statistics.

        Returns:
            Dictionary with hits, misses, and size
        """
        if self._cache:
            return self._cache.get_stats()
        return {"hits": 0, "misses": 0, "size": 0}

    def close_cache(self) -> None:
        """Close cache backend (saves for JSON, closes connections for SQLite)."""
        if self._cache:
            self._cache.close()

    def clear_cache(self) -> bool:
        """
        Clear all cache entries.

        Returns:
            True if cache was cleared successfully
        """
        if self._cache:
            return self._cache.clear()
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
    def _call_fpcalc(
        file_path: Path, raw: bool = False, debug: bool = False
    ) -> Tuple[int, str]:
        """
        Call fpcalc binary directly to generate Chromaprint fingerprint.

        Python 3.13 removed modules that audioread depends on, so we bypass
        it and call fpcalc directly.

        Args:
            file_path: Path to audio file
            raw: If True, get raw (uncompressed) fingerprint for fuzzy matching
            debug: If True, print detailed timing information

        Returns:
            Tuple of (duration_seconds, fingerprint_string)
        """
        try:
            import time

            cmd = ["fpcalc"]
            if raw:
                cmd.append("-raw")
            cmd.append(str(file_path))

            t_start = time.time()
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )
            t_elapsed = time.time() - t_start

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

            if debug and t_elapsed > 0.1:
                file_size = file_path.stat().st_size / (1024 * 1024)
                duration_min = duration / 60.0
                processing_ratio = t_elapsed / duration if duration > 0 else 0
                print(
                    f"  DEBUG: fpcalc took {t_elapsed:.3f}s "
                    f"({file_size:.2f}MB file, {duration_min:.2f}min audio, "
                    f"processing_ratio={processing_ratio:.3f}x realtime)"
                )
                print(f"  File: {file_path}")

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

    def compute_raw_fingerprint(
        self, file_path: Path, debug: bool = False
    ) -> List[int]:
        """
        Compute raw Chromaprint fingerprint for fuzzy matching.

        Returns list of integers representing the raw fingerprint,
        suitable for similarity comparison using Hamming distance.

        Args:
            file_path: Path to audio file
            debug: If True, print detailed timing information

        Returns:
            List of integers representing raw fingerprint

        Raises:
            ValueError: If fingerprinting fails
        """
        try:
            duration, raw_fp_str = AudioHasher._call_fpcalc(
                file_path, raw=True, debug=debug
            )
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

        # Check cache using file path + mtime (fast!)
        # Get file mtime
        file_mtime = int(file_path.stat().st_mtime)

        # Check cache (unless in update_cache mode)
        if self._cache and not self.update_cache:
            # Try new fast path+mtime based cache first
            if hasattr(self._cache, "get_by_path"):
                cached_result = self._cache.get_by_path(str(file_path), file_mtime)
                if cached_result:
                    # New format: tuple of (fingerprint, metadata_json)
                    cached_value = cached_result[0]  # fingerprint string
                    # metadata is cached_result[1] but not used here
            else:
                # Fallback to old hash-based cache for backwards compatibility
                file_hash = AudioHasher.compute_file_hash(file_path)
                cached_value = self._cache.get(file_hash)
                cached_result = (cached_value, None) if cached_value else None

            if cached_result and cached_result[0]:
                # Cache stores comma-separated string, parse it
                print(f"DEBUG: Cache hit for {file_path.name}")
                return AudioHasher.parse_raw_fingerprint(cached_result[0])

        # Cache miss or update_cache mode - compute fingerprint
        if self.update_cache:
            self.cache_updates += 1
            print(f"DEBUG: Cache update mode - recomputing {file_path.name}")
        else:
            print(f"DEBUG: Cache miss - computing {file_path.name}")

        try:
            import time

            t_start = time.time()

            # Get raw fingerprint for fuzzy matching
            t_fp_start = time.time()
            raw_fingerprint = self.compute_raw_fingerprint(file_path, debug=True)
            t_fp_elapsed = time.time() - t_fp_start

            # Store in cache as comma-separated string, along with metadata
            if self._cache:
                t_cache_start = time.time()
                fingerprint_str = ",".join(str(x) for x in raw_fingerprint)

                # Extract metadata at the same time to avoid double processing
                metadata = None
                t_meta_elapsed = 0.0
                if hasattr(self._cache, "set_by_path"):
                    try:
                        import json

                        t_meta_start = time.time()
                        metadata_dict = self.get_audio_metadata_fast(
                            file_path, debug=True
                        )
                        t_meta_elapsed = time.time() - t_meta_start
                        metadata = json.dumps(metadata_dict)
                    except Exception:
                        pass  # Ignore metadata extraction errors

                # Use new fast path+mtime based cache if available
                if hasattr(self._cache, "set_by_path"):
                    self._cache.set_by_path(
                        str(file_path), file_mtime, fingerprint_str, metadata
                    )
                else:
                    # Fallback to old hash-based cache
                    file_hash = AudioHasher.compute_file_hash(file_path)
                    self._cache.set(file_hash, fingerprint_str)

                t_cache_elapsed = time.time() - t_cache_start

            t_total = time.time() - t_start

            # Log detailed timing if processing took >0.1s
            if t_total > 0.1:
                file_size = file_path.stat().st_size / (1024 * 1024)  # MB
                # Get codec and format info if metadata was extracted
                codec = "unknown"
                fmt_info = ""
                if metadata:
                    try:
                        import json

                        meta = json.loads(metadata)
                        codec = meta.get("codec", "unknown") or "unknown"
                        sr = meta.get("sample_rate")
                        bd = meta.get("bit_depth")
                        br = meta.get("bitrate")
                        if sr:
                            fmt_info += f" {sr}Hz"
                        if bd:
                            fmt_info += f" {bd}bit"
                        if br:
                            fmt_info += f" {br//1000}kbps"
                    except Exception:
                        pass

                print(
                    f"DEBUG: Hash took {t_total:.3f}s "
                    f"(fp={t_fp_elapsed:.3f}s, meta={t_meta_elapsed:.3f}s, "
                    f"cache={t_cache_elapsed:.3f}s) "
                    f"[{file_size:.2f}MB {codec}{fmt_info}]"
                )
                print(f"  File: {file_path}")

            return raw_fingerprint

        except Exception as e:
            raise ValueError(f"Failed to hash audio file {file_path}: {e}") from e

    def get_audio_metadata_cached(
        self, file_path: Path
    ) -> Dict[str, Optional[Union[str, int, float]]]:
        """
        Get audio metadata with caching support.

        Tries cache first, then extracts metadata using mutagen.
        Note: Metadata is usually cached by compute_audio_hash, so this
        should be fast in most cases.

        Returns:
            Dictionary with codec, sample_rate, bit_depth, bitrate, channels
        """
        import json

        file_mtime = int(file_path.stat().st_mtime)

        # Try to get from cache
        if self._cache and hasattr(self._cache, "get_by_path"):
            cached_result = self._cache.get_by_path(str(file_path), file_mtime)
            if cached_result and cached_result[1]:  # Has cached metadata
                try:
                    metadata_dict: Dict[str, Optional[Union[str, int, float]]]
                    metadata_dict = json.loads(cached_result[1])
                    return metadata_dict
                except (json.JSONDecodeError, TypeError):
                    pass  # Fall through to extract

        # Cache miss - extract metadata directly
        # (This should be rare since compute_audio_hash caches it)
        return self.get_audio_metadata_fast(file_path)

    @staticmethod
    def get_audio_metadata_fast(
        file_path: Path, debug: bool = False
    ) -> Dict[str, Optional[Union[str, int, float]]]:
        """
        Extract audio metadata using mutagen (fast, no subprocess).

        Args:
            file_path: Path to audio file
            debug: If True, print detailed timing information

        Returns:
            Dictionary with codec, sample_rate, bit_depth, bitrate, channels
        """
        try:
            import time

            t_start = time.time()
            from mutagen import File as MutagenFile

            t_parse_start = time.time()
            audio = MutagenFile(str(file_path))
            t_parse = time.time() - t_parse_start

            if audio is None or audio.info is None:
                return {
                    "codec": None,
                    "sample_rate": None,
                    "bit_depth": None,
                    "bitrate": None,
                    "channels": None,
                }

            # Extract codec from MIME type
            codec = None
            if hasattr(audio, "mime") and audio.mime:
                # mime is like ['audio/flac'] or ['audio/mpeg']
                codec = audio.mime[0].split("/")[-1].upper()
                # Normalize codec names
                if codec == "MPEG":
                    codec = "MP3"
                elif codec == "X-FLAC":
                    codec = "FLAC"

            # Get audio info
            info = audio.info
            sample_rate = getattr(info, "sample_rate", None)
            bit_depth = getattr(info, "bits_per_sample", None)
            bitrate = getattr(info, "bitrate", None)
            channels = getattr(info, "channels", None)

            t_total = time.time() - t_start

            if debug and t_total > 0.05:
                file_size = file_path.stat().st_size / (1024 * 1024)
                print(
                    f"  DEBUG: mutagen parse took {t_parse:.3f}s, "
                    f"total={t_total:.3f}s for {file_path.name} "
                    f"({file_size:.2f}MB {codec})"
                )

            return {
                "codec": codec,
                "sample_rate": int(sample_rate) if sample_rate else None,
                "bit_depth": int(bit_depth) if bit_depth else None,
                "bitrate": int(bitrate) if bitrate else None,
                "channels": int(channels) if channels else None,
            }

        except Exception:
            # Fall back to empty metadata on any error
            return {
                "codec": None,
                "sample_rate": None,
                "bit_depth": None,
                "bitrate": None,
                "channels": None,
            }

    @staticmethod
    def get_audio_metadata(
        file_path: Path,
    ) -> Dict[str, Optional[Union[str, int, float]]]:
        """
        Extract audio metadata using ffprobe (legacy fallback).

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
    def get_audio_tags(file_path: Path) -> Dict[str, Optional[str]]:
        """
        Extract album and artist tags from audio file using ffprobe.

        Returns:
            Dictionary with 'album' and 'artist' keys (None if not found)
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
                    str(file_path),
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )

            import json as json_module

            data = json_module.loads(result.stdout)
            tags = data.get("format", {}).get("tags", {})

            # Handle both lowercase and uppercase tag names
            album = tags.get("album") or tags.get("ALBUM")
            artist = tags.get("artist") or tags.get("ARTIST")

            return {"album": album, "artist": artist}
        except Exception:
            return {"album": None, "artist": None}

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
