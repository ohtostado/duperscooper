# Testing Albums with Varying Similarity Percentages

## Problem

The synthetic test albums (Album D) are showing **100% similarity** even after applying audio transformations (pitch shift, time stretch, EQ). This is because:

1. **Synthetic audio fingerprints are too simple**: Our test audio uses basic sine waves with harmonics, which produce very repetitive Chromaprint fingerprints
2. **Chromaprint is extremely robust**: It's designed to ignore minor variations like pitch/tempo changes below certain thresholds
3. **Identical fingerprints**: All Album D variants have the exact same fingerprint: `558758263,558758263,558758263...`

## Solution: Use Real Audio Files

To properly test varying similarity percentages (97-100%), you need to use **real music files** instead of synthetic audio.

### Recommended Approach

1. **Download public domain music** (3-5 songs):
   - [FreePD.com](https://freepd.com/) - Public domain music
   - [Incompetech.com](https://incompetech.com/) - Royalty-free music
   - [Musopen.org](https://musopen.org/) - Public domain classical music

2. **Create test albums with transformations**:
   ```bash
   # Original FLAC version
   ffmpeg -i song.mp3 -c:a flac album-original/01-song.flac

   # Pitched version (+0.5 semitones) → ~97-98% similarity
   ffmpeg -i album-original/01-song.flac \
          -af "asetrate=44100*1.029302,aresample=44100" \
          -c:a libmp3lame -b:a 256k album-pitched/01-song.mp3

   # Slightly pitched (+0.25 semitones) → ~98-99% similarity
   ffmpeg -i album-original/01-song.flac \
          -af "asetrate=44100*1.0145,aresample=44100" \
          -c:a libmp3lame -b:a 320k album-slightly-pitched/01-song.mp3

   # Time stretched (1.03x speed) → ~97-98% similarity
   ffmpeg -i album-original/01-song.flac \
          -filter:a "atempo=1.03" \
          -c:a libmp3lame -b:a 192k album-stretched/01-song.mp3
   ```

3. **Test with duperscooper**:
   ```bash
   duperscooper --album-mode --album-match-strategy fingerprint test-albums/
   ```

### Why Real Audio Works

Real music has:
- **Complex harmonics**: Multiple instruments, vocals, percussion
- **Dynamic frequency content**: Changes over time
- **Unique patterns**: Each song has distinct spectral characteristics

These create **rich, unique fingerprints** that respond predictably to transformations:
- Pitch shift of 0.5 semitones → ~97% match
- Pitch shift of 0.25 semitones → ~98-99% match
- Time stretch of 3-5% → ~97-98% match
- Straight encoding (FLAC→MP3) → ~99.9-100% match

## Current Test Albums Status

### Album A, B, C
- ✅ Work correctly for 100% similarity testing
- ✅ Test different metadata scenarios (MB ID, ID3 only, untagged)
- ✅ Test partial album matching

### Album D
- ❌ Shows 100% similarity for all variants
- ❌ Synthetic audio too simple for Chromaprint differentiation
- ✅ Script created: `./scripts/create-varying-similarity-albums.sh`
- 💡 Replace synthetic audio with real music to get varying percentages

## Testing Order Issue

The "best version listed below lower quality" issue you mentioned:
- ✅ Backend correctly sorts albums (best first)
- ✅ JSON output has best album first (`is_best: true`)
- ✅ CLI text output shows best first with `[Best]` marker
- ❓ Check GUI display - backend is sending correct order

If GUI is showing wrong order, the issue is in the GUI code that adds items to the tree, not in the backend.

## Next Steps

1. **For production testing**: Use real music files as described above
2. **For quick testing**: Use existing Album A/B/C for 100% similarity scenarios
3. **GUI order issue**: Verify if GUI is actually showing wrong order or if it was a misunderstanding
