#!/usr/bin/env bash
#
# Run one formal QoS condition with controlled board-to-host UDP impairment.
# This uses an ingress tc filter with gact random drop, scoped to UDP packets
# from the board. It is intentionally separate from host-to-board netem.

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
    echo "Error: passwordless sudo for tc is required for automated ingress setup." >&2
    exit 2
fi

DATE="${RESULTS_DATE:-$(date +%Y%m%d)}"
STAMP=$(date +%Y%m%d_%H%M%S)
LOSS_LABEL="${LOSS_PERCENT//./p}pct"
CONDITION_OVERRIDE="${CONDITION_OVERRIDE:-}"
if [ -n "${CONDITION_OVERRIDE}" ] && ! [[ "${CONDITION_OVERRIDE}" =~ ^[A-Za-z0-9_.-]+$ ]]; then
    echo "Error: CONDITION_OVERRIDE contains unsupported characters" >&2
    exit 2
fi
CONDITION="${CONDITION_OVERRIDE:-round4_transport_${QOS_MODE}_${LOSS_LABEL}_board_to_host}"
PCAP_DIR="${PCAP_DIR_OVERRIDE:-${PROJECT_ROOT}/results/experiments/pcaps}"
PCAP_PATH="${PCAP_DIR}/${STAMP}_${CONDITION}.pcapng"
CAPTURE_LOG="${PCAP_PATH}.log"
TC_STATE_LOG="${PCAP_PATH}.tc.txt"
LEDGER="${PROJECT_ROOT}/results/experiments/${DATE}/TRANSPORT_INGRESS_GACT_LEDGER.md"
CAPTURE_PID=""
INGRESS_ACTIVE=0

mkdir -p "${PCAP_DIR}" "$(dirname "${LEDGER}")"

cleanup() {
    local status=$?
    if [ -n "${CAPTURE_PID}" ]; then
        kill "${CAPTURE_PID}" 2>/dev/null || true
        wait "${CAPTURE_PID}" 2>/dev/null || true
    fi
    if [ "${INGRESS_ACTIVE}" = "1" ]; then
        {
            printf '\nphase=final timestamp=%s\n' "$(date --iso-8601=seconds)"
            sudo -n tc qdisc show dev "${NETEM_INTERFACE}"
            sudo -n tc -s filter show dev "${NETEM_INTERFACE}" ingress
        } >> "${TC_STATE_LOG}" 2>&1 || true
        sudo tc qdisc del dev "${NETEM_INTERFACE}" ingress 2>/dev/null || true
    fi
    if [ -f "${PCAP_PATH}" ]; then
        printf '%s | qos=%s | firmware=%s | direction=board_to_host | target_loss=%s%% | denominator=%s | effective_loss=%s%% | pcap=%s | sha256=%s | tc_state=%s | tc_state_sha256=%s\n' \
            "${STAMP}" "${QOS_MODE}" "${FIRMWARE_MODE}" "${LOSS_PERCENT}" \
            "${DROP_DENOMINATOR:-n/a}" "${EFFECTIVE_DROP_PERCENT:-${LOSS_PERCENT}}" \
            "${PCAP_PATH}" "$(sha256sum "${PCAP_PATH}" | awk '{print $1}')" \
            "${TC_STATE_LOG}" "$([ -f "${TC_STATE_LOG}" ] && sha256sum "${TC_STATE_LOG}" | awk '{print $1}' || printf 'missing')" >> "${LEDGER}"
    fi
    exit "${status}"
}
trap cleanup EXIT INT TERM

echo "Capturing RTPS traffic on ${CAPTURE_INTERFACE}; applying ${LOSS_PERCENT}% ingress random drop from ${BOARD_IP} on ${NETEM_INTERFACE}."
echo "Scope: board-to-host only. Do not generalize this result to bidirectional loss."

{
    printf 'phase=baseline timestamp=%s\n' "$(date --iso-8601=seconds)"
    sudo -n tc qdisc show dev "${NETEM_INTERFACE}"
    sudo -n tc -s filter show dev "${NETEM_INTERFACE}" ingress
} > "${TC_STATE_LOG}" 2>&1

tshark -i "${CAPTURE_INTERFACE}" \
    -f "host ${BOARD_IP} and udp portrange 7400-7420" \
    -w "${PCAP_PATH}" > "${CAPTURE_LOG}" 2>&1 &
CAPTURE_PID=$!
sleep 2
if ! kill -0 "${CAPTURE_PID}" 2>/dev/null; then
    echo "Error: tshark capture failed to remain active; see ${CAPTURE_LOG}" >&2
    exit 2
fi

DROP_DENOMINATOR=""
EFFECTIVE_DROP_PERCENT="${LOSS_PERCENT}"
if awk -v loss="${LOSS_PERCENT}" 'BEGIN { exit !(loss > 0) }'; then
    sudo tc qdisc del dev "${NETEM_INTERFACE}" ingress 2>/dev/null || true
    sudo tc qdisc add dev "${NETEM_INTERFACE}" ingress
    INGRESS_ACTIVE=1
    if awk -v loss="${LOSS_PERCENT}" 'BEGIN { exit !(loss >= 100) }'; then
        sudo tc filter add dev "${NETEM_INTERFACE}" ingress protocol ip pref 10 flower \
            src_ip "${BOARD_IP}" ip_proto udp \
            action gact drop
    else
        # gact random uses an inverse-probability denominator: 10 ~= 10%.
        DROP_DENOMINATOR=$(awk -v loss="${LOSS_PERCENT}" 'BEGIN { printf "%d", (100.0 / loss) + 0.5 }')
        EFFECTIVE_DROP_PERCENT=$(awk -v denominator="${DROP_DENOMINATOR}" \
            'BEGIN { printf "%.6f", 100.0 / denominator }')
        sudo tc filter add dev "${NETEM_INTERFACE}" ingress protocol ip pref 10 flower \
            src_ip "${BOARD_IP}" ip_proto udp \
            action gact pass random netrand drop "${DROP_DENOMINATOR}"
    fi
    {
        printf 'phase=configured timestamp=%s\n' "$(date --iso-8601=seconds)"
        sudo -n tc qdisc show dev "${NETEM_INTERFACE}"
        sudo -n tc -s filter show dev "${NETEM_INTERFACE}" ingress
    } > "${TC_STATE_LOG}" 2>&1
fi

FORMAL_RUN=1 \
QOS_MODE="${QOS_MODE}" \
FIRMWARE_MODE="${FIRMWARE_MODE}" \
FIRMWARE_BINARY="${FIRMWARE_BINARY}" \
INJECTION_LAYER="transport_ingress_gact_board_to_host_target_${LOSS_PERCENT}pct_${DROP_DENOMINATOR:+1of${DROP_DENOMINATOR}_}effective_${EFFECTIVE_DROP_PERCENT}pct" \
HOST_MODE="cpp" \
BOARD_IP="${BOARD_IP}" \
RESULTS_DATE="${DATE}" \
    "${SCRIPT_DIR}/run_matrix.sh" "mros2qos" "${CONDITION}" "${REPETITIONS}"
