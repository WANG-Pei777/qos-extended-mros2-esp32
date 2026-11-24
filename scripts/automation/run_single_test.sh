#!/usr/bin/env bash
#
# Run a single test iteration with tshark capture
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Arguments
PORT="${1:?Missing serial port}"
CAPTURE_DURATION="${2:-75}"
OUTPUT_PREFIX="${3:?Missing output prefix}"
RUN_ID="${4:-1}"

# Setup ROS2 environment
set +u
source /opt/ros/humble/setup.bash
set -u
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"
export ROS_LOCALHOST_ONLY="${ROS_LOCALHOST_ONLY:-0}"

PCAP_FILE="${OUTPUT_PREFIX}_run${RUN_ID}.pcapng"
SERIAL_LOG="${OUTPUT_PREFIX}_run${RUN_ID}_serial.log"
HOST_LOG="${OUTPUT_PREFIX}_run${RUN_ID}_host.log"
STATS_FILE="${OUTPUT_PREFIX}_run${RUN_ID}_stats.json"

echo "[test] Run ${RUN_ID}"
echo "[test] Port: ${PORT}"
echo "[test] Duration: ${CAPTURE_DURATION}s"
echo "[test] PCAP: ${PCAP_FILE}"

# Clean up any existing processes
pgrep -f "echo_reply.py" | xargs -r kill -9 || true
pgrep -f "idf_monitor.py" | xargs -r kill -9 || true
sleep 1

# Start tshark capture in background
echo "[test] Starting tshark capture..."
tshark -i any -f "udp portrange 7400-7420" -w "${PCAP_FILE}" \
  -a duration:${CAPTURE_DURATION} > /dev/null 2>&1 &
TSHARK_PID=$!

# Wait for tshark to initialize
sleep 2

# Start ROS2 echo host
echo "[test] Starting ROS2 echo host..."
QOS_VALIDATION_SKIP_KILL=1 "${PROJECT_ROOT}/scripts/validation/qos_host.sh" all \
  > "${HOST_LOG}" 2>&1 &
HOST_PID=$!

# Wait for host to settle
sleep 5

# Reset ESP32 and capture serial output
echo "[test] Resetting ESP32 and capturing serial..."
python3 - "${PORT}" "${CAPTURE_DURATION}" "${SERIAL_LOG}" <<'PY'
import serial
import sys
import time

port = sys.argv[1]
seconds = float(sys.argv[2])
log_path = sys.argv[3]

ser = serial.Serial(port, 115200, timeout=0.2)
try:
    # Hardware reset via DTR/RTS
    ser.dtr = False
    ser.rts = True
    time.sleep(0.15)
    ser.rts = False
    time.sleep(0.2)
except Exception as exc:
    print(f"[warn] reset toggle: {exc}", file=sys.stderr)

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

# Wait for tshark to finish
echo "[test] Waiting for tshark to complete..."
wait ${TSHARK_PID} 2>/dev/null || true

# Kill host
kill ${HOST_PID} 2>/dev/null || true
wait ${HOST_PID} 2>/dev/null || true

# Extract statistics from serial log
echo "[test] Extracting statistics..."
python3 - "${SERIAL_LOG}" "${STATS_FILE}" <<'PY'
import json
import re
import sys

log_path = sys.argv[1]
output_path = sys.argv[2]

with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

stats = {
    'tx_count': 0,
    'rx_count': 0,
    'rtt_ms': [],
    'matched_pub': False,
    'matched_sub': False,
    'packets_dropped': 0
}

# Extract TX/RX counts
tx_match = re.search(r'TX:\s+(\d+)\s+msgs', content)
if tx_match:
    stats['tx_count'] = int(tx_match.group(1))

rx_match = re.search(r'RX:\s+(\d+)\s+msgs', content)
if rx_match:
    stats['rx_count'] = int(rx_match.group(1))

# Extract RTT values (format: "RTT: 15.2 ms")
rtt_matches = re.findall(r'RTT:\s+([\d.]+)\s+ms', content)
stats['rtt_ms'] = [float(x) for x in rtt_matches]

# Check matching
if 'publisher matched with remote subscriber' in content:
    stats['matched_pub'] = True
if 'subscriber matched with remote publisher' in content:
    stats['matched_sub'] = True

# Extract packet drops
drop_match = re.search(r'Packets Dropped:\s+(\d+)', content)
if drop_match:
    stats['packets_dropped'] = int(drop_match.group(1))

# Calculate RTT statistics
if stats['rtt_ms']:
    stats['rtt_min'] = min(stats['rtt_ms'])
    stats['rtt_max'] = max(stats['rtt_ms'])
    stats['rtt_avg'] = sum(stats['rtt_ms']) / len(stats['rtt_ms'])
    stats['rtt_count'] = len(stats['rtt_ms'])

with open(output_path, 'w') as f:
    json.dump(stats, f, indent=2)

print(f"[stats] TX={stats['tx_count']} RX={stats['rx_count']} RTT_count={len(stats['rtt_ms'])}")
if stats['rtt_ms']:
    print(f"[stats] RTT: min={stats['rtt_min']:.1f} avg={stats['rtt_avg']:.1f} max={stats['rtt_max']:.1f} ms")
PY

echo "[test] Run ${RUN_ID} complete"
echo "[test] Files:"
echo "  PCAP:   ${PCAP_FILE}"
echo "  Serial: ${SERIAL_LOG}"
echo "  Stats:  ${STATS_FILE}"
