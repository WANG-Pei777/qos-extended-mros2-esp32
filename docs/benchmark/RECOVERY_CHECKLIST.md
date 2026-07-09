# Board Recovery Checklist

**当前状态**: ESP32 watchdog deadlock (ReaderThread on CPU 1)  
**触发原因**: R3 reset storm run 9 - 多次快速重置后状态损坏  
**需要操作**: 硬件重置 + 固件重新烧录

---

## 立即恢复步骤

### 1. 重新烧录固件 (必需)

```bash
cd /home/wsde-47/mROS2-QoS/workspace/qos_eval
source ~/esp-idf/export.sh
idf.py -p /dev/ttyUSB0 flash monitor
```

**验收标准**:
- 串口输出显示 "mROS2 node initialized"
- 无 watchdog 错误
- 按 Ctrl+] 退出 monitor

### 2. 基线验证

```bash
cd /home/wsde-47/mROS2-QoS
bash scripts/validation/qos_flash.sh all /dev/ttyUSB0
```

期望输出: TX=40 RX=40 matched=1&1

---

## 恢复后实验序列

### Option A: 保守路线 (推荐)

```bash
# Step 1: R1@15% 效力探针 (20 min)
HOST_MODE=lossy:0.15 bash scripts/experiment/run_matrix.sh mros2qos efficacy_probe_15 5

# 判据: ≥4/5 runs 成功, RX ≤ TX
# 如果通过, 继续 Step 2; 否则降低 E2 丢包率范围

# Step 2: R4 E1 三系统对比 (1 hour)
# (每臂重新烧录, 降低崩溃风险)
bash scripts/experiment/run_e1_three_system.sh  # (需要创建此脚本)

# Step 3: R2 E2 正式采集 (4 hours)
bash scripts/experiment/run_e2_interleaved_v2.sh

# Step 4: R3 E3 reset storm (30 min, 降低到 N=10 如果仍崩溃)
HOST_MODE=external bash scripts/experiment/run_matrix.sh mros2qos reset_storm_postfix_v3 10
```

### Option B: 激进路线 (跳过 R1 重测)

直接执行 R4 → R3(N=10) → R2({0,1,5,10}%)

**风险**: E2 在 15% 丢包时可能失败率高

---

## 已修复的 Bug (本次会话)

### ✅ F1 External Mode Fix
- **文件**: scripts/experiment/run_matrix.sh
- **修复**: Lines 56-58 和 137 添加 HOST_MODE 检查
- **影响**: R3/E3 测试现在可以使用常驻 host

### ✅ F2 QoS Alignment
- **文件**: tools/echo_cpp/src/echo_node.cpp, workspace/qos_eval/main/app.cpp
- **修复**: 移除 deadline/lifespan 参数
- **影响**: 消除 "incompatible QoS" 警告

### ✅ F3 Efficacy Gate
- **文件**: scripts/experiment/run_e2_interleaved_v2.sh
- **修复**: Run 1 强制检查 Dropped>0
- **影响**: 防止无效注入产生虚假数据

---

## 未解决问题

### 🟡 RX > TX Counter Anomaly
- **现象**: R1 run1 RX=83 vs TX=40
- **可能原因**: RELIABLE QoS 重传被重复计数
- **临时方案**: 使用 HOST Dropped% 作为主指标
- **长期修复**: 需要在 app.cpp 添加序列号去重

### 🔴 Watchdog Deadlock Risk
- **触发条件**: 快速多次 reset (E3 设计)
- **缓解措施**: 
  1. 每个实验阶段间 power cycle
  2. E3 降低 runs 到 10 次
  3. 增加 watchdog timeout (需修改 app.cpp)

---

## 提交清单 (恢复后)

```bash
# 1. 提交 Round 2 修复
git add scripts/experiment/run_matrix.sh
git add tools/echo_cpp/src/echo_node.cpp
git add workspace/qos_eval/main/app.cpp
git add scripts/experiment/run_e2_interleaved_v2.sh
git commit -m "Round-2 remediation: HOST_MODE external fix, QoS alignment, efficacy gate

- F1: Fixed run_matrix.sh to preserve external host process
- F2: Removed deadline/lifespan from echo_cpp and app.cpp
- F3: Added injection efficacy gate to E2 driver

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"

# 2. 打标签
git tag -a v0.3.1-experiment-freeze -m "True freeze point: Round-2 remediation complete"
git push origin v0.3.1-experiment-freeze
```

---

**恢复完成后通知**: 告知 Claude "固件已恢复" 继续执行实验序列
