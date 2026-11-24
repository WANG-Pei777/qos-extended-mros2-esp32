# TRANSIENT_LOCAL Durability Test Plan

## Goal

Verify that ESP32 mROS2 correctly implements TRANSIENT_LOCAL durability:
a late-joining ROS2 subscriber receives messages that were published before it joined.

## Prerequisites

- ESP32-S3 flashed with `step8_transient_local` firmware
- ROS2 Humble subscriber running on the host (WSL2)
- ESP32 and ROS2 host on the same WiFi network

## Test Procedure

### Step 1: Build and flash

```bash
cd workspace/step8_transient_local
source ~/esp-idf/export.sh
idf.py build
idf.py -p /dev/ttyUSB0 flash monitor
```

### Step 2: Wait for cached messages

ESP32 will publish 10 messages with `TRANSIENT_LOCAL` durability before any subscriber exists. Wait for the log line:

```
All cached messages published.
```

### Step 3: Start ROS2 subscriber

Before the 60-second timeout, run on the ROS2 host:

```bash
source /opt/ros/humble/setup.bash
ros2 topic echo /step8_transient_local --qos-reliability RELIABLE \
  --qos-durability TRANSIENT_LOCAL
```

### Step 4: Observe results

**PASS criteria:**
- ROS2 subscriber receives the 10 `[CACHED]` messages that were published before it joined
- ESP32 log shows `Subscriber matched after Xms!`

**FAIL criteria:**
- ROS2 subscriber receives only `[POST_MATCH]` messages, not `[CACHED]` ones
- No subscriber matched within 60 seconds

### Step 5: Verify via ROS2 discovery

```bash
ros2 topic info /step8_transient_local --verbose
```

Expected output should show:
```
Durability: TRANSIENT_LOCAL
Reliability: RELIABLE
```

## Expected Evidence

```
ESP32 serial:
  [CACHED] #0 T:...
  [CACHED] #1 T:...
  ...
  [CACHED] #9 T:...
  All cached messages published.
  Subscriber matched after Xms!
  [POST_MATCH] #0 T:...
  ...

ROS2 terminal:
  data: '[CACHED] #0 T:...'
  data: '[CACHED] #1 T:...'
  ...
  data: '[CACHED] #9 T:...'
  data: '[POST_MATCH] #0 T:...'
  ...
```

## Known Limitations

- This is a manual verification test. Automated late-joiner detection would require
  a Python script that starts the ROS2 subscriber after a delay.
- The number of cached messages retained depends on `KEEP_LAST(depth=10)`.
  If more than 10 messages are published before the subscriber joins, only the
  last 10 will be retained.
- This test does not verify that TRANSIENT_LOCAL works across ESP32 reset/reboot
  (that would require persistent storage, which is outside current scope).

## Maturity Target

After successful hardware verification, this test elevates Durability from L2 to L3
in the QoS Evidence Matrix (configured + focused behavior tests + real-hardware
TRANSIENT_LOCAL late-joiner evidence).
