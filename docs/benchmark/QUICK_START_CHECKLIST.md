# 实验快速启动清单

## 📋 实验前准备（第一天开始前完成）

### ✅ 硬件检查
- [ ] ESP32-S3 已连接到电脑
- [ ] USB 线缆工作正常
- [ ] WSL 能识别设备：`ls /dev/ttyUSB*`
- [ ] WiFi AP 工作正常

### ✅ 软件环境
- [ ] ROS 2 Humble 已安装：`ros2 --version`
- [ ] ESP-IDF 已配置：`. ~/esp/esp-idf/export.sh`
- [ ] Wireshark 已安装（Windows）
- [ ] WSL 防火墙已配置（运行过 `wsl_firewall_admin.ps1`）

### ✅ 项目准备
- [ ] mROS2-QoS 项目已克隆并编译通过
- [ ] upstream bench 已准备（如果需要对比）
- [ ] micro-ROS bench 已准备（如果需要对比）
- [ ] `qos_verify.sh` 能正常运行

### ✅ 数据记录工具
- [ ] Excel 或 Google Sheets 已打开
- [ ] 创建了实验记录模板
- [ ] 准备了截图工具（Windows：Win+Shift+S）

### ✅ 目录结构
```bash
cd ~/mROS2-QoS
mkdir -p results/experiments_2026/{raw_data,figures,analysis}
```

---

## 🎯 第一天：三系统基础对比（3小时）

### 上午（1.5小时）：mROS2-QoS + upstream

#### Experiment 1A: mROS2-QoS (30 min)
- [ ] 启动 Wireshark，过滤器：`udp portrange 7400-7420`
- [ ] 运行测试：`./scripts/validation/qos_verify.sh /dev/ttyUSB0`
- [ ] 保存抓包：`capture_mros2qos_reliable.pcapng`
- [ ] 记录 RTT：min=___, avg=___, max=___

#### Experiment 1B: upstream (30 min)
- [ ] 切换到 upstream 环境
- [ ] 启动 Wireshark（重新开始）
- [ ] 运行测试：`python3 test_upstream_rtt.py`
- [ ] 保存抓包：`capture_upstream_besteffort.pcapng`
- [ ] 记录 RTT：min=___, avg=___, max=___

#### 休息 + 数据整理 (30 min)
- [ ] 检查 pcapng 文件能否正常打开
- [ ] 填写 Excel 表格
- [ ] 备份文件到安全位置

### 下午（1.5小时）：micro-ROS

#### Experiment 1C: micro-ROS (60 min)
- [ ] 终端1：启动 Agent `micro_ros_agent udp4 --port 7408`
- [ ] 终端2：烧录 micro-ROS 固件
- [ ] 终端3：启动 Wireshark
- [ ] 终端4：运行测试脚本
- [ ] 保存抓包：`capture_microros_agent.pcapng`
- [ ] 记录 RTT：min=___, avg=___, max=___

#### 数据验证 (30 min)
- [ ] 三个 pcapng 文件都已保存
- [ ] RTT 数据已记录到表格
- [ ] 初步对比：哪个最快？差多少？

---

## 🎯 第二天：Wireshark 深度分析（4小时）

### 上午（2小时）：RELIABLE vs BEST_EFFORT + Flow Graph

#### Analysis 2A: RELIABLE vs BEST_EFFORT (60 min)
- [ ] 打开 `capture_mros2qos_reliable.pcapng`
- [ ] 过滤器：`rtps.sm.id == 0x07`（HEARTBEAT）
- [ ] 记录 HEARTBEAT 数量：___
- [ ] 导出 CSV：`heartbeat_mros2qos.csv`
- [ ] 截图1：保存为 `fig_heartbeat_reliable.png`

- [ ] 打开 `capture_upstream_besteffort.pcapng`
- [ ] 同样过滤器，观察无/少 HEARTBEAT
- [ ] 截图2：保存为 `fig_no_heartbeat_besteffort.png`

#### Analysis 2B: Flow Graph (60 min)
- [ ] mROS2-QoS Flow Graph → 截图3
- [ ] upstream Flow Graph → 截图4
- [ ] micro-ROS Flow Graph（三跳）→ 截图5
- [ ] 对比并标注关键差异

### 下午（2小时）：RTT延迟分布 + TRANSIENT_LOCAL

#### Analysis 2C: RTT 延迟分布 (60 min)
- [ ] 添加 Delta Time 列
- [ ] 导出 `rtt_deltas_mros2qos.csv`
- [ ] 导出 `rtt_deltas_upstream.csv`
- [ ] 导出 `rtt_deltas_microros.csv`
- [ ] IO Graph 截图（3个系统）

#### Analysis 2D: TRANSIENT_LOCAL (60 min)
- [ ] 创建 `test_late_joiner.py` 脚本
- [ ] 重新运行晚加入测试
- [ ] 启动 Wireshark 抓包
- [ ] 保存：`capture_transient_local_late_joiner.pcapng`
- [ ] 截图7-9：包列表、序列号、ESP32日志
- [ ] 记录：晚加入收到 ___ 条历史消息

---

## 🎯 第三天：核心参数实验（6小时）

### 上午（3小时）：心跳周期

#### Experiment 3.1: HEARTBEAT Period (3 hours)
- [ ] 备份 config.h：`cp config.h config.h.backup`

**100ms:**
- [ ] 修改 `SF_WRITER_HB_PERIOD_MS = 100`
- [ ] 编译烧录：`idf.py build flash`
- [ ] 抓包测试
- [ ] 保存：`capture_hb_100ms.pcapng`
- [ ] 记录 RTT：___

**500ms:**
- [ ] 修改参数 → 编译 → 测试 → 保存 → 记录

**1000ms:**
- [ ] 修改参数 → 编译 → 测试 → 保存 → 记录

**2000ms:**
- [ ] 修改参数 → 编译 → 测试 → 保存 → 记录

**4000ms (默认):**
- [ ] 修改参数 → 编译 → 测试 → 保存 → 记录

**8000ms:**
- [ ] 修改参数 → 编译 → 测试 → 保存 → 记录

- [ ] 恢复默认：`cp config.h.backup config.h`
- [ ] 在 Wireshark 中统计每个配置的 HEARTBEAT 包数

### 下午（3小时）：历史深度

#### Experiment 3.2: History Depth (3 hours)
- [ ] 修改 `HISTORY_SIZE_STATEFUL = 3` → 测试 → 记录
- [ ] `= 5` → 测试 → 记录
- [ ] `= 10` (默认) → 测试 → 记录
- [ ] `= 20` → 测试 → 记录
- [ ] `= 30` → 测试 → 记录
- [ ] `= 50` → 测试 → 记录

- [ ] 从 ESP32 日志提取 free heap 数据
- [ ] 从编译输出提取 flash size
- [ ] 可选：对 depth >= 5 做晚加入测试

---

## 🎯 第四天：其他参数实验（6小时）

### 上午（3小时）：SPDP 发现周期

#### Experiment 3.3: SPDP Period (3 hours)
- [ ] 修改 `SPDP_RESEND_PERIOD_MS = 250` → 测试 → 记录启动时间
- [ ] `= 500` → 测试 → 记录
- [ ] `= 1000` (默认) → 测试 → 记录
- [ ] `= 2000` → 测试 → 记录
- [ ] `= 5000` → 测试 → 记录

- [ ] 在 Wireshark 中统计 SPDP 包频率

### 下午（3小时）：租约时长

#### Experiment 3.4: Lease Duration (3 hours)
- [ ] 修改 `SPDP_DEFAULT_REMOTE_LEASE_DURATION = {5, 0}` → 测试重启恢复
- [ ] `= {12, 0}` (默认) → 测试
- [ ] `= {30, 0}` → 测试
- [ ] `= {60, 0}` → 测试
- [ ] `= {180, 0}` → 测试

**重启恢复测试步骤：**
1. 正常通信
2. 按 ESP32 RST 按钮
3. 计时到恢复通信
4. 重复 3 次取平均

---

## 🎯 第五天（可选）：扩展参数（6小时）

### 如果时间充足，测试以下参数：

#### Experiment 3.5: 读写者数量 (60 min)
- [ ] `NUM_STATEFUL_WRITERS/READERS = 4` → 测试
- [ ] `= 8` (默认) → 测试
- [ ] `= 16` → 测试
- [ ] `= 32` → 测试

#### Experiment 3.6: 代理数量 (60 min)
- [ ] `NUM_WRITER_PROXIES_PER_READER = 2` → 测试
- [ ] `= 6` (默认) → 测试
- [ ] `= 10` → 测试
- [ ] `= 15` → 测试

#### Experiment 3.7: 工作队列长度 (60 min)
- [ ] `THREAD_POOL_WORKLOAD_QUEUE_LENGTH = 10` → 测试
- [ ] `= 20` (默认) → 测试
- [ ] `= 50` → 测试
- [ ] `= 100` → 测试

#### 其他参数（根据时间选择）
- [ ] 3.8: 线程池大小
- [ ] 3.9: 主题名长度
- [ ] 3.10: 线程优先级

---

## 🎯 数据分析和画图（你自己完成，3-5天）

### 第一轮图表：基础对比

#### 必做图表
- [ ] **图1.1**: RTT 对比箱线图（3系统）
- [ ] **图1.2**: RTT 对比柱状图（带误差线）
- [ ] **图2.2**: Flow Graph 三系统对比
- [ ] **图2.6**: 架构对比示意图（三跳 vs 两跳）
- [ ] **图3.1**: HEARTBEAT 周期 vs RTT 曲线
- [ ] **图3.2**: HEARTBEAT 周期 vs 网络开销

#### 必做表格
- [ ] **表1**: 三系统性能对比总表
- [ ] **表2.1**: HEARTBEAT/ACKNACK 统计
- [ ] **表2.3**: TRANSIENT_LOCAL 验证结果
- [ ] **表3.1**: HEARTBEAT 周期实验汇总
- [ ] **表3.2**: History Depth 实验汇总

### 第二轮图表：深度分析

#### 进阶图表
- [ ] **图2.3**: RTT 延迟分布直方图
- [ ] **图2.4**: RTT 累积分布函数 (CDF)
- [ ] **图2.5**: TRANSIENT_LOCAL 时序图
- [ ] **图3.3**: History Depth vs 内存占用
- [ ] **图3.4**: History Depth vs Flash 大小
- [ ] **图3.5**: SPDP 周期 vs 冷启动时间

### 第三轮图表：综合分析

#### 高级图表
- [ ] **图3.总.1**: 参数影响热力图（10参数 × 4维度）
- [ ] **图3.总.2**: 场景化配置雷达图（4场景 × 6维度）

---

## 📊 最终检查清单

### 数据完整性
- [ ] 所有 pcapng 文件已保存并能打开
- [ ] 所有 CSV 文件已导出
- [ ] 所有截图清晰可读
- [ ] Excel 表格数据完整无缺失

### 文件组织
- [ ] `raw_data/` 目录包含所有原始数据
- [ ] `figures/` 目录包含所有截图
- [ ] `analysis/` 目录包含分析表格
- [ ] 文件命名规范一致

### 备份
- [ ] 所有数据已备份到外部硬盘/云盘
- [ ] 重要图表已复制到论文目录
- [ ] 实验笔记已整理

---

## 🎓 和导师讨论准备

### 准备材料
- [ ] 实验设计 PPT（10-15 页）
- [ ] 核心数据表格打印版
- [ ] 关键图表打印版
- [ ] 遇到的问题和解决方案笔记

### 讨论要点
1. **项目价值**
   - [ ] 能清楚解释为什么在 upstream 基础上加 QoS
   - [ ] 能量化说明性能提升（百分比）
   - [ ] 能对比 micro-ROS 的架构差异

2. **参数理解**
   - [ ] 能解释每个参数的作用机制
   - [ ] 能说明为什么选这些测试值
   - [ ] 能讨论 trade-off（延迟 vs 开销）

3. **实验方法**
   - [ ] 能解释为什么用 Wireshark
   - [ ] 能说明如何保证实验可重复性
   - [ ] 能讨论实验的局限性

### 预期问题准备
1. "为什么不直接用 micro-ROS？"
   - 答：架构对比数据 + Agent 开销分析

2. "QoS 扩展增加了多少成本？"
   - 答：+5.6% flash, RTT 基本持平

3. "这些参数调节有什么实际意义？"
   - 答：4 个场景化配置 + 应用场景分析

---

## ✅ 成功标志

### 最小成功（足够毕业论文）
- [x] 三系统 RTT 对比完成
- [x] 5 个 Wireshark 分析完成
- [x] 4 个核心参数实验完成
- [x] 8-10 张图表
- [x] 5-8 个数据表格

### 完整成功（可发表论文）
- [x] 以上全部
- [x] 10 个参数实验全部完成
- [x] 4 个场景化配置验证
- [x] 15-20 张图表
- [x] 10-15 个数据表格
- [x] 可重复的实验方法论

---

## 📞 紧急联系

### 遇到阻塞问题？
1. **先查**：`EXPERIMENTAL_PROCEDURE.md` 故障排查章节
2. **再查**：项目 README 和 GitHub Issues
3. **问人**：导师/同学/师兄师姐

### 时间不够？
**优先级排序：**
1. 核心：三系统对比 + HEARTBEAT 实验（必做）
2. 重要：Flow Graph + History Depth 实验
3. 加分：其他参数实验

---

**记住：实验是为了理解协议，不是为了凑数据。质量 > 数量！**

**Good luck! 加油！🚀**
