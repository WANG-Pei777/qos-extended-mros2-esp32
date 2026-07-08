#!/usr/bin/env bash
#
# Run all parameter sweeps overnight
# Estimated time: 12-15 hours for 4 core parameters
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${1:-/dev/ttyUSB0}"
REPETITIONS="${2:-30}"

echo "========================================="
echo "Automated Parameter Sweep - All Parameters"
echo "========================================="
echo "Port: ${PORT}"
echo "Repetitions per value: ${REPETITIONS}"
echo "Estimated total time: 12-15 hours"
echo ""
echo "Parameters to sweep:"
echo "  1. heartbeat_period (6 values × ${REPETITIONS} × 75s ≈ 3 hours)"
echo "  2. history_size     (6 values × ${REPETITIONS} × 75s ≈ 3 hours)"
echo "  3. spdp_period      (5 values × ${REPETITIONS} × 75s ≈ 3 hours)"
echo "  4. lease_duration   (5 values × ${REPETITIONS} × 75s ≈ 3 hours)"
echo ""
read -p "Press Enter to start, or Ctrl+C to cancel..."

OVERALL_START=$(date +%s)

# Define parameters in order
PARAMS=("heartbeat_period" "history_size" "spdp_period" "lease_duration")

for param in "${PARAMS[@]}"; do
    echo ""
    echo "========================================="
    echo "Starting sweep: ${param}"
    echo "Time: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "========================================="

    PARAM_START=$(date +%s)

    "${SCRIPT_DIR}/param_sweep.sh" "${param}" "${PORT}" "${REPETITIONS}"
    EXIT_CODE=$?

    PARAM_END=$(date +%s)
    PARAM_ELAPSED=$((PARAM_END - PARAM_START))

    if [ ${EXIT_CODE} -eq 0 ]; then
        echo ""
        echo "[✓] ${param} sweep COMPLETED in $((PARAM_ELAPSED / 3600))h $((PARAM_ELAPSED % 3600 / 60))m"
    else
        echo ""
        echo "[✗] ${param} sweep FAILED with exit code ${EXIT_CODE}"
        echo "    Continuing with next parameter..."
    fi

    # Brief pause between sweeps
    echo "    Pausing 10 seconds before next sweep..."
    sleep 10
done

OVERALL_END=$(date +%s)
OVERALL_ELAPSED=$((OVERALL_END - OVERALL_START))

echo ""
echo "========================================="
echo "ALL PARAMETER SWEEPS COMPLETE!"
echo "========================================="
echo "Total time: $((OVERALL_ELAPSED / 3600))h $((OVERALL_ELAPSED % 3600 / 60))m"
echo "Results directory: $(pwd)/results/param_sweep/"
echo ""
echo "Next steps:"
echo "  1. Check aggregate statistics:"
echo "     find results/param_sweep -name '*_aggregate.json' -exec cat {} \;"
echo "  2. Open representative pcapng files in Wireshark for evidence screenshots"
echo "  3. Run your analysis scripts to generate comparison plots"
echo ""
echo "Artifact evaluation tips:"
echo "  - All raw pcapng files are in results/param_sweep/"
echo "  - Each test has N=${REPETITIONS} repetitions for statistical significance"
echo "  - Use aggregate.json files for mean ± stdev reporting"
