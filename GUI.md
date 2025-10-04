# duperscooper GUI

PySide6/Qt graphical interface for duperscooper.

## Installation

### Install GUI Dependencies

```bash
# Option 1: Install with pip
pip install -r requirements-gui.txt

# Option 2: Install as optional dependency
pip install -e ".[gui]"
```

### Verify Installation

```bash
# Check if PySide6 is installed
python -c "import PySide6; print(PySide6.__version__)"

# Should output something like: 6.6.0
```

## Usage

### Launch GUI

```bash
# Option 1: Via installed script
duperscooper-gui

# Option 2: Via Python module
python -m duperscooper_gui
```

### Features

**Scan Tab:**
- Add multiple paths to scan
- Configure scan mode (Track or Album)
- Choose algorithm (Perceptual or Exact)
- Adjust similarity threshold
- Set worker thread count
- View real-time scan progress

**Results Tab:** (Coming Soon)
- View duplicate groups
- See quality information
- Select files/albums for deletion
- Pre-selected based on recommended_action

**Staging Tab:** (Coming Soon)
- View staged deletion batches
- Restore files/albums
- Permanently delete batches
- Configure retention policies

## Editing UI Files

The GUI uses Qt Designer `.ui` files for layout. You can edit these visually!

### Install Qt Designer

Qt Designer is included with PySide6:

```bash
# Launch Qt Designer
pyside6-designer

# Or on some systems:
designer
```

### Open UI Files

1. Launch Qt Designer
2. File → Open
3. Navigate to `src/duperscooper_gui/ui/`
4. Open any `.ui` file (e.g., `main_window.ui`)

### Edit Visually

- Drag and drop widgets from the Widget Box
- Set properties in the Property Editor
- Arrange layouts visually
- Preview the interface (Form → Preview)
- Save changes (File → Save)

### Available UI Files

- `main_window.ui` - Main application window with tabs
- More coming soon...

## Architecture

```
src/duperscooper_gui/
├── __init__.py           # Package metadata
├── __main__.py           # GUI entry point
├── ui/                   # Qt Designer .ui files (editable in Designer)
│   └── main_window.ui
├── windows/              # Python UI loaders and logic
│   ├── __init__.py
│   └── main_window.py    # Loads main_window.ui and adds behavior
├── models/               # Data models (coming soon)
│   └── __init__.py
└── utils/                # Helper functions
    ├── __init__.py
    └── backend_interface.py  # CLI subprocess wrapper
```

## Backend Integration

The GUI uses the duperscooper CLI as a backend via subprocess calls. This approach:

- ✅ Keeps GUI and CLI completely separate
- ✅ No code duplication
- ✅ CLI remains fully functional independently
- ✅ All CLI features automatically available to GUI
- ✅ Easy to test and maintain

See `utils/backend_interface.py` for implementation details.

## Development

### Running from Source

```bash
# Install in editable mode with GUI dependencies
pip install -e ".[gui]"

# Launch GUI
python -m duperscooper_gui
```

### Code Quality

```bash
# Format code
black src/duperscooper_gui/

# Lint
ruff check src/duperscooper_gui/

# Type check
mypy src/duperscooper_gui/
```

## Troubleshooting

### Qt Designer not found

```bash
# Find Qt Designer location
python -c "import PySide6; print(PySide6.__path__)"

# Designer is usually in the 'designer' subdirectory
```

### Import errors

Make sure you've installed the GUI dependencies:

```bash
pip install -r requirements-gui.txt
```

### UI file not loading

Check that the path in `main_window.py` correctly points to the `.ui` file:

```python
ui_file = Path(__file__).parent.parent / "ui" / "main_window.ui"
```

## Roadmap

- [ ] Results viewer with duplicate groups
- [ ] Deletion controls with preview
- [ ] Staging management interface
- [ ] Settings dialog for preferences
- [ ] Drag-and-drop for adding paths
- [ ] Dark mode support
- [ ] Persistent settings
