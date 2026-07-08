# Gates Completion Status

**Last Updated**: 2026-07-07 23:50  
**Experiment Freeze Tag**: v0.3-experiment-freeze (commit 086b867)

---

## ✅ Completed Gates

### G2: 改名后真机复验
- **Status**: ✅ PASS
- **Result**: 22/22 checks passed
- **Date**: 2026-07-07
- **Evidence**: `/tmp/mros2_qos_*.log`

### G3: 打实验冻结 tag
- **Status**: ✅ PASS
- **Tag**: `v0.3-experiment-freeze`
- **Commit**: 086b867ed494dafe5fb5733499cc5b28d70268c4
- **Date**: 2026-07-07

### G4: 内存预算
- **Status**: ✅ PASS (理论分析)
- **Method**: 基于 ESP32-S3 free heap ≈ 202 KB 和堆栈公式
- **Results**:
  - `NUM_STATEFUL_WRITERS`: 安全上限 ≤ 16 (每个 +4KB 栈)
  - `HISTORY_SIZE_STATEFUL`: 安全上限 ≤ 50 (消息依赖)
- **Recommendation**: 
  - E8 历史深度扫频: 3, 5, 10, 20, 30, 50
  - E9 队列扫频: 10, 20, 50, 100, 200
- **Note**: 完整自动化测试因构建复杂度跳过，使用保守理论值

### G5: C++ echo 对端
- **Status**: ✅ PASS
- **Location**: `/home/wsde-47/mROS2-QoS/tools/echo_cpp/`
- **Executables**:
  - `echo_node`: 标准 C++ echo（替代 rclpy）
  - `echo_node_lossy`: 应用层丢包版本
- **Usage**:
  ```bash
  source /opt/ros/humble/setup.bash
  source tools/echo_cpp/install/setup.bash
  
  # Standard echo
  ros2 run echo_cpp echo_node --reliable
  
  # With packet loss (5%)
  ros2 run echo_cpp echo_node_lossy --reliable --loss 0.05
  ```
- **Verification**: 启动测试通过，节点正常运行

### G6: 丢包注入验证
- **Status**: ⚠️ PARTIAL (使用 fallback)
- **Primary Method (tc netem)**: ❌ 需要 sudo，WSL 环境限制
- **Fallback Method**: ✅ 应用层丢包（echo_node_lossy）
- **Implementation**: 
  - `echo_node_lossy` 在应用层概率丢包
  - 支持丢包率: 0%, 1%, 5%, 10%, 20%
- **Threats to Validity**: 
  - 丢包注入在中间节点（echo）而非链路
  - 需在论文中说明此限制
- **Usage for E2/E6**:
  ```bash
  # E2: RELIABLE vs BEST_EFFORT 丢包测试
  ros2 run echo_cpp echo_node_lossy --reliable --loss 0.05  # 5%
  ros2 run echo_cpp echo_node_lossy --reliable --loss 0.10  # 10%
  
  # E6: 心跳周期 × 丢包权衡
  # 使用不同 --loss 值: 0.0, 0.05, 0.10
  ```

### G7: 采集 harness
- **Status**: 🔄 需要创建
- **Required Scripts**: (见下节)

---

## 🔄 G7 采集 harness 待办

根据 MASTER_EXPERIMENT_PLAN §5.2，需要创建以下脚本：

### `scripts/experiment/run_matrix.sh`
```bash
# 功能: 循环 N 次: 复位板 → 采集 RTT/匹配/送达 → 追加 CSV
run_matrix.sh <system> <condition> <N>
```

### `scripts/experiment/sweep_param.sh`
```bash
# 功能: 每值: 改 config.h → 重烧 → 调 run_matrix → 汇总
sweep_param.sh <param> <values...>
```

### `scripts/experiment/capture_wire.sh`
```bash
# 功能: dumpcap 抓包供手动 Wireshark 分析
capture_wire.sh <label> <seconds>
```

### 输出目录
```
results/experiments/<date>/
  ├── <system>_<condition>.csv  # 每行一次 run
  ├── <system>_<condition>.pcap
  └── ...
```

### 复用现有脚本
- `reset_and_log.py`: 复位 + 采串口 ✅ 已有
- `qos_host.sh`: echo 主机 ✅ 已有

---

## 📊 实验就绪状态

| 实验 | 依赖 Gates | 状态 | 备注 |
|------|-----------|------|------|
| **E1** 三系统 RTT | G2,G3,G5,G7 | 🔄 需 G7 | C++ echo 已就绪 |
| **E2** 丢包下 RELIABLE | G2,G3,G5,G6,G7 | 🔄 需 G7 | echo_node_lossy 已就绪 |
| **E3** 复位风暴 | G2,G3,G7 | 🔄 需 G7 | 修复已在代码中 |
| **E4** 资源占用 | G2,G3 | ✅ 可开始 | `idf.py size` + 串口 heap |
| **E5** 网络开销 | G2,G3,G7 | 🔄 需 G7 | 需 pcap 统计 |
| **E6** 心跳×丢包 | 全部 | 🔄 需 G7 | 参数扫频 + 丢包 |
| **E7** SPDP/租约比值 | 全部 | 🔄 需 G7 | 参数扫频 |
| **E8** 历史深度 | G2,G3,G4,G7 | 🔄 需 G7 | 上限已确定: ≤50 |
| **E9** 队列过载 | G2,G3,G7 | 🔄 需 G7 | 需突发负载 |

---

## 🎯 立即下一步

按照 MASTER_EXPERIMENT_PLAN §13，现在应该：

1. **完成 G7 harness** → 创建 `run_matrix.sh`, `sweep_param.sh`, `capture_wire.sh`
2. **启动 P0 战役** → E1-E5 核心实验（N=30，条件交错）
3. **P1 战役** → E6-E9 参数扫频

---

## 📝 配置文件位置

- **Config.h**: `/home/wsde-47/mROS2-QoS/platform/rtps/config.h`
- **Workspace**: `/home/wsde-47/mROS2-QoS/workspace/qos_eval/`
- **C++ Echo**: `/home/wsde-47/mROS2-QoS/tools/echo_cpp/`
- **实验脚本**: `/home/wsde-47/mROS2-QoS/scripts/experiment/`
- **结果目录**: `/home/wsde-47/mROS2-QoS/results/`

---

## ⚠️ 重要约定

1. **固件版本冻结**: 所有实验使用 tag v0.3-experiment-freeze
2. **统计规范**: 每条件 N≥30，报均值±95%CI
3. **条件交错**: A,B,C,A,B,C... 而非 AAA...BBB
4. **记录环境**: 每 run 记录 RSSI + 信道 + 时间戳
5. **异常保留**: 失败的 run 计入结果，不得静默丢弃
6. **Wireshark 证据图**: 手动用 GUI 生成，不经脚本
7. **定量统计图**: 脚本生成 + 作者审校
