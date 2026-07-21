# mROS2-ESP32 QoS Hardware Validation

This repository contains the mROS2-ESP32 QoS implementation, ESP32-S3 firmware,
controlled network experiments, and reproducible analysis tooling:

```text
WSL2 ROS2 Humble <-> ESP32-S3 mROS2
```

USB serial is used only for flashing and observing logs. The actual ROS2/mROS2
communication runs over WiFi using DDS/RTPS.

The public repository is intentionally source-first. Local captures, build
trees, generated bundles, credentials, and presentation files are excluded.
See [the repository scope](docs/REPOSITORY_SCOPE.md) for the boundary.

## Validation Entry Point

The primary hardware validation firmware is:

```text
workspace/qos_eval
```

Quick validation checklist:

```text
docs/validation/QUICK_START.md
```

Detailed validation procedures:

```text
docs/validation/RUNBOOK.md
docs/validation/QUICK_REFERENCE.md
```

QoS status and evidence:

```text
docs/qos/QOS_IMPLEMENTATION_STATUS.md
docs/qos/QOS_EVIDENCE_MATRIX.md
```

## Clone And Local Configuration

Clone this repository:

```bash
git clone https://github.com/hal-lab-u-tokyo/mROS2-QoS.git
cd mROS2-QoS
```

Create local WiFi credentials before building:

```bash
cp platform/wifi/wifi_secrets.example.h platform/wifi/wifi_secrets.h
```

Then edit `platform/wifi/wifi_secrets.h` for the local SSID and password. This file is ignored by git.

The validation scripts generate the local ROS2/WSL target IP in:

```text
platform/rtps/config_local.h
```

That file is also ignored by git. Run this whenever the WSL IP or network changes:

```bash
./scripts/validation/qos_set_remote_ip.sh
```

## One-Command Readiness Check

From WSL:

```bash
cd /home/your-user/mROS2-QoS
./scripts/validation/qos_ready.sh /dev/ttyUSB0 all
```

Only accept the hardware validation as ready when the output contains:

```text
[verify] RESULT: PASS
[ready] RESULT: ALL PASS
```

## Windows WSL2 Firewall Setup

When using WSL2 mirrored networking, run this once from an elevated Windows PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
& "\\wsl.localhost\Ubuntu-22.04\home\your-user\mROS2-QoS\scripts\validation\wsl_firewall_admin.ps1"
```

This allows DDS/RTPS UDP ports `7400-7420` into WSL.

## Validation Scope

The current real-hardware validation path verifies:

```text
ESP32 -> ROS2: /qos_eval, RELIABLE
ROS2 -> ESP32: /qos_eval_reply, RELIABLE
```

The seven QoS-related categories implemented or evaluated by the workflow are:

```text
Reliability
Durability
History
Deadline
Lifespan
Liveliness
Resource Limits
```

Important boundaries:

```text
This is a QoS extension prototype and real-hardware validation workflow, not a
complete product-grade DDS QoS implementation. The strict full-RELIABLE path
has passed the current real-hardware preflight and reset-stress checks.

Energy measurement is deferred. No energy result or per-message energy claim is
made until an external calibrated monitor and GPIO time alignment are available.
```

## Current Project Layout

```text
mros2/                    Core mROS2 and embeddedRTPS source
platform/                 ESP32 WiFi and RTPS platform configuration
workspace/qos_eval/       Real-hardware QoS validation firmware
components/               Reusable telemetry and benchmark components
microros_bench/           micro-ROS matched-workload baseline source
upstream_bench/           upstream baseline runner and configuration notes
scripts/validation/       Flashing, preflight, and WSL firewall helpers
scripts/experiment/       Formal collection, audit, and analysis tools
scripts/test/             Static QoS validation checks
docs/validation/          Hardware validation instructions
docs/qos/                 QoS implementation status and evidence matrix
docs/benchmark/           Frozen protocols and experiment runbooks
docs/figures/             Reproducible figure sources and previews
```
