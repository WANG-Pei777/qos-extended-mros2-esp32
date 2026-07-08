#!/usr/bin/env bash
#
# E6: Heartbeat Period × Packet Loss Trade-off
# Core parameter sweep from MASTER_EXPERIMENT_PLAN §7.2
# HB periods: 100, 500, 1000, 2000, 4000, 8000 ms
# Loss rates: 0%, 5%, 10%
# N=30 per condition
#
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "========================================="
echo "E6: Heartbeat Period × Packet Loss"
echo "========================================="
echo "Testing HB period trade-off under packet loss"
echo "HB periods: 100, 500, 1000, 2000, 4000, 8000 ms"
echo "Loss rates: 0%, 5%, 10%"
echo "Estimated time: 12-15 hours"
echo ""
echo "[auto] Starting in 3 seconds..."
sleep 3

START_TIME=$(date +%s)

# Loss rates to test
LOSS_RATES=("0.0" "0.05" "0.10")

for LOSS in "${LOSS_RATES[@]}"; do
    LOSS_PCT=$(echo "${LOSS} * 100" | bc | cut -d. -f1)

    echo ""
    echo "========================================="
    echo "Testing: Loss = ${LOSS_PCT}%"
    echo "========================================="

    # Sweep heartbeat period
    "${SCRIPT_DIR}/sweep_param.sh" heartbeat_period 100 500 1000 2000 4000 8000 \
        --loss "${LOSS}" \
        --condition "hb_sweep_${LOSS_PCT}pct"

    echo "[E6] Loss ${LOSS_PCT}% complete"
done

END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))

echo ""
echo "========================================="
echo "E6 Complete"
echo "========================================="
echo "Total time: $((ELAPSED / 3600))h $((ELAPSED % 3600 / 60))m"
echo ""
echo "Analysis:"
echo "  - Plot: HB Period (x) vs Recovery Latency (y) × Loss Rate"
echo "  - Plot: HB Period (x) vs Network Overhead (packets) × Loss Rate"
echo "  - Expected: Lower HB = faster recovery but higher overhead"
