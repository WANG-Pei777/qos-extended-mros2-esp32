# ROUND4 Claim-to-Evidence Table

This table maps paper-facing claims to the exact evidence currently available.
It is intentionally conservative: claims are directional and tied to the
recorded ESP32/ROS 2 testbed, firmware binaries, network window, and impairment
mechanism.

## Evidence Sets

| Evidence set | Direction | Result directory | Source commit in manifests | N per cell |
| --- | --- | --- | --- | ---: |
| ROUND4-H2B-net37 | host-to-board netem | `results/experiments/20260711_net37` | `64e7ec710b3342b838b9561ec5808e882c082efe` | 30 |
| ROUND4-B2H-net37 | board-to-host ingress gact | `results/experiments/20260712_b2h_net37` | `4837a369bad28dc8b84e495f8cba22d6c556a1fd` | 30 |

## Claims

| Claim ID | Paper-facing claim | Current status | Primary evidence | Guardrail |
| --- | --- | --- | --- | --- |
| C1 | In the host-to-board impairment direction, Reliable does not provide a broad delivery advantage over Best Effort. | Supported narrowly | `20260711_net37/analysis/round4_transport_qos_effects.csv`; `20260711_net37/analysis/figures/round4_qos_effects.svg`; full-set audit with `audit_round4_result_set.py` | Do not generalize to all DDS, all networks, or bidirectional impairment. |
| C2 | In the host-to-board direction, both QoS modes deliver 100 percent at 0 percent injected loss in this setup. | Supported | `20260711_net37/analysis/round4_transport_summary.csv`; raw 0 percent CSVs and manifests | This is a baseline sanity result, not a reliability theorem. |
| C3 | In the board-to-host impairment direction, Reliable exhibits substantially higher RTT tails than Best Effort at nonzero loss. | Supported narrowly | `20260712_b2h_net37/analysis/round4_transport_summary.csv`; `20260712_b2h_net37/analysis/round4_transport_qos_effects.csv`; RTT figure SVG | Existing formal p95 is p95 of per-run RTT means. Per-message RTT instrumentation exists now, but these cells need rerun before using p95/p99 message-tail claims. |
| C4 | In the board-to-host direction, Best Effort RTT remains near 20 ms through 15 percent ingress loss while delivery declines with loss. | Supported narrowly | `20260712_b2h_net37/analysis/round4_transport_summary.csv`; delivery and RTT figures | Do not imply loss-free delivery; delivery falls from 100 percent to about 86 percent at 15 percent. |
| C5 | Direction matters: host-to-board and board-to-host impairment produce qualitatively different Reliable/Best Effort tradeoffs. | Supported as an observation | Both summary/effect CSVs; both figure sets; both result-set audits | Treat as a testbed observation until independently repeated. |
| C6 | RTPS wire traffic was captured and packet-level timeline evidence was extracted for every formal condition in both directions. | Supported | `round4_rtps_capture_summary.csv` and `round4_rtps_timeline_evidence.csv` in both analysis directories; pcap ledger files; pcap SHA-256 hashes | Timeline evidence includes discovery/control traffic and does not by itself prove application-sample retransmission. |
| C7 | Reliable improves reliability under packet loss. | Not supported as a broad claim | H2B confidence intervals cross zero; B2H Reliable delivery is lower than Best Effort at 5 percent and 15 percent | Avoid this claim unless narrowed and backed by additional protocol analysis. |
| C8 | The measured high RTT under Reliable is caused by a specific RTPS mechanism. | Not yet supported | Timeline summaries expose direction, ACKNACK bitmap presence, and RTPS counters, but not yet application-sample reconstruction | Requires deeper pcap inspection: application writer/reader entity isolation, sequence-number timelines, ACKNACK bitmaps, HEARTBEAT timing, retransmission evidence. |

## Required Citations Within The Repository

| Artifact type | Host-to-board | Board-to-host |
| --- | --- | --- |
| Raw CSVs | `results/experiments/20260711_net37/mros2qos_round4_transport_*pct.csv` | `results/experiments/20260712_b2h_net37/mros2qos_round4_transport_*pct_board_to_host.csv` |
| Manifests | `results/experiments/20260711_net37/*_manifest.json` | `results/experiments/20260712_b2h_net37/*_manifest.json` |
| Summary tables | `results/experiments/20260711_net37/analysis/round4_transport_summary.csv` | `results/experiments/20260712_b2h_net37/analysis/round4_transport_summary.csv` |
| QoS effects | `results/experiments/20260711_net37/analysis/round4_transport_qos_effects.csv` | `results/experiments/20260712_b2h_net37/analysis/round4_transport_qos_effects.csv` |
| Figures | `results/experiments/20260711_net37/analysis/figures/*.svg` | `results/experiments/20260712_b2h_net37/analysis/figures/*.svg` |
| RTPS summaries | `results/experiments/20260711_net37/analysis/round4_rtps_capture_summary.csv`; `results/experiments/20260711_net37/analysis/round4_rtps_timeline_evidence.csv` | `results/experiments/20260712_b2h_net37/analysis/round4_rtps_capture_summary.csv`; `results/experiments/20260712_b2h_net37/analysis/round4_rtps_timeline_evidence.csv` |
| Audit commands | `scripts/experiment/audit_round4_result_set.py` | `scripts/experiment/audit_round4_result_set.py --direction board_to_host` |

## Next Evidence Upgrades

1. Add per-message RTT export or keep the current RTT-tail language strictly as
   "p95 of per-run RTT means." Export support now exists through
   `_rtt_samples.csv`; rerun key cells before claiming per-message p95/p99.
2. Reconstruct application-sample-level RTPS sequence/ACKNACK/HEARTBEAT
   timelines before attributing latency to retransmission or discovery behavior.
3. Repeat at least the key 0, 5, and 15 percent cells in an independent network
   window to separate testbed effects from environmental effects.
