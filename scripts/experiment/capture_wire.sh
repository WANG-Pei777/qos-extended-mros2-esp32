#!/usr/bin/env bash
#
# capture_wire.sh - Capture packets with dumpcap for manual Wireshark analysis
# Usage: capture_wire.sh <label> <seconds>
#
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

LABEL="${1:?Usage: $0 <label> <seconds>}"
SECONDS="${2:-120}"

DATE=$(date +%Y%m%d_%H%M%S)
RESULTS_DIR="${PROJECT_ROOT}/results/experiments/pcaps"
OUTPUT_PCAP="${RESULTS_DIR}/${DATE}_${LABEL}.pcapng"

mkdir -p "${RESULTS_DIR}"

echo "========================================="
echo "capture_wire.sh"
echo "========================================="
echo "Label: ${LABEL}"
echo "Duration: ${SECONDS}s"
echo "Output: ${OUTPUT_PCAP}"
echo ""

# Check for dumpcap/tshark
if ! command -v tshark &> /dev/null; then
    echo "[ERROR] tshark not found, install with: sudo apt install tshark"
    exit 1
fi

echo "[capture] Starting packet capture..."
echo "[capture] Filter: udp portrange 7400-7420"
echo "[capture] Press Ctrl+C to stop early"
echo ""

# Capture with tshark (dumpcap wrapper)
tshark -i any -f "udp portrange 7400-7420" -w "${OUTPUT_PCAP}" -a duration:${SECONDS}

echo ""
echo "========================================="
echo "Capture complete"
echo "========================================="
echo "PCAP file: ${OUTPUT_PCAP}"
echo ""
echo "Manual Wireshark analysis steps:"
echo "  1. Open: wireshark ${OUTPUT_PCAP}"
echo "  2. Display filters:"
echo "     - HEARTBEAT: rtps.sm.id == 0x07"
echo "     - ACKNACK: rtps.sm.id == 0x06"
echo "     - DATA: rtps.sm.id == 0x15"
echo "  3. Statistics → Flow Graph (select 'All Flows')"
echo "  4. Statistics → I/O Graph"
echo ""
echo "For paper evidence figures (manual screenshots):"
echo "  - Flow Graph: protocol sequence diagram"
echo "  - I/O Graph: packet rate over time"
echo "  - Filter + packet list: HEARTBEAT/ACKNACK evidence"
