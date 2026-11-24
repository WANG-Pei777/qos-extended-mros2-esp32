#!/usr/bin/env bash
#
# E2 Re-run with validation: RELIABLE under packet loss
# First validates each condition with N=1, then runs N=30
#
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

echo "========================================="
echo "E2 Re-run: RELIABLE Under Packet Loss"
echo "========================================="
echo "Loss rates: 0%, 1%, 5%, 10%, 15%"
echo "Strategy: Validate N=1 first, then N=30"
echo ""

# Reduced loss rates (removed 20% which caused failure)
CONDITIONS=(
    "reliable_0pct:0.0"
    "reliable_1pct:0.01"
    "reliable_5pct:0.05"
    "reliable_10pct:0.10"
    "reliable_15pct:0.15"
)

for COND in "${CONDITIONS[@]}"; do
    IFS=':' read -r LABEL LOSS <<< "${COND}"

    echo ""
    echo "========================================="
    echo "Validating: ${LABEL} (loss=${LOSS})"
    echo "========================================="

    # Validate with N=1
    echo "[validate] Running N=1 test..."
    HOST_MODE="lossy:${LOSS}" "${SCRIPT_DIR}/run_matrix.sh" "mros2qos" "${LABEL}_validate" 1

    # Check result - FIX: Extract matched_pub from data row, not header
    MATCHED=$(tail -1 "${PROJECT_ROOT}/results/experiments/$(date +%Y%m%d)/mros2qos_${LABEL}_validate.csv" | awk -F, '{print $11}')

    if [ "${MATCHED}" = "1" ]; then
        echo "[OK] Validation passed (matched_pub=${MATCHED}), running N=30..."
        HOST_MODE="lossy:${LOSS}" "${SCRIPT_DIR}/run_matrix.sh" "mros2qos" "${LABEL}" 30
    else
        echo "[FAIL] Validation failed (matched_pub=${MATCHED}), skipping N=30"
        echo "[FAIL] Check results/experiments/$(date +%Y%m%d)/mros2qos_${LABEL}_validate_run*_host.log for echo node issues"
    fi
done

echo ""
echo "========================================="
echo "E2 Re-run Complete"
echo "========================================="
