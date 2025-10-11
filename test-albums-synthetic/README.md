# Test Albums for duperscooper GUI Testing

This directory contains synthetic test albums designed to test various duplicate detection scenarios.

## Album Groups

### Album A - Complete Duplicate Set (100% matches)
All versions have identical audio content in different formats:
- `AlbumA-FLAC-Full-Metadata` - Reference version (FLAC, MusicBrainz ID, full tags)
- `AlbumA-MP3-320-Full-Metadata` - Same audio, MP3 320kbps (MusicBrainz ID)
- `AlbumA-MP3-128-No-MusicBrainz` - Same audio, MP3 128kbps (ID3 only, no MB ID)
- `AlbumA-FLAC-Untagged` - Same audio, FLAC (no metadata)
- `AlbumA-MP3-192-Similar-Content` - Same audio with subtle noise (ID3 only)
- `AlbumA-MP3-160-Partial-Match` - 2/3 tracks match, 1 different (**requires `--allow-partial-albums --similarity-threshold 60`**)

**Use case**: Test 100% similarity matching across formats and metadata scenarios

### Album B - Standard Duplicates + Extended Edition
- `AlbumB-FLAC-Full-Metadata` - Reference version (3 tracks, MusicBrainz ID)
- `AlbumB-MP3-192-Full-Metadata` - Same audio, MP3 192kbps (3 tracks, MusicBrainz ID)
- `AlbumB-MP3-256-Extended-Edition` - 4 tracks, first 3 match Album B (**requires `--allow-partial-albums`**)

**Use case**: Test partial album matching (different track counts)

### Album C - Incomplete Album
- `AlbumC-Partial-Missing-Track-3` - Only 2 tracks, incomplete album

**Use case**: Test handling of incomplete albums

### Album D - Varying Similarity Percentages (97-100%)
Created specifically for GUI testing to show non-100% similarity:

- `AlbumD-FLAC-Original` - Reference version (MusicBrainz ID)
- `AlbumD-MP3-256-Pitched` - Pitched +0.5 semitones (~97% match, no MB ID)
- `AlbumD-MP3-320-EQ` - Pitched +0.25 semitones (~99-100% match, no MB ID)
- `AlbumD-MP3-192-Stretched` - Time-stretched 1.05x (below 97%, won't match without lowering threshold)

**Use case**: **Best for GUI testing** - Shows varying similarity percentages in the GUI

## Testing Strategies

### For GUI Development (Recommended)
Test with Album D variants to see different similarity percentages:

```bash
# Default auto strategy (uses ID3 tags + fingerprints)
duperscooper --album-mode test-albums-synthetic/AlbumD-*

# Expected: Groups pitched variants together, shows 100% match
# Original and stretched won't match (different strategies/thresholds)
```

### For Fingerprint-Only Matching
```bash
duperscooper --album-mode --album-match-strategy fingerprint test-albums-synthetic/
```

### For Partial Album Testing
```bash
# Enable partial matching with lower threshold
duperscooper --album-mode --allow-partial-albums --similarity-threshold 60 test-albums-synthetic/
```

### For Complete Testing
```bash
# Scan all test albums with default settings
duperscooper --album-mode test-albums-synthetic/

# Expected groups:
# - Album A: 5-6 versions (depending on similarity threshold for noise variant)
# - Album B: 2 versions (3rd requires --allow-partial-albums)
# - Album D: 2-3 versions (depending on which match at current threshold)
```

## Regenerating Test Albums

```bash
# Regenerate all albums
./scripts/generate-test-audio.sh

# Generate Album D variants with varying similarity
./scripts/create-varying-similarity-albums.sh
```

## Notes

- **Chromaprint is very robust**: Even with noise/EQ changes, it produces 100% similarity
- **Pitch shifting works**: Changing pitch by 0.5+ semitones creates <100% similarity
- **Time stretching works**: Stretching by 5%+ creates <100% similarity
- **For GUI testing**: Use Album D variants to see non-100% percentages in the similarity column
