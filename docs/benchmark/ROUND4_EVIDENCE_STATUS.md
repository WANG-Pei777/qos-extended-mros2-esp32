# ROUND4 Evidence Status

## Main Transport Result Set

Current host-to-board result set:

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
- `analyze_rtps_timeline.py` generated packet-level direction, ACKNACK bitmap,
  and RTPS counter summaries for all ten host-to-board formal captures.

Current board-to-host result set:

- result directory: `results/experiments/20260712_b2h_net37`
- source commit recorded in manifests: `4837a369bad28dc8b84e495f8cba22d6c556a1fd`
- board IP: `10.37.12.107`
- repetitions: 30 accepted units per QoS/loss cell
- direction: board-to-host ingress `tc gact random` only
- Best Effort firmware SHA-256: `199f57a5d60074f48475c9dff580986ab004d6a226e34a92220a3e940404e33b`
- Reliable firmware SHA-256: `4c184540f1875c1bdf8e7d02bc01fb58c46d9f0e74bc335c5a1feb24530a5bea`

Required checks passed:

- `validate_round4.py` passes for all ten board-to-host formal CSVs.
- `audit_round4_result_set.py --direction board_to_host` passes for the full
  ten-condition matrix.
- `summarize_round4.py` generated board-to-host condition and effect-size tables.
- `plot_round4_transport.py` generated direction-labeled delivery, RTT, and
  effect-size figures.
- `summarize_rtps_pcap.py` summarizes the ten complete board-to-host formal
  captures. The interrupted Best Effort 15 percent capture is excluded from the
  analysis summary; the complete rerun is
  `20260712_104142_round4_transport_best_effort_15pct_board_to_host.pcapng`.
- `analyze_rtps_timeline.py` generated packet-level direction, ACKNACK bitmap,
  and RTPS counter summaries for all ten complete board-to-host captures.

Current per-message RTT key-cell rerun:

- result directory: `results/experiments/20260712_rtt_samples_b2h_net219_v2`
- source commit recorded in manifests: `059d483e9c76247b0cefd22e926a0996d8d9cc32`
- board IP: `10.219.224.107`
- host IP: `10.219.224.195`
- direction/loss: board-to-host ingress `tc gact random`, 15 percent only
- repetitions: 30 accepted units for Reliable and 30 for Best Effort
- Best Effort firmware SHA-256: `c2c8acaca9444d12fa42d58e194b36ba7babbd08509f5368578c4f518c069a9f`
- Reliable firmware SHA-256: `c4873bd46e92546bd00c4848f6f4143f7834cd39dc917039db81221bfad5ea30`

Required checks passed:

- `validate_round4.py` passes for both 15 percent CSVs.
- `_rtt_samples.csv` sidecar row counts equal the sum of `rtt_count` in the
  corresponding main CSVs.
- `summarize_round4_rtt_samples.py` generated true per-message RTT mean,
  median, p95, p99, and max summaries.
- `summarize_round4.py`, `plot_round4_transport.py`, `summarize_rtps_pcap.py`,
  and `analyze_rtps_timeline.py` generated matched analysis artifacts for the
  15 percent key-cell rerun.

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

The board-to-host impairment direction shows a stronger directional asymmetry.
Best Effort delivery declines roughly with the injected ingress loss while RTT
stays near 20 ms through 15 percent loss. Reliable has much heavier RTT tails:
Reliable-minus-Best-Effort mean RTT differences are about 134 ms at 1 percent,
465 ms at 5 percent, 957 ms at 10 percent, and 1190 ms at 15 percent, with
bootstrap intervals well above zero. Reliable delivery is also lower than Best
Effort at 5 percent and 15 percent in this result set.

These board-to-host results support a narrow claim that, in this ESP32/ROS 2
testbed and impairment direction, Reliable can trade lower effective delivery
and substantially higher latency tails for retransmission-oriented behavior
rather than delivering a simple reliability win. This still needs protocol-level
pcap inspection before attributing the effect to a specific RTPS mechanism.
Current timeline summaries separate packet direction and expose ACKNACK bitmap
presence, but they still include discovery/control traffic and are not yet a
per-application-sample retransmission reconstruction.

Per-message RTT support has been added for future reruns: firmware now prints
`RTT_SAMPLE seq=<n> rtt_us=<us>` for each valid measured reply, `run_matrix.sh`
writes `_rtt_samples.csv` sidecars, and `summarize_round4_rtt_samples.py`
computes per-message mean/median/p95/p99/max summaries. Existing formal result
sets were collected before this instrumentation, so their RTT-tail values remain
per-run summary statistics unless those cells are rerun.

The 15 percent board-to-host key cell has now been rerun with per-message RTT
instrumentation in `20260712_rtt_samples_b2h_net219_v2`. In that rerun, Best
Effort has 1042 per-message RTT samples with p95 35.276 ms and p99 76.168 ms.
Reliable has 950 per-message RTT samples with p95 3267.115 ms and p99 6222.092
ms. Reliable-minus-Best-Effort mean RTT is 1136.828 ms by the run-level
bootstrap summary, and Reliable delivery is 7.667 percentage points lower.

## Remaining Gaps Before A Top-Tier Submission

- Rerun the remaining 0, 1, 5, and 10 percent board-to-host cells with the
  `RTT_SAMPLE` firmware if the paper needs full per-message RTT curves.
- Reconstruct application-sample-level RTPS behavior from pcap before making a
  specific retransmission or protocol-overhead claim.
- Repeat the matrix on at least one independent network window or physical
  environment to quantify environment sensitivity.
- Add a claim-to-evidence table that maps every paper claim to CSV, manifest,
  pcap, figure, and analysis-script paths.
