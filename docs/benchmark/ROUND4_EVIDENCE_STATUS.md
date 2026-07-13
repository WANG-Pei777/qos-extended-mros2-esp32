# ROUND4 Evidence Status

## Formal Result Sets

Historical host-to-board matrix:

- result directory: `results/experiments/20260711_net37`
- source commit in manifests: `64e7ec710b3342b838b9561ec5808e882c082efe`
- board IP: `10.37.12.107`
- direction: host-to-board netem only
- repetitions: 30 accepted runs per QoS/loss cell
- RTT granularity: run-level summaries

Historical board-to-host matrix:

- result directory: `results/experiments/20260712_b2h_net37`
- source commit in manifests: `4837a369bad28dc8b84e495f8cba22d6c556a1fd`
- board IP: `10.37.12.107`
- direction: board-to-host ingress `tc gact random` only
- repetitions: 30 accepted runs per QoS/loss cell
- RTT granularity: run-level summaries

Current board-to-host per-message RTT matrix:

- result directory: `results/experiments/20260712_rtt_samples_b2h_net219_v2`
- source commit in every manifest:
  `d7f8ab446240e93b8b05a27816313f1338c2a629`
- board IP: `10.219.224.107`
- host IP: `10.219.224.195`
- direction: board-to-host ingress `tc gact random` only
- loss levels: 0, 1, 5, 10, and 15 percent
- repetitions: 30 accepted runs per QoS/loss cell, 300 total runs
- per-message RTT samples: 11,054 total
- Best Effort firmware SHA-256:
  `4ad1d876df0b459111905a365804f3572b1e504dcd26d4470b67f8cd3ab3a370`
- Reliable firmware SHA-256:
  `76f797528786683ffe9f1e16c734b39cb4bcdfc086cbc8db03695bfb244491d0`

## Validation Status

The current board-to-host matrix passes the following checks:

- `audit_round4_result_set.py --direction board_to_host` reports
  `PASS: 10 conditions, 30 rows each`.
- Every main CSV has 30 rows.
- For every cell, `_rtt_samples.csv` row count equals the sum of `rtt_count`
  in the corresponding main CSV.
- Every manifest records the same source commit and the expected QoS-specific
  firmware SHA-256.
- `summarize_round4.py` generated run-level condition and independent-group
  bootstrap effect tables.
- `summarize_round4_rtt_samples.py` generated per-message RTT mean, median,
  p95, and p99 run-cluster bootstrap intervals plus Reliable-minus-Best-Effort
  effect intervals. Runs are resampled as clusters with messages kept inside
  their originating run.
- `plot_round4_transport.py` generated delivery, RTT, and QoS-effect figures.
- Ten final PCAP SHA-256 values match
  `TRANSPORT_INGRESS_GACT_LEDGER.md`.
- `summarize_rtps_pcap.py` and `analyze_rtps_timeline.py` generated matched
  RTPS capture and packet-level timeline summaries for all ten cells.
- `reconstruct_rtps_app_samples.py` isolated the application writer/reader
  entity IDs, separated 30 GUID-delimited runs in every capture, and generated
  per-run DATA sequence, ACKNACK request, HEARTBEAT, and NACK-to-DATA link
  artifacts.

The exact Reliable matrix binary was not retained as an immutable file. Its
manifest SHA-256 is `76f797528786683ffe9f1e16c734b39cb4bcdfc086cbc8db03695bfb244491d0`,
but the manifest path `workspace/qos_eval/build/qos_eval.bin` was overwritten by
the subsequent Best Effort build. A detached `d7f8ab4` rebuild matched the
recorded app version, compile time, source configuration, and remote IP but did
not reproduce the original SHA-256. This is an artifact-retention gap.

A source-equivalent 22-assertion hardware verification was attempted and
archived in `results/experiments/20260713_instrumented_verify_d7f8ab4`. It
returned 8 PASS and 14 FAIL because the prerequisite ESP32/ROS 2 endpoint
discovery gate failed (`publisher=no subscriber=no wait=70000ms`). The
downstream behavior checks therefore did not execute. This attempt is neither
an exact-binary verification nor evidence of 14 independent QoS regressions.

## Current Interpretation

The host-to-board result does not support a broad claim that Reliable improves
delivery over Best Effort. Delivery effects are small and the bootstrap
confidence intervals cross zero at all injected-loss levels.

The current board-to-host matrix shows a stronger asymmetry. Reliable-minus-
Best-Effort delivery differences are -1.583, -1.417, -3.000, and -6.417
percentage points at 1, 5, 10, and 15 percent loss. Only the 15 percent interval
excludes zero: -6.417 percentage points, 95 percent CI [-11.333, -1.667].
This does not support a broad delivery advantage for Reliable.

Reliable has substantially higher run-level mean RTT under nonzero
board-to-host loss. Reliable-minus-Best-Effort differences are 232.727,
478.336, 916.022, and 1205.655 ms at 1, 5, 10, and 15 percent loss; all four
bootstrap intervals are above zero. At 0 percent, the 0.792 ms difference has
a confidence interval that crosses zero.

The per-message analysis exposes the tail shape. At 15 percent loss, Reliable
has 932 samples with median 551.477 ms, p95 4796.700 ms, and p99 5833.193 ms.
Best Effort has 1009 samples with median 17.053 ms, p95 31.747 ms, and p99
105.674 ms. The Reliable-minus-Best-Effort p95 difference is 4764.953 ms,
with a run-cluster bootstrap 95 percent CI [3458.286, 5071.694].

Reliable p95 is also higher at 1, 5, and 10 percent. The corresponding
differences and 95 percent CIs are 2294.141 [1.642, 2640.703], 2730.941
[2063.270, 3059.703], and 2967.935 [2648.872, 3303.455] ms. The 1 percent
result is boundary-level evidence because its lower interval endpoint is close
to zero; the 5 through 15 percent intervals are much more stable. At 0 percent,
Reliable p95 is lower by 5.544 ms, 95 percent CI [-9.616, -2.440].

The application-entity reconstruction identifies board writer
`0x000001:0x03` and host reader `0x000012:0x04` for `/qos_eval`. Best Effort
has zero repeated application DATA sequence observations at every loss level.
For Reliable, unique sequences with DATA observed both before and after a
matching ACKNACK request increase from 0 at zero loss to 7, 32, 53, and 67 at
1, 5, 10, and 15 percent loss. At 15 percent, 71 requested-sequence links have
a later same-sequence DATA observation, with median NACK-to-DATA delay
39.524 ms. The board application writer HEARTBEAT interval has a run-median
near 4000 ms.

At the independent-run level, the number of Reliable runs with at least one
sequence observed both before and after its ACKNACK request is 0, 6, 19, 26,
and 29 out of 30 at 0, 1, 5, 10, and 15 percent loss.

These are wire-level sequence observations, not proof that the first packet
was delivered or that writer-history eviction caused an unmatched request.
Ingress capture can observe a packet before `tc` drops it. A specific internal
RTPS mechanism therefore remains a hypothesis pending controlled intervention
or direct writer-history state evidence.

The defensible paper claim is narrow: in this ESP32/mROS2 and ROS 2 testbed,
board-to-host ingress impairment produced a Reliable latency-tail penalty
without a measured delivery advantage, and the effect differed from the
host-to-board impairment result. This is a testbed observation, not a general
DDS reliability theorem.

## Remaining Gaps Before A Top-Tier Submission

1. Restore board/host discovery in a clean network window and rerun the
   22-assertion suite. Exact-binary verification of the existing matrix is no
   longer possible because the original binary was not retained; report the
   replacement explicitly as source-equivalent verification.
2. Extend the application-entity reconstruction with writer-history state or
   controlled intervention before attributing unmatched ACKNACK requests or
   the RTT tail to history eviction, heartbeat timing, or head-of-line
   blocking.
3. Test pre-registered mechanism interventions, such as writer history depth
   and heartbeat period, only after confirming that the implementation exposes
   and records those controls.
4. Repeat at least the 0, 5, and 15 percent cells in an independent network
   window or physical environment.
5. Rerun host-to-board cells with per-message RTT if the paper compares tail
   distributions across directions.
6. Add a semantically aligned external baseline before making comparative
   claims about mROS2 versus another ROS 2/DDS implementation.
