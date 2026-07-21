# 完整实验操作手册 - 分步执行指南

## 📋 实验概览

本手册包含完整的实验流程，分为三大部分：
1. **三系统基础对比**（micro-ROS / upstream / mROS2-QoS）
2. **Wireshark 深度分析**（5 个分析任务）
3. **参数调节实验**（10 个参数）

**约定**：
- ✅ **你执行**：需要你手动操作的步骤
- 📊 **你分析**：需要你提取数据、画图的部分
- ℹ️ **说明**：背景信息和注意事项

---

# 第一部分：三系统基础对比

## 准备工作

### ✅ 步骤 0.1：检查环境

```bash
# 检查 ESP32 连接
ls /dev/ttyUSB*

# 检查 ROS2 环境
source /opt/ros/humble/setup.bash
ros2 topic list

# 检查 Wireshark 安装
wireshark --version
```

### ✅ 步骤 0.2：创建实验数据目录

```bash
cd ~/mROS2-QoS
mkdir -p results/experiments_2026
cd results/experiments_2026

# 创建子目录
mkdir -p 1_system_comparison
mkdir -p 2_wireshark_analysis
mkdir -p 3_parameter_tuning
mkdir -p raw_data
mkdir -p figures
```

---

## 实验 1A：mROS2-QoS (RELIABLE) 基线测试

### ✅ 步骤 1A.1：启动 Wireshark 抓包

**在 Windows 上打开 Wireshark：**

1. 双击 Wireshark 图标
2. 选择网络适配器（通常是 "以太网" 或 eth1）
3. 在 "Capture Filter" 输入框输入：
   ```
   udp portrange 7400-7420
   ```
4. 点击蓝色鲨鱼鳍图标（或按 Ctrl+E）开始抓包
5. **不要关闭 Wireshark，让它持续抓包**

### ✅ 步骤 1A.2：运行测试

**在 WSL 终端执行：**

```bash
cd ~/mROS2-QoS
source /opt/ros/humble/setup.bash

# 运行完整验证测试
./scripts/validation/qos_verify.sh /dev/ttyUSB0
```

**等待测试完成**（约 30-40 秒），看到：
```
[verify] RESULT: PASS
```

### ✅ 步骤 1A.3：停止 Wireshark 并保存

1. 回到 Wireshark 窗口
2. 点击红色方块图标（或按 Ctrl+E）停止抓包
3. File → Save As
4. 文件名：`capture_mros2qos_reliable.pcapng`
5. 保存位置：`\\wsl.localhost\Ubuntu-22.04\home\wsde-47\mROS2-QoS\results\experiments_2026\raw_data\`
6. 点击 "Save"

### 📊 步骤 1A.4：记录基础数据

**打开你准备的 Excel/表格，记录以下数据：**

从测试输出中找到：
```
RTT Results:
  Min: XX.XX ms
  Avg: XX.XX ms
  Max: XX.XX ms
  Median: XX.XX ms
  Valid samples: 40/40
```

**记录到表格：**
| 系统 | RTT min | RTT avg | RTT max | 丢包数 |
|------|---------|---------|---------|--------|
| mROS2-QoS | ___ | ___ | ___ | 0 |

---

## 实验 1B：upstream (BEST_EFFORT) 对比测试

### ✅ 步骤 1B.1：切换到 upstream 测试环境

```bash
cd ~/mROS2-QoS/upstream_bench
source /opt/ros/humble/setup.bash
```

### ✅ 步骤 1B.2：启动 Wireshark 抓包

**重复步骤 1A.1**（重新开始抓包）

### ✅ 步骤 1B.3：运行 upstream 测试

```bash
python3 test_upstream_rtt.py
```

**等待测试完成**（约 40 秒）

### ✅ 步骤 1B.4：停止 Wireshark 并保存

保存为：`capture_upstream_besteffort.pcapng`

### 📊 步骤 1B.5：记录数据

从输出中提取 RTT 数据，记录到表格：
| 系统 | RTT min | RTT avg | RTT max | 丢包数 |
|------|---------|---------|---------|--------|
| upstream | ___ | ___ | ___ | ___ |

---

## 实验 1C：micro-ROS 对比测试

### ✅ 步骤 1C.1：启动 micro-ROS Agent

**打开新的 WSL 终端：**

```bash
# 终端 1：启动 Agent
cd ~
micro_ros_agent udp4 --port 7408

# 保持这个终端运行
```

### ✅ 步骤 1C.2：烧录 micro-ROS 固件

**打开另一个 WSL 终端：**

```bash
# 终端 2：烧录固件
cd ~/mROS2-QoS/microros_bench/micro_ros_espidf_component/examples/int32_publisher
idf.py flash monitor
```

**等待烧录完成并看到连接 Agent 的日志**

### ✅ 步骤 1C.3：启动 Wireshark 抓包

**重复步骤 1A.1**（注意：这次会抓到 Agent 相关流量）

### ✅ 步骤 1C.4：运行 micro-ROS 测试

**打开第三个 WSL 终端：**

```bash
# 终端 3：运行测试脚本
cd ~/mROS2-QoS/microros_bench
source /opt/ros/humble/setup.bash
python3 test_microros_rtt.py
```

### ✅ 步骤 1C.5：停止 Wireshark 并保存

保存为：`capture_microros_agent.pcapng`

### 📊 步骤 1C.6：记录数据

| 系统 | RTT min | RTT avg | RTT max | 丢包数 |
|------|---------|---------|---------|--------|
| micro-ROS | ___ | ___ | ___ | ___ |

### ✅ 步骤 1C.7：关闭 Agent

回到终端 1，按 Ctrl+C 停止 Agent

---

## 📊 阶段性总结：你需要完成的分析

### 数据文件清单

你现在应该有：
- [ ] `capture_mros2qos_reliable.pcapng`
- [ ] `capture_upstream_besteffort.pcapng`
- [ ] `capture_microros_agent.pcapng`
- [ ] Excel 表格中有三个系统的 RTT 数据

### 你需要画的图

**图 1.1：RTT 对比箱线图**
- X 轴：三个系统
- Y 轴：RTT (ms)
- 数据：从你的表格中获取 min/avg/max

**图 1.2：RTT 对比柱状图**
- 并排柱状图
- 显示 avg RTT，误差线显示 min-max 范围

---

# 第二部分：Wireshark 深度分析

## 分析任务 2A：RELIABLE vs BEST_EFFORT 对比

### ✅ 步骤 2A.1：打开 mROS2-QoS 抓包

1. 打开 Wireshark
2. File → Open
3. 选择 `capture_mros2qos_reliable.pcapng`

### ✅ 步骤 2A.2：查看所有 RTPS 包

在顶部显示过滤器输入框输入：
```
rtps
```

按 Enter，你应该看到蓝色背景的包列表

### ✅ 步骤 2A.3：过滤 HEARTBEAT 包

显示过滤器改为：
```
rtps.sm.id == 0x07
```

**观察：**
- 有多少个 HEARTBEAT 包？（看底部状态栏 "Displayed: XXX"）
- 包之间的时间间隔是多少？（看 Time 列）

### 📊 步骤 2A.4：记录 HEARTBEAT 统计

**方法 1：手动计数**
- 看 Wireshark 底部状态栏："Displayed: XXX packets"

**方法 2：导出列表**
- File → Export Packet Dissections → As CSV
- 保存为：`heartbeat_mros2qos.csv`
- **你需要**：在 Excel 中打开，统计包数和时间间隔

### ✅ 步骤 2A.5：过滤 ACKNACK 包

显示过滤器改为：
```
rtps.sm.id == 0x06
```

**观察：**
- 有多少个 ACKNACK 包？
- 这些包出现在什么时候？（测试开始/结束？）

### 📊 步骤 2A.6：记录 ACKNACK 统计

同样导出为 CSV：`acknack_mros2qos.csv`

### ✅ 步骤 2A.7：对比 upstream BEST_EFFORT

1. 打开 `capture_upstream_besteffort.pcapng`
2. 应用同样的过滤器：`rtps.sm.id == 0x07`
3. **观察**：应该看到很少或没有 HEARTBEAT 包

### 📊 步骤 2A.8：截图保存

**截图 1**：mROS2-QoS 的 HEARTBEAT 列表
- 显示过滤器：`rtps.sm.id == 0x07`
- 确保能看到包列表和底部统计
- 保存为：`fig_heartbeat_reliable.png`

**截图 2**：upstream 的包列表（无 HEARTBEAT）
- 同样过滤器
- 保存为：`fig_no_heartbeat_besteffort.png`

### 📊 你需要做的分析

**表 2.1：HEARTBEAT/ACKNACK 统计对比**
| 系统 | HEARTBEAT 数 | ACKNACK 数 | 平均间隔 (ms) |
|------|-------------|-----------|--------------|
| mROS2-QoS | ___ | ___ | ___ |
| upstream | ___ | ___ | ___ |

**图 2.1：并排对比图**
- 左：mROS2-QoS 有 HEARTBEAT
- 右：upstream 无 HEARTBEAT
- 用你的截图

---

## 分析任务 2B：Flow Graph 时序图

### ✅ 步骤 2B.1：打开 mROS2-QoS 抓包

```
File → Open → capture_mros2qos_reliable.pcapng
```

### ✅ 步骤 2B.2：选择时间窗口

显示过滤器：
```
frame.time_relative > 10 && frame.time_relative < 20
```

这样只看测试中间的 10 秒，避免启动和结束的干扰

### ✅ 步骤 2B.3：生成 Flow Graph

1. 菜单：Statistics → Flow Graph
2. 在弹出窗口中：
   - Flow type: 选择 "All Flows"
   - ✅ 勾选 "Limit to display filter"
3. 点击 OK

### ✅ 步骤 2B.4：调整显示

在 Flow Graph 窗口中：
- 可以滚动查看完整的时序
- 左右两列是 IP 地址（ESP32 和 Host）
- 中间箭头是消息流向

### 📊 步骤 2B.5：截图保存

**截图 3**：mROS2-QoS Flow Graph
- 选择一个有代表性的片段（包含 DATA + HEARTBEAT + ACKNACK）
- 保存为：`fig_flowgraph_reliable.png`

### ✅ 步骤 2B.6：重复 upstream

1. 打开 `capture_upstream_besteffort.pcapng`
2. 同样的时间过滤器
3. Statistics → Flow Graph

### 📊 步骤 2B.7：截图保存

**截图 4**：upstream Flow Graph
- 应该只看到 DATA 包，没有 HEARTBEAT/ACKNACK
- 保存为：`fig_flowgraph_besteffort.png`

### ✅ 步骤 2B.8：重复 micro-ROS

1. 打开 `capture_microros_agent.pcapng`
2. **注意**：这次会看到三个 IP（ESP32 / Agent / ROS2 Host）
3. Statistics → Flow Graph

### 📊 步骤 2B.9：截图保存

**截图 5**：micro-ROS Flow Graph
- **关键**：标注出 Agent 的位置
- 显示三跳：ESP32 → Agent → Host
- 保存为：`fig_flowgraph_microros_agent.png`

### 📊 你需要做的图

**图 2.2：三系统时序对比图**
- 3 张 Flow Graph 并排或上下排列
- 标注关键差异：
  - mROS2-QoS：两跳 + HEARTBEAT
  - upstream：两跳无 HEARTBEAT
  - micro-ROS：三跳（Agent）

---

## 分析任务 2C：RTT 延迟分布

### ✅ 步骤 2C.1：打开 mROS2-QoS 抓包

### ✅ 步骤 2C.2：添加 Delta Time 列

1. 右键点击列标题区域（No. / Time / Source 那一行）
2. 选择 "Column Preferences"
3. 点击左下角 "+" 按钮添加新列
4. 填写：
   - Title: `Delta`
   - Type: 选择 "Delta time displayed"
   - Fields: `frame.time_delta_displayed`
5. 点击 OK

现在你应该看到新的 Delta 列，显示每个包和前一个包的时间差

### ✅ 步骤 2C.3：改变时间显示格式

菜单：View → Time Display Format → Seconds Since Previous Displayed Packet

### ✅ 步骤 2C.4：过滤特定方向的包

显示过滤器（只看 ESP32 → Host）：
```
ip.src == 192.0.2.1 && udp
```

**注意**：把 `192.0.2.1` 改成你的 ESP32 实际 IP

### 📊 步骤 2C.5：导出延迟数据

1. File → Export Packet Dissections → As CSV
2. 保存为：`rtt_deltas_mros2qos.csv`
3. **你需要**：在 Excel/Python 中分析这个 CSV
   - 找到 Time 列或 Delta 列
   - 计算统计数据（均值、标准差、分位数）
   - 画直方图或箱线图

### ✅ 步骤 2C.6：使用 IO Graph

1. Statistics → I/O Graph
2. 在 Y 轴设置中：
   - 点击 "Y Axis" 下拉菜单
   - 选择 "AVG(*)"
   - 在旁边的 "Y Field" 输入：`frame.time_delta_displayed`
3. X 轴间隔：改为 "1 sec"
4. 应用显示过滤器：`ip.src == 192.0.2.1 && udp`

### 📊 步骤 2C.7：截图 IO Graph

**截图 6**：mROS2-QoS 延迟曲线
- 保存为：`fig_iograph_rtt_mros2qos.png`

### ✅ 步骤 2C.8：重复其他两个系统

重复步骤 2C.1 - 2C.7，分别处理：
- `capture_upstream_besteffort.pcapng`
- `capture_microros_agent.pcapng`

保存为：
- `rtt_deltas_upstream.csv`
- `rtt_deltas_microros.csv`
- `fig_iograph_rtt_upstream.png`
- `fig_iograph_rtt_microros.png`

### 📊 你需要做的分析

**图 2.3：RTT 延迟分布直方图**
- 3 个系统的直方图叠加或并排
- X 轴：RTT (ms)
- Y 轴：频数

**图 2.4：RTT 累积分布函数 (CDF)**
- 显示 P50, P95, P99 分位数

**表 2.2：延迟统计详细数据**
| 系统 | Mean | Std | P50 | P95 | P99 |
|------|------|-----|-----|-----|-----|
| mROS2-QoS | ___ | ___ | ___ | ___ | ___ |
| upstream | ___ | ___ | ___ | ___ | ___ |
| micro-ROS | ___ | ___ | ___ | ___ | ___ |

---

## 分析任务 2D：TRANSIENT_LOCAL 晚加入验证

ℹ️ **这个实验需要重新运行，不能用之前的抓包**

### ✅ 步骤 2D.1：修改测试脚本（准备晚加入场景）

创建一个新的测试脚本：

```bash
cd ~/mROS2-QoS
nano scripts/test_late_joiner.py
```

粘贴以下内容：

```python
#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import time

class LateJoinerTest(Node):
    def __init__(self):
        super().__init__('late_joiner_subscriber')
        # 延迟 15 秒后才创建订阅者
        time.sleep(15)
        print(">>> [15s later] Creating subscriber now...")
        
        self.subscription = self.create_subscription(
            String,
            '/qos_eval',
            self.callback,
            10
        )
        self.msg_count = 0

    def callback(self, msg):
        self.msg_count += 1
        print(f"[Received #{self.msg_count}] {msg.data}")

def main():
    rclpy.init()
    node = LateJoinerTest()
    print(">>> Subscriber will start in 15 seconds...")
    print(">>> ESP32 should be publishing now!")
    
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
```

保存（Ctrl+O, Enter, Ctrl+X）并添加执行权限：

```bash
chmod +x scripts/test_late_joiner.py
```

### ✅ 步骤 2D.2：烧录固件（确保使用 TRANSIENT_LOCAL）

确认 `workspace/qos_eval/main.cpp` 中发布者使用 TRANSIENT_LOCAL：

```bash
cd ~/mROS2-QoS
grep -A 5 "Durability" workspace/qos_eval/main/main.cpp
```

应该看到：
```cpp
pub_qos.durability = TRANSIENT_LOCAL_DURABILITY_QOS;
```

如果不是，需要修改并重新烧录：

```bash
cd workspace/qos_eval
idf.py build flash
```

### ✅ 步骤 2D.3：启动 Wireshark 抓包

按照之前的步骤启动 Wireshark，过滤器：`udp portrange 7400-7420`

### ✅ 步骤 2D.4：启动 ESP32 发布

**按 ESP32 的 RST 按钮重启**，应该看到开始发布消息

### ✅ 步骤 2D.5：运行晚加入订阅者

**等 ESP32 启动完成后**（约 10 秒），运行：

```bash
cd ~/mROS2-QoS
source /opt/ros/humble/setup.bash
python3 scripts/test_late_joiner.py
```

你会看到：
```
>>> Subscriber will start in 15 seconds...
>>> ESP32 should be publishing now!
```

**等待 15 秒**，然后：

```
>>> [15s later] Creating subscriber now...
[Received #1] ...
[Received #2] ...
...
```

### ✅ 步骤 2D.6：观察 ESP32 日志

在另一个终端监控 ESP32：

```bash
cd ~/mROS2-QoS/workspace/qos_eval
idf.py monitor
```

找到类似的日志：
```
[TRANSIENT_LOCAL] Late joiner detected
[TRANSIENT_LOCAL] Sending cached history: 5/5 samples
```

### ✅ 步骤 2D.7：停止 Wireshark 并保存

保存为：`capture_transient_local_late_joiner.pcapng`

### ✅ 步骤 2D.8：在 Wireshark 中验证

1. 打开刚保存的 pcapng
2. 显示过滤器：`rtps`
3. 找到订阅者加入的时刻（看 Time 列，约 15-20 秒附近）
4. 在那个时刻附近应该看到：
   - ACKNACK 包（订阅者宣告加入）
   - HEARTBEAT 包（发布者响应）
   - 多个 DATA 包（历史数据重传）

### ✅ 步骤 2D.9：查看 DATA 序列号

1. 点击一个 DATA 包
2. 展开中间窗格的协议树：
   ```
   Real-Time Publish-Subscribe Protocol
     └─ Submessage: DATA
         └─ writerSeqNumber: XXX
   ```
3. 检查历史数据的序列号是否是旧的（比当前序列号小）

### 📊 步骤 2D.10：截图证据

**截图 7**：晚加入时刻的包列表
- 显示 ACKNACK 后跟随的多个 DATA 包
- 保存为：`fig_transient_local_packets.png`

**截图 8**：DATA 包的序列号详情
- 展开 RTPS 协议树，显示 writerSeqNumber
- 保存为：`fig_transient_local_seqnum.png`

**截图 9**：ESP32 日志
- 显示 "Sending cached history" 的日志
- 保存为：`fig_transient_local_esp32_log.png`

### 📊 你需要做的分析

**表 2.3：TRANSIENT_LOCAL 验证结果**
| 指标 | 结果 |
|------|------|
| ESP32 发布消息数（晚加入前） | ___ |
| 晚加入订阅者收到历史消息数 | ___ |
| 历史缓存深度（ESP32 日志） | ___ /  ___ |
| Wireshark 看到的重传 DATA 包数 | ___ |

**图 2.5：TRANSIENT_LOCAL 时序图**
- 标注三个阶段：
  1. ESP32 发布（无订阅者）
  2. 订阅者加入（ACKNACK）
  3. 历史数据重传（多个 DATA）

---

## 分析任务 2E：Agent 三跳可视化

ℹ️ **使用之前的 micro-ROS 抓包**

### ✅ 步骤 2E.1：打开 micro-ROS 抓包

```
File → Open → capture_microros_agent.pcapng
```

### ✅ 步骤 2E.2：识别三个 IP 地址

显示过滤器：`udp`

在包列表中查看 Source 和 Destination 列，你应该看到 3 个不同的 IP：

1. **ESP32 IP**：通常是 `10.x.x.x` 或 `192.168.x.x`（设备 IP）
2. **Agent IP**：WSL2 的 IP（通常和 Host 相同或相近）
3. **ROS2 Host IP**：可能和 Agent 相同（如果 Agent 和 ROS2 在同一个 WSL）

### 📊 步骤 2E.3：记录 IP 地址

| 角色 | IP 地址 |
|------|---------|
| ESP32 | ___ |
| Agent | ___ |
| ROS2 Host | ___ |

### ✅ 步骤 2E.4：查看 Conversations

1. Statistics → Conversations
2. 选择 "UDP" 标签
3. 你应该看到多个对话：
   - ESP32 ↔ Agent（XRCE-DDS 流量）
   - Agent ↔ ROS2 Host（DDS/RTPS 流量）

### 📊 步骤 2E.5：截图 Conversations

**截图 10**：Conversations 窗口
- 显示所有 UDP 对话
- 保存为：`fig_microros_conversations.png`

### ✅ 步骤 2E.6：生成 Flow Graph

1. 选择时间窗口：`frame.time_relative > 5 && frame.time_relative < 15`
2. Statistics → Flow Graph
3. ✅ 勾选 "Limit to display filter"
4. 观察三个节点之间的消息流动

### 📊 步骤 2E.7：截图 Flow Graph

**截图 11**：micro-ROS 三跳时序图
- 用不同颜色标注 ESP32 / Agent / ROS2 Host
- 保存为：`fig_microros_three_hop_flowgraph.png`

### ✅ 步骤 2E.8：对比 mROS2-QoS

1. 打开 `capture_mros2qos_reliable.pcapng`
2. Statistics → Conversations → UDP
3. 应该只看到 2 个节点：ESP32 ↔ ROS2 Host

### 📊 步骤 2E.9：截图对比

**截图 12**：mROS2-QoS Conversations
- 显示只有两个节点
- 保存为：`fig_mros2qos_conversations.png`

### 📊 你需要做的图

**图 2.6：架构对比示意图**
- 左：micro-ROS（ESP32 → Agent → ROS2，3 跳）
- 右：mROS2-QoS（ESP32 ⇄ ROS2，2 跳）
- 用你的 Conversations 截图作为证据

**表 2.4：网络跳数对比**
| 系统 | 跳数 | 架构 | 延迟影响 |
|------|------|------|---------|
| micro-ROS | 3 | ESP32 → Agent → ROS2 | 更高 |
| mROS2-QoS | 2 | ESP32 ⇄ ROS2 | 更低 |
| upstream | 2 | ESP32 ⇄ ROS2 | 更低 |

---

# 第三部分：参数调节实验

## 准备工作

### ✅ 步骤 3.0：创建参数实验记录表格

在 Excel 中创建以下表格模板：

**表 3.0：参数实验汇总**
| 实验编号 | 参数名 | 参数值 | RTT avg | RTT std | 包数统计 | 备注 |
|---------|--------|--------|---------|---------|---------|------|
| 3.1.1 | HB_PERIOD | 100 | ___ | ___ | ___ | |
| 3.1.2 | HB_PERIOD | 500 | ___ | ___ | ___ | |
| ... | ... | ... | ... | ... | ... | |

---

## 实验 3.1：心跳周期调节（最重要）

### 参数说明
- **文件位置**：`~/mROS2-QoS/platform/rtps/config.h`
- **参数行号**：第 90 行
- **参数名**：`SF_WRITER_HB_PERIOD_MS`
- **默认值**：4000 ms
- **测试值**：100, 500, 1000, 2000, 4000, 8000 ms

### ✅ 步骤 3.1.1：备份原始配置

```bash
cd ~/mROS2-QoS
cp platform/rtps/config.h platform/rtps/config.h.backup
```

### ✅ 步骤 3.1.2：修改参数（第一个值：100ms）

```bash
nano platform/rtps/config.h
```

找到第 90 行：
```c
const uint16_t SF_WRITER_HB_PERIOD_MS = 4000;
```

改为：
```c
const uint16_t SF_WRITER_HB_PERIOD_MS = 100;
```

保存（Ctrl+O, Enter, Ctrl+X）

### ✅ 步骤 3.1.3：编译并烧录

```bash
cd ~/mROS2-QoS/workspace/qos_eval
idf.py build flash
```

**等待编译和烧录完成**（约 2-3 分钟）

### ✅ 步骤 3.1.4：启动 Wireshark 抓包

按照第一部分的步骤启动 Wireshark，过滤器：`udp portrange 7400-7420`

### ✅ 步骤 3.1.5：运行测试

```bash
cd ~/mROS2-QoS
source /opt/ros/humble/setup.bash
./scripts/validation/qos_verify.sh /dev/ttyUSB0
```

### ✅ 步骤 3.1.6：停止 Wireshark 并保存

保存为：`capture_hb_100ms.pcapng`

### 📊 步骤 3.1.7：记录数据

| 参数值 | RTT min | RTT avg | RTT max | HEARTBEAT 数 |
|--------|---------|---------|---------|-------------|
| 100 ms | ___ | ___ | ___ | ___ |

### ✅ 步骤 3.1.8：重复其他值

**重复步骤 3.1.2 - 3.1.7，依次测试：**
- 500 ms → `capture_hb_500ms.pcapng`
- 1000 ms → `capture_hb_1000ms.pcapng`
- 2000 ms → `capture_hb_2000ms.pcapng`
- 4000 ms → `capture_hb_4000ms.pcapng`（默认值）
- 8000 ms → `capture_hb_8000ms.pcapng`

### ✅ 步骤 3.1.9：恢复默认值

```bash
cd ~/mROS2-QoS
cp platform/rtps/config.h.backup platform/rtps/config.h
```

### 📊 你需要做的分析

**图 3.1：HEARTBEAT 周期 vs RTT**
- X 轴：HEARTBEAT 周期 (ms)
- Y 轴：RTT avg (ms)
- 折线图 + 误差线

**图 3.2：HEARTBEAT 周期 vs 网络开销**
- X 轴：HEARTBEAT 周期 (ms)
- Y 轴：HEARTBEAT 包数 / 测试时长
- 柱状图

**表 3.1：HEARTBEAT 周期实验汇总**
| 周期 (ms) | RTT avg | HEARTBEAT 数 | 总包数 | 总字节数 | 结论 |
|----------|---------|-------------|--------|---------|------|
| 100 | ___ | ___ | ___ | ___ | 低延迟，高开销 |
| 500 | ___ | ___ | ___ | ___ | |
| 1000 | ___ | ___ | ___ | ___ | |
| 2000 | ___ | ___ | ___ | ___ | |
| 4000 | ___ | ___ | ___ | ___ | 默认配置 |
| 8000 | ___ | ___ | ___ | ___ | 高延迟，低开销 |

---

## 实验 3.2：历史深度调节

### 参数说明
- **参数行号**：第 80 行
- **参数名**：`HISTORY_SIZE_STATEFUL`
- **默认值**：10
- **测试值**：3, 5, 10, 20, 30, 50

### ✅ 步骤 3.2.1：修改参数（第一个值：3）

```bash
nano platform/rtps/config.h
```

找到第 80 行：
```c
const uint8_t HISTORY_SIZE_STATEFUL = 10;
```

改为：
```c
const uint8_t HISTORY_SIZE_STATEFUL = 3;
```

### ✅ 步骤 3.2.2：编译烧录并测试

```bash
cd workspace/qos_eval
idf.py build flash

cd ~/mROS2-QoS
source /opt/ros/humble/setup.bash
./scripts/validation/qos_verify.sh /dev/ttyUSB0
```

### 📊 步骤 3.2.3：检查 ESP32 日志

在输出中找到：
```
[QoS] History cache: X/3 samples
```

记录 X 的值（实际使用的缓存数量）

### ✅ 步骤 3.2.4：晚加入测试（可选，针对 depth >= 5）

如果时间充足，用之前创建的 `test_late_joiner.py` 测试：

1. ESP32 重启后发布 10+ 条消息
2. 运行晚加入订阅者
3. 记录收到多少历史消息（应该 <= depth）

### ✅ 步骤 3.2.5：重复其他值

依次测试：3, 5, 10, 20, 30, 50

### 📊 你需要做的分析

**图 3.3：History Depth vs 内存占用**
- X 轴：History depth
- Y 轴：Free heap (KB)
- 从 ESP32 日志中提取 free heap 数据

**图 3.4：History Depth vs Flash 大小**
- X 轴：History depth
- Y 轴：Binary size (KB)
- 从编译输出中提取（`idf.py size`）

**表 3.2：History Depth 实验汇总**
| Depth | 晚加入收到 | Free Heap | Flash Size | 备注 |
|-------|----------|-----------|------------|------|
| 3 | ___ | ___ | ___ | 最小配置 |
| 5 | ___ | ___ | ___ | |
| 10 | ___ | ___ | ___ | 默认配置 |
| 20 | ___ | ___ | ___ | |
| 30 | ___ | ___ | ___ | |
| 50 | ___ | ___ | ___ | 大缓存 |

---

## 实验 3.3：SPDP 发现周期

### 参数说明
- **参数行号**：第 91 行
- **参数名**：`SPDP_RESEND_PERIOD_MS`
- **默认值**：1000 ms
- **测试值**：250, 500, 1000, 2000, 5000 ms

### ✅ 步骤 3.3.1：准备测量冷启动时间

创建测试脚本：

```bash
nano scripts/measure_cold_start.sh
```

粘贴：

```bash
#!/bin/bash
echo "Resetting ESP32..."
./scripts/validation/qos_verify.sh /dev/ttyUSB0 | grep -E "(match|discovery|first)" | head -5
```

保存并添加执行权限：

```bash
chmod +x scripts/measure_cold_start.sh
```

### ✅ 步骤 3.3.2：修改参数并测试

对每个值：
1. 修改 `SPDP_RESEND_PERIOD_MS`
2. 编译烧录
3. 运行测试并记录启动时间

### 📊 你需要做的分析

**图 3.5：SPDP 周期 vs 冷启动时间**
- X 轴：SPDP 周期 (ms)
- Y 轴：启动到首次通信 (s)

**表 3.3：SPDP 周期实验汇总**
| 周期 (ms) | 冷启动时间 | SPDP 包数/60s | 结论 |
|----------|-----------|--------------|------|
| 250 | ___ | ___ | 快速发现 |
| 500 | ___ | ___ | |
| 1000 | ___ | ___ | 默认配置 |
| 2000 | ___ | ___ | |
| 5000 | ___ | ___ | 慢发现 |

---

## 实验 3.4：租约时长

### 参数说明
- **参数行号**：第 97-98 行
- **参数名**：`SPDP_DEFAULT_REMOTE_LEASE_DURATION`
- **默认值**：{12, 0} 秒
- **测试值**：{5,0}, {12,0}, {30,0}, {60,0}, {180,0}

### ✅ 步骤 3.4.1：修改参数

```bash
nano platform/rtps/config.h
```

找到：
```c
const Duration_t SPDP_DEFAULT_REMOTE_LEASE_DURATION = {12, 0};
```

改为（例如 5 秒）：
```c
const Duration_t SPDP_DEFAULT_REMOTE_LEASE_DURATION = {5, 0};
```

### ✅ 步骤 3.4.2：重启恢复测试

1. 正常通信后按 ESP32 RST 按钮
2. 记录恢复通信的时间
3. 重复 3 次取平均值

### 📊 你需要做的分析

**表 3.4：租约时长实验汇总**
| 租约 (s) | 重启恢复时间 | 结论 |
|---------|-------------|------|
| 5 | ___ | 快速故障检测 |
| 12 | ___ | 默认配置 |
| 30 | ___ | |
| 60 | ___ | |
| 180 | ___ | 慢故障检测（幽灵风险） |

---

## 实验 3.5-3.10：扩展参数（可选）

ℹ️ **如果时间充足，按照相同流程测试以下参数：**

### 实验 3.5：读写者数量
- `NUM_STATEFUL_WRITERS` / `NUM_STATEFUL_READERS`
- 测试值：4, 8, 16, 32
- 观察：多 topic 支持能力，内存占用

### 实验 3.6：代理数量
- `NUM_WRITER_PROXIES_PER_READER`
- 测试值：2, 6, 10, 15
- 观察：多对多通信能力

### 实验 3.7：工作队列长度
- `THREAD_POOL_WORKLOAD_QUEUE_LENGTH`
- 测试值：10, 20, 50, 100, 200
- 观察：高频发布下的丢包率

### 实验 3.8：线程池大小
- `THREAD_POOL_NUM_WRITERS` / `NUM_READERS`
- 测试值：1, 2, 4
- 观察：并发性能，CPU 占用

### 实验 3.9：主题名长度
- `MAX_TOPICNAME_LENGTH`
- 测试值：20, 40, 80, 128
- 观察：内存占用变化

### 实验 3.10：线程优先级
- `THREAD_POOL_READER_PRIO`
- 测试值：16, 20, 24, 28
- 观察：高负载下的响应时间

---

## 📊 第三部分总结：你需要完成的分析

### 核心实验数据汇总

**表 3.总：参数调节综合对比**
| 参数 | 最优值 | 默认值 | 影响维度 | 推荐场景 |
|------|--------|--------|---------|---------|
| HB_PERIOD | ___ | 4000 | 延迟、网络开销 | ___ |
| HISTORY_DEPTH | ___ | 10 | 内存、可靠性 | ___ |
| SPDP_PERIOD | ___ | 1000 | 启动速度 | ___ |
| LEASE_DURATION | ___ | 12 | 故障检测 | ___ |

### 核心图表

**图 3.总.1：参数影响热力图**
- 行：10 个参数
- 列：RTT / 内存 / 启动时间 / 网络开销
- 颜色：影响程度（红=高影响，绿=低影响）

**图 3.总.2：场景化配置雷达图**
- 4 个场景：低延迟 / 高可靠 / 低功耗 / 大规模
- 6 个维度：延迟 / 吞吐 / 内存 / 可靠性 / 启动速度 / 网络效率

---



---

# 附录：快速参考

## Wireshark 常用过滤器

| 用途 | 过滤器 |
|------|--------|
| 所有 RTPS 包 | `rtps` |
| HEARTBEAT 包 | `rtps.sm.id == 0x07` |
| ACKNACK 包 | `rtps.sm.id == 0x06` |
| DATA 包 | `rtps.sm.id == 0x15` |
| 特定端口 | `udp.port == 7400 \|\| udp.port == 7411` |
| 特定 IP | `ip.addr == 192.0.2.1` |
| 时间窗口 | `frame.time_relative > 10 && frame.time_relative < 20` |

## 参数快速查找表

| 参数名 | 文件行号 | 默认值 | 影响 |
|--------|---------|--------|------|
| SF_WRITER_HB_PERIOD_MS | 90 | 4000 | 心跳周期 |
| HISTORY_SIZE_STATEFUL | 80 | 10 | 历史深度 |
| SPDP_RESEND_PERIOD_MS | 91 | 1000 | 发现周期 |
| SPDP_DEFAULT_REMOTE_LEASE_DURATION | 97-98 | {12,0} | 租约时长 |
| NUM_STATEFUL_WRITERS | 67 | 8 | 写者数量 |
| NUM_STATEFUL_READERS | 66 | 8 | 读者数量 |
| NUM_WRITER_PROXIES_PER_READER | 71 | 6 | 写者代理 |
| THREAD_POOL_WORKLOAD_QUEUE_LENGTH | 117 | 20 | 工作队列 |
| THREAD_POOL_NUM_WRITERS | 113 | 1 | 写线程数 |
| THREAD_POOL_READER_PRIO | 116 | 24 | 读线程优先级 |

## 常用命令快速参考

### 编译和烧录
```bash
cd ~/mROS2-QoS/workspace/qos_eval
idf.py build flash
idf.py monitor  # 查看日志
```

### 运行测试
```bash
cd ~/mROS2-QoS
source /opt/ros/humble/setup.bash
./scripts/validation/qos_verify.sh /dev/ttyUSB0
```

### upstream 测试
```bash
cd ~/mROS2-QoS/upstream_bench
source /opt/ros/humble/setup.bash
python3 test_upstream_rtt.py
```

### micro-ROS 测试
```bash
# 终端 1
micro_ros_agent udp4 --port 7408

# 终端 2
cd ~/mROS2-QoS/microros_bench
python3 test_microros_rtt.py
```

## 实验检查清单

### 第一部分：三系统对比
- [ ] mROS2-QoS 抓包和 RTT 数据
- [ ] upstream 抓包和 RTT 数据
- [ ] micro-ROS 抓包和 RTT 数据
- [ ] 绘制 RTT 对比图

### 第二部分：Wireshark 分析
- [ ] RELIABLE vs BEST_EFFORT 对比（截图 1-2）
- [ ] Flow Graph 三系统对比（截图 3-5）
- [ ] RTT 延迟分布导出（CSV 3个）
- [ ] TRANSIENT_LOCAL 验证（截图 7-9）
- [ ] Agent 三跳可视化（截图 10-12）

### 第三部分：参数调节
- [ ] 心跳周期实验（6 个值）
- [ ] 历史深度实验（6 个值）
- [ ] SPDP 周期实验（5 个值）
- [ ] 租约时长实验（5 个值）
- [ ] 可选：扩展参数实验（6 个）

## 数据文件组织结构

```
results/experiments_2026/
├── raw_data/
│   ├── capture_mros2qos_reliable.pcapng
│   ├── capture_upstream_besteffort.pcapng
│   ├── capture_microros_agent.pcapng
│   ├── capture_transient_local_late_joiner.pcapng
│   ├── capture_hb_100ms.pcapng
│   ├── capture_hb_500ms.pcapng
│   ├── ... (其他参数实验抓包)
│   ├── heartbeat_mros2qos.csv
│   ├── rtt_deltas_mros2qos.csv
│   └── ... (其他导出的 CSV)
├── figures/
│   ├── fig_heartbeat_reliable.png
│   ├── fig_flowgraph_reliable.png
│   ├── fig_transient_local_packets.png
│   └── ... (所有截图)
├── 1_system_comparison/
│   └── summary_tables.xlsx
├── 2_wireshark_analysis/
│   └── analysis_results.xlsx
└── 3_parameter_tuning/
    └── parameter_results.xlsx
```

## 预估时间

| 部分 | 任务 | 预估时间 |
|------|------|---------|
| 第一部分 | 三系统基础对比 | 2-3 小时 |
| 第二部分 | Wireshark 分析 | 3-4 小时 |
| 第三部分（核心） | 4 个参数实验 | 4-6 小时 |
| 第三部分（扩展） | 6 个参数实验 | 4-6 小时 |
| 数据分析和画图 | 你自己完成 | 8-12 小时 |
| **总计** | | **21-31 小时** |

**建议**：
- 第一周：完成第一、二部分
- 第二周：完成第三部分核心 4 个参数
- 第三周：数据分析和画图
- 第四周（可选）：扩展参数 + 论文写作

---

# 故障排查

## 问题 1：Wireshark 看不到包

**症状**：抓包后没有 RTPS 包

**解决**：
1. 检查过滤器是否正确：`udp portrange 7400-7420`
2. 检查选择的网卡是否正确（应该是 WSL bridge）
3. 检查 WSL 防火墙：运行 `wsl_firewall_admin.ps1`
4. 确认 ESP32 已连接 WiFi（查看 ESP32 日志）

## 问题 2：编译失败

**症状**：`idf.py build` 报错

**解决**：
1. 检查语法错误（config.h 修改后）
2. 清理重新编译：`idf.py fullclean && idf.py build`
3. 检查 ESP-IDF 环境：`. ~/esp/esp-idf/export.sh`

## 问题 3：ESP32 无法连接

**症状**：`/dev/ttyUSB0: No such file`

**解决**：
1. 检查 USB 连接：`ls /dev/ttyUSB*`
2. 如果是 `ttyUSB1`，命令中改为 `/dev/ttyUSB1`
3. 检查权限：`sudo chmod 666 /dev/ttyUSB0`

## 问题 4：测试超时

**症状**：测试卡住或超时

**解决**：
1. 按 ESP32 RST 按钮重启
2. 检查 WiFi 连接是否稳定
3. 检查 ROS2 节点是否运行：`ros2 topic list`

---

# 致谢和支持

本实验手册基于以下项目和工具：
- mROS2-QoS: https://github.com/WANG-Pei777/mROS2-QoS
- mROS-base/mros2-esp32: https://github.com/mROS-base/mros2-esp32
- micro-ROS: https://micro.ros.org
- Wireshark: https://www.wireshark.org
- ROS 2 Humble: https://docs.ros.org/en/humble/

如果遇到问题，可以：
1. 查看项目 README 和文档
2. 检查 GitHub Issues
3. 询问导师或同学

**祝实验顺利！Good luck! 加油！**


