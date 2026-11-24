#!/usr/bin/env bash
#
# G6: Packet Loss Injection Verification
# Test if tc netem works on WSL mirrored networking for WiFi traffic
#
set -eo pipefail

echo "========================================="
echo "G6: Packet Loss Injection Verification"
echo "========================================="
echo ""

# Check if running on WSL
if ! grep -qi microsoft /proc/version; then
    echo "[WARN] Not running on WSL"
fi

# Find WiFi interface
WIFI_IF=$(ip -br link | grep -i wlan | awk '{print $1}' || echo "")
ETH_IF=$(ip route | grep default | awk '{print $5}' | head -1)

echo "[info] Network interfaces:"
ip -br addr
echo ""
echo "[info] Default route interface: ${ETH_IF}"
echo "[info] WiFi interface: ${WIFI_IF:-none}"
echo ""

# Test 1: Check if tc is available
if ! command -v tc &> /dev/null; then
    echo "[FAIL] tc (traffic control) not installed"
    echo "       Install: sudo apt install iproute2"
    exit 1
fi

echo "[OK] tc command available"
echo ""

# Test 2: Try to add a test qdisc
echo "[test] Attempting to add test qdisc with 1% loss on ${ETH_IF}..."

if sudo tc qdisc add dev ${ETH_IF} root netem loss 1% 2>&1 | tee /tmp/g6_tc_test.log; then
    echo "[OK] tc qdisc added successfully"

    # Verify it's active
    echo ""
    echo "[verify] Current qdisc on ${ETH_IF}:"
    sudo tc qdisc show dev ${ETH_IF}

    # Clean up
    echo ""
    echo "[cleanup] Removing test qdisc..."
    sudo tc qdisc del dev ${ETH_IF} root 2>/dev/null || true

    echo ""
    echo "========================================="
    echo "G6: PASS - tc netem works on this system"
    echo "========================================="
    echo ""
    echo "Packet loss injection method:"
    echo "  sudo tc qdisc add dev ${ETH_IF} root netem loss 5%"
    echo "  sudo tc qdisc del dev ${ETH_IF} root  # to remove"
    echo ""
    echo "Loss rates for experiments:"
    echo "  - E2: 0%, 1%, 5%, 10%, 20%"
    echo "  - E6: 0%, 5%, 10%"

else
    echo "[FAIL] tc qdisc failed on ${ETH_IF}"
    echo ""
    echo "Possible reasons:"
    echo "  1. WSL mirrored mode doesn't support tc for WiFi"
    echo "  2. Insufficient permissions (need sudo)"
    echo "  3. Interface doesn't support qdisc"
    echo ""
    echo "Fallback: Use application-layer packet drop in echo node"
    echo "  Modify echo_cpp to drop packets with probability"
    echo ""

    # Try iptables method as alternative
    echo "[test] Trying iptables statistic method..."

    if sudo iptables -A OUTPUT -p udp --dport 7400:7420 -m statistic --mode random --probability 0.01 -j DROP 2>&1; then
        echo "[OK] iptables method works"

        # Show rule
        sudo iptables -L OUTPUT -n --line-numbers | grep 7400

        # Clean up
        sudo iptables -D OUTPUT -p udp --dport 7400:7420 -m statistic --mode random --probability 0.01 -j DROP 2>/dev/null || true

        echo ""
        echo "========================================="
        echo "G6: PARTIAL - Use iptables method"
        echo "========================================="
        echo ""
        echo "Packet loss injection via iptables:"
        echo "  # 5% loss"
        echo "  sudo iptables -A OUTPUT -p udp --dport 7400:7420 -m statistic --mode random --probability 0.05 -j DROP"
        echo ""
        echo "  # Remove rule"
        echo "  sudo iptables -D OUTPUT -p udp --dport 7400:7420 -m statistic --mode random --probability 0.05 -j DROP"

    else
        echo "[FAIL] Both tc and iptables methods failed"
        echo ""
        echo "========================================="
        echo "G6: FAIL - Use application-layer fallback"
        echo "========================================="
        echo ""
        echo "Must implement packet drop in echo_cpp node"
    fi
fi
