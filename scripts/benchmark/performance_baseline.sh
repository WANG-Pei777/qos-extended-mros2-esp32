#!/usr/bin/env bash
#
# Performance baseline measurement for mROS2-QoS
# Establishes performance metrics for optimization tracking
#
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RESULT_DIR="${PROJECT_ROOT}/build/performance_results"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "=========================================="
echo "mROS2-QoS Performance Baseline"
echo "=========================================="
echo ""

mkdir -p "${RESULT_DIR}"

# Check if ESP32 is connected
if [ -z "${1:-}" ]; then
    echo "Usage: $0 /dev/ttyUSB0"
    exit 1
fi

DEVICE=$1
RESULT_FILE="${RESULT_DIR}/baseline_${TIMESTAMP}.json"

echo "Device: ${DEVICE}"
echo "Results will be saved to: ${RESULT_FILE}"
echo ""

# Flash the performance test firmware
echo "[1/3] Building and flashing performance test firmware..."
cd "${PROJECT_ROOT}/workspace/qos_eval"

# Build
idf.py build || {
    echo "Build failed"
    exit 1
}

# Flash
idf.py -p "${DEVICE}" flash || {
    echo "Flash failed"
    exit 1
}

echo ""
echo "[2/3] Running performance test (60 seconds)..."

# Start monitoring
MONITOR_OUTPUT=$(mktemp)
timeout 60 idf.py -p "${DEVICE}" monitor > "${MONITOR_OUTPUT}" 2>&1 || true

echo ""
echo "[3/3] Analyzing results..."

# Extract metrics from logs
THROUGHPUT=$(grep -oP "TX: \K\d+" "${MONITOR_OUTPUT}" | tail -1 || echo "0")
RX_COUNT=$(grep -oP "RX: \K\d+" "${MONITOR_OUTPUT}" | tail -1 || echo "0")
LATENCY=$(grep -oP "Avg latency: \K[\d.]+ms" "${MONITOR_OUTPUT}" | tail -1 || echo "0")
FREE_MEMORY=$(grep -oP "Free heap: \K\d+" "${MONITOR_OUTPUT}" | tail -1 || echo "0")
PACKETS_DROPPED=$(grep -oP "Packets Dropped:\s+\K\d+" "${MONITOR_OUTPUT}" | tail -1 || echo "0")

# Calculate throughput (messages per second)
if [ "$THROUGHPUT" -gt 0 ]; then
    MSG_PER_SEC=$(awk "BEGIN {print $THROUGHPUT / 60}")
else
    MSG_PER_SEC=0
fi

# Generate JSON report
cat > "${RESULT_FILE}" <<EOF
{
  "timestamp": "$(date -Iseconds)",
  "device": "${DEVICE}",
  "firmware": "qos_eval",
  "test_duration_seconds": 60,
  "metrics": {
    "throughput": {
      "total_messages": ${THROUGHPUT},
      "messages_per_second": ${MSG_PER_SEC},
      "unit": "msg/s"
    },
    "latency": {
      "average_ms": ${LATENCY},
      "unit": "milliseconds"
    },
    "memory": {
      "free_heap_bytes": ${FREE_MEMORY},
      "unit": "bytes"
    },
    "reliability": {
      "packets_dropped": ${PACKETS_DROPPED},
      "rx_count": ${RX_COUNT}
    }
  },
  "baseline_targets": {
    "throughput_target": 30,
    "latency_target": 15,
    "memory_target": 225280
  }
}
EOF

# Display results
echo ""
echo "=========================================="
echo "Performance Baseline Results"
echo "=========================================="
echo ""
echo "Throughput:"
echo "  Messages sent:    ${THROUGHPUT}"
echo "  Messages/second:  ${MSG_PER_SEC}"
echo "  Target:           >30 msg/s"
echo ""
echo "Latency:"
echo "  Average:          ${LATENCY} ms"
echo "  Target:           <15 ms"
echo ""
echo "Memory:"
echo "  Free heap:        ${FREE_MEMORY} bytes ($(awk "BEGIN {print ${FREE_MEMORY}/1024}") KB)"
echo "  Target:           >220 KB"
echo ""
echo "Reliability:"
echo "  RX count:         ${RX_COUNT}"
echo "  Packets dropped:  ${PACKETS_DROPPED}"
echo ""
echo "Results saved to: ${RESULT_FILE}"
echo ""

# Compare with targets
PASS_COUNT=0
FAIL_COUNT=0

if awk "BEGIN {exit !($MSG_PER_SEC > 30)}"; then
    echo "✓ Throughput: PASS"
    PASS_COUNT=$((PASS_COUNT + 1))
else
    echo "✗ Throughput: BELOW TARGET"
    FAIL_COUNT=$((FAIL_COUNT + 1))
fi

LATENCY_NUM=$(echo "${LATENCY}" | sed 's/ms//')
if awk "BEGIN {exit !($LATENCY_NUM < 15)}"; then
    echo "✓ Latency: PASS"
    PASS_COUNT=$((PASS_COUNT + 1))
else
    echo "✗ Latency: ABOVE TARGET"
    FAIL_COUNT=$((FAIL_COUNT + 1))
fi

if [ "$FREE_MEMORY" -gt 225280 ]; then
    echo "✓ Memory: PASS"
    PASS_COUNT=$((PASS_COUNT + 1))
else
    echo "✗ Memory: BELOW TARGET"
    FAIL_COUNT=$((FAIL_COUNT + 1))
fi

echo ""
echo "Score: ${PASS_COUNT}/3 targets met"

# Cleanup
rm -f "${MONITOR_OUTPUT}"

if [ "$FAIL_COUNT" -eq 0 ]; then
    exit 0
else
    exit 1
fi
