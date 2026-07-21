# Three-System Matched-Workload Formal Results

**Status:** COMPLETE, AUDITED, ANALYZED, AND SEALED (2026-07-15)

## Dataset

- Formal result root: `results/experiments/20260715_three_system_formal`
- Formal harness commit: `b8c8d84c2e3e37488af64bac0ea20436a8838661`
- Analysis export commit: `d637b39`
- Origin project builder commit: `b0cabd5`
- Frozen schedule: 10 randomized superblocks, all 3 systems per block,
  10 accepted runs per visit
- Final population: 30/30 PASS visits, 300 accepted runs, and 0 rejected
  attempts
- Per-system population: 100 runs and 4,000 measured RTT messages

The design-manifest SHA-256 is
`564b259dee37e78fd7bc5fe3d3e453c37f3129f80554a1f017009d14df0302fb`.
The acceptance-ledger SHA-256 is
`405ca7544322c9d5bf0f23f4deee8cf4f442627b4d5efaf172e9f37e140c057d`.
The deterministic release seal covers 1,323 files and 34,969,443 bytes;
its tree SHA-256 is
`2df90569b2926485fd075f80b64065e711e583a784d035bae6fe35c0a5ff4999`.

## Audit Result

`scripts/experiment/audit_three_system_formal.py` reports PASS:

- exactly 100 accepted runs per system and 10 per scheduled visit
- 12,000 accepted message rows matching every run-level RX count
- 300 unique PCAP paths and hashes, all with board-originated UDP
- all serial, PCAP, firmware, host-binary, schedule, smoke, and asset hashes
  match their recorded provenance
- no RX, delivery, ready-time, or RTT value was used for acceptance
- no rejected attempt was removed; this collection had zero rejections

The final audit-report SHA-256 is
`db6f27c2decd9ad766b7fd6c7ed6f4ba936939d5083cc0f6894b9a9f65cfab28`.

## Statistical Method

The preregistered analysis uses the run as the independent unit, 10,000
run-cluster bootstrap draws for 95% intervals, and exact `2^10` sign-flip
tests over randomized superblock differences. Holm correction covers all six
confirmatory tests: the three system pairs for per-run RTT p95 and
reset-to-ready time. No outliers were removed.

The analysis report is bound to commit `d637b39`, the analysis-script hash,
and the hashes of the design manifest, audit report, accepted-run table, and
accepted-message table. Its SHA-256 is
`053b2b267beb0b3ee608506607eb1e6504508663477c95deb38e1d99cf255845`.

## Primary Outcomes

| System | N | RTT p95 mean, ms [95% CI] | Reset-to-ready mean, s [95% CI] |
| --- | ---: | ---: | ---: |
| mROS2-QoS | 100 | 30.92 [29.37, 32.64] | 11.41 [11.29, 11.55] |
| upstream mros2-esp32 | 100 | 31.76 [29.84, 33.91] | 11.19 [11.07, 11.34] |
| micro-ROS | 100 | 34.69 [32.79, 36.85] | 3.90 [3.67, 4.16] |

All 300 runs delivered 40/40 measured messages.

### RTT p95

No pairwise RTT contrast remains significant after correction. The mROS2-QoS
minus micro-ROS point estimate is -3.77 ms, but its exact `p=0.029297` becomes
Holm `p=0.117188`. The data therefore do not support a confirmatory claim that
any implementation has lower clean-network RTT p95 than another.

### Reset-to-ready

micro-ROS reaches the first echoed warm-up record faster than both direct-RTPS
systems under the frozen continuously running Agent condition:

- mROS2-QoS minus micro-ROS: +7.503 s, exact `p=0.001953`, Holm
  `p=0.011719`
- upstream minus micro-ROS: +7.285 s, exact `p=0.001953`, Holm
  `p=0.011719`

mROS2-QoS minus upstream is +0.219 s and is not significant after correction
(Holm `p=0.117188`). The supported claim is specific to this board, AP, host,
workload, and continuously running Agent; it is not a universal startup claim.

## Resource And Wire Evidence

| System | Firmware, KiB | Free heap, KiB | Board-link packets/message | Board-link bytes/message |
| --- | ---: | ---: | ---: | ---: |
| mROS2-QoS | 775.8 | 231.4 | 3.42 | 553.5 |
| upstream mros2-esp32 | 767.2 | 240.4 | 3.13 | 523.6 |
| micro-ROS | 794.1 | 254.2 | 14.01 | 945.9 |

These are descriptive secondary outcomes. Wire counts cover board-addressed
UDP in each accepted PCAP. The micro-ROS board heap and firmware values do not
include host-side Agent resources, so the table must not be presented as a
complete end-to-end memory comparison.

## Origin And Publication Outputs

The Origin 2024b project contains the 300-run primary worksheet, publication
summary and confirmatory tables, the resource/wire table, two editable native
box-plot pages, the exact final publication figure, caption, and provenance.
The builder reopens the saved project and verifies all five pages and both note
objects before writing its manifest. The project SHA-256 is
`7374a1fc034a289b399beea5c569827738edbf9b9e042864e4e40fb54e92864a`.

Authoritative outputs are:

- `audit/audit_report.json`
- `analysis/analysis_report.json`
- `analysis/origin_primary_data.csv`
- `analysis/publication_system_table.csv`
- `analysis/publication_confirmatory_table.csv`
- `analysis/publication_tables.md`
- `analysis/resource_wire_table.csv`
- `analysis/three_system_primary_outcomes.png`
- `analysis/three_system_primary_outcomes.pdf`
- `analysis/three_system_primary_outcomes.svg`
- `analysis/figure_caption.md`
- `analysis/three_system_formal_origin.opju`
- `analysis/origin_project_manifest.json`
- `release_file_manifest.csv`
- `release_seal.json`

After sealing, `verify_result_tree_seal.py` reports PASS for all 1,323 files.
The host has no residual benchmark, Agent, or capture process, and `eth1` has
no `netem` or ingress impairment qdisc.
