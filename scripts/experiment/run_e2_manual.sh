#!/usr/bin/env bash
#
# E2 Manual: Run N=30 for validated conditions (0% and 1%)
#
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "========================================="
echo "E2 Manual: 0% and 1% Loss (N=30)"
echo "========================================="

# Source ROS2 and echo
set +u
source /opt/ros/humble/setup.bash
source /home/wsde-47/mROS2-QoS/tools/echo_cpp/install/setup.bash
set -u

# Clean all echo processes
pkill -9 -f echo_node 2>/dev/null || true
sleep 2

# 0% loss
echo "[E2] Running 0% loss (N=30)..."
ros2 run echo_cpp echo_node_lossy --reliable --loss 0.0 > /tmp/e2_0pct.log 2>&1 &
ECHO_PID=$!
sleep 5

"${SCRIPT_DIR}/run_matrix.sh" "mros2qos" "reliable_0pct" 30

kill ${ECHO_PID} 2>/dev/null || true
sleep 3
pkill -9 -f echo_node 2>/dev/null || true
sleep 2

# 1% loss
echo "[E2] Running 1% loss (N=30)..."
ros2 run echo_cpp echo_node_lossy --reliable --loss 0.01 > /tmp/e2_1pct.log 2>&1 &
ECHO_PID=$!
sleep 5

"${SCRIPT_DIR}/run_matrix.sh" "mros2qos" "reliable_1pct" 30

kill ${ECHO_PID} 2>/dev/null || true
pkill -9 -f echo_node 2>/dev/null || true

echo ""
echo "========================================="
echo "E2 Manual Complete"
echo "========================================="
echo "0% and 1% loss conditions completed (N=30 each)"
