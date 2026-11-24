# Seven-QoS Performance Protocol Amendment 08

Status: FAMILY HARNESS SMOKE COMPLETE -- NO FORMAL PERFORMANCE DATA
Recorded: 2026-07-23 (Asia/Tokyo)

## Purpose

This amendment records the Liveliness family harness, the bounded dynamic
host-egress outage contract, and the same-commit short/long outage hardware
gates. It preserves all earlier evidence boundaries. No row from the frozen
51-cell, 1,530-run schedule was collected or accepted.

## Corrected Code Line

Commit `904fe1ba2c48785d247b6cbe3e47f9e70289612e` adds the Liveliness
performance smoke path. It is a new code line relative to the earlier
compatibility and mechanism campaigns. Earlier sealed result trees retain
their original binaries and source identities; this amendment neither
relabels nor mixes them with the new Liveliness evidence.

The board requests Automatic Liveliness with a build-time lease, registers
lost and recovered callbacks, establishes a continuously active healthy
baseline, and emits `PERF_LIVELINESS_OUTAGE_READY`. The root runner waits for
that exact UART marker before replacing the dedicated `eth1` root qdisc with
`netem loss 100%`. It records the outage qdisc, UTC start/end timestamps, then
removes the root netem before the workload. Cleanup is unconditional.

The host echo reply writer offers the same finite Liveliness lease as the board
reader. Its input subscription retains the common profile. This is required by
DDS requested/offered compatibility and prevents the finite board request from
being matched to an infinite host offer.

The board records before/after lost and recovered counters, callback counts,
first callback offsets, final writer-alive state, and the complete workload
outcome. The oracle requires counter/callback agreement and uses opposite
expectations on the two sides of the lease boundary.

## Development Diagnostics

The first short-outage development attempt retained an infinite host offer.
Fast DDS reported `LIVELINESS_QOS_POLICY` incompatibility and the UART outage
marker was never reached. A later long-outage attempt used a generic one-second
settle with a 500 ms lease, so a pre-window lost state and initial recovery
contaminated the outage delta. Both attempts remain unsealed diagnostics and
are excluded. The corrected harness uses a 300 ms stream of healthy probes and
requires the writer to be alive before freezing the counters and emitting the
outage marker.

## Same-Commit Liveliness Gates

The below-lease gate is retained at:

`results/diagnostics/20260723_seven_qos_performance_liveliness_LVSM_SHORT_904fe1b_attempt01/`

Configuration: RELIABLE, VOLATILE, KEEP_LAST depth 10, 2,000 ms lease, 250 ms
requested dynamic outage, 64-byte payload, 10 Hz workload, and dedicated
host-egress injection. The marker wait was 30.584 seconds. The recorded netem
interval was approximately 274 ms. Lost and recovered deltas and callbacks
were all zero, both first-event offsets were `-1`, and the writer was alive at
the end. The workload delivered 200/200 with zero publish failures, missed
intervals, or telemetry faults. The firmware SHA-256 is
`6608c3a18aa1f3657db2ef47e591bd9a3f0234407b511cbdf66f87ff709a7bb0` and the
host echo SHA-256 is
`99de77d4bebda7a01ee559956ddd99b12b66b4bac68bb961b63941ceebe2522d`.
The 27-file tree passed seal verification with tree SHA-256
`d2aa0daefc6a5844259696c9d65ae4f42c06cdbf7031cf01681650b12d084c86`.

The above-lease gate is retained at:

`results/diagnostics/20260723_seven_qos_performance_liveliness_LVSM_LONG_904fe1b_attempt01/`

Configuration: the same common workload with a 500 ms lease and 1,000 ms
requested dynamic outage. The marker wait was 34.550 seconds and the recorded
netem interval was approximately 1,022 ms. The board recorded exactly one lost
event and one recovered event, with matching callback counts. The first lost
offset was 710,482 us and the first recovered offset was 1,320,012 us. The
writer was alive at the end, and the workload delivered 200/200 with zero
publish failures, missed intervals, or telemetry faults. The firmware SHA-256
is `3979079ea97dd3b72ffd151a69c81e4db40d7bd6c4952c8c39f927c8e6d2db9b`.
The 27-file tree passed seal verification with tree SHA-256
`8de510ba236d232cf62ee656e305e3ce3809c1a77dd56cbeb65944a553880f93`.

Both runs contain a nonempty PCAP, the active 100% loss qdisc snapshot, the
post-outage canonical qdisc snapshot, copied binaries and CMake cache, generic
telemetry validation, family-specific validation, and verified release seals.

## Remaining Formal Gate

All six performance families now have same-commit or explicitly bound hardware
smoke gates. This closes family-harness smoke readiness only. The root formal
gate and every family formal gate remain false.

Before the frozen 1,530-run schedule can start, the formal runner must bind all
51 cell configurations to build and runtime parameters, freeze per-family
timing tolerances and estimands, implement accepted-run retry and replacement
rules, preserve randomized resume order, and pass a schedule-completeness audit
with directional impairment efficacy and resource telemetry. Until those items
are complete, the expanded protocol uses
`BLOCKED_FORMAL_PROTOCOL_FINALIZATION` and remains `DRAFT_NO_DATA`.

Energy remains `deferred_not_collected` under Amendment 01. These gates support
no energy-use conclusion.
