# micro-ROS Baseline Comparison Protocol (design — not yet executed)

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

## Status

- [ ] micro-ROS firmware built for ESP32-S3 (not yet — needs `micro_ros_espidf_component`)
- [ ] Agent installed on host
- [ ] Identical-payload echo apps written for both stacks
- [ ] Runs executed and analyzed
