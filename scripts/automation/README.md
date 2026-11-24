# 自动化参数扫频实验系统

## 🎯 核心功能

已创建完整的自动化测试套件，支持 **挂夜跑** 的无人值守采集：

- ✅ 自动修改参数 → 编译 → 烧录 → 测试（N=30）
- ✅ tshark 后台自动抓包保存 pcapng
- ✅ 自动提取统计数据到 CSV/JSON
- ✅ 支持核心 4 参数的完整扫频实验

## 📂 文件结构

```
scripts/automation/
├── config.json           # 实验配置（参数定义、测试值）
├── param_sweep.sh        # 主控脚本：参数扫频
├── batch_test.sh         # N=30 重复测试
├── run_single_test.sh    # 单次测试 + tshark 抓包
└── modify_param.py       # 修改 config.h 参数
```

## 🚀 快速开始

### 1️⃣ 单参数测试（验证流程）

**心跳周期扫频**（~3 小时）：
```bash
cd ~/mROS2-QoS
./scripts/automation/param_sweep.sh heartbeat_period /dev/ttyUSB0 30
```

**历史深度扫频**（~4 小时）：
```bash
./scripts/automation/param_sweep.sh history_size /dev/ttyUSB0 30
```

### 2️⃣ 全部核心参数（挂夜跑，~15 小时）

创建一键运行脚本：
```bash
cat > run_all_sweeps.sh << 'EOF'
#!/bin/bash
set -euo pipefail

PARAMS=("heartbeat_period" "history_size" "spdp_period" "lease_duration")

for param in "${PARAMS[@]}"; do
    echo "========================================="
    echo "Starting sweep: ${param}"
    echo "========================================="
    
    ./scripts/automation/param_sweep.sh "${param}" /dev/ttyUSB0 30
    
    if [ $? -eq 0 ]; then
        echo "[OK] ${param} sweep completed"
    else
        echo "[FAIL] ${param} sweep failed"
    fi
    
    sleep 10
done

echo "All sweeps complete!"
EOF

chmod +x run_all_sweeps.sh
./run_all_sweeps.sh
```

## 📊 输出结果结构

```
results/param_sweep/
├── heartbeat_period/
│   ├── 100/                      # 心跳周期 = 100ms
│   │   ├── test_run1.pcapng      # Wireshark 抓包文件
│   │   ├── test_run1_serial.log  # 串口日志
│   │   ├── test_run1_stats.json  # 统计数据
│   │   ├── ... (run2 ~ run30)
│   │   ├── test_summary.csv      # 30 次汇总
│   │   └── test_aggregate.json   # 聚合统计（均值、标准差）
│   ├── 500/
│   ├── 1000/
│   ├── 2000/
│   ├── 4000/
│   └── 8000/
├── history_size/
│   ├── 3/
│   ├── 5/
│   ├── 10/
│   ├── 20/
│   ├── 30/
│   └── 50/
├── spdp_period/
│   └── ...
└── lease_duration/
    └── ...
```

## 🔍 手动部分（你负责）

### Wireshark 证据图（论文用）
```bash
# 打开 Wireshark GUI
wireshark results/param_sweep/heartbeat_period/100/test_run1.pcapng

# 需要手动截图：
1. Statistics → Flow Graph（数据流序列图）
2. Statistics → IO Graph（吞吐量曲线）
3. 过滤 HEARTBEAT：rtps.sm.id == 0x07
4. 过滤 ACKNACK：rtps.sm.id == 0x06
```

### 最终画图（Python/MATLAB）
```python
# 示例：读取聚合统计绘制对比图
import json
import matplotlib.pyplot as plt

params = [100, 500, 1000, 2000, 4000, 8000]
rtt_avgs = []
rtt_stds = []

for p in params:
    with open(f'results/param_sweep/heartbeat_period/{p}/test_aggregate.json') as f:
        data = json.load(f)
        rtt_avgs.append(data['rtt_avg']['mean'])
        rtt_stds.append(data['rtt_avg']['stdev'])

plt.errorbar(params, rtt_avgs, yerr=rtt_stds, marker='o')
plt.xlabel('Heartbeat Period (ms)')
plt.ylabel('RTT (ms)')
plt.title('RTT vs Heartbeat Period')
plt.savefig('rtt_vs_hb_period.pdf')
```

## 💡 参数配置

编辑 `scripts/automation/config.json` 修改测试值：

```json
{
  "parameters": {
    "heartbeat_period": {
      "values": [100, 500, 1000, 2000, 4000, 8000],
      "default": 4000
    },
    "history_size": {
      "values": [3, 5, 10, 20, 30, 50],
      "default": 10
    }
  }
}
```

## ⚙️ 高级选项

### 修改重复次数（默认 N=30）
```bash
# 快速验证用 N=5
./scripts/automation/param_sweep.sh heartbeat_period /dev/ttyUSB0 5

# 高置信度用 N=50
./scripts/automation/param_sweep.sh heartbeat_period /dev/ttyUSB0 50
```

### 修改单次测试时长（默认 75 秒）
编辑 `config.json`：
```json
"test_config": {
  "capture_duration": 90  // 改为 90 秒
}
```

### 暂停/恢复
```bash
# Ctrl+C 暂停
# 重新运行同一命令会从下一个参数值继续
```

## 🐛 故障排查

### 串口权限问题
```bash
sudo usermod -aG dialout $USER
# 退出重新登录
```

### ESP-IDF 环境未加载
```bash
source /export.sh
```

### tshark 权限问题
```bash
sudo setcap cap_net_raw,cap_net_admin=eip $(which tshark)
```

## 📋 检查清单

实验前：
- [ ] ESP32 已连接到 /dev/ttyUSB0
- [ ] 已安装 tshark（`which tshark`）
- [ ] 已配置 ROS2 Humble（`source /opt/ros/humble/setup.bash`）
- [ ] 磁盘空间充足（~50GB，每个 pcapng 约 100MB）

实验中：
- [ ] 不要断开 ESP32 USB 连接
- [ ] 不要关闭终端窗口
- [ ] 可以用 `tail -f results/param_sweep/heartbeat_period/*/test_aggregate.json` 监控进度

实验后：
- [ ] 检查 `test_aggregate.json` 确认成功率
- [ ] 用 Wireshark 打开代表性 pcapng 截图
- [ ] 运行分析脚本生成对比图

## 🎓 Artifact 评审加分项

✅ **可复现性**：
- 配置文件驱动，参数可调
- 完整的 pcapng 原始数据
- 自动化脚本可重现实验

✅ **统计显著性**：
- N=30 重复测试
- 提供均值、标准差、置信区间

✅ **专业性**：
- 使用标准工具（tshark, ROS2 CLI）
- 结构化数据输出（JSON, CSV）
- 完整日志链（串口、主机、抓包）
