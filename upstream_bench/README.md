# Upstream mROS2-ESP32 Baseline

This directory contains the runner notes for the upstream comparison arm.

## Source

The upstream implementation is maintained at:

```text
https://github.com/mROS-base/mros2-esp32
```

The local clone is intentionally ignored. Record its commit hash in every
formal run manifest instead of committing a second copy of the upstream tree.

## Comparison Boundary

The upstream arm is a direct ESP32-to-ROS 2 RTPS path. It is compared with the
same ESP32-S3 board, Wi-Fi access point, host, payload, publish rate, warm-up,
measurement window, and impairment schedule as the other systems.

The upstream repository provides communication examples and build instructions;
it does not provide the external power-monitor measurement needed for an energy
comparison. Energy measurement remains deferred in this project.

## Local Run

Keep the upstream clone under `upstream_bench/mros2-esp32/`, use the matching
ESP-IDF target, and run the common workload harness from
`scripts/experiment/`. Do not commit the clone, build output, credentials, or
raw captures.
