#!/bin/bash
# Create test albums with varying similarity percentages (97-100%)
# Uses audio transformations on real music to create realistic test scenarios

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
TEST_ALBUMS_DIR="$PROJECT_ROOT/test-albums-synthetic"

# Check for required tools
for tool in ffmpeg fpcalc; do
    if ! command -v $tool &> /dev/null; then
        echo "Error: $tool is required but not installed"
        exit 1
    fi
done

echo "Creating test albums with varying similarity percentages..."
echo ""

# We'll use generated audio with more complex waveforms
# Strategy: Create rich audio, then apply transformations

# ============================================================================
# Album D - Base version with complex waveforms (simulates real music better)
# ============================================================================
ALBUM_D1="$TEST_ALBUMS_DIR/AlbumD-FLAC-Original"
mkdir -p "$ALBUM_D1"

MB_ALBUM_ID_D="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

echo "Creating Album D - Original (3 tracks with rich harmonics)..."

for i in 1 2 3; do
    TRACK_NUM=$(printf "%02d" $i)
    BASE_FREQ=$((220 + (i-1) * 55))  # A3, D4, F#4

    # Create complex waveform with multiple harmonics and amplitude modulation
    # This creates richer audio that responds differently to transformations
    ffmpeg -f lavfi -i "sine=f=${BASE_FREQ}:d=5" \
           -f lavfi -i "sine=f=$((BASE_FREQ * 2)):d=5" \
           -f lavfi -i "sine=f=$((BASE_FREQ * 3)):d=5" \
           -f lavfi -i "sine=f=$((BASE_FREQ * 4)):d=5" \
           -filter_complex \
           "[0:a]volume=1.0[a0]; \
            [1:a]volume=0.5[a1]; \
            [2:a]volume=0.25[a2]; \
            [3:a]volume=0.125[a3]; \
            [a0][a1][a2][a3]amix=inputs=4:duration=first" \
           -ar 44100 -ac 2 -y "$ALBUM_D1/temp-$i.wav" -loglevel error

    # Convert to FLAC with metadata
    ffmpeg -i "$ALBUM_D1/temp-$i.wav" -c:a flac \
        -metadata "title=Song $i" \
        -metadata "artist=Test Artist D" \
        -metadata "album=Test Album D" \
        -metadata "track=$i/3" \
        -metadata "MUSICBRAINZ_ALBUMID=$MB_ALBUM_ID_D" \
        -y "$ALBUM_D1/$TRACK_NUM - Song $i.flac" -loglevel error

    rm "$ALBUM_D1/temp-$i.wav"
done

echo "  ✓ Created Album D - Original"

# ============================================================================
# Album D - Variant 1: Subtle pitch shift (+0.5 semitones)
# Target: ~98-99% similarity (NO MB ID - match by fingerprint only)
# ============================================================================
ALBUM_D2="$TEST_ALBUMS_DIR/AlbumD-MP3-256-Pitched"
mkdir -p "$ALBUM_D2"

echo "Creating Album D - Pitched (+0.5 semitones, target 98-99% match)..."

for i in 1 2 3; do
    TRACK_NUM=$(printf "%02d" $i)

    # Apply pitch shift and convert to WAV (strips metadata)
    ffmpeg -i "$ALBUM_D1/$TRACK_NUM - Song $i.flac" \
           -af "asetrate=44100*1.029302,aresample=44100" \
           -y "$ALBUM_D2/temp-$i.wav" -loglevel error

    # Convert WAV to MP3 with NEW metadata (no MB ID)
    ffmpeg -i "$ALBUM_D2/temp-$i.wav" -c:a libmp3lame -b:a 256k \
           -metadata "title=Song $i" \
           -metadata "artist=Test Artist D" \
           -metadata "album=Test Album D (Remastered)" \
           -metadata "track=$i/3" \
           -y "$ALBUM_D2/$TRACK_NUM - Song $i.mp3" -loglevel error

    rm "$ALBUM_D2/temp-$i.wav"
done

echo "  ✓ Created Album D - Pitched"

# ============================================================================
# Album D - Variant 2: Time stretch (1.01x speed)
# Target: ~97-98% similarity (NO MB ID - match by fingerprint only)
# ============================================================================
ALBUM_D3="$TEST_ALBUMS_DIR/AlbumD-MP3-192-Stretched"
mkdir -p "$ALBUM_D3"

echo "Creating Album D - Time Stretched (1.05x speed, target different % match)..."

for i in 1 2 3; do
    TRACK_NUM=$(printf "%02d" $i)

    # Apply time stretch and convert to WAV (strips metadata)
    ffmpeg -i "$ALBUM_D1/$TRACK_NUM - Song $i.flac" \
           -filter:a "atempo=1.05" \
           -y "$ALBUM_D3/temp-$i.wav" -loglevel error

    # Convert WAV to MP3 with NEW metadata (no MB ID)
    ffmpeg -i "$ALBUM_D3/temp-$i.wav" -c:a libmp3lame -b:a 192k \
           -metadata "title=Song $i" \
           -metadata "artist=Test Artist D" \
           -metadata "album=Test Album D (Special Edition)" \
           -metadata "track=$i/3" \
           -y "$ALBUM_D3/$TRACK_NUM - Song $i.mp3" -loglevel error

    rm "$ALBUM_D3/temp-$i.wav"
done

echo "  ✓ Created Album D - Time Stretched"

# ============================================================================
# Album D - Variant 3: Treble boost (EQ modification)
# Target: ~99% similarity (NO MB ID - match by fingerprint only)
# ============================================================================
ALBUM_D4="$TEST_ALBUMS_DIR/AlbumD-MP3-320-EQ"
mkdir -p "$ALBUM_D4"

echo "Creating Album D - Slightly Pitched (+0.25 semitones, target 98-99% match)..."

for i in 1 2 3; do
    TRACK_NUM=$(printf "%02d" $i)

    # Apply smaller pitch shift and convert to WAV (strips metadata)
    ffmpeg -i "$ALBUM_D1/$TRACK_NUM - Song $i.flac" \
           -af "asetrate=44100*1.0145,aresample=44100" \
           -y "$ALBUM_D4/temp-$i.wav" -loglevel error

    # Convert WAV to MP3 with NEW metadata (no MB ID)
    ffmpeg -i "$ALBUM_D4/temp-$i.wav" -c:a libmp3lame -b:a 320k \
           -metadata "title=Song $i" \
           -metadata "artist=Test Artist D" \
           -metadata "album=Test Album D (Enhanced)" \
           -metadata "track=$i/3" \
           -y "$ALBUM_D4/$TRACK_NUM - Song $i.mp3" -loglevel error

    rm "$ALBUM_D4/temp-$i.wav"
done

echo "  ✓ Created Album D - Slightly Pitched"

echo ""
echo "========================================="
echo "Test albums with varying similarity created!"
echo "========================================="
echo ""
echo "Album D variants (produce different similarity percentages):"
echo "  - Original (FLAC): Reference version with MusicBrainz ID"
echo "  - Pitched +0.5 semitones: ~97% match (fingerprint only, no MB ID)"
echo "  - Time Stretched 1.05x: Different % match (fingerprint only, no MB ID)"
echo "  - Pitched +0.25 semitones: ~98-99% match (fingerprint only, no MB ID)"
echo ""
echo "To verify actual similarity percentages:"
echo "  duperscooper --album-mode $TEST_ALBUMS_DIR"
echo ""
echo "Note: Actual similarity may vary. Run duperscooper to verify."
