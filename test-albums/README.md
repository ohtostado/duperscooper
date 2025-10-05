# Test Album Files (Album Mode)

This directory contains synthetic test albums for testing album-mode duplicate detection.

## Files

- **7 albums** (2.0 MB)
- **20 total tracks**
- Covers all matching scenarios: MusicBrainz ID, ID3 tags, fingerprint matching

## Test Albums

### Album A - Test Album A by Test Artist A

**4 versions** testing different matching strategies:

1. **AlbumA-FLAC-Full-Metadata** (3 tracks, FLAC)
   - Full metadata including MusicBrainz Album ID
   - MusicBrainz ID: `12345678-1234-5678-1234-567812345678`

2. **AlbumA-MP3-320-Full-Metadata** (3 tracks, MP3 320kbps)
   - Same metadata and MusicBrainz ID as #1
   - **Tests:** MusicBrainz ID matching across formats

3. **AlbumA-MP3-128-No-MusicBrainz** (3 tracks, MP3 128kbps)
   - Same audio content but NO MusicBrainz ID
   - Has album/artist ID3 tags only
   - **Tests:** ID3 tag matching without MusicBrainz

4. **AlbumA-FLAC-Untagged** (3 tracks, FLAC)
   - Same audio content but NO metadata at all
   - **Tests:** Fingerprint-only matching

**Audio:** Sine waves at 440, 540, 640 Hz (A, C#, E chord)

### Album B - Test Album B by Test Artist B

**2 versions** testing format conversion:

1. **AlbumB-FLAC-Full-Metadata** (3 tracks, FLAC)
   - Full metadata including MusicBrainz Album ID
   - MusicBrainz ID: `87654321-4321-8765-4321-876543218765`

2. **AlbumB-MP3-192-Full-Metadata** (3 tracks, MP3 192kbps)
   - Same metadata and MusicBrainz ID as #1
   - **Tests:** MusicBrainz ID matching

**Audio:** Sine waves at 294, 349, 392 Hz (D, F, G chord - different from Album A)

### Album C - Test Album C (Partial)

**1 version** testing partial album detection:

1. **AlbumC-Partial-Missing-Track-3** (2 tracks, FLAC)
   - Only tracks 1 and 2 (missing track 3)
   - MusicBrainz ID: `11111111-2222-3333-4444-555555555555`
   - **Tests:** Partial album scenarios

**Audio:** Sine waves at 660, 760 Hz (different from A and B)

## Expected Behavior

When running:
```bash
duperscooper --album-mode test-albums/
```

**Expected output:**
- **2 duplicate groups found**
- Album A group: 4 albums matched
  - Matched by: MusicBrainz ID (3 albums) + Fingerprint (1 untagged album)
- Album B group: 2 albums matched
  - Matched by: MusicBrainz ID

Album C should NOT appear in duplicate groups (only 1 album, no duplicates).

## Test Scenarios Covered

✅ MusicBrainz Album ID matching
✅ ID3 tag matching (album + artist)
✅ Acoustic fingerprint matching (untagged albums)
✅ Canonical matching (untagged albums inherit metadata from tagged versions)
✅ Format conversion (FLAC ↔ MP3 at various bitrates)
✅ Partial albums (missing tracks)

## Generation

These files were generated using:
```bash
./scripts/generate-test-audio.sh
```

All files are 5 seconds per track and use synthetic audio (sine waves) to avoid copyright issues.
