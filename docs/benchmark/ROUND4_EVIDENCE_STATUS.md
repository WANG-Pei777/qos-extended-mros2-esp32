# ROUND4 Evidence Status

## Main Transport Result Set

Current main result set:

- result directory: `results/experiments/20260711_net37`
- source commit recorded in manifests: `64e7ec710b3342b838b9561ec5808e882c082efe`
- board IP: `10.37.12.107`
- repetitions: 30 accepted units per QoS/loss cell
- direction: host-to-board netem only
- Best Effort firmware SHA-256: `4229fb5b5023a869c7fb0b8f93b103a2b692b7c99cb66d3f757ab3f06b4cc5a7`
- Reliable firmware SHA-256: `18074dae39d6403a2f9b8622a6e547ea4dfd5591fe0dc8d19cf9971b9df675c7`

Required checks passed:

- `validate_round4.py` passes for all ten formal CSVs.
- `audit_round4_result_set.py` passes for the full ten-condition matrix.
- `summarize_round4.py` generated condition and effect-size tables.
- `plot_round4_transport.py` generated delivery, RTT, and effect-size figures.
- `summarize_rtps_pcap.py` confirms RTPS DATA, HEARTBEAT, and ACKNACK evidence
  in representative 0 percent and 15 percent captures.

## Current Interpretation

The current host-to-board transport result does not support a broad claim that
Reliable improves delivery over Best Effort. Delivery differences are small and
their bootstrap confidence intervals cross zero at 1, 5, 10, and 15 percent
loss. At 0 percent loss, both modes deliver 100 percent in this setup.

Reliable also does not consistently reduce RTT in this result set. The 1
percent condition shows higher Reliable mean RTT, while the other loss levels
are close or have confidence intervals that cross zero. The 15 percent Reliable
RTT distribution has a visible high-tail effect in the run-level p95 summary.

These results are publishable as a careful negative/nuanced finding only if the
paper claim is framed narrowly: mROS2 QoS behavior under this host-to-board
RTPS/UDP impairment setup, with observed delivery/latency tradeoffs and wire
evidence from pcap. They are not sufficient for a generalized DDS QoS
reliability claim.

## Remaining Gaps Before A Top-Tier Submission

- Run the board-to-host impairment direction with the same N and provenance
  discipline.
- Add true per-message RTT samples or explicitly state that the reported p95 is
  the p95 of per-run RTT means.
- Inspect and report RTPS submessage behavior from pcap, not just packet counts,
  before making any retransmission or protocol-overhead claims.
- Repeat the matrix on at least one independent network window or physical
  environment to quantify environment sensitivity.
- Add a claim-to-evidence table that maps every paper claim to CSV, manifest,
  pcap, figure, and analysis-script paths.
