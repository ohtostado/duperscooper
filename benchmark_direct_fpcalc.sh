#!/bin/bash
# Benchmark calling fpcalc directly from shell vs from Python

TEST_DIR="/Volumes/media/audio/music/complete/lossy/by-artist/e/Escape Tank/[1996] Escape Tank [Instinct Ambient AMB008-2]"

echo "Benchmarking direct fpcalc calls (shell)"
echo "=========================================="

total=0
count=0
for f in "$TEST_DIR"/*.mp3; do
    if [ $count -ge 3 ]; then break; fi
    echo "$(basename "$f")"
    start=$(python3 -c 'import time; print(time.time())')
    fpcalc -raw "$f" > /dev/null
    end=$(python3 -c 'import time; print(time.time())')
    elapsed=$(python3 -c "print($end - $start)")
    echo "  Time: ${elapsed}s"
    total=$(python3 -c "print($total + $elapsed)")
    count=$((count + 1))
done

avg=$(python3 -c "print($total / $count)")
echo ""
echo "Average: ${avg}s per track"
