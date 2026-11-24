#!/usr/bin/env bash
#
# Industrial-grade static analysis script for mROS2-QoS
# Runs multiple static analysis tools and generates reports
#
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REPORT_DIR="${PROJECT_ROOT}/build/analysis_reports"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=========================================="
echo "mROS2-QoS Static Analysis Suite"
echo "=========================================="
echo ""

# Create report directory
mkdir -p "${REPORT_DIR}"

TOTAL_ISSUES=0
FAILED_TOOLS=0

# ==========================================
# 1. cppcheck
# ==========================================
echo -e "${YELLOW}[1/4] Running cppcheck...${NC}"
CPPCHECK_REPORT="${REPORT_DIR}/cppcheck_${TIMESTAMP}.txt"

if command -v cppcheck &> /dev/null; then
    cppcheck --enable=all \
             --std=c++17 \
             --platform=unix32 \
             --suppress=missingIncludeSystem \
             --suppress=unusedFunction \
             --inline-suppr \
             -I"${PROJECT_ROOT}/mros2/include" \
             -I"${PROJECT_ROOT}/mros2/embeddedRTPS/include" \
             -I"${PROJECT_ROOT}/tests/stubs" \
             "${PROJECT_ROOT}/mros2/src" \
             "${PROJECT_ROOT}/mros2/embeddedRTPS/src" \
             2>&1 | tee "${CPPCHECK_REPORT}"

    ISSUES=$(grep -c "error\|warning" "${CPPCHECK_REPORT}" || true)
    TOTAL_ISSUES=$((TOTAL_ISSUES + ISSUES))

    if [ "$ISSUES" -eq 0 ]; then
        echo -e "${GREEN}✓ cppcheck: CLEAN${NC}"
    else
        echo -e "${RED}✗ cppcheck: ${ISSUES} issues found${NC}"
        FAILED_TOOLS=$((FAILED_TOOLS + 1))
    fi
else
    echo -e "${YELLOW}⚠ cppcheck not found, skipping${NC}"
fi

echo ""

# ==========================================
# 2. clang-tidy (if available)
# ==========================================
echo -e "${YELLOW}[2/4] Running clang-tidy...${NC}"
TIDY_REPORT="${REPORT_DIR}/clang-tidy_${TIMESTAMP}.txt"

if command -v clang-tidy &> /dev/null; then
    # Find all C++ source files
    find "${PROJECT_ROOT}/mros2/src" \
         "${PROJECT_ROOT}/mros2/embeddedRTPS/src" \
         -name "*.cpp" -o -name "*.c" | while read -r file; do
        clang-tidy "$file" \
            -p="${PROJECT_ROOT}" \
            --config-file="${PROJECT_ROOT}/.clang-tidy" \
            2>&1 || true
    done | tee "${TIDY_REPORT}"

    ISSUES=$(grep -c "warning\|error" "${TIDY_REPORT}" || true)
    TOTAL_ISSUES=$((TOTAL_ISSUES + ISSUES))

    if [ "$ISSUES" -eq 0 ]; then
        echo -e "${GREEN}✓ clang-tidy: CLEAN${NC}"
    else
        echo -e "${YELLOW}⚠ clang-tidy: ${ISSUES} issues found${NC}"
    fi
else
    echo -e "${YELLOW}⚠ clang-tidy not found, skipping${NC}"
fi

echo ""

# ==========================================
# 3. Code metrics
# ==========================================
echo -e "${YELLOW}[3/4] Analyzing code metrics...${NC}"
METRICS_REPORT="${REPORT_DIR}/metrics_${TIMESTAMP}.txt"

{
    echo "=========================================="
    echo "Code Metrics Report"
    echo "Generated: $(date)"
    echo "=========================================="
    echo ""

    # Lines of code
    echo "--- Lines of Code ---"
    if command -v cloc &> /dev/null; then
        cloc --quiet "${PROJECT_ROOT}/mros2" "${PROJECT_ROOT}/platform"
    else
        find "${PROJECT_ROOT}/mros2" "${PROJECT_ROOT}/platform" \
            -name "*.cpp" -o -name "*.c" -o -name "*.h" -o -name "*.hpp" \
            | xargs wc -l | tail -1
    fi

    echo ""
    echo "--- File Counts ---"
    echo "C++ source files: $(find "${PROJECT_ROOT}/mros2" -name "*.cpp" | wc -l)"
    echo "C source files: $(find "${PROJECT_ROOT}/mros2" -name "*.c" | wc -l)"
    echo "Header files: $(find "${PROJECT_ROOT}/mros2" -name "*.h" -o -name "*.hpp" | wc -l)"

    echo ""
    echo "--- Large Files (>500 lines) ---"
    find "${PROJECT_ROOT}/mros2" \( -name "*.cpp" -o -name "*.h" \) -exec wc -l {} \; \
        | awk '$1 > 500 {print}' | sort -rn

} | tee "${METRICS_REPORT}"

echo -e "${GREEN}✓ Metrics report saved${NC}"
echo ""

# ==========================================
# 4. Security checks
# ==========================================
echo -e "${YELLOW}[4/4] Security analysis...${NC}"
SECURITY_REPORT="${REPORT_DIR}/security_${TIMESTAMP}.txt"

{
    echo "=========================================="
    echo "Security Analysis Report"
    echo "Generated: $(date)"
    echo "=========================================="
    echo ""

    echo "--- Unsafe C Functions ---"
    UNSAFE=$(grep -rn "strcpy\|strcat\|sprintf\|gets\|scanf" \
        "${PROJECT_ROOT}/mros2/src/" \
        "${PROJECT_ROOT}/mros2/embeddedRTPS/src/" \
        --include="*.cpp" --include="*.c" --include="*.h" 2>/dev/null || true)

    if [ -z "$UNSAFE" ]; then
        echo "✓ No unsafe functions found"
    else
        echo "⚠ Unsafe functions detected:"
        echo "$UNSAFE"
        TOTAL_ISSUES=$((TOTAL_ISSUES + $(echo "$UNSAFE" | wc -l)))
    fi

    echo ""
    echo "--- Memory Allocation ---"
    NEW_COUNT=$(grep -rn "\bnew\b" "${PROJECT_ROOT}/mros2/src/" --include="*.cpp" | wc -l)
    DELETE_COUNT=$(grep -rn "\bdelete\b" "${PROJECT_ROOT}/mros2/src/" --include="*.cpp" | wc -l)
    echo "new count: $NEW_COUNT"
    echo "delete count: $DELETE_COUNT"

    if [ "$NEW_COUNT" -gt "$DELETE_COUNT" ]; then
        echo "⚠ Potential memory leak: new > delete"
    fi

    echo ""
    echo "--- Volatile Variables (should use atomic) ---"
    grep -rn "volatile.*bool\|volatile.*int" \
        "${PROJECT_ROOT}/mros2/" \
        --include="*.cpp" --include="*.h" || echo "✓ No volatile variables"

} | tee "${SECURITY_REPORT}"

echo ""

# ==========================================
# Summary
# ==========================================
echo "=========================================="
echo "Analysis Summary"
echo "=========================================="
echo "Reports saved to: ${REPORT_DIR}"
echo ""
echo "cppcheck:      ${CPPCHECK_REPORT}"
echo "clang-tidy:    ${TIDY_REPORT}"
echo "metrics:       ${METRICS_REPORT}"
echo "security:      ${SECURITY_REPORT}"
echo ""

if [ "$TOTAL_ISSUES" -eq 0 ]; then
    echo -e "${GREEN}✓✓✓ ALL CHECKS PASSED ✓✓✓${NC}"
    exit 0
else
    echo -e "${YELLOW}⚠ Total issues found: ${TOTAL_ISSUES}${NC}"
    echo "Review reports for details."
    exit 1
fi
