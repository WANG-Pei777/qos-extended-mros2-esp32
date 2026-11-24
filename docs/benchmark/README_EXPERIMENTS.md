# 实验文档导航

## 📚 文档概览

本目录包含完整的实验设计和操作指南，用于证明 mROS2-QoS 项目的价值和性能优势。

---

## 🎯 核心文档

### 1. **WORKLOAD_PROTOCOL_READINESS_AUDIT_20260720.md** - 新工作负载门禁
- **内容**：大 payload、发布频率、DATA_FRAG、Agent、PCAP 和静态资源的工程审计
- **结论边界**：仅用于预注册前 readiness；N=1 smoke 不进入正式比较
- **硬门禁**：3270-run 能耗矩阵仍等待外接校准功耗仪与 GPIO 对齐

### 2. **IMPAIRMENT_EFFICACY_READINESS_AUDIT_20260720.md** - 网络注入效力审计
- **内容**：loss、burst、delay、jitter、reordering 的命令、PCAP、板端观测与清理闭环
- **结论边界**：host-to-board egress profile 可进入预注册审查；N=1 不作性能结论
- **剩余门禁**：外接功耗仪、正式存储空间和随机化冻结

### 3. **RESOURCE_WORKLOAD_IMPAIRMENT_PROTOCOL_DRAFT.md** - 扩展正式协议
- **内容**：CPU、heap、stack、能耗、payload/rate、impairment 与三系统矩阵
- **状态**：DRAFT；不授权正式采集
- **适用于**：功耗硬件到位后的预注册修订与协议冻结

### 4. **THREE_SYSTEM_FORMAL_RESULTS.md** - 三系统正式结果
- **内容**：300-run 预注册正式对比的审计、统计、PCAP/资源表、Origin 图和封存哈希
- **结论边界**：RTT 对比经 Holm 校正后均不显著；micro-ROS 在持续运行 Agent 条件下冷启动更快
- **适用于**：论文主文、补充材料、答辩和复现审查

### 5. **P4_FORMAL_RESULTS.md** - P4 独立时间窗复现
- **内容**：180-run RELIABLE/BEST_EFFORT 丢包复现的审计、统计、PCAP 与封存哈希
- **结论边界**：5% 和 nominal 15% 下 RELIABLE RTT p95 显著更高，15% 下无交付优势
- **适用于**：论文复现性主张和补充材料

### 6. **EXPERIMENT_DESIGN.md** - 实验总体设计
- **内容**：完整的实验方案设计
- **包括**：
  - 三系统对比矩阵（micro-ROS / upstream / mROS2-QoS）
  - 5 类基础实验（RTT、QoS功能、启动时间、资源占用、网络开销）
  - 5 个 Wireshark 分析任务
  - 10 个参数调节实验
  - 论文写作指导
- **适用于**：理解实验设计思路，和导师讨论方案

### 7. **PARAMETER_TUNING_EXPERIMENTS.md** - 参数调节详细说明
- **内容**：10 个 RTPS 参数的深入分析
- **包括**：
  - 每个参数的作用机制
  - 调节范围和预期影响
  - Wireshark 观察要点
  - 4 个场景化配置（低延迟/高可靠/低功耗/大规模）
- **适用于**：理解参数含义，准备和老师讨论"为什么这样调"

### 8. **EXPERIMENTAL_PROCEDURE.md** - 完整操作手册（⭐ 最重要）
- **内容**：1300 行详细的分步操作指南
- **包括**：
  - ✅ 每一步你需要执行的命令
  - 📊 每一步你需要记录的数据和画的图
  - ℹ️ 注意事项和背景说明
  - 故障排查指南
  - 快速参考附录
- **适用于**：实际执行实验时逐步跟随

---

## 📋 实验执行顺序

### **阶段 1：三系统基础对比**（2-3 小时）
1. 运行 mROS2-QoS 测试并抓包
2. 运行 upstream 测试并抓包
3. 运行 micro-ROS 测试并抓包
4. 记录 RTT 数据

📊 **你需要画**：RTT 对比箱线图、柱状图

### **阶段 2：Wireshark 深度分析**（3-4 小时）
1. RELIABLE vs BEST_EFFORT 对比（看 HEARTBEAT/ACKNACK）
2. Flow Graph 时序图（三系统对比）
3. RTT 延迟分布（导出 CSV）
4. TRANSIENT_LOCAL 晚加入验证
5. Agent 三跳可视化

📊 **你需要画**：协议对比图、延迟分布图、架构对比图

### **阶段 3：核心参数调节**（4-6 小时）
1. 心跳周期（6 个值）
2. 历史深度（6 个值）
3. SPDP 发现周期（5 个值）
4. 租约时长（5 个值）

📊 **你需要画**：参数影响曲线图、热力图

### **阶段 4（可选）：扩展参数**（4-6 小时）
5. 读写者数量
6. 代理数量
7. 工作队列长度
8. 线程池大小
9. 主题名长度
10. 线程优先级

📊 **你需要画**：场景化配置雷达图

---

## 🎓 向老师展示的关键点

### **1. 项目价值**
```
"300 次预注册正式对比表明：
- 三系统在清洁网络下均完成 100% 消息交付
- RTT p95 的三组差异经 Holm 校正后均不显著
- micro-ROS 在持续运行 Agent 条件下比两套 direct RTPS 更快就绪
- mROS2-QoS 的核心贡献应由 QoS 功能和受控丢包机制实验支撑，
  不使用早期 N=1 数据宣称普遍 RTT 优势"
```

早期 `20.7/21.6/27.5 ms` 数字仅是 pilot，不得作为正式论文结论。

### **2. 参数调节理解**
```
"我设计了 10 个参数调节实验：
- 核心 4 个：心跳周期、历史深度、发现周期、租约时长
- 扩展 6 个：读写者数量、代理数量、队列长度、线程池、主题名长度、线程优先级
- 4 个场景化配置：低延迟、高可靠、低功耗、大规模"
```

### **3. Wireshark 分析能力**
```
"我用 Wireshark 分析了：
- RELIABLE 模式的 HEARTBEAT/ACKNACK 机制
- 三系统的协议时序差异（Flow Graph）
- micro-ROS 的三跳架构 vs 我们的两跳直连
- TRANSIENT_LOCAL 的历史数据重传"
```

---

## 📊 预期产出

### **实验数据文件**
```
results/experiments_2026/
├── raw_data/          # 30+ pcapng 文件，10+ CSV 文件
├── figures/           # 20+ 截图和图表
└── analysis/          # Excel 数据汇总表格
```

### **论文素材**
- **5-8 张核心图表**：RTT 对比、Flow Graph、参数影响曲线
- **10-15 个数据表格**：性能对比、参数实验结果
- **完整的实验方法论**：可重复、可验证

### **论文章节结构建议**
```
4. Experimental Evaluation
   4.1 Experimental Setup
   4.2 Three-System Comparison
       - micro-ROS baseline
       - upstream mros2-esp32 baseline
       - mROS2-QoS performance
   4.3 QoS Feature Validation
       - RELIABLE vs BEST_EFFORT
       - TRANSIENT_LOCAL late-joiner
       - History depth enforcement
   4.4 Architecture Analysis
       - Network overhead comparison
       - Agent impact on latency
       - Direct DDS communication advantage

5. RTPS Parameter Tuning and Optimization
   5.1 Heartbeat Period Impact
   5.2 History Depth Optimization
   5.3 Discovery Period Tuning
   5.4 Lease Duration Analysis
   5.5 Multi-Parameter Optimization
   5.6 Scenario-Based Configuration Guidelines
```

---

## ⚡ 快速开始

### **第一次使用？从这里开始：**

1. **阅读实验设计**（20 分钟）
   ```bash
   cat EXPERIMENT_DESIGN.md
   ```

2. **准备环境**（10 分钟）
   ```bash
   cd ~/mROS2-QoS
   mkdir -p results/experiments_2026/{raw_data,figures,analysis}
   ls /dev/ttyUSB*  # 检查 ESP32 连接
   ```

3. **执行第一个实验**（30 分钟）
   - 打开 `EXPERIMENTAL_PROCEDURE.md`
   - 跟随 "实验 1A：mROS2-QoS 基线测试"
   - 逐步执行，记录数据

4. **成功标志**
   - 得到一个 pcapng 文件
   - 记录了 RTT 数据
   - 在 Wireshark 中看到了包

---

## 📞 获得帮助

### **遇到问题？**

1. **查看故障排查**：`EXPERIMENTAL_PROCEDURE.md` 末尾
2. **检查参数说明**：`PARAMETER_TUNING_EXPERIMENTS.md`
3. **回顾设计思路**：`EXPERIMENT_DESIGN.md`

### **常见问题快速索引**
- Wireshark 看不到包 → 检查防火墙和网卡
- 编译失败 → 检查 config.h 语法
- ESP32 连接问题 → 检查 /dev/ttyUSB*
- 测试超时 → 重启 ESP32 和 ROS2 节点

---

## 🎯 成功标准

### **实验完成的标志**

**最小完成集（足够论文）：**
- ✅ 三系统 RTT 对比数据
- ✅ 5 个 Wireshark 分析任务
- ✅ 4 个核心参数实验
- ✅ 10+ 张图表
- ✅ 5+ 个数据表格

**完整完成集（更有说服力）：**
- ✅ 以上全部
- ✅ 10 个参数实验
- ✅ 4 个场景化配置验证
- ✅ 20+ 张图表
- ✅ 15+ 个数据表格

---

## 📖 相关文档

### **项目核心文档**
- `../../README.md` - 项目主文档
- `../qos/QOS_IMPLEMENTATION_STATUS.md` - QoS 实现状态
- `../validation/RUNBOOK.md` - 硬件验证手册

### **其他基准测试**
- `BASELINE_POST_RELIABILITY_FIXES.md` - 可靠性修复后的基线
- `PHASE1_PERFORMANCE.md` - Phase 1 性能报告
- `MICROROS_COMPARISON_PROTOCOL.md` - micro-ROS 对比协议

---

## 💡 小贴士

### **提高效率**
1. **批量修改参数**：准备多个 config.h 副本
2. **自动化测试**：写脚本连续烧录和测试
3. **边做边记录**：不要等全部完成再整理数据
4. **定期备份**：pcapng 文件很大，及时备份

### **论文写作**
1. **先画图后写字**：图表准备好，文字自然流畅
2. **对比是关键**：所有结果都和 baseline 对比
3. **量化结果**：用百分比说明改进（-25% RTT, +5.6% flash）
4. **解释原因**：不只是"更快"，而是"因为直连无 Agent"

---

## 🚀 开始实验

**现在准备好了吗？**

```bash
cd ~/mROS2-QoS/docs/benchmark
cat EXPERIMENTAL_PROCEDURE.md  # 打开操作手册
```

**祝实验顺利！Remember: 老师看重的是你对协议的理解，而不只是数据本身。**

**Good luck! 加油！**
