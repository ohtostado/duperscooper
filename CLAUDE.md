# Claude Instructions for duperscooper

## Project Overview

**duperscooper** is a Python CLI application that finds duplicate audio files
recursively within specified paths. It uses fuzzy matching with raw Chromaprint
fingerprints and Hamming distance to detect duplicate audio content across
different formats, bitrates, and encodings. Also supports exact byte-matching
for identical files.

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
├── cache.py          # CacheBackend interface, SQLite/JSON implementations
├── hasher.py         # AudioHasher: perceptual & exact hashing
├── finder.py         # DuplicateFinder: search logic, parallelization
│                     # DuplicateManager: file operations
└── album.py          # Album: dataclass for album metadata
                      # AlbumScanner: album discovery and metadata extraction
                      # AlbumDuplicateFinder: album duplicate detection
```

### Key Components

#### CacheBackend (cache.py)

- `CacheBackend` (Protocol): Interface for cache implementations
- `SQLiteCacheBackend`: Thread-safe SQLite cache with WAL mode
  - Thread-local database connections for concurrent access
  - `get()`, `set()`: Retrieve and store fingerprints
  - `get_stats()`: Return cache hits/misses/size statistics
  - `clear()`: Remove all cache entries
  - `cleanup_old()`: Remove entries older than specified age
- `JSONCacheBackend`: Legacy JSON file cache (sequential only)
- `migrate_json_to_sqlite()`: Auto-migrate legacy JSON cache to SQLite

#### AudioHasher (hasher.py)

- `is_audio_file()`: Check if file extension is supported
- `compute_file_hash()`: SHA256 for exact matching
- `compute_raw_fingerprint()`: Raw Chromaprint fingerprint (list of integers)
- `compute_audio_hash()`: Returns raw fingerprint for perceptual, SHA256 for
  exact
- `hamming_distance()`: Calculate bit-level differences between fingerprints
- `similarity_percentage()`: Calculate similarity % between fingerprints
- `get_audio_metadata()`: Extract codec, sample rate, bit depth, bitrate,
  channels using ffprobe
- `calculate_quality_score()`: Calculate quality score (lossless > lossy,
  higher bitrate/depth > lower)
- `format_audio_info()`: Format metadata as human-readable string (e.g.,
  "FLAC 44.1kHz 16bit", "MP3 CBR 320kbps")
- **Caching**: Uses CacheBackend interface for thread-safe fingerprint storage

#### DuplicateFinder (finder.py)

- `find_audio_files()`: Recursive file discovery
- `find_duplicates()`: Fingerprint files, group by similarity
- `_fingerprint_parallel()`: Parallel fingerprinting with ThreadPoolExecutor
- `_fingerprint_sequential()`: Single-threaded fingerprinting
- `_format_time()`: Format elapsed/ETA times as human-readable strings
- `_group_exact_duplicates()`: Group by exact hash match (preserves
  fingerprints)
- `_group_fuzzy_duplicates()`: Group by fuzzy similarity using Union-Find
  (preserves fingerprints)
- Handles errors gracefully, tracks error count

#### DuplicateManager (finder.py)

- `identify_highest_quality()`: Identify best quality file in duplicate group,
  calculate similarity scores
- `interactive_delete()`: User-driven duplicate removal with quality
  information
- `format_file_size()`: Human-readable size strings
- `get_file_info()`: File metadata for display

#### Album (album.py)

- `Album` (dataclass): Represents an album with metadata and fingerprints
  - Fields: path, tracks, track_count, musicbrainz_albumid, album_name,
    artist_name, total_size, avg_quality_score, fingerprints,
    has_mixed_mb_ids, quality_info

#### AlbumScanner (album.py)

- `scan_albums()`: Discover all albums in given paths
- `extract_album_metadata()`: Extract metadata from all tracks in album
  directory
- `get_musicbrainz_albumid()`: Extract MusicBrainz album ID via ffprobe
- `get_album_tags()`: Extract album name and artist from metadata
- Leverages existing AudioHasher for fingerprint caching
- Non-recursive directory scan (one album = one directory)

#### AlbumDuplicateFinder (album.py)

- `find_duplicates()`: Find duplicate albums using specified strategy
- `_match_by_musicbrainz()`: Group albums by MusicBrainz ID and track count
- `_match_by_fingerprints()`: Group albums by perceptual fingerprint
  similarity using Union-Find
- `album_similarity()`: Calculate similarity percentage between two albums
  (average track-by-track similarity)
- `get_matched_album_info()`: Determine matched album name and artist for a
  duplicate group (uses most common names)
- `calculate_confidence()`: Calculate confidence that an album belongs to the
  matched group
  - MusicBrainz ID match: 100%
  - Album/artist name match + fingerprints: 90-95%
  - Fingerprint similarity only: 80-90%
- Three matching strategies: `auto` (MB + fingerprint fallback),
  `musicbrainz`, `fingerprint`

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

# Update cache (regenerate hashes for files already in cache)
duperscooper ~/Music --update-cache

# Adjust similarity threshold (default 98%)
duperscooper ~/Music --similarity-threshold 95.0

# Clear the hash cache
duperscooper --clear-cache

# Use 16 worker threads for parallel fingerprinting
duperscooper ~/Music --workers 16

# Sequential fingerprinting (single-threaded)
duperscooper ~/Music --workers 1

# Use legacy JSON cache backend instead of SQLite
duperscooper ~/Music --cache-backend json

# Album mode: Find duplicate albums
duperscooper ~/Music --album-mode

# Album mode with MusicBrainz-only matching
duperscooper ~/Music --album-mode --album-match-strategy musicbrainz

# Album mode with fingerprint-only matching
duperscooper ~/Music --album-mode --album-match-strategy fingerprint

# Album mode with JSON output (includes matched album/artist and confidence)
duperscooper ~/Music --album-mode --output json

# Album mode with CSV output (good for GUI integration)
duperscooper ~/Music --album-mode --output csv > duplicate_albums.csv
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

### Fuzzy Perceptual Matching (Default)

- Uses raw Chromaprint fingerprints (list of 32-bit integers)
- Calculates Hamming distance (bit-level differences) between fingerprints
- Groups files with similarity ≥ threshold (default 98%)
- Detects duplicates across all bitrates and formats:
  - 64kbps MP3 ↔ FLAC: ~98.9% similar
  - 128kbps MP3 ↔ FLAC: ~99.5% similar
  - 320kbps MP3 ↔ FLAC: ~99.9% similar
  - All encodings (VBR, CBR) of same source audio match
- Uses Union-Find algorithm for efficient grouping
- O(n²) pairwise comparisons (suitable for libraries up to ~10k files)

### Multithreading & Parallelization

**Thread-Safe Architecture:**

- **SQLite Cache Backend** (default since v0.4.0):
  - Thread-local database connections (one per worker thread)
  - WAL (Write-Ahead Logging) mode for concurrent reads/writes
  - ACID transactions prevent cache corruption
  - Auto-migration from legacy JSON cache

- **Parallel Fingerprinting** (default since v0.4.0):
  - Uses `ThreadPoolExecutor` for concurrent audio processing
  - Default: 8 worker threads (configurable with `--workers`)
  - I/O-bound workload (subprocess calls to `fpcalc` binary)
  - Thread-safe progress tracking with locks
  - Real-time ETA estimation based on average processing time

**Worker Thread Tuning:**

- **Default (8 threads)**: Optimal for most modern systems (4-8+ cores)
- **High-end systems**: Increase for faster processing
  (`--workers 16` or higher)
- **Low-end systems**: Reduce to avoid overhead (`--workers 4`)
- **Sequential mode**: Use `--workers 1` for single-threaded processing
  (useful for debugging)

**Cache Backend Selection:**

- **SQLite** (default, recommended): Thread-safe, efficient, supports
  concurrent access
  - Location: `~/.config/duperscooper/hashes.db`
- **JSON** (legacy): Sequential only, use `--cache-backend json` for
  compatibility
  - Location: `~/.config/duperscooper/hashes.json`

### Optimization Tips

- **Caching**: Perceptual hashes are cached by file hash (SHA256), so
  unchanged files skip fingerprinting on subsequent runs
- **Similarity Threshold**: Adjust `--similarity-threshold` (default 98.0%)
  - Lower threshold (95%) finds more matches but may include false positives
  - Higher threshold (99.5%) only matches very similar encodings
  - Default 98% works well for all common bitrates (64kbps-FLAC)
- **Cache Management**:
  - Clear cache: `duperscooper --clear-cache`
  - Disable cache: `duperscooper ~/Music --no-cache`
  - Update cache: `duperscooper ~/Music --update-cache` (regenerate cached
    hashes)
  - Cache stores raw fingerprints as comma-separated integers
- **Performance**:
  - Use `--algorithm exact` for faster exact-match-only detection (O(n))
  - Perceptual algorithm is O(n²) - suitable for ~10k files max
  - Use `--min-size` to skip small files (reduce processing)
  - Increase `--workers` for faster fingerprinting on multi-core systems
  - For very large libraries (>10k files), consider using `exact` first

## Output Formats

### Quality Detection

All output formats now include quality information for duplicate groups:

- **Text Output** (default): Shows best quality file first with `[Best]` marker, followed by duplicates with similarity percentage
  ```
  [Best] /path/to/file.flac (30.9 MB) - FLAC 44.1kHz 16bit
    ├─ /path/to/file-320.mp3 (13.4 MB) - MP3 CBR 320kbps [99.9% match]
    ├─ /path/to/file-192.mp3 (8.0 MB) - MP3 CBR 192kbps [99.8% match]
  ```

- **JSON Output**: Includes `audio_info`, `quality_score`, `similarity_to_best`, and `is_best` fields
  ```json
  {
    "path": "/path/to/file.flac",
    "audio_info": "FLAC 44.1kHz 16bit",
    "quality_score": 11644.1,
    "similarity_to_best": 100.0,
    "is_best": true
  }
  ```

- **CSV Output**: Adds columns for `audio_info`, `quality_score`, `similarity_to_best`, and `is_best`

- **Interactive Delete**: Shows quality info for each file to help decide which duplicates to keep/delete

### Quality Scoring System

- **Lossless formats** (FLAC, WAV, ALAC, etc.): `10000 + (bit_depth × 100) + (sample_rate / 1000)`
  - Example: 24-bit 96kHz FLAC = 10000 + 2400 + 96 = 12496
- **Lossy formats** (MP3, AAC, OGG, etc.): `bitrate / 1000` (in kbps)
  - Example: 320kbps MP3 = 320

This ensures lossless files always rank higher than lossy, with finer granularity within each category.

### Album Mode Output Formats

Album mode adds matched album/artist identification and confidence scoring:

- **Text Output** (default): Shows matched album/artist at group level, best quality album with `[Best]` marker, confidence percentage with color coding
  ```
  Group 1: Dirty Deeds by AC/DC
  [Best] /music/ac-dc/dirty-deeds-flac (15 tracks, 450.2 MB)
    Quality: FLAC 44.1kHz 16bit (avg)
    Confidence: 100.0%
    MusicBrainz ID: abc123...
    Metadata: AC/DC - Dirty Deeds Done Dirt Cheap

    /music/ac-dc/dirty-deeds-mp3 (15 tracks, 98.5 MB)
    Quality: MP3 CBR 320kbps (avg)
    Confidence: 95.0%
    Match: 99.8%
  ```

- **JSON Output**: Includes `matched_album`, `matched_artist` at group level, `confidence` for each album
  ```json
  {
    "matched_album": "Dirty Deeds Done Dirt Cheap",
    "matched_artist": "AC/DC",
    "albums": [
      {
        "path": "/music/ac-dc/dirty-deeds-flac",
        "confidence": 100.0,
        "is_best": true,
        "quality_score": 11644.1,
        ...
      }
    ]
  }
  ```

- **CSV Output**: Adds columns for `matched_album`, `matched_artist`, `confidence`
  - Format: `group_id,matched_album,matched_artist,album_path,track_count,total_size_bytes,total_size,quality_info,quality_score,confidence,is_best,musicbrainz_albumid,album_name,artist_name,has_mixed_mb_ids`
  - Good for GUI integration and spreadsheet analysis

### Album Confidence Scoring

Confidence that an album belongs to a matched duplicate group:

- **100%**: All albums have matching MusicBrainz album ID
- **90-95%**: Album/artist metadata matches + high fingerprint similarity
- **80-90%**: Fingerprint similarity only (no metadata match)

Confidence calculation factors:
- Base confidence: 80%
- +5% if album name matches the group's matched album
- +5% if artist name matches the group's matched artist
- +0-10% based on average fingerprint similarity to other albums in group (98-100% similarity range)

## Future Enhancements

### Potential Features

- Parallel hashing with multiprocessing
- Preview audio before deletion
- Dry-run mode for `--delete-duplicates`
- GUI interface

### Code Improvements

- More comprehensive test coverage (integration tests)
- Benchmark Chromaprint performance on large libraries
- Support for more exotic audio formats (AIFF, APE, etc.)
- Optional fuzzy duration matching (±1 second tolerance)

### Album Mode Future Phases

- **Fuzzy Tag Matching**: Match albums/tracks with possible misspellings in ID3 tags
  - Use Levenshtein distance or similar algorithms to match album/artist names
  - Example: "The Beatles" vs "Beatles" or "Led Zeppelin" vs "Led Zepplin"
  - Match against canonical albums (those with MusicBrainz IDs) within close edit distance
  - Configurable threshold for fuzzy matching sensitivity
  - Useful for poorly tagged or user-edited metadata

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

- **Read `.claude-state.md` FIRST** before taking any actions - it contains complete session context, recent work, and current development state
- **Always format code** with Black before presenting to user
- **Always run linting** with Ruff when making changes
- **Prefer editing** existing files over creating new ones
- **Test changes** when modifying core logic
- **Document breaking changes** in commit messages
- **Ask before** installing system packages or major refactors
- **Reference files** using markdown links: `[file.py](src/duperscooper/file.py)`
