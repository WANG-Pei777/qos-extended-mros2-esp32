# micro-ROS Matched-Workload Baseline

This directory contains the source for the micro-ROS comparison workload.

## Source

The ESP-IDF component is obtained from:

```text
https://github.com/micro-ROS/micro_ros_espidf_component
```

The local component checkout and generated Agent toolchain are ignored. Keep
their repository revisions in the run manifest.

## Workload

`telemetry_compare/main/main.c` uses the common workload contract:

- 32 to 2048 byte payload envelope
- fixed publish-rate and 20 second measurement window
- explicit run token and record sequence
- board timestamped RTT records
- delivery, duplicate, malformed, and reordering counters
- optional CPU, heap, stack, and telemetry records

The same workload settings must be used for mROS2-QoS, upstream mROS2-ESP32,
and micro-ROS. The Agent-side resource cost is reported separately from the
ESP32-side resource values.

## Local Build

Place the micro-ROS ESP-IDF component at
`microros_bench/micro_ros_espidf_component/`, then build
`microros_bench/telemetry_compare/` with ESP-IDF for `esp32s3`. Generated build
trees, binaries, and serial captures are local-only.
