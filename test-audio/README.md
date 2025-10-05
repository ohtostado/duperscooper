# Test Audio Files (Track Mode)

This directory contains synthetic test audio files for testing track-mode duplicate detection.

## Files

- **9 total files** (832 KB)
- **3 unique tracks** at different frequencies:
  - Track 1: 440 Hz + 880 Hz (fundamental + octave)
  - Track 2: 523 Hz + 1046 Hz
  - Track 3: 330 Hz + 660 Hz

### Track 1 Variants (Duplicates)
- `track1.flac` - FLAC 44.1kHz 16bit
- `track1-320.mp3` - MP3 CBR 320kbps
- `track1-128.mp3` - MP3 CBR 128kbps
- `track1-64.mp3` - MP3 CBR 64kbps

### Track 2 Variants (Duplicates)
- `track2.flac` - FLAC 44.1kHz 16bit
- `track2-192.mp3` - MP3 CBR 192kbps
- `track2-96.mp3` - MP3 CBR 96kbps

### Track 3 Variants (Duplicates)
- `track3.flac` - FLAC 44.1kHz 16bit
- `track3-160.mp3` - MP3 CBR 160kbps

## Expected Behavior

When running:
```bash
duperscooper test-audio/
```

**Note:** Due to the simplicity of pure sine waves, perceptual matching may not detect these as duplicates. Use `--algorithm exact` to test exact matching functionality, or use the album mode tests in `test-albums/` which work reliably with perceptual matching.

## Generation

These files were generated using:
```bash
./scripts/generate-test-audio.sh
```

All files are 5 seconds long and use synthetic audio (sine waves) to avoid copyright issues.
