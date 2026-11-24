# 第二轮整改执行书(交接文档,按序执行)

> ## 🔴 三审补充指令 v2.1(2026-07-09 下午,基于 ROUND2_ANALYSIS 报告复核)
>
> 报告里的三大"谜团"已全部实证定案,**两处误诊必须纠正,一处违规必须回退**:
>
> ### 实证结论(审计现场证据)
>
> 1. **系统里挂着 9 个 echo 主机僵尸**(5×lossy@0.50、1×lossy@0.01、3×echo_node),
>    全部绑定 RTPS 端口。这一个事实同时解释:
>    - RX=83≈2×40、RX=120=3×40 —— **多主机同时回声**,不是重传/分片;
>    - R1 run3-5 发现失败 —— 参与者堆积把新节点单播端口顶出防火墙 7400-7420 窗
>      (0708 的同款病理);
>    - R3 看门狗崩溃 —— 板子同时被 9 个参与者的发现/心跳/回声轰炸,
>      ReaderThread 吃满 CPU1 饿死 IDLE1。**E3 设计无罪,不许降 N**。
> 2. **"50% 丢包破坏 DDS 发现"是逻辑上不可能的结论**:丢弃发生在 echo 节点的
>    应用层回调,SPDP/SEDP/HEARTBEAT 在 FastDDS 层之下流动,应用层丢 100% 也
>    碰不到发现协议。发现失败的真因见第 1 条。
> 3. 僵尸的成因是**两个机械 bug**:
>    - **B1**:round-1 把 pkill 收紧成 `pgrep -fx ".*/echo_node"` —— full-match
>      对 "…echo_node_lossy --reliable --loss 0.50" 和 "…echo_node --reliable"
>      都**匹配 0 个**(实测),清理成了空操作;
>    - **B2**:用 `ros2 run` 启动 → HOST_PID 是 python 包装器,kill 掉包装器后
>      **真正的节点变孤儿**(实测:包装器 914851 与孤儿节点并存)。
> 4. **F2(提交 9f192d1)方向反了,属冻结违规**:工单要求把 echo_cpp 的 offer
>    调到 23283064ns,实际却删掉了**板端冻结固件**订阅者的 deadline/lifespan 请求。
>    后果:与此前全部数据失去可比性;22 项验证的 Deadline/Lifespan 两项会失败;
>    论文 7 类 QoS 的 reply 路径证据被毁。
>
> ### 修正步骤(严格按序)
>
> ```bash
> # S1. 清僵尸(路径子串匹配,一网打尽两种节点)
> pkill -f "echo_cpp/echo_node"; pkill -f "echo_reply.py"; sleep 2
> pgrep -af "echo_node|echo_reply" && echo "STILL ALIVE - STOP" || echo CLEAN
>
> # S2. 回退 F2 违规提交,按原工单重做
> git revert --no-edit 9f192d1
> #   然后在 tools/echo_cpp/src/echo_node.cpp 和 echo_node_lossy.cpp 的
> #   reply_qos 处,把 deadline(100ms) 改为:
> #   reply_qos.deadline(std::chrono::nanoseconds(23283064));
> #   (lifespan(2000ms) 保留;lifespan 不参与 RxO 匹配,无害)
> cd tools/echo_cpp && colcon build --packages-select echo_cpp && cd -
>
> # S3. 修 B1+B2:run_matrix.sh 中
> #   清理行改为: pkill -f "echo_cpp/echo_node" ; pkill -f "echo_reply.py"
> #   (external 模式跳过不变)
> #   lossy/cpp 模式启动改为直接执行节点二进制(不经 ros2 run):
> #   "${PROJECT_ROOT}/tools/echo_cpp/install/echo_cpp/lib/echo_cpp/echo_node_lossy" \
> #       --reliable --loss "${RATE}" > "${HOST_LOG}" 2>&1 &
>
> # S4. 板子恢复:物理断电重插(watchdog 后必须),然后烧回退后的真冻结固件
> QOS_VALIDATION_MONITOR=0 bash scripts/validation/qos_flash.sh all /dev/ttyUSB0
> #   并跑完整 22 项 verify —— Deadline/Lifespan 两项必须回到 PASS:
> bash scripts/validation/qos_verify.sh /dev/ttyUSB0 110
>
> # S5. 单主机断言加入所有驱动脚本(每条件 run1 前):
> #   [ $(pgrep -cf "echo_cpp/echo_node|echo_reply.py") -eq 1 ] || abort
>
> # S6. 重跑 R1@15%(同意报告的降档;50% 探针其实已证明注入有效——Dropped 40-43%)
> HOST_MODE=lossy:0.15 bash scripts/experiment/run_matrix.sh mros2qos efficacy_probe_15 5
> #   判据修正:RX ≤ TX 且 ≈ TX×(1-0.15)±10%;5/5 匹配;单主机断言全程成立
> ```
>
> 之后按原序 R2(E2 全 5 档,不砍 15%)→ R3(**N=30 不变**)→ R4。
> 报告中的 Option B(跳过验证/砍 N)**驳回**。
> 附带更正:板端读者线程是 embeddedRTPS 的 ReaderThread,mros2 无 XRCE(那是 micro-ROS)。


**生成**:2026-07-09 三审后 · **性质**:可直接照做的工单
**背景必读**:`EXPERIMENT_REMEDIATION_GUIDE.md` 顶部 ⚠️ 二审附录(失效证据)
**记忆必读**:`experiment-harness-audit`

> 三审铁律:**先修 F1–F3 并通过各自验收,才允许采任何一条数据。**
> 首轮失败的共同根源 = run_matrix 无条件自启 Python host;本工单第一目标是杀掉它。

---

## 0. 开工检查(5 分钟)

```bash
cd ~/mROS2-QoS
pgrep -af "run_matrix|sweep|reset_and_log|echo_reply|echo_node"   # 有残留全杀
pkill -f echo_reply.py; pkill -f echo_node
ip -4 addr show eth1 | grep inet        # 记录今日 WSL IP(昨夜已变网:10.84.233.x 段)
git log --oneline -3 && git status --porcelain | wc -l
```

建台账:`results/experiments/$(date +%Y%m%d)/LEDGER.md`,记录:日期、WSL IP、
板 IP、执行顺序、每次异常。**换网后所有跨臂对比必须当日完成**(见 F4)。

---

## F5a. 资产抢救(先做,防再丢)

```bash
tar tzf ~/exp_data_backup_0708.tgz | grep reliable_baseline
tar xzf ~/exp_data_backup_0708.tgz -C /tmp \
    results/experiments/20260708/mros2qos_reliable_baseline.csv
cp /tmp/results/experiments/20260708/mros2qos_reliable_baseline.csv \
   results/experiments/20260708/
wc -l results/experiments/20260708/mros2qos_reliable_baseline.csv   # 期望 31
```

验收:31 行且首行含 commit `086b867`。在 LEDGER 记"restored from tarball"。

## F2. echo_cpp 回复 QoS 修复(核心补丁,15 分钟)

**病灶**(两个文件同一处):`tools/echo_cpp/src/echo_node.cpp:37` 与
`echo_node_lossy.cpp` 对应行:

```cpp
reply_qos.deadline(std::chrono::milliseconds(100));   // ← offered 100ms
```

板端回复订阅者在线上**请求 deadline=23,283,064 ns**(≈23.28 ms;这是板端 SEDP
把 100 ms 的纳秒值写进 DDS fraction 字段造成的编码怪癖——固件已冻结,本轮不修,
论文可作脚注,战役后再上游修复)。DDS 规则 offered ≤ requested → 100 ms 不兼容,
**lossy 节点从未能给板子发消息**。改为与 Python 版完全一致:

```cpp
reply_qos.deadline(std::chrono::nanoseconds(23283064));
```

两个 cpp 都改,然后:

```bash
cd tools/echo_cpp && colcon build --packages-select echo_cpp && cd -
```

**验收(必须实测,不许只编译)**:
```bash
source tools/echo_cpp/install/setup.bash
ros2 run echo_cpp echo_node_lossy --reliable --loss 0.0 > /tmp/f2_check.log 2>&1 &
python3 /tmp/reset_and_log.py /dev/ttyUSB0 40 /tmp/f2_serial.log   # 若无此脚本见指南§3
grep -c "incompatible" /tmp/f2_check.log        # 必须 = 0
grep -aE "RX: [0-9]+ msgs" /tmp/f2_serial.log   # 必须 RX>0(板子收到 C++ 节点回声)
kill %1
```

## F1. run_matrix 增加 HOST_MODE(30 分钟)

改 `scripts/experiment/run_matrix.sh`:

1. 顶部读环境变量:`HOST_MODE="${HOST_MODE:-python}"`,合法值
   `python` / `lossy:<rate>`(如 lossy:0.10)/ `external`。
2. 循环内"启动 host"段改为:

```bash
case "${HOST_MODE}" in
  python)
    "${PROJECT_ROOT}/scripts/validation/qos_host.sh" all > "${HOST_LOG}" 2>&1 &
    HOST_PID=$! ;;
  lossy:*)
    RATE="${HOST_MODE#lossy:}"
    ros2 run echo_cpp echo_node_lossy --reliable --loss "${RATE}" > "${HOST_LOG}" 2>&1 &
    HOST_PID=$! ;;
  external)
    HOST_PID="" ;;      # 调用方管理 host,本脚本不起不杀
esac
```

3. run 前清理与 run 后 kill:仅当 `HOST_PID` 非空才执行;`external` 模式
   **禁止任何 pkill**(E3 常驻/异构臂的命根子)。
4. CSV 表头改追加安全:`[ -f "${OUTPUT_CSV}" ] || echo "...header..." > "${OUTPUT_CSV}"`。
5. **解析器增加异构臂格式**(upstream/micro-ROS bench 输出):在现有正则不中时
   尝试 `RTT_FINAL TX=(\d+) RX=(\d+) RTT n=(\d+) min=(\d+) avg=(\d+) max=(\d+)`,
   映射到相同 CSV 列。

验收:`bash -n` 过;三种模式各 1 run 冒烟:python 正常;lossy:0.0 时 HOST_LOG
是 echo_cpp_lossy 的且板 RX>0;external 模式下脚本全程不碰 host 进程
(`pgrep echo` 数量前后不变)。

## F3. 丢包效力门禁(写进 E2 驱动脚本)

每个 loss>0 条件的 **run1 结束后**强制断言,不过即中止该条件:

```bash
DROPPED=$(grep -oE "Dropped: [0-9]+" "${HOST_LOG}" | tail -1 | grep -oE "[0-9]+")
if [ "${DROPPED:-0}" -eq 0 ]; then
  echo "[GATE FAIL] loss=${RATE} 但 Dropped=0 —— 注入无效,中止"; exit 1
fi
```

## F5b. 仓库清理 + 重打冻结 tag

```bash
git rm --cached workspace/qos_eval/main/CMakeLists.txt.backup "实验文档已完成.txt" 2>/dev/null
rm -f workspace/qos_eval/main/CMakeLists.txt.backup
git add -A scripts/experiment tools/echo_cpp docs/benchmark
git commit -m "Round-2 remediation: HOST_MODE, echo_cpp deadline QoS, efficacy gate, parser for bench apps"
git tag -a v0.3.1-experiment-freeze -m "True freeze point: rename + harness round-2 fixes included"
```

此后所有 CSV 的 commit_hash 应为本 tag 指向的 hash。

---

## 重跑序列(修复验收全过后)

### R1. 效力探针(20 分钟,E2 的通行证)

```bash
HOST_MODE=lossy:0.50 bash scripts/experiment/run_matrix.sh mros2qos efficacy_probe_50 5
```
判据:HOST_LOG 中 `Dropped ≈ 50%`;板端 RX 明显 < TX(约一半);RTT 升高。
结论写 `results/experiments/<date>/INJECTION_EFFICACY.md`。**不过此关,E2/E6 全部冻结。**

### R2. E2 正式采集(交错,含 BE 臂)

- 条件:{0,1,5,10,15}% × {RELIABLE, BEST_EFFORT}。
- RELIABLE 臂:qos_eval 现固件;BE 臂:先看 `workspace/qos_eval/SWITCH_MODE.txt`
  与 `main/app_lossy.cpp` 的切换机制;若为编译开关,BE 档烧 BE 模式固件,
  条件名记 `best_effort_<pct>`,LEDGER 记录固件模式与 hash。
- **交错**:轮转 10 条件 × 每轮 3 run × 10 轮 = N30/条件(host 每条件段由驱动脚本
  以 HOST_MODE=lossy:<rate> 拉起,PID 精确管理)。
- 期望形态:BE 送达率随丢包线性下降,RELIABLE 保持≈100% 且 RTT 随丢包升——
  这才是论文那条曲线。

### R3. E3 重做(两臂,主机常驻)

```bash
# 后修臂(HEAD 固件已在板上):
QOS_VALIDATION_SKIP_KILL=1 nohup bash scripts/validation/qos_host.sh all > /tmp/e3_post_host.log 2>&1 &
HOST_MODE=external bash scripts/experiment/run_matrix.sh mros2qos reset_storm_postfix_v3 30
kill %1
grep -c "node started" /tmp/e3_post_host.log     # 验收 = 1(整臂单实例!)
```

前修臂(话题是旧名,**必须用 worktree 自带 host**):

```bash
git worktree add /tmp/prefix 212122c
cd /tmp/prefix/workspace/step7_full_qos && source ~/esp-idf/export.sh
idf.py build && idf.py -p /dev/ttyUSB0 flash && cd -
QOS_VALIDATION_SKIP_KILL=1 nohup bash /tmp/prefix/scripts/validation/qos_host.sh all > /tmp/e3_pre_host.log 2>&1 &
HOST_MODE=external bash scripts/experiment/run_matrix.sh mros2qos reset_storm_prefix_v2 30
kill %1; grep -c "node started" /tmp/e3_pre_host.log   # 验收 = 1
# 恢复基线:
QOS_VALIDATION_MONITOR=0 bash scripts/validation/qos_flash.sh all /dev/ttyUSB0
git worktree remove /tmp/prefix --force
```

**合理性边界**:前修臂匹配率应落在 **50–90%**(历史≈71%)。
= 0% → 又是话题错配,立停排查;=100% → 碰撞未触发,LEDGER 记录并加跑 30 次。
后修臂 wait 应出现 **亚秒级热匹配**(单实例 host 的标志);若 30 个 wait 全在 8-10s,
说明 host 仍被重启,验收不过。

### R4. E1 三臂(同日同网,块交错)

顺序:mQoS 10 run → upstream 10 → microros 10,循环 3 轮(每系统 N30,6 次重烧)。

| 臂 | 固件 | host(HOST_MODE=external,自管)| 陷阱 |
|---|---|---|---|
| mQoS | qos_eval(HEAD)| `qos_host.sh all` | — |
| upstream | `~/upstream_bench/.../echoreply_string`(先重建:**换网后无需改**,它不烤对端 IP)| `python3 scripts/echo_best_effort.py` | 话题 /step10_best_effort |
| micro-ROS | `~/microros_bench/.../int32_publisher` | `/snap/bin/micro-ros-agent udp4 --port 7408` | **agent IP 烤在 sdkconfig 里,还是旧网 192.0.2.2!必须改 `sdkconfig.defaults.local` 为今日 WSL IP 并重建重烧** |

每臂段前烧对应固件,段后不必恢复(下一段会烧);**全部结束后恢复 mQoS 基线并复验**。
解析靠 F1 第 5 条的新正则。

### R5. 收尾

- E4 补行:microros flash=`stat -c %s` 其 bin;heap 无打印则记 `NA(app 不输出)`,勿填 0。
- E5:三臂各抓 60s pcap(`capture_wire.sh`),tshark 出每样本包数/字节表;
  Flow Graph 证据图**留作者手动**(方案 §9)。
- E6:效力门禁在手后,补 {100,500,1000,2000,8000}ms × {0,5,10}%;4000ms 臂复用。
- 全部 CSV/LEDGER 备份 tar;新脚本 commit。

---

## 总验收清单

- [ ] F2:板端收到 echo_cpp 回声(RX>0)且节点日志无 incompatible
- [ ] F1:三种 HOST_MODE 冒烟通过;CSV 追加安全;异构正则生效
- [ ] R1:INJECTION_EFFICACY.md 写明 Dropped≈50%、板 RX≈½
- [ ] R2:20 个条件 CSV(2 QoS×5 loss×交错),BE 递减 / RELIABLE 平稳曲线可画
- [ ] R3:两臂各 30,host 日志 "node started"=1;prefix 匹配率 50–90%;postfix 出现亚秒 wait
- [ ] R4:三臂同日,upstream/microros CSV 的 rtt 列非零
- [ ] E4 无 0 占位;E5 三 pcap;E6 18 条件
- [ ] LEDGER 完整;板恢复基线复验;tar 备份;git 干净 + v0.3.1 tag
