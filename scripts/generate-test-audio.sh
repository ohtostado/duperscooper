#!/bin/bash
# Generate synthetic test audio files for duperscooper testing
# Uses FFmpeg to create short (2 second) audio files with unique fingerprints

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
TEST_AUDIO_DIR="$PROJECT_ROOT/test-audio-synthetic"
TEST_ALBUMS_DIR="$PROJECT_ROOT/test-albums-synthetic"

# Check for ffmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo "Error: ffmpeg is required but not installed"
    echo "Install: sudo apt install ffmpeg  (or brew install ffmpeg on macOS)"
    exit 1
fi

echo "Generating synthetic test audio files..."
echo "Output directories:"
echo "  - $TEST_AUDIO_DIR"
echo "  - $TEST_ALBUMS_DIR"
echo ""

# Clean and create directories
rm -rf "$TEST_AUDIO_DIR" "$TEST_ALBUMS_DIR"
mkdir -p "$TEST_AUDIO_DIR" "$TEST_ALBUMS_DIR"

# ============================================================================
# TRACK MODE TEST FILES
# ============================================================================
# Generate 3 unique source tracks (2 seconds each, different frequencies)
# Each will have FLAC + multiple MP3 variants

echo "Generating Track Mode test files..."

# Track 1: Musical pattern (440 Hz with harmonics) - 5 seconds
# Generate source ONCE, then create all variants from it
TRACK1_TEMP="$TEST_AUDIO_DIR/track1-source.wav"
# Create a more complex waveform with fundamental + harmonics
ffmpeg -f lavfi -i "sine=frequency=440:duration=5" -f lavfi -i "sine=frequency=880:duration=5" \
    -filter_complex "amix=inputs=2:duration=first" -ar 44100 -ac 2 -y "$TRACK1_TEMP" -loglevel error

# Track 1 variants (all from same source = duplicates)
ffmpeg -i "$TRACK1_TEMP" -c:a flac -y "$TEST_AUDIO_DIR/track1.flac" -loglevel error
ffmpeg -i "$TRACK1_TEMP" -c:a libmp3lame -b:a 320k -y "$TEST_AUDIO_DIR/track1-320.mp3" -loglevel error
ffmpeg -i "$TRACK1_TEMP" -c:a libmp3lame -b:a 128k -y "$TEST_AUDIO_DIR/track1-128.mp3" -loglevel error
ffmpeg -i "$TRACK1_TEMP" -c:a libmp3lame -b:a 64k -y "$TEST_AUDIO_DIR/track1-64.mp3" -loglevel error
rm "$TRACK1_TEMP"

# Track 2: Different musical pattern (523 Hz with harmonics) - 5 seconds
TRACK2_TEMP="$TEST_AUDIO_DIR/track2-source.wav"
ffmpeg -f lavfi -i "sine=frequency=523:duration=5" -f lavfi -i "sine=frequency=1046:duration=5" \
    -filter_complex "amix=inputs=2:duration=first" -ar 44100 -ac 2 -y "$TRACK2_TEMP" -loglevel error

# Track 2 variants (all from same source = duplicates)
ffmpeg -i "$TRACK2_TEMP" -c:a flac -y "$TEST_AUDIO_DIR/track2.flac" -loglevel error
ffmpeg -i "$TRACK2_TEMP" -c:a libmp3lame -b:a 192k -y "$TEST_AUDIO_DIR/track2-192.mp3" -loglevel error
ffmpeg -i "$TRACK2_TEMP" -c:a libmp3lame -b:a 96k -y "$TEST_AUDIO_DIR/track2-96.mp3" -loglevel error
rm "$TRACK2_TEMP"

# Track 3: Yet another pattern (330 Hz with harmonics) - 5 seconds
TRACK3_TEMP="$TEST_AUDIO_DIR/track3-source.wav"
ffmpeg -f lavfi -i "sine=frequency=330:duration=5" -f lavfi -i "sine=frequency=660:duration=5" \
    -filter_complex "amix=inputs=2:duration=first" -ar 44100 -ac 2 -y "$TRACK3_TEMP" -loglevel error

# Track 3 variants (all from same source = duplicates)
ffmpeg -i "$TRACK3_TEMP" -c:a flac -y "$TEST_AUDIO_DIR/track3.flac" -loglevel error
ffmpeg -i "$TRACK3_TEMP" -c:a libmp3lame -b:a 160k -y "$TEST_AUDIO_DIR/track3-160.mp3" -loglevel error
rm "$TRACK3_TEMP"

echo "  ✓ Created 3 unique tracks with 11 total files"

# ============================================================================
# ALBUM MODE TEST FILES
# ============================================================================
echo ""
echo "Generating Album Mode test files..."

# Generate 2 albums (3 tracks each) with various scenarios
# Album A: 3 tracks at different frequencies (440, 523, 659 Hz - A, C, E chord)
# Album B: 3 tracks with different noise colors

# ============================================================================
# Album A - Scenario 1: Full metadata (MusicBrainz ID + tags)
# ============================================================================
ALBUM_A1="$TEST_ALBUMS_DIR/AlbumA-FLAC-Full-Metadata"
mkdir -p "$ALBUM_A1"

# MusicBrainz ID for this album (fake but consistent)
MB_ALBUM_ID="12345678-1234-5678-1234-567812345678"

for i in 1 2 3; do
    FREQ=$((440 + (i-1) * 100))  # 440, 540, 640 Hz
    TRACK_NUM=$(printf "%02d" $i)

    # Generate WAV
    ffmpeg -f lavfi -i "sine=frequency=$FREQ:duration=5" -ar 44100 -ac 2 \
        -y "$ALBUM_A1/temp-$i.wav" -loglevel error

    # Convert to FLAC with full metadata
    ffmpeg -i "$ALBUM_A1/temp-$i.wav" -c:a flac \
        -metadata "title=Track $i" \
        -metadata "artist=Test Artist A" \
        -metadata "album=Test Album A" \
        -metadata "track=$i/3" \
        -metadata "MUSICBRAINZ_ALBUMID=$MB_ALBUM_ID" \
        -y "$ALBUM_A1/$TRACK_NUM - Track $i.flac" -loglevel error

    rm "$ALBUM_A1/temp-$i.wav"
done

echo "  ✓ Created Album A - Full Metadata (3 tracks)"

# ============================================================================
# Album A - Scenario 2: Same content, MP3 320, same metadata
# ============================================================================
ALBUM_A2="$TEST_ALBUMS_DIR/AlbumA-MP3-320-Full-Metadata"
mkdir -p "$ALBUM_A2"

for i in 1 2 3; do
    FREQ=$((440 + (i-1) * 100))
    TRACK_NUM=$(printf "%02d" $i)

    ffmpeg -f lavfi -i "sine=frequency=$FREQ:duration=5" -ar 44100 -ac 2 \
        -y "$ALBUM_A2/temp-$i.wav" -loglevel error

    ffmpeg -i "$ALBUM_A2/temp-$i.wav" -c:a libmp3lame -b:a 320k \
        -metadata "title=Track $i" \
        -metadata "artist=Test Artist A" \
        -metadata "album=Test Album A" \
        -metadata "track=$i/3" \
        -metadata "MUSICBRAINZ_ALBUMID=$MB_ALBUM_ID" \
        -y "$ALBUM_A2/$TRACK_NUM - Track $i.mp3" -loglevel error

    rm "$ALBUM_A2/temp-$i.wav"
done

echo "  ✓ Created Album A - MP3 320 (duplicate, same metadata)"

# ============================================================================
# Album A - Scenario 3: Same content, MP3 128, NO MusicBrainz ID (ID3 tags only)
# ============================================================================
ALBUM_A3="$TEST_ALBUMS_DIR/AlbumA-MP3-128-No-MusicBrainz"
mkdir -p "$ALBUM_A3"

for i in 1 2 3; do
    FREQ=$((440 + (i-1) * 100))
    TRACK_NUM=$(printf "%02d" $i)

    ffmpeg -f lavfi -i "sine=frequency=$FREQ:duration=5" -ar 44100 -ac 2 \
        -y "$ALBUM_A3/temp-$i.wav" -loglevel error

    # Same tags but NO MusicBrainz ID
    ffmpeg -i "$ALBUM_A3/temp-$i.wav" -c:a libmp3lame -b:a 128k \
        -metadata "title=Track $i" \
        -metadata "artist=Test Artist A" \
        -metadata "album=Test Album A" \
        -metadata "track=$i/3" \
        -y "$ALBUM_A3/$TRACK_NUM - Track $i.mp3" -loglevel error

    rm "$ALBUM_A3/temp-$i.wav"
done

echo "  ✓ Created Album A - MP3 128 (duplicate, no MusicBrainz ID)"

# ============================================================================
# Album A - Scenario 4: Same content, FLAC, NO metadata (untagged)
# ============================================================================
ALBUM_A4="$TEST_ALBUMS_DIR/AlbumA-FLAC-Untagged"
mkdir -p "$ALBUM_A4"

for i in 1 2 3; do
    FREQ=$((440 + (i-1) * 100))
    TRACK_NUM=$(printf "%02d" $i)

    ffmpeg -f lavfi -i "sine=frequency=$FREQ:duration=5" -ar 44100 -ac 2 \
        -y "$ALBUM_A4/temp-$i.wav" -loglevel error

    # No metadata at all
    ffmpeg -i "$ALBUM_A4/temp-$i.wav" -c:a flac \
        -y "$ALBUM_A4/track$TRACK_NUM.flac" -loglevel error

    rm "$ALBUM_A4/temp-$i.wav"
done

echo "  ✓ Created Album A - Untagged (duplicate, fingerprint-only match)"

# ============================================================================
# Album B - Scenario 1: Different album, FLAC with metadata
# ============================================================================
ALBUM_B1="$TEST_ALBUMS_DIR/AlbumB-FLAC-Full-Metadata"
mkdir -p "$ALBUM_B1"

MB_ALBUM_ID_B="87654321-4321-8765-4321-876543218765"

# Use different sine wave frequencies (D, F, G notes - different chord from Album A)
FREQS_B=(294 349 392)

for i in 1 2 3; do
    FREQ="${FREQS_B[$((i-1))]}"
    TRACK_NUM=$(printf "%02d" $i)

    ffmpeg -f lavfi -i "sine=frequency=$FREQ:duration=5" \
        -ar 44100 -ac 2 -y "$ALBUM_B1/temp-$i.wav" -loglevel error

    ffmpeg -i "$ALBUM_B1/temp-$i.wav" -c:a flac \
        -metadata "title=Song $i" \
        -metadata "artist=Test Artist B" \
        -metadata "album=Test Album B" \
        -metadata "track=$i/3" \
        -metadata "MUSICBRAINZ_ALBUMID=$MB_ALBUM_ID_B" \
        -y "$ALBUM_B1/$TRACK_NUM - Song $i.flac" -loglevel error

    rm "$ALBUM_B1/temp-$i.wav"
done

echo "  ✓ Created Album B - Full Metadata (3 tracks)"

# ============================================================================
# Album B - Scenario 2: Same content, MP3 192, same metadata
# ============================================================================
ALBUM_B2="$TEST_ALBUMS_DIR/AlbumB-MP3-192-Full-Metadata"
mkdir -p "$ALBUM_B2"

for i in 1 2 3; do
    FREQ="${FREQS_B[$((i-1))]}"
    TRACK_NUM=$(printf "%02d" $i)

    # Same frequencies as Album B1 to ensure duplicate detection
    ffmpeg -f lavfi -i "sine=frequency=$FREQ:duration=5" \
        -ar 44100 -ac 2 -y "$ALBUM_B2/temp-$i.wav" -loglevel error

    ffmpeg -i "$ALBUM_B2/temp-$i.wav" -c:a libmp3lame -b:a 192k \
        -metadata "title=Song $i" \
        -metadata "artist=Test Artist B" \
        -metadata "album=Test Album B" \
        -metadata "track=$i/3" \
        -metadata "MUSICBRAINZ_ALBUMID=$MB_ALBUM_ID_B" \
        -y "$ALBUM_B2/$TRACK_NUM - Song $i.mp3" -loglevel error

    rm "$ALBUM_B2/temp-$i.wav"
done

echo "  ✓ Created Album B - MP3 192 (duplicate)"

# ============================================================================
# Album C - Scenario: Partial album (only 2 of 3 tracks)
# ============================================================================
ALBUM_C1="$TEST_ALBUMS_DIR/AlbumC-Partial-Missing-Track-3"
mkdir -p "$ALBUM_C1"

MB_ALBUM_ID_C="11111111-2222-3333-4444-555555555555"

# Only create tracks 1 and 2 (missing track 3)
for i in 1 2; do
    FREQ=$((660 + (i-1) * 100))  # Different from Album A
    TRACK_NUM=$(printf "%02d" $i)

    ffmpeg -f lavfi -i "sine=frequency=$FREQ:duration=5" -ar 44100 -ac 2 \
        -y "$ALBUM_C1/temp-$i.wav" -loglevel error

    ffmpeg -i "$ALBUM_C1/temp-$i.wav" -c:a flac \
        -metadata "title=Part $i" \
        -metadata "artist=Test Artist C" \
        -metadata "album=Test Album C" \
        -metadata "track=$i/3" \
        -metadata "MUSICBRAINZ_ALBUMID=$MB_ALBUM_ID_C" \
        -y "$ALBUM_C1/$TRACK_NUM - Part $i.flac" -loglevel error

    rm "$ALBUM_C1/temp-$i.wav"
done

echo "  ✓ Created Album C - Partial (only 2/3 tracks)"

# ============================================================================
# Summary
# ============================================================================
echo ""
echo "========================================="
echo "Test audio generation complete!"
echo "========================================="
echo ""
echo "Track Mode: $TEST_AUDIO_DIR"
find "$TEST_AUDIO_DIR" -type f -name "*.flac" -o -name "*.mp3" | wc -l | xargs echo "  - Files:"
du -sh "$TEST_AUDIO_DIR" | awk '{print "  - Size: " $1}'
echo ""
echo "Album Mode: $TEST_ALBUMS_DIR"
find "$TEST_ALBUMS_DIR" -type d -mindepth 1 -maxdepth 1 | wc -l | xargs echo "  - Albums:"
find "$TEST_ALBUMS_DIR" -type f -name "*.flac" -o -name "*.mp3" | wc -l | xargs echo "  - Files:"
du -sh "$TEST_ALBUMS_DIR" | awk '{print "  - Size: " $1}'
echo ""
echo "Test scenarios covered:"
echo "  Track Mode:"
echo "    - 3 unique tracks (different frequencies/noise)"
echo "    - Multiple format variants (FLAC, MP3 64-320kbps)"
echo "    - Should detect duplicates across formats"
echo ""
echo "  Album Mode:"
echo "    - Album A: 4 versions (FLAC full, MP3-320 full, MP3-128 no-MB, FLAC untagged)"
echo "    - Album B: 2 versions (FLAC full, MP3-192 full)"
echo "    - Album C: 1 partial album (2/3 tracks)"
echo "    - Tests: MusicBrainz matching, ID3 tag matching, fingerprint matching, partial albums"
echo ""
echo "To test:"
echo "  duperscooper $TEST_AUDIO_DIR"
echo "  duperscooper --album-mode $TEST_ALBUMS_DIR"
