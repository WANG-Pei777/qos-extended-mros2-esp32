# 实施方案总纲 (Master Experiment Plan)

**版本** 1.1 · 2026-07-15 · 面向顶会投稿
**状态** 历史实验规划，已被正式结果取代。当前论文主张、统计结果和禁止外推边界
以 `docs/papers/CLAIM_EVIDENCE_MATRIX.md`、`docs/papers/EVALUATION_DRAFT.md` 及
三个 `*_FORMAL_RESULTS.md` 为准。本文后续实验清单保留用于追溯规划演变，不能再
作为结果或论文 claim 的权威来源。

---

## 1. 研究定位与主张 (Claims)

**一句话主张:** 在资源受限 MCU 上，agent-less embedded RTPS 可以实现并验证
选定的 DDS QoS 语义；但 QoS 名称本身不能预测应用结果。在定向丢包下，RELIABLE
产生秒级 RTT 尾延迟且没有交付率优势，该结果在新时间/网络窗口复现，而随机化机制
实验表明 heartbeat timing 是有效控制，增加 history depth 在本工作负载下不受支持。

四条可辩护的贡献(每条都必须有实测+统计支撑,不许用"最快/最好"这类措辞):

| # | 贡献 | 支撑实验 | 对照 |
|---|------|----------|------|
| C1 | 选定 QoS 语义的结构化 agent-less 实现与分级真机证据 | QoS evidence matrix | upstream/current path |
| C2 | RELIABLE 在定向丢包下的秒级 RTT 尾延迟代价及 P4 独立窗口复现 | P4, Round 4 | BEST_EFFORT |
| C3 | heartbeat period 的随机化机制干预有效，history depth 效应不受支持 | Round 6 | 250/1000/4000 ms; depth 5/10/20/40 |
| C4 | 三系统展示架构权衡：无显著 RTT 胜者，持续 Agent 条件下 micro-ROS ready 更快 | three-system formal | upstream, micro-ROS |

> ⚠️ 措辞纪律:实验目标一律写成"表征/量化/比较",不写"证明我们最快"。
> 结论让数据说;确认偏误是系统类论文被拒的高频原因。

---

## 2. 三系统对照矩阵(已就位)

| 系统 | 架构 | QoS | 代码位置 | bench app |
|------|------|-----|----------|-----------|
| **mROS2-QoS**(本项目) | ESP32 ⇄ ROS2 直连 RTPS | 7 类 | `workspace/qos_eval` | 已就绪 |
| **upstream mros2-esp32** | ESP32 ⇄ ROS2 直连 RTPS | 固定 BEST_EFFORT | `~/upstream_bench/mros2-esp32` | `echoreply_string`(已改) |
| **micro-ROS** | ESP32 → Agent → ROS2 | 完整(经 agent) | `~/microros_bench/...` | `int32_publisher`(已改为 string-echo) |

硬件/环境: ESP32-S3 单块(同一块板串行测试)、ROS2 Humble on WSL2 mirrored、
同一 WiFi AP。三系统**同板同环境同负载**是公平性的前提。

---

## 3. 方法学修订(相对已有文档的 8 项纠正)

| # | 已有文档的做法 | 问题 | 本方案的做法 |
|---|----------------|------|--------------|
| M1 | 目标"证明你最快" | 确认偏误 | 中性表征;结论由数据+CI 决定 |
| M2 | RTT 用 Wireshark delta time | 测的是网络包间隔,非应用往返 | **RTT 用板上 `esp_timer` 时间戳**(echo 回带 `T:<us>`,三系统统一);Wireshark 只用于网络开销/协议分析 |
| M3 | Python `rclpy` echo 做对端 | 把 rclpy 处理时延计入 RTT | **C++ echo 对端**(见 §5.3);Python 版仅作冒烟 |
| M4 | 干净网络下比 RELIABLE vs BEST_EFFORT | 无丢包时送达率都是 100%,对比无意义 | **引入受控丢包**(§5.4),这是 RELIABLE 价值的唯一显现条件 |
| M5 | 无统计规范 | N=1/40 单次,无 CI | **每条件 N≥30 run,报均值±95%CI,箱线图/CDF**,记录 RSSI/信道 |
| M6 | Flow Graph 选 "TCP Flows" | RTPS 是 UDP,选错抓不到 | Flow Graph 用 **"All Flows / UDP"**;§9 修正全部 Wireshark 步骤 |
| M7 | 独立扫 SPDP 周期与租约 | 二者耦合,独立扫无洞察且翻倍工时 | 扫**比值**"公告次数/租约"(§7.2 E7) |
| M8 | 含主题名长度/优先级等低价值扫频 | 洞察/工时比极低,部分测不出差异 | **砍掉**(§7.3),工时投给 E2/E3/统计 |

---

## 4. 前置条件 (Gate,全部完成才进采集战役)

- [x] **G1 改名冻结**: `step7_full_qos → qos_eval`(2026-07-07 完成)
- [ ] **G2 改名真机复验**: 22 项 verify PASS(改名后被打断,**待补**)
- [ ] **G3 打 tag**: `v0.3-experiment-freeze`,此后配置冻结,否则所有图作废重跑
- [ ] **G4 内存预算**: 见 §6,确定各扫频参数的安全上限
- [ ] **G5 C++ echo 对端**: §5.3,替代 rclpy
- [ ] **G6 丢包注入通道**: §5.4,先验证 WSL mirrored 下是否生效
- [ ] **G7 采集 harness**: §5.2,自动 重烧→复位→N 采样→CSV

---

## 5. 关键基础设施

### 5.1 测量量与统一口径

| 量 | 定义 | 采集来源 | 单位 |
|----|------|----------|------|
| RTT | 板上发出到收到 echo 的 `esp_timer` 差 | 串口 `RTT_*` 行 | µs |
| 匹配延迟 | 复位到 pub&sub 双向 matched | 串口 `Match state wait=` | ms |
| 送达率 | RX/TX(定窗) | 串口计数 | % |
| 恢复成功率 | 复位后 N 次内成功匹配比例 | harness 判定 | % |
| Flash | `idf.py size` | 构建产物 | B |
| Free heap | 运行时 `esp_get_free_heap_size` | 串口 `Memory:` | B |
| 每样本包数/字节 | tshark 统计 ÷ 交付样本数 | pcap | 计数 |

### 5.2 采集 harness(待建 `scripts/experiment/`)

- `run_matrix.sh <system> <condition> <N>` — 循环 N 次: 复位板 → 采 RTT/匹配/送达 → 追加 CSV
- `sweep_param.sh <param> <values...>` — 每值: 改 config.h → 重烧 → 调 run_matrix → 汇总
- `capture_wire.sh <label> <seconds>` — dumpcap 抓 eth1(pcap 供手动 Wireshark 分析)
- 输出: `results/experiments/<date>/<system>_<condition>.csv`(每行一次 run)
- 复用现成: `reset_and_log.py`(复位+采串口)、`qos_host.sh`(echo 主机)

### 5.3 C++ echo 对端(待建)

ROS2 Humble C++ 节点,订阅 `qos_eval`、原样回发 `qos_eval_reply`,RELIABLE/BEST_EFFORT
两套 QoS profile 可选。目的: 从 RTT 中剔除 rclpy 的不确定处理时延。放
`tools/echo_cpp/`(独立 colcon 包)。

### 5.4 受控丢包注入(待建 + 待验证)

RELIABLE 的价值只有在丢包下显现。三种方案按优先级:

1. **`tc netem` / `iptables -m statistic`** 在 WSL(最标准)。**风险**: mirrored networking
   下 WSL netfilter 可能不拦截 WiFi 流量 → **G6 先用一条规则验证是否生效**。
2. 若无效: **echo 主机应用层双向概率丢弃**(确定生效,作为受控代理),在 threats to
   validity 说明它注入在中间节点而非链路。
3. 丢包率档位: 0 / 1 / 5 / 10 / 20 %。

---

## 6. 内存预算(G4,防止 32 writer 之类白烧)

ESP32-S3 实测 free heap ≈ 202 KB。RTPS 线程栈堆用量(config.h):
`OVERALL_HEAP = (POOL_W·4096)+(POOL_R·4096)+(PARTS·SPDP_STACK 4096)+(NUM_SF_WRITERS·HB_STACK 4096)`

当前(8 writer): ≈ 45 KB。**关键: `NUM_STATEFUL_WRITERS` 每+1 加 4 KB 栈。**

| 参数 | 纸面风险 | 处理 |
|------|----------|------|
| `NUM_STATEFUL_WRITERS=32` | 仅心跳栈 128 KB,叠加大概率 OOM/不启动 | **上限先设 16,实测 free heap 再决定 32 是否可测** |
| `HISTORY_SIZE_STATEFUL=50` | cache = 深度×端点×消息;需实测 | 每档记录 free heap,OOM 即为该维度上界(本身是结果) |
| 其余 | 低 | 见 §7 |

方法: 每个扫频值烧录后读串口 `Memory:` free heap,**内存耗尽点本身是可报告的可扩展性包络**。

---

## 7. 实验分层

### 7.1 P0 核心(论文必须有,先做)

| ID | 实验 | 自变量 | 因变量(y) | 固定量 | N | 成功判据 | 工件 |
|----|------|--------|-----------|--------|---|----------|------|
| **E1** | 三系统 RTT | 系统∈{mQoS,up,µROS} | RTT 分布 | 500ms/String/同AP | 30 | 出 CI 不重叠或重叠的明确结论 | 箱线图+CDF+表 |
| **E2** | 丢包下 RELIABLE 价值 | 丢包率×{RELIABLE,BEST_EFFORT} | 送达率, 有效RTT | 同上 | 30 | RELIABLE 送达率随丢包保持高、BE 下降 | 送达率-丢包曲线 |
| **E3** | 复位风暴(可靠性) | {修复前,修复后}×复位次数 | 匹配成功率,恢复时间 | echo常驻 | 30 | 修复后成功率↑显著(已初见 8/8 vs 5/7) | 成功率柱+恢复CDF |
| **E4** | 资源占用 | 系统 | Flash, free heap | — | 3(确定性) | 量化 +5.6% flash 等 | 表 |
| **E5** | 网络开销 | 系统 | 每样本包数/字节 | 同负载 | 3×pcap | 量化 agent 三跳开销 | 表+Flow Graph |

### 7.2 P1 扩展(参数扫频,P0 完成后做)

| ID | 实验 | 自变量 | y | 备注 |
|----|------|--------|---|------|
| **E6** | 心跳周期×丢包 **权衡** | HB∈{100,500,1000,2000,4000,8000}ms × 丢包{0,5,10}% | 丢包恢复延迟 vs HB 包开销 | 干净网下无信息,必须配丢包;这是核心权衡曲线 |
| **E7** | SPDP/租约 **比值** | 比值 announce/lease∈{1.2,3,5,12} | 冷/热匹配延迟, 误判离线率 | 取代独立扫 SPDP+租约(M7) |
| **E8** | 历史深度 | `HISTORY_SIZE_STATEFUL`∈{3,5,10,20,(50 视 §6)} | 突发保留正确性, free heap | 需突发负载(高频发布) |
| **E9** | 队列过载 | `THREAD_POOL_WORKLOAD_QUEUE_LENGTH`∈{10,20,50,100,200} | 过载丢弃率 | 需突发过载负载才有意义 |

### 7.3 明确砍掉(理由存档,防止反复)

| 砍掉项 | 理由 |
|--------|------|
| 主题名长度扫频 | 编译期缓冲区;SEDP 按实际长度传,测不出差异。论文一句话带过 |
| 代理数量扫频 | 仅多对端有影响,本实验单对端 → 改为 §6 RAM 静态表 |
| 线程优先级扫频 | 与 WiFi 任务优先级耦合,难控变量,洞察/工时比最低 |
| 线程池大小独立实验 | 折入 E9/饱和吞吐顺带观测 |
| 读写者数量独立扫频 | 改为"可扩展性包络"= §6 内存表 + 实测最大端点数 |

---

## 8. 统计与可复现规范(每次投稿都被查)

- 每条件 **N≥30** 独立 run;报 **均值 ± 95% CI**(t 分布);RTT 另给**箱线图/CDF**,不要只给均值。
- **条件交错执行**(A,B,C,A,B,C… 而非 AAA…BBB),抵消 WiFi 漂移。
- 每 run 记录 **RSSI + 信道 + 时间戳**;WiFi 环境写入 threats to validity。
- 固件版本 = 冻结 tag 的 commit hash,写进每个 CSV 头。
- 异常 run(如 E3 未匹配)**保留并计入**,不得静默丢弃。
- 原始 CSV + pcap 归档;pcap 含内网 IP,发布前脱敏(见 `docs/figures/README.md` 约定)。

---

## 9. 职责边界:自动化采集 vs 手动出图(正式约定)

**原则**:重复、需精确计时、易出错的机械采集 → 自动化脚本;需要人判断、
用于论文最终呈现的**证据图与协议图** → 作者手动用 Wireshark GUI。二者边界固化如下,
不再混淆。此约定同时作为论文 **artifact / reproducibility 说明**的一部分。

| 环节 | 归属 | 工具 | 产物 |
|------|------|------|------|
| 固件重烧 / 复位 / N 次采样 | **自动化** | harness(§5.2) | 原始 CSV |
| RTT / 送达率 / 匹配延迟 统计量 | **自动化** | 脚本 | CSV |
| 原始 pcap 采集 | **自动化** | `dumpcap`(Wireshark 套件) | pcap → 喂给手动分析 |
| 定量统计图(箱线 / CDF / 权衡曲线) | 脚本生成 **+ 作者审校** | matplotlib(从归档 CSV) | 论文定量图 |
| **协议时序 Flow Graph** | **作者手动** | Wireshark GUI | 论文协议图 |
| **RELIABLE/BEST_EFFORT 的 HEARTBEAT/ACKNACK 证据** | **作者手动** | Wireshark I/O 图 | 论文证据图 |
| **micro-ROS 三跳架构可视化** | **作者手动** | Wireshark Flow Graph | 论文架构图 |
| **TRANSIENT_LOCAL 历史重传证据** | **作者手动** | Wireshark 包列表截图 | 论文证据图 |

**关键约定(写入论文):**

1. **最终进入论文的 Wireshark 证据图与协议图,一律由作者手动从原始 pcap 用
   Wireshark GUI 生成并导出/截图,不经任何自动化脚本。** 目的:保证这些图是标准
   分析工具的原生产物,审稿人可用同一 pcap + 同一工具独立复现,不依赖本项目脚本。
2. 定量统计图(RTT 分布、送达率-丢包曲线等)由脚本从归档 CSV 生成,但**数值口径、
   坐标、结论由作者逐张审校确认**后方可入稿;脚本只是绘制,不做结论判断。
3. 自动化的职责止于"把原始数据和 pcap 可靠、可复现地采集出来";**最终图的呈现与
   判断归作者**。`docs/figures/` 下已有的机制图(发现握手/死锁/心跳)属于第 2 类
   (脚本生成 + 已审校),而本次实验的**证据图/协议图属于第 1 类(全手动)**。

### Wireshark 手动分析清单(修正版)

| 任务 | 修正要点 vs 已有文档 | 产物 |
|------|----------------------|------|
| A1 RELIABLE vs BEST_EFFORT | 过滤器 `rtps.sm.id==0x07/0x06`;I/O 图配置已预置在 Wireshark(`io_graphs`) | 两张对比图 |
| A2 Flow Graph 协议时序 | **Flow type 选 "All Flows",不是 TCP Flows**(RTPS=UDP);先用显示过滤器限时窗 | 三系统时序图 |
| A3 三跳可视化 | micro-ROS pcap 的 Flow Graph 显示 ESP32→Agent→Host | 架构对比图 |
| A4 网络开销统计 | `统计→协议分级`;每样本包数由脚本算,Wireshark 交叉验证 | 表 |
| A5 TRANSIENT_LOCAL | 晚加入订阅者后看 HEARTBEAT+历史 DATA 重传序列号 | 证据截图 |

> RTT 分布**不**用 Wireshark 测(M2);delta-time 列仅用于交叉核对网络抖动。

---

## 10. 执行时间线(诚实估算)

| 阶段 | 内容 | 估时 |
|------|------|------|
| 冻结 | G2 复验 + G3 tag | 0.5 h |
| 基建 | G4 内存预算 + G5 C++echo + G6 丢包验证 + G7 harness | 1–1.5 天 |
| P0 战役 | E1–E5,N=30,条件交错(挂夜跑) | 1–2 天(多为机时) |
| P1 战役 | E6–E9(E6/E8 含重烧,最耗时) | 2–3 天 |
| 分析出图 | 脚本出定量图 + 你手动 Wireshark 出证据图 | 1–2 天 |

单参数扫频机时示例: 6 值 × N30 × ~75s + 重烧 ≈ 4–5 h/参数 → **采集必须自动化**,
手动不可行。

---

## 11. 风险登记

| 风险 | 影响 | 缓解 |
|------|------|------|
| WSL mirrored 下丢包注入无效 | E2/E6 无法做 | G6 先验证;备选应用层丢弃(§5.4) |
| 大端点数 OOM | E8/扩展白烧 | §6 先纸面预算,上限保守 |
| WiFi 环境漂移 | RTT 方差大 | 条件交错 + 记 RSSI + 夜间低干扰时段 |
| micro-ROS agent 状态残留影响 E3 | 复位语义不对等 | E3 主结论用 mQoS 修复前后;µROS 单列讨论 |
| 改名后回归 | 全套失效 | G2 必须先过再冻结 |

---

## 12. 实验→论文图表映射

| 论文素材 | 来源实验 | 类型 |
|----------|----------|------|
| Fig. RTT 分布 | E1 | 箱线图/CDF(脚本) |
| Fig. RELIABLE 价值 | E2 | 送达率-丢包曲线(脚本) |
| Fig. 可靠性修复 | E3 | 成功率柱+已做的死锁 pcap 图 |
| Fig. 心跳权衡 | E6 | 恢复延迟 vs 开销(脚本) |
| Fig. 协议时序/三跳 | E5,A2,A3 | Wireshark Flow Graph(手动) |
| Fig. 发现握手 | 已完成 | `docs/figures/fig_discovery_*`(脚本) |
| Table 资源/开销 | E4,E5 | 表 |

---

## 13. 立即下一步

1. **G2**: 跑改名后 22 项 verify(被打断,需重跑确认冻结安全)
2. **G3**: 打 `v0.3-experiment-freeze` tag
3. **G4**: 内存预算(烧几个 `NUM_STATEFUL_WRITERS`/`HISTORY_SIZE` 值读 free heap 定上限)
4. 然后进 §5 基建(C++ echo + 丢包验证 + harness)

> 本方案经顶会标准审查(见 §3 修订)。P0 五个实验是最小可发表集;P1 增强深度;
> §7.3 砍掉项不再讨论。
