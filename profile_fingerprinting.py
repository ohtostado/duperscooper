#!/usr/bin/env python3
"""Profile where time is spent during fingerprinting."""

import sys
sys.path.insert(0, 'src')

from duperscooper.hasher import AudioHasher
from pathlib import Path
import time

# Test with a real album
test_dir = Path("/Volumes/media/audio/music/complete/lossy/by-artist/e/Escape Tank/[1996] Escape Tank [Instinct Ambient AMB008-2]")
tracks = sorted(test_dir.glob("*.mp3"))[:3]  # First 3 tracks

print(f"Testing {len(tracks)} tracks from: {test_dir.name}\n")
print("=" * 70)

# Test WITHOUT cache
print("\nTEST 1: Without cache (measures pure fpcalc performance)")
print("=" * 70)
hasher = AudioHasher(use_cache=False, fingerprint_length=120)

total_time = 0
for track in tracks:
    print(f"\n{track.name}")
    t_start = time.time()
    fp = hasher.compute_audio_hash(track, algorithm="perceptual")
    t_elapsed = time.time() - t_start
    total_time += t_elapsed
    print(f"  Time: {t_elapsed:.3f}s")

print(f"\nTotal time: {total_time:.3f}s")
print(f"Average per track: {total_time / len(tracks):.3f}s")

# Test WITH cache (second run)
print("\n" + "=" * 70)
print("TEST 2: With cache (second run, should be faster)")
print("=" * 70)
hasher2 = AudioHasher(use_cache=True, fingerprint_length=120)

# First pass to populate cache
for track in tracks:
    hasher2.compute_audio_hash(track, algorithm="perceptual")

# Second pass (cached)
total_time2 = 0
for track in tracks:
    print(f"\n{track.name}")
    t_start = time.time()
    fp = hasher2.compute_audio_hash(track, algorithm="perceptual")
    t_elapsed = time.time() - t_start
    total_time2 += t_elapsed
    print(f"  Time: {t_elapsed:.3f}s")

print(f"\nTotal time: {total_time2:.3f}s")
print(f"Average per track: {total_time2 / len(tracks):.3f}s")
print(f"Speedup from cache: {total_time / total_time2:.1f}x")
