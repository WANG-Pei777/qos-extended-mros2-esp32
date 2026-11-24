# Repository Scope

## Public Source

The GitHub repository keeps material needed to understand, build, validate, or
audit the system:

- mROS2 and embeddedRTPS source code
- ESP32-S3 platform and validation firmware
- benchmark telemetry component
- experiment, audit, analysis, and figure-generation scripts
- frozen protocols, runbooks, status matrices, and reproducibility notes
- upstream and micro-ROS baseline setup instructions

## Local-Only Material

The following remain on the workstation and are intentionally excluded:

- Wi-Fi credentials and local network configuration
- raw results, PCAP captures, serial logs, and generated release bundles
- ESP-IDF, CMake, and colcon build trees
- vendored third-party clones and Agent toolchains
- Origin/Excel project files and inspection sidecars
- presentation files and posters

The local P4 workspace is retained for ongoing collection and audit work under
`mROS2-QoS-p4-run/`; its source is synchronized into the public source tree
only when it is part of the reproducible workflow.

## Evidence Boundary

Existing communication, QoS, reliability, timing, resource, and matched-system
results are documented with their sample sizes and audit status. Energy
measurement is deferred because the external calibrated monitor and GPIO timing
alignment are not yet available. No energy result is implied by the current
software or network traces.

## Reproduction Order

1. Read `README.md` and `docs/validation/QUICK_START.md`.
2. Configure local Wi-Fi and RTPS settings in ignored files.
3. Run static checks before flashing hardware.
4. Run the smoke gate and record firmware, host, and network versions.
5. Use the frozen protocol in `docs/benchmark/` for formal collection.
6. Keep raw captures and generated bundles outside the public Git history.
