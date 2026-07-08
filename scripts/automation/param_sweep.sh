#!/usr/bin/env bash
#
# Master script for parameter sweep experiments
# Automatically modifies parameters, rebuilds firmware, and runs N=30 tests
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/config.json"

# Parse arguments
PARAM_NAME="${1:?Usage: $0 <parameter_name> [port] [repetitions]}"
PORT="${2:-/dev/ttyUSB0}"
REPETITIONS="${3:-30}"

echo "========================================="
echo "Parameter Sweep Automation"
echo "========================================="
echo "Parameter: ${PARAM_NAME}"
echo "Port: ${PORT}"
echo "Repetitions per value: ${REPETITIONS}"
echo ""

# Load configuration
if [ ! -f "${CONFIG_FILE}" ]; then
    echo "[error] Config file not found: ${CONFIG_FILE}"
    exit 1
fi

# Extract parameter values from config
PARAM_VALUES=$(python3 - "${CONFIG_FILE}" "${PARAM_NAME}" <<'PY'
import json
import sys

with open(sys.argv[1]) as f:
    config = json.load(f)

param_name = sys.argv[2]
if param_name not in config['parameters']:
    print(f"[error] Unknown parameter: {param_name}", file=sys.stderr)
    sys.exit(1)

param_config = config['parameters'][param_name]
values = param_config['values']

# Format values for bash array
if param_name == 'lease_duration':
    # Format: "5,0 12,0 30,0 ..."
    formatted = ' '.join([f"{v['seconds']},{v['nanoseconds']}" for v in values])
else:
    formatted = ' '.join([str(v) for v in values])

print(formatted)
PY
)

if [ $? -ne 0 ]; then
    echo "[error] Failed to load parameter values"
    exit 1
fi

echo "[sweep] Parameter values: ${PARAM_VALUES}"
echo ""

# Create results directory
RESULTS_BASE="${PROJECT_ROOT}/results/param_sweep/${PARAM_NAME}"
mkdir -p "${RESULTS_BASE}"

# Create backup of config.h
echo "[sweep] Creating backup of config.h..."
"${SCRIPT_DIR}/modify_param.py" --config "${CONFIG_FILE}" --param "${PARAM_NAME}" \
  --value "0" --backup || true

# Source ESP-IDF environment
echo "[sweep] Setting up ESP-IDF environment..."
set +u
source /home/wsde-47/esp/esp-idf/export.sh
set -u

# Track start time
SWEEP_START=$(date +%s)
TOTAL_VALUES=$(echo ${PARAM_VALUES} | wc -w)
VALUE_INDEX=0

# Sweep over parameter values
for VALUE in ${PARAM_VALUES}; do
    VALUE_INDEX=$((VALUE_INDEX + 1))
    echo ""
    echo "========================================="
    echo "[sweep] Parameter value ${VALUE_INDEX}/${TOTAL_VALUES}: ${VALUE}"
    echo "========================================="

    VALUE_START=$(date +%s)

    # Modify parameter
    echo "[sweep] Modifying parameter..."
    "${SCRIPT_DIR}/modify_param.py" --config "${CONFIG_FILE}" \
      --param "${PARAM_NAME}" --value "${VALUE}"

    if [ $? -ne 0 ]; then
        echo "[error] Failed to modify parameter"
        continue
    fi

    # Build firmware
    echo "[sweep] Building firmware..."
    cd "${PROJECT_ROOT}"
    BUILD_LOG="${RESULTS_BASE}/build_${VALUE}.log"

    if idf.py build > "${BUILD_LOG}" 2>&1; then
        echo "[sweep] Build successful"
    else
        echo "[error] Build failed, see: ${BUILD_LOG}"
        continue
    fi

    # Flash firmware
    echo "[sweep] Flashing firmware..."
    FLASH_LOG="${RESULTS_BASE}/flash_${VALUE}.log"

    if idf.py -p "${PORT}" flash > "${FLASH_LOG}" 2>&1; then
        echo "[sweep] Flash successful"
    else
        echo "[error] Flash failed, see: ${FLASH_LOG}"
        continue
    fi

    # Wait for ESP32 to settle
    echo "[sweep] Waiting for ESP32 to settle (5s)..."
    sleep 5

    # Create output directory for this value
    VALUE_DIR="${RESULTS_BASE}/${VALUE}"
    mkdir -p "${VALUE_DIR}"
    OUTPUT_PREFIX="${VALUE_DIR}/test"

    # Run batch tests
    echo "[sweep] Running ${REPETITIONS} test iterations..."
    "${SCRIPT_DIR}/batch_test.sh" "${PORT}" "${OUTPUT_PREFIX}" "${REPETITIONS}"

    VALUE_END=$(date +%s)
    VALUE_ELAPSED=$((VALUE_END - VALUE_START))

    echo "[sweep] Value ${VALUE} completed in $((VALUE_ELAPSED / 60))m $((VALUE_ELAPSED % 60))s"

    # Estimate remaining time
    REMAINING=$((TOTAL_VALUES - VALUE_INDEX))
    if [ ${VALUE_INDEX} -gt 0 ]; then
        AVG_TIME=$(( (VALUE_END - SWEEP_START) / VALUE_INDEX ))
        EST_REMAINING=$((REMAINING * AVG_TIME))
        echo "[sweep] Estimated remaining: $((EST_REMAINING / 3600))h $((EST_REMAINING % 3600 / 60))m"
    fi
done

# Restore original config.h
echo ""
echo "[sweep] Restoring original config.h..."
"${SCRIPT_DIR}/modify_param.py" --config "${CONFIG_FILE}" \
  --param "${PARAM_NAME}" --restore

SWEEP_END=$(date +%s)
SWEEP_ELAPSED=$((SWEEP_END - SWEEP_START))

echo ""
echo "========================================="
echo "[sweep] Parameter sweep complete!"
echo "========================================="
echo "Parameter: ${PARAM_NAME}"
echo "Total values tested: ${TOTAL_VALUES}"
echo "Repetitions per value: ${REPETITIONS}"
echo "Total tests: $((TOTAL_VALUES * REPETITIONS))"
echo "Total time: $((SWEEP_ELAPSED / 3600))h $((SWEEP_ELAPSED % 3600 / 60))m $((SWEEP_ELAPSED % 60))s"
echo "Results directory: ${RESULTS_BASE}"
echo ""
echo "Next steps:"
echo "  1. Review aggregate statistics in each <value>/test_aggregate.json"
echo "  2. Open Wireshark to create evidence screenshots"
echo "  3. Run analysis scripts to generate comparison plots"
