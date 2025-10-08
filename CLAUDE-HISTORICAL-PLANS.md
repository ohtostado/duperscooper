# Historical Development Plans - duperscooper

**Note:** This file contains completed features and historical context. Only read when explicitly instructed or when researching past decisions.

## Completed Features (All Merged)

### Pre-GUI Backend Features ✅ COMPLETE

**Goal:** Implement essential deletion infrastructure before GUI development.

#### Feature 1: Staging Folder Deletion System (PR #9)
- UUID-based staging in `.deletedByDuperscooper/<uuid>/` directories
- Manifest files with SHA256, fingerprints, restoration tracking
- Track-level restoration tracking
- Custom restoration location via `--restore-to`
- Batch archival to `.restored/`
- CLI: `--stage-album`, `--list-deleted`, `--restore`, `--restore-interactive`, `--empty-deleted`

#### Feature 2: JSON Ingestion / Apply Rules Mode (PR #10)
- `src/duperscooper/rules.py` (RuleEngine, Rule, RuleCondition)
- `src/duperscooper/apply.py` (ScanResultLoader, ApplyEngine)
- Built-in strategies: `eliminate-duplicates`, `keep-lossless`, `keep-format`, `custom`
- CLI: `--apply-rules FILE --strategy STRATEGY [--execute]`

#### Features 3-6: Safety & Parity (PR #11)
- **Dry-Run Mode:** Default for `--apply-rules`, requires `--execute`
- **Non-Interactive Mode:** `--yes` / `-y` flag for automation
- **recommended_action in JSON:** Pre-selection support for GUI
- **Interactive Album Deletion:** `--delete-duplicate-albums` fully functional

#### Feature 7: List/Restore/Empty Commands (PR #9)
- `--list-deleted`, `--restore`, `--restore-interactive`, `--restore-to`
- `--empty-deleted`, `--keep-last N`, `--older-than DAYS`

### GUI Phase 1: Foundation (PR #12) ✅ COMPLETE

**Implemented:**
- Clean directory structure in `src/duperscooper_gui/`
- Main window with tabbed interface (Scan/Results/Staging)
- Qt Designer `.ui` files for visual editing
- Backend interface via subprocess wrapper
- Scan configuration UI (paths, mode, algorithm, threshold, workers)
- Progress tracking infrastructure
- PySide6 dependencies and installation

### GUI Phase 2: Results Viewer (PR #13, PR #16) ✅ COMPLETE

**Implemented:**
- Complete data model for scan results (track and album modes)
- Tree view with 8 columns (Select, Path, Album, Artist, Size, Quality, Similarity, Action)
- Checkboxes for duplicate groups with pre-selection
- Track-level metadata display (album/artist from file tags)
- Quality information display with color coding
- Selection controls (Select All/None/Recommended)
- Deletion preview dialog
- Real-time selection statistics
- Visual highlighting of best quality items
- Platform-specific settings system
- Customizable colors via TOML config

**Features:**
- Smart pre-selection from `recommended_action`
- Best quality items highlighted in bold green
- Color-coded similarity: Dark green (≥99%), Green (≥97%), Orange (≥95%), Red (<95%)
- Icons: 🔊 Audio files, 📁 Folders, 🔍 Search, 💿 Albums
- Comprehensive tooltips with full metadata
- Selection statistics with potential savings

### Album Mode Default (PR #16) ✅ COMPLETE

**Implemented:**
1. **Album Mode as Default**
   - CLI: `--album-mode` default=True, added `--track-mode` flag
   - GUI: Album mode selected by default in dropdown
   - Backend interface updated to use `--track-mode` when disabled

2. **Track-Level Metadata in Album Mode**
   - Display individual track metadata (not aggregated album metadata)
   - Added `AudioHasher.get_audio_tags()` for ffprobe extraction
   - Shows album/artist from actual file tags
   - Helps identify matches with differing metadata

3. **GUI Settings System**
   - Created `src/duperscooper_gui/config/` module
   - Platform-specific config paths (Linux/macOS/Windows)
   - Auto-generated from template on first run
   - Human-editable TOML format

4. **Configuration Sections**
   - `[colors]`: Group headers, best quality, similarity indicators
   - `[scan]`: Default mode, algorithm, threshold, workers
   - `[ui]`: Window size, auto-expand groups

## Future Enhancement Ideas (Low Priority)

### Album Mode Future Phases

**Fuzzy Tag Matching:**
- Use Levenshtein distance for album/artist name matching
- Example: "The Beatles" vs "Beatles" or "Led Zeppelin" vs "Led Zepplin"
- Match against canonical albums within close edit distance
- Configurable threshold for fuzzy matching sensitivity

**Strict Fingerprint Mode:**
- Add `--strict` flag to ignore all metadata completely
- Use only acoustic fingerprint matching with high threshold (99.5%)
- Configurable with `--strict-threshold` option
- Quality control: verify MB ID matches are actually the same recording

### General Enhancement Ideas

- Parallel hashing with multiprocessing
- Preview audio before deletion
- Support for more exotic audio formats (AIFF, APE, etc.)
- Optional fuzzy duration matching (±1 second tolerance)
- More comprehensive test coverage (integration tests)
- Benchmark Chromaprint performance on large libraries

### GUI Feature Wishlist (Completed Items)

1. ✅ Fixed unreadable group headers (white on light grey)
2. ✅ Removed " (avg)" from quality data, added to column header
3. ✅ Removed "results viewer coming soon" placeholder
4. ✅ Added Album and Artist columns with metadata

### GUI Feature Wishlist (Future Items)

**High Priority:**
5. Settings/preferences/options panel (OS-aware menu placement)
6. Cross-platform support (Linux, macOS, Windows)
7. Track deleted files in current session for easy restoration
8. Recall deletions from previous sessions (manifest tracking)

**Medium Priority:**
9. Open log output in scrollable window or external program
10. Save log output to file
11. Show/hide columns (protect critical columns)
12. Resize and reorder columns
13. Save table state (columns, order, widths) with reset to defaults
14. Speaker icon should match row text color
15. Remember window size and position

**Low Priority:**
16. Right-click properties view (location, size, SHA, fingerprint, metadata)
17. Click speaker icon to play/pause audio
18. "Deselect Lossless" button in results viewer
19. Drag-and-drop for adding scan paths
20. Dark mode support
21. Keyboard shortcuts

## Test Environment

### Track Mode Tests
- **Test Files:** `test-audio/` directory
  - test.flac (44.1kHz 16bit, 30.9 MB)
  - 14 MP3 variants (CBR: 64-320kbps, VBR: V2-V9)
  - All successfully detected as duplicates

### Album Mode Tests
- **Test Folders:** `test-albums/` directory
  - 21 album folders total
  - 16 baseline albums (AlbumA × 8, AlbumB × 8)
  - 5 test scenario folders (mixed MB IDs, ID3-only, partial albums)
  - All scenarios verified working correctly

**Important:** Do NOT modify the existing `test-albums/` directory structure. Create new test albums in separate directories (e.g., `temp-test-albums/`).

## Historical Session Notes

### Session: Staging Folder Deletion & Docker (Oct 4, 2025)
- **PR #9 Merged:** Feature 1 Complete - Staging Folder Deletion System

### Session: GUI Foundation & Results Viewer (Oct 4, 2025)
- **PR #12 Merged:** GUI Foundation
- **PR #13 Merged:** Results Viewer Implementation

### Session: Enhanced Results Viewer & Settings System (Oct 5, 2025)
- **PR #16 Merged:** Enhanced results viewer, album mode default, GUI settings

### Session: Dual-Pane Viewer (Oct 8, 2025)
- **PR #18 Created:** Dual-pane interface foundation (WIP)
- Fixed all mypy type errors in dual_pane_viewer.py
- Removed obsolete UI files (main_window.ui, results_widget.ui, results_viewer.py)
- Created planning document: CLAUDE-GUI-DUAL-PANE-PLAN.md
