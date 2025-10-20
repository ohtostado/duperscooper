#!/usr/bin/env python3
"""Test AudioHasher performance with different fingerprint lengths."""

import sys
sys.path.insert(0, 'src')

from duperscooper.hasher import AudioHasher
from pathlib import Path
import time

test_file = Path("/Volumes/media/audio/music/complete/lossy/by-artist/e/Escape Tank/[1996] Escape Tank [Instinct Ambient AMB008-2]/01 - Born With Wings.mp3")

print(f"Testing AudioHasher with file: {test_file.name}\n")

configs = [
    ("Default (120s)", 120),
    ("Fast (60s)", 60),
    ("Full file (0)", 0),
]

for name, fp_length in configs:
    hasher = AudioHasher(use_cache=False, fingerprint_length=fp_length)
    
    print(f"Testing: {name} (fingerprint_length={fp_length})")
    t_start = time.time()
    fingerprint = hasher.compute_raw_fingerprint(test_file, fingerprint_length=fp_length)
    t_elapsed = time.time() - t_start
    
    print(f"  Time: {t_elapsed:.3f}s")
    print(f"  Fingerprint length: {len(fingerprint)} integers\n")

print("Expected: 60s should be fastest, 120s should be middle, 0 should be slowest")
