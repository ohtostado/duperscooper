"""Tests for scan result loading and rule application."""

import json
import tempfile
from pathlib import Path

import pytest

from duperscooper.apply import ApplyEngine, ScanResultLoader
from duperscooper.rules import RuleEngine


class TestScanResultLoader:
    """Test loading scan results from JSON and CSV."""

    def test_load_track_mode_json(self) -> None:
        """Test loading track mode JSON scan results."""
        json_data = [
            {
                "hash": "abc123",
                "files": [
                    {
                        "path": "/music/song.flac",
                        "size": 30000000,
                        "audio_info": "FLAC 44.1kHz 16bit",
                        "quality_score": 11644.1,
                        "similarity_to_best": 100.0,
                        "is_best": True,
                    },
                    {
                        "path": "/music/song.mp3",
                        "size": 5000000,
                        "audio_info": "MP3 CBR 320kbps",
                        "quality_score": 320.0,
                        "similarity_to_best": 99.9,
                        "is_best": False,
                    },
                ],
            }
        ]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(json_data, f)
            json_path = Path(f.name)

        try:
            mode, groups = ScanResultLoader.load_json(json_path)

            assert mode == "track"
            assert len(groups) == 1
            assert groups[0]["hash"] == "abc123"
            assert len(groups[0]["files"]) == 2

        finally:
            json_path.unlink()

    def test_load_album_mode_json(self) -> None:
        """Test loading album mode JSON scan results."""
        json_data = [
            {
                "matched_album": "Test Album",
                "matched_artist": "Test Artist",
                "albums": [
                    {
                        "path": "/music/album-flac",
                        "track_count": 10,
                        "total_size": 300000000,
                        "quality_info": "FLAC 44.1kHz 16bit (avg)",
                        "quality_score": 11644.1,
                        "match_percentage": 100.0,
                        "match_method": "MusicBrainz Album ID",
                        "is_best": True,
                        "musicbrainz_albumid": "abc-123",
                        "album_name": "Test Album",
                        "artist_name": "Test Artist",
                        "has_mixed_mb_ids": False,
                        "is_partial_match": False,
                        "overlap_percentage": 100.0,
                    }
                ],
            }
        ]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(json_data, f)
            json_path = Path(f.name)

        try:
            mode, groups = ScanResultLoader.load_json(json_path)

            assert mode == "album"
            assert len(groups) == 1
            assert groups[0]["matched_album"] == "Test Album"
            assert len(groups[0]["albums"]) == 1

        finally:
            json_path.unlink()

    def test_load_invalid_json_format(self) -> None:
        """Test loading JSON with invalid format raises error."""
        json_data = {"invalid": "format"}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(json_data, f)
            json_path = Path(f.name)

        try:
            with pytest.raises(ValueError, match="must be a non-empty list"):
                ScanResultLoader.load_json(json_path)

        finally:
            json_path.unlink()

    def test_extract_fields_track_mode(self) -> None:
        """Test field extraction for track mode."""
        item = {
            "path": "/music/song.mp3",
            "size": 5000000,
            "audio_info": "MP3 CBR 320kbps",
            "quality_score": 320.0,
            "is_best": False,
        }

        extracted = ScanResultLoader.extract_fields(item, "track")

        assert extracted["format"] == "MP3"
        assert extracted["codec"] == "MP3"
        assert extracted["bitrate"] == 320
        assert extracted["is_lossless"] is False
        assert extracted["file_size"] == 5000000

    def test_extract_fields_lossless_format(self) -> None:
        """Test field extraction for lossless format."""
        item = {
            "path": "/music/song.flac",
            "size": 30000000,
            "audio_info": "FLAC 44.1kHz 16bit",
            "quality_score": 11644.1,
            "is_best": True,
        }

        extracted = ScanResultLoader.extract_fields(item, "track")

        assert extracted["format"] == "FLAC"
        assert extracted["is_lossless"] is True
        assert extracted["sample_rate"] == 44100
        assert extracted["bit_depth"] == 16
        assert extracted["bitrate"] == 0  # Lossless has no bitrate

    def test_extract_fields_album_mode(self) -> None:
        """Test field extraction for album mode."""
        item = {
            "path": "/music/album",
            "total_size": 300000000,
            "quality_info": "MP3 CBR 320kbps (avg)",
            "quality_score": 320.0,
            "is_best": False,
        }

        extracted = ScanResultLoader.extract_fields(item, "album")

        assert extracted["format"] == "MP3"
        assert extracted["is_lossless"] is False
        assert extracted["file_size"] == 300000000


class TestApplyEngine:
    """Test rule application and deletion execution."""

    def test_apply_rules_track_mode(self) -> None:
        """Test applying rules to track mode scan results."""
        groups = [
            {
                "hash": "abc123",
                "files": [
                    {
                        "path": "/music/song.flac",
                        "size": 30000000,
                        "audio_info": "FLAC 44.1kHz 16bit",
                        "quality_score": 11644.1,
                        "similarity_to_best": 100.0,
                        "is_best": True,
                    },
                    {
                        "path": "/music/song.mp3",
                        "size": 5000000,
                        "audio_info": "MP3 CBR 320kbps",
                        "quality_score": 320.0,
                        "similarity_to_best": 99.9,
                        "is_best": False,
                    },
                ],
            }
        ]

        engine = RuleEngine.get_strategy("eliminate-duplicates")
        annotated = ApplyEngine.apply_rules("track", groups, engine)

        assert len(annotated) == 1
        assert len(annotated[0]["files"]) == 2

        # Check actions
        files = annotated[0]["files"]
        assert files[0]["action"] == "keep"  # FLAC is best
        assert files[1]["action"] == "delete"  # MP3 is not best

    def test_apply_rules_album_mode(self) -> None:
        """Test applying rules to album mode scan results."""
        groups = [
            {
                "matched_album": "Test Album",
                "matched_artist": "Test Artist",
                "albums": [
                    {
                        "path": "/music/album-flac",
                        "total_size": 300000000,
                        "quality_info": "FLAC 44.1kHz 16bit (avg)",
                        "quality_score": 11644.1,
                        "is_best": True,
                    },
                    {
                        "path": "/music/album-mp3",
                        "total_size": 50000000,
                        "quality_info": "MP3 CBR 320kbps (avg)",
                        "quality_score": 320.0,
                        "is_best": False,
                    },
                ],
            }
        ]

        engine = RuleEngine.get_strategy("eliminate-duplicates")
        annotated = ApplyEngine.apply_rules("album", groups, engine)

        assert len(annotated) == 1
        assert len(annotated[0]["albums"]) == 2

        # Check actions
        albums = annotated[0]["albums"]
        assert albums[0]["action"] == "keep"  # FLAC is best
        assert albums[1]["action"] == "delete"  # MP3 is not best

    def test_apply_keep_lossless_strategy(self) -> None:
        """Test keep-lossless strategy."""
        groups = [
            {
                "hash": "abc123",
                "files": [
                    {
                        "path": "/music/song.flac",
                        "size": 30000000,
                        "audio_info": "FLAC 44.1kHz 16bit",
                        "quality_score": 11644.1,
                        "is_best": True,
                    },
                    {
                        "path": "/music/song.mp3",
                        "size": 5000000,
                        "audio_info": "MP3 CBR 320kbps",
                        "quality_score": 320.0,
                        "is_best": False,
                    },
                ],
            }
        ]

        engine = RuleEngine.get_strategy("keep-lossless")
        annotated = ApplyEngine.apply_rules("track", groups, engine)

        files = annotated[0]["files"]
        assert files[0]["action"] == "keep"  # FLAC is lossless
        assert files[1]["action"] == "delete"  # MP3 is lossy

    def test_apply_keep_format_strategy(self) -> None:
        """Test keep-format strategy."""
        groups = [
            {
                "hash": "abc123",
                "files": [
                    {
                        "path": "/music/song.flac",
                        "size": 30000000,
                        "audio_info": "FLAC 44.1kHz 16bit",
                        "quality_score": 11644.1,
                        "is_best": True,
                    },
                    {
                        "path": "/music/song.mp3",
                        "size": 5000000,
                        "audio_info": "MP3 CBR 320kbps",
                        "quality_score": 320.0,
                        "is_best": False,
                    },
                ],
            }
        ]

        engine = RuleEngine.get_strategy("keep-format", format_param="FLAC")
        annotated = ApplyEngine.apply_rules("track", groups, engine)

        files = annotated[0]["files"]
        assert files[0]["action"] == "keep"  # FLAC matches format
        assert files[1]["action"] == "delete"  # MP3 doesn't match

    def test_generate_report_track_mode(self) -> None:
        """Test report generation for track mode."""
        annotated = [
            {
                "hash": "abc123",
                "files": [
                    {
                        "path": "/music/song.flac",
                        "size": 30000000,
                        "audio_info": "FLAC 44.1kHz 16bit",
                        "is_best": True,
                        "action": "keep",
                    },
                    {
                        "path": "/music/song.mp3",
                        "size": 5000000,
                        "audio_info": "MP3 CBR 320kbps",
                        "is_best": False,
                        "action": "delete",
                    },
                ],
            }
        ]

        report = ApplyEngine.generate_report("track", annotated)

        assert "DELETION PLAN" in report
        assert "KEEP" in report
        assert "DELETE" in report
        assert "song.flac" in report
        assert "song.mp3" in report
        assert "Items to keep:   1" in report
        assert "Items to delete: 1" in report

    def test_generate_report_album_mode(self) -> None:
        """Test report generation for album mode."""
        annotated = [
            {
                "matched_album": "Test Album",
                "albums": [
                    {
                        "path": "/music/album-flac",
                        "total_size": 300000000,
                        "quality_info": "FLAC 44.1kHz 16bit (avg)",
                        "is_best": True,
                        "action": "keep",
                    },
                    {
                        "path": "/music/album-mp3",
                        "total_size": 50000000,
                        "quality_info": "MP3 CBR 320kbps (avg)",
                        "is_best": False,
                        "action": "delete",
                    },
                ],
            }
        ]

        report = ApplyEngine.generate_report("album", annotated)

        assert "DELETION PLAN" in report
        assert "album-flac" in report
        assert "album-mp3" in report
        assert "Items to keep:   1" in report
        assert "Items to delete: 1" in report

    def test_format_size(self) -> None:
        """Test human-readable size formatting."""
        assert "5.0 MB" in ApplyEngine._format_size(5 * 1024 * 1024)
        assert "1.0 GB" in ApplyEngine._format_size(1024 * 1024 * 1024)
        assert "500.0 B" in ApplyEngine._format_size(500)
