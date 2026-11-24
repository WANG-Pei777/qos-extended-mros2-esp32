# Impairment Efficacy Readiness Audit

Status: ENGINEERING READINESS ONLY -- profiles ready for preregistration review
Date: 2026-07-20

## Evidence Boundary

This audit covers excluded N=1 pilots for the current implementation at Best
Effort and Reliable, 512-byte payloads, 50 Hz, and 20-second measurement windows.
It establishes that the impairment harness changes the intended host-to-board
egress path and that the board can observe the resulting mechanism. It does not
estimate performance and must not enter formal cross-system statistics.

All profiles in this audit affect host-to-board egress on `eth1` only. They do not
represent bidirectional impairment. Direction-interaction experiments require a
separate preregistered ingress/AP/IFB path and are not implied by these results.

## Frozen Candidate Profiles

| Profile | Exact netem arguments | Scope |
| --- | --- | --- |
| clean | no netem qdisc | control |
| independent loss 5% | `loss random 5%` | host-to-board egress |
| independent loss 15% | `loss random 15%` | host-to-board egress |
| burst loss | `loss gemodel 1% 25% 95% 0.1%` | host-to-board egress |
| fixed delay 20 ms | `delay 20ms` | host-to-board egress |
| fixed delay 50 ms | `delay 50ms` | host-to-board egress |
| delay variation | `delay 20ms 10ms distribution normal` | host-to-board egress |
| reordering | `delay 20ms reorder 25% 50% gap 5` | host-to-board egress |

The Gilbert-Elliott arguments are respectively good-to-bad transition 1%,
bad-to-good transition 25%, bad-state loss 95%, and good-state loss 0.1%.
The installed `tc` version has no seed option; exact commands, configured/final
statistics, and cleanup state are retained for every attempt.

## Campaigns and Audit

The v1 matrix collected 16/16 cells and 16 PCAPs. Its independent audit passes
all artifact, validator, PCAP, qdisc, and cleanup checks. Ten efficacy gates passed
immediately. Burst, delay variation, and reordering were initially blocked because
the board exposed only aggregate RTT and delivery counts.

The v2 harness adds post-window-only observability:

- missing sample count, number of missing runs, and longest missing run;
- board-visible arrival inversions;
- RTT sum and squared sum for a run-level variance calculation.

No additional UART is emitted during the measurement window. The validator
reconciles the fields between `COMPARE_FINAL` and `BENCH_FINAL`, checks missing-run
arithmetic, and validates the RTT moments. Old logs without these optional fields
remain valid.

The v2 matched-control matrix collected 10/10 cells and 10 PCAPs. Its audit passes
8/8 QoS-by-profile-family efficacy gates:

| QoS | Gate | Observed engineering evidence |
| --- | --- | --- |
| Best Effort | delay variation | clean RTT SD 5.147 ms; impaired SD 12.175 ms; quadrature-added 11.033 ms |
| Reliable | delay variation | clean RTT SD 3.722 ms; impaired SD 14.216 ms; quadrature-added 13.720 ms |
| Best Effort | reordering | 49 netem requeues and 19 board arrival inversions |
| Reliable | reordering | 56 netem requeues and zero board arrival inversions; the visible receive path remained ordered |
| Best Effort | independent versus burst loss | 5% max missing run 2; burst max 7 across 13 runs |
| Reliable | independent versus burst loss | 5% max missing run 2; burst max 20 across 17 runs |

Fixed-delay v1 mean RTT shifts were +20.244 ms and +51.430 ms for Best Effort,
and +19.342 ms and +46.730 ms for Reliable at configured 20 ms and 50 ms delays.
Observed 5% and 15% qdisc drop ratios passed the pilot tolerance for both QoS
modes. These are efficacy checks, not comparative outcome estimates.

The v2 audit is
`results/audits/20260720_impairment_observability_v2_pilots/audit.json`, SHA-256
`d6870167af9918807766e9429b2ea95d8911eb58d4e85679406adf322aad99f6`.
Its ledger, summary, PCAP inventory, and efficacy-table SHA-256 values are
`12913c5b4e3e6612932bcc3088567deeef76400d4541309d2b2a17b8ada8f00b`,
`bb4a679dc858f31d391751a86320e30675c212773c61d2e413b60389f0834ab0`,
`9b841da3e75a39cae2a5e717fde159ca46bab4f57cae4a2df74cbd9f247a3bc0`, and
`6ce9bbe15a7a51e0b363a88879f3a3d698d0041c065ef7db0a4dc40d4ea1a698`.

## Mechanism Boundary

Reliable did not imply complete delivery in every N=1 pilot. For example, the v1
20 ms, delay-variation, reordering, 5% loss, and 15% loss cells delivered 900,
880, 966, 958, and 849 of 1,000 replies. This variation is a reason to run the
preregistered N=30 cells; it is not a failure criterion and not evidence that one
QoS mode is superior.

## Storage Incident and Gate

During the first impairment build, the Windows `C:` volume fell to approximately
11 MB free. WSL returned filesystem-wide `EIO`, including reads of `/etc/passwd`.
No result tree was being collected. WSL was stopped, 7.033 GiB of regenerable
NVIDIA DX cache was removed, and the distribution, project files, and qdisc state
were revalidated before work resumed.

The smoke runner now refuses to start below 5 GiB free on `/mnt/c`. This threshold
is adequate only for short pilots. The 26 impairment pilot directories occupy
approximately 534 MiB, of which 35 MiB is PCAP and most of the rest is duplicated
ELF/map provenance. Naively repeating that layout for 3,270 runs would consume
roughly 70 GiB before power traces and analysis products.

Before formal collection, store each unique firmware/ELF/map/CMake bundle once in
a content-addressed campaign bundle and let per-run manifests reference its hash.
Freeze a measured storage projection and require free host capacity of at least
the larger of 50 GiB or twice the projected campaign size. The current host does
not pass that formal storage gate.

## Decision

The host-egress impairment profile set is ready for preregistration review. Formal
collection is not authorized. It remains blocked on the calibrated external power
monitor and GPIO alignment, formal storage remediation, schedule/randomization
freeze, and explicit handling of unsupported baseline cells. Bidirectional or
direction-interaction claims remain outside this profile set.
