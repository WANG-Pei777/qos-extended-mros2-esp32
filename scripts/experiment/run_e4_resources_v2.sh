#!/usr/bin/env bash
#
# E4: Resource Occupancy (Fixed - Three Systems)
# Per EXPERIMENT_REMEDIATION_GUIDE §3.⑤
#
set -eo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DATE=$(date +%Y%m%d)
RESULTS_DIR="${PROJECT_ROOT}/results/experiments/${DATE}"
OUTPUT_CSV="${RESULTS_DIR}/e4_resource_occupancy_v2.csv"

mkdir -p "${RESULTS_DIR}"

echo "========================================="
echo "E4: Resource Occupancy (Three Systems)"
echo "========================================="
echo "Measuring Flash + Free Heap"
echo "Systems: mROS2-QoS, upstream, micro-ROS"
echo ""

# Initialize CSV
echo "system,flash_bytes,free_heap_bytes,run_id,commit_hash" > "${OUTPUT_CSV}"

COMMIT_HASH=$(cd "${PROJECT_ROOT}" && git rev-parse HEAD)

# === mROS2-QoS (current baseline) ===
echo "[E4] System 1: mROS2-QoS"
cd "${PROJECT_ROOT}/workspace/qos_eval"
FLASH_SIZE=$(stat -c %s build/qos_eval.bin 2>/dev/null || echo "0")
echo "  Flash: ${FLASH_SIZE} bytes"

# Get heap from recent serial logs
for i in 1 2 3; do
    LOG="${RESULTS_DIR}/mros2qos_reliable_0pct_run${i}_serial.log"
    if [ -f "${LOG}" ]; then
        HEAP=$(grep "Memory:" "${LOG}" | tail -1 | grep -oP '\d+(?= bytes free)' || echo "0")
        if [ "${HEAP}" != "0" ]; then
            echo "  Run ${i}: Free heap = ${HEAP} bytes"
            echo "mros2qos,${FLASH_SIZE},${HEAP},${i},${COMMIT_HASH}" >> "${OUTPUT_CSV}"
        fi
    fi
done

# === upstream mros2-esp32 ===
echo ""
echo "[E4] System 2: upstream mros2-esp32"
if [ -d ~/upstream_bench/mros2-esp32/workspace/echoreply_string ]; then
    cd ~/upstream_bench/mros2-esp32/workspace/echoreply_string
    FLASH_SIZE=$(stat -c %s build/echoreply_string.bin 2>/dev/null || echo "0")
    echo "  Flash: ${FLASH_SIZE} bytes"
    echo "  Note: Heap measurement requires flashing and running (deferred)"
    echo "upstream,${FLASH_SIZE},0,0,upstream_baseline" >> "${OUTPUT_CSV}"
else
    echo "  ⚠️  upstream_bench not found, skipping"
fi

# === micro-ROS ===
echo ""
echo "[E4] System 3: micro-ROS"
if [ -d ~/microros_bench ]; then
    echo "  Note: micro-ROS uses different build system"
    echo "  Flash/Heap measurement requires manual inspection (deferred)"
    echo "microros,0,0,0,microros_baseline" >> "${OUTPUT_CSV}"
else
    echo "  ⚠️  microros_bench not found, skipping"
fi

echo ""
echo "========================================="
echo "E4 Complete"
echo "========================================="
echo "Results: ${OUTPUT_CSV}"
echo ""
echo "Summary:"
cat "${OUTPUT_CSV}"
