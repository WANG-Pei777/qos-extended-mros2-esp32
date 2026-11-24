#!/usr/bin/env bash
set -euo pipefail

POLICY="${1:-all}"
PORT="${2:-/dev/ttyUSB0}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORKSPACE="qos_eval"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/validation/qos_flash.sh [all] [port]

This project keeps one hardware validation workflow:
  all    WSL2 ROS2 <-> ESP32 mROS2 bidirectional QoS validation path

Examples:
  QOS_VALIDATION_MONITOR=0 ./scripts/validation/qos_flash.sh all /dev/ttyUSB0
  ./scripts/validation/qos_flash.sh all /dev/ttyUSB0
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
source "${HOME}/esp-idf/export.sh"
set -u

cd "${PROJECT_ROOT}/workspace/${WORKSPACE}"
echo "[qos-validation] policy=all"
echo "[qos-validation] reply_path=RELIABLE"
echo "[qos-validation] workspace=${WORKSPACE}"
echo "[qos-validation] port=${PORT}"
if [ "${QOS_VALIDATION_AUTO_REMOTE_IP:-1}" = "1" ]; then
  if [ -n "${QOS_VALIDATION_REMOTE_IP:-}" ]; then
    "${PROJECT_ROOT}/scripts/validation/qos_set_remote_ip.sh" "${QOS_VALIDATION_REMOTE_IP}"
  else
    "${PROJECT_ROOT}/scripts/validation/qos_set_remote_ip.sh"
  fi
else
  echo "[qos-validation] auto remote IP update disabled"
fi
if [ -f build/CMakeCache.txt ] && ! grep -q "${PROJECT_ROOT}/workspace/${WORKSPACE}" build/CMakeCache.txt; then
  echo "[qos-validation] removing stale build directory with old source path"
  rm -rf build
fi

MROS2_QOS_FULL_RELIABLE_REPLY=1 idf.py reconfigure
MROS2_QOS_FULL_RELIABLE_REPLY=1 idf.py build
if [ "${QOS_VALIDATION_MONITOR:-1}" = "0" ]; then
  MROS2_QOS_FULL_RELIABLE_REPLY=1 idf.py -p "${PORT}" flash
else
  MROS2_QOS_FULL_RELIABLE_REPLY=1 idf.py -p "${PORT}" flash monitor
fi
