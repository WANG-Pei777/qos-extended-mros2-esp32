# Documentation

```text
DESIGN_MAP.md                       Where each QoS mechanism lives in the code
REPOSITORY_SCOPE.md                 What is and is not part of this repository

validation/QUICK_START.md           Shortest path from build to a hardware check
validation/QUICK_REFERENCE.md       Command reference
validation/RUNBOOK.md               Windows + WSL2 setup and the full validation flow

qos/QOS_IMPLEMENTATION_STATUS.md    Implementation snapshot (historical)
qos/QOS_EVIDENCE_MATRIX.md          Evidence per QoS category (historical)
transient_local/TEST_PLAN.md        Transient Local replay test plan

benchmark/                          Experiment protocols, amendments, and results
figures/                            Figures generated from the measurement data
```

Executable tooling for the experiments is under `scripts/experiment/`; the
upstream mros2-esp32 and micro-ROS baselines are under `upstream_bench/` and
`microros_bench/`.

Measured setup: ROS 2 Humble on WSL2 talking to an ESP32-S3 running the
firmware in `workspace/qos_eval`. This is a research prototype, not a complete
DDS QoS implementation.
