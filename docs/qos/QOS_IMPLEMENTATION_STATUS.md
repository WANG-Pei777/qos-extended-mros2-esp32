# QoS Implementation Status

> **Historical snapshot (2026-06).** Reliability, Durability, and History
> changed materially on 2026-07-26. For current behavior, limitations, naming,
> and reproducible evidence, use
> `RELIABILITY_DURABILITY_HISTORY_SUPPORT_MATRIX.md`. If this historical text
> conflicts with that matrix or `QOS_SEMANTIC_SPECIFICATION_DRAFT.md`, the
> newer documents control. Current naming is **mros2** and **ROS 2**.

This document separates three questions:

1. What the current hardware validation has proven.
2. What the current source code implements.
3. What remains before the project can be described as a complete product-grade DDS/ROS 2 QoS implementation.

## Current Position

The project extends the original fixed QoS behavior in mros2 on ESP32 with a
structured QoS profile, selected SEDP QoS fields, and real-hardware validation
on ESP32-S3.

```text
QoSProfile API: present
QoSProfile validation: present for invalid depth/duration and unsupported manual liveliness modes
QoS SEDP serialization: partial support for Reliability, Durability, Deadline, Lifespan, Liveliness, History, and Resource Limits PIDs
Strict bidirectional RELIABLE path: ESP32 -> ROS 2 RELIABLE and ROS 2 -> ESP32 RELIABLE verified on real hardware
Full RELIABLE reply path: 2026-06-10 preflight and 3-run reset stress validation passed
Deadline/Lifespan/Liveliness/Resource Limits behavior checks: present
Deadline missed count: advanced by missed period instead of repeated poll/heartbeat loops
History KEEP_LAST(depth): writer cache enforces depth, verified by hardware log evidence showing 5/5 samples
Reader receive observability: received, accepted-before-match, out-of-order-drop, and unmatched-writer-drop counters are present
WSL2 mirrored networking: validated on the current machine, but should be rechecked after changing computer, network, or WSL IP
```

The current implementation is still an engineering prototype. It should not be presented as a complete DDS QoS product implementation.

## Validated QoS Categories

| Category | Current source support | Current validation support | Product-grade gap |
| --- | --- | --- | --- |
| Reliability | Stateful Reliable and Stateless Best Effort paths; HEARTBEAT/ACKNACK repair, GAP, duplicate suppression, mixed-Reader release, bounded/coalesced retry scheduling and bounded ACKNACK work. | Current host state suite 146/146 plus focused ESP32 and ROS 2 hardware regressions; see the support matrix. | Full DDS conformance, broad vendor/network campaigns, and generated-payload parsing closure remain outside the supported claim. |
| Durability | Volatile visibility/release and bounded Transient Local replay for Stateful and Stateless Writers, including fragmented replay. | Late Volatile exclusion, ordered Transient Local replay, Reader-departure release, and current-source ESP32 cases pass. | Transient/Persistent durability and keyed-instance persistence are unsupported by design. |
| History | Stateful/Stateless Keep Last and Keep All with atomic admission, physical/sample/byte limits, sequence exhaustion, and deterministic ownership release. | History ownership 47/47; resource tests 26/26; current ESP32 KeepLast, KeepAll, atomic replacement, and fragmented replay pass. | Per-instance History and a queued Subscriber `take()` backlog are not implemented; large campaigns are deliberately deferred. |
| Deadline | Deadline duration is carried into reader/writer state; missed count advances by missed period. | Focused ESP32 deadline miss check. | DDS-compatible requested/offered deadline status callbacks and ROS2 event interop are not complete. |
| Lifespan | Lifespan duration is represented and writer cache aging logic exists. | Focused expired/fresh behavior check; reply endpoint discovery. | Cache expiry during retransmission, late delivery, and RELIABLE edge cases needs more testing. |
| Liveliness | AUTOMATIC setting and lease duration are represented; reader tracks heartbeat/activity; liveliness lost/recovered state machine with transition counters; manual modes are rejected by QoS validation. | Focused activity and lease checks; lost/recovered transition counters exposed via mROS2 API. | Manual liveliness semantics (MANUAL_BY_TOPIC, MANUAL_BY_NODE) are not complete. |
| Resource Limits | Max samples and max bytes are represented; writer-side local checks exist; SEDP emits standard sample-count resource limit. | Burst rejection behavior and resource statistics are visible in ESP32 logs. | `maxBytes` is ESP32-local and not represented by the DDS PID_RESOURCE_LIMITS field; allocation failure reporting needs more design. |

## Latest Real-Hardware Validation

Latest local evidence from 2026-06-10:

```text
Strict bidirectional RELIABLE preflight: PASS
Result directory: /home/your-user/mROS2-QoS/results/qos_preflight_20260610_022457

Strict bidirectional RELIABLE reset stress validation: 3/3 PASS
Result directory: /home/your-user/mROS2-QoS/results/qos_reset_stress_20260610_022750
summary.txt: runs=3, passed=3, failed=0
```

These results support the current stable hardware validation path. They do not prove a complete product-grade DDS QoS implementation.

## Latest Engineering Change

The latest changes added reader receive-path statistics, a conservative early-data recovery path, liveliness state machine, and TRANSIENT_LOCAL late-joiner fix:

```text
subscriber_received_count()
subscriber_accepted_before_match_count()
subscriber_out_of_order_drop_count()
subscriber_unmatched_writer_drop_count()
subscriber_liveliness_lost_count()
subscriber_liveliness_recovered_count()
subscriber_check_liveliness()
```

`StatefulReader` now leaves visible evidence for these cases:

```text
1. DATA arrives before SEDP endpoint matching has completed.
2. A stale proxy exists briefly after reset while DATA from the new writer has already arrived.
3. A DATA sequence number older than the expected sequence number is dropped.
4. Liveliness transitions: alive → lost (heartbeat lease expired), lost → recovered (heartbeat received).
```

`StatefulWriter::addNewMatchedReader()` now sends a HEARTBEAT before cached DATA submessages for TRANSIENT_LOCAL durability, enabling late-joining readers to properly receive historical data.

The reader callback is also invoked outside the reader mutex, which reduces the chance that callback behavior disturbs RTPS receive-state handling.

## DDS QoS Beyond Current Scope

Complete DDS QoS is broader than the seven categories validated here. Product-level work may also need policies such as:

```text
Presentation
Partition
Ownership
Ownership Strength
Destination Order
Time Based Filter
Transport Priority
User Data / Topic Data / Group Data
Durability Service
Reader Data Lifecycle
Writer Data Lifecycle
Latency Budget
```

These are not product-grade features in the current project.

## Product-Grade Definition

For this project, product-grade QoS would require at least:

```text
1. API: clear public API, defaults, validity checks, and compatibility checks for each supported QoS policy.
2. Discovery: correct serialization and deserialization of interoperable SEDP/PID fields.
3. Behavior: QoS values affect writer, reader, cache, and endpoint matching behavior.
4. Events: deadline and liveliness status can be queried or reported through callbacks.
5. Interoperability: validation against ROS2 Humble, Fast DDS, Cyclone DDS, and representative endpoint combinations.
6. Stress: automated tests for reset, late joiner, packet loss, duplicate endpoints, and network jitter.
7. Documentation: each QoS policy clearly marked as supported, partial, or unsupported.
```

## Recommended Roadmap

### Phase 1: Stabilize The Existing Seven Categories

```text
Reliability: add loss/reorder tests and ACKNACK state tests.
Durability: add TRANSIENT_LOCAL late-joiner tests.
History: enforce KEEP_LAST depth with deterministic tests.
Deadline: expose missed-count/status through the mROS2 API.
Lifespan: test cache expiry during RELIABLE retransmission.
Liveliness: implement lost/recovered status and lease expiry events.
Resource Limits: define exact behavior on allocation and sample rejection.
```

### Phase 2: Make Discovery Product-Grade

```text
Audit all serialized PID fields.
Add compatibility tests against ROS2 topic info and actual endpoint matching.
Avoid adding SEDP fields that break matching without parser and compatibility coverage.
Add duplicate and stale endpoint handling tests.
```

### Phase 3: Expand Beyond The Current Scope

```text
Decide which DDS QoS policies are realistic for ESP32.
Implement only policies that can be supported within memory and CPU constraints.
Clearly mark unsupported policies instead of silently ignoring them.
```

## Recommended Public Wording

Use:

```text
The project currently implements a bounded QoS extension for mros2 on ESP32.
The strict hardware validation workflow uses RELIABLE in both directions, with real-hardware bidirectional communication and focused evidence for several QoS-related behaviors.
The current evidence supports this validation path, but it is not yet product-grade DDS RELIABLE certification.
It is not yet a complete DDS QoS product implementation.
```

Avoid:

```text
All DDS QoS is fully implemented.
The seven QoS policies are all complete.
ROS 2 topic info proves every QoS field.
```

## Security Hardening (2026-06-14)

Phase 1 security fixes applied and verified on real hardware:

```text
Buffer overflow:     Fixed 4 strcpy → strncpy + null termination (Domain.cpp)
Memory leak:         Fixed new without delete → static allocation (mros2.cpp)
Integer overflow:    Added overflow protection to duration conversions (qos.h)
Error handling:      Replaced 5 infinite loops with handle_fatal_error() (mros2.cpp)
Input validation:    Added RTPS packet bounds checks (MessageReceiver.cpp, MessageTypes.h)
Concurrency:         Replaced volatile bool with std::atomic<bool> (mros2.cpp)
Graceful shutdown:   Implemented mros2::shutdown() API (mros2.cpp, mros2.h)
CI/CD:               Enhanced CI with security checks and cppcheck (.github/workflows/ci.yml)
```

All fixes verified with: unit tests (97/97), hardware validation (ALL PASS), and static analysis (cppcheck clean).

Performance baseline: 21.1 msg/s throughput, 21.9ms avg latency, 202KB free memory.
```
