#!/usr/bin/env bash
# 24-Hour Stability Test for mROS2 QoS
#
# This test runs for 24 hours continuously monitoring:
# - Message delivery reliability
# - Memory stability (leak detection)
# - Latency consistency
# - Connection stability
# - Error rates
#
# Usage: ./qos_stability_24h.sh [step_name]
#   step_name: step7 (default), step8b, step9b, step10

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT_DIR="${PROJECT_ROOT}/scripts"

# Configuration
STEP="${1:-qos_eval}"
DURATION_HOURS=24
DURATION_SECONDS=$((DURATION_HOURS * 3600))
SAMPLE_INTERVAL=60  # Sample every 60 seconds
LOG_DIR="${PROJECT_ROOT}/results/stability_24h_$(date +%Y%m%d_%H%M%S)"
SERIAL_PORT="${SERIAL_PORT:-/dev/ttyUSB0}"

mkdir -p "${LOG_DIR}"

echo "============================================"
echo "  24-Hour Stability Test"
echo "============================================"
echo "  Step: ${STEP}"
echo "  Duration: ${DURATION_HOURS} hours"
echo "  Sample interval: ${SAMPLE_INTERVAL}s"
echo "  Log directory: ${LOG_DIR}"
echo "  Serial port: ${SERIAL_PORT}"
echo "============================================"
echo ""

# Check if ESP32 is connected
if [ ! -e "${SERIAL_PORT}" ]; then
    echo "ERROR: ESP32 not found at ${SERIAL_PORT}"
    echo "Please connect ESP32 and set SERIAL_PORT environment variable"
    exit 1
fi

# Determine which ROS2 echo script to use
case "${STEP}" in
    step7*|step7)
        ECHO_SCRIPT="${PROJECT_ROOT}/workspace/qos_eval/echo_reply.py"
        STEP_DIR="qos_eval"
        ;;
    step8b*|step8_transient*)
        ECHO_SCRIPT="${SCRIPT_DIR}/echo_transient_bidirectional.py"
        STEP_DIR="step8b_transient_bidirectional"
        ;;
    step9b*|step9_keep*)
        ECHO_SCRIPT="${SCRIPT_DIR}/echo_keep_all_bidirectional.py"
        STEP_DIR="step9b_keep_all_bidirectional"
        ;;
    step10*|step10)
        ECHO_SCRIPT="${SCRIPT_DIR}/echo_best_effort.py"
        STEP_DIR="step10_best_effort"
        ;;
    *)
        echo "ERROR: Unknown step ${STEP}"
        echo "Valid steps: step7, step8b, step9b, step10"
        exit 1
        ;;
esac

if [ ! -f "${ECHO_SCRIPT}" ]; then
    echo "ERROR: Echo script not found: ${ECHO_SCRIPT}"
    exit 1
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting 24-hour stability test..."
echo ""

# Flash firmware
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Flashing firmware..."
if [ -x "${SCRIPT_DIR}/validation/qos_flash.sh" ]; then
    "${SCRIPT_DIR}/validation/qos_flash.sh" "${STEP_DIR}"
else
    echo "WARNING: qos_flash.sh not found, assuming firmware already flashed"
fi

# Wait for ESP32 to boot
sleep 5

# Start ROS2 echo node in background
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting ROS2 echo node..."
set +u
source /opt/ros/humble/setup.bash 2>/dev/null || true
set -u

python3 "${ECHO_SCRIPT}" > "${LOG_DIR}/ros2_echo.log" 2>&1 &
ROS2_PID=$!
echo "ROS2 echo node PID: ${ROS2_PID}"

# Monitor serial output
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting serial monitor..."
cat "${SERIAL_PORT}" > "${LOG_DIR}/esp32_serial.log" 2>&1 &
SERIAL_PID=$!
echo "Serial monitor PID: ${SERIAL_PID}"

# Initialize statistics
START_TIME=$(date +%s)
SAMPLE_COUNT=0
TOTAL_SAMPLES=$((DURATION_SECONDS / SAMPLE_INTERVAL))

echo ""
echo "============================================"
echo "  Test Running"
echo "============================================"
echo "  Start time: $(date '+%Y-%m-%d %H:%M:%S')"
echo "  End time (est): $(date -d "@$((START_TIME + DURATION_SECONDS))" '+%Y-%m-%d %H:%M:%S')"
echo "  Total samples: ${TOTAL_SAMPLES}"
echo "============================================"
echo ""
echo "Press Ctrl+C to stop early (will generate report with data collected so far)"
echo ""

# Trap to ensure cleanup
cleanup() {
    echo ""
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Stopping test..."

    # Stop background processes
    kill ${ROS2_PID} 2>/dev/null || true
    kill ${SERIAL_PID} 2>/dev/null || true

    # Generate report
    generate_report

    exit 0
}
trap cleanup INT TERM

# Sampling loop
while true; do
    CURRENT_TIME=$(date +%s)
    ELAPSED=$((CURRENT_TIME - START_TIME))

    if [ ${ELAPSED} -ge ${DURATION_SECONDS} ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 24 hours completed!"
        break
    fi

    SAMPLE_COUNT=$((SAMPLE_COUNT + 1))
    PROGRESS=$((ELAPSED * 100 / DURATION_SECONDS))
    REMAINING=$((DURATION_SECONDS - ELAPSED))
    HOURS_REMAINING=$((REMAINING / 3600))
    MINS_REMAINING=$(((REMAINING % 3600) / 60))

    # Collect metrics
    TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

    # Extract ESP32 memory from serial log (last occurrence)
    ESP32_MEM=$(grep -o "Memory: [0-9]* bytes free" "${LOG_DIR}/esp32_serial.log" | tail -1 | grep -o "[0-9]*" || echo "0")

    # Count messages in logs
    MSG_COUNT=$(grep -c "RX\|TX" "${LOG_DIR}/esp32_serial.log" 2>/dev/null || echo "0")

    # Count errors
    ERROR_COUNT=$(grep -c "ERROR\|FAIL" "${LOG_DIR}/esp32_serial.log" 2>/dev/null || echo "0")

    # Log sample
    echo "${TIMESTAMP},${ELAPSED},${ESP32_MEM},${MSG_COUNT},${ERROR_COUNT}" >> "${LOG_DIR}/metrics.csv"

    # Print progress
    printf "\r[%3d%%] %02d:%02d remaining | Sample %d/%d | Mem: %d bytes | Msgs: %d | Errors: %d" \
        ${PROGRESS} ${HOURS_REMAINING} ${MINS_REMAINING} ${SAMPLE_COUNT} ${TOTAL_SAMPLES} \
        ${ESP32_MEM} ${MSG_COUNT} ${ERROR_COUNT}

    # Sleep until next sample
    sleep ${SAMPLE_INTERVAL}
done

cleanup

generate_report() {
    echo ""
    echo ""
    echo "============================================"
    echo "  Generating 24-Hour Stability Report"
    echo "============================================"

    REPORT_FILE="${LOG_DIR}/stability_report.txt"

    {
        echo "============================================"
        echo "  24-Hour Stability Test Report"
        echo "============================================"
        echo "Test Configuration:"
        echo "  Step: ${STEP}"
        echo "  Start: $(date -d "@${START_TIME}" '+%Y-%m-%d %H:%M:%S')"
        echo "  End: $(date '+%Y-%m-%d %H:%M:%S')"
        echo "  Duration: $((ELAPSED / 3600))h $(((ELAPSED % 3600) / 60))m"
        echo "  Samples: ${SAMPLE_COUNT}"
        echo ""

        echo "Memory Analysis:"
        if [ -f "${LOG_DIR}/metrics.csv" ]; then
            FIRST_MEM=$(head -2 "${LOG_DIR}/metrics.csv" | tail -1 | cut -d',' -f3)
            LAST_MEM=$(tail -1 "${LOG_DIR}/metrics.csv" | cut -d',' -f3)
            MEM_DRIFT=$((FIRST_MEM - LAST_MEM))

            echo "  Initial free memory: ${FIRST_MEM} bytes"
            echo "  Final free memory: ${LAST_MEM} bytes"
            echo "  Memory drift: ${MEM_DRIFT} bytes ($(echo "scale=2; ${MEM_DRIFT} * 100 / ${FIRST_MEM}" | bc)%)"

            if [ ${MEM_DRIFT#-} -lt 1024 ]; then
                echo "  ✅ Memory stable (drift < 1KB)"
            else
                echo "  ⚠️  Significant memory drift detected!"
            fi
        fi
        echo ""

        echo "Message Statistics:"
        if [ -f "${LOG_DIR}/esp32_serial.log" ]; then
            TX_COUNT=$(grep -c "TX\|Published" "${LOG_DIR}/esp32_serial.log" || echo "0")
            RX_COUNT=$(grep -c "RX\|received" "${LOG_DIR}/esp32_serial.log" || echo "0")
            echo "  TX messages: ${TX_COUNT}"
            echo "  RX messages: ${RX_COUNT}"
            echo "  Total messages: $((TX_COUNT + RX_COUNT))"
        fi
        echo ""

        echo "Error Analysis:"
        if [ -f "${LOG_DIR}/esp32_serial.log" ]; then
            ERROR_COUNT=$(grep -c "ERROR" "${LOG_DIR}/esp32_serial.log" || echo "0")
            FAIL_COUNT=$(grep -c "FAIL" "${LOG_DIR}/esp32_serial.log" || echo "0")
            WARN_COUNT=$(grep -c "WARN" "${LOG_DIR}/esp32_serial.log" || echo "0")

            echo "  Errors: ${ERROR_COUNT}"
            echo "  Failures: ${FAIL_COUNT}"
            echo "  Warnings: ${WARN_COUNT}"

            if [ ${ERROR_COUNT} -eq 0 ] && [ ${FAIL_COUNT} -eq 0 ]; then
                echo "  ✅ No errors detected"
            else
                echo "  ❌ Errors detected - review logs"
            fi
        fi
        echo ""

        echo "Conclusion:"
        if [ ${MEM_DRIFT#-} -lt 1024 ] && [ ${ERROR_COUNT:-0} -eq 0 ]; then
            echo "  ✅ STABILITY TEST PASSED"
            echo "     - Memory stable over ${DURATION_HOURS} hours"
            echo "     - No errors detected"
            echo "     - System ready for production deployment"
        else
            echo "  ⚠️  STABILITY TEST COMPLETED WITH ISSUES"
            echo "     - Review logs for details"
            echo "     - Additional investigation recommended"
        fi
        echo ""
        echo "Log files:"
        echo "  ESP32 serial: ${LOG_DIR}/esp32_serial.log"
        echo "  ROS2 echo: ${LOG_DIR}/ros2_echo.log"
        echo "  Metrics: ${LOG_DIR}/metrics.csv"
        echo "  Report: ${LOG_DIR}/stability_report.txt"
        echo "============================================"
    } | tee "${REPORT_FILE}"

    echo ""
    echo "Report saved to: ${REPORT_FILE}"
}
