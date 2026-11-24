# Round 6 Formal Mechanism Results

**Status:** COMPLETE AND AUDITED (2026-07-14)

## Dataset

- Formal result root: `results/experiments/20260713_round6_formal_5dabf7e`
- Firmware source commit: `5dabf7ed5798065b9ebfb87b4d4ad42d0ee1970b`
- Formal harness commit: `5946a74a116b0241494f02791ec04ca06793fff3`
- Analysis commit: `1c99afa53dabbd5b98faeacfcf2e8745b92980e5`
- Frozen schedule: 10 randomized superblocks, 12 cells, 3 accepted runs per visit
- Final population: 120/120 PASS visits and 360 accepted runs (30 per cell)
- Instrumentation exclusions: 1 retained run

The accepted-run ledger SHA-256 is
`b7b99e0a6ef43fac7fee3920f31b4d1c12cebff88609471500f9f9d48f01f39e`.
The complete design-manifest SHA-256 is
`c55619a4dd913ed51e23181520ce1b7b53cfe4b16001000ee5fde51fb2a85909`.
The deterministic release seal covers 2,504 files and 122,055,179 bytes;
its tree SHA-256 is
`8c7611249f242b7c84858e0975d14b5bd6d72b4753b8b275eeb230cc1c82c958`.

The one exclusion occurred in block 5, visit 3. WSL `eth1` became unavailable
after the first run, and five subsequent `tshark` preflight attempts exited
before producing result rows. The incomplete visit, logs, PCAP, and decision
record are retained under `rejected_visits`. The first run was excluded solely
to preserve the preregistered three-consecutive-run visit; its delivery and RTT
were not used in the decision. The cell visit was then repeated under the same
formal harness commit.

## Audit Result

`scripts/experiment/audit_round6_formal.py` reports PASS:

- 12 cells with exactly 30 accepted runs each
- 10 blocks with exactly 3 accepted runs per cell and block
- 360 unique accepted PCAP hashes and 360 unique `tc` state hashes
- all serial, condition-manifest, PCAP, and `tc` hashes match the ledger
- all accepted RTT sidecar counts match the run rows
- board-originated UDP evidence in every accepted PCAP (317 to 2,151 packets)
- observed `gact` drop rate mean 14.401%, range 10.056% to 19.786%
- no residual ingress qdisc or host process after completion

The nominal 15% target is implemented as `gact random netrand drop val 7`, or
14.285714% configured probability. Both values must remain visible in figures
and prose.

## Statistical Method

The authoritative combined analysis is under `analysis/complete_1c99afa`.
It includes 10,000 run-stratified bootstrap draws and exact `2^10` block
sign-flip randomization tests. Holm correction covers 24 confirmatory tests:
six prespecified contrasts across four primary outcomes. The right-censoring
variant of unresolved requests is a sensitivity analysis outside that family.

The heartbeat manipulation check reconstructs all three levels at approximately
250, 1,000, and 4,000 ms. One of 360 runs had no estimable inter-heartbeat
interval after near-simultaneous duplicate frames were removed; its serial
configuration and all primary outcomes were complete, so it remains accepted.

## Confirmatory Findings

### H1: Runtime History Depth

**Not supported.** Relative to depth 5, depths 10, 20, and 40 show no
Holm-significant improvement in delivery, run-level RTT p95, strong wire repair
evidence, or unresolved requested sequences. The data do not justify claiming
that deeper runtime history caused better repair under this workload.

### H2: Heartbeat Period

**Supported for application outcomes.** Averaged over depth, heartbeat 250 ms
versus 4,000 ms changed:

- delivery ratio by +0.3772 (95% bootstrap CI +0.3453 to +0.4083), exact
  randomization `p=0.001953`, Holm `p=0.046875`
- run-level RTT p95 by -3,032.6 ms (95% bootstrap CI -3,325.9 to -2,740.5 ms),
  exact randomization `p=0.001953`, Holm `p=0.046875`

Heartbeat 1,000 ms versus 4,000 ms is also Holm-significant for both outcomes.
The faster heartbeat also reduces unresolved wire requests in the point
estimate, but that contrast does not remain significant after the full 24-test
Holm correction (`p=0.15625`).

### H3: Depth-by-Heartbeat Interaction

**Not supported.** No interaction contrast remains significant after Holm
correction. The delivery interaction has an unadjusted signal, but its
family-adjusted `p=0.705078`; it must not be presented as confirmatory evidence.

## Wire Evidence Boundary

Application-entity reconstruction finds DATA with the same sequence both before
a matching NACK and later in 358/360 runs. This is strong evidence that repair
traffic exists, but it is nearly saturated and does not identify a depth effect.
Ingress capture can observe a packet before `tc` drops it, so pre-NACK DATA is
wire evidence rather than proof of host application delivery. The application
delivery and RTT rows remain the evidence supporting H2.

The analysis uses `tshark` directly on archived PCAPs and is reproducible without
a manual Wireshark session. Wireshark may still be used to create a human-readable
paper illustration, but it is not required for validity of the quantitative
results.

## Authoritative Outputs

- `formal_audit_report.json`
- `analysis/factorial_4d1bfb6/round6_run_outcomes.csv`
- `analysis/wire_1c99afa/round6_wire_run_outcomes.csv`
- `analysis/complete_1c99afa/complete_analysis_manifest.json`
- `analysis/complete_1c99afa/round6_complete_cell_summary.csv`
- `analysis/complete_1c99afa/round6_complete_contrasts.csv`
- `analysis/complete_1c99afa/round6_complete_outcomes.png`
- `analysis/complete_1c99afa/round6_complete_outcomes.pdf`
- `release_file_manifest.csv`
- `release_seal.json`

All earlier dry-run or superseded analysis directories are exploratory artifacts;
`complete_1c99afa` is the authoritative confirmatory output.
