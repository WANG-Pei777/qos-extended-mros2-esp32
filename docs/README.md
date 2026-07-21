# mROS2-ESP32 QoS Documentation

This directory contains reproducibility notes, hardware validation procedures, and QoS evidence documents.

## Start Here

```text
docs/REPOSITORY_SCOPE.md              Public/private file boundary
docs/validation/QUICK_START.md        Shortest hardware validation path
docs/benchmark/README_EXPERIMENTS.md  Experiment entry point
docs/qos/QOS_IMPLEMENTATION_STATUS.md Implementation status
docs/qos/QOS_EVIDENCE_MATRIX.md       Evidence matrix and limitations
```

## Hardware Validation

```text
docs/validation/QUICK_START.md      Shortest validation path
docs/validation/QUICK_REFERENCE.md  Command reference
docs/validation/RUNBOOK.md          Windows + WSL2 hardware setup and validation flow
```

## QoS Status

```text
docs/qos/QOS_IMPLEMENTATION_STATUS.md  Current QoS implementation status and product-grade gaps
docs/qos/QOS_EVIDENCE_MATRIX.md        Evidence matrix for the validated QoS categories
```

## Experiment and Baseline Material

```text
docs/benchmark/                   Frozen protocols, collection, audit, and analysis
scripts/experiment/               Executable experiment tooling
upstream_bench/                   Upstream mros2-esp32 baseline instructions
microros_bench/                   micro-ROS matched-workload baseline instructions
docs/figures/                     Reproducible figures from local evidence
```

## Scope

```text
WSL2 ROS2 Humble <-> ESP32-S3 mROS2
workspace/qos_eval
```

This project is a QoS extension prototype and hardware validation workflow, not a complete product-grade DDS QoS implementation.
