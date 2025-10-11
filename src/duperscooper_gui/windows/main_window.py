"""Main window for duperscooper GUI."""

from pathlib import Path
from typing import List, Optional

from PySide6.QtGui import QCloseEvent
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QFileDialog,
    QMainWindow,
    QMessageBox,
)

from ..utils.realtime_scanner import RealtimeScanThread
from .dual_pane_viewer import DualPaneViewer


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self) -> None:
        super().__init__()

        # Load UI from .ui file
        ui_file = Path(__file__).parent.parent / "ui" / "main_window_new.ui"
        loader = QUiLoader()
        self.ui = loader.load(str(ui_file), self)  # type: ignore[attr-defined]

        # Set the loaded UI as the central widget
        self.setCentralWidget(self.ui.centralwidget)
        self.setMenuBar(self.ui.menubar)
        self.setStatusBar(self.ui.statusbar)

        # Resize to match UI
        self.resize(1200, 800)

        # Connect signals
        self._connect_signals()

        # Create dual-pane viewer as main interface
        self.dual_pane_viewer = DualPaneViewer(self)
        self.ui.dualPaneContainer.layout().addWidget(self.dual_pane_viewer)
        self.dual_pane_viewer.scan_requested.connect(self.on_dual_pane_scan_requested)
        self.dual_pane_viewer.stop_requested.connect(self.on_dual_pane_stop_requested)
        self.dual_pane_viewer.stop_and_process_requested.connect(
            self.on_dual_pane_stop_and_process_requested
        )
        self.dual_pane_viewer.stop_processing_requested.connect(
            self.on_dual_pane_stop_processing_requested
        )
        self.dual_pane_viewer.deletion_requested.connect(
            self.on_dual_pane_deletion_requested
        )

        # Track dual-pane scan thread
        self.dual_pane_scan_thread: Optional[RealtimeScanThread] = None
        self.scan_was_stopped = False

        # Status message
        self.ui.statusbar.showMessage("Ready")

    def _connect_signals(self) -> None:
        """Connect UI signals to slots."""
        # File menu
        self.ui.actionOpen.triggered.connect(self.open_results)
        self.ui.actionSave.triggered.connect(self.save_results)
        self.ui.actionExit.triggered.connect(self.close)
        self.ui.actionAbout.triggered.connect(self.show_about)

    def open_results(self) -> None:
        """Open scan results from file."""
        filename, _ = QFileDialog.getOpenFileName(
            self, "Open Scan Results", "", "JSON Files (*.json)"
        )
        if filename:
            # TODO: Load results into dual-pane viewer
            self.ui.statusbar.showMessage(f"Loaded: {filename}")

    def save_results(self) -> None:
        """Save scan results to file."""
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Scan Results", "", "JSON Files (*.json)"
        )
        if filename:
            # TODO: Save results from dual-pane viewer
            self.ui.statusbar.showMessage(f"Saved: {filename}")

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

    # Dual-pane viewer handlers

    def on_dual_pane_scan_requested(self, paths: List[str], mode: str):
        """Handle scan request from dual-pane viewer."""
        from ..utils.realtime_scanner import RealtimeScanThread

        # Reset stop flag
        self.scan_was_stopped = False

        # Start real-time scan thread
        self.dual_pane_scan_thread = RealtimeScanThread(paths, mode)
        self.dual_pane_scan_thread.progress.connect(self.on_dual_pane_scan_progress)
        self.dual_pane_scan_thread.group_found.connect(
            self.dual_pane_viewer.add_duplicate_group
        )
        self.dual_pane_scan_thread.finished.connect(self.on_dual_pane_scan_finished)
        self.dual_pane_scan_thread.error.connect(self.on_dual_pane_scan_error)
        self.dual_pane_scan_thread.processing_started.connect(
            self.on_dual_pane_processing_started
        )
        self.dual_pane_scan_thread.start()

        # Notify dual-pane viewer
        self.dual_pane_viewer.on_scan_started()

        # Update status
        self.ui.statusbar.showMessage(f"Scanning {len(paths)} path(s)...")
        self.ui.scanLogText.append(f"▶ Starting {mode} scan of {len(paths)} path(s)...")

    def on_dual_pane_stop_requested(self):
        """Handle stop request from dual-pane viewer."""
        if self.dual_pane_scan_thread and self.dual_pane_scan_thread.isRunning():
            self.scan_was_stopped = True
            self.dual_pane_scan_thread.stop()
            self.ui.statusbar.showMessage("Stopping scan...")
            self.ui.scanLogText.append("⏹ Stopping scan...")

    def on_dual_pane_stop_and_process_requested(self):
        """Handle stop-and-process request from dual-pane viewer."""
        if self.dual_pane_scan_thread and self.dual_pane_scan_thread.isRunning():
            self.dual_pane_scan_thread.stop_and_process()
            self.ui.statusbar.showMessage(
                "Stopping directory scan, will process albums found..."
            )
            self.ui.scanLogText.append(
                "⏹ Directory scan stopped, processing albums found so far..."
            )

    def on_dual_pane_stop_processing_requested(self):
        """Handle stop-processing request from dual-pane viewer."""
        if self.dual_pane_scan_thread and self.dual_pane_scan_thread.isRunning():
            self.dual_pane_scan_thread.stop_processing()
            self.ui.statusbar.showMessage("Stopping processing...")
            self.ui.scanLogText.append("⏹ Stopping processing...")

    def on_dual_pane_processing_started(self):
        """Handle processing phase starting."""
        self.dual_pane_viewer.on_processing_started()
        self.ui.statusbar.showMessage("Processing albums...")
        self.ui.scanLogText.append("▶ Processing albums...")

    def on_dual_pane_scan_progress(self, message: str, percentage: int):
        """Handle scan progress from dual-pane scan."""
        self.ui.scanLogText.append(message)
        # Reset stop buttons when stop is acknowledged
        # But not if processing is starting (message contains "processing")
        if ("stopped" in message.lower() or "stopping" in message.lower()) and (
            "processing" not in message.lower()
        ):
            self.dual_pane_viewer.reset_stop_buttons()
        # TODO: Update dual-pane viewer progress

    def on_dual_pane_scan_finished(self):
        """Handle scan completion from dual-pane scan."""
        # Groups were already added in real-time via group_found signal
        self.dual_pane_viewer.on_scan_finished()

        total_groups = self.dual_pane_viewer.ui.resultsTree.topLevelItemCount()
        if self.scan_was_stopped:
            self.ui.scanLogText.append("⏹ Scan stopped by user")
            self.ui.statusbar.showMessage("Scan stopped")
        else:
            self.ui.scanLogText.append(
                f"✓ Scan complete - {total_groups} duplicate groups found"
            )
            self.ui.statusbar.showMessage(
                f"Scan complete - {total_groups} groups found"
            )

    def on_dual_pane_scan_error(self, error_message: str):
        """Handle scan error from dual-pane scan."""
        self.dual_pane_viewer.on_scan_error(error_message)
        self.ui.scanLogText.append(f"❌ Scan Error:\n{error_message}")
        self.ui.statusbar.showMessage("Scan failed - see log")

    def on_dual_pane_deletion_requested(self, paths: List[str], mode: str):
        """Handle deletion request from dual-pane viewer."""
        # Use backend interface to stage items
        from ..utils.backend_interface import stage_items

        try:
            # Stage the items
            stage_items(paths, mode)

            # Log success
            self.ui.scanLogText.append(f"✓ Staged {len(paths)} {mode}(s) for deletion")
            self.ui.statusbar.showMessage(f"Staged {len(paths)} item(s) for deletion")

        except Exception as e:
            # Log error
            self.ui.scanLogText.append(f"❌ Deletion Error:\n{str(e)}")
            self.ui.statusbar.showMessage("Deletion failed - see log")
            QMessageBox.critical(
                self, "Deletion Error", f"Failed to delete items:\n\n{str(e)}"
            )

    def closeEvent(self, event: QCloseEvent) -> None:
        """Handle window close - clean up running threads."""
        # Stop scan thread if running
        if self.dual_pane_scan_thread and self.dual_pane_scan_thread.isRunning():
            self.dual_pane_scan_thread.stop()
            self.dual_pane_scan_thread.wait(2000)  # Wait up to 2 seconds
            if self.dual_pane_scan_thread.isRunning():
                # Force terminate if it won't stop
                self.dual_pane_scan_thread.terminate()
                self.dual_pane_scan_thread.wait()

        # Accept the close event
        event.accept()
