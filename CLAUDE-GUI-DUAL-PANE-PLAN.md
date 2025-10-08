# Dual-Pane Scan & Stage Interface Plan

## Overview

Replace the current 3-tab workflow (Scan → Results → Staging) with a single dual-pane interface that combines scanning, staging, and deletion in one view.

## Current Problems

1. **Too many steps**: Scan → Review Results → Stage → Review Staging → Delete
2. **Lost context**: Switching tabs loses visual context of what's selected
3. **Can't stage during scan**: Must wait for scan to complete before staging
4. **Confusing workflow**: Users unsure when files actually get deleted

## Proposed Solution: 3-Pane Interface

### Layout (3 Panes: Paths + Results + Staging)

```
┌─────────────────────────────────────────────────────────────┐
│  SCAN PATHS (Top Pane - Full Width)                         │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ /home/user/Music                                [✖]    │ │
│  │ /home/user/Downloads/Albums                     [✖]    │ │
│  └────────────────────────────────────────────────────────┘ │
│  [+ Add Path] [Browse] [Track Mode ▼] [▶ Start Scan]       │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────────────┐       ┌──────────────────────┐   │
│  │  SCAN RESULTS        │       │  STAGED FOR DELETION │   │
│  │  (Duplicates Found)  │       │  (Ready to Delete)   │   │
│  ├──────────────────────┤       ├──────────────────────┤   │
│  │                      │       │                      │   │
│  │  ☐ Group 1: Album A  │       │  ☑ Group 3: Album X  │   │
│  │    ☐ Copy 1 (FLAC)   │       │    ☑ Copy 1 (MP3)    │   │
│  │    ☐ Copy 2 (MP3)    │       │    ☑ Copy 2 (AAC)    │   │
│  │                      │       │                      │   │
│  │  ☐ Group 2: Track B  │       │  ☑ Track Y (low)     │   │
│  │    ☐ Best (320kbps)  │       │    ☑ Copy 1 (AAC)    │   │
│  │    ☐ Dup (128kbps)   │  >>>  │                      │   │
│  │                      │  <<<  │  Total: 2 items      │   │
│  │  [Scanning: 45%]     │       │  Size: 45.2 MB       │   │
│  │  1,234 files scanned │       │                      │   │
│  │                      │       │  [🗑️ Delete All]     │   │
│  └──────────────────────┘       └──────────────────────┘   │
│                                                              │
│  [Select All] [Deselect All] [Stage Selected >>]            │
│               [<< Unstage Selected] [Clear Staging]         │
│                                                              │
│  Status: Scanning... 1,234 files processed | 15 groups found│
└─────────────────────────────────────────────────────────────┘
```

**Note:** The UI has 3 distinct panes:
1. **Top pane (full width)**: Scan paths list with controls
2. **Bottom-left pane**: Scan results (duplicates found)
3. **Bottom-right pane**: Staged for deletion

## Workflow Steps

### Step 1: Configure & Start Scan

1. User selects path(s) and mode (Track/Album)
2. Clicks "▶ Start Scan"
3. Both panes are visible:
   - Left pane: Empty, shows "Scanning..." progress
   - Right pane: Empty staging area

### Step 2: Real-time Results & Staging

**As scan runs:**
- Duplicate groups appear in left pane in real-time
- User can immediately select and stage items
- Staged items move to right pane
- Scan continues in background

**User actions:**
- Select items in left pane → Click "Stage >>" → Items move to right pane
- Select items in right pane → Click "<< Unstage" → Items move back to left pane
- Can stage/unstage while scan is still running

### Step 3: Delete Staged Items

1. Review staged items in right pane
2. Click "🗑️ Delete All" button
3. Confirmation dialog appears
4. Files moved to `.deletedByDuperscooper/`
5. Staging pane cleared
6. Can continue staging more items from left pane

## Technical Implementation

### New Components

#### 1. `dual_pane_widget.ui` (Qt Designer)
```xml
<QSplitter orientation="horizontal">
  <QWidget name="resultsPane">
    <QTreeWidget name="resultsTree"/>
    <QLabel name="resultsSummary"/>
  </QWidget>

  <QWidget name="stagingPane">
    <QTreeWidget name="stagingTree"/>
    <QLabel name="stagingSummary"/>
    <QPushButton name="deleteAllButton"/>
  </QWidget>
</QSplitter>

<QHBoxLayout name="buttonBar">
  <QPushButton name="selectAllButton"/>
  <QPushButton name="deselectAllButton"/>
  <QPushButton name="stageButton"/>
  <QPushButton name="unstageButton"/>
  <QPushButton name="clearStagingButton"/>
</QHBoxLayout>
```

#### 2. `dual_pane_viewer.py` (Python)
```python
class DualPaneViewer(QWidget):
    """Dual-pane scan results and staging interface."""

    deletion_requested = Signal(list)  # Emit when Delete All clicked

    def __init__(self):
        # Two tree widgets: results_tree, staging_tree
        # StagingQueue for tracking staged items
        pass

    def add_duplicate_group(self, group_data):
        """Add group to results pane (real-time during scan)."""
        # Add to results_tree
        # Auto-check items marked for deletion
        pass

    def stage_selected(self):
        """Move selected items from results to staging pane."""
        # Get selected from results_tree
        # Add to staging_tree
        # Remove from results_tree
        # Add to StagingQueue
        pass

    def unstage_selected(self):
        """Move selected items from staging to results pane."""
        # Get selected from staging_tree
        # Add to results_tree
        # Remove from staging_tree
        # Remove from StagingQueue
        pass

    def delete_all_staged(self):
        """Delete all items in staging pane."""
        # Show confirmation dialog
        # Call backend_interface.stage_items()
        # Clear staging_tree and StagingQueue
        pass
```

#### 3. Backend Integration

**Modify `scanner_thread.py`:**
```python
class ScannerThread(QThread):
    group_found = Signal(dict)  # NEW: Emit each group as found

    def run(self):
        # ... existing scan logic ...
        for group in duplicate_groups:
            self.group_found.emit(group)  # Emit real-time
```

**Connect in main window:**
```python
self.scanner.group_found.connect(self.dual_pane.add_duplicate_group)
```

### Data Flow

```
1. Scan starts
   └→ ScannerThread emits group_found signals
      └→ DualPaneViewer.add_duplicate_group()
         └→ Items appear in results_tree (left pane)

2. User stages items
   └→ Click "Stage >>" button
      └→ DualPaneViewer.stage_selected()
         ├→ Remove from results_tree
         ├→ Add to staging_tree (right pane)
         └→ Add to StagingQueue

3. User deletes staged
   └→ Click "Delete All" button
      └→ DualPaneViewer.delete_all_staged()
         ├→ Show confirmation dialog
         ├→ Call backend_interface.stage_items()
         ├→ Clear staging_tree
         └→ Clear StagingQueue
```

## Key Features

### Real-time Scanning
- Groups appear in results pane as they're found
- Progress bar shows scan status
- Can stage items before scan completes

### Bidirectional Movement
- "Stage >>" moves results → staging
- "<< Unstage" moves staging → results
- Visual feedback shows items moving between panes

### Clear State Management
- Left pane = duplicates found (not deleted)
- Right pane = queued for deletion (not deleted yet)
- "Delete All" = actual deletion happens here

### Simplified UX
- One tab instead of three
- See both results and staging at once
- Immediate feedback on actions
- No confusion about when deletion happens

## Migration Plan

### Phase 1: Build Dual-Pane UI
1. Create `dual_pane_widget.ui` in Qt Designer
2. Implement `DualPaneViewer` class
3. Add to main window as new tab

### Phase 2: Real-time Scan Integration
1. Modify `ScannerThread` to emit `group_found` signal
2. Connect to `add_duplicate_group()` method
3. Test real-time updates during scan

### Phase 3: Staging Logic
1. Implement `stage_selected()` and `unstage_selected()`
2. Integrate with `StagingQueue`
3. Add visual feedback for movement

### Phase 4: Deletion Integration
1. Implement `delete_all_staged()` with confirmation
2. Connect to existing `stage_items()` backend
3. Test complete workflow

### Phase 5: Cleanup
1. Mark old tabs as deprecated
2. Add migration notice
3. Eventually remove old 3-tab workflow

## Benefits

### User Experience
- ✅ Simpler workflow (1 tab vs 3 tabs)
- ✅ Visual context maintained (see both panes)
- ✅ Can stage while scanning (real-time)
- ✅ Clear distinction (results vs staged)
- ✅ Easy to undo (unstage items)

### Technical
- ✅ Reuses existing `StagingQueue`
- ✅ Reuses existing `stage_items()` backend
- ✅ Minimal changes to scan logic
- ✅ Can coexist with old UI during migration

### Performance
- ✅ Real-time updates (no waiting for scan)
- ✅ Incremental staging (don't have to stage all at once)
- ✅ Better responsiveness (async scan + staging)

## Open Questions

1. **What happens to scan results when staged?**
   - Option A: Remove from left pane completely
   - Option B: Gray out but keep visible
   - **Decision: Remove (cleaner UI)**

2. **Show empty groups?**
   - If all items in a group are staged, hide the group?
   - **Decision: Yes, hide empty groups**

3. **Default selections?**
   - Auto-select recommended items?
   - **Decision: No, let user choose (prevent accidents)**

4. **Scan completion behavior?**
   - Auto-switch to staging pane when scan done?
   - **Decision: No, stay on current view**

## Testing Checklist

- [ ] Start scan, verify groups appear in real-time
- [ ] Stage items while scan running
- [ ] Unstage items back to results
- [ ] Delete staged items (confirm dialog)
- [ ] Verify files moved to `.deletedByDuperscooper/`
- [ ] Clear staging without deleting
- [ ] Handle empty groups correctly
- [ ] Test with both track and album modes
- [ ] Test with large scan results (1000+ groups)
- [ ] Verify selection state persists during stage/unstage

## Future Enhancements

1. **Drag & Drop**: Drag items between panes instead of buttons
2. **Batch Operations**: Right-click → "Stage entire group"
3. **Filters**: Filter results pane by format, quality, size
4. **Search**: Search in results/staging panes
5. **Preview**: Audio preview before deletion
6. **Undo Stack**: Multi-level undo for staging operations
