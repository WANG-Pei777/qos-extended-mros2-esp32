# Historical ROUND4 Execution Plan

This is the original recovery-era execution plan. It is retained for audit
history only and must not govern formal collection. The authoritative protocol
is ROUND4_TOP_TIER_PROTOCOL.md, which requires clean provenance, unique reply
counts, and transport-layer evidence.

# 第四轮执行书:采集战役(修复已由审计会话完成,本单只管跑数)

**生成**:2026-07-10 凌晨 · **基线提交**:`a1ccfaa` · **tag**:`v0.3.2-true-freeze`

## 修复现状(你不需要再修任何东西)

审计会话已完成并真机验证:板端 QoS 恢复(deadline/lifespan 回归,22/22 全 PASS)、
看门狗回 5s、echo_node/echo_node_lossy 统一 offer `23283064ns`、run_matrix 修复
主机泄漏两根因(路径子串 pkill + 直接执行二进制,双 run 烟测 0 堆积)、CSV 新增
`link_ping_avg_ms` 列并带**链路准入门禁**。所谓"板子系统性故障"已证伪
(清场后 22/22 + RTT 18ms)。

## 最高纪律(不变 + 一条新增)

1. 每步验收 = 阻塞门禁;冲突时停下写偏离报告;**禁改板端固件**。
2. 单会话占用 /dev/ttyUSB0;开工先 `pgrep -af 'echo_node|echo_reply'` 清场确认。
3. **新增:链路门禁默认开启(LINK_GATE_MS=100),禁止用 LINK_GATE_MS=0 关闭。**
   当下 WiFi 环境在 ~15ms 与 1s+ 之间分钟级振荡;门禁会自动等待坏窗口过去
   (每次 30s×最多 10 次)。若连续多轮都被门禁卡住,记录 LEDGER 后改时段再跑。
4. 数据可信判据:行内 `link_ping_avg_ms < 100` 且 commit hash ≥ `a1ccfaa`。
5. 完工产出 `ROUND4_ANALYSIS.md` 到桌面(逐项验收表+数据摘要+异常)。

## 战役顺序

### C1. 效力探针 @15%(通行证,~20 分钟)
```bash
cd /home/wsde-47/mROS2-QoS
HOST_MODE=lossy:0.15 bash scripts/experiment/run_matrix.sh mros2qos efficacy_probe_15_v2 5
```
验收:5/5 匹配;RX ≤ TX 且 ≈ TX×0.85±10%(RX>TX 即主机堆积,立即停);
HOST_LOG `Dropped ≈ 15%`;每行 ping<100。结论写 INJECTION_EFFICACY.md。

### C2. E2 正式(交错,含 BE 臂)
{0,1,5,10,15}% × {RELIABLE, BEST_EFFORT},每条件 N=30,轮转交错(每轮每条件 3 run)。
BE 臂看 `workspace/qos_eval/SWITCH_MODE.txt` 切换,LEDGER 记固件模式。
每条件 run1 后:F3 门禁(loss>0 必须 Dropped>0)。
期望:BE 送达率随丢包下降 / RELIABLE 保持 ≈100% 且 RTT 上升——论文主曲线。

### C3. E3 复位风暴(两臂,主机常驻,N=30)
```bash
# 后修臂
QOS_VALIDATION_SKIP_KILL=1 nohup bash scripts/validation/qos_host.sh all > /tmp/e3_post.log 2>&1 &
HOST_MODE=external bash scripts/experiment/run_matrix.sh mros2qos reset_storm_postfix_v5 30
kill %1; grep -c "node started" /tmp/e3_post.log   # 必须 = 1
# 前修臂(worktree 自带 host,话题旧名!)
git worktree add /tmp/prefix 212122c
cd /tmp/prefix/workspace/step7_full_qos && source ~/esp-idf/export.sh && idf.py build && idf.py -p /dev/ttyUSB0 flash && cd -
QOS_VALIDATION_SKIP_KILL=1 nohup bash /tmp/prefix/scripts/validation/qos_host.sh all > /tmp/e3_pre.log 2>&1 &
HOST_MODE=external bash scripts/experiment/run_matrix.sh mros2qos reset_storm_prefix_v4 30
kill %1; grep -c "node started" /tmp/e3_pre.log    # 必须 = 1
QOS_VALIDATION_MONITOR=0 bash scripts/validation/qos_flash.sh all /dev/ttyUSB0  # 恢复基线
git worktree remove /tmp/prefix --force
```
验收:前修臂匹配率 50–90%(0%=话题错配;100%=记录后加跑 30);
后修臂应出现亚秒 wait(全 8–10s = host 被重启,不过)。
若看门狗崩:留日志、断电重插重烧、继续;连续 2 次才停。

### C4. E1 三臂(同日同网,10 run×3 轮交错)
| 臂 | 固件 | host(HOST_MODE=external 自管)| 陷阱 |
|---|---|---|---|
| mQoS | qos_eval HEAD | qos_host.sh | — |
| upstream | ~/upstream_bench/.../echoreply_string | scripts/echo_best_effort.py | 话题 /step10_best_effort |
| micro-ROS | ~/microros_bench/.../int32_publisher | /snap/bin/micro-ros-agent udp4 --port 7408 | **sdkconfig 里 agent IP 必须改成当前 WSL IP 再重建重烧** |
结束恢复 mQoS 基线 + 22 项 verify。

### C5. 收尾
E4 补行(无 heap 打印记 NA 勿填 0)→ E5 三 pcap + 开销表(Flow Graph 留作者手动)
→ E6 {100,500,1000,2000,8000}×{0,5,10}%(4000ms 臂可复用)→ tar 备份 → commit
→ ROUND4_ANALYSIS.md 交桌面。

## 陷阱速查(累计版,只列高频)
主机堆积(已修,但 RX>TX 仍是第一报警)| ros2 run 孤儿(已修)| 话题旧名(前修臂)|
agent 旧 IP(micro-ROS)| 板子闲置掉网(先复位)| 双会话同板 | 链路坏窗口(门禁会等)
