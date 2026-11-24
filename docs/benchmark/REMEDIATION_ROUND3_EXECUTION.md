# 第三轮整改执行书(自包含工单,按序执行)

**生成**:2026-07-09 下午,ROUND2_ANALYSIS 复核后 · **取代**:ROUND2 工单及其 v2.1 附录
**记忆参照**:`experiment-harness-audit`(含全部历史证据)

---

## 最高纪律(第二轮的教训,违者全部返工)

1. **每步验收是阻塞门禁**:不过不进下一步。第二轮所有损失都源于跳验收。
2. **偏离协议**:工单与现实冲突时,**停下,写偏离报告交回**,不许自行改方案;
   **绝对禁止改动板端固件**(提交 9f192d1 删除板端 QoS 请求 = 冻结违规,已勒令回退)。
3. 同一时刻单会话操作 /dev/ttyUSB0;采集前先复位板子。
4. 完工后生成 `ROUND3_ANALYSIS.md` 到桌面(格式仿 ROUND2_ANALYSIS:
   逐项验收状态表 + 数据摘要 + 异常与证据 + LEDGER 同步更新)。

## 背景一段话(不必翻旧文档)

第二轮失败的唯一真凶:**echo 主机进程泄漏堆积**(审计时系统挂着 9 个僵尸)。
它同时造成 RX=2×/3×TX(多主机齐回声)、探针发现失败(参与者把端口顶出防火墙
7400-7420 窗)、板端看门狗崩溃(9 参与者流量轰炸 ReaderThread)。泄漏的机械成因:
B1 清理正则 `pgrep -fx ".*/echo_node"` full-match **匹配不到任何进程**(空操作);
B2 `ros2 run` 包装器被 kill 后**真节点变孤儿**。另:应用层丢弃碰不到 DDS 发现
(丢弃在 FastDDS 之上),"丢包破坏发现"结论作废;E3 设计无罪,N=30 不变。

---

## S 系列:修复(顺序执行,每步验收)

### S1. 清僵尸

```bash
pkill -f "echo_cpp/echo_node"; pkill -f "echo_reply.py"; sleep 2
pgrep -af "echo_node|echo_reply" && echo "STILL ALIVE - STOP" || echo CLEAN
```
验收:输出 CLEAN;`ss -ulpn | grep ':74'` 无 echo 残留端口。

### S2. 回退冻结违规,按原始工单重做 F2

```bash
cd ~/mROS2-QoS
git revert --no-edit 9f192d1
```
然后编辑 `tools/echo_cpp/src/echo_node.cpp` **和** `echo_node_lossy.cpp`:
reply 发布者的 `deadline(std::chrono::milliseconds(100))` 改为

```cpp
reply_qos.deadline(std::chrono::nanoseconds(23283064));
```

(`lifespan(2000ms)` 保留——lifespan 不参与 RxO 匹配。23283064ns 是板端 SEDP
把 100ms 纳秒值写进 fraction 字段的编码结果,与能正常工作的 Python host 一致。)

```bash
cd tools/echo_cpp && colcon build --packages-select echo_cpp && cd -
git add -A && git commit -m "F2 redo: offer deadline 23283064ns on echo_cpp reply publishers (per work order)"
```

验收:`grep -n 23283064 tools/echo_cpp/src/*.cpp` 两个文件各 1 处;
`grep -rn "deadline" workspace/qos_eval/main/app.cpp` 恢复回退前状态(板端请求完好)。

### S3. 修 B1 + B2(run_matrix.sh)

- 清理行(非 external 模式)替换为:
  ```bash
  pkill -f "echo_cpp/echo_node" 2>/dev/null || true
  pkill -f "echo_reply.py" 2>/dev/null || true
  sleep 1
  ```
- lossy / cpp 模式启动**直接执行节点二进制**(不经 ros2 run,HOST_PID 才是真身):
  ```bash
  "${PROJECT_ROOT}/tools/echo_cpp/install/echo_cpp/lib/echo_cpp/echo_node_lossy" \
      --reliable --loss "${RATE}" > "${HOST_LOG}" 2>&1 &
  HOST_PID=$!
  ```
  (需先 `source tools/echo_cpp/install/setup.bash` 保证 rmw 环境;二进制路径存在性先 `ls` 验证)
- run 末尾 kill 后加断言:`pgrep -f "echo_cpp/echo_node" | wc -l` 必须为 0(external 模式除外)。

验收:lossy:0.0 冒烟 2 连 run,第二 run 开始前后 `pgrep -cf "echo_cpp/echo_node|echo_reply"`
分别为 0/1/0(无堆积);external 冒烟确认脚本全程不碰 host。

### S4. 板子恢复(看门狗崩溃后必须走硬流程)

1. **物理断电重插** ESP32(不是软复位);Windows 侧重新
   `usbipd attach --wsl --busid 4-2`,确认 `/dev/ttyUSB0` 出现。
2. 烧回退后的真冻结固件并完整验证:
```bash
QOS_VALIDATION_MONITOR=0 bash scripts/validation/qos_flash.sh all /dev/ttyUSB0
bash scripts/validation/qos_verify.sh /dev/ttyUSB0 110
```
验收:**22/22 PASS**——特别是 "Deadline: finite deadline visible" 和
"Lifespan: 2000000000" 两项(9f192d1 未回退干净则此二项必 FAIL)。

### S5. 单主机断言进所有驱动脚本

每条件 run1 之前:
```bash
N=$(pgrep -cf "echo_cpp/echo_node|echo_reply.py")
[ "$N" -eq 1 ] || { echo "[GATE] host count=$N ≠ 1, abort"; exit 1; }
```

---

## R 系列:重跑(S 全过后)

### R1'. 效力探针 @15%(E2 最高档,20 分钟)

```bash
HOST_MODE=lossy:0.15 bash scripts/experiment/run_matrix.sh mros2qos efficacy_probe_15 5
```
判据(修正版):5/5 匹配;HOST_LOG `Dropped ≈ 15%±5`;**RX ≤ TX 且 RX ≈ TX×0.85±10%**
(RX>TX 即主机又堆积,回 S1);RTT 相对 0% 基线略升。
结论追加进 `INJECTION_EFFICACY.md`。不过关 → E2/E6 冻结并写偏离报告。

### R2. E2 正式采集(交错,含 BE 臂)

- 条件 {0,1,5,10,15}% × {RELIABLE, BEST_EFFORT},每条件 N=30,轮转交错
  (10 条件 × 3 run × 10 轮);host 由驱动脚本按 HOST_MODE=lossy:<rate> 管理。
- BE 臂固件切换看 `workspace/qos_eval/SWITCH_MODE.txt`;固件模式与 hash 记 LEDGER。
- 每条件 run1 后跑 F3 门禁(Dropped>0)+ S5 单主机断言。
- 期望:BE 送达随丢包下降,RELIABLE ≈100% 且 RTT 随丢包升。

### R3. E3 复位风暴(两臂,主机常驻,N=30 不变)

后修臂:
```bash
QOS_VALIDATION_SKIP_KILL=1 nohup bash scripts/validation/qos_host.sh all > /tmp/e3_post_host.log 2>&1 &
HOST_MODE=external bash scripts/experiment/run_matrix.sh mros2qos reset_storm_postfix_v4 30
kill %1
grep -c "node started" /tmp/e3_post_host.log    # 验收 = 1
```
前修臂(**worktree 自带 host,话题旧名**):
```bash
git worktree add /tmp/prefix 212122c
cd /tmp/prefix/workspace/step7_full_qos && source ~/esp-idf/export.sh && idf.py build && idf.py -p /dev/ttyUSB0 flash && cd -
QOS_VALIDATION_SKIP_KILL=1 nohup bash /tmp/prefix/scripts/validation/qos_host.sh all > /tmp/e3_pre_host.log 2>&1 &
HOST_MODE=external bash scripts/experiment/run_matrix.sh mros2qos reset_storm_prefix_v3 30
kill %1; grep -c "node started" /tmp/e3_pre_host.log   # 验收 = 1
QOS_VALIDATION_MONITOR=0 bash scripts/validation/qos_flash.sh all /dev/ttyUSB0   # 恢复基线
git worktree remove /tmp/prefix --force
```
合理性边界:前修臂匹配率 **50–90%**(=0% 是话题错配,=100% 记 LEDGER 加跑 30);
后修臂应出现**亚秒级 wait**(30 个全 8-10s = host 被重启,验收不过)。
若再遇看门狗:留串口崩溃日志,断电重插重烧,LEDGER 记录,继续;连续 2 次崩溃才停并报告。

### R4. E1 三臂(同日同网,块交错 10×3 轮)

| 臂 | 固件 | host(自管,HOST_MODE=external)| 专属陷阱 |
|---|---|---|---|
| mQoS | qos_eval HEAD | `qos_host.sh all` | — |
| upstream | `~/upstream_bench/.../echoreply_string` | `python3 scripts/echo_best_effort.py` | 话题 /step10_best_effort |
| micro-ROS | `~/microros_bench/.../int32_publisher` | `/snap/bin/micro-ros-agent udp4 --port 7408` | **sdkconfig 里 agent IP 是旧网 192.0.2.2,必须改成今日 WSL IP(ip addr show eth1)再重建重烧** |

解析靠 run_matrix 的 `RTT_FINAL` 备用正则(实测 upstream 串口确有该行)。
全臂结束恢复 mQoS 基线 + 22 项 verify。

### R5. 收尾

E4 补 microros/upstream 行(无 heap 打印记 `NA`,勿填 0);E5 三臂 pcap + 开销表
(Flow Graph 证据图留作者手动);E6 补 {100,500,1000,2000,8000}×{0,5,10}%;
数据 tar 备份;脚本全部 commit;重打 `v0.3.1-experiment-freeze`(注:回退+F2 重做后
的 HEAD 才是真冻结点);LEDGER 收口。

---

## 总验收清单

- [ ] S1 CLEAN;S2 两处 23283064ns + 板端 QoS 复原;S3 双冒烟无堆积;
      S4 **22/22(含 Deadline/Lifespan 两项)**;S5 断言入脚本
- [ ] R1' 5/5 且 RX≈0.85TX;R2 二十条件曲线形态正确;R3 两臂 host 单实例、
      prefix 50–90%、postfix 见亚秒 wait;R4 三臂同日、异构 rtt 非零
- [ ] E4 无 0 占位;E5 pcap×3;E6 15 条件补齐
- [ ] `ROUND3_ANALYSIS.md` 交桌面;LEDGER/备份/commit/tag 完成

## 陷阱累积表(新增三条)

| 陷阱 | 后果 | 规避 |
|---|---|---|
| `pgrep -fx` full-match 带参进程 | 清理空操作 → 主机堆积 | 用路径子串 `pkill -f "echo_cpp/echo_node"` |
| `ros2 run` 包装器 PID | kill 包装器留孤儿节点 | 直接执行节点二进制 |
| "更省事"的 QoS 修法 | 动了冻结固件,毁可比性与论文证据 | 偏离协议:停下写报告,禁改板端 |
| (承前)话题旧名/agent 旧 IP/换网漂移/闲置掉网/双会话 | — | 见各步内嵌提示 |
