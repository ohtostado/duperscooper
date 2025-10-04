# duperscooper

## Find and eliminate duplicate audio files with intelligent perceptual matching

duperscooper is a Python CLI tool that identifies duplicate audio files using acoustic fingerprinting technology. It can detect duplicates across different formats, bitrates, and encodings—even finding that a 64kbps MP3 and a lossless FLAC are the same song. Works at both the track level and album level.

## Key Features

- **Perceptual Audio Matching** - Detects duplicates across all formats and bitrates using Chromaprint fingerprints with Hamming distance (default 98% similarity threshold)
- **Album-Level Detection** - Find duplicate albums using MusicBrainz IDs, ID3 tags, or acoustic fingerprints
- **Quality Detection** - Automatically identifies the best quality version (lossless > lossy, higher bitrate/bit depth preferred)
- **Rules Engine** - Apply custom deletion rules to scan results with built-in strategies or YAML/JSON configs
- **Safe Deletion** - Staging system with full restoration capability and SHA256 verification
- **Fast Performance** - Multi-threaded fingerprinting (8 workers default) with SQLite caching for instant repeated scans
- **Flexible Output** - Text (color-coded), JSON, or CSV formats for easy integration with other tools
- **Partial Album Matching** - Detect albums with missing tracks as potential duplicates
- **Tab Completion** - Bash/zsh/tcsh command-line completion support

## Installation

### Prerequisites

duperscooper requires two external tools for audio processing:

```bash
# Ubuntu/Debian
sudo apt install libchromaprint-tools ffmpeg

# macOS
brew install chromaprint ffmpeg

# Verify installation
fpcalc --version
ffprobe -version
```

### Install duperscooper

#### Local Development Installation

```bash
# Clone repository
git clone https://github.com/ohtostado/duperscooper.git
cd duperscooper

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install duperscooper
pip install -e .

# Optional: Install tab completion
pip install shtab
./install-completion.sh bash  # or zsh, tcsh
```

#### Docker Installation

Add duperscooper to any Dockerfile with just 2 additions:

```dockerfile
# Add system dependencies to your apt install section
RUN apt-get update && apt-get install -y --no-install-recommends \
    libchromaprint-tools \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install duperscooper (works for both root and non-root users)
RUN pip install --no-cache-dir git+https://github.com/ohtostado/duperscooper.git
```

**Alternative:** Install from local copy (if building with repo context):

```dockerfile
# In your Dockerfile
COPY duperscooper /tmp/duperscooper
RUN pip install --no-cache-dir /tmp/duperscooper && rm -rf /tmp/duperscooper
```

The `duperscooper` command will be available in the shell after installation.

## Quick Start

```bash
# Find duplicate tracks in your music library
duperscooper ~/Music

# Find duplicate albums
duperscooper ~/Music --album-mode

# Output as JSON for further processing
duperscooper ~/Music --album-mode --output json > duplicates.json

# Use 16 threads for faster processing
duperscooper ~/Music --workers 16
```

## Usage

### Track Mode (Default)

Track mode finds duplicate audio files by comparing individual tracks.

```bash
# Basic usage - scan directory for duplicate tracks
duperscooper ~/Music

# Scan multiple directories
duperscooper ~/Music ~/Downloads

# Include small files (default: skip files < 1MB)
duperscooper ~/Music --min-size 0

# Adjust similarity threshold (default: 97%)
duperscooper ~/Music --similarity-threshold 95.0

# Use exact byte matching instead of perceptual (faster, less flexible)
duperscooper ~/Music --algorithm exact

# Interactive deletion mode
duperscooper ~/Music --delete-duplicates

# Non-interactive deletion (auto-delete all except best quality)
duperscooper ~/Music --delete-duplicates --yes

# Output formats (includes recommended_action field for GUI integration)
duperscooper ~/Music --output json > duplicates.json
duperscooper ~/Music --output csv > duplicates.csv
```

### Album Mode

Album mode finds duplicate albums (directories) using multiple matching strategies.

```bash
# Find duplicate albums (auto strategy: MusicBrainz → ID3 tags → fingerprints)
duperscooper ~/Music --album-mode

# Match only by MusicBrainz Album ID
duperscooper ~/Music --album-mode --album-match-strategy musicbrainz

# Match only by acoustic fingerprints (ignore metadata)
duperscooper ~/Music --album-mode --album-match-strategy fingerprint

# Allow partial album matches (e.g., albums missing tracks)
duperscooper ~/Music --album-mode --allow-partial-albums

# Set minimum overlap for partial matches (default: 70%)
duperscooper ~/Music --album-mode --allow-partial-albums --min-album-overlap 80

# Interactive album deletion
duperscooper ~/Music --album-mode --delete-duplicate-albums

# Non-interactive album deletion (auto-delete all except best quality)
duperscooper ~/Music --album-mode --delete-duplicate-albums --yes

# Output formats (includes recommended_action field for GUI integration)
duperscooper ~/Music --album-mode --output json > albums.json
duperscooper ~/Music --album-mode --output csv > albums.csv
```

### Cache Management

duperscooper caches audio fingerprints to speed up repeated scans.

```bash
# Clear the cache
duperscooper --clear-cache

# Disable cache for a single scan
duperscooper ~/Music --no-cache

# Force regeneration of cached fingerprints
duperscooper ~/Music --update-cache

# Use legacy JSON cache instead of SQLite
duperscooper ~/Music --cache-backend json
```

**Cache location:** `~/.config/duperscooper/hashes.db` (SQLite) or `hashes.json` (legacy)

### Performance Tuning

```bash
# Use 16 worker threads for faster fingerprinting
duperscooper ~/Music --workers 16

# Use single-threaded mode (useful for debugging)
duperscooper ~/Music --workers 1

# Disable progress bar output
duperscooper ~/Music --no-progress
```

### Apply Rules to Scan Results (Two-Phase Workflow)

Save scan results, review them, then apply deletion rules:

```bash
# Step 1: Scan and save (track or album mode)
duperscooper ~/Music --output json > scan.json
duperscooper ~/Music --album-mode --output json > albums.json

# Step 2: Preview deletion plan (dry-run mode, default)
duperscooper --apply-rules scan.json --strategy eliminate-duplicates

# Step 3: Execute deletions (stages to .deletedByDuperscooper/)
duperscooper --apply-rules scan.json --strategy eliminate-duplicates --execute

# Non-interactive execution (skip confirmations, for automation/GUI)
duperscooper --apply-rules scan.json --strategy eliminate-duplicates --execute --yes
```

**Built-in strategies:**

```bash
# Keep best quality only (default)
duperscooper --apply-rules scan.json --strategy eliminate-duplicates --execute

# Keep only lossless formats (FLAC, WAV, etc.)
duperscooper --apply-rules scan.json --strategy keep-lossless --execute

# Keep only specific format (e.g., FLAC)
duperscooper --apply-rules scan.json --strategy keep-format --format FLAC --execute

# Use custom rules from YAML config
duperscooper --apply-rules scan.json --strategy custom --config my-rules.yaml --execute
```

**Example custom rules** (`my-rules.yaml`):

```yaml
rules:
  # Always keep best quality
  - name: "Keep best quality"
    action: keep
    priority: 100
    conditions:
      - field: is_best
        operator: "=="
        value: true

  # Delete low bitrate MP3s
  - name: "Delete MP3s under 192kbps"
    action: delete
    priority: 50
    logic: AND
    conditions:
      - field: format
        operator: "=="
        value: "MP3"
      - field: quality_score
        operator: "<"
        value: 192

default_action: keep
```

See [docs/rules-examples.yaml](docs/rules-examples.yaml) for more examples.

### Staging and Restoration

All deletions are staged for safety - you can restore them at any time:

```bash
# List all staged deletions
duperscooper --list-deleted

# Restore a specific batch
duperscooper --restore <batch-uuid>

# Restore to different location
duperscooper --restore <batch-uuid> --restore-to /backup/music

# Interactive restoration (choose individual tracks/albums)
duperscooper --restore-interactive <batch-uuid>

# Permanently delete old staged batches
duperscooper --empty-deleted --older-than 30  # older than 30 days
duperscooper --empty-deleted --keep-last 5     # keep only 5 most recent
```

## How It Works

### Perceptual Matching

duperscooper uses **Chromaprint** acoustic fingerprinting to create a unique "signature" for each audio file based on its actual sound content. These fingerprints are compared using **Hamming distance** (bit-level differences) to calculate similarity percentages.

**Key characteristics:**

- Detects duplicates across all formats: FLAC, MP3, AAC, OGG, OPUS, M4A, WMA, WAV
- Works across all bitrates: 64kbps MP3 ≈ 98% similar to FLAC
- Default threshold: 97% similarity
- Algorithm complexity: O(n²) with Union-Find optimization

### Quality Scoring

duperscooper automatically identifies the highest quality version of each duplicate:

**Lossless formats** (FLAC, WAV, ALAC, APE):

```text
score = 10000 + (bit_depth × 100) + (sample_rate / 1000)
```

Example: 24-bit 96kHz FLAC = 10000 + 2400 + 96 = **12496**

**Lossy formats** (MP3, AAC, OGG, OPUS):

```text
score = bitrate / 1000 (in kbps)
```

Example: 320kbps MP3 = **320**

This ensures lossless files always rank higher than lossy, with finer granularity within each category.

### Album Matching Strategies

**Auto strategy** (default):

1. Identify canonical albums (those with MusicBrainz IDs or complete ID3 tags)
2. Group canonical albums by fingerprint similarity
3. Match untagged albums against canonical groups
4. Untagged albums inherit matched album/artist names

**MusicBrainz strategy:**

- Groups albums by MusicBrainz Album ID + track count
- 100% confidence when MB IDs match
- Ignores albums without MB IDs

**Fingerprint strategy:**

- Groups albums by acoustic fingerprint similarity only
- Ignores all metadata (MB IDs, ID3 tags)
- Useful for poorly-tagged libraries

### Confidence Scoring

Album mode displays confidence that an album belongs to a duplicate group:

- **100%**: All albums have matching MusicBrainz Album ID
- **90-95%**: Album/artist metadata matches + high fingerprint similarity
- **80-90%**: Fingerprint similarity only (no metadata match)

## Output Formats

### Text Output (Default)

**Track Mode:**

```text
Group 1:
[Best] /music/song.flac (30.9 MB) - FLAC 44.1kHz 16bit
  ├─ /music/song-64.mp3 (2.8 MB) - MP3 CBR 64kbps
     [97.9% match]
  ├─ /music/song-128.mp3 (5.6 MB) - MP3 CBR 128kbps
     [99.5% match]
  └─ /music/song-320.mp3 (13.4 MB) - MP3 CBR 320kbps
     [99.9% match]

Space wasted on duplicates: 22.8 MB
```

**Album Mode:**

```text
Group 1: Back in Black by AC/DC
[Best] /music/ac-dc/back-in-black-flac (10 tracks, 380 MB)
       FLAC 44.1kHz 16bit (avg)
       Confidence: 100.0%
       MusicBrainz ID: abc123...
       Match: MusicBrainz Album ID

       /music/ac-dc/back-in-black-mp3-320 (10 tracks, 98 MB)
       MP3 CBR 320kbps (avg)
       Confidence: 95.0%
       Match: 99.8% (ID3 Album/Artist Tags)

       /music/backups/ac-dc-192 (10 tracks, 65 MB)
       MP3 CBR 192kbps (avg)
       Confidence: 90.0%
       Match: 99.2% (Acoustic Fingerprint)
```

### JSON Output

```bash
duperscooper ~/Music --album-mode --output json
```

```json
{
  "duplicate_groups": [
    {
      "group_id": 1,
      "matched_album": "Back in Black",
      "matched_artist": "AC/DC",
      "albums": [
        {
          "path": "/music/ac-dc/back-in-black-flac",
          "track_count": 10,
          "total_size_bytes": 398458880,
          "total_size": "380.0 MB",
          "quality_info": "FLAC 44.1kHz 16bit (avg)",
          "quality_score": 11644.1,
          "confidence": 100.0,
          "is_best": true,
          "musicbrainz_albumid": "abc123...",
          "album_name": "Back in Black",
          "artist_name": "AC/DC",
          "has_mixed_mb_ids": false,
          "match_method": "MusicBrainz Album ID"
        }
      ]
    }
  ],
  "total_groups": 1,
  "total_duplicates": 2
}
```

### CSV Output

Good for spreadsheet analysis or GUI integration:

```bash
duperscooper ~/Music --album-mode --output csv > duplicates.csv
```

**Columns:** `group_id`, `matched_album`, `matched_artist`, `album_path`, `track_count`, `total_size_bytes`, `total_size`, `quality_info`, `quality_score`, `confidence`, `is_best`, `musicbrainz_albumid`, `album_name`, `artist_name`, `has_mixed_mb_ids`, `match_method`

## Performance

### Benchmarks

Tested on 21 albums (203 audio files, 4.6GB) - album mode:

| Workers | Scan Time | Speedup |
|---------|-----------|---------|
| 1       | 52.3s     | 1.0x    |
| 4       | 34.0s     | 1.5x    |
| 8       | 34.0s     | 1.5x    |
| 16      | 34.0s     | 1.5x    |
| Cached  | 3.3s      | 15.8x   |

**Notes:**

- Parallel processing provides ~1.5x speedup on this dataset
- Diminishing returns beyond 4 workers (likely due to dataset size)
- Cached scans are ~16x faster (3.3s vs 52.3s for cold start)
- I/O-bound workload (subprocess calls to `fpcalc`)
- Larger datasets will see more benefit from additional workers

### Scaling Considerations

- **Small libraries** (< 1,000 files): Any setting works well
- **Medium libraries** (1,000-10,000 files): Use 8-16 workers
- **Large libraries** (> 10,000 files): Consider using `--algorithm exact` first for faster detection

Perceptual matching is O(n²), suitable for libraries up to ~10,000 files.

## Development

### Setup Development Environment

```bash
# Clone and setup
git clone https://github.com/ohtostado/duperscooper.git
cd duperscooper
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

### Quality Checks

All checks must pass before committing:

```bash
# Format code
.venv/bin/black src/ tests/

# Lint and auto-fix issues
.venv/bin/ruff check --fix src/ tests/

# Type check
.venv/bin/mypy src/

# Run tests
.venv/bin/pytest tests/ -v

# Run tests with coverage
.venv/bin/pytest tests/ --cov=duperscooper
```

### Running Tests

```bash
# All tests
pytest tests/ -v

# Specific test file
pytest tests/test_cache.py -v

# With coverage report
pytest tests/ --cov=duperscooper --cov-report=html
```

### Project Structure

```text
duperscooper/
├── src/duperscooper/
│   ├── __init__.py       # Package metadata
│   ├── __main__.py       # CLI interface, output formatting
│   ├── cache.py          # SQLite/JSON cache backends
│   ├── hasher.py         # Audio fingerprinting, metadata extraction
│   ├── finder.py         # Duplicate detection, parallelization
│   └── album.py          # Album scanning and matching
├── tests/
│   ├── test_cache.py     # Cache backend tests
│   └── test_finder.py    # Duplicate finder tests
├── test-audio/           # Test files for track mode
├── test-albums/          # Test folders for album mode
├── requirements.txt      # Python dependencies
└── pyproject.toml        # Project configuration
```

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run all quality checks (black, ruff, mypy, pytest)
5. Commit with conventional commit messages (`feat:`, `fix:`, `docs:`, etc.)
6. Reference issues in commit messages (`Fixes #123`)
7. Push to your fork and open a pull request

## License

See [LICENSE](LICENSE) file for details.

## Acknowledgments

- **Chromaprint** - Acoustic fingerprinting library by Lukáš Lalinský
- **FFmpeg** - Audio metadata extraction
- Built with Python 3.8+ compatibility

## Troubleshooting

### "fpcalc: command not found"

```bash
# Install Chromaprint
sudo apt install libchromaprint-tools  # Ubuntu/Debian
brew install chromaprint               # macOS
```

### "ffprobe: command not found"

```bash
# Install FFmpeg
sudo apt install ffmpeg  # Ubuntu/Debian
brew install ffmpeg      # macOS
```

### Import errors

```bash
# Ensure virtual environment is activated
source .venv/bin/activate
pip install -r requirements.txt
```

### Slow performance

```bash
# Increase worker threads
duperscooper ~/Music --workers 16

# Or use exact matching (faster but less flexible)
duperscooper ~/Music --algorithm exact
```

## Links

- **GitHub**: <https://github.com/ohtostado/duperscooper>
- **Issues**: <https://github.com/ohtostado/duperscooper/issues>
- **Chromaprint**: <https://acoustid.org/chromaprint>
