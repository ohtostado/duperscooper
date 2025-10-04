"""Main window for duperscooper GUI."""

import sys
from pathlib import Path
from typing import List

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QMainWindow,
    QMessageBox,
)
from PySide6.QtUiTools import QUiLoader


class ScanThread(QThread):
    """Background thread for running scans."""

    progress = Signal(str)  # Emits progress messages
    finished = Signal(str)  # Emits final JSON output
    error = Signal(str)  # Emits error messages

    def __init__(self, paths: List[str], options: dict):
        super().__init__()
        self.paths = paths
        self.options = options

    def run(self):
        """Run the scan in background thread."""
        try:
            from ...utils.backend_interface import run_scan

            # This will be implemented next
            result = run_scan(self.paths, self.options)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()

        # Load UI from .ui file
        ui_file = Path(__file__).parent.parent / "ui" / "main_window.ui"
        loader = QUiLoader()
        self.ui = loader.load(str(ui_file), self)

        # Set the loaded UI as the central widget
        self.setCentralWidget(self.ui.centralwidget)
        self.setMenuBar(self.ui.menubar)
        self.setStatusBar(self.ui.statusbar)

        # Resize to match UI
        self.resize(1000, 700)

        # Connect signals
        self._connect_signals()

        # Track scan paths
        self.scan_paths: List[str] = []

        # Status message
        self.ui.statusbar.showMessage("Ready")

    def _connect_signals(self):
        """Connect UI signals to slots."""
        # File menu
        self.ui.actionOpen.triggered.connect(self.open_results)
        self.ui.actionSave.triggered.connect(self.save_results)
        self.ui.actionExit.triggered.connect(self.close)
        self.ui.actionAbout.triggered.connect(self.show_about)

        # Scan tab
        self.ui.addPathButton.clicked.connect(self.add_path)
        self.ui.removePathButton.clicked.connect(self.remove_path)
        self.ui.startScanButton.clicked.connect(self.start_scan)

    def add_path(self):
        """Add a path to scan."""
        directory = QFileDialog.getExistingDirectory(
            self, "Select Directory to Scan"
        )
        if directory:
            self.scan_paths.append(directory)
            self.ui.pathsList.addItem(directory)
            self.ui.statusbar.showMessage(f"Added path: {directory}")

    def remove_path(self):
        """Remove selected path."""
        current_row = self.ui.pathsList.currentRow()
        if current_row >= 0:
            removed_path = self.scan_paths.pop(current_row)
            self.ui.pathsList.takeItem(current_row)
            self.ui.statusbar.showMessage(f"Removed path: {removed_path}")

    def start_scan(self):
        """Start scanning for duplicates."""
        if not self.scan_paths:
            QMessageBox.warning(
                self,
                "No Paths",
                "Please add at least one path to scan.",
            )
            return

        # Gather scan options
        options = {
            "album_mode": self.ui.modeCombo.currentIndex() == 1,
            "algorithm": (
                "exact" if self.ui.algorithmCombo.currentIndex() == 1 else "perceptual"
            ),
            "threshold": self.ui.thresholdSpin.value(),
            "workers": self.ui.workersSpin.value(),
        }

        # Update UI
        self.ui.startScanButton.setEnabled(False)
        self.ui.scanProgressBar.setValue(0)
        self.ui.scanLogText.clear()
        self.ui.statusbar.showMessage("Scanning...")

        # Start scan thread
        self.scan_thread = ScanThread(self.scan_paths, options)
        self.scan_thread.progress.connect(self.on_scan_progress)
        self.scan_thread.finished.connect(self.on_scan_finished)
        self.scan_thread.error.connect(self.on_scan_error)
        self.scan_thread.start()

    def on_scan_progress(self, message: str):
        """Handle scan progress updates."""
        self.ui.scanLogText.append(message)
        # Scroll to bottom
        self.ui.scanLogText.verticalScrollBar().setValue(
            self.ui.scanLogText.verticalScrollBar().maximum()
        )

    def on_scan_finished(self, json_output: str):
        """Handle scan completion."""
        self.ui.scanProgressBar.setValue(100)
        self.ui.startScanButton.setEnabled(True)
        self.ui.statusbar.showMessage("Scan complete!")

        self.ui.scanLogText.append("\n=== Scan Complete ===")
        self.ui.scanLogText.append(f"Found duplicates. JSON output ready.")

        # Switch to results tab
        self.ui.tabWidget.setCurrentIndex(1)

        # TODO: Load results into results viewer

    def on_scan_error(self, error_message: str):
        """Handle scan errors."""
        self.ui.scanProgressBar.setValue(0)
        self.ui.startScanButton.setEnabled(True)
        self.ui.statusbar.showMessage("Scan failed!")

        QMessageBox.critical(
            self,
            "Scan Error",
            f"An error occurred during scanning:\n\n{error_message}",
        )

    def open_results(self):
        """Open scan results from file."""
        filename, _ = QFileDialog.getOpenFileName(
            self, "Open Scan Results", "", "JSON Files (*.json);;CSV Files (*.csv)"
        )
        if filename:
            self.ui.statusbar.showMessage(f"Loaded: {filename}")
            # TODO: Load and display results

    def save_results(self):
        """Save scan results to file."""
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Scan Results", "", "JSON Files (*.json);;CSV Files (*.csv)"
        )
        if filename:
            self.ui.statusbar.showMessage(f"Saved: {filename}")
            # TODO: Save current results

    def show_about(self):
        """Show about dialog."""
        from .. import __version__

        QMessageBox.about(
            self,
            "About duperscooper",
            f"<h2>duperscooper</h2>"
            f"<p>Version {__version__}</p>"
            f"<p>Duplicate audio file finder with perceptual matching</p>"
            f"<p>Uses Chromaprint fingerprinting and quality detection</p>",
        )
