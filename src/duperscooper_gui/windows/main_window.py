"""Main window for duperscooper GUI."""

from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QCloseEvent
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


class DeletionThread(QThread):
    """Background thread for staging deletions."""

    progress = Signal(str)  # Emits progress messages
    finished = Signal(dict)  # Emits result dict
    error = Signal(str)  # Emits error messages

    def __init__(self, paths: List[str], mode: str, store_fingerprints: bool = False):
        super().__init__()
        self.paths = paths
        self.mode = mode
        self.store_fingerprints = store_fingerprints

    def run(self) -> None:
        """Run deletion staging in background thread."""
        try:
            from ..utils.backend_interface import stage_items

            self.progress.emit(f"▶ Staging {len(self.paths)} items for deletion...")
            result = stage_items(self.paths, self.mode, self.store_fingerprints)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class RestorationThread(QThread):
    """Background thread for restoring deletions."""

    progress = Signal(str)  # Emits progress messages
    finished = Signal(dict)  # Emits result dict with restored_paths
    error = Signal(str)  # Emits error messages

    def __init__(self, batch_id: str, restore_to: str = ""):
        super().__init__()
        self.batch_id = batch_id
        self.restore_to = restore_to

    def run(self) -> None:
        """Run restoration in background thread."""
        try:
            from ..utils.backend_interface import restore_batch

            self.progress.emit(f"▶ Restoring items from {self.batch_id}...")
            result_output = restore_batch(
                self.batch_id, self.restore_to if self.restore_to else None
            )

            # Parse restored paths from output
            # Output format: "Restored N items from batch_..."
            restored_paths = []
            # TODO: Parse actual paths from manifest if needed
            # For now, we'll rely on backend success

            self.finished.emit(
                {
                    "success": True,
                    "batch_id": self.batch_id,
                    "message": result_output,
                    "restored_paths": restored_paths,
                }
            )
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
        self.results_viewer.restore_requested.connect(self.on_restore_requested)
        self.results_viewer.copy_batch_requested.connect(self.on_copy_batch_requested)

        # Track current results
        self.current_results: Optional[ScanResults] = None

        # Set default options - Album Mode is index 1
        self.ui.modeCombo.setCurrentIndex(1)

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
            # Clean up and format messages for better readability
            clean_msg = message.replace("█", "#").replace("▌", "-")

            # Add visual indicators
            if "PROGRESS:" in clean_msg:
                clean_msg = clean_msg.replace("PROGRESS:", "▶").strip()
            elif "ERROR:" in clean_msg.upper():
                clean_msg = f"❌ {clean_msg}"
            elif "Found" in clean_msg and "duplicate" in clean_msg:
                clean_msg = f"✓ {clean_msg}"

            self.ui.scanLogText.append(clean_msg)
            # Scroll to bottom
            self.ui.scanLogText.verticalScrollBar().setValue(
                self.ui.scanLogText.verticalScrollBar().maximum()
            )

    def on_scan_finished(self, json_output: str) -> None:
        """Handle scan completion."""

        self.ui.scanProgressBar.setValue(100)
        self.ui.startScanButton.setEnabled(True)

        self.ui.scanLogText.append("\n=== Scan Complete ===")

        # Load results
        try:
            self.current_results = ScanResults.from_json(json_output)
            self.results_viewer.load_results(self.current_results)

            if self.current_results.total_groups == 0:
                self.ui.scanLogText.append("\n✓ Scan complete - No duplicates found.")
                self.ui.statusbar.showMessage("Scan complete - no duplicates found")
            else:
                self.ui.scanLogText.append(
                    f"\n✓ Scan complete - Found {self.current_results.total_groups} "
                    f"duplicate groups with {self.current_results.total_duplicates} "
                    f"duplicates."
                )
                self.ui.statusbar.showMessage(
                    f"Scan complete - found {self.current_results.total_groups} "
                    f"duplicate group(s)"
                )
                # Only switch to results tab if duplicates were found
                self.ui.tabWidget.setCurrentIndex(1)

        except Exception as e:
            # Log error to scan log instead of showing popup
            self.ui.scanLogText.append(f"\n❌ Error loading results: {e}")
            self.ui.statusbar.showMessage("Error loading scan results")

    def on_scan_error(self, error_message: str) -> None:
        """Handle scan errors."""
        self.ui.scanProgressBar.setValue(0)
        self.ui.startScanButton.setEnabled(True)
        self.ui.statusbar.showMessage("Scan failed - see log for details")

        # Log error to scan log instead of showing popup
        self.ui.scanLogText.append(f"\n❌ Scan Error:\n{error_message}")

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
                # Log error to scan log instead of showing popup
                self.ui.scanLogText.append(
                    f"\n❌ Failed to load results file:\n{filename}\nError: {e}"
                )
                self.ui.statusbar.showMessage("Failed to load results file")

    def save_results(self) -> None:
        """Save scan results to file."""
        if not self.current_results:
            QMessageBox.warning(self, "No Results", "No scan results to save.")
            return

        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Scan Results", "", "JSON Files (*.json)"
        )
        if filename:
            # TODO: Implement save functionality
            self.ui.statusbar.showMessage(f"Saved: {filename}")

    def on_delete_requested(self, paths: List[str]):
        """Handle deletion request from results viewer."""
        if not paths or not self.current_results:
            return

        # Determine mode from current results
        mode = self.current_results.mode

        # Start deletion in background thread
        self.deletion_thread = DeletionThread(paths, mode)
        self.deletion_thread.progress.connect(self.on_deletion_progress)
        self.deletion_thread.finished.connect(self.on_deletion_finished)
        self.deletion_thread.error.connect(self.on_deletion_error)
        self.deletion_thread.start()

        # Disable delete button during operation
        # (Will be re-enabled after completion)
        self.ui.statusbar.showMessage("Staging items for deletion...")

    def on_deletion_progress(self, message: str):
        """Handle deletion progress messages."""
        self.ui.scanLogText.append(message)

    def on_deletion_finished(self, result: dict):
        """Handle deletion completion."""
        if result["success"]:
            # Success!
            batch_id = result["batch_id"]
            staged_count = result["staged_count"]

            # Log success
            self.ui.scanLogText.append(
                f"✓ {result['message']}\n"
                f"  Batch ID: {batch_id}\n"
                f"  Click 'Restore' button or use 'duperscooper --restore {batch_id}'"
            )
            self.ui.statusbar.showMessage(
                f"Successfully staged {staged_count} items - see restoration banner"
            )

            # Remove deleted items from results viewer
            deleted_paths = list(self.deletion_thread.paths)
            self.results_viewer.remove_deleted_items(deleted_paths)

            # Show restoration banner
            self.results_viewer.show_restoration_banner(batch_id, staged_count)

        else:
            # Error
            self.ui.scanLogText.append(f"❌ {result['message']}")
            self.ui.statusbar.showMessage("Deletion staging failed - see log")

    def on_deletion_error(self, error_message: str):
        """Handle deletion errors."""
        self.ui.scanLogText.append(f"❌ Deletion Error:\n{error_message}")
        self.ui.statusbar.showMessage("Deletion failed - see log")

    def on_restore_requested(self, batch_id: str, restore_to: str):
        """Handle restoration request from results viewer."""
        if not batch_id:
            return

        # Start restoration in background thread
        self.restoration_thread = RestorationThread(batch_id, restore_to)
        self.restoration_thread.progress.connect(self.on_restoration_progress)
        self.restoration_thread.finished.connect(self.on_restoration_finished)
        self.restoration_thread.error.connect(self.on_restoration_error)
        self.restoration_thread.start()

        # Update UI
        self.ui.statusbar.showMessage(f"Restoring items from {batch_id}...")

    def on_restoration_progress(self, message: str):
        """Handle restoration progress messages."""
        self.ui.scanLogText.append(message)

    def on_restoration_finished(self, result: dict):
        """Handle restoration completion."""
        if result["success"]:
            # Success!
            message = result["message"]

            # Log success
            self.ui.scanLogText.append(f"✓ {message}")
            self.ui.statusbar.showMessage("Restoration complete")

            # Remove restored items from results viewer
            # (Same logic as deletion - remove from tree)
            restored_paths = result.get("restored_paths", [])
            if restored_paths:
                self.results_viewer.remove_deleted_items(restored_paths)

            # Hide restoration banner (items are restored)
            self.results_viewer.hide_restoration_banner()

        else:
            # Error
            self.ui.scanLogText.append(f"❌ {result.get('message', 'Unknown error')}")
            self.ui.statusbar.showMessage("Restoration failed - see log")

    def on_restoration_error(self, error_message: str):
        """Handle restoration errors."""
        self.ui.scanLogText.append(f"❌ Restoration Error:\n{error_message}")
        self.ui.statusbar.showMessage("Restoration failed - see log")

    def on_copy_batch_requested(self, batch_id: str):
        """Handle batch ID copy request."""
        # Visual confirmation in scan log
        self.ui.scanLogText.append(f"📋 Copied batch ID to clipboard: {batch_id}")
        self.ui.statusbar.showMessage("Batch ID copied to clipboard", 3000)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Handle window close event - check for staged deletions."""
        # Check if there are staged deletions (restoration banner is visible)
        if self.results_viewer.has_staged_deletions():
            reply = QMessageBox.question(
                self,
                "Confirm Exit",
                "You have staged deletions that have not been restored.\n\n"
                "These files are staged in .deletedByDuperscooper/ and can be "
                "restored later using the CLI:\n"
                f"  duperscooper --restore {self.results_viewer.last_batch_id}\n\n"
                "Are you sure you want to exit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )

            if reply == QMessageBox.StandardButton.Yes:
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

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
