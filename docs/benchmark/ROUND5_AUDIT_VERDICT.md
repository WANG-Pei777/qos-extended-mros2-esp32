# 第五轮审计意见书 (2026-07-13)

**审计对象**: ROUND4 传输矩阵、逐消息 RTT 插桩、PCAP/RTPS 证据链  
**核验方式**: 原始 CSV、sidecar、manifest、固件 SHA-256 与 PCAP SHA-256 逐项核对

## 当前裁定

1. 当前 `20260712_rtt_samples_b2h_net219_v2` 是完整的 board-to-host
   逐消息 RTT 矩阵，不再只是 15% 关键格。10 个条件均为 N=30，共 300 个
   accepted runs 和 11,054 条 RTT 样本。
2. 完整矩阵审计通过。所有单元来自提交
   `d7f8ab446240e93b8b05a27816313f1338c2a629`，同一 QoS 下固件哈希一致，
   主 CSV 的 `rtt_count` 与 sidecar 行数逐格相等。
3. 10 个最终 PCAP 的 SHA-256 与账本一致，RTPS capture summary 和 packet-level
   timeline 已生成。该证据证明线上出现了 DATA、HEARTBEAT 和 ACKNACK，但尚不能
   证明某个具体应用样本发生了何种重传。
4. 数据可以支撑限定范围的论文结果，但尚不能据此宣称“达到顶会发表标准”。
   机制归因、独立重复、插桩固件全套验证和外部基线仍是实质缺口。

## 可支持的结果

- board-to-host 非零丢包下，Reliable 的 run-level mean RTT 显著高于 Best
  Effort。1%、5%、10%、15% 的差值分别为 232.727、478.336、916.022、
  1205.655 ms，四个 bootstrap 95% CI 均高于 0。
- 15% 丢包下，Reliable delivery 比 Best Effort 低 6.417 个百分点，
  95% CI 为 [-11.333, -1.667]。1%、5%、10% 的 delivery 差值区间仍跨 0。
- 15% 丢包下，Reliable 的逐消息 RTT 中位数/p95/p99 为
  551.477/4796.700/5833.193 ms；Best Effort 为
  17.053/31.747/105.674 ms。
- 逐消息 tail 已采用 run-cluster bootstrap:每次重采样 run，并保留 run 内全部
  message。15% 下 p95 差值为 4764.953 ms，95% CI
  [3458.286, 5071.694]。1%、5%、10% 下 p95 差值区间也高于 0，但 1% 下界
  仅 1.642 ms，应作为边界性证据表述。

## 机制假说

writer history depth、heartbeat period、队头阻塞或重试流量都可能参与形成
Reliable 长尾，但当前证据无法区分这些解释。`KEEP_LAST(5) × 4 s heartbeat`
只能作为待检验假说，不能写入结论。只有在完成实体隔离的 sample timeline 和
预注册参数干预后，才能进行机制归因。

## 下一阶段优先级

P0 统计任务已完成:固定种子 `20260711`、10,000 次 run-cluster bootstrap、
单元测试和 QoS tail difference 产物均已生成。

| 优先级 | 任务 | 通过标准 |
| --- | --- | --- |
| P1 | 对当前插桩固件运行并归档 22 项 verify | exact binary/config 可追溯，22 项结果全部有日志 |
| P2 | 按应用 writer/reader entity 重建 RTPS sample timeline | 能把 sequence、HEARTBEAT、ACKNACK bitmap 与重发 DATA 对齐 |
| P3 | 预注册 HISTORY depth × heartbeat 参数实验 | 配置真实生效并进入 manifest；随机化/交错执行；主终点事先冻结 |
| P4 | 在独立网络窗口重复 0%、5%、15% | 效应方向与 tail 结论可复现 |
| P5 | 加入语义对齐的外部实现基线 | 消息大小、频率、QoS、硬件、丢包方向和统计单位一致 |

## 发表边界

当前最强且诚实的表述是：在记录的 ESP32/mROS2 与 ROS 2 测试床中，
board-to-host ingress impairment 使 Reliable 出现显著的 run-level latency
penalty 和 run-cluster bootstrap 支持的 p95 重尾，同时没有测得 delivery
优势；该现象与 host-to-board
方向不同。不得外推为 DDS 普遍规律，也不得在 sample-level RTPS 重建前断言
具体重传机制。
