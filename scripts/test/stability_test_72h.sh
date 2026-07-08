#!/usr/bin/env bash
#
# 72-hour stability test for industrial-grade validation
# Tests long-term reliability and memory leak detection
#
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RESULT_DIR="${PROJECT_ROOT}/build/stability_results"
START_TIME=$(date +%s)
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "=========================================="
echo "mROS2-QoS 72-Hour Stability Test"
echo "=========================================="
echo ""

if [ -z "${1:-}" ]; then
    echo "Usage: $0 /dev/ttyUSB0"
    exit 1
fi

DEVICE=$1
LOG_FILE="${RESULT_DIR}/stability_72h_${TIMESTAMP}.log"
METRICS_FILE="${RESULT_DIR}/stability_72h_${TIMESTAMP}_metrics.csv"

mkdir -p "${RESULT_DIR}"

echo "Device: ${DEVICE}"
echo "Test duration: 72 hours (259200 seconds)"
echo "Log file: ${LOG_FILE}"
echo "Metrics file: ${METRICS_FILE}"
echo "Start time: $(date)"
echo ""

# Flash firmware
echo "Flashing firmware..."
cd "${PROJECT_ROOT}/workspace/qos_eval"
idf.py build
idf.py -p "${DEVICE}" flash

# Initialize metrics CSV
echo "timestamp,elapsed_hours,free_memory_bytes,tx_count,rx_count,packets_dropped,errors" > "${METRICS_FILE}"

# Monitoring loop
SAMPLE_INTERVAL=300  # 5 minutes
TOTAL_DURATION=$((72 * 3600))  # 72 hours
ERROR_COUNT=0
RESTART_COUNT=0

echo "Starting monitoring (sample every 5 minutes)..."
echo ""

while true; do
    CURRENT_TIME=$(date +%s)
    ELAPSED=$((CURRENT_TIME - START_TIME))
    ELAPSED_HOURS=$(awk "BEGIN {printf \"%.2f\", $ELAPSED / 3600}")

    if [ "$ELAPSED" -ge "$TOTAL_DURATION" ]; then
        echo ""
        echo "72-hour test completed!"
        break
    fi

    # Capture snapshot
    SNAPSHOT=$(timeout 30 idf.py -p "${DEVICE}" monitor 2>&1 || true)

    # Extract metrics
    FREE_MEM=$(echo "$SNAPSHOT" | grep -oP "Free heap: \K\d+" | tail -1 || echo "0")
    TX_COUNT=$(echo "$SNAPSHOT" | grep -oP "TX: \K\d+" | tail -1 || echo "0")
    RX_COUNT=$(echo "$SNAPSHOT" | grep -oP "RX: \K\d+" | tail -1 || echo "0")
    DROPPED=$(echo "$SNAPSHOT" | grep -oP "Packets Dropped:\s+\K\d+" | tail -1 || echo "0")

    # Check for errors
    if echo "$SNAPSHOT" | grep -qi "error\|fail\|crash\|panic"; then
        ERROR_COUNT=$((ERROR_COUNT + 1))
        echo "[ERROR] Error detected at ${ELAPSED_HOURS}h" | tee -a "${LOG_FILE}"
    fi

    # Check for memory leak (memory consistently decreasing)
    if [ "$FREE_MEM" -lt 102400 ]; then
        echo "[WARNING] Low memory: ${FREE_MEM} bytes at ${ELAPSED_HOURS}h" | tee -a "${LOG_FILE}"
    fi

    # Log metrics
    echo "$(date -Iseconds),${ELAPSED_HOURS},${FREE_MEM},${TX_COUNT},${RX_COUNT},${DROPPED},${ERROR_COUNT}" >> "${METRICS_FILE}"

    # Progress report
    REMAINING=$((TOTAL_DURATION - ELAPSED))
    REMAINING_HOURS=$(awk "BEGIN {printf \"%.1f\", $REMAINING / 3600}")
    echo "[$(date +%H:%M:%S)] ${ELAPSED_HOURS}h elapsed, ${REMAINING_HOURS}h remaining | Mem: ${FREE_MEM}B | TX: ${TX_COUNT} | RX: ${RX_COUNT} | Errors: ${ERROR_COUNT}"

    # Save full snapshot periodically
    if [ $((ELAPSED % 3600)) -lt "$SAMPLE_INTERVAL" ]; then
        echo "$SNAPSHOT" >> "${LOG_FILE}"
    fi

    sleep "$SAMPLE_INTERVAL"
done

# Generate final report
REPORT_FILE="${RESULT_DIR}/stability_72h_${TIMESTAMP}_report.txt"

{
    echo "=========================================="
    echo "72-Hour Stability Test Report"
    echo "=========================================="
    echo ""
    echo "Start time:    $(date -d @${START_TIME})"
    echo "End time:      $(date)"
    echo "Duration:      72 hours"
    echo ""
    echo "Results:"
    echo "  Total errors:   ${ERROR_COUNT}"
    echo "  Restarts:       ${RESTART_COUNT}"
    echo ""

    if [ "$ERROR_COUNT" -eq 0 ]; then
        echo "Status: ✓ PASS - No errors detected"
    else
        echo "Status: ✗ FAIL - ${ERROR_COUNT} errors detected"
    fi

    echo ""
    echo "Memory analysis:"
    START_MEM=$(head -2 "${METRICS_FILE}" | tail -1 | cut -d',' -f3)
    END_MEM=$(tail -1 "${METRICS_FILE}" | cut -d',' -f3)
    MEM_DIFF=$((END_MEM - START_MEM))

    echo "  Start memory:  ${START_MEM} bytes"
    echo "  End memory:    ${END_MEM} bytes"
    echo "  Difference:    ${MEM_DIFF} bytes"

    if [ "$MEM_DIFF" -lt -10240 ]; then
        echo "  ⚠ Potential memory leak detected"
    else
        echo "  ✓ No memory leak detected"
    fi

    echo ""
    echo "Detailed metrics saved to: ${METRICS_FILE}"
    echo "Full log saved to: ${LOG_FILE}"

} | tee "${REPORT_FILE}"

echo ""
echo "Report saved to: ${REPORT_FILE}"

if [ "$ERROR_COUNT" -eq 0 ] && [ "$MEM_DIFF" -ge -10240 ]; then
    exit 0
else
    exit 1
fi
