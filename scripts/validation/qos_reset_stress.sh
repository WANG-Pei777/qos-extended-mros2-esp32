#!/usr/bin/env bash
set -euo pipefail

RUNS="${1:-3}"
PORT="${2:-/dev/ttyUSB0}"
CAPTURE_SECONDS="${3:-110}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RESULT_DIR="${QOS_STRESS_RESULT_DIR:-${PROJECT_ROOT}/results/qos_reset_stress_$(date +%Y%m%d_%H%M%S)}"
RUN_SETTLE_SECONDS="${QOS_STRESS_RUN_SETTLE_SECONDS:-3}"
ATTEMPTS_PER_RUN="${QOS_STRESS_ATTEMPTS_PER_RUN:-3}"

mkdir -p "${RESULT_DIR}"

echo "[stress] runs=${RUNS}"
echo "[stress] port=${PORT}"
echo "[stress] capture_seconds=${CAPTURE_SECONDS}"
echo "[stress] result_dir=${RESULT_DIR}"
echo "[stress] run_settle_seconds=${RUN_SETTLE_SECONDS}"
echo "[stress] attempts_per_run=${ATTEMPTS_PER_RUN}"

pass_count=0
for i in $(seq 1 "${RUNS}"); do
  echo
  echo "===== stress run ${i}/${RUNS} ====="
  run_pass=0
  for attempt in $(seq 1 "${ATTEMPTS_PER_RUN}"); do
    echo "[stress] run ${i}: attempt ${attempt}/${ATTEMPTS_PER_RUN}"
    export QOS_VERIFY_SERIAL_LOG="${RESULT_DIR}/run_${i}_attempt_${attempt}_serial.log"
    export QOS_VERIFY_HOST_LOG="${RESULT_DIR}/run_${i}_attempt_${attempt}_host.log"
    export QOS_VERIFY_TOPIC_LOG="${RESULT_DIR}/run_${i}_attempt_${attempt}_topic.log"
    if "${PROJECT_ROOT}/scripts/validation/qos_verify.sh" "${PORT}" "${CAPTURE_SECONDS}" \
        > "${RESULT_DIR}/run_${i}_attempt_${attempt}_summary.log" 2>&1; then
      cp "${QOS_VERIFY_SERIAL_LOG}" "${RESULT_DIR}/run_${i}_serial.log"
      cp "${QOS_VERIFY_HOST_LOG}" "${RESULT_DIR}/run_${i}_host.log"
      cp "${QOS_VERIFY_TOPIC_LOG}" "${RESULT_DIR}/run_${i}_topic.log"
      cp "${RESULT_DIR}/run_${i}_attempt_${attempt}_summary.log" "${RESULT_DIR}/run_${i}_summary.log"
      run_pass=1
      break
    fi
    tail -n 8 "${RESULT_DIR}/run_${i}_attempt_${attempt}_summary.log" || true
    if [ "${attempt}" -lt "${ATTEMPTS_PER_RUN}" ]; then
      sleep "${RUN_SETTLE_SECONDS}"
    fi
  done

  if [ "${run_pass}" -eq 1 ]; then
    pass_count=$((pass_count + 1))
    echo "[stress] run ${i}: PASS"
  else
    cp "${RESULT_DIR}/run_${i}_attempt_${ATTEMPTS_PER_RUN}_summary.log" "${RESULT_DIR}/run_${i}_summary.log" 2>/dev/null || true
    echo "[stress] run ${i}: FAIL"
  fi
  tail -n 18 "${RESULT_DIR}/run_${i}_summary.log" || true
  if [ "${i}" -lt "${RUNS}" ]; then
    sleep "${RUN_SETTLE_SECONDS}"
  fi
done

{
  echo "runs=${RUNS}"
  echo "passed=${pass_count}"
  echo "failed=$((RUNS - pass_count))"
  echo "result_dir=${RESULT_DIR}"
} | tee "${RESULT_DIR}/summary.txt"

if [ "${pass_count}" -eq "${RUNS}" ]; then
  echo "[stress] RESULT: PASS"
else
  echo "[stress] RESULT: FAIL"
  exit 1
fi
