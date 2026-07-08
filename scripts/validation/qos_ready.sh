#!/usr/bin/env bash
set -euo pipefail

PORT="${1:-/dev/ttyUSB0}"
ACTION="${2:-check}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/validation/qos_ready.sh [port] [check|flash|preflight|all]

Actions:
  check      Update WSL IP in firmware config, run static checks, build firmware.
  flash      Do check, then flash ESP32.
  preflight  Do check, then run real-hardware preflight without flashing.
  all        Do check, flash ESP32, then run real-hardware preflight.
EOF
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  usage
  exit 0
fi

case "${ACTION}" in
  check|flash|preflight|all) ;;
  -h|--help) usage; exit 0 ;;
  *)
    echo "[ready] unknown action: ${ACTION}" >&2
    usage
    exit 1
    ;;
esac

cd "${PROJECT_ROOT}"
echo "[ready] project=${PROJECT_ROOT}"
echo "[ready] port=${PORT}"
echo "[ready] action=${ACTION}"
echo

echo "== 1. Update firmware target IP =="
"${PROJECT_ROOT}/scripts/validation/qos_set_remote_ip.sh"
echo

echo "== 2. Environment doctor =="
"${PROJECT_ROOT}/scripts/validation/qos_network_doctor.sh" "${PORT}" | sed -n '1,120p'
echo

echo "== 3. Static QoS checks =="
"${PROJECT_ROOT}/scripts/test/qos_static_checks.sh"
echo

echo "== 4. Firmware build =="
set +u
# shellcheck disable=SC1091
source "${HOME}/esp-idf/export.sh" >/tmp/mros2_idf_export.log 2>&1
set -u
(
  cd "${PROJECT_ROOT}/workspace/qos_eval"
  MROS2_QOS_FULL_RELIABLE_REPLY=1 idf.py build
)
echo

case "${ACTION}" in
  check)
    echo "[ready] RESULT: CHECK PASS"
    echo "[ready] To flash and preflight: ./scripts/validation/qos_ready.sh ${PORT} all"
    ;;
  flash)
    echo "== 5. Flash ESP32 =="
    QOS_VALIDATION_MONITOR=0 "${PROJECT_ROOT}/scripts/validation/qos_flash.sh" all "${PORT}"
    echo "[ready] RESULT: FLASH PASS"
    ;;
  preflight)
    echo "== 5. Real-hardware preflight =="
    "${PROJECT_ROOT}/scripts/validation/qos_preflight.sh" "${PORT}" 3
    echo "[ready] RESULT: PREFLIGHT PASS"
    ;;
  all)
    echo "== 5. Flash ESP32 =="
    QOS_VALIDATION_MONITOR=0 "${PROJECT_ROOT}/scripts/validation/qos_flash.sh" all "${PORT}"
    echo
    echo "== 6. Real-hardware preflight =="
    "${PROJECT_ROOT}/scripts/validation/qos_preflight.sh" "${PORT}" 3
    echo "[ready] RESULT: ALL PASS"
    ;;
esac
