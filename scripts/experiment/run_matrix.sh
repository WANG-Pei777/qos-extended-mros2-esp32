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
HOST_MODE="${HOST_MODE:-python}"
QOS_MODE="${QOS_MODE:-reliable}"
FIRMWARE_MODE="${FIRMWARE_MODE:-}"
FIRMWARE_BINARY="${FIRMWARE_BINARY:-}"
FORMAL_RUN="${FORMAL_RUN:-0}"
INJECTION_LAYER="${INJECTION_LAYER:-}"

DATE="${RESULTS_DATE:-$(date +%Y%m%d)}"
RESULTS_DIR="${PROJECT_ROOT}/results/experiments/${DATE}"
OUTPUT_CSV="${RESULTS_DIR}/${SYSTEM}_${CONDITION}.csv"
RTT_SAMPLES_CSV="${RESULTS_DIR}/${SYSTEM}_${CONDITION}_rtt_samples.csv"
MANIFEST_PATH="${RESULTS_DIR}/${SYSTEM}_${CONDITION}_manifest.json"
CSV_HEADER="run_id,timestamp,system,condition,formal_run,qos_mode,firmware_mode,injection_layer,host_mode,host_loss_rate,host_injection_attempted,host_injection_dropped,host_injection_observed_rate,tx_count,rx_count,rx_raw_count,rx_duplicate_count,rx_malformed_count,rx_pre_measurement_count,rx_tracker_overflow_count,rtt_min_us,rtt_avg_us,rtt_max_us,rtt_count,matched_pub,matched_sub,match_wait_ms,board_packets_dropped,rssi,channel,manifest_sha256,commit_hash,worktree_state,worktree_fingerprint,link_ping_avg_ms"
RTT_SAMPLES_HEADER="run_id,timestamp,system,condition,qos_mode,firmware_mode,injection_layer,sequence,rtt_us,manifest_sha256,commit_hash"

case "${QOS_MODE}" in
    reliable)
        HOST_QOS_FLAG="--reliable"
        ;;
    best_effort)
        HOST_QOS_FLAG="--best-effort"
        ;;
    *)
        echo "Error: QOS_MODE must be reliable or best_effort (got '${QOS_MODE}')" >&2
        exit 2
        ;;
esac

case "${FORMAL_RUN}" in
    0|1)
        ;;
    *)
        echo "Error: FORMAL_RUN must be 0 or 1" >&2
        exit 2
        ;;
esac

if [ -z "${FIRMWARE_MODE}" ]; then
    if [ "${FORMAL_RUN}" = "1" ]; then
        echo "Error: FORMAL_RUN=1 requires explicit FIRMWARE_MODE provenance" >&2
        exit 2
    fi
    FIRMWARE_MODE="unspecified"
fi

if [ -z "${FIRMWARE_BINARY}" ]; then
    if [ "${FORMAL_RUN}" = "1" ]; then
        echo "Error: FORMAL_RUN=1 requires FIRMWARE_BINARY for binary provenance" >&2
        exit 2
    fi
    FIRMWARE_BINARY=""
elif [ ! -f "${FIRMWARE_BINARY}" ]; then
    echo "Error: FIRMWARE_BINARY does not exist: ${FIRMWARE_BINARY}" >&2
    exit 2
fi

if [ -z "${INJECTION_LAYER}" ]; then
    case "${HOST_MODE}" in
        lossy:*) INJECTION_LAYER="application_reply" ;;
        *) INJECTION_LAYER="none" ;;
    esac
fi

mkdir -p "${RESULTS_DIR}"

echo "========================================="
echo "run_matrix.sh"
echo "========================================="
echo "System: ${SYSTEM}"
echo "Condition: ${CONDITION}"
echo "Repetitions: ${N}"
echo "Output: ${OUTPUT_CSV}"
echo "QoS: host=${QOS_MODE}, firmware=${FIRMWARE_MODE}, host_mode=${HOST_MODE}, injection=${INJECTION_LAYER}"
echo ""

# Never append a new protocol row to a legacy CSV.
if [ ! -f "${OUTPUT_CSV}" ]; then
    echo "${CSV_HEADER}" > "${OUTPUT_CSV}"
elif [ "$(head -n 1 "${OUTPUT_CSV}")" != "${CSV_HEADER}" ]; then
    echo "Error: ${OUTPUT_CSV} uses a legacy or incompatible CSV schema." >&2
    echo "Choose a new condition label; do not mix ROUND4 rows with prior data." >&2
    exit 2
fi

if [ ! -f "${RTT_SAMPLES_CSV}" ]; then
    echo "${RTT_SAMPLES_HEADER}" > "${RTT_SAMPLES_CSV}"
elif [ "$(head -n 1 "${RTT_SAMPLES_CSV}")" != "${RTT_SAMPLES_HEADER}" ]; then
    echo "Error: ${RTT_SAMPLES_CSV} uses an incompatible RTT sample schema." >&2
    echo "Choose a new condition label; do not mix per-message RTT rows with prior data." >&2
    exit 2
fi

COMMIT_HASH=$(cd "${PROJECT_ROOT}" && git rev-parse HEAD)
if [ -n "$(cd "${PROJECT_ROOT}" && git status --porcelain=v1)" ]; then
    WORKTREE_STATE="dirty"
    WORKTREE_FINGERPRINT=$(cd "${PROJECT_ROOT}" && {
        git diff --binary
        git diff --cached --binary
        git status --porcelain=v1
        git ls-files --others --exclude-standard | while IFS= read -r path; do
            sha256sum "${path}"
        done
    } | sha256sum | awk '{print $1}')
else
    WORKTREE_STATE="clean"
    WORKTREE_FINGERPRINT="clean"
fi

if [ "${FORMAL_RUN}" = "1" ] && [ "${WORKTREE_STATE}" != "clean" ]; then
    echo "Error: FORMAL_RUN=1 requires a clean git worktree; current state is dirty." >&2
    echo "Commit the validated harness or run a non-formal pilot with FORMAL_RUN=0." >&2
    exit 2
fi

EXISTING_RUNS="$(($(wc -l < "${OUTPUT_CSV}") - 1))"
if [ "${EXISTING_RUNS}" -lt 0 ]; then
    EXISTING_RUNS=0
fi

# Source ROS2
set +u
source /opt/ros/humble/setup.bash
set -u

export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"
export ROS_LOCALHOST_ONLY="${ROS_LOCALHOST_ONLY:-0}"

BOARD_IP="${BOARD_IP:-10.84.233.107}"
LINK_GATE_MS="${LINK_GATE_MS:-100}"
if [ "${LINK_GATE_MS}" = "0" ]; then
    echo "[link-gate] LINK_GATE_MS=0 is prohibited by ROUND4; aborting" >&2
    exit 2
fi

HOST_BINARY=""
case "${HOST_MODE}" in
    cpp)
        HOST_BINARY="${PROJECT_ROOT}/tools/echo_cpp/install/echo_cpp/lib/echo_cpp/echo_node"
        ;;
    lossy:*)
        HOST_BINARY="${PROJECT_ROOT}/tools/echo_cpp/install/echo_cpp/lib/echo_cpp/echo_node_lossy"
        ;;
esac

MANIFEST_SHA=$(python3 "${SCRIPT_DIR}/write_manifest.py" \
    --path "${MANIFEST_PATH}" \
    --project-root "${PROJECT_ROOT}" \
    --system "${SYSTEM}" \
    --condition "${CONDITION}" \
    --formal-run "${FORMAL_RUN}" \
    --qos-mode "${QOS_MODE}" \
    --firmware-mode "${FIRMWARE_MODE}" \
    --host-mode "${HOST_MODE}" \
    --injection-layer "${INJECTION_LAYER}" \
    --board-ip "${BOARD_IP}" \
    --link-gate-ms "${LINK_GATE_MS}" \
    --commit-hash "${COMMIT_HASH}" \
    --worktree-state "${WORKTREE_STATE}" \
    --worktree-fingerprint "${WORKTREE_FINGERPRINT}" \
    --host-binary "${HOST_BINARY}" \
    --firmware-binary "${FIRMWARE_BINARY}")
echo "Manifest: ${MANIFEST_PATH} (${MANIFEST_SHA})"

for i in $(seq 1 ${N}); do
    echo ""
    RUN_ID="$((EXISTING_RUNS + i))"
    echo "--- Run ${i}/${N} (run_id=${RUN_ID}) ---"
    TIMESTAMP=$(date +%s)

    SERIAL_LOG="${RESULTS_DIR}/${SYSTEM}_${CONDITION}_run${RUN_ID}_serial.log"
    HOST_LOG="${RESULTS_DIR}/${SYSTEM}_${CONDITION}_run${RUN_ID}_host.log"

    # Clean up any existing processes (skip in external mode per F1)
    # B1 fix: -fx full-match patterns matched NOTHING against real cmdlines
    # ("...echo_node_lossy --reliable --loss 0.50") -> cleanup was a no-op and
    # hosts stacked across runs (the 9-zombie incident). Use path substrings.
    if [ "${HOST_MODE}" != "external" ]; then
        pkill -9 -f "echo_cpp/echo_node" 2>/dev/null || true
        pkill -9 -f "echo_reply.py" 2>/dev/null || true
        sleep 1
    fi

    # F1 fix: HOST_MODE controls echo host startup.
    # Modes: "python" (legacy), "cpp" (echo_cpp), "lossy:RATE" (echo_node_lossy), "external" (user-managed)
    HOST_PID=""

    if [ "${HOST_MODE}" = "python" ]; then
        if [ "${QOS_MODE}" != "reliable" ]; then
            echo "Error: HOST_MODE=python does not expose a BEST_EFFORT QoS setting" >&2
            exit 2
        fi
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
        # B2 fix: launch the node binary DIRECTLY. `ros2 run` makes HOST_PID a
        # python wrapper; killing the wrapper orphans the actual node.
        "${PROJECT_ROOT}/tools/echo_cpp/install/echo_cpp/lib/echo_cpp/echo_node" \
            "${HOST_QOS_FLAG}" > "${HOST_LOG}" 2>&1 &
        HOST_PID=$!
        trap "kill ${HOST_PID} 2>/dev/null || true" EXIT
        sleep 5
    elif [[ "${HOST_MODE}" =~ ^lossy: ]]; then
        # Lossy injection mode: echo_node_lossy with specified loss rate
        LOSS_RATE="${HOST_MODE#lossy:}"
        if ! [[ "${LOSS_RATE}" =~ ^([0-9]+([.][0-9]*)?|[.][0-9]+)$ ]] || \
           ! awk -v rate="${LOSS_RATE}" 'BEGIN { exit !(rate >= 0 && rate <= 1) }'; then
            echo "Error: lossy HOST_MODE requires a rate in [0, 1] (got '${LOSS_RATE}')" >&2
            exit 2
        fi
        set +u
        source /opt/ros/humble/setup.bash
        source "${PROJECT_ROOT}/tools/echo_cpp/install/setup.bash"
        set -u
        # B2 fix: direct binary launch (see cpp mode note above)
        "${PROJECT_ROOT}/tools/echo_cpp/install/echo_cpp/lib/echo_cpp/echo_node_lossy" \
            "${HOST_QOS_FLAG}" --loss "${LOSS_RATE}" > "${HOST_LOG}" 2>&1 &
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

    # Link-health covariate (RSSI is unavailable on the frozen firmware):
    # ICMP avg to the board right before the run. Detects transient network
    # degradation windows (e.g. post-WSL-restart 1s+ DDS latency, 2026-07-10)
    # so affected runs can be identified/covaried in analysis.
    # Admission gate: the link oscillates between healthy (~15 ms) and 1 s+
    # windows on a minutes scale (observed 2026-07-10). Wait out bad windows
    # instead of collecting garbage.
    PING_AVG=""
    for attempt in $(seq 1 10); do
        PING_AVG=$(ping -c 5 -i 0.2 -W 1 "${BOARD_IP}" 2>/dev/null \
            | grep -oE 'rtt min/avg/max/mdev = [0-9.]+/[0-9.]+' \
            | grep -oE '[0-9.]+$' || echo "")
        if { [ -n "${PING_AVG}" ] && \
             awk -v avg="${PING_AVG}" -v limit="${LINK_GATE_MS}" 'BEGIN { exit !(avg < limit) }'; }; then
            break
        fi
        echo "[link-gate] ping_avg=${PING_AVG:-timeout} ms >= ${LINK_GATE_MS} ms, waiting 30 s (${attempt}/10)"
        sleep 30
    done
    if [ -z "${PING_AVG}" ] || \
       ! awk -v avg="${PING_AVG}" -v limit="${LINK_GATE_MS}" 'BEGIN { exit !(avg < limit) }'; then
        echo "[link-gate] failed: ping_avg=${PING_AVG:-timeout} ms >= ${LINK_GATE_MS} ms; aborting" >&2
        exit 2
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

    # Parse board and host evidence into one schema-bound row.
    python3 - "${SERIAL_LOG}" "${HOST_LOG}" "${OUTPUT_CSV}" "${RTT_SAMPLES_CSV}" "${RUN_ID}" "${TIMESTAMP}" "${SYSTEM}" "${CONDITION}" "${FORMAL_RUN}" "${QOS_MODE}" "${FIRMWARE_MODE}" "${INJECTION_LAYER}" "${HOST_MODE}" "${MANIFEST_SHA}" "${COMMIT_HASH}" "${WORKTREE_STATE}" "${WORKTREE_FINGERPRINT}" "${PING_AVG}" <<'PY'
import csv
import re
import sys

serial_log_path = sys.argv[1]
host_log_path = sys.argv[2]
output_csv = sys.argv[3]
rtt_samples_csv = sys.argv[4]
run_id = sys.argv[5]
timestamp = sys.argv[6]
system = sys.argv[7]
condition = sys.argv[8]
formal_run = sys.argv[9]
qos_mode = sys.argv[10]
firmware_mode = sys.argv[11]
injection_layer = sys.argv[12]
host_mode = sys.argv[13]
manifest_sha256 = sys.argv[14]
commit_hash = sys.argv[15]
worktree_state = sys.argv[16]
worktree_fingerprint = sys.argv[17]
link_ping_avg_ms = sys.argv[18]

with open(serial_log_path, encoding='utf-8', errors='replace') as f:
    serial_content = f.read()

try:
    with open(host_log_path, encoding='utf-8', errors='replace') as f:
        host_content = f.read()
except FileNotFoundError:
    host_content = ""


def final_int(pattern, content):
    matches = re.findall(pattern, content)
    return int(matches[-1]) if matches else 0


tx_count = final_int(r'TX:\s+(\d+)\s+msgs', serial_content)
rx_count = final_int(r'RX:\s+(\d+)\s+msgs', serial_content)
rx_raw_count = final_int(r'RX raw observations:\s+(\d+)', serial_content)
rx_duplicate_count = final_int(r'RX duplicate replies:\s+(\d+)', serial_content)
rx_malformed_count = final_int(r'RX malformed replies:\s+(\d+)', serial_content)
rx_pre_measurement_count = final_int(r'RX pre-measurement replies:\s+(\d+)', serial_content)
rx_tracker_overflow_count = final_int(r'RX sequence tracker overflow:\s+(\d+)', serial_content)
rtt_min = float(final_int(r'Min:\s+(\d+)\s+us', serial_content))
rtt_max = float(final_int(r'Max:\s+(\d+)\s+us', serial_content))
rtt_avg = float(final_int(r'Avg:\s+(\d+)\s+us', serial_content))
rtt_count = final_int(r'Samples:\s+(\d+)', serial_content)

# Old format for backward compatibility with board serial output.
if rtt_min == 0 and rtt_max == 0:
    rtt_us = [float(value) * 1000 for value in re.findall(r'RTT:\s+([\d.]+)\s+ms', serial_content)]
    if rtt_us:
        rtt_min = min(rtt_us)
        rtt_max = max(rtt_us)
        rtt_avg = sum(rtt_us) / len(rtt_us)
        rtt_count = len(rtt_us)

matched_pub = int('publisher matched with remote subscriber' in serial_content)
matched_sub = int('subscriber matched with remote publisher' in serial_content)
match_wait_ms = final_int(r'Match state.*?wait=(\d+)ms', serial_content)
board_packets_dropped = final_int(r'Packets Dropped:\s+(\d+)', serial_content)

host_loss_rate = ""
host_injection_attempted = ""
host_injection_dropped = ""
host_injection_observed_rate = ""
if host_mode.startswith('lossy:'):
    host_loss_rate = host_mode.split(':', 1)[1]
    summaries = re.findall(
        r'INJECTION_SUMMARY attempted=(\d+) echoed=(\d+) dropped=(\d+) configured_rate=([0-9.]+)',
        host_content,
    )
    progress = re.findall(r'Echoed:\s*(\d+),\s*Dropped:\s*(\d+)', host_content)
    if summaries:
        attempted, _echoed, dropped, _configured_rate = summaries[-1]
        host_injection_attempted = int(attempted)
        host_injection_dropped = int(dropped)
    elif progress:
        echoed, dropped = progress[-1]
        host_injection_attempted = int(echoed) + int(dropped)
        host_injection_dropped = int(dropped)

    if host_injection_attempted:
        host_injection_observed_rate = f"{host_injection_dropped / host_injection_attempted:.6f}"

with open(output_csv, 'a', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow([
        run_id, timestamp, system, condition, formal_run, qos_mode, firmware_mode,
        injection_layer, host_mode, host_loss_rate, host_injection_attempted, host_injection_dropped,
        host_injection_observed_rate, tx_count, rx_count, rx_raw_count, rx_duplicate_count,
        rx_malformed_count, rx_pre_measurement_count, rx_tracker_overflow_count, f"{rtt_min:.0f}",
        f"{rtt_avg:.0f}", f"{rtt_max:.0f}", rtt_count, matched_pub, matched_sub,
        match_wait_ms, board_packets_dropped, "", "", manifest_sha256, commit_hash, worktree_state,
        worktree_fingerprint, link_ping_avg_ms,
    ])

rtt_samples = re.findall(r'RTT_SAMPLE\s+seq=(\d+)\s+rtt_us=(\d+)', serial_content)
if rtt_samples:
    with open(rtt_samples_csv, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        for sequence, rtt_us in rtt_samples:
            writer.writerow([
                run_id, timestamp, system, condition, qos_mode, firmware_mode,
                injection_layer, sequence, rtt_us, manifest_sha256, commit_hash,
            ])

injection = "n/a"
if host_injection_attempted != "":
    injection = f"{host_injection_dropped}/{host_injection_attempted}"
print(
    f"[result] TX={tx_count} RX={rx_count} RTT={rtt_count} "
    f"samples={len(rtt_samples)} matched={matched_pub}&{matched_sub} injection={injection}"
)
PY

    echo "[run ${RUN_ID}] Complete"
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
