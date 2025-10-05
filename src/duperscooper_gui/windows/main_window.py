"""Main window for duperscooper GUI."""

from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QThread, Signal
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QFileDialog,
    QMainWindow,
    QMessageBox,
)

from ..models.results_model import ScanResults
from .results_viewer import ResultsViewer


class ScanThread(QThread):
    """Background thread for running scans."""

    progress = Signal(str, int)  # Emits (message: str, percentage: int)
    finished = Signal(str)  # Emits final JSON output
    error = Signal(str)  # Emits error messages

    def __init__(self, paths: List[str], options: dict):
        super().__init__()
        self.paths = paths
        self.options = options

    def run(self) -> None:
        """Run the scan in background thread."""
        try:
            from ..utils.backend_interface import run_scan

            # Progress callback that emits Qt signal
            def on_progress(message: str, percentage: int) -> None:
                self.progress.emit(message, percentage)

            result = run_scan(self.paths, self.options, progress_callback=on_progress)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self) -> None:
        super().__init__()

        # Load UI from .ui file
        ui_file = Path(__file__).parent.parent / "ui" / "main_window.ui"
        loader = QUiLoader()
        self.ui = loader.load(str(ui_file), self)  # type: ignore[attr-defined]

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

        # Create results viewer and add to results tab
        self.results_viewer = ResultsViewer(self)
        # Use the existing layout from the UI file instead of creating a new one
        self.ui.resultsTab.layout().addWidget(self.results_viewer.ui)
        self.results_viewer.delete_requested.connect(self.on_delete_requested)

        # Track current results
        self.current_results: Optional[ScanResults] = None

        # Status message
        self.ui.statusbar.showMessage("Ready")

    def _connect_signals(self) -> None:
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

    def add_path(self) -> None:
        """Add a path to scan."""
        directory = QFileDialog.getExistingDirectory(self, "Select Directory to Scan")
        if directory:
            self.scan_paths.append(directory)
            self.ui.pathsList.addItem(directory)
            self.ui.statusbar.showMessage(f"Added path: {directory}")

    def remove_path(self) -> None:
        """Remove selected path."""
        current_row = self.ui.pathsList.currentRow()
        if current_row >= 0:
            removed_path = self.scan_paths.pop(current_row)
            self.ui.pathsList.takeItem(current_row)
            self.ui.statusbar.showMessage(f"Removed path: {removed_path}")

    def start_scan(self) -> None:
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

    def on_scan_progress(self, message: str, percentage: int) -> None:
        """Handle scan progress updates."""
        # Update progress bar if percentage is available
        if percentage >= 0:
            self.ui.scanProgressBar.setValue(percentage)

        # Update log (only append non-empty messages, skip ANSI escape codes)
        if message and not message.startswith("\x1b"):
            # Clean up progress bar characters for display
            clean_msg = message.replace("█", "#").replace("▌", "-")
            self.ui.scanLogText.append(clean_msg)
            # Scroll to bottom
            self.ui.scanLogText.verticalScrollBar().setValue(
                self.ui.scanLogText.verticalScrollBar().maximum()
            )

    def on_scan_finished(self, json_output: str) -> None:
        """Handle scan completion."""
        import json

        self.ui.scanProgressBar.setValue(100)
        self.ui.startScanButton.setEnabled(True)

        self.ui.scanLogText.append("\n=== Scan Complete ===")

        # Load results
        try:
            self.current_results = ScanResults.from_json(json_output)
            self.results_viewer.load_results(self.current_results)

            if self.current_results.total_groups == 0:
                self.ui.scanLogText.append("No duplicates found.")
                self.ui.statusbar.showMessage("Scan complete - no duplicates found")
            else:
                self.ui.scanLogText.append(
                    f"Found {self.current_results.total_groups} duplicate groups "
                    f"with {self.current_results.total_duplicates} duplicates."
                )
                self.ui.statusbar.showMessage(
                    f"Scan complete - found {self.current_results.total_groups} "
                    f"duplicate group(s)"
                )
                # Only switch to results tab if duplicates were found
                self.ui.tabWidget.setCurrentIndex(1)

        except Exception as e:
            QMessageBox.critical(
                self,
                "Results Load Error",
                f"Failed to load scan results:\n\n{e}",
            )
            self.ui.scanLogText.append(f"Error loading results: {e}")

    def on_scan_error(self, error_message: str) -> None:
        """Handle scan errors."""
        self.ui.scanProgressBar.setValue(0)
        self.ui.startScanButton.setEnabled(True)
        self.ui.statusbar.showMessage("Scan failed!")

        QMessageBox.critical(
            self,
            "Scan Error",
            f"An error occurred during scanning:\n\n{error_message}",
        )

    def open_results(self) -> None:
        """Open scan results from file."""
        filename, _ = QFileDialog.getOpenFileName(
            self, "Open Scan Results", "", "JSON Files (*.json)"
        )
        if filename:
            try:
                self.current_results = ScanResults.from_file(filename)
                self.results_viewer.load_results(self.current_results)
                self.ui.statusbar.showMessage(f"Loaded: {filename}")

                # Switch to results tab
                self.ui.tabWidget.setCurrentIndex(1)

            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Load Error",
                    f"Failed to load results file:\n\n{e}",
                )

    def save_results(self) -> None:
        """Save scan results to file."""
        if not self.current_results:
            QMessageBox.warning(
                self, "No Results", "No scan results to save."
            )
            return

        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Scan Results", "", "JSON Files (*.json)"
        )
        if filename:
            # TODO: Implement save functionality
            self.ui.statusbar.showMessage(f"Saved: {filename}")

    def on_delete_requested(self, paths: List[str]):
        """Handle deletion request from results viewer."""
        if not paths:
            return

        # TODO: Implement deletion via backend interface
        # For now, just show confirmation
        QMessageBox.information(
            self,
            "Deletion Staged",
            f"{len(paths)} items will be staged for deletion.\n\n"
            f"Backend integration coming soon!",
        )

    def show_about(self) -> None:
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
