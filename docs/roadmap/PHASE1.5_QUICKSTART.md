# Phase 1.5 快速开始指南

## 🎯 目标

完成 Phase 1.5 的硬件验证，补全企业级验证中的关键缺失测试。

---

## ⚡ 快速开始（当 ESP32 可用时）

### 一键式验证（推荐）

```bash
cd ~/mROS2-QoS
./scripts/validation/phase1.5_validation_guide.sh
```

这个交互式脚本会引导你完成所有步骤。

---

## 📋 手动步骤（详细版）

### 前提条件

1. **硬件**: ESP32-S3 通过 USB 连接
2. **环境**: 
   ```bash
   # ESP-IDF
   source ~/esp/esp-idf/export.sh
   
   # ROS2
   source /opt/ros/humble/setup.bash
   ```

---

### Step 1: 最关键 - QoS 不匹配测试 (15分钟)

**为什么最重要**: 这是之前完全缺失的测试，验证 DDS 兼容性规则。

```bash
cd ~/mROS2-QoS

# Flash firmware
./scripts/validation/qos_flash.sh step11_qos_mismatch

# 监控串口输出，查看 4 个测试结果
```

**预期结果**:
- Test 1 (RELIABLE→BEST_EFFORT): ✅ MATCH
- Test 2 (BEST_EFFORT→RELIABLE): ❌ REJECT (正确拒绝)
- Test 3 (VOLATILE→TRANSIENT_LOCAL): ✅ MATCH
- Test 4 (TRANSIENT_LOCAL→VOLATILE): ✅ MATCH

---

### Step 2: TRANSIENT_LOCAL 双向测试 (10分钟)

**验证**: ESP32 能否接收 ROS2 的缓存消息

```bash
# Terminal 1: 启动 ROS2 节点（先启动！）
python3 scripts/echo_transient_bidirectional.py

# Terminal 2: Flash ESP32
./scripts/validation/qos_flash.sh step8b_transient_bidirectional
```

**预期结果**:
- ROS2 发布 8 条缓存消息
- ESP32 启动后接收全部 8 条
- ESP32 也发布 8 条给 ROS2

---

### Step 3: KEEP_ALL 双向测试 (10分钟)

**验证**: ESP32 的 KEEP_ALL 订阅行为

```bash
# Terminal 1: 启动 ROS2 节点
python3 scripts/echo_keep_all_bidirectional.py

# Terminal 2: Flash ESP32
./scripts/validation/qos_flash.sh step9b_keep_all_bidirectional
```

**预期结果**:
- 双向消息传输正常
- 缓存满时正确拒绝
- 资源限制工作正常

---

### Step 4: 24小时稳定性测试 (1天，无人值守)

**企业级必需**: 验证长期运行稳定性

```bash
# 启动测试（后台运行）
./scripts/test/qos_stability_24h.sh step7

# 24小时后查看报告
cat results/stability_24h_*/stability_report.txt
```

**通过标准**:
- ✅ 内存漂移 < 1KB
- ✅ 0 崩溃/重启
- ✅ 0 错误
- ✅ 消息传递一致

---

### Step 5: 可选增强测试 (20分钟)

```bash
# 组合场景测试
./scripts/validation/qos_flash.sh step12_qos_combinations

# 边界条件测试
./scripts/validation/qos_flash.sh step13_boundary_tests
```

---

## ✅ 验证完成检查清单

完成以下所有项目后，Phase 1.5 验证完成：

### P0 - 必需测试
- [ ] step11: QoS 不匹配测试通过
  - [ ] Test 1: RELIABLE→BEST_EFFORT 匹配 ✅
  - [ ] Test 2: BEST_EFFORT→RELIABLE 正确拒绝 ❌
  - [ ] Test 3: VOLATILE→TRANSIENT_LOCAL 匹配 ✅
  - [ ] Test 4: TRANSIENT_LOCAL→VOLATILE 匹配 ✅

- [ ] step8b: TRANSIENT_LOCAL 双向通过
  - [ ] ESP32 接收 ROS2 的 8 条缓存消息
  - [ ] ROS2 接收 ESP32 的 8 条缓存消息

- [ ] step9b: KEEP_ALL 双向通过
  - [ ] ESP32 双向收发正常
  - [ ] 资源限制正确执行

### P1 - 稳定性测试
- [ ] 24小时测试启动
- [ ] 24小时后检查报告
  - [ ] 内存漂移 < 1KB
  - [ ] 无崩溃/重启
  - [ ] 无严重错误

### P2 - 可选增强
- [ ] step12: 组合场景测试
- [ ] step13: 边界条件测试

---

## 📊 测试结果记录

### step11: QoS 不匹配测试

```
日期: ___________
结果: [ ] PASS  [ ] FAIL

Test 1: [ ] PASS  [ ] FAIL
Test 2: [ ] PASS  [ ] FAIL (应该拒绝)
Test 3: [ ] PASS  [ ] FAIL
Test 4: [ ] PASS  [ ] FAIL

备注:
_______________________________
_______________________________
```

### step8b: TRANSIENT_LOCAL 双向

```
日期: ___________
结果: [ ] PASS  [ ] FAIL

ROS2→ESP32 缓存消息: ____ / 8
ESP32→ROS2 缓存消息: ____ / 8

备注:
_______________________________
_______________________________
```

### step9b: KEEP_ALL 双向

```
日期: ___________
结果: [ ] PASS  [ ] FAIL

ESP32 发布: 接受 ____ / 拒绝 ____
ESP32 接收: ____ 条消息

备注:
_______________________________
_______________________________
```

### 24小时稳定性测试

```
开始时间: ___________
结束时间: ___________
结果: [ ] PASS  [ ] FAIL

初始内存: _________ bytes
最终内存: _________ bytes
内存漂移: _________ bytes

错误数: _________
警告数: _________

备注:
_______________________________
_______________________________
```

---

## 🐛 常见问题

### Q1: ESP32 连接不上

```bash
# 检查设备
ls -la /dev/ttyUSB* /dev/ttyACM*

# 添加用户到 dialout 组
sudo usermod -a -G dialout $USER

# 重新登录或重启
```

### Q2: Flash 失败

```bash
# 清除 flash
idf.py -p /dev/ttyUSB0 erase_flash

# 重新 flash
./scripts/validation/qos_flash.sh step11_qos_mismatch
```

### Q3: ROS2 节点找不到 topic

```bash
# 检查 ROS_DOMAIN_ID
export ROS_DOMAIN_ID=0

# 检查网络
ros2 topic list

# 重启 ROS2 节点
```

### Q4: 24小时测试意外停止

```bash
# 检查日志
cat results/stability_24h_*/esp32_serial.log | tail -100

# 重新启动（从头开始）
./scripts/test/qos_stability_24h.sh step7
```

---

## 📚 相关文档

- [PHASE1.5_TEST_SUITE_SUMMARY.md](PHASE1.5_TEST_SUITE_SUMMARY.md) - 测试套件总结
- [PHASE1_ENTERPRISE_VALIDATION_REPORT.md](PHASE1_ENTERPRISE_VALIDATION_REPORT.md) - 企业验证报告
- [docs/qos/ENTERPRISE_VALIDATION_MATRIX.md](docs/qos/ENTERPRISE_VALIDATION_MATRIX.md) - 验证矩阵
- [docs/qos/QOS_TEST_COVERAGE_ANALYSIS.md](docs/qos/QOS_TEST_COVERAGE_ANALYSIS.md) - 测试覆盖分析

---

## 🎓 完成后

Phase 1.5 所有测试通过后：

1. **更新文档**: 在 PHASE1_ENTERPRISE_VALIDATION_REPORT.md 中标记测试完成
2. **评估**: 企业级评分从 6.5/10 提升到 8.7/10
3. **认证**: 系统达到生产就绪标准
4. **Phase 2**: 可以开始 Phase 2（生产部署或高级功能）

---

**祝验证顺利！** 🚀

有任何问题请查看详细文档或重新运行交互式指南。
