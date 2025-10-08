"""Dual-pane viewer for scan results and staging."""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QFileDialog,
    QListWidget,
    QMessageBox,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
)


class DualPaneViewer(QWidget):
    """Dual-pane interface combining scan, results, and staging.

    Layout:
    - Top pane: Scan paths configuration
    - Bottom-left pane: Scan results (duplicates found)
    - Bottom-right pane: Staged for deletion

    Workflow:
    1. Add paths and configure scan
    2. Start scan - results appear in real-time on left
    3. Select items on left → Stage >> → Move to right
    4. Select items on right → << Unstage → Move back to left
    5. Click "Delete All" to perform deletion
    """

    # Signals
    scan_requested = Signal(list, str)  # paths, mode
    stop_requested = Signal()
    deletion_requested = Signal(list, str)  # paths, mode

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        # Load UI
        loader = QUiLoader()
        ui_file = Path(__file__).parent.parent / "ui" / "dual_pane_widget.ui"
        self.ui = loader.load(str(ui_file), self)

        # Set up layout
        layout = self.layout()
        if layout is None:
            from PySide6.QtWidgets import QVBoxLayout

            layout = QVBoxLayout(self)
        layout.addWidget(self.ui)

        # Load default mode from config
        from duperscooper_gui.config.settings import Settings

        self.current_mode = Settings.DEFAULT_MODE

        # Track results data (path -> item data dict)
        self.results_data: Dict[str, Dict[str, Any]] = {}
        self.staging_data: Dict[str, Dict[str, Any]] = {}

        # Track group structure (path -> metadata)
        # Format: {path: {"group_item": QTreeWidgetItem, "group_id": int,
        #                 "original_index": int}}
        # original_index is the item's index when first added (never changes)
        self.item_metadata: Dict[str, Dict[str, Any]] = {}

        # Track group membership (group_id -> list of paths in original order)
        self.group_members: Dict[int, List[str]] = {}

        # Connect signals
        self.ui.addPathButton.clicked.connect(self.on_add_path_clicked)  # type: ignore[attr-defined]
        self.ui.removePathButton.clicked.connect(self.on_remove_path_clicked)  # type: ignore[attr-defined]
        self.ui.pathsList.itemSelectionChanged.connect(self.on_paths_selection_changed)  # type: ignore[attr-defined]

        self.ui.modeCombo.currentIndexChanged.connect(self.on_mode_changed)  # type: ignore[attr-defined]
        self.ui.startScanButton.clicked.connect(self.on_start_scan_clicked)  # type: ignore[attr-defined]
        self.ui.stopScanButton.clicked.connect(self.on_stop_scan_clicked)  # type: ignore[attr-defined]

        self.ui.selectAllButton.clicked.connect(self.on_select_all_clicked)  # type: ignore[attr-defined]
        self.ui.deselectAllButton.clicked.connect(self.on_deselect_all_clicked)  # type: ignore[attr-defined]
        self.ui.selectRecommendedButton.clicked.connect(  # type: ignore[attr-defined]
            self.on_select_recommended_clicked
        )
        self.ui.stageButton.clicked.connect(self.on_stage_clicked)  # type: ignore[attr-defined]
        self.ui.unstageButton.clicked.connect(self.on_unstage_clicked)  # type: ignore[attr-defined]
        self.ui.clearStagingButton.clicked.connect(self.on_clear_staging_clicked)  # type: ignore[attr-defined]

        self.ui.deleteAllButton.clicked.connect(self.on_delete_all_clicked)  # type: ignore[attr-defined]

        self.ui.resultsTree.itemSelectionChanged.connect(  # type: ignore[attr-defined]
            self.on_results_selection_changed
        )
        self.ui.resultsTree.itemChanged.connect(self.on_results_item_changed)  # type: ignore[attr-defined]

        self.ui.stagingTree.itemSelectionChanged.connect(  # type: ignore[attr-defined]
            self.on_staging_selection_changed
        )
        self.ui.stagingTree.itemChanged.connect(self.on_staging_item_changed)  # type: ignore[attr-defined]

        # Load default paths and mode from config
        self._load_defaults()

    def _load_defaults(self) -> None:
        """Load default paths and mode from config."""
        from duperscooper_gui.config.settings import Settings

        # Set mode combo box
        mode_index = 1 if Settings.DEFAULT_MODE == "album" else 0
        self.ui.modeCombo.setCurrentIndex(mode_index)  # type: ignore[attr-defined]

        # Load default paths
        for path in Settings.DEFAULT_PATHS:
            if Path(path).exists():
                self.ui.pathsList.addItem(path)  # type: ignore[attr-defined]

        # Update button state based on loaded paths
        self.update_scan_button_state()

    def on_add_path_clicked(self) -> None:
        """Add a new path to the paths list."""
        # For now, open file dialog
        self.on_browse_clicked()

    def on_remove_path_clicked(self) -> None:
        """Remove selected path from the paths list."""
        paths_list: QListWidget = self.ui.pathsList  # type: ignore[attr-defined]
        selected_items = paths_list.selectedItems()
        for item in selected_items:
            row = paths_list.row(item)
            paths_list.takeItem(row)

        self.update_scan_button_state()

    def on_browse_clicked(self) -> None:
        """Browse for a directory to add."""
        directory = QFileDialog.getExistingDirectory(
            self, "Select Directory to Scan", str(Path.home())
        )

        if directory:
            paths_list: QListWidget = self.ui.pathsList  # type: ignore[attr-defined]
            # Check if already in list
            for i in range(paths_list.count()):
                if paths_list.item(i).text() == directory:  # type: ignore[union-attr]
                    QMessageBox.information(
                        self, "Already Added", "This path is already in the list."
                    )
                    return

            paths_list.addItem(directory)
            self.update_scan_button_state()

    def on_paths_selection_changed(self) -> None:
        """Handle path selection change."""
        paths_list: QListWidget = self.ui.pathsList  # type: ignore[attr-defined]
        self.ui.removePathButton.setEnabled(len(paths_list.selectedItems()) > 0)  # type: ignore[attr-defined]

    def on_mode_changed(self, index: int) -> None:
        """Handle mode change."""
        self.current_mode = "track" if index == 0 else "album"

    def on_start_scan_clicked(self) -> None:
        """Start scan with current paths and mode."""
        # Get paths from list
        paths_list: QListWidget = self.ui.pathsList  # type: ignore[attr-defined]
        paths = []
        for i in range(paths_list.count()):
            item = paths_list.item(i)
            if item:
                paths.append(item.text())

        if not paths:
            QMessageBox.warning(
                self, "No Paths", "Please add at least one path to scan."
            )
            return

        # Clear previous results
        results_tree: QTreeWidget = self.ui.resultsTree  # type: ignore[attr-defined]
        staging_tree: QTreeWidget = self.ui.stagingTree  # type: ignore[attr-defined]
        results_tree.clear()
        staging_tree.clear()
        self.results_data.clear()
        self.staging_data.clear()
        self.item_metadata.clear()

        # Update UI state
        self.ui.startScanButton.setEnabled(False)  # type: ignore[attr-defined]
        self.ui.stopScanButton.setEnabled(True)  # type: ignore[attr-defined]
        self.ui.pathsGroup.setEnabled(False)  # type: ignore[attr-defined]
        self.ui.statusLabel.setText("Scanning...")  # type: ignore[attr-defined]

        # Emit signal
        self.scan_requested.emit(paths, self.current_mode)

    def on_stop_scan_clicked(self) -> None:
        """Stop the current scan."""
        self.stop_requested.emit()
        self.ui.stopScanButton.setEnabled(False)  # type: ignore[attr-defined]
        self.ui.statusLabel.setText("Stopping scan...")  # type: ignore[attr-defined]

    def on_scan_started(self) -> None:
        """Handle scan started."""
        self.ui.statusLabel.setText("Scanning for duplicates...")  # type: ignore[attr-defined]

    def on_scan_finished(self) -> None:
        """Handle scan finished."""
        self.ui.startScanButton.setEnabled(True)  # type: ignore[attr-defined]
        self.ui.stopScanButton.setEnabled(False)  # type: ignore[attr-defined]
        self.ui.pathsGroup.setEnabled(True)  # type: ignore[attr-defined]

        # total_groups = self.ui.resultsTree.topLevelItemCount()
        # self.ui.statusLabel.setText(
        #     f"Scan complete - {total_groups} duplicate groups found"
        # )

    def on_scan_error(self, error_msg: str) -> None:
        """Handle scan error."""
        self.ui.startScanButton.setEnabled(True)  # type: ignore[attr-defined]
        self.ui.stopScanButton.setEnabled(False)  # type: ignore[attr-defined]
        self.ui.pathsGroup.setEnabled(True)  # type: ignore[attr-defined]
        self.ui.statusLabel.setText(f"Scan error: {error_msg}")  # type: ignore[attr-defined]

        QMessageBox.critical(
            self, "Scan Error", f"An error occurred during scanning:\n\n{error_msg}"
        )

    def _format_group_header(self, group_id: int, items: List[Dict[str, Any]]) -> str:
        """Format group header with album/artist metadata.

        Args:
            group_id: Group number
            items: List of items in the group

        Returns:
            Formatted header string
        """
        if not items:
            return f"Group {group_id}"

        # Try to get album/artist from first item (they should all be the same)
        first_item = items[0]
        album = first_item.get("album_name", "").strip()
        artist = first_item.get("artist_name", "").strip()

        # Format based on available metadata
        if album and artist:
            return f"Group {group_id}: {album} by {artist}"
        elif album:
            return f"Group {group_id}: {album}"
        else:
            # Use folder name from path
            path = first_item.get("path", "")
            if path:
                folder_name = Path(path).parent.name
                return f"Group {group_id}: {folder_name}"
            else:
                return f"Group {group_id}"

    def add_duplicate_group(self, group_data: dict) -> None:
        """Add a duplicate group to results pane (real-time during scan).

        Args:
            group_data: Dict with group information (matches ScanResults format)
        """
        # Add files/albums to group
        items = group_data.get("files", []) or group_data.get("albums", [])
        group_id = group_data.get("group_id", 0)

        # Extract album/artist metadata for group header
        group_header = self._format_group_header(group_id, items)

        # Create group item
        results_tree: QTreeWidget = self.ui.resultsTree  # type: ignore[attr-defined]
        group_item = QTreeWidgetItem(
            results_tree,
            ["", group_header, "", "", ""],
        )
        group_item.setExpanded(True)

        # Track all paths in this group in original order
        group_paths = []

        for original_index, item in enumerate(items):
            path = item.get("path", "")
            size_mb = item.get("size_bytes", 0) / (1024 * 1024)
            quality = item.get("audio_info", "") or item.get("quality_info", "")
            similarity = item.get("similarity_to_best", 0)
            is_best = item.get("is_best", False)

            # Create tree item
            child_item = QTreeWidgetItem(
                group_item,
                [
                    "",
                    path,
                    f"{size_mb:.1f} MB",
                    quality,
                    f"{similarity:.1f}%" if similarity > 0 else "",
                ],
            )
            # Check recommended items by default
            recommended = item.get("recommended_action") == "delete"
            child_item.setCheckState(
                0, Qt.CheckState.Checked if recommended else Qt.CheckState.Unchecked
            )

            # Mark best item
            if is_best:
                child_item.setText(1, f"[Best] {path}")

            # Store data and metadata
            self.results_data[path] = item
            self.item_metadata[path] = {
                "group_item": group_item,
                "group_id": group_id,
                "original_index": original_index,
            }
            group_paths.append(path)

        # Store group membership
        self.group_members[group_id] = group_paths

        self.update_results_summary()
        self.update_button_states()

    def on_select_all_clicked(self) -> None:
        """Select all items in results pane."""
        results_tree: QTreeWidget = self.ui.resultsTree  # type: ignore[attr-defined]
        self._set_all_checked(results_tree, True)

    def on_deselect_all_clicked(self) -> None:
        """Deselect all items in results pane."""
        results_tree: QTreeWidget = self.ui.resultsTree  # type: ignore[attr-defined]
        self._set_all_checked(results_tree, False)

    def on_select_recommended_clicked(self) -> None:
        """Select items recommended for deletion (not marked as best)."""
        results_tree: QTreeWidget = self.ui.resultsTree  # type: ignore[attr-defined]
        root = results_tree.invisibleRootItem()
        for i in range(root.childCount()):
            group_item = root.child(i)
            for j in range(group_item.childCount()):
                item = group_item.child(j)
                path = item.text(1).replace("[Best] ", "")
                # Check recommended_action from stored data
                if path in self.results_data:
                    recommended = (
                        self.results_data[path].get("recommended_action") == "delete"
                    )
                    item.setCheckState(
                        0,
                        (
                            Qt.CheckState.Checked
                            if recommended
                            else Qt.CheckState.Unchecked
                        ),
                    )

    def _set_all_checked(self, tree: QTreeWidget, checked: bool) -> None:
        """Set all items in tree to checked/unchecked."""
        root = tree.invisibleRootItem()
        for i in range(root.childCount()):
            group_item = root.child(i)
            for j in range(group_item.childCount()):
                item = group_item.child(j)
                item.setCheckState(
                    0, Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
                )

    def on_stage_clicked(self) -> None:
        """Move selected items from results to staging pane."""
        # Get checked items from results tree
        items_to_stage: List[Tuple[str, QTreeWidgetItem]] = []
        results_tree: QTreeWidget = self.ui.resultsTree  # type: ignore[attr-defined]
        root = results_tree.invisibleRootItem()

        for i in range(root.childCount()):
            group_item = root.child(i)
            for j in range(group_item.childCount()):
                item = group_item.child(j)
                if item.checkState(0) == Qt.CheckState.Checked:
                    path = item.text(1).replace("[Best] ", "")
                    items_to_stage.append((path, item))

        if not items_to_stage:
            QMessageBox.information(self, "No Selection", "No items selected to stage.")
            return

        # Move to staging pane
        staging_tree: QTreeWidget = self.ui.stagingTree  # type: ignore[attr-defined]
        for path, item in items_to_stage:
            # Add to staging tree (include all 5 columns)
            staging_item = QTreeWidgetItem(
                staging_tree,
                [
                    "",
                    item.text(1),  # Path/Album
                    item.text(2),  # Size
                    item.text(3),  # Quality
                    item.text(4),  # Similarity
                ],
            )
            staging_item.setCheckState(0, Qt.CheckState.Unchecked)

            # Move data
            if path in self.results_data:
                self.staging_data[path] = self.results_data.pop(path)

        # Remove from results tree
        self._remove_checked_items(results_tree)

        self.update_results_summary()
        self.update_staging_summary()
        self.update_button_states()

    def on_unstage_clicked(self) -> None:
        """Move selected items from staging back to results pane."""
        # Get checked items from staging tree
        items_to_unstage: List[Tuple[str, QTreeWidgetItem]] = []
        staging_tree: QTreeWidget = self.ui.stagingTree  # type: ignore[attr-defined]
        root = staging_tree.invisibleRootItem()

        for i in range(root.childCount()):
            item = root.child(i)
            if item.checkState(0) == Qt.CheckState.Checked:
                path = item.text(1).replace("[Best] ", "")
                items_to_unstage.append((path, item))

        if not items_to_unstage:
            QMessageBox.information(
                self, "No Selection", "No items selected to unstage."
            )
            return

        # Move back to results pane, restoring group structure
        self._restore_items_to_results(items_to_unstage)

        # Remove from staging tree
        self._remove_checked_items(staging_tree)

        self.update_results_summary()
        self.update_staging_summary()
        self.update_button_states()

    def on_clear_staging_clicked(self) -> None:
        """Clear all items from staging (move back to results)."""
        # Get all items from staging tree
        items_to_unstage: List[Tuple[str, QTreeWidgetItem]] = []
        staging_tree: QTreeWidget = self.ui.stagingTree  # type: ignore[attr-defined]
        root = staging_tree.invisibleRootItem()

        for i in range(root.childCount()):
            item = root.child(i)
            path = item.text(1).replace("[Best] ", "")
            items_to_unstage.append((path, item))

        if not items_to_unstage:
            return

        # Show confirmation dialog
        reply = QMessageBox.question(
            self,
            "Unstage All",
            f"Move all {len(items_to_unstage)} staged item(s) back to results?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        # Move all items back to results pane, restoring group structure
        self._restore_items_to_results(items_to_unstage)

        # Clear staging tree
        staging_tree.clear()

        self.update_results_summary()
        self.update_staging_summary()
        self.update_button_states()

    def _restore_items_to_results(
        self, items_to_unstage: List[Tuple[str, QTreeWidgetItem]]
    ) -> None:
        """Restore items to their original group and position in results tree.

        Args:
            items_to_unstage: List of (path, staging_item) tuples
        """
        results_tree: QTreeWidget = self.ui.resultsTree  # type: ignore[attr-defined]
        for path, staging_item in items_to_unstage:
            # Get original metadata
            if path not in self.item_metadata:
                # Fallback: add to top level if metadata lost
                results_item = QTreeWidgetItem(
                    results_tree,
                    [
                        "",
                        staging_item.text(1),
                        staging_item.text(2),
                        staging_item.text(3),
                        "",
                    ],
                )
                results_item.setCheckState(0, Qt.CheckState.Unchecked)
            else:
                metadata = self.item_metadata[path]
                group_item = metadata["group_item"]

                # Get original data to restore similarity and best status
                original_data = self.staging_data.get(path, {})
                is_best = original_data.get("is_best", False)
                similarity = original_data.get("similarity_to_best", 0)

                # Create tree item with original formatting
                display_path = staging_item.text(1)
                if is_best and not display_path.startswith("[Best]"):
                    display_path = f"[Best] {path}"
                elif not is_best and display_path.startswith("[Best]"):
                    display_path = path

                results_item = QTreeWidgetItem(
                    [
                        "",
                        display_path,
                        staging_item.text(2),
                        staging_item.text(3),
                        f"{similarity:.1f}%" if similarity > 0 else "",
                    ],
                )

                # Add as child of group (append to end is safer than trying to
                # restore exact position when other items may still be in the group)
                group_item.addChild(results_item)

                # Always leave unchecked when unstaging
                results_item.setCheckState(0, Qt.CheckState.Unchecked)

            # Move data back
            if path in self.staging_data:
                self.results_data[path] = self.staging_data.pop(path)

    def _remove_checked_items(self, tree: QTreeWidget) -> None:
        """Remove all checked items from tree."""
        root = tree.invisibleRootItem()
        for i in reversed(range(root.childCount())):
            group_or_item = root.child(i)

            # Check if this is a group or standalone item
            if group_or_item.childCount() > 0:
                # It's a group - remove checked children
                for j in reversed(range(group_or_item.childCount())):
                    child = group_or_item.child(j)
                    if child.checkState(0) == Qt.CheckState.Checked:
                        group_or_item.removeChild(child)

                # Remove empty groups
                if group_or_item.childCount() == 0:
                    root.removeChild(group_or_item)
            else:
                # It's a standalone item - remove if checked
                if group_or_item.checkState(0) == Qt.CheckState.Checked:
                    root.removeChild(group_or_item)

    def on_delete_all_clicked(self) -> None:
        """Delete all staged items."""
        staging_tree: QTreeWidget = self.ui.stagingTree  # type: ignore[attr-defined]
        if staging_tree.topLevelItemCount() == 0:
            QMessageBox.information(self, "No Items", "No items staged for deletion.")
            return

        # Get all paths from staging
        paths = list(self.staging_data.keys())

        if not paths:
            return

        # Calculate total size
        total_size = sum(
            item.get("size_bytes", 0) for item in self.staging_data.values()
        )
        size_mb = total_size / (1024 * 1024)

        # Show confirmation dialog
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("Confirm Deletion")
        msg.setText(
            f"Are you sure you want to delete {len(paths)} item(s) ({size_mb:.1f} MB)?"
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

        # Emit deletion signal
        self.deletion_requested.emit(paths, self.current_mode)

        # Clear staging
        staging_tree.clear()
        self.staging_data.clear()

        self.update_staging_summary()
        self.update_button_states()

        # Show success message
        QMessageBox.information(
            self,
            "Deletion Complete",
            f"Successfully moved {len(paths)} item(s) to staging.\n"
            f"Files are now in .deletedByDuperscooper/",
        )

    def on_results_selection_changed(self) -> None:
        """Handle results tree selection change."""
        self.update_button_states()

    def on_results_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        """Handle results tree item changed (checkbox toggled)."""
        if column == 0:  # Checkbox column
            self.update_button_states()

    def on_staging_selection_changed(self) -> None:
        """Handle staging tree selection change."""
        self.update_button_states()

    def on_staging_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        """Handle staging tree item changed (checkbox toggled)."""
        if column == 0:  # Checkbox column
            self.update_button_states()

    def update_scan_button_state(self) -> None:
        """Update start scan button enabled state."""
        paths_list: QListWidget = self.ui.pathsList  # type: ignore[attr-defined]
        has_paths = paths_list.count() > 0
        self.ui.startScanButton.setEnabled(has_paths)  # type: ignore[attr-defined]

    def update_button_states(self) -> None:
        """Update button enabled states based on current state."""
        results_tree: QTreeWidget = self.ui.resultsTree  # type: ignore[attr-defined]
        staging_tree: QTreeWidget = self.ui.stagingTree  # type: ignore[attr-defined]

        # Results pane buttons
        has_results = results_tree.topLevelItemCount() > 0
        self.ui.selectAllButton.setEnabled(has_results)  # type: ignore[attr-defined]
        self.ui.deselectAllButton.setEnabled(has_results)  # type: ignore[attr-defined]
        self.ui.selectRecommendedButton.setEnabled(has_results)  # type: ignore[attr-defined]

        # Stage button - enabled if any results are checked
        has_checked_results = self._has_checked_items(results_tree)
        self.ui.stageButton.setEnabled(has_checked_results)  # type: ignore[attr-defined]

        # Staging pane buttons
        has_staging = staging_tree.topLevelItemCount() > 0
        self.ui.deleteAllButton.setEnabled(has_staging)  # type: ignore[attr-defined]
        self.ui.clearStagingButton.setEnabled(has_staging)  # type: ignore[attr-defined]

        # Unstage button - enabled if any staging items are checked
        has_checked_staging = self._has_checked_items(staging_tree)
        self.ui.unstageButton.setEnabled(has_checked_staging)  # type: ignore[attr-defined]

    def _has_checked_items(self, tree: QTreeWidget) -> bool:
        """Check if tree has any checked items."""
        root = tree.invisibleRootItem()
        for i in range(root.childCount()):
            group_or_item = root.child(i)

            if group_or_item.childCount() > 0:
                # It's a group
                for j in range(group_or_item.childCount()):
                    if group_or_item.child(j).checkState(0) == Qt.CheckState.Checked:
                        return True
            else:
                # Standalone item
                if group_or_item.checkState(0) == Qt.CheckState.Checked:
                    return True
        return False

    def update_results_summary(self) -> None:
        """Update results pane summary label."""
        count = len(self.results_data)
        total_size = sum(
            item.get("size_bytes", 0) for item in self.results_data.values()
        )
        size_mb = total_size / (1024 * 1024)

        if count == 0:
            self.ui.resultsSummary.setText("No duplicates in results")  # type: ignore[attr-defined]
        else:
            item_type = "files" if self.current_mode == "track" else "albums"
            self.ui.resultsSummary.setText(  # type: ignore[attr-defined]
                f"{count} {item_type}, {size_mb:.1f} MB total"
            )

    def update_staging_summary(self) -> None:
        """Update staging pane summary label."""
        count = len(self.staging_data)
        total_size = sum(
            item.get("size_bytes", 0) for item in self.staging_data.values()
        )
        size_mb = total_size / (1024 * 1024)

        if count == 0:
            self.ui.stagingSummary.setText("No items staged")  # type: ignore[attr-defined]
        else:
            item_type = "files" if self.current_mode == "track" else "albums"
            self.ui.stagingSummary.setText(  # type: ignore[attr-defined]
                f"{count} {item_type} staged, {size_mb:.1f} MB total"
            )
