#!/usr/bin/env bash
#
# E1: Three-System RTT Comparison
# Tests: mROS2-QoS, upstream mros2-esp32, micro-ROS
# N=30 per system, interleaved execution
#
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

echo "========================================="
echo "E1: Three-System RTT Comparison"
echo "========================================="
echo "Systems: mROS2-QoS, upstream, micro-ROS"
echo "N=30 per system, interleaved"
echo "Estimated time: 4 hours"
echo ""
echo "[auto] Starting in 3 seconds..."
sleep 3

START_TIME=$(date +%s)

# Test mROS2-QoS (current system, already flashed from G2)
echo ""
echo "========================================="
echo "Testing: mROS2-QoS (RELIABLE)"
echo "========================================="
"${SCRIPT_DIR}/run_matrix.sh" "mros2qos" "reliable_baseline" 30

echo ""
echo "========================================="
echo "E1 Complete"
echo "========================================="

END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))

echo "Total time: $((ELAPSED / 3600))h $((ELAPSED % 3600 / 60))m"
echo ""
echo "Results:"
echo "  mROS2-QoS: results/experiments/$(date +%Y%m%d)/mros2qos_reliable_baseline.csv"
echo ""
echo "Next steps:"
echo "  1. Test upstream mros2-esp32 (need to flash upstream firmware)"
echo "  2. Test micro-ROS (need to flash micro-ROS firmware + start agent)"
echo "  3. Generate box plots + CDF from CSV files"
echo ""
echo "Note: Upstream and micro-ROS testing require different firmware."
echo "      Run those manually or create separate scripts."
