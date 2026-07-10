#!/usr/bin/env bash
#
# Run one formal QoS condition with controlled host-to-board UDP impairment.
# This is intentionally separate from echo_node_lossy application reply drops.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

QOS_MODE="${1:?Usage: $0 <reliable|best_effort> <loss_percent> [repetitions]}"
LOSS_PERCENT="${2:?Missing loss percent}"
REPETITIONS="${3:-30}"
FIRMWARE_MODE="${FIRMWARE_MODE:?Set FIRMWARE_MODE after confirming the flashed board mode}"
FIRMWARE_BINARY="${FIRMWARE_BINARY:?Set FIRMWARE_BINARY to the exact flashed build/qos_eval.bin}"
NETEM_INTERFACE="${NETEM_INTERFACE:-eth1}"
CAPTURE_INTERFACE="${CAPTURE_INTERFACE:-${NETEM_INTERFACE}}"
BOARD_IP="${BOARD_IP:-10.84.233.107}"
NETWORK_CHANGE_ACK="${NETWORK_CHANGE_ACK:-0}"

case "${QOS_MODE}" in
    reliable|best_effort)
        ;;
    *)
        echo "Error: QoS mode must be reliable or best_effort" >&2
        exit 2
        ;;
esac

if [ "${FIRMWARE_MODE}" != "${QOS_MODE}" ]; then
    echo "Error: FIRMWARE_MODE must match the requested QoS mode" >&2
    exit 2
fi

if ! [[ "${LOSS_PERCENT}" =~ ^([0-9]+([.][0-9]*)?|[.][0-9]+)$ ]] || \
   ! awk -v loss="${LOSS_PERCENT}" 'BEGIN { exit !(loss >= 0 && loss <= 100) }'; then
    echo "Error: loss_percent must be in [0, 100]" >&2
    exit 2
fi

if [ "${NETWORK_CHANGE_ACK}" != "1" ]; then
    echo "Refusing to change ${NETEM_INTERFACE}. Re-run with NETWORK_CHANGE_ACK=1 after confirming this is the dedicated test link." >&2
    exit 2
fi

for command in tc tshark sha256sum; do
    command -v "${command}" >/dev/null || {
        echo "Error: required command not found: ${command}" >&2
        exit 2
    }
done

if ! sudo -n tc qdisc show dev "${NETEM_INTERFACE}" >/dev/null; then
    echo "Error: passwordless sudo for tc is required for automated netem setup." >&2
    echo "Run this script from an authorized lab shell, or configure a dedicated test interface." >&2
    exit 2
fi

DATE=$(date +%Y%m%d)
STAMP=$(date +%Y%m%d_%H%M%S)
LOSS_LABEL="${LOSS_PERCENT//./p}pct"
CONDITION="round4_transport_${QOS_MODE}_${LOSS_LABEL}"
PCAP_DIR="${PROJECT_ROOT}/results/experiments/pcaps"
PCAP_PATH="${PCAP_DIR}/${STAMP}_${CONDITION}_host_to_board.pcapng"
CAPTURE_LOG="${PCAP_PATH}.log"
LEDGER="${PROJECT_ROOT}/results/experiments/${DATE}/TRANSPORT_NETEM_LEDGER.md"
CAPTURE_PID=""
NETEM_ACTIVE=0

mkdir -p "${PCAP_DIR}" "$(dirname "${LEDGER}")"

cleanup() {
    local status=$?
    if [ -n "${CAPTURE_PID}" ]; then
        kill "${CAPTURE_PID}" 2>/dev/null || true
        wait "${CAPTURE_PID}" 2>/dev/null || true
    fi
    if [ "${NETEM_ACTIVE}" = "1" ]; then
        sudo tc qdisc del dev "${NETEM_INTERFACE}" root 2>/dev/null || true
    fi
    if [ -f "${PCAP_PATH}" ]; then
        printf '%s | qos=%s | firmware=%s | direction=host_to_board | loss=%s%% | pcap=%s | sha256=%s\n' \
            "${STAMP}" "${QOS_MODE}" "${FIRMWARE_MODE}" "${LOSS_PERCENT}" \
            "${PCAP_PATH}" "$(sha256sum "${PCAP_PATH}" | awk '{print $1}')" >> "${LEDGER}"
    fi
    exit "${status}"
}
trap cleanup EXIT INT TERM

echo "Capturing RTPS traffic on ${CAPTURE_INTERFACE}; applying ${LOSS_PERCENT}% egress loss on ${NETEM_INTERFACE}."
echo "Scope: host-to-board only. Do not generalize this result to bidirectional loss."

tshark -i "${CAPTURE_INTERFACE}" \
    -f "host ${BOARD_IP} and udp portrange 7400-7420" \
    -w "${PCAP_PATH}" > "${CAPTURE_LOG}" 2>&1 &
CAPTURE_PID=$!
sleep 2

# This replaces the root qdisc only after explicit acknowledgement. Cleanup
# removes this script's qdisc so the interface returns to its kernel default.
sudo tc qdisc replace dev "${NETEM_INTERFACE}" root netem loss "${LOSS_PERCENT}%"
NETEM_ACTIVE=1

FORMAL_RUN=1 \
QOS_MODE="${QOS_MODE}" \
FIRMWARE_MODE="${FIRMWARE_MODE}" \
FIRMWARE_BINARY="${FIRMWARE_BINARY}" \
INJECTION_LAYER="transport_egress_netem_host_to_board_${LOSS_PERCENT}pct" \
HOST_MODE="cpp" \
    "${SCRIPT_DIR}/run_matrix.sh" "mros2qos" "${CONDITION}" "${REPETITIONS}"
