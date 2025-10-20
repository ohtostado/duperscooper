#!/usr/bin/env python3
"""Test fpcalc with different -length values."""

import subprocess
import time
from pathlib import Path

test_file = Path("/Volumes/media/audio/music/complete/lossy/by-artist/e/Escape Tank/[1996] Escape Tank [Instinct Ambient AMB008-2]/01 - Born With Wings.mp3")

if not test_file.exists():
    print(f"Test file not found: {test_file}")
    exit(1)

print(f"File: {test_file.name}")
print(f"Size: {test_file.stat().st_size / (1024*1024):.2f} MB\n")

tests = [
    ("No -length (default)", ["fpcalc", "-raw", str(test_file)]),
    ("-length 60", ["fpcalc", "-raw", "-length", "60", str(test_file)]),
    ("-length 120", ["fpcalc", "-raw", "-length", "120", str(test_file)]),
    ("-length 0 (full)", ["fpcalc", "-raw", "-length", "0", str(test_file)]),
]

results = []
for name, cmd in tests:
    print(f"Testing: {name}")
    print(f"  Command: {' '.join(cmd)}")
    t_start = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    t_elapsed = time.time() - t_start
    
    # Count fingerprint length
    for line in result.stdout.split('\n'):
        if line.startswith('FINGERPRINT='):
            fp_count = len(line.split('=')[1].split(','))
            break
    else:
        fp_count = 0
    
    results.append((name, t_elapsed, fp_count))
    print(f"  Time: {t_elapsed:.3f}s, Fingerprint ints: {fp_count}\n")

print("=" * 60)
print("SUMMARY")
print("=" * 60)
for name, elapsed, fp_count in results:
    print(f"{name:20s}: {elapsed:.3f}s  ({fp_count} ints)")
