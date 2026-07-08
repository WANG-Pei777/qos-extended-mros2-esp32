#!/usr/bin/env bash
#
# E2 Re-run with validation: RELIABLE under packet loss
# First validates each condition with N=1, then runs N=30
#
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

echo "========================================="
echo "E2 Re-run: RELIABLE Under Packet Loss"
echo "========================================="
echo "Loss rates: 0%, 1%, 5%, 10%, 15%"
echo "Strategy: Validate N=1 first, then N=30"
echo ""

# Source ROS2 and C++ echo
set +u
source /opt/ros/humble/setup.bash
source "${PROJECT_ROOT}/tools/echo_cpp/install/setup.bash"
set -u

# Reduced loss rates (removed 20% which caused failure)
CONDITIONS=(
    "reliable_0pct:0.0"
    "reliable_1pct:0.01"
    "reliable_5pct:0.05"
    "reliable_10pct:0.10"
    "reliable_15pct:0.15"
)

for COND in "${CONDITIONS[@]}"; do
    IFS=':' read -r LABEL LOSS <<< "${COND}"

    echo ""
    echo "========================================="
    echo "Validating: ${LABEL} (loss=${LOSS})"
    echo "========================================="

    # Clean any existing echo processes first
    pkill -9 -f "echo_node_lossy" 2>/dev/null || true
    sleep 2

    # Start echo node
    ros2 run echo_cpp echo_node_lossy --reliable --loss ${LOSS} > /tmp/e2_echo_${LABEL}.log 2>&1 &
    ECHO_PID=$!
    sleep 5

    # Validate with N=1
    echo "[validate] Running N=1 test..."
    "${SCRIPT_DIR}/run_matrix.sh" "mros2qos" "${LABEL}_validate" 1

    # Check result - FIX: Extract matched_pub from data row, not header
    MATCHED=$(tail -1 /home/wsde-47/mROS2-QoS/results/experiments/$(date +%Y%m%d)/mros2qos_${LABEL}_validate.csv | awk -F, '{print $11}')

    if [ "${MATCHED}" = "1" ]; then
        echo "[OK] Validation passed (matched_pub=${MATCHED}), running N=30..."
        "${SCRIPT_DIR}/run_matrix.sh" "mros2qos" "${LABEL}" 30
    else
        echo "[FAIL] Validation failed (matched_pub=${MATCHED}), skipping N=30"
        echo "[FAIL] Check /tmp/e2_echo_${LABEL}.log for echo node issues"
    fi

    # Kill echo node explicitly
    kill ${ECHO_PID} 2>/dev/null || true
    wait ${ECHO_PID} 2>/dev/null || true

    # Double-check cleanup
    pkill -9 -f "echo_node_lossy.*${LOSS}" 2>/dev/null || true
    sleep 3
done

echo ""
echo "========================================="
echo "E2 Re-run Complete"
echo "========================================="
