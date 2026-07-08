# RTPS Parameter Tuning Experiments - Complete Guide

## 目标

通过系统地调节 RTPS/DDS 协议参数，深入理解协议行为，并为不同应用场景找到最优配置。

## 配置文件位置

```
/home/wsde-47/mROS2-QoS/platform/rtps/config.h
```

修改后需要重新编译：
```bash
cd /home/wsde-47/mROS2-QoS/workspace/qos_eval
idf.py build flash
```

---

## 实验 1：心跳周期调节（影响可靠性和延迟）

### 参数位置
```c
const uint16_t SF_WRITER_HB_PERIOD_MS = 4000;  // 第 90 行
```

### 作用说明
- RELIABLE 模式下，发送方周期性发送 HEARTBEAT 消息
- HEARTBEAT 告诉接收方：我有哪些序列号的数据
- 接收方根据 HEARTBEAT 发现丢包，通过 ACKNACK 请求重传

### 调节范围
```c
SF_WRITER_HB_PERIOD_MS: 100, 500, 1000, 2000, 4000, 8000 (ms)
```

### 预期影响

| 周期 | 可靠性 | 延迟 | 网络开销 | 适用场景 |
|------|--------|------|----------|----------|
| 100 ms | ⭐⭐⭐⭐⭐ | 低 | 高 | 高频数据，低延迟要求 |
| 1000 ms | ⭐⭐⭐⭐ | 中 | 中 | 平衡配置 |
| 4000 ms | ⭐⭐⭐ | 高 | 低 | 低频数据，节省带宽 |
| 8000 ms | ⭐⭐ | 很高 | 很低 | 极低频数据 |

### Wireshark 观察要点

1. **统计 HEARTBEAT 频率**：
   ```
   显示过滤器：rtps.sm.id == 0x07
   Statistics → IO Graph
   Y 轴：Packets/tick
   X 轴间隔：1 Second
   ```
   
2. **测量重传延迟**（模拟丢包场景）：
   ```
   人为制造干扰（开启其他下载）
   观察从 HEARTBEAT 到 ACKNACK 到重传 DATA 的时间
   ```

3. **记录数据**：
   ```
   | HB 周期 | HB 包数/40s | ACKNACK 数 | RTT avg | RTT max | 网络总字节 |
   |---------|-------------|------------|---------|---------|------------|
   | 100     |             |            |         |         |            |
   | 500     |             |            |         |         |            |
   | 1000    |             |            |         |         |            |
   | 2000    |             |            |         |         |            |
   | 4000    |             |            |         |         |            |
   | 8000    |             |            |         |         |            |
   ```

---

## 实验 2：历史缓冲深度（影响突发数据处理）

### 参数位置
```c
const uint8_t HISTORY_SIZE_STATELESS = 2;   // 第 79 行
const uint8_t HISTORY_SIZE_STATEFUL = 10;   // 第 80 行
```

### 作用说明
- STATEFUL（RELIABLE）：保存最近 N 条消息用于重传和晚加入订阅者
- STATELESS（BEST_EFFORT）：临时缓冲

### 调节范围
```c
HISTORY_SIZE_STATEFUL: 3, 5, 10, 20, 30, 50
```

### 预期影响

| Depth | 内存占用 | 晚加入能力 | 突发容量 | 适用场景 |
|-------|----------|------------|----------|----------|
| 3 | 低 | 3 条 | 小 | 低频单消息 |
| 10 | 中 | 10 条 | 中 | **默认配置** |
| 30 | 高 | 30 条 | 大 | 高频或关键历史数据 |
| 50 | 很高 | 50 条 | 很大 | 需要长历史记录 |

### Wireshark 观察要点

1. **TRANSIENT_LOCAL 晚加入测试**：
   ```bash
   # 步骤：
   1. ESP32 发布 N 条消息（N > history depth）
   2. 等待 10 秒
   3. 启动晚加入订阅者
   4. 观察订阅者收到多少历史消息
   ```
   
2. **Wireshark 验证**：
   ```
   显示过滤器：rtps.sm.id == 0x15
   在晚加入时刻查看重传的 DATA 序列号
   应该只看到最新的 [depth] 条
   ```

3. **ESP32 日志验证**：
   ```
   [QoS] History cache: X/Y samples
   X 应该 <= Y (Y = HISTORY_SIZE_STATEFUL)
   ```

4. **记录数据**：
   ```
   | Depth | 发送消息数 | 晚加入收到 | ESP32 堆内存 | Flash 大小 |
   |-------|-----------|-----------|--------------|------------|
   | 3     | 20        |           |              |            |
   | 5     | 20        |           |              |            |
   | 10    | 20        |           |              |            |
   | 20    | 30        |           |              |            |
   | 30    | 40        |           |              |            |
   | 50    | 60        |           |              |            |
   ```

---

## 实验 3：SPDP 发现周期（影响启动速度）

### 参数位置
```c
const uint16_t SPDP_RESEND_PERIOD_MS = 1000;  // 第 91 行
```

### 作用说明
- SPDP (Simple Participant Discovery Protocol) 是 DDS 的参与者发现协议
- 周期性广播/单播自己的存在
- 周期越短，发现越快，但网络开销越大

### 调节范围
```c
SPDP_RESEND_PERIOD_MS: 250, 500, 1000, 2000, 5000 (ms)
```

### 预期影响

| 周期 | 冷启动速度 | 网络开销 | 适用场景 |
|------|-----------|----------|----------|
| 250 ms | ⚡ 极快 | 高 | 频繁重启的系统 |
| 1000 ms | ✅ 快 | 中 | **默认配置** |
| 2000 ms | 中 | 低 | 稳定系统 |
| 5000 ms | 慢 | 很低 | 极少重启的系统 |

### Wireshark 观察要点

1. **统计 SPDP 频率**：
   ```
   显示过滤器：rtps.sm.id == 0x09
   (SPDP 使用 DATA submessage，但可以通过端口 7400 识别)
   或者：udp.port == 7400
   ```

2. **测量发现时间**：
   ```
   从 ESP32 reset 到第一个 SEDP (端点发现) 消息出现的时间
   ```

3. **记录数据**：
   ```
   | SPDP 周期 | 冷启动时间 | SPDP 包数/60s | 到首次匹配 |
   |----------|-----------|--------------|-----------|
   | 250      |           |              |           |
   | 500      |           |              |           |
   | 1000     |           |              |           |
   | 2000     |           |              |           |
   | 5000     |           |              |           |
   ```

---

## 实验 4：租约时长（影响故障检测）

### 参数位置
```c
const Duration_t SPDP_DEFAULT_REMOTE_LEASE_DURATION = {12, 0};  // 第 97-98 行
const Duration_t SPDP_MAX_REMOTE_LEASE_DURATION = {180, 0};     // 第 104-105 行
```

### 作用说明
- 租约 = 参与者的"心跳超时"时间
- 如果在租约期内没收到对方的 SPDP，认为对方已离线
- **重要**：影响重启后旧连接被清理的速度

### 调节范围
```c
SPDP_DEFAULT_REMOTE_LEASE_DURATION: {5,0}, {12,0}, {30,0}, {60,0}, {180,0}
// 格式：{秒, 纳秒}
```

### 预期影响

| 租约 | 故障检测速度 | 重启恢复速度 | "幽灵连接"风险 |
|------|-------------|-------------|---------------|
| 5s | ⚡ 极快 | ⚡ 极快 | ✅ 低 |
| 12s | ✅ 快 | ✅ 快 | ✅ 低（**当前配置**） |
| 30s | 中 | 慢 | ⚠️ 中 |
| 180s | 慢 | 很慢 | ❌ 高（upstream 默认） |

### Wireshark 观察要点

1. **重启恢复测试**：
   ```bash
   # 步骤：
   1. 正常通信
   2. ESP32 reset（不关闭 ROS2 节点）
   3. 测量到恢复通信的时间
   ```

2. **租约过期测试**：
   ```bash
   # 步骤：
   1. 正常通信
   2. ESP32 断电（拔 USB）
   3. 在 Wireshark 中观察 ROS2 多久停止发送 HEARTBEAT
   ```

3. **记录数据**：
   ```
   | 租约 | 重启恢复时间 | 断电检测时间 | 首次通信延迟 |
   |------|-------------|-------------|-------------|
   | 5    |             |             |             |
   | 12   |             |             |             |
   | 30   |             |             |             |
   | 60   |             |             |             |
   | 180  |             |             |             |
   ```

---

## 实验 5：读写者数量限制（影响系统规模）

### 参数位置
```c
const uint8_t NUM_STATEFUL_READERS = 8;              // 第 66 行
const uint8_t NUM_STATEFUL_WRITERS = 8;              // 第 67 行
const uint8_t NUM_WRITERS_PER_PARTICIPANT = 16;      // 第 69 行
const uint8_t NUM_READERS_PER_PARTICIPANT = 16;      // 第 70 行
```

### 作用说明
- 限制同时可以创建多少个 Publisher/Subscriber
- 每个都会分配内存和资源
- 如果超出限制，创建会失败

### 调节范围
```c
NUM_STATEFUL_WRITERS: 4, 8, 16, 32
NUM_STATEFUL_READERS: 4, 8, 16, 32
```

### 预期影响

| 数量 | 内存占用 | 支持 Topic 数 | Flash 大小 |
|------|----------|--------------|------------|
| 4 | 低 | 少 | 小 |
| 8 | 中 | 中（**默认**） | 中 |
| 16 | 高 | 多 | 大 |
| 32 | 很高 | 很多 | 很大 |

### 实验设计

1. **多 Topic 压力测试**：
   ```bash
   # 创建 N 个 topic 同时通信
   # 观察到达限制时的行为
   ```

2. **内存占用测试**：
   ```bash
   # ESP32 日志中查看 free heap
   # idf.py size 查看 flash 大小
   ```

3. **记录数据**：
   ```
   | Writers/Readers | 支持 Topic 数 | Free Heap (KB) | Flash (KB) |
   |----------------|--------------|----------------|------------|
   | 4/4            |              |                |            |
   | 8/8            |              |                |            |
   | 16/16          |              |                |            |
   | 32/32          |              |                |            |
   ```

---

## 实验 6：代理数量（影响多对多通信）

### 参数位置
```c
const uint8_t NUM_WRITER_PROXIES_PER_READER = 6;  // 第 71 行
const uint8_t NUM_READER_PROXIES_PER_WRITER = 6;  // 第 72 行
```

### 作用说明
- Proxy = 对端的本地代理对象
- 一个 Reader 可以从多个 Writer 接收（需要多个 WriterProxy）
- 一个 Writer 可以发给多个 Reader（需要多个 ReaderProxy）

### 调节范围
```c
NUM_WRITER_PROXIES_PER_READER: 2, 6, 10, 15
NUM_READER_PROXIES_PER_WRITER: 2, 6, 10, 15
```

### 预期影响

| Proxies | 多对多能力 | 内存占用 | 适用场景 |
|---------|-----------|----------|----------|
| 2 | 低 | 低 | 1对1 或 1对多（少） |
| 6 | 中（**默认**） | 中 | 小规模系统 |
| 15 | 高 | 高 | 大规模多对多 |

### 实验设计

1. **多订阅者测试**：
   ```bash
   # ESP32 发布 1 个 topic
   # 启动 N 个 ROS2 订阅者
   # 观察到达限制时的行为
   ```

2. **多发布者测试**：
   ```bash
   # 启动 N 个 ROS2 发布者
   # ESP32 订阅 1 个 topic
   # 观察能接收多少个发布者的数据
   ```

---

## 实验 7：工作队列长度（影响吞吐量）

### 参数位置
```c
const int THREAD_POOL_WORKLOAD_QUEUE_LENGTH = 20;  // 第 117 行
```

### 作用说明
- 线程池的任务队列长度
- 队列满时，新任务会被丢弃或阻塞
- 高频发布时可能需要更大队列

### 调节范围
```c
THREAD_POOL_WORKLOAD_QUEUE_LENGTH: 10, 20, 50, 100, 200
```

### 预期影响

| 队列长度 | 突发处理能力 | 内存占用 | 适用场景 |
|---------|-------------|----------|----------|
| 10 | 低 | 低 | 低频数据 |
| 20 | 中（**默认**） | 中 | 常规场景 |
| 100 | 高 | 高 | 高频突发 |
| 200 | 很高 | 很高 | 极高频流式数据 |

### 实验设计

1. **高频发布测试**：
   ```bash
   # 修改发布周期为 10ms（100 Hz）
   # 观察是否有丢包
   ```

2. **ESP32 日志观察**：
   ```
   查找 "queue full" 或 "dropped" 关键词
   ```

3. **记录数据**：
   ```
   | 队列长度 | 发布频率 | 丢包数 | CPU 占用 |
   |---------|---------|--------|---------|
   | 10      | 100 Hz  |        |         |
   | 20      | 100 Hz  |        |         |
   | 50      | 100 Hz  |        |         |
   | 100     | 100 Hz  |        |         |
   ```

---

## 实验 8：线程池大小（影响并发性能）

### 参数位置
```c
const int THREAD_POOL_NUM_WRITERS = 1;  // 第 113 行
const int THREAD_POOL_NUM_READERS = 1;  // 第 114 行
```

### 作用说明
- 处理发送和接收的线程数
- 多线程可以提高并发，但增加调度开销
- ESP32 的 CPU 核心有限（2 核）

### 调节范围
```c
THREAD_POOL_NUM_WRITERS: 1, 2, 4
THREAD_POOL_NUM_READERS: 1, 2, 4
```

### 预期影响

| 线程数 | 并发能力 | CPU 开销 | 适用场景 |
|--------|---------|---------|----------|
| 1/1 | 低（**默认**） | 低 | 单 topic 或低频 |
| 2/2 | 中 | 中 | 多 topic 中频 |
| 4/4 | 高 | 高 | 大规模高频 |

### 实验设计

1. **多 Topic 并发测试**：
   ```bash
   # 同时发布 4 个 topic
   # 测量总吞吐量
   ```

2. **CPU 占用监控**：
   ```bash
   # ESP32 任务监控
   vTaskGetRunTimeStats()
   ```

---

## 实验 9：主题名长度限制（影响灵活性）

### 参数位置
```c
const uint8_t MAX_TYPENAME_LENGTH = 40;   // 第 82 行
const uint8_t MAX_TOPICNAME_LENGTH = 40;  // 第 83 行
```

### 作用说明
- 限制 topic 名称和类型名称的最大长度
- 更长的名称需要更多内存

### 调节范围
```c
MAX_TOPICNAME_LENGTH: 20, 40, 80, 128
```

### 实验设计

1. **长名称测试**：
   ```bash
   # 创建名称长度为 N 的 topic
   # 观察是否被截断
   ```

2. **内存影响**：
   ```bash
   # 对比不同长度限制的内存占用
   ```

---

## 实验 10：线程优先级调节（影响实时性）

### 参数位置
```c
const uint8_t SPDP_WRITER_PRIO = 24;           // 第 94 行
const int THREAD_POOL_WRITER_PRIO = 24;        // 第 115 行
const int THREAD_POOL_READER_PRIO = 24;        // 第 116 行
```

### 作用说明
- FreeRTOS 线程优先级（0-31，数字越大优先级越高）
- 影响实时响应能力

### 调节范围
```c
THREAD_POOL_READER_PRIO: 16, 20, 24, 28
// 发现线程保持 24，只调节数据线程
```

### 实验设计

1. **高负载下的响应时间**：
   ```bash
   # 同时运行其他 FreeRTOS 任务
   # 测量 RTT 变化
   ```

---

## 综合实验：参数组合优化

### 场景 1：低延迟配置
```c
SF_WRITER_HB_PERIOD_MS = 500           // 快速心跳
SPDP_RESEND_PERIOD_MS = 500            // 快速发现
SPDP_DEFAULT_REMOTE_LEASE_DURATION = {5, 0}  // 快速故障检测
HISTORY_SIZE_STATEFUL = 5              // 小缓存
THREAD_POOL_WORKLOAD_QUEUE_LENGTH = 50 // 大队列
```

### 场景 2：高可靠配置
```c
SF_WRITER_HB_PERIOD_MS = 1000
HISTORY_SIZE_STATEFUL = 30             // 大历史缓存
SPDP_DEFAULT_REMOTE_LEASE_DURATION = {30, 0}
NUM_READER_PROXIES_PER_WRITER = 10     // 支持更多订阅者
```

### 场景 3：低功耗配置
```c
SF_WRITER_HB_PERIOD_MS = 8000          // 慢心跳
SPDP_RESEND_PERIOD_MS = 5000           // 慢发现
HISTORY_SIZE_STATEFUL = 3              // 小缓存
THREAD_POOL_NUM_WRITERS = 1
THREAD_POOL_NUM_READERS = 1
```

### 场景 4：大规模配置
```c
NUM_STATEFUL_WRITERS = 32
NUM_STATEFUL_READERS = 32
NUM_WRITER_PROXIES_PER_READER = 15
NUM_READER_PROXIES_PER_WRITER = 15
THREAD_POOL_NUM_WRITERS = 2
THREAD_POOL_NUM_READERS = 2
```

---

## 实验数据汇总表格

### 总表：所有参数的影响矩阵

| 参数 | 默认值 | 影响维度 | 调节优先级 | 论文价值 |
|------|--------|---------|-----------|---------|
| SF_WRITER_HB_PERIOD_MS | 4000 | 延迟、可靠性、网络开销 | ⭐⭐⭐⭐⭐ | 高 |
| HISTORY_SIZE_STATEFUL | 10 | 内存、晚加入能力 | ⭐⭐⭐⭐⭐ | 高 |
| SPDP_RESEND_PERIOD_MS | 1000 | 启动速度、网络开销 | ⭐⭐⭐⭐ | 中 |
| SPDP_DEFAULT_REMOTE_LEASE_DURATION | 12s | 故障检测、重启恢复 | ⭐⭐⭐⭐ | 中 |
| NUM_STATEFUL_WRITERS/READERS | 8 | 系统规模、内存 | ⭐⭐⭐ | 中 |
| NUM_WRITER_PROXIES_PER_READER | 6 | 多对多能力 | ⭐⭐⭐ | 中 |
| THREAD_POOL_WORKLOAD_QUEUE_LENGTH | 20 | 吞吐量、突发处理 | ⭐⭐⭐ | 中 |
| THREAD_POOL_NUM_WRITERS/READERS | 1 | 并发性能 | ⭐⭐ | 低 |
| THREAD_POOL_READER_PRIO | 24 | 实时性 | ⭐⭐ | 低 |
| MAX_TOPICNAME_LENGTH | 40 | 灵活性、内存 | ⭐ | 低 |

---

## Wireshark 通用分析流程

### 每次参数修改后的标准流程

1. **编译烧录**：
   ```bash
   cd /home/wsde-47/mROS2-QoS/workspace/qos_eval
   idf.py build flash
   ```

2. **启动 Wireshark**：
   ```
   捕获过滤器：udp portrange 7400-7420
   ```

3. **运行测试**：
   ```bash
   cd /home/wsde-47/mROS2-QoS
   ./scripts/validation/qos_verify.sh /dev/ttyUSB0
   ```

4. **保存抓包**：
   ```
   文件命名规范：
   capture_[参数名]_[参数值].pcapng
   例如：capture_hb_period_1000ms.pcapng
   ```

5. **Wireshark 分析**：
   ```
   1. 统计包数：Statistics → Capture File Properties
   2. 协议分布：Statistics → Protocol Hierarchy
   3. 时序图：Statistics → Flow Graph
   4. HEARTBEAT 频率：过滤 rtps.sm.id == 0x07
   5. ACKNACK 统计：过滤 rtps.sm.id == 0x06
   6. 延迟分布：IO Graph，Y 轴为 frame.time_delta
   ```

6. **记录数据到 Excel/CSV**

---

## 论文写作建议

### 参数调节章节结构

```
5. RTPS Parameter Tuning and Optimization

5.1 Methodology
    - 参数选择标准
    - 测试环境和工具
    - 评估指标

5.2 Heartbeat Period Impact (SF_WRITER_HB_PERIOD_MS)
    - 实验设计
    - Wireshark 流量分析
    - RTT vs HB Period 曲线图
    - Trade-off 分析

5.3 History Depth Optimization (HISTORY_SIZE_STATEFUL)
    - Late-joiner 实验
    - 内存占用对比
    - 推荐配置

5.4 Discovery Period Tuning (SPDP_RESEND_PERIOD_MS)
    - 冷启动时间测量
    - 网络开销对比

5.5 Lease Duration Analysis
    - 故障检测时间
    - Ghosting 问题解决

5.6 Multi-Parameter Optimization
    - 场景化配置
    - 帕累托前沿分析

5.7 Best Practice Guidelines
    - 低延迟场景推荐配置
    - 高可靠场景推荐配置
    - 低功耗场景推荐配置
```

### 关键配图

1. **图 5-1**：HEARTBEAT Period vs RTT（折线图）
2. **图 5-2**：History Depth vs Memory Footprint（柱状图）
3. **图 5-3**：Wireshark Flow Graph 对比（HB=100ms vs 4000ms）
4. **图 5-4**：参数影响热力图（所有参数 × 所有指标）
5. **图 5-5**：场景化配置雷达图（4 个场景对比）

---

## 快速开始清单

### 第一周：核心参数（2个）
- [ ] 实验 1：HEARTBEAT 周期（6 个值）
- [ ] 实验 2：History 深度（6 个值）

### 第二周：重要参数（3个）
- [ ] 实验 3：SPDP 周期（5 个值）
- [ ] 实验 4：租约时长（5 个值）
- [ ] 实验 7：工作队列（5 个值）

### 第三周：扩展参数（4个）
- [ ] 实验 5：读写者数量（4 个值）
- [ ] 实验 6：代理数量（4 个值）
- [ ] 实验 8：线程池（3 个值）
- [ ] 实验 10：线程优先级（4 个值）

### 第四周：综合优化
- [ ] 4 个场景配置验证
- [ ] 论文数据整理
- [ ] Wireshark 截图标注

---

## 需要的帮助？

告诉我你想：
1. **从哪个实验开始**（推荐从实验 1 开始）
2. **需要详细的 Wireshark 操作步骤**
3. **需要 Python 脚本自动化测试**
4. **需要数据分析和作图代码**

我随时可以提供每个实验的详细操作指令！
