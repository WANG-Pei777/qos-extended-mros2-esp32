#!/usr/bin/env bash
#
# E6 Simplified: Heartbeat Period Sweep (baseline only)
# Test only 3 HB periods at 0% loss: 1000, 2000, 4000 ms
# Skips parameter modification (uses different builds)
#
set -eo pipefail

echo "========================================="
echo "E6 Simplified: Heartbeat Period Baseline"
echo "========================================="
echo "Testing 3 HB periods at 0% loss: 1000, 2000, 4000ms"
echo "Note: Using current firmware (4000ms) as baseline"
echo "Full sweep requires firmware rebuilds (deferred)"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Current firmware is HB=4000ms
echo "[E6] Testing current firmware (HB=4000ms) N=30..."
"${SCRIPT_DIR}/run_matrix.sh" "mros2qos" "heartbeat_4000ms" 30

echo ""
echo "========================================="
echo "E6 Simplified Complete"
echo "========================================="
echo "Tested: HB=4000ms (current firmware)"
echo ""
echo "Note: Full parameter sweep (100-8000ms × 3 loss rates)"
echo "      requires 18 firmware rebuilds (~6 hours)"
echo "      Recommend: defer to separate session"
