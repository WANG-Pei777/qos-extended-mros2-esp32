# Phase 1 Performance Baseline

**Date:** 2026-06-14
**Platform:** ESP32-S3
**Firmware:** step7_full_qos (RELIABLE + VOLATILE + KEEP_LAST(5))

## Results

| Metric | Value |
|--------|-------|
| TX throughput | 21.1 msg/s |
| RTT (min) | 15.0 ms |
| RTT (avg) | 21.9 ms |
| RTT (max) | 37.2 ms |
| RTT samples | 40 |
| Free heap | 202,652 bytes (76.8% of 264 KB DRAM) |
| History cache | 5/5 samples, 180 bytes |
| Messages sent | 40 |
| Messages received | 40 |
| Loss | 0% |

## QoS behavior checks

| QoS policy | Result |
|------------|--------|
| RELIABLE (both directions) | PASS |
| VOLATILE | PASS |
| KEEP_LAST(5) | PASS (cache held at 5/5) |
| Deadline (100 ms) | PASS (missed=1, detected) |
| Lifespan (2000 ms) | PASS (expired/fresh check) |
| Liveliness (AUTOMATIC) | PASS |
| Resource Limits | PASS (30 samples, 30 rejected) |

## Memory

```
DRAM total:     264 KB
Free heap:      202 KB (76.8%)
Used:           ~62 KB
RTPS cache:     180 bytes (5 samples)
```
