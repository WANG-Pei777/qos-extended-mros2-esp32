# Performance Baseline After Reliability Fixes (2026-07-07)

Firmware: `workspace/step7_full_qos`, RELIABLE both directions, VOLATILE, KEEP_LAST(5).
Fixes included: hardware-RNG GUID prefix, 12 s announced SPDP lease, Wi-Fi
reconnect-forever, `WIFI_PS_NONE`. Peer: ROS 2 Humble / FastDDS echo node in WSL2
(mirrored networking), same Wi-Fi AP. Full evidence: 22/22 verification PASS +
8/8 reset-stress (`results/wireshark/stress_20260706_235327/`).

## Results vs previous baseline (2026-06-14)

| Metric | 2026-06-14 | This baseline | Note |
|---|---|---|---|
| DDS RTT min | 15.0 ms | **11.7 ms** | `WIFI_PS_NONE` removes DTIM sleep |
| DDS RTT avg | 21.9 ms | **20.7 ms** | bounded by Python echo host, not ESP32 |
| DDS RTT max | 37.2 ms | 38.3 ms | Wi-Fi jitter dominated |
| RTT samples | 40 | 40 | one run; N≥30 runs still TODO for paper |
| TX throughput | 21.1 msg/s | 21.1 msg/s | application-paced, NOT a transport limit |
| Endpoint match (cold) | ~9–10 s | **8.7 s** | fresh daemon + host |
| Endpoint match (warm re-match) | ~9–10 s | **0.4–0.9 s** | 12 s lease removes ghost interference |
| Reset→match success | 5/7 (~71 %) | **8/8** | discovery deadlock eliminated |
| Idle ICMP loss | 50–66 % | **10 %** | PS_NONE; residual = Wi-Fi environment |
| Free memory | 202,652 B | 202,520 B | no regression (Δ −132 B) |

## Methodology caveats (write these into any paper)

1. **Throughput is application-paced** (fixed publish interval): 21.1 msg/s measures
   the workload, not the stack's capacity. A saturation test (publish as fast as
   possible, sweep payload 16 B–1 KB) is required to claim a throughput number.
2. **RTT includes the peer**: the reply path goes through a Python `rclpy` echo node;
   its processing time is a large, uncontrolled term. For stack-attributable latency,
   use a C++ echo peer or timestamped one-way measurement with synchronized clocks.
3. Single board, single AP, uncontrolled 2.4 GHz channel, N=1 run per condition.
   Paper-grade numbers need N≥30 runs with mean/95 % CI and recorded RSSI/channel.
4. `WIFI_PS_NONE` trades power for latency/reachability — quantify the current draw
   (e.g. with a USB power meter) and report the tradeoff.
