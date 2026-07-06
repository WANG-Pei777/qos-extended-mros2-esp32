# Phase 1 性能基准报告

**日期:** 2026-06-14  
**平台:** ESP32-S3  
**固件:** step7_full_qos (RELIABLE + VOLATILE + KEEP_LAST(5))

---

## 测试结果

| 指标 | 值 |
|------|-----|
| TX 吞吐量 | 21.1 msg/s |
| RTT 延迟 (Min) | 15.0 ms |
| RTT 延迟 (Avg) | 21.9 ms |
| RTT 延迟 (Max) | 37.2 ms |
| 延迟采样数 | 40 |
| 可用内存 | 202,652 bytes (76.8% of 264KB DRAM) |
| History cache | 5/5 samples, 180 bytes |
| TX 消息总数 | 40 |
| RX 消息总数 | 40 |
| 丢包率 | 0% |

---

## QoS 行为验证

| QoS 策略 | 结果 |
|-----------|------|
| RELIABLE (双向) | ✅ PASS |
| VOLATILE | ✅ PASS |
| KEEP_LAST(5) | ✅ PASS (5/5 cache enforced) |
| Deadline (100ms) | ✅ PASS (missed=1, 正确检测) |
| Lifespan (2000ms) | ✅ PASS (expired/fresh check) |
| Liveliness (AUTOMATIC) | ✅ PASS |
| Resource Limits | ✅ PASS (30 samples, 30 rejected) |

---

## 资源消耗

```
DRAM 总量:     264 KB
可用内存:      202 KB (76.8%)
已用内存:      ~62 KB
RTPS 缓存:     180 bytes (5 samples)
```

---

## 基准数据用途

这些数据作为 Phase 2 (KAN 自适应 QoS) 的 baseline：
- 动态网络下的吞吐量对比
- 延迟优化目标
- 内存预算约束
