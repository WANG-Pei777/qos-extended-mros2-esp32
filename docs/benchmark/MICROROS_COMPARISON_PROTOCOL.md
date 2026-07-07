# micro-ROS Baseline Comparison Protocol (first execution: 2026-07-07)

Reviewers of any embedded-ROS 2 paper will ask "why not micro-ROS?". This protocol
defines an apples-to-apples comparison on the SAME hardware so the answer is measured,
not argued.

## Systems under test

| | mROS2-QoS (this project) | micro-ROS |
|---|---|---|
| Stack | embeddedRTPS (bare DDS/RTPS over UDP) | Micro XRCE-DDS client → Agent → DDS |
| Peer visibility | native DDS participant | via Agent proxy |
| Board | ESP32-S3 (same unit) | ESP32-S3 (same unit) |
| Transport | Wi-Fi UDP | Wi-Fi UDP |
| Peer host | ROS 2 Humble in WSL2, same AP | same + `micro_ros_agent` |

Key architectural difference to state up front: micro-ROS requires the Agent process;
mROS2 speaks RTPS directly. Discovery latency and Agent overhead are therefore part
of the comparison, not confounds.

## Setup

1. micro-ROS side: `micro_ros_espidf_component` (ESP-IDF v5.x compatible), example
   `int32_publisher` / a custom echo app mirroring `step7_full_qos` topics and QoS
   (RELIABLE / VOLATILE / KEEP_LAST(5), `std_msgs/String` of identical payload size).
2. Host: `micro_ros_agent udp4 --port 8888` in the same WSL2 environment.
3. Identical Wi-Fi AP, channel, and board position; record RSSI per run.

## Metrics (N ≥ 30 runs each, report mean ± 95 % CI)

| Metric | Method |
|---|---|
| Cold-start to first matched pub/sub | serial timestamp from reset to match |
| Warm re-match after reset | reset with peer left running (our stress harness) |
| RTT (echo round trip) | identical C++ echo peer for both systems |
| Saturation throughput | publish min-interval sweep, payload 16 B–1 KB |
| Flash / RAM footprint | `idf.py size` + runtime free heap |
| Reset-storm robustness | 8× consecutive reset→match success rate |
| Wire overhead | tshark on eth1: packets/bytes per delivered sample |

## Existing assets to reuse

- Reset/verify harness: `scripts/validation/qos_verify.sh`, stress harness in
  `results/wireshark/stress_*/` methodology
- Capture + analysis: tshark recipes in `results/wireshark/RTPS_PARAMETER_EXPERIMENT.md`

## First results (2026-07-07, N=1 run each, same board/AP/host/echo node)

Setup that worked: `micro_ros_espidf_component` humble branch builds cleanly on
ESP-IDF v5.1.7 / esp32s3; agent = eProsima `micro-ros-agent` snap. **Gotcha:** the
agent port must lie inside the Windows-firewall-opened UDP range (8888 was silently
blocked by the WSL2 firewall rules; port 7408 works).

Workload parity: string-echo app on the SAME topics (`/step7_full_qos`(_reply)),
same 500 ms period, same 40-sample window, same `echo_reply.py` host
(micro-ROS side: `~/microros_bench/.../examples/int32_publisher/main/main.c`,
original example backed up as `~/microros_bench/int32_main.c.bak`).

| Metric | mROS2-QoS (native RTPS) | micro-ROS (XRCE + agent) |
|---|---|---|
| RTT min / avg / max (40 samples) | **11.7 / 20.7 / 38.3 ms** | 18.0 / 27.5 / 102.5 ms |
| Delivery | 40/40 | 40/40 (80/80 extended) |
| App binary size | **779,920 B** | 789,888 B |
| Cold start to first data | ~11 s (true peer SEDP discovery, 8.7 s match) | ~2.7 s (agent session 28 ms) |
| Warm re-match after reset | **0.4–0.9 s** | not measured |
| Host infrastructure | none (peer-to-peer DDS) | agent process required |

Interpretation for the paper:
- mROS2 wins the data path decisively: −25 % average RTT, −35 % min, and a 63 %
  tighter tail (max 38 vs 103 ms) — consistent with the agent adding a
  serialize-forward hop (ESP32→agent→FastDDS→peer vs ESP32→peer directly).
- micro-ROS wins cold start, but the comparison is semantically asymmetric:
  an XRCE session to a preconfigured agent is not peer discovery. State this
  explicitly; reviewers will otherwise flag it.
- Footprints are within 1.3 % of each other — neither side can claim a
  memory advantage from this measurement alone (RAM footprint still TODO).

## Status

- [x] micro-ROS firmware built for ESP32-S3 (`micro_ros_espidf_component`, humble, IDF v5.1.7)
- [x] Agent installed on host (eProsima snap, UDP port 7408)
- [x] Identical-payload echo app written for micro-ROS; mROS2 side reuses step7
- [x] First runs executed and analyzed (table above)
- [ ] N≥30 repetitions with mean/95 % CI
- [ ] Saturation throughput sweep (payload 16 B–1 KB)
- [ ] RAM footprint and energy comparison
- [ ] micro-ROS reset-storm robustness (8× cycle, agent left running)
