#!/usr/bin/env python3
"""Test parallel vs sequential fingerprinting performance."""

import sys
sys.path.insert(0, 'src')

from duperscooper.album import AlbumScanner
from duperscooper.hasher import AudioHasher
from pathlib import Path
import time

test_dir = Path("/Volumes/media/audio/music/complete/lossy/by-artist/e/Escape Tank/[1996] Escape Tank [Instinct Ambient AMB008-2]")

print(f"Testing album scanning with different worker counts")
print(f"Album: {test_dir.name}\n")

for workers in [1, 4, 8, 12]:
    hasher = AudioHasher(use_cache=False, fingerprint_length=120)
    scanner = AlbumScanner(hasher, verbose=False)
    
    print(f"Workers: {workers}")
    t_start = time.time()
    albums = scanner.scan_albums([test_dir], max_workers=workers)
    t_elapsed = time.time() - t_start
    
    print(f"  Time: {t_elapsed:.3f}s")
    print(f"  Tracks: {albums[0].track_count if albums else 0}")
    print()

print("Expected: More workers = faster (up to CPU core count)")
