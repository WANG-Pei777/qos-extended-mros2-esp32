#!/usr/bin/env bash
set -euo pipefail

POLICY="${1:-all}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
QOS_MODE="${QOS_HOST_QOS_MODE:-reliable}"
IMPLEMENTATION="${QOS_HOST_IMPLEMENTATION:-python}"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/validation/qos_host.sh [all]

Runs the ROS2 side of the hardware validation workflow:
  ESP32 publishes /qos_eval
  ROS2 replies on /qos_eval_reply

Environment:
  QOS_HOST_QOS_MODE=reliable|best_effort
  QOS_HOST_IMPLEMENTATION=python|cpp
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

case "${QOS_MODE}" in
  reliable)
    QOS_FLAG="--reliable"
    QOS_LABEL="RELIABLE"
    ;;
  best_effort)
    QOS_FLAG="--best-effort"
    QOS_LABEL="BEST_EFFORT"
    ;;
  *)
    echo "Unknown QOS_HOST_QOS_MODE: ${QOS_MODE}" >&2
    exit 2
    ;;
esac

case "${IMPLEMENTATION}" in
  python|cpp) ;;
  *)
    echo "Unknown QOS_HOST_IMPLEMENTATION: ${IMPLEMENTATION}" >&2
    exit 2
    ;;
esac

set +u
source /opt/ros/humble/setup.bash
set -u

export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"
export ROS_LOCALHOST_ONLY="${ROS_LOCALHOST_ONLY:-0}"

if [ "${QOS_VALIDATION_SKIP_KILL:-0}" != "1" ]; then
  pkill -f "${PROJECT_ROOT}/workspace/qos_eval/echo_reply.py" 2>/dev/null || true
  pkill -f "${PROJECT_ROOT}/tools/echo_cpp/install/echo_cpp/lib/echo_cpp/echo_node" 2>/dev/null || true
fi

echo "[qos-host] implementation=${IMPLEMENTATION} reply_mode=${QOS_LABEL}"
if [ "${IMPLEMENTATION}" = "cpp" ]; then
  HOST_BINARY="${PROJECT_ROOT}/tools/echo_cpp/install/echo_cpp/lib/echo_cpp/echo_node"
  if [ ! -x "${HOST_BINARY}" ]; then
    echo "C++ echo host unavailable: ${HOST_BINARY}" >&2
    exit 2
  fi
  exec "${HOST_BINARY}" "${QOS_FLAG}"
fi

QOS_REPLY_RELIABILITY="${QOS_LABEL}" \
  exec python3 -u "${PROJECT_ROOT}/workspace/qos_eval/echo_reply.py"
