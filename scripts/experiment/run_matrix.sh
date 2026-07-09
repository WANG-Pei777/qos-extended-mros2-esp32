#!/usr/bin/env bash
#
# run_matrix.sh - Run N repetitions of a test condition
# Usage: run_matrix.sh <system> <condition> <N>
#
# Output: results/experiments/<date>/<system>_<condition>.csv
#
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

SYSTEM="${1:?Usage: $0 <system> <condition> <N>}"
CONDITION="${2:?Missing condition}"
N="${3:-30}"

DATE=$(date +%Y%m%d)
RESULTS_DIR="${PROJECT_ROOT}/results/experiments/${DATE}"
OUTPUT_CSV="${RESULTS_DIR}/${SYSTEM}_${CONDITION}.csv"

mkdir -p "${RESULTS_DIR}"

echo "========================================="
echo "run_matrix.sh"
echo "========================================="
echo "System: ${SYSTEM}"
echo "Condition: ${CONDITION}"
echo "Repetitions: ${N}"
echo "Output: ${OUTPUT_CSV}"
echo ""

# Initialize CSV with header if not exists
if [ ! -f "${OUTPUT_CSV}" ]; then
    echo "run_id,timestamp,system,condition,tx_count,rx_count,rtt_min_us,rtt_avg_us,rtt_max_us,rtt_count,matched_pub,matched_sub,match_wait_ms,packets_dropped,rssi,channel,commit_hash" > "${OUTPUT_CSV}"
fi

COMMIT_HASH=$(cd "${PROJECT_ROOT}" && git rev-parse HEAD)

# Source ROS2
set +u
source /opt/ros/humble/setup.bash
set -u

export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"
export ROS_LOCALHOST_ONLY="${ROS_LOCALHOST_ONLY:-0}"

for i in $(seq 1 ${N}); do
    echo ""
    echo "--- Run ${i}/${N} ---"
    TIMESTAMP=$(date +%s)

    SERIAL_LOG="${RESULTS_DIR}/${SYSTEM}_${CONDITION}_run${i}_serial.log"
    HOST_LOG="${RESULTS_DIR}/${SYSTEM}_${CONDITION}_run${i}_host.log"

    # Clean up any existing processes (skip in external mode per F1)
    if [ "${HOST_MODE}" != "external" ]; then
        pgrep -fx "python3 .*echo_reply.py" | xargs -r kill -9 2>/dev/null || true
        pgrep -fx ".*/echo_node" | xargs -r kill -9 2>/dev/null || true
        sleep 1
    fi

    # F1 fix: HOST_MODE controls echo host startup
    # Modes: "python" (legacy), "cpp" (echo_cpp), "lossy:RATE" (echo_node_lossy), "external" (user-managed)
    HOST_MODE="${HOST_MODE:-python}"
    HOST_PID=""

    if [ "${HOST_MODE}" = "python" ]; then
        # Legacy Python echo_reply.py
        "${PROJECT_ROOT}/scripts/validation/qos_host.sh" all > "${HOST_LOG}" 2>&1 &
        HOST_PID=$!
        trap "kill ${HOST_PID} 2>/dev/null || true" EXIT
        sleep 5
    elif [ "${HOST_MODE}" = "cpp" ]; then
        # C++ echo_node (requires pre-built tools/echo_cpp)
        set +u  # Allow unbound variables for ROS2/colcon setup
        source /opt/ros/humble/setup.bash
        source "${PROJECT_ROOT}/tools/echo_cpp/install/setup.bash"
        set -u
        ros2 run echo_cpp echo_node --reliable > "${HOST_LOG}" 2>&1 &
        HOST_PID=$!
        trap "kill ${HOST_PID} 2>/dev/null || true" EXIT
        sleep 5
    elif [[ "${HOST_MODE}" =~ ^lossy: ]]; then
        # Lossy injection mode: echo_node_lossy with specified loss rate
        LOSS_RATE="${HOST_MODE#lossy:}"
        set +u
        source /opt/ros/humble/setup.bash
        source "${PROJECT_ROOT}/tools/echo_cpp/install/setup.bash"
        set -u
        ros2 run echo_cpp echo_node_lossy --reliable --loss "${LOSS_RATE}" > "${HOST_LOG}" 2>&1 &
        HOST_PID=$!
        trap "kill ${HOST_PID} 2>/dev/null || true" EXIT
        sleep 5
    elif [ "${HOST_MODE}" = "external" ]; then
        # User manages host externally (e.g., echo_node_lossy for E2)
        echo "[host] Using external HOST (HOST_MODE=external)" > "${HOST_LOG}"
        sleep 2
    else
        echo "Error: Unknown HOST_MODE='${HOST_MODE}'" >&2
        exit 1
    fi

    # Reset ESP32 and capture serial
    python3 - /dev/ttyUSB0 75 "${SERIAL_LOG}" <<'PY'
import serial
import sys
import time

port = sys.argv[1]
seconds = float(sys.argv[2])
log_path = sys.argv[3]

ser = serial.Serial(port, 115200, timeout=0.2)
try:
    ser.dtr = False
    ser.rts = True
    time.sleep(0.15)
    ser.rts = False
    time.sleep(0.2)
except Exception as exc:
    print(f"[warn] reset: {exc}", file=sys.stderr)

start = time.time()
with open(log_path, "w", encoding="utf-8", errors="replace") as log:
    while time.time() - start < seconds:
        data = ser.read(4096)
        if data:
            text = data.decode("utf-8", "replace")
            log.write(text)
            log.flush()
ser.close()
PY

    # Kill host (if managed by run_matrix)
    # F1 fix: external mode must not touch host process at all
    if [ "${HOST_MODE}" != "external" ] && [ -n "${HOST_PID}" ]; then
        kill ${HOST_PID} 2>/dev/null || true
        wait ${HOST_PID} 2>/dev/null || true
    fi

    # Parse results
    python3 - "${SERIAL_LOG}" "${OUTPUT_CSV}" "${i}" "${TIMESTAMP}" "${SYSTEM}" "${CONDITION}" "${COMMIT_HASH}" <<'PY'
import re
import sys

log_path = sys.argv[1]
output_csv = sys.argv[2]
run_id = sys.argv[3]
timestamp = sys.argv[4]
system = sys.argv[5]
condition = sys.argv[6]
commit_hash = sys.argv[7]

with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

# Extract metrics
tx_match = re.search(r'TX:\s+(\d+)\s+msgs', content)
rx_match = re.search(r'RX:\s+(\d+)\s+msgs', content)

tx_count = int(tx_match.group(1)) if tx_match else 0
rx_count = int(rx_match.group(1)) if rx_match else 0

# RTT values - parse from Latency section (microseconds)
# Format: "Min: 12345 us", "Max: 23456 us", "Avg: 15678 us"
min_match = re.search(r'Min:\s+(\d+)\s+us', content)
max_match = re.search(r'Max:\s+(\d+)\s+us', content)
avg_match = re.search(r'Avg:\s+(\d+)\s+us', content)

rtt_min = float(min_match.group(1)) if min_match else 0
rtt_max = float(max_match.group(1)) if max_match else 0
rtt_avg = float(avg_match.group(1)) if avg_match else 0

# Also check sample count
sample_match = re.search(r'Samples:\s+(\d+)', content)
rtt_count = int(sample_match.group(1)) if sample_match else 0

# Old format for backward compatibility
if rtt_min == 0 and rtt_max == 0:
    rtt_matches = re.findall(r'RTT:\s+([\d.]+)\s+ms', content)
    rtt_us = [float(x) * 1000 for x in rtt_matches]
    if rtt_us:
        rtt_min = min(rtt_us)
        rtt_max = max(rtt_us)
        rtt_avg = sum(rtt_us) / len(rtt_us)
        rtt_count = len(rtt_us)

# rtt_min, rtt_max, rtt_avg, rtt_count already set above

# Matching
matched_pub = 1 if 'publisher matched with remote subscriber' in content else 0
matched_sub = 1 if 'subscriber matched with remote publisher' in content else 0

match_wait_match = re.search(r'Match state.*?wait=(\d+)ms', content)
match_wait_ms = int(match_wait_match.group(1)) if match_wait_match else 0

# Packet drops
drop_match = re.search(r'Packets Dropped:\s+(\d+)', content)
packets_dropped = int(drop_match.group(1)) if drop_match else 0

# RSSI/Channel (would need to capture from WiFi status)
rssi = ""
channel = ""

# Append to CSV
with open(output_csv, 'a') as f:
    f.write(f"{run_id},{timestamp},{system},{condition},{tx_count},{rx_count},")
    f.write(f"{rtt_min:.0f},{rtt_avg:.0f},{rtt_max:.0f},{rtt_count},")
    f.write(f"{matched_pub},{matched_sub},{match_wait_ms},{packets_dropped},")
    f.write(f"{rssi},{channel},{commit_hash}\n")

print(f"[result] TX={tx_count} RX={rx_count} RTT={rtt_count} matched={matched_pub}&{matched_sub}")
PY

    echo "[run ${i}] Complete"
done

echo ""
echo "========================================="
echo "Matrix run complete: ${N} runs"
echo "========================================="
echo "Results: ${OUTPUT_CSV}"
echo ""
echo "Summary statistics:"
python3 - "${OUTPUT_CSV}" <<'PY'
import csv
import sys
from statistics import mean, stdev

csv_path = sys.argv[1]

with open(csv_path) as f:
    reader = csv.DictReader(f)
    data = list(reader)

if len(data) == 0:
    print("No data")
    sys.exit(0)

rtt_avgs = [float(row['rtt_avg_us']) for row in data if row['rtt_avg_us'] and float(row['rtt_avg_us']) > 0]
match_rate_pub = sum(int(row['matched_pub']) for row in data) / len(data)
match_rate_sub = sum(int(row['matched_sub']) for row in data) / len(data)

if rtt_avgs:
    if len(rtt_avgs) > 1:
        print(f"  RTT avg: {mean(rtt_avgs)/1000:.2f} ± {stdev(rtt_avgs)/1000:.2f} ms (n={len(rtt_avgs)})")
    else:
        print(f"  RTT avg: {mean(rtt_avgs)/1000:.2f} ms (n=1, no stdev)")
    print(f"  RTT range: [{min(rtt_avgs)/1000:.2f}, {max(rtt_avgs)/1000:.2f}] ms")
else:
    print("  RTT: no valid samples")

print(f"  Match rate: pub={match_rate_pub*100:.1f}% sub={match_rate_sub*100:.1f}%")
print(f"  Total runs: {len(data)}")
PY
