#!/bin/bash
# Network packet loss test for RELIABLE QoS verification
# Must run with sudo: sudo bash scripts/test_packet_loss.sh
#
# Tests: ESP32 RELIABLE path with 10% packet loss
# Expected: All messages delivered (retransmission compensates for loss)

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INTERFACE="eth1"
LOSS_RATE="${1:-10}"

echo "=== Packet Loss Test ==="
echo "Interface: $INTERFACE"
echo "Loss rate: ${LOSS_RATE}%"
echo ""

# Step 1: Enable packet loss
echo "[1/5] Enabling ${LOSS_RATE}% packet loss on $INTERFACE..."
tc qdisc add dev "$INTERFACE" root netem loss "${LOSS_RATE}%" 2>/dev/null || \
  tc qdisc change dev "$INTERFACE" root netem loss "${LOSS_RATE}%"
echo "  tc rule active"

# Step 2: Flash ESP32
echo "[2/5] Flashing ESP32..."
cd "$PROJECT_ROOT/workspace/qos_eval"
source ~/esp-idf/export.sh >/dev/null 2>&1
idf.py -p /dev/ttyUSB0 flash >/dev/null 2>&1
echo "  Flash complete"

# Step 3: Run validation
echo "[3/5] Running hardware validation with packet loss..."
cd "$PROJECT_ROOT"
RESULT_DIR=$(./scripts/validation/qos_ready.sh /dev/ttyUSB0 all 2>&1 | tee /dev/stderr | grep "serial:" | awk '{print $2}')

# Step 4: Check results
echo ""
echo "[4/5] Checking results..."
if [ -n "$RESULT_DIR" ] && [ -f "$RESULT_DIR/attempt_1_summary.log" ]; then
    if grep -q "RESULT: PASS" "$RESULT_DIR/attempt_1_summary.log"; then
        echo "  ✅ PASS: All QoS tests passed with ${LOSS_RATE}% packet loss"
    else
        echo "  ❌ FAIL: Some QoS tests failed with ${LOSS_RATE}% packet loss"
    fi

    # Check for packet drops
    DROPS=$(grep "Packets Dropped:" "$RESULT_DIR/attempt_1_serial.log" 2>/dev/null | tail -1)
    echo "  $DROPS"
else
    echo "  ⚠️ Could not find validation results"
fi

# Step 5: Remove packet loss
echo ""
echo "[5/5] Removing packet loss rule..."
tc qdisc del dev "$INTERFACE" root 2>/dev/null || true
echo "  Cleaned up"

echo ""
echo "=== Test Complete ==="
