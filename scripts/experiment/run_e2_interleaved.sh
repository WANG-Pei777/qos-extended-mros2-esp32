#!/usr/bin/env bash
#
# E2 Interleaved: 5 loss conditions × 6 rounds = N=30 per condition (interleaved)
# Each round: A,B,C,D,E (5 runs each) → mitigates temporal bias
#
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

echo "========================================="
echo "E2 Interleaved: RELIABLE Under Packet Loss"
echo "========================================="
echo "Strategy: 5 conditions × 6 rounds (interleaved)"
echo "Each round: 5 runs per condition"
echo "Total: 30 runs per condition (交错采样缓解时间偏差)"
echo ""

# 5 loss conditions
CONDITIONS=(
    "reliable_0pct:0.0"
    "reliable_1pct:0.01"
    "reliable_5pct:0.05"
    "reliable_10pct:0.10"
    "reliable_15pct:0.15"
)

START_TIME=$(date +%s)

# 6 rounds of interleaved sampling
for ROUND in {1..6}; do
    echo ""
    echo "========================================="
    echo "Round ${ROUND}/6"
    echo "========================================="

    for COND in "${CONDITIONS[@]}"; do
        IFS=':' read -r LABEL LOSS <<< "${COND}"

        echo ""
        echo "[Round ${ROUND}] ${LABEL} (loss=${LOSS})"

        # Run 5 iterations for this condition in this round
        HOST_MODE="lossy:${LOSS}" "${SCRIPT_DIR}/run_matrix.sh" "mros2qos" "${LABEL}" 5
        sleep 2
    done

    echo "[Round ${ROUND}] Complete"
done

END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))

echo ""
echo "========================================="
echo "E2 Interleaved Complete"
echo "========================================="
echo "Total time: $((ELAPSED / 3600))h $((ELAPSED % 3600 / 60))m"
echo ""
echo "Results: 5 conditions × 30 runs (交错采样)"
echo "  - reliable_0pct.csv"
echo "  - reliable_1pct.csv"
echo "  - reliable_5pct.csv"
echo "  - reliable_10pct.csv"
echo "  - reliable_15pct.csv"
