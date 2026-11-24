# mros2-ESP32 QoS Documentation

This directory contains reproducibility notes, hardware validation procedures, and QoS evidence documents.

## Start Here

```text
docs/REPOSITORY_SCOPE.md              Public/private file boundary
docs/validation/QUICK_START.md        Shortest hardware validation path
docs/benchmark/README_EXPERIMENTS.md  Experiment entry point
docs/qos/QOS_IMPLEMENTATION_STATUS.md Historical implementation snapshot
docs/qos/QOS_EVIDENCE_MATRIX.md       Historical campaign evidence snapshot
docs/qos/QOS_SEMANTIC_SPECIFICATION_DRAFT.md
                                      Draft semantic contract and design gaps
docs/qos/RELIABILITY_HISTORY_HEARTBEAT_DESIGN.md
                                      Reliability repair and History behavior contract
docs/qos/RELIABILITY_DURABILITY_HISTORY_SUPPORT_MATRIX.md
                                      Current three-policy support and evidence matrix
docs/qos/RTPS_GAP_SMALL_SMOKE_RUNBOOK.md
                                      Packet-level GAP hardware gate
```

## Hardware Validation

```text
docs/validation/QUICK_START.md      Shortest validation path
docs/validation/QUICK_REFERENCE.md  Command reference
docs/validation/RUNBOOK.md          Windows + WSL2 hardware setup and validation flow
```

## QoS Status

```text
docs/qos/QOS_IMPLEMENTATION_STATUS.md  Historical implementation snapshot and product-grade gaps
docs/qos/QOS_EVIDENCE_MATRIX.md        Historical seven-category campaign evidence
docs/qos/QOS_SEMANTIC_SPECIFICATION_DRAFT.md
                                       Intended semantics, current mappings, and open decisions
docs/qos/RELIABILITY_HISTORY_HEARTBEAT_DESIGN.md
                                       Reliability repair and History behavior contract
docs/qos/RELIABILITY_DURABILITY_HISTORY_SUPPORT_MATRIX.md
                                       Current Reliability/Durability/History closure record
docs/qos/RTPS_GAP_SMALL_SMOKE_RUNBOOK.md
                                       Directed ACKNACK and GAP evidence contract
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
WSL2 ROS 2 Humble <-> ESP32-S3 mros2
workspace/qos_eval
```

This project is a QoS extension prototype and hardware validation workflow, not a complete product-grade DDS QoS implementation.
