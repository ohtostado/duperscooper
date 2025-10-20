#!/usr/bin/env python3
"""Test to reproduce Group 5 false positive bug."""

from pathlib import Path
from src.duperscooper.hasher import AudioHasher
from src.duperscooper.album import Album, AlbumDuplicateFinder

# Create mock albums matching Group 5
album1 = Album(
    path=Path("/fake/Escape Tank"),
    tracks=[Path("t1.mp3"), Path("t2.mp3"), Path("t3.mp3")],
    track_count=3,
    musicbrainz_albumid=None,
    album_name="Escape Tank",
    artist_name="Escape Tank",
    total_size=115255943,
    avg_quality_score=256.0,
    fingerprints=[[1,2,3], [4,5,6], [7,8,9]],  # dummy fingerprints
    has_mixed_mb_ids=False,
    quality_info="MP3 CBR 256kbps",
)

album2 = Album(
    path=Path("/fake/Tension Wire Fence"),
    tracks=[Path("t1.mp3"), Path("t2.mp3"), Path("t3.mp3")],
    track_count=3,
    musicbrainz_albumid=None,
    album_name="Tension Wire Fence Vol 1",
    artist_name="The Dark Outside",
    total_size=121621298,
    avg_quality_score=210.784,
    fingerprints=[[100,200,300], [400,500,600], [700,800,900]],  # very different
    has_mixed_mb_ids=False,
    quality_info="MP3 VBR 193kbps",
)

# Create hasher and finder
hasher = AudioHasher()
finder = AlbumDuplicateFinder(
    hasher,
    verbose=True,
    allow_partial=True,
    min_overlap=70.0,
    similarity_threshold=98.0,
)

# Calculate similarity
similarity = finder.album_similarity(album1, album2)
print(f"Album similarity: {similarity:.2f}%")
print(f"Threshold: {finder.similarity_threshold}%")
print(f"Should be grouped: {similarity >= finder.similarity_threshold}")

# Test Union-Find
groups = finder._union_find_similar_albums([album1, album2])
print(f"\nGroups found: {len(groups)}")
for i, group in enumerate(groups):
    print(f"  Group {i+1}: {len(group)} albums")
    for album in group:
        print(f"    - {album.album_name}")
