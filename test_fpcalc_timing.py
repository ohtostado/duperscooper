#!/usr/bin/env python3
"""Test fpcalc timing with and without -length parameter."""

import subprocess
import time
from pathlib import Path

# Find a test audio file
test_file = Path("/Volumes/media/audio/music/complete/lossy/by-artist/e/Escape Tank/[1996] Escape Tank [Instinct Ambient AMB008-2]/01 - Born With Wings.mp3")

if not test_file.exists():
    print(f"Test file not found: {test_file}")
    exit(1)

print(f"Testing with file: {test_file.name}")
print(f"File size: {test_file.stat().st_size / (1024*1024):.2f} MB\n")

# Test 1: With -length 120 (our optimization)
print("=" * 60)
print("TEST 1: fpcalc -raw -length 120")
print("=" * 60)
cmd1 = ["fpcalc", "-raw", "-length", "120", str(test_file)]
print(f"Command: {' '.join(cmd1)}\n")
t1_start = time.time()
result1 = subprocess.run(cmd1, capture_output=True, text=True, check=True)
t1_elapsed = time.time() - t1_start
print(f"Time elapsed: {t1_elapsed:.3f}s")
print(f"Output preview: {result1.stdout[:200]}")

# Test 2: Without -length (full file)
print("\n" + "=" * 60)
print("TEST 2: fpcalc -raw (no -length, full file)")
print("=" * 60)
cmd2 = ["fpcalc", "-raw", str(test_file)]
print(f"Command: {' '.join(cmd2)}\n")
t2_start = time.time()
result2 = subprocess.run(cmd2, capture_output=True, text=True, check=True)
t2_elapsed = time.time() - t2_start
print(f"Time elapsed: {t2_elapsed:.3f}s")
print(f"Output preview: {result2.stdout[:200]}")

# Compare
print("\n" + "=" * 60)
print("COMPARISON")
print("=" * 60)
print(f"With -length 120: {t1_elapsed:.3f}s")
print(f"Without -length:  {t2_elapsed:.3f}s")
print(f"Speedup: {t2_elapsed/t1_elapsed:.2f}x")
