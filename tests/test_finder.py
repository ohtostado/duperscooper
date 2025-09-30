"""Tests for duplicate finder functionality."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Mock pydub and acoustid to avoid Python 3.13 audioop issues in tests
sys.modules["pydub"] = MagicMock()
sys.modules["pydub.AudioSegment"] = MagicMock()
sys.modules["acoustid"] = MagicMock()

from duperscooper.finder import (  # noqa: E402
    DuplicateFinder,
    DuplicateManager,
)
from duperscooper.hasher import AudioHasher  # noqa: E402


class TestAudioHasher:
    """Tests for AudioHasher class."""

    def test_is_audio_file_valid_extensions(self) -> None:
        """Test audio file extension detection."""
        audio_extensions = [".mp3", ".flac", ".wav", ".ogg", ".m4a", ".aac", ".wma"]
        for ext in audio_extensions:
            assert AudioHasher.is_audio_file(Path(f"test{ext}"))
            assert AudioHasher.is_audio_file(Path(f"test{ext.upper()}"))

    def test_is_audio_file_invalid_extensions(self) -> None:
        """Test non-audio file detection."""
        assert not AudioHasher.is_audio_file(Path("test.txt"))
        assert not AudioHasher.is_audio_file(Path("test.jpg"))
        assert not AudioHasher.is_audio_file(Path("test.mp4"))


class TestDuplicateFinder:
    """Tests for DuplicateFinder class."""

    def test_init_defaults(self) -> None:
        """Test DuplicateFinder initialization with defaults."""
        finder = DuplicateFinder()
        assert finder.min_size == 0
        assert finder.algorithm == "perceptual"
        assert finder.verbose is False

    def test_init_custom_values(self) -> None:
        """Test DuplicateFinder initialization with custom values."""
        finder = DuplicateFinder(min_size=1024, algorithm="exact", verbose=True)
        assert finder.min_size == 1024
        assert finder.algorithm == "exact"
        assert finder.verbose is True


class TestDuplicateManager:
    """Tests for DuplicateManager class."""

    def test_format_file_size(self) -> None:
        """Test file size formatting."""
        assert DuplicateManager.format_file_size(500) == "500.0 B"
        assert DuplicateManager.format_file_size(1024) == "1.0 KB"
        assert DuplicateManager.format_file_size(1048576) == "1.0 MB"
        assert DuplicateManager.format_file_size(1073741824) == "1.0 GB"

    @patch("duperscooper.finder.Path.stat")
    def test_get_file_info(self, mock_stat: MagicMock) -> None:
        """Test file info retrieval."""
        mock_stat.return_value.st_size = 1024
        file_path = Path("/test/file.mp3")

        info = DuplicateManager.get_file_info(file_path)

        assert "path" in info
        assert "size" in info
        assert "size_bytes" in info
        assert info["size_bytes"] == 1024
