# P4 Independent-Window Formal Results

**Status:** COMPLETE, AUDITED, ANALYZED, AND SEALED (2026-07-15)

## Dataset

- Formal result root: `results/experiments/20260715_p4_independent`
- Firmware source commit: `43ab8a86233f3a00d86160c296e4bef0486a2375`
- Formal harness commit: `e20da4bbc0d0c93419e66c36212a077c89da53dc`
- Independent-window start: `2026-07-15T03:31:14+09:00`
- Frozen schedule: 10 randomized superblocks, 6 cells, 3 accepted runs
  per visit
- Final population: 60/60 PASS visits, 180 accepted runs, and 0 rejected
  runs

The design-manifest SHA-256 is
`96555eff224fe87f8421fec32cab526d227d36ad6af6d5f43401738a4820a4cf`.
The acceptance-ledger SHA-256 is
`a2415bfe236db95b3856fc514b2a87c0f8c6f23c6cd65c71b4f62436fb84deb2`.
The deterministic release seal covers 1,282 files and 31,495,649 bytes;
its tree SHA-256 is
`a54f57528c6d616e7ffaad522c8f735f651961dd5fa2778ef98d39a4f50a3c4f`.

## Audit Result

`scripts/experiment/audit_p4_formal.py` reports PASS:

- exactly 30 accepted runs in each QoS-by-loss cell
- 180 unique accepted PCAP hashes and 180 unique accepted `tc` state hashes
- all run, sidecar, serial, firmware, host, PCAP, and `tc` provenance hashes
  match
- every accepted PCAP contains board-originated UDP (198 to 265 packets)
- observed 5% target drop rate mean 4.780%, range 1.878% to 7.798%
- observed nominal 15% target drop rate mean 14.289%, range 9.053% to
  19.600%
- acceptance used instrumentation and provenance only

The nominal 15% condition is configured as `gact` probability 1/7, or
14.285714%. Both labels remain visible in the analysis. The audit-report
SHA-256 is
`2d539c19b339fab439a0c2b7902241094bbd93f087b1bec42a9c4232246095cb`.

## Statistical Method

The preregistered analysis uses independent runs, 10,000 run-stratified
bootstrap draws, exact `2^10` superblock sign-flip tests, and Holm correction
across the six primary contrasts: RELIABLE minus BEST_EFFORT for RTT p95 and
delivery at 0%, 5%, and nominal 15% loss.

## Cell Outcomes

| Loss target | QoS | N | Delivery mean [95% CI] | RTT p95 mean, ms [95% CI] |
| ---: | --- | ---: | ---: | ---: |
| 0% | RELIABLE | 30 | 1.0000 [1.0000, 1.0000] | 35.49 [33.12, 38.28] |
| 0% | BEST_EFFORT | 30 | 1.0000 [1.0000, 1.0000] | 41.76 [36.90, 47.28] |
| 5% | RELIABLE | 30 | 0.9417 [0.9108, 0.9658] | 2112.73 [1710.61, 2525.26] |
| 5% | BEST_EFFORT | 30 | 0.9575 [0.9458, 0.9683] | 41.13 [33.07, 53.04] |
| 15% | RELIABLE | 30 | 0.7833 [0.7367, 0.8250] | 3051.72 [2539.39, 3602.62] |
| 15% | BEST_EFFORT | 30 | 0.8483 [0.8317, 0.8650] | 37.58 [34.91, 40.45] |

## Confirmatory Findings

P4 meets the preregistered replication-success rule. RELIABLE minus
BEST_EFFORT RTT p95 is:

- +2071.60 ms at 5%, 95% CI [1668.62, 2485.60], exact `p=0.001953`,
  Holm `p=0.011719`
- +3014.14 ms at nominal 15%, 95% CI [2502.36, 3564.97], exact
  `p=0.001953`, Holm `p=0.011719`

At nominal 15%, RELIABLE delivery is 6.5 percentage points lower than
BEST_EFFORT, 95% CI [-11.50, -1.92], exact `p=0.003906`, Holm
`p=0.015625`. At 5%, the -1.58 percentage-point effect is not significant
(Holm `p=0.523438`). At 0%, both modes deliver 100%; the RTT contrast does not
survive the six-test correction (Holm `p=0.082031`).

The supported paper claim is narrow: on the same ESP32 and ROS 2 testbed, in a
new WSL/network window, board-to-host impairment again produced a large
RELIABLE RTT-tail penalty without a delivery advantage. P4 is temporal and
network-window replication, not cross-device or cross-site replication.

## Authoritative Outputs

- `analysis/formal_audit_report.json`
- `analysis/confirmatory_92e5218/p4_analysis_manifest.json`
- `analysis/confirmatory_92e5218/p4_cell_summary.csv`
- `analysis/confirmatory_92e5218/p4_contrasts.csv`
- `analysis/confirmatory_92e5218/p4_complete_summary.md`
- `analysis/confirmatory_92e5218/p4_primary_outcomes.png`
- `analysis/confirmatory_92e5218/p4_primary_outcomes.pdf`
- `analysis/wire_92e5218/p4_wire_analysis_manifest.json`
- `analysis/wire_92e5218/p4_wire_cell_summary.csv`
- `release_file_manifest.csv`
- `release_seal.json`

`verify_result_tree_seal.py` reports PASS for every sealed file. The analysis
manifest SHA-256 is
`c39dd43156d5e3114441cc8fe0dfb1d5867aeaf589e43bcd4a1be6212e2197f2`.
