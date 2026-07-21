#!/usr/bin/env bash
#
# sweep_param.sh - Parameter sweep with rebuild and flash
# Usage: sweep_param.sh <param_name> <value1> <value2> ...
#
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
CONFIG_H="${PROJECT_ROOT}/platform/rtps/config.h"
WORKSPACE="${PROJECT_ROOT}/workspace/qos_eval"

PARAM_NAME="${1:?Usage: $0 <param_name> <value1> <value2> ...}"
shift
VALUES=("$@")

if [ ${#VALUES[@]} -eq 0 ]; then
    echo "Error: No values provided"
    exit 1
fi

for VALUE in "${VALUES[@]}"; do
    if [[ "${VALUE}" == --* ]]; then
        echo "[ERROR] Unsupported option passed as a sweep value: ${VALUE}" >&2
        echo "[ERROR] See docs/benchmark/ROUND6_MECHANISM_PREREGISTRATION.md" >&2
        exit 2
    fi
done

if [ "${FORMAL_RUN:-0}" = "1" ]; then
    echo "[ERROR] This legacy source-mutating sweep is prohibited for formal runs." >&2
    echo "[ERROR] See docs/benchmark/ROUND6_MECHANISM_PREREGISTRATION.md" >&2
    exit 2
fi

echo "========================================="
echo "sweep_param.sh"
echo "========================================="
echo "Parameter: ${PARAM_NAME}"
echo "Values: ${VALUES[@]}"
echo ""

# Backup config.h
cp "${CONFIG_H}" "${CONFIG_H}.sweep_backup"
echo "[backup] Created: ${CONFIG_H}.sweep_backup"

# Source ESP-IDF
set +u
source "${IDF_PATH:?Set IDF_PATH}/export.sh" > /dev/null 2>&1
set -u

for VALUE in "${VALUES[@]}"; do
    echo ""
    echo "========================================="
    echo "Testing: ${PARAM_NAME} = ${VALUE}"
    echo "========================================="

    # Restore backup first
    cp "${CONFIG_H}.sweep_backup" "${CONFIG_H}"

    # Modify parameter based on type
    case "${PARAM_NAME}" in
        heartbeat_period)
            sed -i "s/const uint16_t SF_WRITER_HB_PERIOD_MS = [0-9]\+/const uint16_t SF_WRITER_HB_PERIOD_MS = ${VALUE}/" "${CONFIG_H}"
            ;;
        history_size)
            sed -i "s/const uint8_t HISTORY_SIZE_STATEFUL = [0-9]\+/const uint8_t HISTORY_SIZE_STATEFUL = ${VALUE}/" "${CONFIG_H}"
            ;;
        spdp_period)
            sed -i "s/const uint16_t SPDP_RESEND_PERIOD_MS = [0-9]\+/const uint16_t SPDP_RESEND_PERIOD_MS = ${VALUE}/" "${CONFIG_H}"
            ;;
        lease_duration)
            # Format: VALUE is "12,0" for {12, 0}
            IFS=',' read -r SEC NSEC <<< "${VALUE}"
            sed -i "s/const Duration_t SPDP_DEFAULT_REMOTE_LEASE_DURATION = {[^}]*}/const Duration_t SPDP_DEFAULT_REMOTE_LEASE_DURATION = {${SEC}, ${NSEC}}/" "${CONFIG_H}"
            ;;
        *)
            echo "[ERROR] Unknown parameter: ${PARAM_NAME}"
            exit 1
            ;;
    esac

    echo "[modified] ${PARAM_NAME} = ${VALUE}"

    # Build
    cd "${WORKSPACE}"
    echo "[build] Building firmware..."
    if ! idf.py build > /tmp/sweep_build_${VALUE}.log 2>&1; then
        echo "[FAIL] Build failed, see /tmp/sweep_build_${VALUE}.log"
        continue
    fi

    # Flash
    echo "[flash] Flashing..."
    if ! idf.py -p /dev/ttyUSB0 flash > /tmp/sweep_flash_${VALUE}.log 2>&1; then
        echo "[FAIL] Flash failed, see /tmp/sweep_flash_${VALUE}.log"
        continue
    fi

    echo "[flash] Complete, waiting for settle (5s)..."
    sleep 5

    # Run tests
    CONDITION="${PARAM_NAME}_${VALUE}"
    "${SCRIPT_DIR}/run_matrix.sh" "mros2qos" "${CONDITION}" 30

    echo "[sweep] ${PARAM_NAME}=${VALUE} complete"
done

# Restore original
cp "${CONFIG_H}.sweep_backup" "${CONFIG_H}"
echo ""
echo "[restore] Original config.h restored"

echo ""
echo "========================================="
echo "Parameter sweep complete"
echo "========================================="
echo "Parameter: ${PARAM_NAME}"
echo "Values tested: ${VALUES[@]}"
echo "Results in: results/experiments/<date>/"
