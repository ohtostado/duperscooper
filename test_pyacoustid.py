#!/usr/bin/env python3
"""Test pyacoustid fingerprinting speed (what Picard uses)."""

import time
from pathlib import Path

try:
    import acoustid
except ImportError:
    print("pyacoustid not installed. Installing...")
    import subprocess
    subprocess.run(["pip3", "install", "pyacoustid"], check=True)
    import acoustid

test_dir = Path("/Volumes/media/audio/music/complete/lossy/by-artist/e/Escape Tank/[1996] Escape Tank [Instinct Ambient AMB008-2]")
tracks = sorted(test_dir.glob("*.mp3"))[:3]

print(f"Testing pyacoustid (Picard's fingerprinting library)")
print(f"Testing {len(tracks)} tracks\n")

total_time = 0
for track in tracks:
    print(f"{track.name}")
    t_start = time.time()
    
    try:
        duration, fingerprint = acoustid.fingerprint_file(str(track))
        t_elapsed = time.time() - t_start
        total_time += t_elapsed
        print(f"  Duration: {duration}s")
        print(f"  Time to fingerprint: {t_elapsed:.3f}s")
        print()
    except Exception as e:
        print(f"  Error: {e}\n")

print(f"Total time: {total_time:.3f}s")
print(f"Average per track: {total_time / len(tracks):.3f}s")
