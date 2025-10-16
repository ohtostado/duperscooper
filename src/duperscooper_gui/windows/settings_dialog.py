"""Settings dialog for duperscooper GUI."""

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..config.settings import get_config_file, load_config


class ColorButton(QPushButton):
    """Button that shows and allows editing a color."""

    def __init__(self, color: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.color = color
        self.setFixedSize(60, 30)
        self.update_color(color)
        self.clicked.connect(self.choose_color)

    def update_color(self, color: str) -> None:
        """Update button background color."""
        self.color = color
        self.setStyleSheet(f"background-color: {color};")

    def choose_color(self) -> None:
        """Open color picker dialog."""
        from PySide6.QtGui import QColor

        current_color = QColor(self.color)
        color = QColorDialog.getColor(current_color, self, "Choose Color")
        if color.isValid():
            self.update_color(color.name())


class SettingsDialog(QDialog):
    """Settings dialog for editing user configuration."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.resize(500, 600)

        # Load current config
        self.config = load_config()

        # Setup UI
        self.setup_ui()

    def setup_ui(self) -> None:
        """Setup the settings UI."""
        layout = QVBoxLayout()

        # Colors section
        colors_group = self.create_colors_group()
        layout.addWidget(colors_group)

        # Scan defaults section
        scan_group = self.create_scan_group()
        layout.addWidget(scan_group)

        # UI preferences section
        ui_group = self.create_ui_group()
        layout.addWidget(ui_group)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.save_settings)
        button_layout.addWidget(save_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)

        self.setLayout(layout)

    def create_colors_group(self) -> QGroupBox:
        """Create color settings group."""
        group = QGroupBox("Colors")
        layout = QFormLayout()

        # Group header colors
        self.group_header_bg = ColorButton(
            self.config["colors"]["group_header"]["background"]
        )
        layout.addRow("Group Header Background:", self.group_header_bg)

        self.group_header_fg = ColorButton(
            self.config["colors"]["group_header"]["foreground"]
        )
        layout.addRow("Group Header Foreground:", self.group_header_fg)

        # Best quality color
        self.best_quality_color = ColorButton(
            self.config["colors"]["best_quality"]["color"]
        )
        layout.addRow("Best Quality Marker:", self.best_quality_color)

        # Similarity colors
        self.sim_very_high = ColorButton(
            self.config["colors"]["similarity"]["very_high"]
        )
        layout.addRow("Similarity Very High (≥99%):", self.sim_very_high)

        self.sim_high = ColorButton(self.config["colors"]["similarity"]["high"])
        layout.addRow("Similarity High (≥97%):", self.sim_high)

        self.sim_medium = ColorButton(self.config["colors"]["similarity"]["medium"])
        layout.addRow("Similarity Medium (≥95%):", self.sim_medium)

        self.sim_low = ColorButton(self.config["colors"]["similarity"]["low"])
        layout.addRow("Similarity Low (<95%):", self.sim_low)

        group.setLayout(layout)
        return group

    def create_scan_group(self) -> QGroupBox:
        """Create scan settings group."""
        group = QGroupBox("Scan Defaults")
        layout = QFormLayout()

        # Similarity threshold
        self.similarity_threshold = QDoubleSpinBox()
        self.similarity_threshold.setRange(80.0, 100.0)
        self.similarity_threshold.setSingleStep(0.1)
        self.similarity_threshold.setValue(self.config["scan"]["similarity_threshold"])
        self.similarity_threshold.setSuffix("%")
        layout.addRow("Similarity Threshold:", self.similarity_threshold)

        # Workers
        self.workers = QSpinBox()
        self.workers.setRange(1, 32)
        self.workers.setValue(self.config["scan"]["workers"])
        layout.addRow("Worker Threads:", self.workers)

        group.setLayout(layout)
        return group

    def create_ui_group(self) -> QGroupBox:
        """Create UI settings group."""
        group = QGroupBox("UI Preferences")
        layout = QFormLayout()

        # Window size
        self.window_width = QSpinBox()
        self.window_width.setRange(800, 3840)
        self.window_width.setSingleStep(100)
        self.window_width.setValue(self.config["ui"]["window_width"])
        layout.addRow("Default Window Width:", self.window_width)

        self.window_height = QSpinBox()
        self.window_height.setRange(600, 2160)
        self.window_height.setSingleStep(100)
        self.window_height.setValue(self.config["ui"]["window_height"])
        layout.addRow("Default Window Height:", self.window_height)

        # Auto expand groups
        self.auto_expand = QCheckBox()
        self.auto_expand.setChecked(self.config["ui"]["auto_expand_groups"])
        layout.addRow("Auto-expand Result Groups:", self.auto_expand)

        # Config file path (read-only)
        config_path = QLineEdit(str(get_config_file()))
        config_path.setReadOnly(True)
        layout.addRow("Configuration File:", config_path)

        group.setLayout(layout)
        return group

    def save_settings(self) -> None:
        """Save settings to config file."""
        try:
            # Build updated config
            updated_config = {
                "colors": {
                    "group_header": {
                        "background": self.group_header_bg.color,
                        "foreground": self.group_header_fg.color,
                    },
                    "best_quality": {"color": self.best_quality_color.color},
                    "similarity": {
                        "very_high": self.sim_very_high.color,
                        "high": self.sim_high.color,
                        "medium": self.sim_medium.color,
                        "low": self.sim_low.color,
                        "threshold_very_high": self.config["colors"]["similarity"][
                            "threshold_very_high"
                        ],
                        "threshold_high": self.config["colors"]["similarity"][
                            "threshold_high"
                        ],
                        "threshold_medium": self.config["colors"]["similarity"][
                            "threshold_medium"
                        ],
                    },
                },
                "scan": {
                    "default_mode": self.config["scan"]["default_mode"],
                    "algorithm": self.config["scan"]["algorithm"],
                    "similarity_threshold": self.similarity_threshold.value(),
                    "workers": self.workers.value(),
                    "default_paths": self.config["scan"].get("default_paths", []),
                },
                "ui": {
                    "window_width": self.window_width.value(),
                    "window_height": self.window_height.value(),
                    "auto_expand_groups": self.auto_expand.isChecked(),
                },
            }

            # Write to TOML file
            config_file = get_config_file()
            self.write_toml(config_file, updated_config)

            QMessageBox.information(
                self,
                "Settings Saved",
                "Settings have been saved successfully.\n\n"
                "Some changes may require restarting the application to take effect.",
            )
            self.accept()

        except Exception as e:
            QMessageBox.critical(
                self, "Error Saving Settings", f"Failed to save settings:\n{e}"
            )

    def write_toml(self, path: Path, config: dict) -> None:
        """Write config dictionary to TOML file."""
        import tomli_w

        with open(path, "wb") as f:
            tomli_w.dump(config, f)
