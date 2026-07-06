# QoS Evidence Matrix

This document describes only facts that are currently supported by source code, real-hardware logs, or ROS2 discovery. It does not present the validation results as complete DDS product-grade capability.

## Validation Scope

```text
ESP32 -> ROS2 topic: /step7_full_qos
ESP32 role: publisher
Configured QoS: RELIABLE, VOLATILE, KEEP_LAST(5), resource limits

ROS2 -> ESP32 topic: /step7_full_qos_reply
ESP32 role: subscriber
ROS2 role: publisher
Configured QoS: RELIABLE, VOLATILE, finite deadline, finite lifespan, AUTOMATIC liveliness
```

## Maturity Levels

```text
L3: Implemented and verified by real-hardware behavior plus ROS2 discovery where applicable.
L2: Configured and verified by focused behavior/log evidence, but not complete DDS production behavior.
L1: Represented in the QoS profile or local configuration, with limited validation evidence.
L0: Not implemented or not covered by current validation.
```

## Evidence Matrix

| QoS policy | Current value in validation path | Maturity | Evidence | Accurate statement |
| --- | --- | --- | --- | --- |
| Reliability | ESP32 uplink `RELIABLE`; ROS2 reply `RELIABLE` | L3 for the current path | Bidirectional real-hardware TX/RX; `ros2 topic info --verbose`; strict preflight PASS; 3-run reset stress PASS. 2026-06-14: verified with concurrency fix (atomic bool), input validation, and graceful shutdown. | Both directions are configured as RELIABLE and exercised on real hardware. |
| Durability | `VOLATILE` on step7; `TRANSIENT_LOCAL` on step8 | L3 for current path | VOLATILE visible in ROS2 discovery. TRANSIENT_LOCAL late-joiner: ESP32 publishes 10 cached messages before subscriber joins; ROS2 subscriber receives `[CACHED]` messages via HEARTBEAT-triggered history delivery. Verified on real hardware 2026-06-12. | TRANSIENT_LOCAL late-joiner historical data delivery is implemented and verified. The StatefulWriter sends HEARTBEAT before cached DATA to announce available sequence numbers. |
| History | `KEEP_LAST(5)` | L2 | ROS2 CLI exposes the History field but reports depth as UNKNOWN; ESP32 startup log; QoS profile; `History cache: 5/5 samples`; `History KEEP_LAST enforcement PASSED`; SEDP emits PID_HISTORY | Writer-side depth enforcement is implemented and verified. ROS2 CLI visibility alone is not enough to prove KEEP_LAST(5). |
| Deadline | ESP32 app-level `100ms`; reply endpoint finite deadline | L2 | ESP32 `Deadline missed: YES`; ROS2 discovery on reply path; deadline counters advance by missed period | Deadline detection behavior is verified, but complete DDS deadline status/event interop is not product-grade yet. |
| Lifespan | `2000ms` | L2 | ESP32 expired/fresh checks; ROS2 discovery on reply path | Current evidence is focused behavior testing and endpoint discovery, not exhaustive RTPS cache expiry coverage. |
| Liveliness | `AUTOMATIC`, lease `3000ms` | L2+ | ESP32 writer activity/lease log; ROS2 discovery shows `AUTOMATIC`; liveliness lost/recovered state machine implemented with transition counters. | Automatic liveliness configuration, observed writer activity, and lost/recovered state transitions are implemented. Full manual liveliness semantics not yet complete. |
| Resource Limits | `30 samples`, `12288 bytes` | L2 | ESP32 burst test: rejected count and resource stats; SEDP emits standard sample-count resource limit | Local resource limiting behavior is verified. `maxBytes` is ESP32-local and not a standard ROS2-visible resource-limit field. |

## Security Hardening Evidence (2026-06-14)

```
Buffer overflow:     Fixed (strcpy → strncpy + null termination)
Memory leak:         Fixed (new → static allocation)
Integer overflow:    Fixed (duration overflow protection)
Error handling:      Fixed (infinite loops → handle_fatal_error with restart)
Input validation:    Fixed (RTPS packet size, nextPos overflow, submsg bounds)
Concurrency:         Fixed (volatile bool → std::atomic<bool>)
Graceful shutdown:   Implemented (mros2::shutdown() API)
Static analysis:     cppcheck clean, CI pipeline added
```

## Bidirectional Communication Evidence

Latest real-hardware evidence on 2026-06-10:

```text
Strict full-RELIABLE preflight PASS:
  /home/your-user/mROS2-QoS/results/qos_preflight_20260610_022457

Strict full-RELIABLE reset stress 3/3 PASS:
  /home/your-user/mROS2-QoS/results/qos_reset_stress_20260610_022750

ROS2 topic info evidence:
  Reliability: ESP32->ROS2 RELIABLE and ROS2->ESP32 RELIABLE visible
  Durability: VOLATILE visible
  History: History field visible; depth is UNKNOWN in current ROS2 Humble output
  Deadline: finite deadline visible
  Lifespan: finite lifespan visible
  Liveliness: AUTOMATIC visible

ESP32 behavior evidence:
  History: KEEP_LAST(5) configured and enforced
  Resource Limits: configured sample/byte limit plus burst rejection behavior
  Deadline/Lifespan/Liveliness: additional focused behavior checks
```

ESP32 serial monitor should show:

```text
publisher matched with remote subscriber
subscriber matched with remote publisher
Warm-up reply confirmed
[ROS2 -> ESP32] Echo reply received
TX: 40 msgs
RX: nonzero; latest preflight example was RX: 40 msgs
Packets Dropped:  0
All phases complete.
```

Interpretation:

```text
TX proves ESP32 -> ROS2.
RX proves ROS2 -> ESP32.
RX is not expected to equal TX in every combined run because KEEP_LAST and resource-limit phases intentionally drop or reject some samples.
Warm-up reply confirmed proves formal statistics start only after the real echo path is alive.
```

The final ESP32 report also prints reader-side receive diagnostics:

```text
Reader received count
Reader accepted-before-match count
Reader out-of-order drop count
Reader unmatched-writer drop count
Reader liveliness lost count
Reader liveliness recovered count
```

These counters are debugging evidence for discovery, ordering, reset behavior, and liveliness state transitions. They help explain failures, but they are not themselves QoS policy proof.

## Network Preconditions

Before interpreting any QoS result, confirm DDS/RTPS packets can enter WSL:

```bash
cd /home/your-user/mros2/mros2-esp32
./scripts/validation/qos_network_doctor.sh /dev/ttyUSB0
./scripts/validation/qos_network_doctor.sh /dev/ttyUSB0 20
```

If ESP32 logs show SPDP/SEDP sends but `tcpdump` in WSL sees no UDP traffic on `7400/7401/7410-7420`, the failure is a Windows/WSL network ingress problem, not evidence that a QoS policy failed.

## What Not To Claim

Do not claim:

```text
All DDS QoS policies are fully implemented.
All seven QoS categories are production-grade.
Every QoS field is completely visible through ros2 topic info.
History depth and Resource Limits are fully represented through stable SEDP interop.
Manual liveliness and liveliness-lost events are complete.
```

Accurate wording:

```text
This project extends mROS2-ESP32 beyond the old fixed-BEST_EFFORT-style behavior by adding a structured QoS profile, SEDP discovery for several endpoint QoS fields, and real-hardware tests for selected policies.
The current strict validation path gives strong evidence for bidirectional RELIABLE real-hardware communication and focused evidence for Deadline, Lifespan, Liveliness, History, and Resource Limits.
It is still an engineering prototype, not a complete DDS QoS product implementation.
```
