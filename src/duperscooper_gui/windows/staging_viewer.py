"""Staging management viewer for duperscooper GUI."""

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QMessageBox,
    QRadioButton,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class LoadBatchesThread(QThread):
    """Background thread for loading staged batches."""

    finished = Signal(list)  # Emits list of batch dicts
    error = Signal(str)  # Emits error messages

    def run(self) -> None:
        """Load batches in background thread."""
        try:
            from ..utils.backend_interface import list_deleted

            batches = list_deleted()
            self.finished.emit(batches)
        except Exception as e:
            self.error.emit(str(e))


class StagingViewer(QWidget):
    """
    Staging management interface for viewing and restoring batches.

    Displays a table of staged deletion batches with metadata and provides
    controls for restore and empty operations.
    """

    # Signals
    restore_requested = Signal(str, str)  # (batch_id, restore_to)
    empty_requested = Signal(int, int)  # (older_than, keep_last)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        # Load UI from .ui file
        ui_file = Path(__file__).parent.parent / "ui" / "staging_widget.ui"
        loader = QUiLoader()
        self.ui = loader.load(str(ui_file), self)  # type: ignore[attr-defined]

        # Set layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ui)

        # Track batches
        self.batches: List[Dict] = []

        # Connect signals
        self.ui.refreshButton.clicked.connect(self.refresh_queue)
        self.ui.removeButton.clicked.connect(self.on_remove_clicked)
        self.ui.deleteAllButton.clicked.connect(self.on_delete_all_clicked)
        self.ui.emptyButton.clicked.connect(self.on_empty_clicked)
        self.ui.batchTable.itemSelectionChanged.connect(self.on_selection_changed)

        # Load initial data
        self.refresh_queue()

    def refresh_batches(self) -> None:
        """Refresh the list of staged batches."""
        # Start background thread to load batches
        self.load_thread = LoadBatchesThread()
        self.load_thread.finished.connect(self.on_batches_loaded)
        self.load_thread.error.connect(self.on_load_error)
        self.load_thread.start()

        # Update UI
        self.ui.refreshButton.setEnabled(False)
        self.ui.refreshButton.setText("🔄 Loading...")

    def on_batches_loaded(self, batches: List[Dict]) -> None:
        """Handle batches loaded successfully."""
        print(f"DEBUG: Loaded {len(batches)} batches")  # Debug
        self.batches = batches
        self.populate_table()

        # Re-enable refresh button
        self.ui.refreshButton.setEnabled(True)
        self.ui.refreshButton.setText("🔄 Refresh")

    def on_load_error(self, error_message: str) -> None:
        """Handle batch loading error."""
        print(f"ERROR loading batches: {error_message}")  # Debug
        self.ui.summaryLabel.setText(f"Error loading batches: {error_message}")

        # Re-enable refresh button
        self.ui.refreshButton.setEnabled(True)
        self.ui.refreshButton.setText("🔄 Refresh")

    def populate_table(self) -> None:
        """Populate table with completed batch data.

        Already in .deletedByDuperscooper.
        """
        print(f"DEBUG: populate_table called with {len(self.batches)} batches")  # Debug
        # Clear existing rows
        self.ui.batchTable.setRowCount(0)

        if not self.batches:
            print(
                "DEBUG: No batches, showing 'No completed deletions' message"
            )  # Debug
            self.ui.summaryLabel.setText("No completed deletions")
            return

        # Add rows - using new 4-column format
        for batch in self.batches:
            row = self.ui.batchTable.rowCount()
            self.ui.batchTable.insertRow(row)

            # Type (mode)
            mode = batch.get("mode", "unknown")
            self.ui.batchTable.setItem(row, 0, QTableWidgetItem(mode.title()))

            # Path (staging location)
            staging_path = batch.get("staging_path", "")
            batch_id = batch.get("id", "")
            display_path = f"Batch {batch_id.replace('batch_', '')} - {staging_path}"
            path_item = QTableWidgetItem(display_path)
            path_item.setData(Qt.ItemDataRole.UserRole, batch_id)  # Store batch ID
            self.ui.batchTable.setItem(row, 1, path_item)

            # Size
            size_bytes = batch.get("space_freed_bytes", 0)
            size_str = self.format_size(size_bytes)
            self.ui.batchTable.setItem(row, 2, QTableWidgetItem(size_str))

            # Quality Info (show date + item count)
            timestamp_str = batch.get("timestamp", "")
            try:
                dt = datetime.fromisoformat(timestamp_str)
                date_str = dt.strftime("%Y-%m-%d %H:%M")
            except (ValueError, TypeError):
                date_str = timestamp_str
            items = batch.get("total_items_deleted", 0)
            info_str = f"{date_str} - {items} items"
            self.ui.batchTable.setItem(row, 3, QTableWidgetItem(info_str))

        # Update summary
        total_items = sum(b.get("total_items_deleted", 0) for b in self.batches)
        total_size = sum(b.get("space_freed_bytes", 0) for b in self.batches)
        size_str = self.format_size(total_size)

        self.ui.summaryLabel.setText(
            f"{len(self.batches)} completed deletion(s), "
            f"{total_items} item(s), {size_str} total"
        )

        # Delete All button is for queue items, not completed batches
        self.ui.deleteAllButton.setEnabled(False)

        # Resize columns to content
        self.ui.batchTable.resizeColumnsToContents()

    def refresh_queue(self) -> None:
        """Refresh the staging queue display (items not yet moved)."""
        from ..models.staging_queue import StagingQueue

        queue = StagingQueue()
        items = queue.get_all()

        # Clear existing rows
        self.ui.batchTable.setRowCount(0)

        if not items:
            self.ui.summaryLabel.setText("No items staged for deletion")
            self.ui.deleteAllButton.setEnabled(False)
            return

        # Group items by mode for display
        track_items = [item for item in items if item.mode == "track"]
        album_items = [item for item in items if item.mode == "album"]

        # Add track items
        for item in track_items:
            row = self.ui.batchTable.rowCount()
            self.ui.batchTable.insertRow(row)

            # Type
            self.ui.batchTable.setItem(row, 0, QTableWidgetItem("Track"))

            # Path
            path_item = QTableWidgetItem(item.path)
            path_item.setData(Qt.ItemDataRole.UserRole, item.path)
            self.ui.batchTable.setItem(row, 1, path_item)

            # Size
            size_str = self.format_size(item.size_bytes)
            self.ui.batchTable.setItem(row, 2, QTableWidgetItem(size_str))

            # Quality info
            self.ui.batchTable.setItem(row, 3, QTableWidgetItem(item.quality_info))

        # Add album items
        for item in album_items:
            row = self.ui.batchTable.rowCount()
            self.ui.batchTable.insertRow(row)

            # Type
            self.ui.batchTable.setItem(row, 0, QTableWidgetItem("Album"))

            # Path (with album/artist if available)
            display_path = item.path
            if item.album_name and item.artist_name:
                display_path = f"{item.artist_name} - {item.album_name}"
            elif item.album_name:
                display_path = item.album_name
            path_item = QTableWidgetItem(display_path)
            path_item.setData(Qt.ItemDataRole.UserRole, item.path)
            self.ui.batchTable.setItem(row, 1, path_item)

            # Size
            size_str = self.format_size(item.size_bytes)
            self.ui.batchTable.setItem(row, 2, QTableWidgetItem(size_str))

            # Quality info
            self.ui.batchTable.setItem(row, 3, QTableWidgetItem(item.quality_info))

        # Update summary
        total_size = sum(item.size_bytes for item in items)
        size_str = self.format_size(total_size)

        self.ui.summaryLabel.setText(f"{len(items)} item(s) staged, {size_str} total")

        # Enable Delete All button
        self.ui.deleteAllButton.setEnabled(len(items) > 0)

        # Resize columns to content
        self.ui.batchTable.resizeColumnsToContents()

    def on_selection_changed(self) -> None:
        """Handle table selection change."""
        selected_rows = len(self.ui.batchTable.selectionModel().selectedRows())
        self.ui.removeButton.setEnabled(selected_rows > 0)

    def on_remove_clicked(self) -> None:
        """Handle remove button click (remove selected items from queue)."""
        from ..models.staging_queue import StagingQueue

        # Get selected rows
        selected_rows = self.ui.batchTable.selectionModel().selectedRows()
        if not selected_rows:
            return

        # Get paths from selected rows
        paths_to_remove = []
        for index in selected_rows:
            row = index.row()
            # Get path from column 1 (Path/Album)
            path_item = self.ui.batchTable.item(row, 1)
            if path_item:
                # For queue items, the actual path is stored in UserRole
                path = path_item.data(Qt.ItemDataRole.UserRole)
                if not path:
                    # Fallback to text if UserRole not set
                    path = path_item.text()
                paths_to_remove.append(path)

        if not paths_to_remove:
            return

        # Remove from queue
        queue = StagingQueue()
        queue.remove_items(paths_to_remove)

        # Refresh display
        self.refresh_queue()

    def on_restore_clicked(self) -> None:
        """Handle restore button click."""
        # Get selected batch
        selected_rows = self.ui.batchTable.selectionModel().selectedRows()
        if not selected_rows:
            return

        row = selected_rows[0].row()
        batch_id_item = self.ui.batchTable.item(row, 0)
        if not batch_id_item:
            return

        batch_id = batch_id_item.data(Qt.ItemDataRole.UserRole)

        # Show restore location dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Restore Location")
        layout = QVBoxLayout(dialog)

        # Radio buttons for location
        original_radio = QRadioButton("Restore to original location")
        original_radio.setChecked(True)
        layout.addWidget(original_radio)

        custom_radio = QRadioButton("Restore to custom location:")
        layout.addWidget(custom_radio)

        # Custom path input
        from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QPushButton

        custom_layout = QHBoxLayout()
        custom_path_edit = QLineEdit()
        custom_path_edit.setEnabled(False)
        browse_button = QPushButton("Browse...")
        browse_button.setEnabled(False)

        def on_custom_toggled(checked: bool):
            custom_path_edit.setEnabled(checked)
            browse_button.setEnabled(checked)

        custom_radio.toggled.connect(on_custom_toggled)

        def on_browse():
            directory = QFileDialog.getExistingDirectory(
                dialog, "Select Restore Location"
            )
            if directory:
                custom_path_edit.setText(directory)

        browse_button.clicked.connect(on_browse)

        custom_layout.addWidget(custom_path_edit)
        custom_layout.addWidget(browse_button)
        layout.addLayout(custom_layout)

        # OK/Cancel buttons
        from PySide6.QtWidgets import QDialogButtonBox

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        # Show dialog
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Determine restore location
            if custom_radio.isChecked():
                restore_to = custom_path_edit.text()
                if not restore_to:
                    QMessageBox.warning(
                        self, "Invalid Location", "Please select a restore location"
                    )
                    return
            else:
                restore_to = ""  # Empty = original location

            # Emit signal
            self.restore_requested.emit(batch_id, restore_to)

    def on_delete_all_clicked(self) -> None:
        """Handle delete all staged button click.

        Move files to .deletedByDuperscooper.
        """
        from ..models.staging_queue import StagingQueue

        queue = StagingQueue()
        items = queue.get_all()

        if not items:
            QMessageBox.warning(self, "No Items", "No items staged for deletion.")
            return

        # Show confirmation dialog
        total_size = sum(item.size_bytes for item in items)
        size_str = self.format_size(total_size)

        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("Confirm Deletion")
        msg.setText(
            f"Are you sure you want to delete {len(items)} item(s) ({size_str})?"
        )
        msg.setInformativeText(
            "Files will be moved to .deletedByDuperscooper and can be restored later."
        )
        msg.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        msg.setDefaultButton(QMessageBox.StandardButton.No)

        if msg.exec() != QMessageBox.StandardButton.Yes:
            return

        # Move files using backend interface
        from ..utils.backend_interface import stage_items

        # Group by mode
        track_paths = [item.path for item in items if item.mode == "track"]
        album_paths = [item.path for item in items if item.mode == "album"]

        try:
            # Stage tracks
            if track_paths:
                stage_items(track_paths, mode="track")

            # Stage albums
            if album_paths:
                stage_items(album_paths, mode="album")

            # Clear the queue
            queue.clear()

            # Refresh display
            self.refresh_queue()

            # Show success message
            QMessageBox.information(
                self,
                "Deletion Complete",
                f"Successfully moved {len(items)} item(s) to staging.\n"
                f"Use 'Refresh' to see completed deletions.",
            )

        except Exception as e:
            QMessageBox.critical(
                self, "Deletion Failed", f"Failed to delete items: {str(e)}"
            )

    def on_empty_clicked(self) -> None:
        """Handle empty deleted button click."""
        # Show empty options dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Empty Deleted Batches")
        layout = QVBoxLayout(dialog)

        # Options
        from PySide6.QtWidgets import QCheckBox, QSpinBox

        older_check = QCheckBox("Delete batches older than:")
        older_spin = QSpinBox()
        older_spin.setMinimum(1)
        older_spin.setMaximum(365)
        older_spin.setValue(30)
        older_spin.setSuffix(" days")
        older_spin.setEnabled(False)
        older_check.toggled.connect(older_spin.setEnabled)

        from PySide6.QtWidgets import QHBoxLayout

        older_layout = QHBoxLayout()
        older_layout.addWidget(older_check)
        older_layout.addWidget(older_spin)
        layout.addLayout(older_layout)

        keep_check = QCheckBox("Keep the most recent:")
        keep_spin = QSpinBox()
        keep_spin.setMinimum(1)
        keep_spin.setMaximum(100)
        keep_spin.setValue(5)
        keep_spin.setSuffix(" batches")
        keep_spin.setEnabled(False)
        keep_check.toggled.connect(keep_spin.setEnabled)

        keep_layout = QHBoxLayout()
        keep_layout.addWidget(keep_check)
        keep_layout.addWidget(keep_spin)
        layout.addLayout(keep_layout)

        # Warning
        from PySide6.QtWidgets import QLabel

        warning_label = QLabel(
            "⚠️ This will permanently delete the selected batches.\n"
            "This action cannot be undone!"
        )
        warning_label.setStyleSheet("color: #d32f2f; font-weight: bold;")
        layout.addWidget(warning_label)

        # OK/Cancel buttons
        from PySide6.QtWidgets import QDialogButtonBox

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        # Show dialog
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Get options
            older_than = older_spin.value() if older_check.isChecked() else None
            keep_last = keep_spin.value() if keep_check.isChecked() else None

            if older_than is None and keep_last is None:
                QMessageBox.warning(
                    self,
                    "No Options Selected",
                    "Please select at least one deletion criteria",
                )
                return

            # Emit signal (convert None to -1 for signal compatibility)
            self.empty_requested.emit(
                older_than if older_than is not None else -1,
                keep_last if keep_last is not None else -1,
            )

    @staticmethod
    def format_size(size_bytes: int) -> str:
        """Format byte size as human readable string."""
        size: float = float(size_bytes)
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"
