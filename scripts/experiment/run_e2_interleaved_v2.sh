#!/usr/bin/env bash
#
# E2: one QoS arm of the ROUND4 application-layer reply-loss matrix.
# Run this script once after flashing each board QoS mode.
#
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
QOS_MODE="${1:?Usage: $0 <reliable|best_effort> [rounds]}"
ROUNDS="${2:-6}"
RUNS_PER_ROUND=5
FIRMWARE_MODE="${FIRMWARE_MODE:?Set FIRMWARE_MODE after confirming the flashed board mode}"
FIRMWARE_BINARY="${FIRMWARE_BINARY:?Set FIRMWARE_BINARY to the exact flashed build/qos_eval.bin}"

case "${QOS_MODE}" in
    reliable|best_effort)
        ;;
    *)
        echo "Error: QoS mode must be reliable or best_effort" >&2
        exit 2
        ;;
esac

if [ "${FIRMWARE_MODE}" != "${QOS_MODE}" ]; then
    echo "Error: flashed FIRMWARE_MODE (${FIRMWARE_MODE}) does not match requested QoS (${QOS_MODE})" >&2
    exit 2
fi

echo "========================================="
echo "E2 Interleaved: ${QOS_MODE} Under Application Reply Loss"
echo "========================================="
echo "Strategy: 5 conditions × ${ROUNDS} rounds (interleaved)"
echo "Each round: ${RUNS_PER_ROUND} runs per condition"
echo "F3 Gate: validate host configuration and traffic on run 1"
echo ""

# 5 loss conditions
CONDITIONS=(
    "round4_${QOS_MODE}_0pct:0.0"
    "round4_${QOS_MODE}_1pct:0.01"
    "round4_${QOS_MODE}_5pct:0.05"
    "round4_${QOS_MODE}_10pct:0.10"
    "round4_${QOS_MODE}_15pct:0.15"
)

START_TIME=$(date +%s)
DATE=$(date +%Y%m%d)
RESULTS_DIR="${PROJECT_ROOT}/results/experiments/${DATE}"
EFFICACY_LOG="${PROJECT_ROOT}/results/experiments/${DATE}/E2_${QOS_MODE}_INJECTION_EFFICACY.md"
mkdir -p "${RESULTS_DIR}"

# Initialize efficacy log
echo "# Injection Efficacy Report" > "${EFFICACY_LOG}"
echo "" >> "${EFFICACY_LOG}"
echo "**Date**: ${DATE}" >> "${EFFICACY_LOG}"
echo "**QoS mode**: ${QOS_MODE}" >> "${EFFICACY_LOG}"
echo "**Firmware mode**: ${FIRMWARE_MODE}" >> "${EFFICACY_LOG}"
echo "**Injection layer**: application_reply (not network/RTPS loss)" >> "${EFFICACY_LOG}"
echo "" >> "${EFFICACY_LOG}"
echo "| Condition | Loss Rate | Attempts (Run 1) | Configuration status |" >> "${EFFICACY_LOG}"
echo "|-----------|-----------|------------------|----------------------|" >> "${EFFICACY_LOG}"

# Interleaved sampling within one flashed QoS arm.
for ROUND in $(seq 1 "${ROUNDS}"); do
    echo ""
    echo "========================================="
    echo "Round ${ROUND}/${ROUNDS}"
    echo "========================================="

    for COND in "${CONDITIONS[@]}"; do
        IFS=':' read -r LABEL LOSS <<< "${COND}"

        echo ""
        echo "[Round ${ROUND}] ${LABEL} (loss=${LOSS})"

        # Run a short block per condition, then rotate to the next condition.
        for i in $(seq 1 "${RUNS_PER_ROUND}"); do
            RUN_NUM=$(( (ROUND - 1) * RUNS_PER_ROUND + i ))
            echo "  Run ${RUN_NUM}/$((ROUNDS * RUNS_PER_ROUND))"

            FORMAL_RUN=1 \
            QOS_MODE="${QOS_MODE}" \
            FIRMWARE_MODE="${FIRMWARE_MODE}" \
            FIRMWARE_BINARY="${FIRMWARE_BINARY}" \
            INJECTION_LAYER="application_reply" \
            HOST_MODE="lossy:${LOSS}" \
                "${SCRIPT_DIR}/run_matrix.sh" "mros2qos" "${LABEL}" 1

            # A single 40-message run can legitimately observe zero drops at
            # 1%. Validate configuration and traffic here; rate efficacy is
            # checked over the full condition at the end of the experiment.
            if [ "${RUN_NUM}" -eq 1 ]; then
                CSV_PATH="${RESULTS_DIR}/mros2qos_${LABEL}.csv"
                ATTEMPTS=$(python3 - "${CSV_PATH}" "${QOS_MODE}" "${FIRMWARE_MODE}" "${LOSS}" <<'PY'
import csv
import math
import sys

csv_path, qos_mode, firmware_mode, loss = sys.argv[1:]
with open(csv_path, newline='', encoding='utf-8') as handle:
    rows = list(csv.DictReader(handle))
row = rows[-1]

if row['qos_mode'] != qos_mode or row['firmware_mode'] != firmware_mode:
    raise SystemExit('QoS or firmware provenance mismatch')
if row['injection_layer'] != 'application_reply':
    raise SystemExit('unexpected injection layer')
if not math.isclose(float(row['host_loss_rate']), float(loss), abs_tol=1e-12):
    raise SystemExit('configured loss rate mismatch')
attempts = int(row['host_injection_attempted'])
if attempts <= 0:
    raise SystemExit('host received no traffic')
print(attempts)
PY
)
                echo "| ${LABEL} | ${LOSS} | ${ATTEMPTS} | PASS |" >> "${EFFICACY_LOG}"
                echo "  [F3 Gate] configuration and host traffic confirmed (${ATTEMPTS} attempts)"
            fi
        done
        sleep 2
    done

    echo "[Round ${ROUND}] Complete"
done

END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))

echo "" >> "${EFFICACY_LOG}"
echo "## Aggregate Injection Validation" >> "${EFFICACY_LOG}"
for COND in "${CONDITIONS[@]}"; do
    IFS=':' read -r LABEL LOSS <<< "${COND}"
    CSV_PATH="${RESULTS_DIR}/mros2qos_${LABEL}.csv"
    VALIDATION=$(python3 "${SCRIPT_DIR}/validate_injection.py" "${CSV_PATH}" "${LOSS}" \
        --min-attempts "$((ROUNDS * RUNS_PER_ROUND * 30))")
    echo "- ${LABEL}: ${VALIDATION}" | tee -a "${EFFICACY_LOG}"
done

echo "" >> "${EFFICACY_LOG}"
echo "**Result**: All conditions passed configuration and aggregate efficacy validation." >> "${EFFICACY_LOG}"

echo ""
echo "========================================="
echo "E2 Interleaved Complete"
echo "========================================="
echo "Total time: $((ELAPSED / 3600))h $((ELAPSED % 3600 / 60))m"
echo ""
echo "Results: 5 conditions × $((ROUNDS * RUNS_PER_ROUND)) runs (interleaved)"
echo "Efficacy report: ${EFFICACY_LOG}"
