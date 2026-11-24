# ROUND4 Claim-to-Evidence Table

This table maps paper-facing claims to exact repository evidence. Claims are
directional and tied to the recorded ESP32/ROS 2 testbed, firmware binaries,
network window, and impairment mechanism.

## Evidence Sets

| Evidence set | Direction and RTT granularity | Result directory | Source commit in manifests | N per cell |
| --- | --- | --- | --- | ---: |
| ROUND4-H2B-net37 | host-to-board netem; run-level RTT | `results/experiments/20260711_net37` | `64e7ec710b3342b838b9561ec5808e882c082efe` | 30 |
| ROUND4-B2H-net37 | board-to-host ingress gact; run-level RTT | `results/experiments/20260712_b2h_net37` | `4837a369bad28dc8b84e495f8cba22d6c556a1fd` | 30 |
| ROUND4-B2H-net219-v2 | board-to-host ingress gact; full per-message RTT matrix | `results/experiments/20260712_rtt_samples_b2h_net219_v2` | `d7f8ab446240e93b8b05a27816313f1338c2a629` | 30 |

## Claims

| Claim ID | Paper-facing claim | Status | Primary evidence | Guardrail |
| --- | --- | --- | --- | --- |
| C1 | Under host-to-board impairment, Reliable does not show a broad delivery advantage over Best Effort. | Supported narrowly | `20260711_net37/analysis/round4_transport_qos_effects.csv`; full-set audit | Do not generalize beyond this testbed or call the impairment bidirectional. |
| C2 | Under board-to-host impairment, Reliable mean RTT is higher than Best Effort at 1, 5, 10, and 15 percent loss. | Supported | `20260712_rtt_samples_b2h_net219_v2/analysis/round4_transport_qos_effects.csv`; run-level bootstrap CIs | The 0 percent RTT difference is not distinguishable from zero. |
| C3 | Under board-to-host impairment, Reliable has a higher per-message RTT p95 than Best Effort at 1, 5, 10, and 15 percent loss. | Supported with run-cluster intervals | `20260712_rtt_samples_b2h_net219_v2/analysis/round4_rtt_message_qos_effects.csv`; matched sidecars | The 1 percent CI lower endpoint is 1.642 ms and should be described as boundary-level evidence; 5 through 15 percent are stronger. |
| C4 | At 15 percent board-to-host loss, Reliable delivery is lower than Best Effort by 6.417 percentage points. | Supported narrowly | `20260712_rtt_samples_b2h_net219_v2/analysis/round4_transport_qos_effects.csv`; 95 percent CI [-11.333, -1.667] | Delivery differences at 1, 5, and 10 percent have intervals crossing zero. |
| C5 | Direction matters: host-to-board and board-to-host impairment produce qualitatively different QoS tradeoffs. | Supported as an observation | Both full-matrix summaries, figures, manifests, and audits | Treat this as testbed-specific until independently repeated. |
| C6 | RTPS wire traffic was captured and application entity sequence evidence was reconstructed for every cell in the current matrix. | Supported | Current `round4_rtps_capture_summary.csv`; `round4_rtps_timeline_evidence.csv`; `round4_rtps_app_reconstruction_summary.csv`; ledger; PCAP hashes | Ingress capture can observe a packet before `tc` drops it; wire observation is not application delivery. |
| C7 | Reliable improves delivery under packet loss. | Not supported as a broad claim | H2B intervals cross zero; current B2H result is nonpositive and significantly negative at 15 percent | Exclude this claim from the paper. |
| C8 | Reliable produces post-ACKNACK same-sequence DATA observations whose frequency increases with injected board-to-host loss. | Supported as wire behavior | `round4_rtps_app_nack_data_links.csv`; `round4_rtps_app_reconstruction_runs.csv` | Do not convert this into a history-eviction, delivery, or causal latency claim without controlled intervention. |

## Current Matrix Artifacts

| Artifact | Path |
| --- | --- |
| Raw run CSVs | `results/experiments/20260712_rtt_samples_b2h_net219_v2/mros2qos_round4_transport_*pct_board_to_host.csv` |
| Per-message sidecars | `results/experiments/20260712_rtt_samples_b2h_net219_v2/*_rtt_samples.csv` |
| Manifests | `results/experiments/20260712_rtt_samples_b2h_net219_v2/*_manifest.json` |
| Run-level summary | `results/experiments/20260712_rtt_samples_b2h_net219_v2/analysis/round4_transport_summary.csv` |
| Run-level QoS effects | `results/experiments/20260712_rtt_samples_b2h_net219_v2/analysis/round4_transport_qos_effects.csv` |
| Per-message RTT summary | `results/experiments/20260712_rtt_samples_b2h_net219_v2/analysis/round4_rtt_message_summary.csv` |
| Per-message QoS effects | `results/experiments/20260712_rtt_samples_b2h_net219_v2/analysis/round4_rtt_message_qos_effects.csv` |
| Figures | `results/experiments/20260712_rtt_samples_b2h_net219_v2/analysis/figures/*` |
| RTPS capture summary | `results/experiments/20260712_rtt_samples_b2h_net219_v2/analysis/round4_rtps_capture_summary.csv` |
| RTPS timeline summary | `results/experiments/20260712_rtt_samples_b2h_net219_v2/analysis/round4_rtps_timeline_evidence.csv` |
| Application RTPS run reconstruction | `results/experiments/20260712_rtt_samples_b2h_net219_v2/analysis/round4_rtps_app_reconstruction_runs.csv` |
| Application ACKNACK-to-DATA links | `results/experiments/20260712_rtt_samples_b2h_net219_v2/analysis/round4_rtps_app_nack_data_links.csv` |
| Application RTPS condition summary | `results/experiments/20260712_rtt_samples_b2h_net219_v2/analysis/round4_rtps_app_reconstruction_summary.csv` |
| Capture ledger | `results/experiments/20260712_rtt_samples_b2h_net219_v2/TRANSPORT_INGRESS_GACT_LEDGER.md` |
| Full-set audit | `scripts/experiment/audit_round4_result_set.py --direction board_to_host` |
| Source-equivalent verification attempt | `results/experiments/20260713_instrumented_verify_d7f8ab4/verification_manifest.json` |

## Next Evidence Upgrades

1. Resolve the current endpoint-discovery gate and pass the 22-assertion suite
   on a clearly labeled source-equivalent rebuild. The original exact matrix
   binary cannot be recovered from its overwritten build path.
2. Add writer-history state or a controlled parameter intervention before
   testing a named mechanism.
3. Repeat pre-registered key cells in an independent environment.
4. Add a semantically aligned external implementation baseline.
