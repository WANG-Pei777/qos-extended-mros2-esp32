#!/usr/bin/env bash
# Auto-reconnecting ROS2 subscriber for TRANSIENT_LOCAL testing.
# Re-subscribes whenever the publisher disappears (e.g. after ESP32 reset).
set -o pipefail

TOPIC="/step8_transient_local"
RELIABILITY="reliable"
DURABILITY="transient_local"

source /opt/ros/humble/setup.bash

echo "=== Auto-reconnect subscriber for $TOPIC ==="
echo "Waiting for publisher... (Ctrl+C to stop)"

while true; do
  echo "[subscriber] Starting ros2 topic echo..."
  ros2 topic echo "${TOPIC}" \
    --qos-reliability "${RELIABILITY}" \
    --qos-durability "${DURABILITY}" 2>&1 || true

  echo "[subscriber] Subscriber exited. Waiting 3s before restart..."
  sleep 3
  echo "[subscriber] Reconnecting..."
done
