# 实验整改指导（会话交接文档）

**生成**:2026-07-08 审批后 · **对象**:接手采集战役的 Claude 会话/人
**上位文件**:`docs/benchmark/MASTER_EXPERIMENT_PLAN.md`(方案不变,本文只管执行整改)
**先读**:项目记忆 `experiment-harness-audit`、`rtps-parameter-experiment`、
`microros-comparison`、`hardware-bidirectional-test`(含 usbipd/烧录/验证命令)

---

## 0. 硬约束(违反任何一条=数据作废)

1. **同一时刻只允许一个会话操作 /dev/ttyUSB0**(2026-07-08 上午发生过双会话互杀)。
   开工前 `pgrep -af "run_matrix|sweep|reset_and_log|echo_reply|echo_node"`,有活先协调。
2. 配置已冻结于 tag `v0.3-experiment-freeze`;除方案 §7.2 规定的扫频参数外
   **不得改 config.h**;扫频结束必须恢复原值并复验。
3. CSV 只追加不覆盖;异常 run(未匹配/超时)**保留计入**,不许删行。
4. 烧过外来固件(upstream/micro-ROS/修复前)后,**必须恢复 mROS2 基线并复验**
   (`qos_flash.sh all` + 串口见 matched + RX: 40)。
5. 板子闲置久了会掉网:**任何采集前先复位一次**。

---

## 1. 状态快照(2026-07-08 12:00)

- git:HEAD=`086b867`,tag v0.3 已打;**工作树 53 个脏文件未提交**(含全部 harness 修复——最高风险)。
- 有效数据(可保留入论文管线):
  - `mros2qos_reliable_baseline.csv`(E1 mQoS 臂,N=30,RTT/匹配字段齐)
  - `mros2qos_heartbeat_4000ms.csv`(E6 首档,N=30,数据健康)
  - E2 RELIABLE 5 档重采(0/1/5/10/15pct,各 N=30)——**暂扣**,待任务②判定注入有效性后定生死
  - E3 `reset_storm_postfix.csv` 重采——**作废重做**(协议偏离,见任务③)
- 作废数据:20260708 目录里时间戳早于 07:00 的非 baseline CSV(上午审计结论)。
- harness 已修:pkill 精确匹配(`-fx`)、每条件 `_validate` 预检。
  **未修**:CSV `>` 覆盖(run_matrix.sh 第 34 行)、rssi/channel 空置、条件交错缺失。

## 2. 审批新发现(整改动机)

- **发现①**:E2 重采的 RTT 随丢包**非单调**(0%=32.5ms 最高,5%=21.9 最低)→
  丢包注入有效性未证实,或 WiFi 时段漂移未被交错抵消。E2 数据暂不可用。
- **发现②**:E3 的 harness 每 run 重启 echo 主机 → 每次都是冷发现(wait 中位 8.9s),
  **对端无残留状态**,而残留状态才是死锁 bug 的触发条件。E3 测错场景。

---

## 3. 整改任务(按顺序执行)

### ① 立即提交(10 分钟,保护资产)

```bash
cd /home/wsde-47/mROS2-QoS
git add scripts/experiment/ tools/ docs/benchmark/MASTER_EXPERIMENT_PLAN.md \
        docs/benchmark/EXPERIMENT_REMEDIATION_GUIDE.md
git commit -m "Add experiment harness with audit fixes (exact-match pkill, per-condition validate)"
# 数据不进 git(results/ 已 ignore),但建议打包备份一份:
tar czf ~/exp_data_backup_$(date +%m%d).tgz results/experiments/
```

验收:`git status` 中 scripts/experiment 干净;备份包存在。

### ② 注入有效性判别(约 40 分钟,决定 E2 生死)

原理:BEST_EFFORT 无重传,15% 注入下送达率必须显著 <100%;若 =100%,注入必坏。

```bash
# 板端固件不动(RELIABLE app 也订 BE?不行——需 BE 工作负载)。
# 用 step10 BE 工作负载:worktree 里有 workspace/step10_best_effort(BE 双向)
# 更简做法:直接用 echo_cpp 的 --loss 通道对 RELIABLE 板加 50% 极端档:
ros2 run echo_cpp echo_node_lossy --reliable --loss 0.50 &   # 记下 PID
bash scripts/experiment/run_matrix.sh mros2qos reliable_50pct_probe 5
# 判定:
#  - RELIABLE@50% 若 RTT 明显升高/送达仍~100%但重传可见 → 注入生效 ✓
#  - 若 5 个 run 的 RTT 与 0% 无差(±噪声)且 host log 无 drop 计数 → 注入无效 ✗
# 交叉验证注入确实在跑:run 期间 pgrep -af echo_node_lossy 必须存活整个窗口;
# 并检查 /tmp/e2_echo_*.log 是否有丢弃计数输出。
```

- 生效 → E2 五档 RELIABLE 数据**转正**,但仍需补交错重采一轮(任务④)方可入稿;
- 无效 → 排查 echo_node_lossy 源码丢弃逻辑(tools/echo_cpp/),修后 E2 全部重采。

验收:书面结论写入 `results/experiments/20260708/INJECTION_EFFICACY.md`(几行即可)。

### ③ E3 按方案重做(核心,~2h 机时)

协议(方案 §7.1 固定量 "echo 常驻"):

```bash
# 一次启动主机,期间不重启:
QOS_VALIDATION_SKIP_KILL=1 nohup bash scripts/validation/qos_host.sh all > /tmp/e3_host.log 2>&1 &
# 30 次连续复位循环(每次: reset → 串口40s → 解析 matched/wait),主机不动。
# 参考 stress 脚本形态:results/wireshark/stress_20260706_235327 用的那套
# (memory: rtps-parameter-experiment 记有 8/8 那次的方法)。
```

**修复前臂**(必须有,C3 贡献的对照):

```bash
git worktree add /tmp/prefix 212122c        # 96b26d9(修复) 的父提交
cd /tmp/prefix/workspace/step7_full_qos     # 注意:旧名,且话题是 /step7_full_qos
source ~/esp-idf/export.sh && idf.py build && idf.py -p /dev/ttyUSB0 flash
# 陷阱:HEAD 的 qos_host.sh 听 /qos_eval,对不上!必须用 worktree 里自己的:
QOS_VALIDATION_SKIP_KILL=1 bash /tmp/prefix/scripts/validation/qos_host.sh all &
# 同样主机常驻 + 30 次复位;串口关键词相同(matched/Match state)。
# 结束后:恢复 HEAD 固件(qos_flash.sh all)+复验,git worktree remove /tmp/prefix
```

验收:两个 CSV(prefix/postfix)各 30 行,主机日志证明全程单实例;
预期 postfix≈30/30 且 wait 应显著短于 prefix(prefix 应复现约 20-30% 卡死)。

### ④ harness 补丁 + E2 交错重采

- run_matrix.sh 第 34 行改为:文件不存在才写表头,否则跳过(追加模式)。
- 新增 `run_e2_interleaved.sh`:条件轮转 A,B,C,D,E × 6 轮 =每条件 N30 交错完成
  (每轮每条件 5 run;echo_node_lossy 每条件段启停,用 **精确 PID kill**,不许 pkill 模式)。
- RSSI:固件冻结无法加打印 → 在 MASTER 计划 §8 追加一行偏离记录:
  "RSSI 未逐 run 记录;以条件交错 + 分块重复缓解,列入 threats to validity"。
  CSV 里 rssi/channel 两列**删除**,别留空列。

验收:重采后 5 档 RTT 随丢包单调不减(或差异落在 CI 内且有交错佐证)。

### ⑤ E4 修复重跑(30 分钟)

解析源:flash= `stat -c %s build/qos_eval.bin`(或 idf.py size 输出),
heap= 串口 `Memory: (\d+) bytes free`。三系统各 3 run。
upstream/micro-ROS 的 bin 路径见记忆 microros-comparison(`~/upstream_bench`、`~/microros_bench`)。

### ⑥ E1 补两臂(半天)

- upstream:`~/upstream_bench/mros2-esp32/workspace/echoreply_string`(RTT bench 已写好,
  话题 /step10_best_effort,主机用 `scripts/echo_best_effort.py`);
- micro-ROS:`~/microros_bench/.../int32_publisher`(string-echo 已写好),
  **agent 必须用 7408 端口**(8888 被防火墙拦,记忆有案),
  `/snap/bin/micro-ros-agent udp4 --port 7408`;
- 各 N=30,用 run_matrix(system 参数分别记 upstream / microros);
- **每臂结束恢复 mROS2 基线固件并复验**(硬约束 4)。

### ⑦ E5 + E6 收尾

- E5:`capture_wire.sh` 三系统各抓 60s 负载 pcap → tshark 统计每样本包数/字节;
  Flow Graph 证据图**留给作者手动**(方案 §9,不许脚本出)。
- E6:在 E2 注入通道被证实后,按 {100,500,1000,2000,4000,8000}×{0,5,10}% 补齐;
  4000ms 臂已有可复用。**先跑完 P0 再动 E6**(方案 §7 顺序)。

---

## 4. 完成判据(全绿才算战役结束)

- [ ] E1 三臂 CSV 齐(3×30),交错或注明顺序偏离
- [ ] E2 判别结论 + 交错重采,RELIABLE/BE 两臂 × 5 档
- [ ] E3 prefix/postfix 双臂,主机常驻协议,成功率+恢复时间可画图
- [ ] E4 表(3 系统 flash/heap 非零)
- [ ] E5 三 pcap + 开销表
- [ ] E6 18 条件补齐
- [ ] 所有新脚本已 commit;数据有 tar 备份;板子回到基线并复验

## 5. 陷阱速查(血泪账,别再踩)

| 陷阱 | 后果 | 规避 |
|---|---|---|
| pkill 子串匹配 | 杀掉 echo_node_lossy → 注入失效 | 已修为 -fx;新脚本用 PID |
| trap 循环覆盖 | 僵尸参与者积累 → 端口爬出防火墙 7400-7420 → 全体不匹配数小时 | 每条件显式 kill $PID |
| 每 run 重启主机 | E3 变冷发现,测错场景 | E3 主机常驻 |
| 验证型 app 遇丢包 warm-up 中止 | 全零行 | 丢包实验容忍 warm-up 失败继续统计(app 有 VALIDATION NOT READY 分支,解析时按 matched 字段判定,勿弃行) |
| 板子闲置掉网 | 抓不到任何包 | 采集前先复位 |
| 修复前臂话题是旧名 | 主机对不上 | 用 worktree 自带 qos_host.sh |
| micro-ROS agent 8888 | 防火墙静默拦截,rclc 初始化 abort | 用 7408 |
| 双会话同板 | 互杀进程,数据污染 | 硬约束 1 |
