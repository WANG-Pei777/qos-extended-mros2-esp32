#!/usr/bin/env bash
set -euo pipefail

PORT="${1:-/dev/ttyUSB0}"
CAPTURE_SECONDS="${2:-0}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
IFACE="$(ip route show default | awk '{print $5; exit}')"
WSL_IPV4="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for (i=1; i<=NF; i++) if ($i=="src") {print $(i+1); exit}}')"

echo "[doctor] mROS2/ROS2 network doctor"
echo "[doctor] port=${PORT}"
echo

echo "== WSL network =="
hostname -I || true
ip -4 route || true
if [ -n "${IFACE}" ]; then
  ip -4 addr show "${IFACE}" || true
fi
CONFIG_SOURCE="${PROJECT_ROOT}/platform/rtps/config.h"
if [ -f "${PROJECT_ROOT}/platform/rtps/config_local.h" ]; then
  CONFIG_SOURCE="${PROJECT_ROOT}/platform/rtps/config_local.h"
fi
CONFIG_IP="$(grep -Eo 'REMOTE_PARTICIPANT_IP\{[0-9, ]+\}' "${CONFIG_SOURCE}" | head -1 | sed -E 's/.*\{([0-9]+),[ ]*([0-9]+),[ ]*([0-9]+),[ ]*([0-9]+)\}/\1.\2.\3.\4/' || true)"
echo "WSL IPv4 for ROS2: ${WSL_IPV4:-unknown}"
echo "Firmware REMOTE_PARTICIPANT_IP: ${CONFIG_IP:-unknown}"
if [ -n "${WSL_IPV4}" ] && [ -n "${CONFIG_IP}" ] && [ "${WSL_IPV4}" != "${CONFIG_IP}" ]; then
  echo "[WARN] firmware target IP does not match WSL IPv4. Run:"
  echo "       ./scripts/validation/qos_set_remote_ip.sh"
fi
echo

echo "== Serial =="
if [ -e "${PORT}" ]; then
  ls -l "${PORT}"
else
  echo "[WARN] ${PORT} not found. Attach USB from Windows PowerShell with usbipd."
fi
echo

echo "== ROS2 environment =="
if [ -f /opt/ros/humble/setup.bash ]; then
  set +u
  # shellcheck disable=SC1091
  source /opt/ros/humble/setup.bash
  set -u
  echo "ROS2 Humble: OK"
  echo "ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-0}"
  echo "ROS_LOCALHOST_ONLY=${ROS_LOCALHOST_ONLY:-0}"
  env | grep -E '^(RMW|FAST|CYCLONE|ROS_)' | sort || true
else
  echo "[WARN] /opt/ros/humble/setup.bash not found"
fi
echo

echo "== Windows WSL networking/firewall =="
if command -v powershell.exe >/dev/null 2>&1 &&
   powershell.exe -NoProfile -Command '$PSVersionTable.PSVersion' >/dev/null 2>&1; then
  powershell.exe -NoProfile -Command 'Get-Content $env:USERPROFILE\.wslconfig -ErrorAction SilentlyContinue; Get-NetFirewallHyperVVMSetting -ErrorAction SilentlyContinue | Format-List VMCreatorId,Enabled,DefaultInboundAction,AllowHostPolicyMerge; Get-NetFirewallHyperVRule -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -like "*mROS2*" -or $_.DisplayName -like "*DDS*" -or $_.DisplayName -like "*RTPS*" } | Format-Table -AutoSize DisplayName,Direction,Protocol,LocalPorts,Action,Enabled' || true
else
  echo "[INFO] powershell.exe not available from this WSL shell; run the PowerShell command below from Windows."
fi
echo

cat <<'EOF'
== Required administrator PowerShell rule when WSL mirrored mode blocks LAN inbound ==
$id = '{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}'
New-NetFirewallHyperVRule `
  -Name 'mros2-dds-rtps-wsl-udp-7400-7420' `
  -DisplayName 'mROS2 DDS RTPS WSL UDP 7400-7420' `
  -Direction Inbound `
  -VMCreatorId $id `
  -Protocol UDP `
  -LocalPorts 7400-7420 `
  -Action Allow `
  -Enabled True
EOF
echo

if [ "${CAPTURE_SECONDS}" != "0" ]; then
  if [ -z "${IFACE}" ]; then
    echo "[WARN] no default interface found; cannot capture."
    exit 0
  fi
  echo "== DDS/RTPS UDP capture (${CAPTURE_SECONDS}s on ${IFACE}) =="
  echo "[doctor] Reset ESP32 now if you want to see discovery packets."
  sudo timeout "${CAPTURE_SECONDS}" tcpdump -ni "${IFACE}" \
    'udp and (port 7400 or port 7401 or port 7410 or port 7411 or portrange 7412-7420)' \
    -vv || true
fi
