#!/usr/bin/env bash
#
# E2 Manual: Run N=30 for validated conditions (0% and 1%)
#
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

echo "========================================="
echo "E2 Manual: 0% and 1% Loss (N=30)"
echo "========================================="

# 0% loss
echo "[E2] Running 0% loss (N=30)..."
HOST_MODE="lossy:0.0" "${SCRIPT_DIR}/run_matrix.sh" "mros2qos" "reliable_0pct" 30

# 1% loss
echo "[E2] Running 1% loss (N=30)..."
HOST_MODE="lossy:0.01" "${SCRIPT_DIR}/run_matrix.sh" "mros2qos" "reliable_1pct" 30

echo ""
echo "========================================="
echo "E2 Manual Complete"
echo "========================================="
echo "0% and 1% loss conditions completed (N=30 each)"
