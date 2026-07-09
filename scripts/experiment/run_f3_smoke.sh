#!/usr/bin/env bash
#
# F3 Smoke Test: Verify injection efficacy gate
# Quick test: 1% loss × 1 run to verify gate works
#
set -eo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

echo "========================================="
echo "F3 Smoke Test: Injection Efficacy Gate"
echo "========================================="
echo "Testing: 1% loss × 1 run"
echo ""

# Source ROS2 and echo
set +u
source /opt/ros/humble/setup.bash
source "${PROJECT_ROOT}/tools/echo_cpp/install/setup.bash"
set -u

# Clean processes
pkill -9 -f "echo_node_lossy" 2>/dev/null || true
sleep 2

# Start echo_node_lossy with 1% loss
HOST_LOG="/tmp/f3_smoke_host.log"
ros2 run echo_cpp echo_node_lossy --reliable --loss 0.01 > "${HOST_LOG}" 2>&1 &
ECHO_PID=$!
sleep 5

# Run 1 test
"${PROJECT_ROOT}/scripts/experiment/run_matrix.sh" "mros2qos" "f3_smoke_1pct" 1

# Check efficacy
DROPPED=$(grep -oE "Dropped: [0-9]+" "${HOST_LOG}" | tail -1 | grep -oE "[0-9]+" || echo "0")
echo ""
echo "========================================="
echo "F3 Gate Check"
echo "========================================="
echo "Dropped packets: ${DROPPED}"

if [ "${DROPPED}" -eq 0 ]; then
    echo "❌ FAIL: Injection ineffective (Dropped=0)"
    kill ${ECHO_PID} 2>/dev/null || true
    exit 1
else
    echo "✅ PASS: Efficacy confirmed (Dropped=${DROPPED})"
fi

# Cleanup
kill ${ECHO_PID} 2>/dev/null || true

echo ""
echo "F3 Smoke Test: ✅ PASS"
