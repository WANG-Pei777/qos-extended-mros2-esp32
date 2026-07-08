#!/usr/bin/env bash
#
# G5: Test C++ echo node
#
set -eo pipefail

echo "========================================="
echo "G5: Testing C++ Echo Node"
echo "========================================="
echo ""

# Source workspaces
set +u
source /opt/ros/humble/setup.bash
source /home/wsde-47/mROS2-QoS/tools/echo_cpp/install/setup.bash
set -u

# Start C++ echo node
echo "[test] Starting C++ echo node..."
ros2 run echo_cpp echo_node --reliable &
ECHO_PID=$!

sleep 3

# Check if running
if ! kill -0 ${ECHO_PID} 2>/dev/null; then
    echo "[FAIL] Echo node failed to start"
    exit 1
fi

echo "[OK] Echo node started successfully (PID: ${ECHO_PID})"
echo ""
echo "Usage for experiments:"
echo "  ros2 run echo_cpp echo_node --reliable"
echo "  ros2 run echo_cpp echo_node --best-effort"
echo ""

# Kill test node
kill ${ECHO_PID} 2>/dev/null || true

echo "========================================="
echo "G5: C++ Echo Node Ready"
echo "========================================="
