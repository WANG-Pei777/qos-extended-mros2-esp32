#!/usr/bin/env bash
#
# Run N repetitions of a test for statistical significance
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Arguments
PORT="${1:?Missing serial port}"
OUTPUT_PREFIX="${2:?Missing output prefix}"
REPETITIONS="${3:-30}"
CAPTURE_DURATION="${4:-75}"

echo "[batch] Starting batch test"
echo "[batch] Repetitions: ${REPETITIONS}"
echo "[batch] Output prefix: ${OUTPUT_PREFIX}"

# Create output directory
OUTPUT_DIR="$(dirname "${OUTPUT_PREFIX}")"
mkdir -p "${OUTPUT_DIR}"

# Create summary file
SUMMARY_CSV="${OUTPUT_PREFIX}_summary.csv"
echo "run_id,tx_count,rx_count,rtt_count,rtt_min,rtt_avg,rtt_max,matched_pub,matched_sub,packets_dropped" > "${SUMMARY_CSV}"

# Run tests
for i in $(seq 1 ${REPETITIONS}); do
    echo ""
    echo "========================================="
    echo "[batch] Starting run ${i}/${REPETITIONS}"
    echo "========================================="

    START_TIME=$(date +%s)

    # Run single test
    "${SCRIPT_DIR}/run_single_test.sh" "${PORT}" "${CAPTURE_DURATION}" "${OUTPUT_PREFIX}" "${i}"

    # Parse stats and append to summary
    STATS_FILE="${OUTPUT_PREFIX}_run${i}_stats.json"
    if [ -f "${STATS_FILE}" ]; then
        python3 - "${STATS_FILE}" "${i}" "${SUMMARY_CSV}" <<'PY'
import json
import sys

stats_file = sys.argv[1]
run_id = sys.argv[2]
summary_file = sys.argv[3]

with open(stats_file) as f:
    stats = json.load(f)

# Append to CSV
with open(summary_file, 'a') as f:
    f.write(f"{run_id},")
    f.write(f"{stats.get('tx_count', 0)},")
    f.write(f"{stats.get('rx_count', 0)},")
    f.write(f"{stats.get('rtt_count', 0)},")
    f.write(f"{stats.get('rtt_min', '')},")
    f.write(f"{stats.get('rtt_avg', '')},")
    f.write(f"{stats.get('rtt_max', '')},")
    f.write(f"{1 if stats.get('matched_pub') else 0},")
    f.write(f"{1 if stats.get('matched_sub') else 0},")
    f.write(f"{stats.get('packets_dropped', 0)}\n")
PY
    fi

    END_TIME=$(date +%s)
    ELAPSED=$((END_TIME - START_TIME))
    REMAINING=$((REPETITIONS - i))
    EST_REMAINING=$((REMAINING * ELAPSED))

    echo "[batch] Run ${i} completed in ${ELAPSED}s"
    echo "[batch] Estimated remaining time: $((EST_REMAINING / 60))m $((EST_REMAINING % 60))s"
done

echo ""
echo "========================================="
echo "[batch] All runs complete"
echo "========================================="
echo "[batch] Summary: ${SUMMARY_CSV}"

# Generate aggregate statistics
python3 - "${SUMMARY_CSV}" "${OUTPUT_PREFIX}_aggregate.json" <<'PY'
import csv
import json
import sys
from statistics import mean, stdev

summary_file = sys.argv[1]
output_file = sys.argv[2]

data = []
with open(summary_file) as f:
    reader = csv.DictReader(f)
    data = list(reader)

# Calculate aggregates
rtt_avgs = [float(row['rtt_avg']) for row in data if row['rtt_avg']]
rtt_mins = [float(row['rtt_min']) for row in data if row['rtt_min']]
rtt_maxs = [float(row['rtt_max']) for row in data if row['rtt_max']]

aggregate = {
    'total_runs': len(data),
    'successful_runs': sum(1 for row in data if float(row.get('rtt_count', 0)) > 0),
    'rtt_avg': {
        'mean': mean(rtt_avgs) if rtt_avgs else 0,
        'stdev': stdev(rtt_avgs) if len(rtt_avgs) > 1 else 0,
        'min': min(rtt_avgs) if rtt_avgs else 0,
        'max': max(rtt_avgs) if rtt_avgs else 0
    },
    'rtt_min': {
        'mean': mean(rtt_mins) if rtt_mins else 0,
        'stdev': stdev(rtt_mins) if len(rtt_mins) > 1 else 0,
        'best': min(rtt_mins) if rtt_mins else 0
    },
    'rtt_max': {
        'mean': mean(rtt_maxs) if rtt_maxs else 0,
        'stdev': stdev(rtt_maxs) if len(rtt_maxs) > 1 else 0,
        'worst': max(rtt_maxs) if rtt_maxs else 0
    },
    'match_rate': {
        'publisher': sum(int(row['matched_pub']) for row in data) / len(data),
        'subscriber': sum(int(row['matched_sub']) for row in data) / len(data)
    }
}

with open(output_file, 'w') as f:
    json.dump(aggregate, f, indent=2)

print("\n[aggregate] Statistics:")
print(f"  Total runs: {aggregate['total_runs']}")
print(f"  Successful: {aggregate['successful_runs']}")
print(f"  RTT avg: {aggregate['rtt_avg']['mean']:.2f} ± {aggregate['rtt_avg']['stdev']:.2f} ms")
print(f"  RTT min: {aggregate['rtt_min']['mean']:.2f} ± {aggregate['rtt_min']['stdev']:.2f} ms")
print(f"  RTT max: {aggregate['rtt_max']['mean']:.2f} ± {aggregate['rtt_max']['stdev']:.2f} ms")
print(f"  Match rate: pub={aggregate['match_rate']['publisher']*100:.1f}% sub={aggregate['match_rate']['subscriber']*100:.1f}%")
PY

echo "[batch] Aggregate statistics: ${OUTPUT_PREFIX}_aggregate.json"
