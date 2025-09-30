# Claude Instructions for duperscooper

## Project Overview

**duperscooper** is a Python CLI application that finds duplicate audio files
recursively within specified paths. It uses Chromaprint/AcoustID fingerprinting
to detect similar audio content across different formats, bitrates, and sample
rates, or exact byte-matching for identical files.

## Code Style & Standards

### Python Conventions

- **Formatting**: Black with 88-character line length
- **Linting**: Ruff with comprehensive rules, auto-fixes enabled
- **Type Hints**: Required for all function signatures (MyPy enforced)
- **Imports**: Organized by Ruff (stdlib → third-party → local)
- **Docstrings**: Use for public functions/classes; focus on complex logic

### Quality Commands

```bash
black src/ tests/                    # Format code
ruff check --fix src/ tests/         # Lint and auto-fix
mypy src/                            # Type check
pytest tests/ -v                     # Run tests
pytest tests/ --cov=duperscooper     # Run with coverage
```

## Architecture

### Module Structure

```text
src/duperscooper/
├── __init__.py       # Package metadata, version
├── __main__.py       # CLI interface (argparse), output formatting
├── hasher.py         # AudioHasher: perceptual & exact hashing
└── finder.py         # DuplicateFinder: search logic
                      # DuplicateManager: file operations
```

### Key Components

#### AudioHasher (hasher.py)

- `is_audio_file()`: Check if file extension is supported
- `compute_file_hash()`: SHA256 for exact matching
- `compute_audio_hash()`: Chromaprint fingerprint for perceptual matching
- `get_audio_metadata()`: Extract duration, channels, sample rate
- **Caching**: Stores file hash → perceptual hash mappings in
  `~/.config/duperscooper/hashes.json` to avoid re-fingerprinting unchanged
  files on subsequent runs

#### DuplicateFinder (finder.py)

- `find_audio_files()`: Recursive file discovery
- `find_duplicates()`: Hash all files, group by hash
- Handles errors gracefully, tracks error count

#### DuplicateManager (finder.py)

- `interactive_delete()`: User-driven duplicate removal
- `format_file_size()`: Human-readable size strings
- `get_file_info()`: File metadata for display

## Development Guidelines

### Adding Features

1. **New audio formats**: Add extension to `AudioHasher.SUPPORTED_FORMATS`
2. **New hash algorithms**: Extend `compute_audio_hash()` with new case
3. **New output formats**: Add function to `__main__.py`, update argparse choices
4. **New CLI options**: Add to `parse_args()`, pass through to classes

### Code Changes

- **Never** add wildcard imports (`from x import *`)
- **Always** add type hints to new functions
- **Always** handle exceptions in file/audio operations
- **Update tests** when changing public interfaces
- **Format code** before committing

### Testing

- Use `pytest` with markers: `@pytest.mark.integration`, `@pytest.mark.slow`
- Mock file I/O and audio processing for unit tests
- Test edge cases: empty files, corrupted audio, permission errors
- Run `pytest --cov` to verify coverage

## Dependencies

### Core Runtime

- `tqdm`: Progress bars

Note: Audio fingerprinting is done by calling the `fpcalc` binary directly
instead of using Python libraries, for Python 3.13 compatibility.

### Development

- `black`, `ruff`, `mypy`: Code quality
- `pytest`, `pytest-cov`: Testing

### Adding Dependencies

1. Add to `pyproject.toml` `dependencies` list
2. Pin version in `requirements.txt`
3. Document purpose in this file
4. Test compatibility with Python 3.8+

## Common Tasks

### Running the Application

```bash
# Development mode (from project root)
python -m duperscooper /path/to/music --verbose

# Installed mode
pip install -e .
duperscooper /path/to/music
```

### Example Usage

```bash
# Find duplicates with progress (default, min 1MB files)
duperscooper ~/Music

# Find all files including small ones, output as JSON
duperscooper ~/Music --min-size 0 --output json

# Exact byte matching instead of perceptual
duperscooper ~/Music --algorithm exact

# Interactive deletion mode without progress output
duperscooper ~/Music --delete-duplicates --no-progress

# Multiple paths, CSV output
duperscooper ~/Music ~/Downloads --output csv > duplicates.csv

# Disable cache (compute all hashes from scratch)
duperscooper ~/Music --no-cache

# Clear the hash cache
duperscooper --clear-cache
```

### Debugging

- Progress output shown by default; use `--no-progress` to disable
- Check stderr for error messages (preserved separately)
- Add `print()` statements in code (not in production)
- Use `pytest -v -s` to see print output in tests

## Error Handling

### Expected Behaviors

- **Missing paths**: Log error, continue with other paths
- **Corrupted audio**: Log error, skip file, continue
- **Permission denied**: Log error, skip file, continue
- **Keyboard interrupt**: Exit gracefully with message
- All errors increment `error_count`, reported at end

### Exit Codes

- `0`: Success (no duplicates found)
- `1`: Error during execution
- `2`: Success (duplicates found)
- `130`: User cancelled (Ctrl+C)

## Performance Considerations

### Perceptual Hashing (Chromaprint)

- Uses Chromaprint/AcoustID fingerprinting algorithm
- Analyzes spectral characteristics over time (frequency domain)
- Robust to format, bitrate, and sample rate differences
- Matches 128kbps MP3 vs 320kbps MP3 vs FLAC reliably
- Duration-aware: includes track length in fingerprint
- Slower than exact hashing but highly accurate for similar audio

### Optimization Tips

- **Caching**: Perceptual hashes are cached in `~/.config/duperscooper/hashes.json`
  keyed by file hash (SHA256), so unchanged files skip fingerprinting on
  subsequent runs
- **Cache Management**:
  - Clear cache: `duperscooper --clear-cache`
  - Disable cache: `duperscooper ~/Music --no-cache`
  - Cache location: `$XDG_CONFIG_HOME/duperscooper/hashes.json`
    (defaults to `~/.config/duperscooper/hashes.json`)
- Use `--algorithm exact` for faster exact-match-only detection
- Use `--min-size` to skip small files (reduce processing)
- Process large libraries in batches if memory constrained

## Future Enhancements

### Potential Features

- Parallel hashing with multiprocessing
- Similarity threshold tuning (currently binary match)
- Preview audio before deletion
- Dry-run mode for `--delete-duplicates`
- GUI interface
- Automatic "best quality" file selection
- Cache management commands (clear, show stats, etc.)

### Code Improvements

- More comprehensive test coverage (integration tests)
- Benchmark Chromaprint performance on large libraries
- Support for more exotic audio formats (AIFF, APE, etc.)
- Similarity threshold tuning (allow near-matches with configurable tolerance)
- Optional fuzzy duration matching (±1 second tolerance)

## Git & GitHub

### Commit Guidelines

- Reference issues in commit messages: "Fixes #123", "Implements #456"
- Use conventional commits: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`
- Format code before committing
- Run tests before pushing

### Branch Strategy

- `main`: Stable releases
- Feature branches: `add-feature-name` or `fix-bug-description`
- Keep commits atomic and well-described

## Troubleshooting

### Common Issues

**Import errors**: Ensure virtual environment activated and dependencies
installed

```bash
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
```

**Chromaprint errors**: `pyacoustid` requires the `fpcalc` binary and FFmpeg

```bash
# Ubuntu/Debian
sudo apt install libchromaprint-tools

# macOS
brew install chromaprint

# Verify installation
fpcalc --version
```

**Type checking failures**: Run `mypy src/` and fix reported issues

**Test failures**: Ensure all dependencies installed, check test environment

## Notes for Claude

- **Always format code** with Black before presenting to user
- **Always run linting** with Ruff when making changes
- **Prefer editing** existing files over creating new ones
- **Test changes** when modifying core logic
- **Document breaking changes** in commit messages
- **Ask before** installing system packages or major refactors
- **Reference files** using markdown links: `[file.py](src/duperscooper/file.py)`
