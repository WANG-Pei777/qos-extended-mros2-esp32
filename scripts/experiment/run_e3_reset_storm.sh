#!/usr/bin/env bash
#
# E3: Reset Storm (Reliability Fix Verification)
# Tests discovery reliability after repeated resets
# N=30 resets
#
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "========================================="
echo "E3: Reset Storm (Post-Fix)"
echo "========================================="
echo "Testing discovery reliability after repeated resets"
echo "Current firmware: post-fix (GUID entropy + lease fixes)"
echo "N=30"
echo ""

START_TIME=$(date +%s)

# Run N=30 reset tests
"${SCRIPT_DIR}/run_matrix.sh" "mros2qos" "reset_storm_postfix" 30

END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))

echo ""
echo "========================================="
echo "E3 Complete"
echo "========================================="
echo "Total time: $((ELAPSED / 3600))h $((ELAPSED % 3600 / 60))m"
echo ""
echo "Results: results/experiments/$(date +%Y%m%d)/mros2qos_reset_storm_postfix.csv"
echo ""
echo "Analysis: Match success rate should be ~100% (post-fix)"
