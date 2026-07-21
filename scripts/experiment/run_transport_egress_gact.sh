#!/usr/bin/env bash
# Run one H2B condition with board-scoped egress gact impairment and one PCAP.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

QOS_MODE="${1:?Usage: $0 <reliable|best_effort> <target_loss_percent> [repetitions]}"
LOSS_PERCENT="${2:?Missing target loss percent}"
REPETITIONS="${3:-1}"
FIRMWARE_MODE="${FIRMWARE_MODE:?Set FIRMWARE_MODE to the exact flashed mode}"
FIRMWARE_BINARY="${FIRMWARE_BINARY:?Set FIRMWARE_BINARY to the exact flashed binary}"
NETEM_INTERFACE="${NETEM_INTERFACE:-eth1}"
CAPTURE_INTERFACE="${CAPTURE_INTERFACE:-${NETEM_INTERFACE}}"
BOARD_IP="${BOARD_IP:-192.0.2.1}"
NETWORK_CHANGE_ACK="${NETWORK_CHANGE_ACK:-0}"
FORMAL_RUN_OVERRIDE="${FORMAL_RUN_OVERRIDE:-1}"

case "${QOS_MODE}" in
    reliable|best_effort) ;;
    *) echo "Error: invalid QoS mode ${QOS_MODE}" >&2; exit 2 ;;
esac
if [ "${FIRMWARE_MODE}" != "${QOS_MODE}" ]; then
    echo "Error: firmware and host QoS modes differ" >&2
    exit 2
fi
if ! [[ "${LOSS_PERCENT}" =~ ^(0|1|5|10|15)$ ]]; then
    echo "Error: formal H2B target loss must be 0, 1, 5, 10, or 15" >&2
    exit 2
fi
if [ "${NETWORK_CHANGE_ACK}" != "1" ]; then
    echo "Error: refusing to change ${NETEM_INTERFACE} without acknowledgement" >&2
    exit 2
fi
if ! [[ "${REPETITIONS}" =~ ^[1-9][0-9]*$ ]]; then
    echo "Error: repetitions must be positive" >&2
    exit 2
fi
for command in tc tshark sha256sum; do
    command -v "${command}" >/dev/null || {
        echo "Error: missing command ${command}" >&2
        exit 2
    }
done
sudo -n tc qdisc show dev "${NETEM_INTERFACE}" >/dev/null || {
    echo "Error: passwordless sudo for tc is required" >&2
    exit 2
}

DATE="${RESULTS_DATE:-$(date +%Y%m%d)}"
STAMP="$(date +%Y%m%d_%H%M%S)"
CONDITION_OVERRIDE="${CONDITION_OVERRIDE:-}"
if [ -n "${CONDITION_OVERRIDE}" ] && ! [[ "${CONDITION_OVERRIDE}" =~ ^[A-Za-z0-9_.-]+$ ]]; then
    echo "Error: invalid CONDITION_OVERRIDE" >&2
    exit 2
fi
CONDITION="${CONDITION_OVERRIDE:-round4_transport_${QOS_MODE}_${LOSS_PERCENT}pct_host_to_board}"
PCAP_DIR="${PCAP_DIR_OVERRIDE:-${PROJECT_ROOT}/results/experiments/${DATE}/pcaps}"
PCAP_PATH="${PCAP_DIR}/${STAMP}_${CONDITION}.pcapng"
CAPTURE_LOG="${PCAP_PATH}.log"
TC_STATE_LOG="${PCAP_PATH}.tc.txt"
LEDGER="${PROJECT_ROOT}/results/experiments/${DATE}/TRANSPORT_EGRESS_GACT_LEDGER.md"
CAPTURE_PID=""
EGRESS_ACTIVE=0
DROP_DENOMINATOR=""
EFFECTIVE_DROP_PERCENT="${LOSS_PERCENT}"

mkdir -p "${PCAP_DIR}" "$(dirname "${LEDGER}")"

cleanup() {
    local status=$?
    if [ -n "${CAPTURE_PID}" ]; then
        kill "${CAPTURE_PID}" 2>/dev/null || true
        wait "${CAPTURE_PID}" 2>/dev/null || true
    fi
    {
        printf '\nphase=final_before_cleanup timestamp=%s\n' "$(date --iso-8601=seconds)"
        sudo -n tc qdisc show dev "${NETEM_INTERFACE}"
        sudo -n tc -s filter show dev "${NETEM_INTERFACE}" egress
    } >> "${TC_STATE_LOG}" 2>&1 || true
    if [ "${EGRESS_ACTIVE}" = "1" ]; then
        sudo -n tc qdisc del dev "${NETEM_INTERFACE}" clsact 2>/dev/null || true
    fi
    {
        printf '\nphase=post_cleanup timestamp=%s\n' "$(date --iso-8601=seconds)"
        sudo -n tc qdisc show dev "${NETEM_INTERFACE}"
        sudo -n tc -s filter show dev "${NETEM_INTERFACE}" egress
    } >> "${TC_STATE_LOG}" 2>&1 || true
    if [ -f "${PCAP_PATH}" ]; then
        printf '%s | qos=%s | firmware=%s | direction=host_to_board | target_loss=%s%% | denominator=%s | effective_loss=%s%% | pcap=%s | sha256=%s | tc_state=%s | tc_state_sha256=%s\n' \
            "${STAMP}" "${QOS_MODE}" "${FIRMWARE_MODE}" "${LOSS_PERCENT}" \
            "${DROP_DENOMINATOR:-n/a}" "${EFFECTIVE_DROP_PERCENT}" \
            "${PCAP_PATH}" "$(sha256sum "${PCAP_PATH}" | awk '{print $1}')" \
            "${TC_STATE_LOG}" "$(sha256sum "${TC_STATE_LOG}" | awk '{print $1}')" \
            >> "${LEDGER}"
    fi
    exit "${status}"
}
trap cleanup EXIT INT TERM

BASELINE_QDISC="$(sudo -n tc qdisc show dev "${NETEM_INTERFACE}")"
if grep -Eq '(^| )netem |(^| )ingress |(^| )clsact ' <<< "${BASELINE_QDISC}"; then
    echo "Error: stale impairment qdisc on ${NETEM_INTERFACE}" >&2
    exit 2
fi
{
    printf 'phase=baseline timestamp=%s\n' "$(date --iso-8601=seconds)"
    printf '%s\n' "${BASELINE_QDISC}"
    sudo -n tc -s filter show dev "${NETEM_INTERFACE}" egress
} > "${TC_STATE_LOG}" 2>&1

tshark -i "${CAPTURE_INTERFACE}" \
    -f "host ${BOARD_IP} and udp portrange 7400-7420" \
    -w "${PCAP_PATH}" > "${CAPTURE_LOG}" 2>&1 &
CAPTURE_PID=$!
sleep 2
if ! kill -0 "${CAPTURE_PID}" 2>/dev/null; then
    echo "Error: tshark capture failed; see ${CAPTURE_LOG}" >&2
    exit 2
fi

if [ "${LOSS_PERCENT}" != "0" ]; then
    DROP_DENOMINATOR=$(awk -v loss="${LOSS_PERCENT}" \
        'BEGIN { printf "%d", (100.0 / loss) + 0.5 }')
    EFFECTIVE_DROP_PERCENT=$(awk -v denominator="${DROP_DENOMINATOR}" \
        'BEGIN { printf "%.6f", 100.0 / denominator }')
    sudo -n tc qdisc add dev "${NETEM_INTERFACE}" clsact
    EGRESS_ACTIVE=1
    sudo -n tc filter add dev "${NETEM_INTERFACE}" egress protocol ip pref 10 flower \
        dst_ip "${BOARD_IP}" ip_proto udp \
        action gact pass random netrand drop "${DROP_DENOMINATOR}"
fi
{
    printf '\nphase=configured timestamp=%s target_loss=%s effective_loss=%s denominator=%s\n' \
        "$(date --iso-8601=seconds)" "${LOSS_PERCENT}" \
        "${EFFECTIVE_DROP_PERCENT}" "${DROP_DENOMINATOR:-n/a}"
    sudo -n tc qdisc show dev "${NETEM_INTERFACE}"
    sudo -n tc -s filter show dev "${NETEM_INTERFACE}" egress
} >> "${TC_STATE_LOG}" 2>&1

if [ "${LOSS_PERCENT}" = "0" ]; then
    INJECTION_LAYER="transport_egress_gact_host_to_board_target_0pct_effective_0pct"
else
    INJECTION_LAYER="transport_egress_gact_host_to_board_target_${LOSS_PERCENT}pct_1of${DROP_DENOMINATOR}_effective_${EFFECTIVE_DROP_PERCENT}pct"
fi

FORMAL_RUN="${FORMAL_RUN_OVERRIDE}" \
QOS_MODE="${QOS_MODE}" \
FIRMWARE_MODE="${FIRMWARE_MODE}" \
FIRMWARE_BINARY="${FIRMWARE_BINARY}" \
INJECTION_LAYER="${INJECTION_LAYER}" \
HOST_MODE="cpp" \
BOARD_IP="${BOARD_IP}" \
RESULTS_DATE="${DATE}" \
    "${SCRIPT_DIR}/run_matrix.sh" "mros2qos" "${CONDITION}" "${REPETITIONS}"
