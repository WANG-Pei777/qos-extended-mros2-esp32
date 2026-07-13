# Round 6 Mechanism Experiment Preregistration

**Status:** frozen design. Endpoint discovery and the 22-assertion source-equivalent baseline verification passed after the AP restart on 2026-07-13. Formal execution remains blocked on parameterized firmware, the memory pilot, immutable archival of all variants, and per-cell smoke gates.

The legacy parameter-sweep scripts are not authorized for formal data collection. This document freezes the hypotheses, factors, execution order, outcomes, and analysis before new mechanism data are observed.

## Motivation

Round 4 application-entity reconstruction found a Reliable sequence both before a matching NACK and in later DATA in 0/6/19/26/29 of 30 runs at 0/1/5/10/15% board-to-host loss. Best Effort had no such links. This supports post-NACK wire behavior but does not identify the cause of the Reliable tail.

The implementation exposes three distinct limits that must not be conflated:

| Setting | Current value | Role |
| --- | ---: | --- |
| `pub_qos.depth` | 5 | Runtime KEEP_LAST eviction depth |
| `HISTORY_SIZE_STATEFUL` | 10 | Compile-time stateful cache capacity ceiling |
| publisher `max_samples` | 30 | Resource limit |

Sweeping only `HISTORY_SIZE_STATEFUL` above 5 would not necessarily change runtime eviction. A depth of 40 would also exceed the current compile-time capacity and could be confounded by the resource limit.

## Frozen Hypotheses

- **H1:** Increasing runtime KEEP_LAST depth reduces requested sequences with no later observed DATA and improves delivery under loss.
- **H2:** Reducing the Reliable writer heartbeat period reduces run-level RTT p95 and NACK-to-later-DATA latency.
- **H3:** Runtime history depth and heartbeat period interact: deeper history is useful only when repair is requested before samples become unavailable.

## Factorial Design

| Factor | Levels |
| --- | --- |
| QoS | Reliable only |
| Direction and impairment | board-to-host ingress, 15% netem loss |
| Runtime KEEP_LAST depth | 5, 10, 20, 40 |
| Heartbeat period | 250, 1000, 4000 ms |
| Accepted independent runs | 30 per cell |

All 12 cells use compile-time stateful history capacity 48. Publisher `max_samples` must be at least 48, and `max_bytes` must be shown nonbinding in a memory pilot. These controls remain identical across cells.

## Implementation Gate

Formal builds must expose and log these independent build parameters:

- `MROS2_QOS_HISTORY_DEPTH`
- `MROS2_RTPS_HISTORY_CAPACITY`
- `MROS2_RTPS_HEARTBEAT_PERIOD_MS`
- `MROS2_QOS_RESOURCE_MAX_SAMPLES`
- `MROS2_QOS_RESOURCE_MAX_BYTES`

The boot log, build metadata, and result manifest must agree. Before the matrix starts:

1. Build all 12 firmware variants from one clean commit.
2. Reject a build unless capacity is at least runtime depth and resource limits are nonbinding.
3. Archive every firmware binary immutably with SHA-256 before flashing.
4. Pass the 22-assertion baseline verification with the designated baseline binary.
5. Pass three smoke runs per cell, including configuration and capture validation.

No formal run may edit a tracked source file in place.

## Randomization And Independence

Use 10 randomized superblocks. Each superblock visits every one of the 12 cells once in a seeded order and collects three consecutive accepted runs per visit, yielding 30 accepted runs per cell. The frozen randomization seed is `20260714`.

A run receives a new application process/GUID boundary and its own sidecar. Rejected runs are retained with a rejection reason and are not silently replaced. Thermal state, board resets, capture continuity, netem state, and firmware SHA are recorded.

## Frozen Outcomes

Primary run-level outcomes:

1. Message RTT p95.
2. Delivery ratio.
3. Indicator that at least one sequence is observed both before a matching NACK and in later DATA.
4. Count of requested sequences with no later observed DATA.

Secondary outcomes include run-median NACK-to-later-DATA latency, HEARTBEAT interval, ACKNACK count, and retransmission-related packet count. The final heartbeat interval is right-censored; outcome 4 must be reported both with all observations and with requests in that interval excluded.

## Frozen Analysis

- Runs, not messages or packets, are the independent experimental units.
- Use run-cluster bootstrap confidence intervals for message-tail outcomes.
- Report prespecified depth contrasts, heartbeat contrasts, and the depth-by-heartbeat interaction.
- Control the family of confirmatory contrasts with Holm correction.
- Report effect sizes and 95% confidence intervals regardless of significance.
- Keep failed/rejected-run accounting and all exclusions in the audit ledger.

## Claim Boundary

H1 requires a monotonic or otherwise model-supported depth effect on delivery or unresolved requests while capacity and resources remain fixed. H2 requires a heartbeat effect on RTT p95 or NACK-to-DATA latency. H3 requires a supported interaction. Wire-level same-sequence observation alone cannot establish application delivery, writer-history eviction, or causality.

## Legacy Script Status

`scripts/experiment/sweep_param.sh` mutates tracked source and lacks the required provenance controls. The historical `run_e6_heartbeat_sweep.sh` also passed `--loss` and `--condition` as if they were sweep values. Both are prohibited for formal data collection; the E6 wrapper now exits immediately.
