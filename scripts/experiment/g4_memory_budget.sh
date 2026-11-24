#!/usr/bin/env bash
#
# G4: Memory Budget - Test parameter upper bounds to prevent OOM
# Tests NUM_STATEFUL_WRITERS and HISTORY_SIZE_STATEFUL incrementally
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
CONFIG_H="${PROJECT_ROOT}/platform/rtps/config.h"
PORT="${1:-/dev/ttyUSB0}"

echo "========================================="
echo "G4: Memory Budget Testing"
echo "========================================="
echo "Testing parameter upper bounds to prevent OOM"
echo "Config: ${CONFIG_H}"
echo ""

# Backup config.h
cp "${CONFIG_H}" "${CONFIG_H}.g4_backup"
echo "[backup] Created: ${CONFIG_H}.g4_backup"

# Results file
RESULTS_CSV="${PROJECT_ROOT}/results/g4_memory_budget.csv"
mkdir -p "$(dirname "${RESULTS_CSV}")"
echo "parameter,value,free_heap_bytes,status,notes" > "${RESULTS_CSV}"

# Source ESP-IDF
set +u
source "${IDF_PATH:?Set IDF_PATH}/export.sh" > /dev/null 2>&1
set -u

test_config() {
    local param_name="$1"
    local param_value="$2"
    local line_pattern="$3"

    echo ""
    echo "========================================="
    echo "Testing: ${param_name} = ${param_value}"
    echo "========================================="

    # Modify config.h
    sed -i.bak "s/${line_pattern} [0-9]\+/${line_pattern} ${param_value}/" "${CONFIG_H}"

    # Build
    cd "${PROJECT_ROOT}"
    echo "[build] Compiling..."
    if ! idf.py build > /tmp/g4_build.log 2>&1; then
        echo "[FAIL] Build failed"
        echo "${param_name},${param_value},0,BUILD_FAIL,See /tmp/g4_build.log" >> "${RESULTS_CSV}"
        return 1
    fi

    # Flash
    echo "[flash] Flashing..."
    if ! idf.py -p "${PORT}" flash > /tmp/g4_flash.log 2>&1; then
        echo "[FAIL] Flash failed"
        echo "${param_name},${param_value},0,FLASH_FAIL,See /tmp/g4_flash.log" >> "${RESULTS_CSV}"
        return 1
    fi

    # Wait and capture serial output
    echo "[serial] Capturing boot sequence..."
    sleep 3

    # Reset and capture
    python3 - "${PORT}" <<'PY'
import serial
import sys
import time
import re

port = sys.argv[1]
ser = serial.Serial(port, 115200, timeout=0.5)

# Hardware reset
try:
    ser.dtr = False
    ser.rts = True
    time.sleep(0.15)
    ser.rts = False
except:
    pass

# Capture for 15 seconds
start = time.time()
output = []
while time.time() - start < 15:
    data = ser.read(4096)
    if data:
        text = data.decode('utf-8', 'replace')
        output.append(text)
        print(text, end='', flush=True)

ser.close()

# Parse free heap
full_output = ''.join(output)
heap_match = re.search(r'Free heap:\s+(\d+)\s+bytes', full_output)
if heap_match:
    heap = int(heap_match.group(1))
    print(f"\n[PARSED] Free heap: {heap} bytes", file=sys.stderr)
    sys.exit(0)
else:
    # Check if boot failed
    if 'abort()' in full_output or 'Guru Meditation' in full_output or 'LoadProhibited' in full_output:
        print("\n[PARSED] CRASH detected", file=sys.stderr)
        sys.exit(2)
    else:
        print("\n[PARSED] No heap info found", file=sys.stderr)
        sys.exit(1)
PY

    EXIT_CODE=$?

    if [ ${EXIT_CODE} -eq 0 ]; then
        # Extract heap from stderr
        HEAP=$(python3 - "${PORT}" <<'PY2' 2>&1 | grep "Free heap" | awk '{print $4}' || echo "0"
import sys
print("Free heap: 0 bytes")  # Placeholder, actual parsing done above
PY2
)
        # Get actual heap from the output above
        HEAP=$(grep "Free heap:" /tmp/g4_serial.log 2>/dev/null | tail -1 | grep -oP '\d+' || echo "unknown")
        echo "[OK] Free heap: ${HEAP} bytes"
        echo "${param_name},${param_value},${HEAP},OK,Booted successfully" >> "${RESULTS_CSV}"
        return 0
    elif [ ${EXIT_CODE} -eq 2 ]; then
        echo "[FAIL] System crashed (OOM or stack overflow)"
        echo "${param_name},${param_value},0,CRASH,OOM or stack overflow" >> "${RESULTS_CSV}"
        return 1
    else
        echo "[WARN] Could not parse heap info"
        echo "${param_name},${param_value},unknown,UNKNOWN,Boot status unclear" >> "${RESULTS_CSV}"
        return 0
    fi
}

# Test 1: NUM_STATEFUL_WRITERS
echo ""
echo "========================================="
echo "Test Series 1: NUM_STATEFUL_WRITERS"
echo "========================================="
echo "Current default: 8"
echo "Testing: 8 (baseline), 12, 16, 24, 32"
echo ""

for value in 8 12 16 24 32; do
    test_config "NUM_STATEFUL_WRITERS" "${value}" "const uint8_t NUM_STATEFUL_WRITERS ="

    # If crash, don't test higher values
    if grep -q "CRASH" "${RESULTS_CSV}" | tail -1; then
        echo "[STOP] Crashed at ${value}, stopping NUM_STATEFUL_WRITERS tests"
        break
    fi
done

# Restore default before next test
cp "${CONFIG_H}.g4_backup" "${CONFIG_H}"

# Test 2: HISTORY_SIZE_STATEFUL
echo ""
echo "========================================="
echo "Test Series 2: HISTORY_SIZE_STATEFUL"
echo "========================================="
echo "Current default: 10"
echo "Testing: 10 (baseline), 20, 30, 50, 100"
echo ""

for value in 10 20 30 50 100; do
    test_config "HISTORY_SIZE_STATEFUL" "${value}" "const uint8_t HISTORY_SIZE_STATEFUL ="

    if grep -q "CRASH" "${RESULTS_CSV}" | tail -1; then
        echo "[STOP] Crashed at ${value}, stopping HISTORY_SIZE_STATEFUL tests"
        break
    fi
done

# Restore original config
cp "${CONFIG_H}.g4_backup" "${CONFIG_H}"
echo ""
echo "========================================="
echo "G4: Memory Budget Testing Complete"
echo "========================================="
echo "Results: ${RESULTS_CSV}"
echo ""
cat "${RESULTS_CSV}"
echo ""
echo "Interpretation:"
echo "  - OK: Safe to use in experiments"
echo "  - CRASH: Upper bound reached, do not exceed"
echo "  - Recommended max values will be used in experiment config"
