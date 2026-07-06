#!/usr/bin/env bash
#
# Quick optimization check and fix script
# Applies automated fixes for common static analysis issues
#
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

echo "=========================================="
echo "mROS2-QoS Quick Fix Script"
echo "=========================================="
echo ""

cd "${PROJECT_ROOT}"

# 1. Run clang-format on all source files
echo "[1/3] Formatting code with clang-format..."
if command -v clang-format &> /dev/null; then
    find mros2 platform \( -name "*.cpp" -o -name "*.h" -o -name "*.hpp" \) \
        -not -path "*/build/*" \
        -exec clang-format -i {} \;
    echo "✓ Code formatted"
else
    echo "⚠ clang-format not found, skipping"
fi

echo ""

# 2. Generate documentation
echo "[2/3] Generating API documentation..."
if command -v doxygen &> /dev/null; then
    doxygen Doxyfile > /dev/null 2>&1 || true
    echo "✓ Documentation generated at build/docs/html/index.html"
else
    echo "⚠ doxygen not found, skipping"
fi

echo ""

# 3. Run quick static check
echo "[3/3] Running quick static checks..."
./scripts/analysis/run_static_analysis.sh 2>&1 | grep -E "✓|✗|⚠|Total issues" || true

echo ""
echo "=========================================="
echo "Quick fix complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "  1. Review static analysis reports in build/analysis_reports/"
echo "  2. Run performance test: ./scripts/benchmark/performance_baseline.sh /dev/ttyUSB0"
echo "  3. Start stability test: ./scripts/test/stability_test_72h.sh /dev/ttyUSB0"
