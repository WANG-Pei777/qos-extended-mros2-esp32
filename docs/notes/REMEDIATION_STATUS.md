## 工具任务执行状态

### ✅ 已完成（按 EXPERIMENT_REMEDIATION_GUIDE §3）

**① 立即提交**
- commit 096913c (harness fixes)
- commit 035070e (remediation data)
- 数据备份: ~/exp_data_backup_0708.tgz

**② 基线恢复**
- 固件已烧录并验证（TX=40 RX=40）

**③ E3 修复前/后对比**
- Pre-fix (212122c): 0/30 匹配（0%）
- Post-fix (baseline): 30/30 匹配（100%）
- 结论: 修复有效 ✅

**④ E2 交错重采**
- 5 条件 × 6 轮 = 30 runs/condition（交错采样）
- 0%, 1%, 5%, 10%, 15% 丢包全部成功
- 总时间: 3h 29m

**⑤ E4 修复重跑**
- mROS2-QoS: Flash 779KB, Heap 198KB
- upstream: Flash 738KB（heap 待测）
- micro-ROS: 待测

### ⏸️ 待执行

**⑥ E1 补两臂**
- upstream mros2-esp32 (N=30)
- micro-ROS (N=30)
- 预计时间: ~2-3 小时

### 📊 数据文件位置

**有效数据（20260708/20260709）:**
- E2: mros2qos_reliable_{0,1,5,10,15}pct.csv
- E3: mros2qos_reset_storm_{prefix,postfix_v2}.csv
- E4: e4_resource_occupancy_v2.csv

**总采集量:** 240+ runs (E2/E3/E4)
