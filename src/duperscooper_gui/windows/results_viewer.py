"""Results viewer widget for displaying duplicate groups."""

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QMessageBox,
    QStyle,
    QTreeWidgetItem,
    QWidget,
)

from ..models.results_model import (
    ScanResults,
)


class ResultsViewer(QWidget):
    """Widget for viewing and managing scan results."""

    delete_requested = Signal(list)  # Emits list of paths to delete

    def __init__(self, parent=None):
        super().__init__(parent)

        # Load UI
        ui_file = Path(__file__).parent.parent / "ui" / "results_widget.ui"
        loader = QUiLoader()
        self.ui = loader.load(str(ui_file), self)

        # Store results
        self.results: Optional[ScanResults] = None

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
            group_item.setBackground(1, QBrush(QColor("#f5f5f5")))

            # Add files
            for file in group.files:
                file_item = QTreeWidgetItem(
                    group_item,
                    [
                        "",  # Checkbox
                        file.path,
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
                    for col in range(6):
                        font = file_item.font(col)
                        font.setBold(True)
                        file_item.setFont(col, font)
                        file_item.setForeground(col, QBrush(QColor("#2e7d32")))
                else:
                    # Color code similarity
                    sim_color = self._get_similarity_color(file.similarity_to_best)
                    file_item.setForeground(4, QBrush(sim_color))

                # Add tooltip with detailed info
                tooltip = (
                    f"Path: {file.path}\n"
                    f"Size: {file.size_mb:.2f} MB ({file.size_bytes:,} bytes)\n"
                    f"Quality: {file.audio_info}\n"
                    f"Quality Score: {file.quality_score:.1f}\n"
                    f"Similarity to Best: {file.similarity_to_best:.2f}%\n"
                    f"Recommended: {file.recommended_action.title()}"
                )
                file_item.setToolTip(1, tooltip)

        # Resize columns
        for i in range(6):
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
            group_item.setBackground(1, QBrush(QColor("#f5f5f5")))

            # Add albums
            for album in group.albums:
                album_item = QTreeWidgetItem(
                    group_item,
                    [
                        "",
                        album.path,
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
                    for col in range(6):
                        font = album_item.font(col)
                        font.setBold(True)
                        album_item.setFont(col, font)
                        album_item.setForeground(col, QBrush(QColor("#2e7d32")))
                else:
                    # Color code similarity
                    sim_color = self._get_similarity_color(album.match_percentage)
                    album_item.setForeground(4, QBrush(sim_color))

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
        for i in range(6):
            self.ui.resultsTree.resizeColumnToContents(i)

    def _get_similarity_color(self, similarity: float) -> QColor:
        """Get color based on similarity percentage."""
        if similarity >= 99.0:
            return QColor("#1b5e20")  # Dark green - very similar
        elif similarity >= 97.0:
            return QColor("#388e3c")  # Green - similar
        elif similarity >= 95.0:
            return QColor("#f57c00")  # Orange - moderately similar
        else:
            return QColor("#c62828")  # Red - less similar

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
        """Request deletion of selected items."""
        if not self.results:
            return

        selected_paths = self._get_selected_paths()
        if not selected_paths:
            QMessageBox.warning(self, "No Selection", "No items selected for deletion.")
            return

        # Confirm deletion
        item_type = "files" if self.results.mode == "track" else "albums"
        reply = QMessageBox.question(
            self,
            "Confirm Deletion",
            f"Stage {len(selected_paths)} {item_type} for deletion?\n\n"
            f"Potential savings: {self.results.potential_savings_mb:.1f} MB\n\n"
            f"Items will be moved to staging and can be restored.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            # Emit signal with paths to delete
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

        return paths
