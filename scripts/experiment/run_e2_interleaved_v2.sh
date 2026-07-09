#!/usr/bin/env bash
#
# E2 Interleaved with F3 Efficacy Gate
# Per REMEDIATION_ROUND2_EXECUTION.md §1.F3
#
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

echo "========================================="
echo "E2 Interleaved: RELIABLE Under Packet Loss"
echo "========================================="
echo "Strategy: 5 conditions × 6 rounds (interleaved)"
echo "Each round: 5 runs per condition"
echo "Total: 30 runs per condition"
echo "F3 Gate: Efficacy check on run 1 for loss>0"
echo ""

# Source ROS2 and echo
set +u
source /opt/ros/humble/setup.bash
source "${PROJECT_ROOT}/tools/echo_cpp/install/setup.bash"
set -u

# 5 loss conditions
CONDITIONS=(
    "reliable_0pct:0.0"
    "reliable_1pct:0.01"
    "reliable_5pct:0.05"
    "reliable_10pct:0.10"
    "reliable_15pct:0.15"
)

START_TIME=$(date +%s)
DATE=$(date +%Y%m%d)
EFFICACY_LOG="${PROJECT_ROOT}/results/experiments/${DATE}/INJECTION_EFFICACY.md"

# Initialize efficacy log
echo "# Injection Efficacy Report" > "${EFFICACY_LOG}"
echo "" >> "${EFFICACY_LOG}"
echo "**Date**: ${DATE}" >> "${EFFICACY_LOG}"
echo "**Test**: E2 Interleaved (RELIABLE under packet loss)" >> "${EFFICACY_LOG}"
echo "" >> "${EFFICACY_LOG}"
echo "| Condition | Loss Rate | Dropped (Run 1) | Status |" >> "${EFFICACY_LOG}"
echo "|-----------|-----------|-----------------|--------|" >> "${EFFICACY_LOG}"

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

        # Clean any existing echo processes
        pkill -9 -f "echo_node_lossy" 2>/dev/null || true
        sleep 2

        # Start echo_node_lossy for this condition
        HOST_LOG="/tmp/e2_${LABEL}_r${ROUND}_host.log"
        ros2 run echo_cpp echo_node_lossy --reliable --loss ${LOSS} > "${HOST_LOG}" 2>&1 &
        ECHO_PID=$!
        sleep 5

        # Run 5 iterations for this condition in this round
        for i in {1..5}; do
            RUN_NUM=$(( (ROUND - 1) * 5 + i ))
            echo "  Run ${RUN_NUM}/30"

            "${SCRIPT_DIR}/run_matrix.sh" "mros2qos" "${LABEL}" 1

            # F3 Efficacy Gate: Check on first run of each condition
            if [ ${RUN_NUM} -eq 1 ] && [ "${LOSS}" != "0.0" ]; then
                DROPPED=$(grep -oE "Dropped: [0-9]+" "${HOST_LOG}" | tail -1 | grep -oE "[0-9]+" || echo "0")
                echo "  [F3 Gate] Checking efficacy: Dropped=${DROPPED}"

                if [ "${DROPPED}" -eq 0 ]; then
                    echo "| ${LABEL} | ${LOSS} | 0 | ❌ FAIL (injection inactive) |" >> "${EFFICACY_LOG}"
                    echo "[GATE FAIL] loss=${LOSS} but Dropped=0 — injection ineffective, aborting ${LABEL}"
                    kill ${ECHO_PID} 2>/dev/null || true
                    exit 1
                else
                    echo "| ${LABEL} | ${LOSS} | ${DROPPED} | ✅ PASS |" >> "${EFFICACY_LOG}"
                    echo "  [F3 Gate] ✅ Efficacy confirmed (Dropped=${DROPPED})"
                fi
            fi
        done

        # Kill echo node explicitly by PID
        kill ${ECHO_PID} 2>/dev/null || true
        wait ${ECHO_PID} 2>/dev/null || true
        sleep 2
    done

    echo "[Round ${ROUND}] Complete"
done

# Final cleanup
pkill -9 -f "echo_node_lossy" 2>/dev/null || true

END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))

echo "" >> "${EFFICACY_LOG}"
echo "**Result**: All conditions passed efficacy gate ✅" >> "${EFFICACY_LOG}"

echo ""
echo "========================================="
echo "E2 Interleaved Complete"
echo "========================================="
echo "Total time: $((ELAPSED / 3600))h $((ELAPSED % 3600 / 60))m"
echo ""
echo "Results: 5 conditions × 30 runs (interleaved)"
echo "Efficacy report: ${EFFICACY_LOG}"
