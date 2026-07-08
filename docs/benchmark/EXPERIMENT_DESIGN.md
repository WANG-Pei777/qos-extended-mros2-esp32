# 三系统对比实验设计方案

## 项目核心价值

**证明在导师的 mros2-esp32 基础上添加 QoS 支持的价值：**

1. **性能不降反升**：QoS 扩展后的 RELIABLE 模式比 upstream 的 BEST_EFFORT 更快更稳定
2. **功能显著增强**：从固定 QoS 到支持 7 种 QoS 策略（Reliability/Durability/History/Deadline/Lifespan/Liveliness/Resource Limits）
3. **成本可控**：仅增加 5.6% flash（41KB），运行时性能几乎无损耗
4. **优于官方方案**：比 micro-ROS 更快（-25% avg RTT），无需 Agent，真正的点对点通信

---

## 三系统对比表

| 系统 | 架构 | QoS 支持 | 优势 | 劣势 |
|------|------|----------|------|------|
| **micro-ROS** | ESP32 → Agent → ROS2 | ✅ 完整 | 官方支持，生态完整 | 需要 Agent，增加延迟和部署复杂度 |
| **mros2-esp32 (upstream)** | ESP32 ⇄ ROS2 (直接) | ❌ 固定 BEST_EFFORT | 无 Agent，直接通信 | 无可靠传输，无 QoS 配置 |
| **mROS2-QoS (你的项目)** | ESP32 ⇄ ROS2 (直接) | ✅ 7 种策略 | 直接通信 + 完整 QoS | 原型阶段（但已硬件验证） |

---

## 实验矩阵设计

### 📊 实验 1：RTT 性能对比（核心指标）

**目标**：证明你的实现最快

| 指标 | micro-ROS | upstream | **你的项目** | 预期结果 |
|------|-----------|----------|--------------|----------|
| RTT min (ms) | 18.0 | 12.8 | **11.7** | ✅ 最优 |
| RTT avg (ms) | 27.5 | 21.6 | **20.7** | ✅ 最优 |
| RTT max (ms) | 102.5 | 43.8 | **38.3** | ✅ 最优 |
| 丢包率 | 0% | 0%* | **0%** | ✅ 持平（但有保障） |

*upstream 无重传机制，丢包后无法恢复

**实验条件**：
- N = 40 样本（后续扩展到 N=30 runs）
- 相同硬件：ESP32-S3
- 相同网络：同一 WiFi AP
- 相同负载：500ms 周期，String echo

---

### 📊 实验 2：QoS 功能验证（独有优势）

**目标**：展示只有你的项目支持的功能

| QoS 策略 | 测试场景 | Wireshark 观察目标 | 预期证据 |
|----------|----------|-------------------|----------|
| **RELIABLE** | 正常通信 | HEARTBEAT + ACKNACK | ✅ 有重传机制 |
| **BEST_EFFORT** | 对比测试 | 无 ACKNACK | ✅ 可配置切换 |
| **TRANSIENT_LOCAL** | 晚加入订阅者 | 发送历史数据 | ✅ 历史缓存 5/5 |
| **History KEEP_LAST(5)** | 突发数据 | 只保留最新 5 条 | ✅ 缓存限制生效 |
| **Deadline** | 超时检测 | 日志 missed count | ✅ 检测到超时 |
| **Liveliness** | 断网重连 | lost → recovered | ✅ 状态机转换 |
| **Lifespan** | 过期数据 | 过期消息不转发 | ✅ 时效性保证 |

**对比项**：
- micro-ROS：✅ 支持（通过 Agent）
- upstream：❌ 不支持（固定 BEST_EFFORT）
- 你的项目：✅ **直接支持，无需 Agent**

---

### 📊 实验 3：启动和恢复时间

**目标**：展示不同架构的系统行为差异

| 指标 | micro-ROS | upstream | **你的项目** |
|------|-----------|----------|--------------|
| 冷启动到首次通信 | **2.7s** ⚡ | ~8s | 8.7s |
| 架构解释 | Agent 会话（不是真正的 peer 发现） | DDS SEDP 发现 | DDS SEDP 发现 |
| 热重启匹配 | 未测 | 未测 | **0.4-0.9s** ⚡ |
| 重启鲁棒性 | 待测（Agent 可能残留状态） | 租约幽灵（100s） | **12s 租约修复** |

**解释要点**：
- micro-ROS 冷启动快，但那是连接到预配置的 Agent，不是真正的 peer 发现
- 你的项目和 upstream 都做真正的 DDS 发现，时间相似
- 你的项目在热重启上有优化（租约修复）

---

### 📊 实验 4：资源占用

**目标**：证明成本可控

| 指标 | upstream | **你的项目** | 增量 |
|------|----------|--------------|------|
| Flash | 738,832 B | 779,920 B | **+41 KB (+5.6%)** |
| 功能增益 | 固定 QoS | 7 种 QoS 策略 | 性价比高 |
| RAM | 待测 | 待测 | 待测 |

---

### 📊 实验 5：网络开销分析（Wireshark）

**目标**：量化不同架构的网络效率

| 指标 | 测量方法 | micro-ROS | upstream | 你的项目 |
|------|----------|-----------|----------|----------|
| 每消息包数 | tshark 统计 | 4-6 包（经过 Agent） | 2 包 | 2-3 包（RELIABLE） |
| 每消息字节数 | tshark 统计 | 待测 | 待测 | 待测 |
| HEARTBEAT 频率 | 包间隔统计 | N/A（Agent 内部） | N/A（无状态） | 可配置（4000ms） |
| 重传行为 | 模拟丢包 | ✅（Agent 处理） | ❌ 无重传 | ✅ ACKNACK 驱动 |

---

## Wireshark 抓包和分析步骤（手动操作指南）

### 🎯 第一部分：基础抓包（3 个系统各抓一次）

#### **步骤 A1：mROS2-QoS (RELIABLE) 抓包**

```bash
# 终端 1：启动 Wireshark
# 在 Windows GUI 中打开 Wireshark
# 选择网卡 eth1（WSL bridge）
# 捕获过滤器输入：udp portrange 7400-7420
# 点击 "Start capturing"

# 终端 2：运行测试
cd /home/wsde-47/mROS2-QoS
source /opt/ros/humble/setup.bash
./scripts/validation/qos_verify.sh /dev/ttyUSB0

# 等待测试完成（约 30 秒）
# 回到 Wireshark，点击红色方块停止抓包
# 保存为：capture_mros2qos_reliable.pcapng
```

#### **步骤 A2：upstream (BEST_EFFORT) 抓包**

```bash
# 终端 1：Wireshark（同上，重新开始抓包）

# 终端 2：运行 upstream 测试
cd /home/wsde-47/mros2_upstream_bench
source /opt/ros/humble/setup.bash
python3 test_upstream_rtt.py

# 停止 Wireshark
# 保存为：capture_upstream_besteffort.pcapng
```

#### **步骤 A3：micro-ROS 抓包**

```bash
# 终端 1：启动 Agent
micro_ros_agent udp4 --port 7408

# 终端 2：Wireshark（重新开始抓包）

# 终端 3：运行 micro-ROS 测试
cd /home/wsde-47/microros_bench
python3 test_microros_rtt.py

# 停止 Wireshark
# 保存为：capture_microros_agent.pcapng
```

---

### 🎯 第二部分：Wireshark 分析步骤

#### **分析 1：对比 RELIABLE vs BEST_EFFORT**

**目标**：直观看到 ACKNACK 重传机制的差异

**操作步骤**：

1. **打开你的项目抓包**：
   ```
   File → Open → capture_mros2qos_reliable.pcapng
   ```

2. **应用显示过滤器**：
   ```
   rtps
   ```

3. **查看协议层级**：
   ```
   在包列表中选中任意 DATA 包
   → 展开 "Real-Time Publish-Subscribe Protocol"
   → 看到 submessageId: DATA (0x15)
   ```

4. **统计 HEARTBEAT 包**：
   ```
   显示过滤器改为：rtps.sm.id == 0x07
   → 右键任意包 → Prepare as Filter → Selected
   → Statistics → Packet Lengths
   ```
   
   **记录**：
   - HEARTBEAT 包总数：______
   - 平均间隔：______ ms

5. **统计 ACKNACK 包**：
   ```
   显示过滤器改为：rtps.sm.id == 0x06
   ```
   
   **记录**：
   - ACKNACK 包总数：______
   - 是否有重传请求：______ (查看 Info 列)

6. **对比 upstream BEST_EFFORT**：
   ```
   打开 capture_upstream_besteffort.pcapng
   应用过滤器：rtps.sm.id == 0x07 || rtps.sm.id == 0x06
   ```
   
   **预期结果**：
   - ❌ 没有或极少 HEARTBEAT
   - ❌ 没有 ACKNACK

7. **截图保存**：
   - 你的项目：HEARTBEAT + ACKNACK 列表截图
   - upstream：纯 DATA 包截图
   - **用于论文对比**

---

#### **分析 2：画 Flow Graph（时序图）**

**目标**：生成论文用的协议时序图

**操作步骤**：

1. **打开抓包文件**：
   ```
   capture_mros2qos_reliable.pcapng
   ```

2. **选择时间窗口**：
   ```
   显示过滤器：frame.time_relative > 10 && frame.time_relative < 15
   （只看测试期间的 5 秒）
   ```

3. **生成 Flow Graph**：
   ```
   Statistics → Flow Graph
   → 在弹出窗口中：
     - Flow type: TCP Flows (默认)
     - 勾选 "Limit to display filter"
   → 点击 OK
   ```

4. **调整显示**：
   ```
   → 在 Flow Graph 窗口中
   → View → Time of Day (改为相对时间更清晰)
   ```

5. **截图保存**：
   ```
   → 截图整个 Flow Graph 窗口
   → 保存为：flowgraph_mros2qos_reliable.png
   ```

6. **重复操作**：
   - upstream：flowgraph_upstream_besteffort.png
   - micro-ROS：flowgraph_microros_agent.png（会看到 Agent 作为中间节点）

7. **论文用图对比**：
   ```
   mROS2-QoS:  ESP32 ⇄ Host (有 HEARTBEAT/ACKNACK)
   upstream:   ESP32 ⇄ Host (纯 DATA)
   micro-ROS:  ESP32 ⇄ Agent ⇄ Host (三跳)
   ```

---

#### **分析 3：测量网络延迟分布**

**目标**：画出 RTT 分布图

**操作步骤**：

1. **打开抓包文件并过滤**：
   ```
   capture_mros2qos_reliable.pcapng
   显示过滤器：udp.port == 7400 || udp.port == 7411
   ```

2. **添加 Delta Time 列**：
   ```
   → 右键列标题区域
   → Column Preferences
   → 点击 "+" 添加新列：
     Title: Delta
     Type: Delta time displayed
     Fields: frame.time_delta_displayed
   → 点击 OK
   ```

3. **改时间显示格式**：
   ```
   View → Time Display Format → Seconds Since Previous Displayed Packet
   ```

4. **导出延迟数据**：
   ```
   → 只看一个方向的包：ip.src == 10.54.75.107
   → File → Export Packet Dissections → As CSV
   → 保存为：rtt_deltas_mros2qos.csv
   → 在 Excel/Python 中画直方图
   ```

5. **使用 IO Graph 画延迟曲线**：
   ```
   Statistics → IO Graph
   → Y 轴改为：AVG(*) frame.time_delta_displayed
   → X 轴间隔：1 Sec
   → 截图保存为：iograph_rtt_mros2qos.png
   ```

6. **重复三个系统**，对比图表

---

#### **分析 4：TRANSIENT_LOCAL 历史数据验证**

**目标**：证明晚加入订阅者能收到历史数据

**操作步骤**：

1. **运行专门测试**：
   ```bash
   # 终端 1：启动 Wireshark 抓包
   
   # 终端 2：先启动发布者
   cd /home/wsde-47/mROS2-QoS
   source /opt/ros/humble/setup.bash
   # 烧录并启动 ESP32（发布 5 条消息后等待）
   
   # 等待 10 秒
   
   # 终端 3：晚启动订阅者
   python3 scripts/echo_reply.py  # 延迟启动
   
   # 停止 Wireshark，保存为：capture_transient_local.pcapng
   ```

2. **在 Wireshark 中验证**：
   ```
   显示过滤器：rtps
   → 找到订阅者加入的时间点（ACKNACK 出现）
   → 看在 ACKNACK 之后是否有历史 DATA 包重传
   → Info 列应该显示旧的序列号
   ```

3. **查看 ESP32 日志**：
   ```
   应该看到：
   [TRANSIENT_LOCAL] Sending cached history to late joiner
   History cache: 5/5 samples
   ```

4. **截图证据**：
   - Wireshark：晚加入时刻的 HEARTBEAT + 历史 DATA 截图
   - ESP32 日志：历史缓存统计

---

#### **分析 5：micro-ROS Agent 三跳可视化**

**目标**：展示 Agent 架构的额外跳数

**操作步骤**：

1. **打开 micro-ROS 抓包**：
   ```
   capture_microros_agent.pcapng
   ```

2. **查找 Agent IP**：
   ```
   显示过滤器：udp
   → 在包列表中找到三个 IP：
     - ESP32 IP (例如 10.54.75.107)
     - Agent IP (WSL IP)
     - ROS2 Host IP (可能与 Agent 相同)
   ```

3. **画 Flow Graph**：
   ```
   Statistics → Flow Graph
   → 应该看到：
     ESP32 → Agent (XRCE 协议)
     Agent → ROS2 Host (DDS/RTPS)
   ```

4. **对比你的项目**：
   ```
   打开 capture_mros2qos_reliable.pcapng
   Statistics → Flow Graph
   → 只有两个节点：
     ESP32 ⇄ ROS2 Host (直接 RTPS)
   ```

5. **论文配图**：
   ```
   并排放置两个 Flow Graph：
   左：micro-ROS (三跳)
   右：mROS2-QoS (两跳，标注 "Direct DDS Communication")
   ```

---

### 🎯 第三部分：参数调节实验

**目标**：展示你理解 RTPS 协议原理

#### **实验 B1：调整 HEARTBEAT 周期**

1. **修改配置**：
   ```bash
   cd /home/wsde-47/mROS2-QoS
   # 找到 config.h 并修改
   vim mros2/embeddedRTPS/include/rtps/config.h
   
   # 修改这行：
   #define SF_WRITER_HB_PERIOD_MS 4000
   # 改为：1000
   ```

2. **编译烧录**：
   ```bash
   cd workspace/qos_eval
   idf.py build flash
   ```

3. **抓包测试**：
   ```
   重复上面的抓包流程
   保存为：capture_hb1000ms.pcapng
   ```

4. **分析变化**：
   ```
   显示过滤器：rtps.sm.id == 0x07
   → 统计 HEARTBEAT 间隔
   → 预期：从 4000ms 降到 1000ms
   ```

5. **测量 RTT 变化**：
   ```bash
   python3 test_rtt.py
   → 记录 RTT avg
   → 对比默认配置
   ```

6. **重复实验**：
   ```
   HEARTBEAT 周期：4000 / 2000 / 1000 / 500 / 100 ms
   记录：RTT avg, HEARTBEAT 包数, 网络流量
   ```

7. **作图**：
   ```
   X 轴：HEARTBEAT 周期 (ms)
   Y 轴：RTT avg (ms)
   结论：周期越短，RTT 波动越小（但网络开销增加）
   ```

---

#### **实验 B2：调整 History Depth**

1. **修改配置**：
   ```c
   #define HISTORY_SIZE_STATEFUL 10
   // 改为：5, 10, 20, 30
   ```

2. **突发数据测试**：
   ```bash
   # 修改发布频率为 50ms（高频）
   # 测试历史缓存是否生效
   ```

3. **Wireshark 验证**：
   ```
   → 看 ACKNACK 请求的序列号范围
   → 验证只保留最新 N 条
   ```

4. **ESP32 日志**：
   ```
   History cache: X/X samples
   → X 应该等于配置的 depth
   ```

---

## 📈 最终输出（论文用）

### **表格 1：性能对比总表**

| 指标 | micro-ROS | upstream | **mROS2-QoS** | 改进 |
|------|-----------|----------|---------------|------|
| RTT avg (ms) | 27.5 | 21.6 | **20.7** | **-25% vs micro-ROS** |
| QoS 支持 | ✅ (需 Agent) | ❌ | ✅ (直接) | **架构优势** |
| Flash (KB) | 771 | 722 | 761 | **+5.6%（7 QoS 策略）** |
| 部署复杂度 | Agent required | 简单 | 简单 | **无 Agent** |

### **图 1：RTT 分布箱线图**

```
三个系统的 RTT 分布对比（N=40）
→ 你的项目：最窄的箱体 + 最低的中位数
```

### **图 2：协议时序对比**

```
Flow Graph 并排对比：
- micro-ROS：三跳（ESP32 → Agent → ROS2）
- mROS2-QoS：两跳（ESP32 ⇄ ROS2）
- 标注 HEARTBEAT/ACKNACK 位置
```

### **图 3：HEARTBEAT 周期对 RTT 的影响**

```
X 轴：HEARTBEAT 周期 (100, 500, 1000, 2000, 4000 ms)
Y 轴：RTT avg (ms)
曲线：展示 trade-off（可靠性 vs 开销）
```

### **图 4：QoS 功能对比雷达图**

```
维度：Reliability, Durability, History, Deadline, Lifespan, Liveliness, Resource Limits
三条线：micro-ROS (满分), upstream (只有中心点), mROS2-QoS (满分)
```

---

## 📝 实验记录表格模板

### RTT 数据记录

| 运行 | 系统 | RTT min | RTT avg | RTT max | 丢包 | 备注 |
|------|------|---------|---------|---------|------|------|
| 1 | mROS2-QoS | | | | | |
| 2 | mROS2-QoS | | | | | |
| ... | ... | | | | | |
| 30 | mROS2-QoS | | | | | |
| 1 | upstream | | | | | |
| ... | ... | | | | | |
| 1 | micro-ROS | | | | | |
| ... | ... | | | | | |

### Wireshark 数据记录

| 系统 | 总包数 | DATA 包 | HEARTBEAT | ACKNACK | 总字节 | pcapng 文件 |
|------|--------|---------|-----------|---------|--------|-------------|
| mROS2-QoS | | | | | | capture_mros2qos_reliable.pcapng |
| upstream | | | | | | capture_upstream_besteffort.pcapng |
| micro-ROS | | | | | | capture_microros_agent.pcapng |

### 参数调节记录

| HEARTBEAT 周期 | RTT avg | RTT std | HB 包数 | 网络字节 |
|----------------|---------|---------|---------|----------|
| 4000 ms (默认) | | | | |
| 2000 ms | | | | |
| 1000 ms | | | | |
| 500 ms | | | | |
| 100 ms | | | | |

---

## ✅ 检查清单

### 实验准备
- [ ] 三个系统固件都已编译并可烧录
- [ ] Wireshark 已安装并测试
- [ ] WSL 防火墙已配置（UDP 7400-7420）
- [ ] WiFi 环境稳定（记录 RSSI）
- [ ] 记录表格已打印或准备好

### 基础抓包（3个系统）
- [ ] mROS2-QoS RELIABLE 抓包完成
- [ ] upstream BEST_EFFORT 抓包完成
- [ ] micro-ROS 抓包完成
- [ ] 所有 pcapng 文件已备份

### Wireshark 分析
- [ ] RELIABLE vs BEST_EFFORT 对比截图
- [ ] Flow Graph 三个系统都已生成
- [ ] RTT 延迟数据已导出 CSV
- [ ] IO Graph 已截图
- [ ] TRANSIENT_LOCAL 历史数据已验证

### 参数调节实验
- [ ] HEARTBEAT 周期扫描（5个值）
- [ ] History depth 扫描（4个值）
- [ ] 每个配置都有对应的 pcapng
- [ ] 数据已记录到表格

### 论文素材
- [ ] 性能对比总表已填写
- [ ] RTT 箱线图已绘制
- [ ] 协议时序图已标注
- [ ] 参数影响曲线已绘制
- [ ] QoS 功能雷达图已绘制

---

## 🚀 下一步

告诉我你想从哪里开始：

1. **现在就开始抓包**（我给你每一步的命令）
2. **先检查三个系统的准备情况**（确保都能跑）
3. **先做参数调节实验**（理解 config.h 的作用）
4. **其他问题**

你打算什么时候开始实验？需要我帮你准备什么？
