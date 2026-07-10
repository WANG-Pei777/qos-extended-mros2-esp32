#!/usr/bin/env bash
#
# F3 Smoke Test: Verify injection efficacy gate
# Quick test: 15% loss × 1 run to verify gate works
#
set -eo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FIRMWARE_MODE="${FIRMWARE_MODE:-reliable}"

echo "========================================="
echo "F3 Smoke Test: Injection Efficacy Gate"
echo "========================================="
echo "Testing: 15% loss × 1 run"
echo ""

# Run 1 non-formal pilot. Formal E2 runs require a clean committed worktree.
QOS_MODE="reliable" \
FIRMWARE_MODE="${FIRMWARE_MODE}" \
INJECTION_LAYER="application_reply" \
HOST_MODE="lossy:0.15" \
    "${PROJECT_ROOT}/scripts/experiment/run_matrix.sh" "mros2qos" "round4_f3_smoke_15pct" 1

DATE=$(date +%Y%m%d)
RESULTS_DIR="${PROJECT_ROOT}/results/experiments/${DATE}"
CSV_PATH="${RESULTS_DIR}/mros2qos_round4_f3_smoke_15pct.csv"

# Check configuration and traffic, not a single random drop outcome.
read -r ATTEMPTED DROPPED < <(python3 - "${CSV_PATH}" <<'PY'
import csv
import sys

with open(sys.argv[1], newline='', encoding='utf-8') as handle:
    row = list(csv.DictReader(handle))[-1]

if row['qos_mode'] != 'reliable' or row['injection_layer'] != 'application_reply':
    raise SystemExit('unexpected smoke-test provenance')
if float(row['host_loss_rate']) != 0.15:
    raise SystemExit('unexpected smoke-test loss rate')
print(row['host_injection_attempted'], row['host_injection_dropped'])
PY
)
echo ""
echo "========================================="
echo "F3 Gate Check"
echo "========================================="
echo "Host attempts: ${ATTEMPTED}"
echo "Host drops: ${DROPPED}"

if [ "${ATTEMPTED}" -le 0 ]; then
    echo "FAIL: host received no traffic"
    exit 1
fi

echo "PASS: configuration and traffic confirmed"

echo ""
echo "F3 Smoke Test: PASS"
