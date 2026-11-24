# Where things are

Which source file implements which mechanism, and which script produced which
measurement. The measured source revision is tagged `v1.0.0`.

## Design

| Mechanism | Source |
| --- | --- |
| `QoSProfile`, creation-time validation, error on rejection | `mros2/include/mros2/qos.h` (`QoSPolicy::validate`, `validation_error`), `mros2/src/mros2.cpp` (`create_publisher`, `create_subscription`) |
| offered/requested matching (Reliability, Durability, Deadline, Liveliness lease) | `mros2/embeddedRTPS/include/rtps/discovery/QoSCompatibility.h`, called from `src/discovery/SEDPAgent.cpp` |
| SEDP parameters | `mros2/embeddedRTPS/src/discovery/TopicData.cpp` (`serializeIntoUcdrBuffer`) |
| effective cache capacity, Keep Last / Keep All admission, Lifespan purge | `mros2/embeddedRTPS/include/rtps/entities/ResourceLimits.h`, `storages/SimpleHistoryCache.h`, `entities/StatefulWriter.tpp` |
| Transient Local replay, relevance, Volatile first-relevant sequence | `mros2/embeddedRTPS/include/rtps/entities/DurabilityState.h`, `StatefulWriter.tpp` (`addNewMatchedReader`) |
| Algorithm 1, budget `B`, Classify, hold state | `mros2/embeddedRTPS/include/rtps/entities/ReliabilityState.h` (`ACKNACK_SEQUENCE_RESPONSE_BUDGET`, `classifyRequestedSequence*`), `StatefulWriter.tpp` (`onNewAckNack`) |
| reader side: in-order admission, repair request on AHEAD, skip to HEARTBEAT first-available | `mros2/embeddedRTPS/include/rtps/entities/ReaderSequence.h`, `StatefulReader.tpp` (`newChange`, `onNewHeartbeat`), `WriterProxy.h` (`getMissing`) |
| operating values (HEARTBEAT 100 ms, B = 4, cache 40) | `workspace/seven_qos_performance_pilot/CMakeLists.txt`; defaults in `platform/rtps/config.h` and `ReliabilityState.h` |
| diagnostics counters | `StatefulWriter.h`, `StatefulReader.h`, exposed through `mros2/include/mros2.h` |

## Measurement setup

| Element | Source |
| --- | --- |
| Board workload (200 requests at 10 Hz, 64 B payload, 5 s window) | `workspace/seven_qos_performance_pilot/main/app.cpp` |
| Host echo node (Reliable/Best Effort, Volatile, Keep Last 10) | `tools/echo_cpp/src/echo_node.cpp` |
| micro-ROS baseline with the same telemetry | `microros_bench/telemetry_compare/` |
| Unmodified mros2-esp32 baseline | `upstream_bench/` |
| netem loss injection (egress / ifb ingress), qdisc snapshots, captures | `scripts/experiment/run_*impairment*.py`, `scripts/experiment/capture_wire.sh` |
| Telemetry: idle-task run-time counters, min free heap, stack high-water marks | `components/benchmark_telemetry/benchmark_telemetry.cpp` |
| Run validation, schedule hashes, audits | `scripts/experiment/audit_*.py`, `scripts/experiment/seal_result_tree.py`, `docs/benchmark/SEVEN_QOS_PERFORMANCE_PROTOCOL_AMENDMENT_*.md` |

## Measurements

| Result | Source / evidence |
| --- | --- |
| validator unit checks (102 + 22) | `tests/test_qos.cpp`, `tests/test_qos_compatibility.cpp` (`./scripts/test/run_host_tests.sh`) |
| 48-case compatibility campaign against ROS 2 Humble / Fast DDS | `tools/echo_cpp/src/qos_compatibility_probe.cpp`, `workspace/seven_qos_compatibility/`, `docs/benchmark/CODELINE_PROVENANCE_20260722.md` |
| loss sweep, ablation, baseline; lossy-run analysis | campaign `sqp-rerun-v2-loss` (local results tree, not in git); analysis scripts in `scripts/experiment/analyze_*.py` |
| resource table | telemetry records in each run's `serial.raw`; pooled by `scripts/experiment/analyze_three_system_formal.py` |
| late-join replay | campaign `sqp-rerun-v2-latejoin`; validator in `scripts/experiment/` |

## Later work

Branches other than the tagged revision carry later experiments (event-driven
HEARTBEAT timing, a host simulation of the writer under `sim/`). They are not
needed to build or reproduce what is described here.
