#!/usr/bin/env bash
set -euo pipefail

PORT="${1:-/dev/ttyUSB0}"
ATTEMPTS="${2:-3}"
CAPTURE_SECONDS="${3:-110}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RESULT_DIR="${QOS_PREFLIGHT_RESULT_DIR:-${PROJECT_ROOT}/results/qos_preflight_$(date +%Y%m%d_%H%M%S)}"

mkdir -p "${RESULT_DIR}"

echo "[preflight] port=${PORT}"
echo "[preflight] attempts=${ATTEMPTS}"
echo "[preflight] capture_seconds=${CAPTURE_SECONDS}"
echo "[preflight] result_dir=${RESULT_DIR}"

for attempt in $(seq 1 "${ATTEMPTS}"); do
  echo
  echo "===== preflight attempt ${attempt}/${ATTEMPTS} ====="
  export QOS_VERIFY_SERIAL_LOG="${RESULT_DIR}/attempt_${attempt}_serial.log"
  export QOS_VERIFY_HOST_LOG="${RESULT_DIR}/attempt_${attempt}_host.log"
  export QOS_VERIFY_TOPIC_LOG="${RESULT_DIR}/attempt_${attempt}_topic.log"
  if "${PROJECT_ROOT}/scripts/validation/qos_verify.sh" "${PORT}" "${CAPTURE_SECONDS}" \
      > "${RESULT_DIR}/attempt_${attempt}_summary.log" 2>&1; then
    cat "${RESULT_DIR}/attempt_${attempt}_summary.log"
    echo "[preflight] RESULT: PASS on attempt ${attempt}"
    exit 0
  fi
  tail -n 35 "${RESULT_DIR}/attempt_${attempt}_summary.log" || true
done

echo "[preflight] RESULT: FAIL after ${ATTEMPTS} attempts"
exit 1
