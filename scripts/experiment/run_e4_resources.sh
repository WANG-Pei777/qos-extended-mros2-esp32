#!/usr/bin/env bash
#
# E4: Resource Occupancy (Flash + Free Heap)
# Fixed version with corrected parsing
#
set -eo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DATE=$(date +%Y%m%d)
RESULTS_DIR="${PROJECT_ROOT}/results/experiments/${DATE}"
OUTPUT_CSV="${RESULTS_DIR}/e4_resource_occupancy.csv"

mkdir -p "${RESULTS_DIR}"

echo "========================================="
echo "E4: Resource Occupancy"
echo "========================================="
echo "Measuring Flash + Free Heap for mROS2-QoS"
echo ""

# Initialize CSV
echo "system,flash_bytes,free_heap_bytes,run_id,notes" > "${OUTPUT_CSV}"

COMMIT_HASH=$(cd "${PROJECT_ROOT}" && git rev-parse HEAD)

# Get Flash size from binary file
cd "${PROJECT_ROOT}/workspace/qos_eval"
FLASH_SIZE=$(ls -l build/qos_eval.bin 2>/dev/null | awk '{print $5}' || echo "0")
echo "[E4] Flash size: ${FLASH_SIZE} bytes"

# Get Free Heap from existing E2 serial logs (reuse data)
HEAP_VALUES=()
for i in 1 2 3; do
    LOG="${RESULTS_DIR}/mros2qos_reliable_0pct_run${i}_serial.log"
    if [ -f "${LOG}" ]; then
        HEAP=$(grep "Memory:" "${LOG}" | tail -1 | grep -oP '\d+(?= bytes free)' || echo "0")
        if [ "${HEAP}" != "0" ]; then
            echo "[E4] Run ${i}: Free heap = ${HEAP} bytes (from E2 logs)"
            echo "mros2qos,${FLASH_SIZE},${HEAP},${i},commit=${COMMIT_HASH},reused_e2_log" >> "${OUTPUT_CSV}"
            HEAP_VALUES+=("${HEAP}")
        fi
    fi
done

echo ""
echo "========================================="
echo "E4 Complete"
echo "========================================="
echo "Results: ${OUTPUT_CSV}"
echo ""

# Calculate average
if [ ${#HEAP_VALUES[@]} -gt 0 ]; then
    AVG=$(awk '{s+=$1} END {print s/NR}' <<< "$(printf '%s\n' "${HEAP_VALUES[@]}")")
    echo "Flash: ${FLASH_SIZE} bytes"
    echo "Free Heap: ${AVG} bytes (avg, n=${#HEAP_VALUES[@]})"
fi
