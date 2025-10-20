#!/usr/bin/env python3
"""Analyze actual Group 5 albums to understand why they were grouped."""

import json

# Load scan results
with open('scan-results.json') as f:
    data = json.load(f)

# Find Group 5
for group in data:
    if group.get('group_id') == 5:
        print("=== GROUP 5 ANALYSIS ===\n")
        print(f"Items in group: {len(group['items'])}")
        print(f"Similarity stats: {group['similarity_stats']}")
        print()
        
        for item in group['items']:
            print(f"Album: {item['album_name']}")
            print(f"  Artist: {item['artist_name']}")
            print(f"  Tracks: {item['track_count']}")
            print(f"  Match %: {item['match_percentage']:.2f}%")
            print(f"  Match method: {item['match_method']}")
            print(f"  Confidence: {item['confidence']}%")
            print(f"  Is best: {item['is_best']}")
            print()
        
        # The key question: if similarity is 49%, why were they grouped?
        print("\n=== HYPOTHESIS ===")
        print("Option 1: Bug in album_similarity() during grouping phase")
        print("Option 2: Bug in _get_album_match_percentage() during output phase (FIXED)")
        print("Option 3: Albums were actually similar during scan but files changed")
        print()
        print("The 49.28% shown is calculated AFTER grouping by _get_album_match_percentage.")
        print("We need to check if album_similarity() would have returned >=98% during grouping.")
        print()
        print("Since both albums have 3 tracks, album_similarity() does position-based")
        print("matching: avg(track1_sim, track2_sim, track3_sim)")
        print()
        print("If avg similarity was actually >=98% during grouping, but now shows 49%,")
        print("then the files must have changed OR the fingerprints are incomplete/corrupted.")
        break
