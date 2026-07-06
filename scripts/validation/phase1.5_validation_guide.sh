#!/usr/bin/env bash
# Phase 1.5 Hardware Validation Guide
# 完整的硬件验证执行指南

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "============================================"
echo "  Phase 1.5 硬件验证执行指南"
echo "============================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_section() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

# ============================================
# STEP 1: Environment Check
# ============================================

print_section "STEP 1: 环境检查"

echo "检查 ESP32 连接..."
if ls /dev/ttyUSB* >/dev/null 2>&1 || ls /dev/ttyACM* >/dev/null 2>&1; then
    SERIAL_PORT=$(ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null | head -1)
    print_success "ESP32 已连接: ${SERIAL_PORT}"
    export SERIAL_PORT
else
    print_error "ESP32 未连接"
    echo ""
    echo "请执行以下操作："
    echo "  1. 连接 ESP32 到 USB 端口"
    echo "  2. 检查设备权限: sudo usermod -a -G dialout \$USER"
    echo "  3. 重新登录或重启"
    echo ""
    exit 1
fi

echo ""
echo "检查 ESP-IDF..."
if command -v idf.py >/dev/null 2>&1; then
    print_success "ESP-IDF 已安装"
else
    print_warning "ESP-IDF 未在 PATH 中"
    echo ""
    echo "请执行以下操作："
    echo "  source ~/esp/esp-idf/export.sh"
    echo "  或者根据你的安装路径调整"
    echo ""
    read -p "是否现在尝试自动 source? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        if [ -f ~/esp/esp-idf/export.sh ]; then
            source ~/esp/esp-idf/export.sh
            print_success "ESP-IDF 环境已加载"
        elif [ -f ~/.espressif/esp-idf/export.sh ]; then
            source ~/.espressif/esp-idf/export.sh
            print_success "ESP-IDF 环境已加载"
        else
            print_error "未找到 ESP-IDF，请手动 source"
            exit 1
        fi
    else
        exit 1
    fi
fi

echo ""
echo "检查 ROS2..."
if command -v ros2 >/dev/null 2>&1; then
    print_success "ROS2 已安装"
else
    print_warning "ROS2 未找到"
    echo ""
    echo "请执行以下操作："
    echo "  source /opt/ros/humble/setup.bash"
    echo "  或者根据你的 ROS2 版本调整"
    echo ""
    read -p "是否现在尝试自动 source? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        if [ -f /opt/ros/humble/setup.bash ]; then
            source /opt/ros/humble/setup.bash
            print_success "ROS2 环境已加载"
        else
            print_error "未找到 ROS2，请手动 source"
            exit 1
        fi
    else
        exit 1
    fi
fi

print_success "环境检查完成！"

# ============================================
# STEP 2: Pre-flight Check
# ============================================

print_section "STEP 2: 预检查"

echo "检查新创建的 workspace..."
EXPECTED_WORKSPACES=(
    "step11_qos_mismatch"
    "step8b_transient_bidirectional"
    "step9b_keep_all_bidirectional"
    "step12_qos_combinations"
    "step13_boundary_tests"
)

ALL_FOUND=true
for ws in "${EXPECTED_WORKSPACES[@]}"; do
    if [ -d "${PROJECT_ROOT}/workspace/${ws}" ]; then
        print_success "${ws}"
    else
        print_error "${ws} 未找到"
        ALL_FOUND=false
    fi
done

if [ "$ALL_FOUND" = false ]; then
    print_error "部分 workspace 缺失，请先创建"
    exit 1
fi

echo ""
echo "检查测试脚本..."
EXPECTED_SCRIPTS=(
    "scripts/test/qos_stability_24h.sh"
    "scripts/echo_transient_bidirectional.py"
    "scripts/echo_keep_all_bidirectional.py"
    "scripts/echo_qos_mismatch.py"
)

for script in "${EXPECTED_SCRIPTS[@]}"; do
    if [ -f "${PROJECT_ROOT}/${script}" ]; then
        print_success "${script}"
    else
        print_error "${script} 未找到"
        ALL_FOUND=false
    fi
done

if [ "$ALL_FOUND" = false ]; then
    print_error "部分脚本缺失"
    exit 1
fi

print_success "预检查完成！"

# ============================================
# STEP 3: Priority P0 Tests
# ============================================

print_section "STEP 3: 优先级 P0 测试 (必须)"

echo "这些是最关键的测试，必须立即执行："
echo ""
echo "  1. step11: QoS 不匹配测试 ⭐ 最重要"
echo "  2. step8b: TRANSIENT_LOCAL 双向"
echo "  3. step9b: KEEP_ALL 双向"
echo ""

read -p "是否开始 P0 测试? [y/N] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "测试已取消"
    exit 0
fi

# Test 1: QoS Mismatch (step11)
print_section "测试 1/3: QoS 不匹配测试 (step11)"

print_info "这个测试验证 DDS QoS 兼容性规则"
print_info "预期结果："
echo "  ✅ Test 1: RELIABLE pub + BEST_EFFORT sub → MATCH"
echo "  ❌ Test 2: BEST_EFFORT pub + RELIABLE sub → REJECT"
echo "  ✅ Test 3: VOLATILE pub + TRANSIENT_LOCAL sub → MATCH"
echo "  ✅ Test 4: TRANSIENT_LOCAL pub + VOLATILE sub → MATCH"
echo ""

read -p "按回车开始 flash step11..."
./scripts/validation/qos_flash.sh step11_qos_mismatch || {
    print_error "Flash 失败"
    exit 1
}

print_info "请查看 ESP32 串口输出，验证以下内容："
echo "  1. 4个测试是否都执行了"
echo "  2. Test 2 是否正确拒绝了不兼容的 QoS"
echo "  3. 其他测试是否通过"
echo ""

read -p "测试是否通过? [y/N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    print_success "step11 测试通过"
else
    print_warning "step11 测试需要进一步检查"
fi

# Test 2: TRANSIENT_LOCAL Bidirectional (step8b)
print_section "测试 2/3: TRANSIENT_LOCAL 双向测试 (step8b)"

print_info "这个测试验证 ESP32 能否接收 ROS2 的缓存消息"
print_info "需要两个终端："
echo ""
echo "Terminal 1 (ROS2 节点):"
echo "  python3 scripts/echo_transient_bidirectional.py"
echo ""
echo "Terminal 2 (Flash ESP32):"
echo "  ./scripts/validation/qos_flash.sh step8b_transient_bidirectional"
echo ""
print_warning "请在另一个终端启动 ROS2 节点后，再继续"
echo ""

read -p "ROS2 节点是否已启动? [y/N] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    print_warning "跳过 step8b 测试"
else
    read -p "按回车开始 flash step8b..."
    ./scripts/validation/qos_flash.sh step8b_transient_bidirectional || {
        print_error "Flash 失败"
        exit 1
    }

    print_info "预期结果："
    echo "  1. ROS2 节点应该发布 8 条缓存消息"
    echo "  2. ESP32 启动后应该接收到全部 8 条缓存消息"
    echo "  3. ESP32 也发布 8 条缓存消息给 ROS2"
    echo ""

    read -p "测试是否通过? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_success "step8b 测试通过"
    else
        print_warning "step8b 测试需要进一步检查"
    fi
fi

# Test 3: KEEP_ALL Bidirectional (step9b)
print_section "测试 3/3: KEEP_ALL 双向测试 (step9b)"

print_info "这个测试验证 ESP32 的 KEEP_ALL 双向行为"
echo ""
echo "Terminal 1 (ROS2 节点):"
echo "  python3 scripts/echo_keep_all_bidirectional.py"
echo ""
echo "Terminal 2 (Flash ESP32):"
echo "  ./scripts/validation/qos_flash.sh step9b_keep_all_bidirectional"
echo ""
print_warning "请在另一个终端启动 ROS2 节点后，再继续"
echo ""

read -p "ROS2 节点是否已启动? [y/N] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    print_warning "跳过 step9b 测试"
else
    read -p "按回车开始 flash step9b..."
    ./scripts/validation/qos_flash.sh step9b_keep_all_bidirectional || {
        print_error "Flash 失败"
        exit 1
    }

    print_info "预期结果："
    echo "  1. ESP32 发布消息，部分被拒绝（缓存满）"
    echo "  2. ESP32 接收来自 ROS2 的消息"
    echo "  3. 双向 KEEP_ALL 行为正确"
    echo ""

    read -p "测试是否通过? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_success "step9b 测试通过"
    else
        print_warning "step9b 测试需要进一步检查"
    fi
fi

print_success "P0 测试完成！"

# ============================================
# STEP 4: Priority P1 Tests (24h)
# ============================================

print_section "STEP 4: 优先级 P1 - 24小时稳定性测试"

print_info "24小时稳定性测试是企业级验证的必要条件"
print_warning "这个测试需要 24 小时无人值守运行"
echo ""
echo "测试内容："
echo "  - 连续运行 24 小时"
echo "  - 每 60 秒采样内存/消息/错误"
echo "  - 自动生成完整报告"
echo ""
echo "启动命令:"
echo "  ./scripts/test/qos_stability_24h.sh step7"
echo ""

read -p "是否现在启动 24 小时测试? [y/N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    print_info "启动 24 小时稳定性测试..."
    ./scripts/test/qos_stability_24h.sh step7 &
    print_success "测试已在后台启动"
    print_info "24 小时后检查报告: results/stability_24h_*/stability_report.txt"
else
    print_warning "24 小时测试已推迟"
    print_info "请稍后手动运行: ./scripts/test/qos_stability_24h.sh step7"
fi

# ============================================
# STEP 5: Priority P2 Tests (Optional)
# ============================================

print_section "STEP 5: 优先级 P2 - 增强测试 (可选)"

echo "这些测试进一步验证系统健壮性："
echo ""
echo "  1. step12: QoS 组合场景测试"
echo "  2. step13: 边界条件测试"
echo ""

read -p "是否运行 P2 测试? [y/N] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    print_warning "P2 测试已跳过"
else
    # Test step12
    print_section "测试 step12: QoS 组合"
    ./scripts/validation/qos_flash.sh step12_qos_combinations || print_error "step12 flash 失败"

    read -p "step12 是否通过? [y/N] " -n 1 -r
    echo
    [[ $REPLY =~ ^[Yy]$ ]] && print_success "step12 通过" || print_warning "step12 需检查"

    # Test step13
    print_section "测试 step13: 边界条件"
    ./scripts/validation/qos_flash.sh step13_boundary_tests || print_error "step13 flash 失败"

    read -p "step13 是否通过? [y/N] " -n 1 -r
    echo
    [[ $REPLY =~ ^[Yy]$ ]] && print_success "step13 通过" || print_warning "step13 需检查"
fi

# ============================================
# Final Summary
# ============================================

print_section "Phase 1.5 硬件验证总结"

echo "已完成的测试："
echo "  ✅ step11: QoS 不匹配测试"
echo "  ✅ step8b: TRANSIENT_LOCAL 双向"
echo "  ✅ step9b: KEEP_ALL 双向"
echo ""

if [ -n "${STABILITY_TEST_PID:-}" ]; then
    echo "  🕐 24小时稳定性测试运行中 (PID: ${STABILITY_TEST_PID})"
    echo ""
fi

echo "下一步："
echo "  1. 检查所有测试结果"
echo "  2. 24小时后查看稳定性报告"
echo "  3. 更新 PHASE1_ENTERPRISE_VALIDATION_REPORT.md"
echo "  4. 如果所有测试通过，Phase 1.5 完成 ✅"
echo ""

print_success "Phase 1.5 硬件验证指南执行完成！"
echo ""
echo "详细文档："
echo "  - PHASE1.5_TEST_SUITE_SUMMARY.md"
echo "  - PHASE1_ENTERPRISE_VALIDATION_REPORT.md"
echo "  - docs/qos/ENTERPRISE_VALIDATION_MATRIX.md"
echo ""
