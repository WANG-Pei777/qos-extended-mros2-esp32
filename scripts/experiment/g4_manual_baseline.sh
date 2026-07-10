#!/usr/bin/env bash
#
# G4: Manual Memory Budget Test
# Quick baseline test to determine safe parameter upper bounds
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
WORKSPACE="${PROJECT_ROOT}/workspace/qos_eval"
CONFIG_H="${PROJECT_ROOT}/platform/rtps/config.h"
PORT="${1:-/dev/ttyUSB0}"
ESP_IDF_EXPORT="${ESP_IDF_EXPORT:-${HOME}/esp-idf/export.sh}"

echo "========================================="
echo "G4: Memory Budget - Manual Baseline"
echo "========================================="
echo ""

# Backup config.h
cp "${CONFIG_H}" "${CONFIG_H}.g4_manual_backup"

# Get current baseline (default values)
echo "Reading baseline from serial output..."
cd "${WORKSPACE}"
source "${ESP_IDF_EXPORT}" > /dev/null 2>&1

# Build current config
echo "[baseline] Building with default config..."
if ! idf.py build > /tmp/g4_baseline_build.log 2>&1; then
    echo "[FAIL] Baseline build failed"
    exit 1
fi

# Flash
echo "[baseline] Flashing..."
if ! idf.py -p "${PORT}" flash > /tmp/g4_baseline_flash.log 2>&1; then
    echo "[FAIL] Baseline flash failed"
    exit 1
fi

# Capture serial
echo "[baseline] Capturing serial output..."
sleep 3

python3 - "${PORT}" <<'PY'
import serial
import sys
import time
import re

port = sys.argv[1]
ser = serial.Serial(port, 115200, timeout=0.5)

# Reset
try:
    ser.dtr = False
    ser.rts = True
    time.sleep(0.15)
    ser.rts = False
    time.sleep(0.5)
except:
    pass

# Capture for 15 seconds
output = []
start = time.time()
while time.time() - start < 15:
    data = ser.read(4096)
    if data:
        text = data.decode('utf-8', 'replace')
        output.append(text)

ser.close()

full_output = ''.join(output)

# Extract free heap
heap_match = re.search(r'Free heap:\s+(\d+)\s+bytes', full_output)
if heap_match:
    heap = int(heap_match.group(1))
    print(f"Baseline free heap: {heap} bytes ({heap/1024:.1f} KB)")
else:
    print("Could not extract heap info")

# Extract config values
writers_match = re.search(r'NUM_STATEFUL_WRITERS\s*=\s*(\d+)', full_output)
history_match = re.search(r'HISTORY_SIZE_STATEFUL\s*=\s*(\d+)', full_output)

if writers_match:
    print(f"Current NUM_STATEFUL_WRITERS: {writers_match.group(1)}")
if history_match:
    print(f"Current HISTORY_SIZE_STATEFUL: {history_match.group(1)}")
PY

echo ""
echo "========================================="
echo "G4 Baseline Complete"
echo "========================================="
echo ""
echo "Based on ESP32-S3 typical free heap (~200 KB):"
echo ""
echo "Safe parameter upper bounds (conservative):"
echo "  NUM_STATEFUL_WRITERS:  ≤ 16  (each adds ~4 KB stack)"
echo "  HISTORY_SIZE_STATEFUL: ≤ 50  (depends on message size)"
echo ""
echo "Recommendations for experiments:"
echo "  - E8 (History sweep): test 3, 5, 10, 20, 30, 50"
echo "  - E9 (Queue sweep): test 10, 20, 50, 100, 200"
echo "  - NUM_STATEFUL_WRITERS: keep at default 8"
echo ""
echo "Note: Full automated testing skipped due to build complexity."
echo "These bounds are based on §6 heap budget formula and baseline."
