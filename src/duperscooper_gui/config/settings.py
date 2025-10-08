"""Settings management for duperscooper GUI.

Handles loading, saving, and accessing user configuration.
Configuration is stored in a platform-specific location:
- Linux/macOS: ~/.config/duperscooper/duperscooper-gui-options.toml
- Windows: %APPDATA%\\duperscooper\\duperscooper-gui-options.toml
"""

import shutil
from pathlib import Path
from typing import Any, Dict

import tomllib
from PySide6.QtGui import QColor


def get_config_dir() -> Path:
    """Get platform-specific configuration directory."""
    import os
    import platform

    system = platform.system()

    if system == "Windows":
        # Windows: %APPDATA%\duperscooper
        appdata = os.getenv("APPDATA")
        if not appdata:
            raise RuntimeError("APPDATA environment variable not set")
        return Path(appdata) / "duperscooper"
    else:
        # Linux/macOS: ~/.config/duperscooper
        home = Path.home()
        return home / ".config" / "duperscooper"


def get_config_file() -> Path:
    """Get path to user configuration file."""
    return get_config_dir() / "duperscooper-gui-options.toml"


def ensure_config_exists() -> Path:
    """
    Ensure user configuration file exists.

    If it doesn't exist, copy the default configuration from the package.

    Returns:
        Path to the user configuration file
    """
    config_file = get_config_file()

    if not config_file.exists():
        # Create config directory if needed
        config_file.parent.mkdir(parents=True, exist_ok=True)

        # Copy default config from package templates
        default_config = Path(__file__).parent / "templates" / "default_config.toml"
        shutil.copy(default_config, config_file)

    return config_file


def load_config() -> Dict[str, Any]:
    """
    Load user configuration from TOML file.

    Returns:
        Configuration dictionary
    """
    config_file = ensure_config_exists()

    with open(config_file, "rb") as f:
        return tomllib.load(f)


# Load config once at module level
_CONFIG = load_config()


class Settings:
    """Application settings loaded from user configuration file."""

    # Colors
    class Colors:
        """Color settings for the results viewer."""

        # Group header colors
        GROUP_HEADER_BACKGROUND = QColor(
            _CONFIG["colors"]["group_header"]["background"]
        )
        GROUP_HEADER_FOREGROUND = QColor(
            _CONFIG["colors"]["group_header"]["foreground"]
        )

        # Best quality file/album color
        BEST_QUALITY_COLOR = QColor(_CONFIG["colors"]["best_quality"]["color"])

        # Similarity percentage colors
        SIMILARITY_VERY_HIGH = QColor(_CONFIG["colors"]["similarity"]["very_high"])
        SIMILARITY_HIGH = QColor(_CONFIG["colors"]["similarity"]["high"])
        SIMILARITY_MEDIUM = QColor(_CONFIG["colors"]["similarity"]["medium"])
        SIMILARITY_LOW = QColor(_CONFIG["colors"]["similarity"]["low"])

        # Similarity thresholds (percentages)
        THRESHOLD_VERY_HIGH = _CONFIG["colors"]["similarity"]["threshold_very_high"]
        THRESHOLD_HIGH = _CONFIG["colors"]["similarity"]["threshold_high"]
        THRESHOLD_MEDIUM = _CONFIG["colors"]["similarity"]["threshold_medium"]

        @classmethod
        def get_similarity_color(cls, similarity: float) -> QColor:
            """
            Get color based on similarity percentage.

            Args:
                similarity: Similarity percentage (0-100)

            Returns:
                QColor for the given similarity level
            """
            if similarity >= cls.THRESHOLD_VERY_HIGH:
                return cls.SIMILARITY_VERY_HIGH
            elif similarity >= cls.THRESHOLD_HIGH:
                return cls.SIMILARITY_HIGH
            elif similarity >= cls.THRESHOLD_MEDIUM:
                return cls.SIMILARITY_MEDIUM
            else:
                return cls.SIMILARITY_LOW

    # Scan defaults
    DEFAULT_MODE = _CONFIG["scan"]["default_mode"]
    ALGORITHM = _CONFIG["scan"]["algorithm"]
    SIMILARITY_THRESHOLD = _CONFIG["scan"]["similarity_threshold"]
    WORKERS = _CONFIG["scan"]["workers"]
    DEFAULT_PATHS = _CONFIG["scan"].get("default_paths", [])

    # UI preferences
    WINDOW_WIDTH = _CONFIG["ui"]["window_width"]
    WINDOW_HEIGHT = _CONFIG["ui"]["window_height"]
    AUTO_EXPAND_GROUPS = _CONFIG["ui"]["auto_expand_groups"]

    @classmethod
    def get_config_file_path(cls) -> Path:
        """Get path to user configuration file for display/editing."""
        return get_config_file()
