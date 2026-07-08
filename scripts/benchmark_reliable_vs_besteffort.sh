#!/bin/bash
# Performance benchmark: RELIABLE vs BEST_EFFORT comparison
# Runs step7 (RELIABLE) and captures performance, then reports

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="/dev/ttyUSB0"

echo "=== Performance Benchmark: RELIABLE vs BEST_EFFORT ==="
echo ""

# Test 1: Run step7 (RELIABLE) and capture metrics
echo "[Test 1] RELIABLE + VOLATILE + KEEP_LAST(5)"
echo "  Flashing step7..."
cd "$PROJECT_ROOT/workspace/qos_eval"
source ~/esp-idf/export.sh >/dev/null 2>&1
idf.py -p "$PORT" flash >/dev/null 2>&1

echo "  Running preflight..."
cd "$PROJECT_ROOT"
./scripts/validation/qos_ready.sh "$PORT" all >/dev/null 2>&1

LATEST=$(ls -td results/qos_preflight_20260614_*/ | head -1)
RELIABLE_TX=$(grep "TX:" "$LATEST/attempt_1_serial.log" 2>/dev/null | grep -o '[0-9]* msgs' | head -1)
RELIABLE_RX=$(grep "RX:" "$LATEST/attempt_1_serial.log" 2>/dev/null | grep -o '[0-9]* msgs' | head -1)
RELIABLE_THROUGHPUT=$(grep "throughput:" "$LATEST/attempt_1_serial.log" 2>/dev/null | grep -o '[0-9.]* msg/s' | head -1)
RELIABLE_LATENCY_MIN=$(grep "Min:" "$LATEST/attempt_1_serial.log" 2>/dev/null | grep -o '[0-9]* us' | head -1)
RELIABLE_LATENCY_MAX=$(grep "Max:" "$LATEST/attempt_1_serial.log" 2>/dev/null | grep -o '[0-9]* us' | head -1)
RELIABLE_LATENCY_AVG=$(grep "Avg:" "$LATEST/attempt_1_serial.log" 2>/dev/null | grep -o '[0-9]* us' | head -1)
RELIABLE_MEMORY=$(grep "Memory:" "$LATEST/attempt_1_serial.log" 2>/dev/null | grep -o '[0-9]* bytes free' | head -1)
RELIABLE_DROPS=$(grep "Packets Dropped:" "$LATEST/attempt_1_serial.log" 2>/dev/null | grep -o '[0-9]*' | head -1)

echo "  TX: $RELIABLE_TX"
echo "  RX: $RELIABLE_RX"
echo "  Throughput: $RELIABLE_THROUGHPUT"
echo "  Latency: $RELIABLE_LATENCY_MIN / $RELIABLE_LATENCY_AVG / $RELIABLE_LATENCY_MAX (min/avg/max)"
echo "  Memory: $RELIABLE_MEMORY"
echo "  Drops: $RELIABLE_DROPS"
echo ""

echo "=== Benchmark Complete ==="
echo ""
echo "| Metric | RELIABLE |"
echo "|--------|----------|"
echo "| TX | $RELIABLE_TX |"
echo "| RX | $RELIABLE_RX |"
echo "| Throughput | $RELIABLE_THROUGHPUT |"
echo "| Latency (min/avg/max) | $RELIABLE_LATENCY_MIN / $RELIABLE_LATENCY_AVG / $RELIABLE_LATENCY_MAX |"
echo "| Memory free | $RELIABLE_MEMORY |"
echo "| Packet drops | $RELIABLE_DROPS |"
