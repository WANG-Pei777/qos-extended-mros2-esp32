# Seven-QoS Performance Protocol Amendment 10

Status: ACTIVE FOR FAMILY-HARNESS DEVELOPMENT -- NO FORMAL PERFORMANCE DATA
Recorded: 2026-07-23 (Asia/Tokyo)

## Purpose

This amendment records an externally controlled Resource Limits ACK-suppression
harness and its excluded hardware gate. It does not collect or accept any row
from the frozen 51-cell, 1,530-run schedule.

## External ACK-Suppression Harness

Commit `22ef9432e16eabbdf9af590ec8f464de8793fd29` adds a positive-duration
Resource Limits mode. After endpoint readiness, the ESP32-S3 emits
`PERF_RESOURCE_ACK_SUPPRESSION_READY`. The root wrapper then applies 100% loss
to the dedicated host-to-board egress path for a bounded interval. During that
interval, the board publishes one more probe sample than the configured writer
sample cap without using the legacy internal transmission hold.

The board records probe attempts, accepted and rejected publishes, allocation
failures, history peak, post-outage history, recovery replies, and the complete
measurement workload. The wrapper records marker wait, outage timestamps,
pre-deletion qdisc counters, post-cleanup qdisc state, and PCAP.

Commit `4e4413ea7f2a131dd2a9a9d3ac7166d7f9ed2cc0` adds a fail-closed dynamic
outage validator. It requires the expected marker/profile, a bounded elapsed
time, positive 100%-loss qdisc drops, matching PCAP metadata, a passing policy
oracle, and canonical network cleanup.

## Development Diagnostics

The first dirty run is retained at:

`results/diagnostics/20260723_seven_qos_performance_resource_R01_ack_dirty_attempt01/`

The network episode and resource probe executed, but the generic validator
still required zero workload publish failures. That expectation was incorrect
for a Resource Limits pressure cell, so the attempt was rejected and retained.

The corrected dirty run is retained at:

`results/diagnostics/20260723_seven_qos_performance_resource_R01_ack_dirty_attempt02/`

It verified the pressure estimand and successful-delivery reconciliation. It
preceded the pre-deletion qdisc counter snapshot and remains excluded.

## Clean Excluded Gate

The complete clean gate is retained at:

`results/diagnostics/20260723_seven_qos_performance_resource_R01_ACK_22ef943_attempt01/`

Configuration: RELIABLE, VOLATILE, KEEP_ALL, `max_samples=5`, one excess probe,
512-byte payload, 50 Hz, and a 1,000 ms host-to-board ACK-suppression episode.
The firmware reports exact source commit `22ef943` and has SHA-256
`ee6ff7221d176641f8dccf96a8cc30e81bcd83e830c772509687b72e11036e2f`.

The marker-aligned outage lasted 1.031849 seconds. The final netem snapshot
recorded 39 dropped host-to-board packets at 100% configured loss. The probe
attempted six publishes, accepted five, rejected one, had zero allocation
failures, reached history peak five, and drained to zero after the outage.
Probe echo replies are retained as a non-gating observation because the
suppression episode intentionally discards them before the reply writer can
recover. History drain and the subsequent bidirectional workload establish
recovery.

The measurement workload attempted 1,000 publishes. The writer rejected 90 at
the configured resource limit and all 910 successful publishes were delivered.
The policy and dynamic-outage validators passed. The PCAP contains 1,823,084
bytes and has SHA-256
`6e265f3be1eb39a4cd7b537bd4b3c4a513bdae64a36e3859d29487faa3ed8d74`.
The network returned to the canonical `mq` plus `fq_codel` state.

The 29-file tree passed release-seal verification with tree SHA-256
`a0914238c5665273a6115cf3cea7552ace8096724adea59690043900019bd502`.

## Evidence Boundary and Remaining Gate

This N=1 result is an excluded harness gate. It freezes a testable external
ACK-suppression mechanism and its audit oracle but is not a formal performance
observation and cannot be promoted into the 1,530-run campaign.

Resource Limits formal collection remains blocked until the 1,000 ms episode
is bound into every Resource cell build/runtime specification, exact artifacts
are frozen, and the formal runner, accepted/rejected ledger, retry behavior,
and schedule-completeness audit are verified. The root formal launch gate and
every family formal launch gate remain false.

Energy remains `deferred_not_collected` under Amendment 01. This smoke supports
no energy-use conclusion.
