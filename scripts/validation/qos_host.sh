#!/usr/bin/env bash
set -euo pipefail

POLICY="${1:-all}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/validation/qos_host.sh [all]

Runs the ROS2 side of the hardware validation workflow:
  ESP32 publishes /qos_eval
  ROS2 replies on /qos_eval_reply
EOF
}

case "${POLICY}" in
  all) ;;
  -h|--help) usage; exit 0 ;;
  *)
    echo "Unknown policy: ${POLICY}"
    usage
    exit 1
    ;;
esac

set +u
source /opt/ros/humble/setup.bash
set -u

export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"
export ROS_LOCALHOST_ONLY="${ROS_LOCALHOST_ONLY:-0}"

if [ "${QOS_VALIDATION_SKIP_KILL:-0}" != "1" ]; then
  pkill -f "${PROJECT_ROOT}/workspace/qos_eval/echo_reply.py" 2>/dev/null || true
fi

echo "[qos-host] reply_mode=RELIABLE"
python3 -u "${PROJECT_ROOT}/workspace/qos_eval/echo_reply.py"
