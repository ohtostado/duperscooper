# Test Album Scenarios

This directory contains various test scenarios for duperscooper album mode.

## Baseline Albums (16 folders)

### AlbumA: "Dirty Deeds Done Dirt Cheap" by AC/DC (9 tracks)

- `AlbumA-FLAC-with-MB` - FLAC 96kHz/24bit with MusicBrainz ID
- `AlbumA-FLAC-no-MB` - FLAC 96kHz/24bit without any tags
- `AlbumA-MP3-with-MB-320` - MP3 320kbps with MusicBrainz ID
- `AlbumA-MP3-with-MB-128` - MP3 128kbps with MusicBrainz ID
- `AlbumA-MP3-with-MB-064` - MP3 64kbps with MusicBrainz ID
- `AlbumA-MP3-no-MB-320` - MP3 320kbps without any tags
- `AlbumA-MP3-no-MB-128` - MP3 128kbps without any tags
- `AlbumA-MP3-no-MB-064` - MP3 64kbps without any tags

### AlbumB: "Spanking Machine" by Babes in Toyland

(11 tracks originally, 10 in some copies)

- `AlbumB-FLAC-with-MB` - FLAC 44.1kHz/16bit with MusicBrainz ID
- `AlbumB-FLAC-no-MB` - FLAC 44.1kHz/16bit without any tags
- `AlbumB-MP3-with-MB-320` - MP3 320kbps with MusicBrainz ID
- `AlbumB-MP3-with-MB-128` - MP3 128kbps with MusicBrainz ID
- `AlbumB-MP3-with-MB-064` - MP3 64kbps with MusicBrainz ID
- `AlbumB-MP3-no-MB-320` - MP3 320kbps without any tags
- `AlbumB-MP3-no-MB-128` - MP3 128kbps without any tags
- `AlbumB-MP3-no-MB-064` - MP3 64kbps without any tags

**Expected Result:** All 8 AlbumA folders should match as one group.
All 8 AlbumB folders should match as one group.

---

## Test Scenario 1: Mixed MusicBrainz IDs Within Album

### Scenario 1 Test Folders

- `AlbumA-FLAC-MIXED-MB-IDs` - Tracks 1-2 have correct MB ID,
  tracks 3-9 have different fake MB ID

**Purpose:** Test detection of inconsistent MusicBrainz IDs within a
single album

**Expected Behavior:**

- Should set `has_mixed_mb_ids=True`
- Should NOT match by MusicBrainz Album ID (conflicting IDs)
- Should fall back to fingerprint matching
- Should still match with other AlbumA copies via fingerprints
- Match method: "Acoustic Fingerprint" (not MB ID)

---

## Test Scenario 2: ID3 Tags Only (No MusicBrainz IDs)

### Scenario 2 Test Folders

- `AlbumA-MP3-ID3-ONLY-320` - MP3 320kbps with album/artist tags
  but MB ID removed
- `AlbumB-MP3-ID3-ONLY-320` - MP3 320kbps with album/artist tags
  but MB ID removed

**Purpose:** Test matching via ID3 album/artist tags when MusicBrainz
IDs are absent

**Expected Behavior:**

- Should be treated as "canonical" (has album+artist metadata)
- Should match with other AlbumA/AlbumB copies
- Match method: "ID3 Album/Artist Tags"
- Should contribute to matched_album and matched_artist identification

---

## Test Scenario 3: Partial Albums (Missing Tracks)

### Scenario 3 Test Folders

- `AlbumA-FLAC-PARTIAL-missing-2-tracks` - FLAC with only 7 tracks
  (missing tracks 4 and 6)
- `AlbumB-MP3-PARTIAL-missing-3-tracks` - MP3 128kbps with only
  7 tracks (missing tracks 2, 8, 10)

**Purpose:** Test that albums with different track counts are NOT
incorrectly matched

**Expected Behavior:**

- Should NOT match with complete AlbumA copies (9 tracks ≠ 7 tracks)
- Should NOT match with complete AlbumB copies (10/11 tracks ≠ 7 tracks)
- Should NOT appear in duplicate groups (need 2+ albums with same
  track count)
- This is by design for Phase 1-5 (exact track count matching only)
- Future Phase 6 will handle partial album detection

---

## Test Summary

Total test folders: 16 baseline + 5 test scenarios = 21 folders

Expected duplicate groups with current implementation:

1. **AlbumA group** (9 tracks): 8 baseline + 1 ID3-only + 1 mixed-MB
   = 10 albums
2. **AlbumB group** (10 tracks): 8 baseline + 1 ID3-only = 9 albums
3. **AlbumA partial** (7 tracks): No match (only 1 album)
4. **AlbumB partial** (7 tracks): No match (only 1 album)

The partial albums should be ignored in current output (< 2 albums in
group).
