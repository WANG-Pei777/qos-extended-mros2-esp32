#!/usr/bin/env bash
#
# G5: Test C++ echo node
#
set -eo pipefail

echo "========================================="
echo "G5: Testing C++ Echo Node"
echo "========================================="
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ECHO_NODE="${PROJECT_ROOT}/tools/echo_cpp/install/echo_cpp/lib/echo_cpp/echo_node"

# Source workspaces
set +u
source /opt/ros/humble/setup.bash
source "${PROJECT_ROOT}/tools/echo_cpp/install/setup.bash"
set -u

if [ ! -x "${ECHO_NODE}" ]; then
    echo "[FAIL] Missing executable: ${ECHO_NODE}"
    exit 1
fi

# Start C++ echo node
echo "[test] Starting C++ echo node..."
"${ECHO_NODE}" --reliable &
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
echo "  ${ECHO_NODE} --reliable"
echo "  ${ECHO_NODE} --best-effort"
echo ""

# Kill test node
kill ${ECHO_PID} 2>/dev/null || true

echo "========================================="
echo "G5: C++ Echo Node Ready"
echo "========================================="
