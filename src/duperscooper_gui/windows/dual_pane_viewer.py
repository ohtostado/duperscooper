"""Dual-pane viewer for scan results and staging."""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHeaderView,
    QListWidget,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


class ItemPropertiesDialog(QDialog):
    """Dialog to display item properties in a table."""

    def __init__(self, item_data: Dict[str, Any], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Item Properties")
        self.resize(600, 400)

        layout = QVBoxLayout(self)

        # Create table
        table = QTableWidget(self)
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(["Property", "Value"])
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        # Populate table with item data
        table.setRowCount(len(item_data))
        for row, (key, value) in enumerate(sorted(item_data.items())):
            # Property name
            key_item = QTableWidgetItem(str(key))
            table.setItem(row, 0, key_item)

            # Property value
            value_item = QTableWidgetItem(str(value))
            table.setItem(row, 1, value_item)

        layout.addWidget(table)


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
    stop_and_process_requested = Signal()
    stop_processing_requested = Signal()
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
        self.ui.removeAllPathsButton.clicked.connect(self.on_remove_all_paths_clicked)  # type: ignore[attr-defined]
        self.ui.pathsList.itemSelectionChanged.connect(self.on_paths_selection_changed)  # type: ignore[attr-defined]

        self.ui.modeCombo.currentIndexChanged.connect(self.on_mode_changed)  # type: ignore[attr-defined]
        self.ui.allowPartialCheckBox.stateChanged.connect(self.on_allow_partial_changed)  # type: ignore[attr-defined]
        self.ui.startScanButton.clicked.connect(self.on_start_scan_clicked)  # type: ignore[attr-defined]

        self.ui.stopScanButton.clicked.connect(self.on_stop_scan_clicked)  # type: ignore[attr-defined]
        self.ui.stopAndProcessButton.clicked.connect(self.on_stop_and_process_clicked)  # type: ignore[attr-defined]

        # Fix ampersand display - Qt interprets & as mnemonic, use && for literal &
        self.ui.stopAndProcessButton.setText("⏹ Stop && Process")  # type: ignore[attr-defined]

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

        # Connect to item expanded/collapsed signals
        self.ui.resultsTree.itemExpanded.connect(self.on_item_expanded)  # type: ignore[attr-defined]
        self.ui.resultsTree.itemCollapsed.connect(self.on_item_collapsed)  # type: ignore[attr-defined]

        # Connect to item clicked signal for single-click expand/collapse
        self.ui.resultsTree.itemClicked.connect(self.on_results_item_clicked)  # type: ignore[attr-defined]

        # Enable context menus on trees
        self.ui.resultsTree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)  # type: ignore[attr-defined]
        self.ui.resultsTree.customContextMenuRequested.connect(  # type: ignore[attr-defined]
            self.on_results_context_menu
        )
        self.ui.stagingTree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)  # type: ignore[attr-defined]
        self.ui.stagingTree.customContextMenuRequested.connect(  # type: ignore[attr-defined]
            self.on_staging_context_menu
        )

        # Load default paths and mode from config
        self._load_defaults()

        # Configure column widths and headers
        self._configure_tree_columns()
        self._update_column_headers()

        # Update album options visibility
        self._update_album_options_visibility()

    def _configure_tree_columns(self) -> None:
        """Configure column widths and alignment for both trees."""
        results_tree: QTreeWidget = self.ui.resultsTree  # type: ignore[attr-defined]
        staging_tree: QTreeWidget = self.ui.stagingTree  # type: ignore[attr-defined]

        for tree in [results_tree, staging_tree]:
            # Column 0: Checkbox - narrow, no indentation
            tree.setColumnWidth(0, 25)
            # Column 1: Best (star) - narrow and centered
            tree.setColumnWidth(1, 50)
            # Other columns will auto-size

            # No indentation - checkboxes aligned to left
            tree.setIndentation(0)

            # Center align the checkbox column header
            header = tree.header()
            if header:
                header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)

            # Disable root decoration (we'll use unicode arrow in header text)
            tree.setRootIsDecorated(False)

    def _update_column_headers(self) -> None:
        """Update column headers based on current mode."""
        results_tree: QTreeWidget = self.ui.resultsTree  # type: ignore[attr-defined]
        staging_tree: QTreeWidget = self.ui.stagingTree  # type: ignore[attr-defined]

        # Column 2 changes based on mode
        column_name = "Folder" if self.current_mode == "album" else "Filename"

        for tree in [results_tree, staging_tree]:
            tree.headerItem().setText(2, column_name)  # type: ignore[union-attr]

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

        # Update button states based on loaded paths
        self.update_scan_button_state()
        self.on_paths_selection_changed()  # Enable Remove All if paths exist

    def on_add_path_clicked(self) -> None:
        """Add a new path to the paths list."""
        # For now, open file dialog
        self.on_browse_clicked()

    def on_remove_path_clicked(self) -> None:
        """Remove selected paths from the paths list."""
        paths_list: QListWidget = self.ui.pathsList  # type: ignore[attr-defined]
        selected_items = paths_list.selectedItems()
        for item in selected_items:
            row = paths_list.row(item)
            paths_list.takeItem(row)

        self.update_scan_button_state()
        self.on_paths_selection_changed()  # Update Remove All button state

    def on_remove_all_paths_clicked(self) -> None:
        """Remove all paths from the paths list."""
        paths_list: QListWidget = self.ui.pathsList  # type: ignore[attr-defined]

        # Confirm if there are paths to remove
        if paths_list.count() == 0:
            return

        reply = QMessageBox.question(
            self,
            "Remove All Paths",
            f"Remove all {paths_list.count()} path(s) from the list?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            paths_list.clear()
            self.update_scan_button_state()
            self.on_paths_selection_changed()  # Update button states

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
            self.on_paths_selection_changed()  # Update Remove All button state

    def on_paths_selection_changed(self) -> None:
        """Handle path selection change."""
        paths_list: QListWidget = self.ui.pathsList  # type: ignore[attr-defined]
        has_selection = len(paths_list.selectedItems()) > 0
        has_paths = paths_list.count() > 0

        self.ui.removePathButton.setEnabled(has_selection)  # type: ignore[attr-defined]
        self.ui.removeAllPathsButton.setEnabled(has_paths)  # type: ignore[attr-defined]

    def on_mode_changed(self, index: int) -> None:
        """Handle mode change."""
        new_mode = "track" if index == 0 else "album"

        # If mode is actually changing and there's data in the trees, confirm first
        if new_mode != self.current_mode:
            results_tree: QTreeWidget = self.ui.resultsTree  # type: ignore[attr-defined]
            staging_tree: QTreeWidget = self.ui.stagingTree  # type: ignore[attr-defined]

            has_data = (
                results_tree.topLevelItemCount() > 0
                or staging_tree.topLevelItemCount() > 0
            )

            if has_data:
                reply = QMessageBox.question(
                    self,
                    "Confirm Mode Change",
                    f"Switching to {new_mode} mode will clear all current "
                    "results and staged items.\n\nDo you want to continue?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )

                if reply != QMessageBox.StandardButton.Yes:
                    # Revert combo box to previous mode
                    old_index = 1 if self.current_mode == "album" else 0
                    self.ui.modeCombo.blockSignals(True)  # type: ignore[attr-defined]
                    self.ui.modeCombo.setCurrentIndex(old_index)  # type: ignore[attr-defined]
                    self.ui.modeCombo.blockSignals(False)  # type: ignore[attr-defined]
                    return

                # Clear both trees
                results_tree.clear()
                staging_tree.clear()
                self.results_data.clear()
                self.staging_data.clear()
                self.item_metadata.clear()
                self.group_members.clear()

                self.update_results_summary()
                self.update_staging_summary()
                self.update_button_states()

        self.current_mode = new_mode
        self._update_column_headers()
        self._update_album_options_visibility()

    def on_allow_partial_changed(self) -> None:
        """Handle allow partial checkbox change."""
        # Just update the state - will be used when scan is started
        pass

    def _update_album_options_visibility(self) -> None:
        """Enable/disable album-specific options based on mode."""
        is_album_mode = self.current_mode == "album"
        self.ui.allowPartialCheckBox.setEnabled(is_album_mode)  # type: ignore[attr-defined]

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
        self.ui.stopAndProcessButton.setEnabled(True)  # type: ignore[attr-defined]
        # Disable path controls but not the whole group (which contains stop buttons)
        self.ui.pathsList.setEnabled(False)  # type: ignore[attr-defined]
        self.ui.addPathButton.setEnabled(False)  # type: ignore[attr-defined]
        self.ui.removePathButton.setEnabled(False)  # type: ignore[attr-defined]
        self.ui.removeAllPathsButton.setEnabled(False)  # type: ignore[attr-defined]
        self.ui.modeCombo.setEnabled(False)  # type: ignore[attr-defined]
        self.ui.statusLabel.setText("Scanning...")  # type: ignore[attr-defined]

        # Emit signal
        self.scan_requested.emit(paths, self.current_mode)

    def on_stop_scan_clicked(self) -> None:
        """Stop the current scan."""
        self.stop_requested.emit()
        # Only disable the button that was clicked
        self.ui.stopScanButton.setText("Stopping...")  # type: ignore[attr-defined]
        self.ui.stopScanButton.setEnabled(False)  # type: ignore[attr-defined]
        # Disable the other stop button too since scan is stopping
        self.ui.stopAndProcessButton.setEnabled(False)  # type: ignore[attr-defined]
        self.ui.statusLabel.setText("Stopping scan...")  # type: ignore[attr-defined]

    def on_stop_and_process_clicked(self) -> None:
        """Stop directory scanning or stop processing, depending on current state."""
        button_text = self.ui.stopAndProcessButton.text()  # type: ignore[attr-defined]

        if "Stop Processing" in button_text:
            # Currently in processing phase, stop it
            self.stop_processing_requested.emit()
            self.ui.stopAndProcessButton.setText("Stopping...")  # type: ignore[attr-defined]
            self.ui.stopAndProcessButton.setEnabled(False)  # type: ignore[attr-defined]
            self.ui.statusLabel.setText("Stopping processing...")  # type: ignore[attr-defined]
        else:
            # Currently in directory scan phase, stop and process
            self.stop_and_process_requested.emit()
            self.ui.stopAndProcessButton.setText("Stopping...")  # type: ignore[attr-defined]
            self.ui.stopAndProcessButton.setEnabled(False)  # type: ignore[attr-defined]
            # Disable the other stop button too since scan is stopping
            self.ui.stopScanButton.setEnabled(False)  # type: ignore[attr-defined]
            self.ui.statusLabel.setText("Stopping directory scan...")  # type: ignore[attr-defined]

    def on_scan_started(self) -> None:
        """Handle scan started."""
        self.ui.statusLabel.setText("Scanning for duplicates...")  # type: ignore[attr-defined]

    def on_scan_finished(self) -> None:
        """Handle scan finished."""
        self.ui.startScanButton.setEnabled(True)  # type: ignore[attr-defined]
        self.ui.stopScanButton.setText("⏹ Stop Scan")  # type: ignore[attr-defined]
        self.ui.stopScanButton.setEnabled(False)  # type: ignore[attr-defined]
        self.ui.stopAndProcessButton.setText("⏹ Stop && Process")  # type: ignore[attr-defined]
        self.ui.stopAndProcessButton.setEnabled(False)  # type: ignore[attr-defined]
        # Re-enable path controls
        self.ui.pathsList.setEnabled(True)  # type: ignore[attr-defined]
        self.ui.addPathButton.setEnabled(True)  # type: ignore[attr-defined]
        self.ui.modeCombo.setEnabled(True)  # type: ignore[attr-defined]
        # Button states updated via on_paths_selection_changed
        self.on_paths_selection_changed()

        # total_groups = self.ui.resultsTree.topLevelItemCount()
        # self.ui.statusLabel.setText(
        #     f"Scan complete - {total_groups} duplicate groups found"
        # )

    def on_scan_error(self, error_msg: str) -> None:
        """Handle scan error."""
        self.ui.startScanButton.setEnabled(True)  # type: ignore[attr-defined]
        self.ui.stopScanButton.setText("⏹ Stop Scan")  # type: ignore[attr-defined]
        self.ui.stopScanButton.setEnabled(False)  # type: ignore[attr-defined]
        self.ui.stopAndProcessButton.setText("⏹ Stop && Process")  # type: ignore[attr-defined]
        self.ui.stopAndProcessButton.setEnabled(False)  # type: ignore[attr-defined]
        # Re-enable path controls
        self.ui.pathsList.setEnabled(True)  # type: ignore[attr-defined]
        self.ui.addPathButton.setEnabled(True)  # type: ignore[attr-defined]
        self.ui.modeCombo.setEnabled(True)  # type: ignore[attr-defined]
        # Button states updated via on_paths_selection_changed
        self.on_paths_selection_changed()
        self.ui.statusLabel.setText(f"Scan error: {error_msg}")  # type: ignore[attr-defined]

        QMessageBox.critical(
            self, "Scan Error", f"An error occurred during scanning:\n\n{error_msg}"
        )

    def reset_stop_buttons(self) -> None:
        """Reset stop buttons to their default state after stop is acknowledged."""
        self.ui.stopScanButton.setText("⏹ Stop Scan")  # type: ignore[attr-defined]
        self.ui.stopAndProcessButton.setText("⏹ Stop && Process")  # type: ignore[attr-defined]

    def on_processing_started(self) -> None:
        """Handle processing phase starting (after directory scan)."""
        # Change button to "Stop Processing" and re-enable it
        self.ui.stopAndProcessButton.setText("⏹ Stop Processing")  # type: ignore[attr-defined]
        self.ui.stopAndProcessButton.setEnabled(True)  # type: ignore[attr-defined]
        # Keep Stop Scan button disabled since directory scan is complete
        self.ui.stopScanButton.setEnabled(False)  # type: ignore[attr-defined]
        self.ui.statusLabel.setText("Processing albums...")  # type: ignore[attr-defined]

    def _format_path_tooltip(self, path: str) -> str:
        """Format a path for tooltip display with line breaks at slashes.

        Args:
            path: Full file path

        Returns:
            Formatted path with line breaks for readability
        """
        # Replace path separators with line breaks for better readability
        return path.replace("/", "/\n")

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

        # Prefix with unicode down arrow to mimic expand/collapse
        group_header = f"▼ {group_header}"

        # Create group item
        results_tree: QTreeWidget = self.ui.resultsTree  # type: ignore[attr-defined]
        group_item = QTreeWidgetItem(
            results_tree,
            [group_header, "", "", "", "", "", "", "", ""],  # 9 columns now
        )
        group_item.setExpanded(True)

        # Style the group header with background color
        from PySide6.QtGui import QBrush, QColor

        for col in range(0, 9):  # Updated to 9 columns
            group_item.setBackground(col, QBrush(QColor("#333333")))
            group_item.setForeground(col, QBrush(QColor("#fff7aa")))

        # Span the header text across all columns
        item_index = results_tree.indexOfTopLevelItem(group_item)
        results_tree.setFirstColumnSpanned(item_index, results_tree.rootIndex(), True)  # type: ignore[call-arg]

        # Track all paths in this group in original order
        group_paths = []

        for original_index, item in enumerate(items):
            path = item.get("path", "")
            path_obj = Path(path)
            filename = path_obj.name
            directory = str(path_obj.parent)

            size_mb = item.get("size_bytes", 0) / (1024 * 1024)
            quality = item.get("audio_info", "") or item.get("quality_info", "")
            # For albums use match_percentage, for tracks use similarity_to_best
            similarity = item.get("match_percentage") or item.get(
                "similarity_to_best", 0
            )
            is_best = item.get("is_best", False)
            quality_score = item.get("quality_score", 0)

            # Extract artist and album metadata
            artist = item.get("artist_name", "")
            album = item.get("album_name", "")

            # Format similarity percentage
            similarity_text = f"{similarity:.1f}%" if similarity >= 0 else ""

            # Create tree item with all columns
            child_item = QTreeWidgetItem(
                [
                    "",  # Column 0: Checkbox
                    "⭐" if is_best else "",  # Column 1: Best
                    filename,  # Column 2: Filename/Folder
                    artist,  # Column 3: Artist
                    album,  # Column 4: Album
                    directory,  # Column 5: Path
                    f"{size_mb:.1f} MB",  # Column 6: Size
                    quality,  # Column 7: Quality
                    similarity_text,  # Column 8: Similarity
                ],
            )
            # Center align the star emoji in column 1
            child_item.setTextAlignment(1, Qt.AlignmentFlag.AlignCenter)

            # Set tooltips for all columns to show full text
            child_item.setToolTip(2, filename)  # Filename
            child_item.setToolTip(3, artist)  # Artist
            child_item.setToolTip(4, album)  # Album
            child_item.setToolTip(
                5, self._format_path_tooltip(path)
            )  # Path (custom format)
            child_item.setToolTip(6, f"{size_mb:.1f} MB")  # Size
            child_item.setToolTip(7, quality)  # Quality
            child_item.setToolTip(8, similarity_text)  # Similarity

            # Check recommended items by default
            recommended = item.get("recommended_action") == "delete"
            child_item.setCheckState(
                0, Qt.CheckState.Checked if recommended else Qt.CheckState.Unchecked
            )

            # Store quality score in item for sorting
            child_item.setData(0, Qt.ItemDataRole.UserRole, quality_score)

            # Insert item in sorted position (highest quality first)
            insert_index = 0
            for i in range(group_item.childCount()):
                existing_item = group_item.child(i)
                existing_quality = existing_item.data(0, Qt.ItemDataRole.UserRole)
                if quality_score > existing_quality:
                    insert_index = i
                    break
                insert_index = i + 1

            group_item.insertChild(insert_index, child_item)

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
                # Reconstruct full path from filename and directory
                filename = item.text(2)  # Column 2 is Filename
                directory = item.text(3)  # Column 3 is Path
                path = str(Path(directory) / filename)
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
                    # Reconstruct full path from filename and directory
                    filename = item.text(2)  # Column 2 is Filename
                    directory = item.text(5)  # Column 5 is Path
                    path = str(Path(directory) / filename)
                    items_to_stage.append((path, item))

        if not items_to_stage:
            QMessageBox.information(self, "No Selection", "No items selected to stage.")
            return

        # Move to staging pane
        staging_tree: QTreeWidget = self.ui.stagingTree  # type: ignore[attr-defined]
        for path, item in items_to_stage:
            # Add to staging tree (include all 9 columns)
            staging_item = QTreeWidgetItem(
                staging_tree,
                [
                    "",  # Column 0: Checkbox
                    item.text(1),  # Column 1: Best (⭐ or empty)
                    item.text(2),  # Column 2: Filename
                    item.text(3),  # Column 3: Artist
                    item.text(4),  # Column 4: Album
                    item.text(5),  # Column 5: Path
                    item.text(6),  # Column 6: Size
                    item.text(7),  # Column 7: Quality
                    item.text(8),  # Column 8: Similarity
                ],
            )
            # Center align the star emoji in column 1
            staging_item.setTextAlignment(1, Qt.AlignmentFlag.AlignCenter)
            staging_item.setCheckState(0, Qt.CheckState.Unchecked)

            # Set tooltips for all columns to show full text
            staging_item.setToolTip(2, item.text(2))  # Filename
            staging_item.setToolTip(3, item.text(3))  # Artist
            staging_item.setToolTip(4, item.text(4))  # Album
            staging_item.setToolTip(5, self._format_path_tooltip(path))  # Path (custom)
            staging_item.setToolTip(6, item.text(6))  # Size
            staging_item.setToolTip(7, item.text(7))  # Quality
            staging_item.setToolTip(8, item.text(8))  # Similarity

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
                # Reconstruct full path from filename and directory
                filename = item.text(2)  # Column 2 is Filename
                directory = item.text(3)  # Column 3 is Path
                path = str(Path(directory) / filename)
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
            # Reconstruct full path from filename and directory
            filename = item.text(2)  # Column 2 is Filename
            directory = item.text(3)  # Column 3 is Path
            path = str(Path(directory) / filename)
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
                        "",  # Column 0: Checkbox
                        staging_item.text(1),  # Column 1: Best (⭐ or empty)
                        staging_item.text(2),  # Column 2: Filename
                        staging_item.text(3),  # Column 3: Artist
                        staging_item.text(4),  # Column 4: Album
                        staging_item.text(5),  # Column 5: Path
                        staging_item.text(6),  # Column 6: Size
                        staging_item.text(7),  # Column 7: Quality
                        staging_item.text(8),  # Column 8: Similarity
                    ],
                )
                # Center align the star emoji in column 1
                results_item.setTextAlignment(1, Qt.AlignmentFlag.AlignCenter)
                results_item.setCheckState(0, Qt.CheckState.Unchecked)

                # Set tooltips for all columns to show full text
                results_item.setToolTip(2, staging_item.text(2))  # Filename
                results_item.setToolTip(3, staging_item.text(3))  # Artist
                results_item.setToolTip(4, staging_item.text(4))  # Album
                results_item.setToolTip(5, self._format_path_tooltip(path))  # Path
                results_item.setToolTip(6, staging_item.text(6))  # Size
                results_item.setToolTip(7, staging_item.text(7))  # Quality
                results_item.setToolTip(8, staging_item.text(8))  # Similarity
            else:
                metadata = self.item_metadata[path]
                group_item = metadata["group_item"]

                # Get original data to restore similarity and best status
                original_data = self.staging_data.get(path, {})
                is_best = original_data.get("is_best", False)
                similarity = original_data.get("similarity_to_best", 0)

                results_item = QTreeWidgetItem(
                    [
                        "",  # Column 0: Checkbox
                        "⭐" if is_best else "",  # Column 1: Best
                        staging_item.text(2),  # Column 2: Filename
                        staging_item.text(3),  # Column 3: Artist
                        staging_item.text(4),  # Column 4: Album
                        staging_item.text(5),  # Column 5: Path
                        staging_item.text(6),  # Column 6: Size
                        staging_item.text(7),  # Column 7: Quality
                        f"{similarity:.1f}%" if similarity > 0 else "",  # Col 8
                    ],
                )

                # Add as child of group (append to end is safer than trying to
                # restore exact position when other items may still be in the group)
                group_item.addChild(results_item)

                # Center align the star emoji in column 1
                results_item.setTextAlignment(1, Qt.AlignmentFlag.AlignCenter)

                # Set tooltips for all columns to show full text
                results_item.setToolTip(2, staging_item.text(2))  # Filename
                results_item.setToolTip(3, staging_item.text(3))  # Artist
                results_item.setToolTip(4, staging_item.text(4))  # Album
                results_item.setToolTip(5, self._format_path_tooltip(path))  # Path
                results_item.setToolTip(6, staging_item.text(6))  # Size
                results_item.setToolTip(7, staging_item.text(7))  # Quality
                similarity_text = f"{similarity:.1f}%" if similarity > 0 else ""
                results_item.setToolTip(8, similarity_text)  # Similarity

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

    def on_results_item_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        """Handle results tree item clicked - toggle expand/collapse on single click."""
        # Only handle clicks on group headers (items with children)
        if item.childCount() > 0:
            # Toggle expanded state
            item.setExpanded(not item.isExpanded())

    def on_item_expanded(self, item: QTreeWidgetItem) -> None:
        """Handle item expanded - change arrow to down."""
        text = item.text(0)
        if text.startswith("▶ "):
            item.setText(0, text.replace("▶ ", "▼ ", 1))

    def on_item_collapsed(self, item: QTreeWidgetItem) -> None:
        """Handle item collapsed - change arrow to right."""
        text = item.text(0)
        if text.startswith("▼ "):
            item.setText(0, text.replace("▼ ", "▶ ", 1))

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

    def on_results_context_menu(self, position) -> None:
        """Show context menu for results tree items."""
        from PySide6.QtWidgets import QMenu

        results_tree: QTreeWidget = self.ui.resultsTree  # type: ignore[attr-defined]
        item = results_tree.itemAt(position)

        if item is None or item.childCount() > 0:
            # No item or group header - don't show menu
            return

        # Get the path from the item
        filename = item.text(2)  # Column 2 is Filename
        directory = item.text(5)  # Column 5 is Path
        path = str(Path(directory) / filename)

        # Check if we have data for this item
        if path not in self.results_data:
            return

        # Create context menu
        menu = QMenu(self)
        properties_action = QAction("Show Properties...", self)
        properties_action.triggered.connect(
            lambda: self.show_item_properties(path, self.results_data)
        )
        menu.addAction(properties_action)

        # Show menu at cursor position
        menu.exec(results_tree.viewport().mapToGlobal(position))

    def on_staging_context_menu(self, position) -> None:
        """Show context menu for staging tree items."""
        from PySide6.QtWidgets import QMenu

        staging_tree: QTreeWidget = self.ui.stagingTree  # type: ignore[attr-defined]
        item = staging_tree.itemAt(position)

        if item is None:
            return

        # Get the path from the item
        filename = item.text(2)  # Column 2 is Filename
        directory = item.text(5)  # Column 5 is Path
        path = str(Path(directory) / filename)

        # Check if we have data for this item
        if path not in self.staging_data:
            return

        # Create context menu
        menu = QMenu(self)
        properties_action = QAction("Show Properties...", self)
        properties_action.triggered.connect(
            lambda: self.show_item_properties(path, self.staging_data)
        )
        menu.addAction(properties_action)

        # Show menu at cursor position
        menu.exec(staging_tree.viewport().mapToGlobal(position))

    def show_item_properties(
        self, path: str, data_dict: Dict[str, Dict[str, Any]]
    ) -> None:
        """Show properties dialog for an item.

        Args:
            path: Full path to the item
            data_dict: Dictionary containing item data (results_data or staging_data)
        """
        if path in data_dict:
            item_data = data_dict[path]
            dialog = ItemPropertiesDialog(item_data, self)
            dialog.exec()
