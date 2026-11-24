#!/usr/bin/env bash
set -euo pipefail

PORT="${1:-/dev/ttyUSB0}"
CAPTURE_SECONDS="${2:-110}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SERIAL_LOG="${QOS_VERIFY_SERIAL_LOG:-/tmp/mros2_qos_serial.log}"
HOST_LOG="${QOS_VERIFY_HOST_LOG:-/tmp/mros2_qos_host.log}"
TOPIC_LOG="${QOS_VERIFY_TOPIC_LOG:-/tmp/mros2_qos_topic.log}"
EXPECT_REPLY_RELIABILITY="${QOS_VERIFY_EXPECT_REPLY_RELIABILITY:-RELIABLE}"
EXPECT_UPLINK_RELIABILITY="${QOS_VERIFY_EXPECT_UPLINK_RELIABILITY:-${EXPECT_REPLY_RELIABILITY}}"
HOST_IMPLEMENTATION="${QOS_VERIFY_HOST_IMPLEMENTATION:-python}"
EXPECT_HISTORY_DEPTH="${QOS_VERIFY_EXPECT_HISTORY_DEPTH:-5}"
EXPECT_HISTORY_CAPACITY="${QOS_VERIFY_EXPECT_HISTORY_CAPACITY:-10}"
EXPECT_HEARTBEAT_MS="${QOS_VERIFY_EXPECT_HEARTBEAT_MS:-4000}"
EXPECT_RESOURCE_MAX_SAMPLES="${QOS_VERIFY_EXPECT_RESOURCE_MAX_SAMPLES:-30}"
EXPECT_RESOURCE_MAX_BYTES="${QOS_VERIFY_EXPECT_RESOURCE_MAX_BYTES:-12288}"
MIN_RX="${QOS_VERIFY_MIN_RX:-10}"
HOST_SETTLE_SECONDS="${QOS_VERIFY_HOST_SETTLE_SECONDS:-8}"
DAEMON_SETTLE_SECONDS="${QOS_VERIFY_DAEMON_SETTLE_SECONDS:-2}"
CLEANUP_SETTLE_SECONDS="${QOS_VERIFY_CLEANUP_SETTLE_SECONDS:-2}"
TOPIC_SPIN_SECONDS="${QOS_VERIFY_TOPIC_SPIN_SECONDS:-8}"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/validation/qos_verify.sh [port] [capture_seconds]

Runs a real-hardware verification:
  1. Starts the ROS2 echo host.
  2. Resets ESP32 through the serial adapter.
  3. Captures ESP32 serial logs.
  4. Captures ROS2 topic info --verbose.
  5. Prints a PASS/FAIL summary.
EOF
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  usage
  exit 0
fi

case "${EXPECT_REPLY_RELIABILITY}" in
  RELIABLE) HOST_QOS_MODE="reliable" ;;
  BEST_EFFORT) HOST_QOS_MODE="best_effort" ;;
  *)
    echo "[verify] expected reply reliability must be RELIABLE or BEST_EFFORT" >&2
    exit 2
    ;;
esac

case "${EXPECT_UPLINK_RELIABILITY}" in
  RELIABLE|BEST_EFFORT) ;;
  *)
    echo "[verify] expected uplink reliability must be RELIABLE or BEST_EFFORT" >&2
    exit 2
    ;;
esac

case "${HOST_IMPLEMENTATION}" in
  python|cpp) ;;
  *)
    echo "[verify] host implementation must be python or cpp" >&2
    exit 2
    ;;
esac

if [ ! -e "${PORT}" ]; then
  echo "[verify] serial port not found: ${PORT}" >&2
  exit 1
fi

set +u
source /opt/ros/humble/setup.bash
set -u

export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"
export ROS_LOCALHOST_ONLY="${ROS_LOCALHOST_ONLY:-0}"

echo "[verify] project=${PROJECT_ROOT}"
echo "[verify] port=${PORT}"
echo "[verify] capture_seconds=${CAPTURE_SECONDS}"
echo "[verify] qos=${EXPECT_UPLINK_RELIABILITY}/${EXPECT_REPLY_RELIABILITY} host=${HOST_IMPLEMENTATION}"

pgrep -f "${PROJECT_ROOT}/workspace/qos_eval/echo_reply.py" | xargs -r kill || true
pgrep -f "${PROJECT_ROOT}/tools/echo_cpp/install/echo_cpp/lib/echo_cpp/echo_node" | xargs -r kill || true
pgrep -f "idf_monitor.py -p ${PORT}" | xargs -r kill || true
pgrep -f "esp_idf_monitor -p ${PORT}" | xargs -r kill || true
pgrep -f "idf.py -p ${PORT} monitor" | xargs -r kill || true
sleep "${CLEANUP_SETTLE_SECONDS}"

echo "[verify] refreshing ROS2 daemon"
ros2 daemon stop >/dev/null 2>&1 || true
sleep "${DAEMON_SETTLE_SECONDS}"
if [ "${QOS_VERIFY_START_ROS_DAEMON:-1}" = "1" ]; then
  ros2 daemon start >/dev/null 2>&1 || true
  sleep "${DAEMON_SETTLE_SECONDS}"
else
  echo "[verify] ROS2 daemon left stopped by QOS_VERIFY_START_ROS_DAEMON=0"
fi

rm -f "${SERIAL_LOG}" "${HOST_LOG}" "${TOPIC_LOG}"

echo "[verify] starting ROS2 echo host"
QOS_VALIDATION_SKIP_KILL=1 \
QOS_HOST_QOS_MODE="${HOST_QOS_MODE}" \
QOS_HOST_IMPLEMENTATION="${HOST_IMPLEMENTATION}" \
  "${PROJECT_ROOT}/scripts/validation/qos_host.sh" all \
  > "${HOST_LOG}" 2>&1 &
HOST_PID=$!
trap 'kill ${HOST_PID} 2>/dev/null || true; wait ${HOST_PID} 2>/dev/null || true' EXIT

sleep "${HOST_SETTLE_SECONDS}"
if ! kill -0 "${HOST_PID}" 2>/dev/null; then
  echo "[verify] host failed to start" >&2
  cat "${HOST_LOG}" >&2 || true
  exit 1
fi

echo "[verify] resetting ESP32 and capturing serial"
python3 - "${PORT}" "${CAPTURE_SECONDS}" "${SERIAL_LOG}" <<'PY'
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
    print(f"[verify] reset toggle warning: {exc}")

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

echo "[verify] capturing topic info"
{
  capture_topic() {
    local topic="$1"
    echo "=== ${topic} ==="
    if ! ros2 topic info "${topic}" --verbose 2>&1; then
      echo "[verify] daemon topic info failed; retrying --no-daemon"
      ros2 topic info "${topic}" --verbose --no-daemon --spin-time "${TOPIC_SPIN_SECONDS}" || true
    fi
  }
  capture_topic /qos_eval
  echo
  capture_topic /qos_eval_reply
} > "${TOPIC_LOG}" 2>&1

echo
echo "===== Serial Key Lines ====="
grep -E 'Reliability:|Durability|History|Deadline|Lifespan|Liveliness|Resources|Mechanism|Match state|matched|Warm-up|VALIDATION NOT READY|Echo reply|Reader heartbeat|Writer activity|finite lease behavior|RTPS QoS State|History cache|Writer deadline|Writer lifespan|Writer resource|Reader deadline|Reader received|Reader accepted-before-match|Reader out-of-order|Reader unmatched-writer|TX:|RX:|Packets Dropped|All phases complete|Resource stats|Rejected:' "${SERIAL_LOG}" || true

echo
echo "===== Host Key Lines ====="
grep -E 'Echo reply node started|Echo replies sent' "${HOST_LOG}" || true

echo
echo "===== Topic QoS Key Lines ====="
grep -E 'Type:|Publisher count|Subscription count|Node name|Reliability:|History|Durability:|Deadline:|Lifespan:|Liveliness:' "${TOPIC_LOG}" || true

rx_count="$(grep -Eo 'RX: [0-9]+ msgs' "${SERIAL_LOG}" | tail -n1 | awk '{print $2}' || true)"
rx_count="${rx_count:-0}"
host_replies="$(grep -Eo 'Echo replies sent: [0-9]+' "${HOST_LOG}" | tail -n1 | awk '{print $4}' || true)"
host_replies="${host_replies:-0}"

topic_section_has() {
  local topic="$1"
  local pattern="$2"
  awk -v topic="=== ${topic} ===" -v pattern="${pattern}" '
    $0 == topic { inside = 1; next }
    /^=== / && inside { inside = 0 }
    inside && $0 ~ pattern { found = 1 }
    END { exit found ? 0 : 1 }
  ' "${TOPIC_LOG}"
}

pass=1
check() {
  local label="$1"
  local command="$2"
  if eval "${command}"; then
    echo "[PASS] ${label}"
  else
    echo "[FAIL] ${label}"
    pass=0
  fi
}

echo
echo "===== Verification Summary ====="
check "ESP32 publisher matched ROS2 subscriber" "grep -q 'publisher matched with remote subscriber' '${SERIAL_LOG}'"
check "ESP32 subscriber matched ROS2 publisher" "grep -q 'subscriber matched with remote publisher' '${SERIAL_LOG}'"
check "No VALIDATION NOT READY marker" "test -z \"\$(grep -F 'VALIDATION NOT READY' '${SERIAL_LOG}' || true)\""
check "Warm-up confirmed bidirectional echo" "grep -q 'Warm-up reply confirmed' '${SERIAL_LOG}'"
check "ROS2 host reply publisher is ${EXPECT_REPLY_RELIABILITY}" "grep -q 'reply=${EXPECT_REPLY_RELIABILITY}' '${HOST_LOG}'"
check "ROS2 host sent echo replies" "[ '${host_replies}' -gt 0 ] || [ '${rx_count}' -ge '${MIN_RX}' ]"
check "ESP32 received enough ROS2 replies" "[ '${rx_count}' -ge '${MIN_RX}' ]"
check "No receive-path packet drops" "grep -q 'Packets Dropped:  0' '${SERIAL_LOG}'"
check "Hardware validation reached final phase" "grep -q 'All phases complete' '${SERIAL_LOG}'"
check "ESP32 DDS endpoint visible" "grep -q '_CREATED_BY_BARE_DDS_APP_' '${TOPIC_LOG}'"

echo
echo "===== ROS2 Topic Info Evidence (standard CLI) ====="
check "QoS 1 Reliability: ESP32->ROS2 ${EXPECT_UPLINK_RELIABILITY} visible" "topic_section_has '/qos_eval' 'Reliability: ${EXPECT_UPLINK_RELIABILITY}'"
check "QoS 1 Reliability: ROS2->ESP32 ${EXPECT_REPLY_RELIABILITY} visible" "topic_section_has '/qos_eval_reply' 'Reliability: ${EXPECT_REPLY_RELIABILITY}'"
check "QoS 2 Durability: VOLATILE visible on ESP32 and reply endpoints" "topic_section_has '/qos_eval' 'Durability: VOLATILE' && topic_section_has '/qos_eval_reply' 'Durability: VOLATILE'"
check "QoS 3 History: ROS2 CLI exposes History field" "topic_section_has '/qos_eval' 'History [(]Depth[)]:' && topic_section_has '/qos_eval_reply' 'History [(]Depth[)]:'"
check "QoS 4 Deadline: finite deadline visible on reply path" "topic_section_has '/qos_eval_reply' 'Deadline: 23283064 nanoseconds'"
check "QoS 5 Lifespan: finite lifespan visible on reply path" "topic_section_has '/qos_eval_reply' 'Lifespan: 2000000000 nanoseconds'"
check "QoS 6 Liveliness: AUTOMATIC visible on reply path" "topic_section_has '/qos_eval_reply' 'Liveliness: AUTOMATIC'"

echo
echo "===== ESP32 Behavior Evidence ====="
check "History behavior: KEEP_LAST(${EXPECT_HISTORY_DEPTH}) configured and enforced" "grep -q 'History    : KEEP_LAST(${EXPECT_HISTORY_DEPTH})' '${SERIAL_LOG}' && grep -q 'Mechanism    : capacity=${EXPECT_HISTORY_CAPACITY}, heartbeat=${EXPECT_HEARTBEAT_MS}ms' '${SERIAL_LOG}' && grep -q 'History KEEP_LAST enforcement PASSED' '${SERIAL_LOG}'"
check "Deadline behavior: missed deadline detected" "grep -q 'Deadline missed: YES' '${SERIAL_LOG}'"
check "Lifespan behavior: expired and fresh message checks passed" "grep -q 'Lifespan check PASSED: expired message correctly identified' '${SERIAL_LOG}' && grep -q 'Lifespan check PASSED: fresh message accepted' '${SERIAL_LOG}'"
check "Liveliness behavior: lease activity and finite lease checks passed" "grep -q 'Liveliness lease check PASSED' '${SERIAL_LOG}' && grep -q 'Liveliness finite lease behavior PASSED' '${SERIAL_LOG}'"
check "QoS 7 Resource Limits behavior: burst rejection visible" "grep -q 'Resources  : ${EXPECT_RESOURCE_MAX_SAMPLES} samples, ${EXPECT_RESOURCE_MAX_BYTES} bytes' '${SERIAL_LOG}' && grep -q 'Rejected during burst:' '${SERIAL_LOG}' && grep -q 'Resource stats:' '${SERIAL_LOG}'"

echo
echo "[verify] logs:"
echo "  serial: ${SERIAL_LOG}"
echo "  host:   ${HOST_LOG}"
echo "  topic:  ${TOPIC_LOG}"

if [ "${pass}" -eq 1 ]; then
  echo "[verify] RESULT: PASS"
else
  echo "[verify] RESULT: FAIL"
  exit 1
fi
