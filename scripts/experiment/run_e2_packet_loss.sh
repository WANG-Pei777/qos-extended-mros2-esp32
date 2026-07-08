#!/usr/bin/env bash
#
# E2: RELIABLE Value Under Packet Loss
# Tests: mROS2-QoS with RELIABLE vs BEST_EFFORT under controlled packet loss
# Loss rates: 0%, 1%, 5%, 10%, 20%
# N=30 per condition
#
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

echo "========================================="
echo "E2: RELIABLE Value Under Packet Loss"
echo "========================================="
echo "Testing RELIABLE vs BEST_EFFORT"
echo "Loss rates: 0%, 1%, 5%, 10%, 20%"
echo "N=30 per condition"
echo "Estimated time: 8 hours"
echo ""
echo "[auto] Starting in 3 seconds..."
sleep 3

START_TIME=$(date +%s)

# Source ROS2 and C++ echo
set +u
source /opt/ros/humble/setup.bash
source "${PROJECT_ROOT}/tools/echo_cpp/install/setup.bash"
set -u

# Test conditions: QoS × Loss Rate
CONDITIONS=(
    "reliable_0pct:0.0"
    "reliable_1pct:0.01"
    "reliable_5pct:0.05"
    "reliable_10pct:0.10"
    "reliable_20pct:0.20"
)

for COND in "${CONDITIONS[@]}"; do
    IFS=':' read -r LABEL LOSS <<< "${COND}"

    echo ""
    echo "========================================="
    echo "Testing: ${LABEL} (loss=${LOSS})"
    echo "========================================="

    # Start C++ echo node with packet loss
    ros2 run echo_cpp echo_node_lossy --reliable --loss ${LOSS} > /tmp/e2_echo_${LABEL}.log 2>&1 &
    ECHO_PID=$!
    trap "kill ${ECHO_PID} 2>/dev/null || true" EXIT

    sleep 5

    # Run N=30 tests
    "${SCRIPT_DIR}/run_matrix.sh" "mros2qos" "${LABEL}" 30

    # Kill echo node
    kill ${ECHO_PID} 2>/dev/null || true
    wait ${ECHO_PID} 2>/dev/null || true

    echo "[E2] ${LABEL} complete"
    sleep 5
done

END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))

echo ""
echo "========================================="
echo "E2 Complete"
echo "========================================="
echo "Total time: $((ELAPSED / 3600))h $((ELAPSED % 3600 / 60))m"
echo ""
echo "Results in: results/experiments/$(date +%Y%m%d)/"
echo ""
echo "Next: Analyze delivery rate vs packet loss"
echo "      RELIABLE should maintain high delivery rate"
echo "      Plot: Loss Rate (x) vs Delivery Rate (y)"
