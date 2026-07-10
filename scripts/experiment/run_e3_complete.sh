#!/usr/bin/env bash
#
# E3 Complete: Pre-fix + Post-fix comparison
# Per EXPERIMENT_REMEDIATION_GUIDE §3.③
#
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

echo "========================================="
echo "E3 Complete Workflow"
echo "========================================="
echo "Part 1: Pre-fix (212122c) - already running"
echo "Part 2: Post-fix (baseline) - will execute after Part 1"
echo ""

# Part 1 should already be running from separate invocation
# This script handles Part 2: Post-fix

echo "[E3] Waiting for pre-fix test to complete..."
echo "[E3] Check ${PROJECT_ROOT}/results/experiments/<date>/mros2qos_reset_storm_prefix.csv"
echo ""
echo "[E3] When complete, run Part 2 manually:"
echo ""
echo "  # Restore baseline firmware"
echo "  cd ${PROJECT_ROOT}/workspace/qos_eval"
echo "  source ~/esp-idf/export.sh && idf.py -p /dev/ttyUSB0 flash"
echo ""
echo "  # Kill pre-fix host"
echo "  pkill -f 'qos_host.sh'"
echo ""
echo "  # Start baseline host"
echo "  QOS_VALIDATION_SKIP_KILL=1 nohup bash scripts/validation/qos_host.sh all > /tmp/e3_postfix_host.log 2>&1 &"
echo ""
echo "  # Run post-fix test (30 resets)"
echo "  bash scripts/experiment/run_matrix.sh mros2qos reset_storm_postfix 30"
echo ""
echo "Expected outcome:"
echo "  - prefix: ~20-30% failures (卡死)"
echo "  - postfix: ~100% success, shorter wait times"
