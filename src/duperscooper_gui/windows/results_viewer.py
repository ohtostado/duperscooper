"""Results viewer widget for displaying duplicate groups."""

from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QMessageBox,
    QStyle,
    QTreeWidgetItem,
    QWidget,
)

from ..config import Settings
from ..models.results_model import (
    ScanResults,
)


class ResultsViewer(QWidget):
    """Widget for viewing and managing scan results."""

    delete_requested = Signal(list)  # Emits list of paths to delete
    restore_requested = Signal(str, str)  # Emits (batch_id, restore_to)
    copy_batch_requested = Signal(str)  # Emits batch_id

    def __init__(self, parent=None):
        super().__init__(parent)

        # Load UI
        ui_file = Path(__file__).parent.parent / "ui" / "results_widget.ui"
        loader = QUiLoader()
        self.ui = loader.load(str(ui_file), self)

        # Store results
        self.results: Optional[ScanResults] = None

        # Store last deletion batch info for restoration
        self.last_batch_id: Optional[str] = None
        self.last_batch_count: int = 0

        # Get standard icons
        self._folder_icon = self.style().standardIcon(QStyle.SP_DirIcon)
        self._file_icon = self.style().standardIcon(QStyle.SP_FileIcon)
        self._audio_icon = self.style().standardIcon(QStyle.SP_MediaVolume)

        # Connect signals
        self._connect_signals()

    def _connect_signals(self):
        """Connect UI signals to slots."""
        self.ui.selectAllButton.clicked.connect(self.select_all)
        self.ui.deselectAllButton.clicked.connect(self.deselect_all)
        self.ui.selectRecommendedButton.clicked.connect(self.select_recommended)
        self.ui.previewButton.clicked.connect(self.preview_deletion)
        self.ui.deleteButton.clicked.connect(self.delete_selected)
        self.ui.resultsTree.itemChanged.connect(self.on_item_changed)

        # Restoration banner signals
        self.ui.restoreButton.clicked.connect(self.on_restore_clicked)
        self.ui.copyBatchButton.clicked.connect(self.on_copy_batch_clicked)
        self.ui.closeBannerButton.clicked.connect(self.hide_restoration_banner)

    def load_results(self, results: ScanResults):
        """Load and display scan results."""
        self.results = results

        # Clear existing items
        self.ui.resultsTree.clear()

        if results.mode == "track":
            self._load_track_results()
        else:
            self._load_album_results()

        # Update summary
        self._update_summary()
        self._update_selection_label()

    def _load_track_results(self):
        """Load track mode results into tree."""
        if not self.results:
            return

        for group in self.results.track_groups:
            # Create group item
            group_item = QTreeWidgetItem(
                self.ui.resultsTree,
                [
                    "",  # Checkbox column
                    f"Group {group.group_id} ({len(group.files)} files)",
                    "",  # Album (empty for group header)
                    "",  # Artist (empty for group header)
                    f"{group.total_size_mb:.1f} MB",
                    "",
                    "",
                    "",
                ],
            )
            group_item.setExpanded(True)

            # Style group header
            font = group_item.font(1)
            font.setBold(True)
            font.setPointSize(font.pointSize() + 1)
            group_item.setFont(1, font)
            group_item.setBackground(1, QBrush(Settings.Colors.GROUP_HEADER_BACKGROUND))
            group_item.setForeground(1, QBrush(Settings.Colors.GROUP_HEADER_FOREGROUND))

            # Add files
            for file in group.files:
                file_item = QTreeWidgetItem(
                    group_item,
                    [
                        "",  # Checkbox
                        file.path,
                        file.album or "",  # Album from metadata
                        file.artist or "",  # Artist from metadata
                        f"{file.size_mb:.1f} MB",
                        file.audio_info,
                        f"{file.similarity_to_best:.1f}%",
                        "Keep" if file.is_best else file.recommended_action.title(),
                    ],
                )

                # Add file icon
                file_item.setIcon(1, self._audio_icon)

                # Add checkbox
                file_item.setFlags(file_item.flags() | Qt.ItemIsUserCheckable)
                file_item.setCheckState(
                    0,
                    Qt.Checked if file.selected_for_deletion else Qt.Unchecked,
                )

                # Store file reference
                file_item.setData(0, Qt.UserRole, file)

                # Color code based on quality and status
                if file.is_best:
                    # Best file: bold green
                    for col in range(8):
                        font = file_item.font(col)
                        font.setBold(True)
                        file_item.setFont(col, font)
                        file_item.setForeground(
                            col, QBrush(Settings.Colors.BEST_QUALITY_COLOR)
                        )
                else:
                    # Color code similarity (now column 6 instead of 4)
                    sim_color = Settings.Colors.get_similarity_color(
                        file.similarity_to_best
                    )
                    file_item.setForeground(6, QBrush(sim_color))

                # Add tooltip with detailed info
                tooltip = (
                    f"Path: {file.path}\n"
                    f"Size: {file.size_mb:.2f} MB ({file.size_bytes:,} bytes)\n"
                    f"Quality: {file.audio_info}\n"
                    f"Quality Score: {file.quality_score:.1f}\n"
                    f"Similarity to Best: {file.similarity_to_best:.2f}%\n"
                )
                if file.album:
                    tooltip += f"Album: {file.album}\n"
                if file.artist:
                    tooltip += f"Artist: {file.artist}\n"
                tooltip += f"Recommended: {file.recommended_action.title()}"
                file_item.setToolTip(1, tooltip)

        # Resize columns
        for i in range(8):
            self.ui.resultsTree.resizeColumnToContents(i)

    def _load_album_results(self):
        """Load album mode results into tree."""
        if not self.results:
            return

        for group in self.results.album_groups:
            # Create group item
            group_header = f"Group {group.group_id}"
            if group.matched_album:
                if group.matched_artist:
                    group_header += f": {group.matched_album} by {group.matched_artist}"
                else:
                    group_header += f": {group.matched_album}"

            group_item = QTreeWidgetItem(
                self.ui.resultsTree,
                [
                    "",
                    f"{group_header} ({len(group.albums)} albums)",
                    "",  # Album (empty for group header)
                    "",  # Artist (empty for group header)
                    f"{group.total_size_mb:.1f} MB",
                    "",
                    "",
                    "",
                ],
            )
            group_item.setExpanded(True)

            # Style group header
            font = group_item.font(1)
            font.setBold(True)
            font.setPointSize(font.pointSize() + 1)
            group_item.setFont(1, font)
            group_item.setBackground(1, QBrush(Settings.Colors.GROUP_HEADER_BACKGROUND))
            group_item.setForeground(1, QBrush(Settings.Colors.GROUP_HEADER_FOREGROUND))

            # Add albums
            for album in group.albums:
                album_item = QTreeWidgetItem(
                    group_item,
                    [
                        "",
                        album.path,
                        album.album or "",  # Track-level album tag
                        album.artist or "",  # Track-level artist tag
                        f"{album.size_mb:.1f} MB",
                        album.quality_info,
                        f"{album.match_percentage:.1f}%",
                        "Keep" if album.is_best else album.recommended_action.title(),
                    ],
                )

                # Add folder icon
                album_item.setIcon(1, self._folder_icon)

                # Add checkbox
                album_item.setFlags(album_item.flags() | Qt.ItemIsUserCheckable)
                album_item.setCheckState(
                    0,
                    Qt.Checked if album.selected_for_deletion else Qt.Unchecked,
                )

                # Store album reference
                album_item.setData(0, Qt.UserRole, album)

                # Color code based on quality and status
                if album.is_best:
                    # Best album: bold green
                    for col in range(8):
                        font = album_item.font(col)
                        font.setBold(True)
                        album_item.setFont(col, font)
                        album_item.setForeground(
                            col, QBrush(Settings.Colors.BEST_QUALITY_COLOR)
                        )
                else:
                    # Color code similarity (now column 6 instead of 4)
                    sim_color = Settings.Colors.get_similarity_color(
                        album.match_percentage
                    )
                    album_item.setForeground(6, QBrush(sim_color))

                # Add tooltip with detailed info
                tooltip = (
                    f"Path: {album.path}\n"
                    f"Tracks: {album.track_count}\n"
                    f"Size: {album.size_mb:.2f} MB ({album.total_size_bytes:,} bytes)\n"
                    f"Quality: {album.quality_info}\n"
                    f"Quality Score: {album.quality_score:.1f}\n"
                    f"Match: {album.match_percentage:.2f}%\n"
                    f"Match Method: {album.match_method}\n"
                )
                if album.album_name:
                    tooltip += f"Album: {album.album_name}\n"
                if album.artist_name:
                    tooltip += f"Artist: {album.artist_name}\n"
                if album.musicbrainz_albumid:
                    tooltip += f"MusicBrainz ID: {album.musicbrainz_albumid}\n"
                tooltip += f"Recommended: {album.recommended_action.title()}"
                album_item.setToolTip(1, tooltip)

        # Resize columns
        for i in range(8):
            self.ui.resultsTree.resizeColumnToContents(i)

    def _update_summary(self):
        """Update summary label."""
        if not self.results:
            self.ui.summaryLabel.setText(
                "No results loaded. Run a scan or open a results file."
            )
            self.ui.statsLabel.setText("")
            return

        if self.results.mode == "track":
            summary = (
                f"🔍 {self.results.total_groups} duplicate groups found • "
                f"📁 {self.results.total_duplicates} duplicate files"
            )
            stats = (
                f"Total size: {self.results.total_size_mb:.1f} MB • "
                f"Potential savings: {self.results.potential_savings_mb:.1f} MB"
            )
        else:
            summary = (
                f"🔍 {self.results.total_groups} duplicate album groups found • "
                f"💿 {self.results.total_duplicates} duplicate albums"
            )
            stats = (
                f"Total size: {self.results.total_size_mb:.1f} MB • "
                f"Potential savings: {self.results.potential_savings_mb:.1f} MB"
            )

        self.ui.summaryLabel.setText(summary)
        self.ui.statsLabel.setText(stats)

    def _update_selection_label(self):
        """Update selection status label."""
        if not self.results:
            self.ui.selectionLabel.setText("0 items selected (0.0 MB)")
            return

        count = self._count_selected()
        size_mb = self.results.potential_savings_mb

        item_type = "files" if self.results.mode == "track" else "albums"
        self.ui.selectionLabel.setText(
            f"{count} {item_type} selected ({size_mb:.1f} MB potential savings)"
        )

    def _count_selected(self) -> int:
        """Count number of selected items."""
        if not self.results:
            return 0

        if self.results.mode == "track":
            return sum(
                sum(1 for f in g.files if f.selected_for_deletion)
                for g in self.results.track_groups
            )
        else:
            return sum(
                sum(1 for a in g.albums if a.selected_for_deletion)
                for g in self.results.album_groups
            )

    def on_item_changed(self, item: QTreeWidgetItem, column: int):
        """Handle checkbox state changes."""
        if column != 0:  # Only handle checkbox column
            return

        # Get the stored data object
        data = item.data(0, Qt.UserRole)
        if data:
            # Update selection state
            checked = item.checkState(0) == Qt.Checked
            data.selected_for_deletion = checked

            # Update UI
            self._update_selection_label()

    def select_all(self):
        """Select all items for deletion."""
        self._set_all_items(True)

    def deselect_all(self):
        """Deselect all items."""
        self._set_all_items(False)

    def select_recommended(self):
        """Select items based on recommended_action."""
        if not self.results:
            return

        # Set selection based on recommended_action
        root = self.ui.resultsTree.invisibleRootItem()
        for i in range(root.childCount()):
            group_item = root.child(i)
            for j in range(group_item.childCount()):
                item = group_item.child(j)
                data = item.data(0, Qt.UserRole)
                if data:
                    should_select = data.recommended_action == "delete"
                    data.selected_for_deletion = should_select
                    item.setCheckState(0, Qt.Checked if should_select else Qt.Unchecked)

        self._update_selection_label()

    def _set_all_items(self, checked: bool):
        """Set all items to checked or unchecked."""
        if not self.results:
            return

        root = self.ui.resultsTree.invisibleRootItem()
        for i in range(root.childCount()):
            group_item = root.child(i)
            for j in range(group_item.childCount()):
                item = group_item.child(j)
                data = item.data(0, Qt.UserRole)
                if data and not data.is_best:  # Don't select best files/albums
                    data.selected_for_deletion = checked
                    item.setCheckState(0, Qt.Checked if checked else Qt.Unchecked)

        self._update_selection_label()

    def preview_deletion(self):
        """Show preview of what will be deleted."""
        if not self.results:
            return

        selected_paths = self._get_selected_paths()
        if not selected_paths:
            QMessageBox.information(
                self, "No Selection", "No items selected for deletion."
            )
            return

        item_type = "files" if self.results.mode == "track" else "albums"
        preview_text = (
            f"The following {len(selected_paths)} {item_type} "
            f"will be staged for deletion:\n\n"
        )
        preview_text += "\n".join(f"  • {p}" for p in selected_paths[:20])

        if len(selected_paths) > 20:
            preview_text += f"\n\n...and {len(selected_paths) - 20} more"

        preview_text += (
            f"\n\nPotential space savings: {self.results.potential_savings_mb:.1f} MB"
        )

        QMessageBox.information(self, "Deletion Preview", preview_text)

    def delete_selected(self):
        """Stage selected items for deletion (no confirmation here)."""
        if not self.results:
            return

        selected_paths = self._get_selected_paths()
        if not selected_paths:
            QMessageBox.warning(self, "No Selection", "No items selected for staging.")
            return

        # Emit signal with paths to stage (no confirmation dialog)
        self.delete_requested.emit(selected_paths)

    def _get_selected_paths(self) -> list:
        """Get list of selected paths."""
        if not self.results:
            return []

        paths = []
        if self.results.mode == "track":
            for group in self.results.track_groups:
                for file in group.files:
                    if file.selected_for_deletion:
                        paths.append(file.path)
        else:
            for group in self.results.album_groups:
                for album in group.albums:
                    if album.selected_for_deletion:
                        paths.append(album.path)

        print(f"DEBUG _get_selected_paths: {len(paths)} paths selected")  # Debug
        return paths

    def remove_deleted_items(self, deleted_paths: List[str]):
        """
        Remove items from tree view after successful deletion.

        Args:
            deleted_paths: List of paths that were deleted
        """
        if not self.results:
            return

        deleted_set = set(deleted_paths)

        # Remove from data model
        if self.results.mode == "track":
            for group in self.results.track_groups:
                group.files = [f for f in group.files if f.path not in deleted_set]
            # Remove empty groups
            self.results.track_groups = [
                g for g in self.results.track_groups if g.files
            ]
        else:
            for group in self.results.album_groups:
                group.albums = [a for a in group.albums if a.path not in deleted_set]
            # Remove empty groups
            self.results.album_groups = [
                g for g in self.results.album_groups if g.albums
            ]

        # Reload the tree view with updated data
        if self.results.mode == "track":
            self._load_track_results()
        else:
            self._load_album_results()

        # Update summary
        self._update_summary()

    def show_restoration_banner(self, batch_id: str, count: int):
        """
        Show restoration banner with batch info.

        Args:
            batch_id: Batch ID for restoration
            count: Number of items in batch
        """
        self.last_batch_id = batch_id
        self.last_batch_count = count

        # Update banner text
        self.ui.restorationLabel.setText(f"✓ Staged {count} items to {batch_id}")

        # Show banner
        self.ui.restorationBanner.setVisible(True)

    def hide_restoration_banner(self):
        """Hide restoration banner."""
        self.ui.restorationBanner.setVisible(False)
        self.last_batch_id = None
        self.last_batch_count = 0

    def on_restore_clicked(self):
        """Handle restore button click."""
        if not self.last_batch_id:
            return

        # Show restore dialog with options
        from PySide6.QtWidgets import (
            QDialog,
            QDialogButtonBox,
            QFileDialog,
            QLabel,
            QPushButton,
            QRadioButton,
            QVBoxLayout,
        )

        dialog = QDialog(self)
        dialog.setWindowTitle("Restore Items")
        dialog.setMinimumWidth(400)

        layout = QVBoxLayout()

        # Title
        title = QLabel(
            f"Restore {self.last_batch_count} items from {self.last_batch_id}?"
        )
        title.setStyleSheet("font-weight: bold; font-size: 12pt;")
        layout.addWidget(title)

        # Options
        original_radio = QRadioButton("Restore to original location")
        original_radio.setChecked(True)
        layout.addWidget(original_radio)

        custom_radio = QRadioButton("Restore to custom location:")
        layout.addWidget(custom_radio)

        # Custom location selector
        custom_path = QLabel("(Select custom location)")
        custom_path.setEnabled(False)
        layout.addWidget(custom_path)

        browse_btn = QPushButton("Browse...")
        browse_btn.setEnabled(False)
        layout.addWidget(browse_btn)

        # Enable custom path when radio selected
        def on_custom_toggled(checked):
            custom_path.setEnabled(checked)
            browse_btn.setEnabled(checked)

        custom_radio.toggled.connect(on_custom_toggled)

        # Browse button
        def on_browse():
            directory = QFileDialog.getExistingDirectory(
                dialog, "Select Restore Location"
            )
            if directory:
                custom_path.setText(directory)

        browse_btn.clicked.connect(on_browse)

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        dialog.setLayout(layout)

        if dialog.exec() == QDialog.Accepted:
            # Determine restore location
            restore_to = None
            if custom_radio.isChecked():
                restore_to = custom_path.text()
                if restore_to == "(Select custom location)":
                    QMessageBox.warning(
                        self,
                        "No Location",
                        "Please select a custom restore location.",
                    )
                    return

            # Emit restore signal
            self.restore_requested.emit(self.last_batch_id, restore_to or "")

    def on_copy_batch_clicked(self):
        """Handle copy batch ID button click."""
        if not self.last_batch_id:
            return

        from PySide6.QtWidgets import QApplication

        # Copy to clipboard
        QApplication.clipboard().setText(self.last_batch_id)

        # Emit signal
        self.copy_batch_requested.emit(self.last_batch_id)

    def has_staged_deletions(self) -> bool:
        """Check if there are staged deletions (restoration banner visible)."""
        return self.ui.restorationBanner.isVisible()
