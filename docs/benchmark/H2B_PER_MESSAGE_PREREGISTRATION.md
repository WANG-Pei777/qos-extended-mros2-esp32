# H2B Per-Message RTT Formal Preregistration

**Status:** FROZEN BEFORE NEW H2B SMOKE OR FORMAL DATA COLLECTION

**Frozen at:** 2026-07-15 20:30 Asia/Tokyo

## Activation And Evidence Boundary

The optional host-to-board (H2B) matrix is activated to close the final item in
the formal collection plan. Historical H2B data under
`results/experiments/20260711_net37` contain run-level summaries and
per-condition captures only. They remain historical evidence and are not reused
as formal observations in this campaign.

This campaign supplies per-message RTT sidecars under the same exact-binary,
per-run PCAP, provenance, randomized-block, audit, and release-seal standard as
P4. It does not create an independent-device or independent-site replication.
Direction is not randomized across P4 and H2B campaigns, so cross-direction
differences are descriptive and cannot be presented as a causal direction
effect.

## Frozen System And Impairment

- Board: the same ESP32-S3 used by P4.
- Host: ROS 2 Humble under WSL2 with the frozen C++ echo binary.
- Firmware: the exact sealed P4 RELIABLE and BEST_EFFORT binaries from
  `results/experiments/20260715_p4_firmware_set_amended`.
- Workload: the existing finite `qos_eval` workload and `RTT_SAMPLE` records.
- Direction: host-to-board only.
- Injection: `tc clsact` egress flower filter limited to UDP whose destination
  is the board, followed by `gact` random drop.
- Capture: one PCAP and one `tc` state record per attempted run. Egress capture
  may observe a packet before the impairment action drops it; application RTT
  and delivery records remain the outcome evidence.

The nominal loss levels are 0%, 1%, 5%, 10%, and 15%. The first four map to
exact inverse-probability denominators 0, 100, 20, and 10. Nominal 15% uses
denominator 7, or 14.285714% configured probability. Both nominal and effective
values remain visible in all outputs.

## Frozen Schedule

| Factor | Value |
| --- | --- |
| QoS | RELIABLE, BEST_EFFORT |
| H2B target loss | 0%, 1%, 5%, 10%, nominal 15% |
| Accepted runs per cell | 30 |
| Superblocks | 10 |
| Visits per superblock | all 10 cells in seeded random order |
| Accepted runs per visit | 3 consecutive resets |
| Total accepted runs | 300 |
| Random seed | `202607154` |

Firmware changes occur only at visit boundaries. A rejected attempt is retained
and replaced within the same visit. The generated schedule and its hash are
frozen in the H2B design-asset manifest before smoke.

## Outcomes And Acceptance

Primary run-level outcomes are delivery ratio and per-run RTT p95. Secondary
run-level outcomes are RTT median/p99, match wait, and link-health ping.
Per-message pooled median/p95/p99 are prespecified secondary outcomes; their
uncertainty resamples whole runs as clusters and keeps messages inside the
selected run.

Acceptance is instrumentation-only and requires:

- a clean recorded harness commit and exact firmware/host hashes;
- the scheduled QoS, target/effective loss, and configuration records;
- endpoint matching and completion of the finite behavior phase;
- one raw serial log, host log, run-specific RTT sidecar, PCAP, and `tc` state;
- sidecar row count equal to the run's recorded RTT count;
- nonempty host-to-board UDP capture; and
- matching hashes for all recorded evidence.

RTT magnitude, delivery ratio, RX count, and observed drop count are never
acceptance criteria. An accepted run with no estimable RTT remains in delivery
analysis and is reported explicitly for RTT; it is not silently replaced.

## Frozen Analysis

Runs are independent units. Cell intervals use 10,000 run-stratified bootstrap
draws. Exact `2^10` sign-flip tests operate on randomized superblock differences.
Holm correction covers ten confirmatory contrasts: RELIABLE minus BEST_EFFORT
for run-level RTT p95 and delivery at each of five loss levels. No outlier
removal is permitted.

Per-message summaries use run-cluster bootstrap intervals and are secondary to
the run-level confirmatory family. Cross-direction comparison with P4 is
descriptive because collection window and direction are confounded. Any future
causal direction claim requires a design that randomizes direction within the
same collection campaign.

## Precollection Gates

1. Verify the complete P4 firmware-set release seal and exact artifact hashes.
2. Freeze and seal the 100-visit H2B schedule and design manifest.
3. Pass exact-binary smoke at 0% and nominal 15% for both QoS modes, with four
   unique PCAPs and `tc` states and no residual qdisc.
4. Record the smoke manifest, host hash, harness commit, interface, board IP,
   and WSL boot ID. Formal execution must match them exactly.
5. Run unit tests for schedule, ledger, audit, and analysis code before formal
   collection.

Any correction before formal collection is recorded as a timestamped amendment.
After the first formal H2B run, the workload, acceptance boundary, factors,
outcomes, and analysis family cannot change.
