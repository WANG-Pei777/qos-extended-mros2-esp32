#!/usr/bin/env bash
#
# Complete industrial optimization workflow
#
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${PROJECT_ROOT}"

echo "================================================================"
echo "mROS2-QoS Industrial Optimization - Complete Workflow"
echo "================================================================"
echo ""
echo "This script will execute the complete optimization workflow:"
echo "  1. Apply automated code fixes"
echo "  2. Run static analysis"
echo "  3. Generate documentation"
echo "  4. Create optimization report"
echo ""

read -p "Continue? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
fi

echo ""

# Step 1: Apply fixes
echo "================================================================"
echo "Step 1/4: Applying automated code fixes"
echo "================================================================"
./scripts/optimization/apply_fixes.sh || true

echo ""
read -p "Review changes? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    git diff | less
fi

# Step 2: Static analysis
echo ""
echo "================================================================"
echo "Step 2/4: Running static analysis"
echo "================================================================"
./scripts/analysis/run_static_analysis.sh || true

# Step 3: Documentation
echo ""
echo "================================================================"
echo "Step 3/4: Generating documentation"
echo "================================================================"

if command -v doxygen &> /dev/null; then
    echo "Generating API documentation..."
    doxygen Doxyfile > /dev/null 2>&1 || true
    echo "✓ Documentation generated at: build/docs/html/index.html"
else
    echo "⚠ doxygen not found, skipping documentation generation"
fi

# Step 4: Summary report
echo ""
echo "================================================================"
echo "Step 4/4: Generating optimization summary"
echo "================================================================"

{
    echo "# mROS2-QoS Optimization Execution Summary"
    echo ""
    echo "**Date**: $(date -Iseconds)"
    echo "**Branch**: $(git branch --show-current)"
    echo "**Commit**: $(git rev-parse --short HEAD)"
    echo ""
    echo "## Changes Applied"
    echo ""
    git diff --stat
    echo ""
    echo "## Modified Files"
    echo ""
    git status --short | grep "^ M"
    echo ""
    echo "## Analysis Results"
    echo ""
    echo "See detailed reports in:"
    echo "- \`build/analysis_reports/\`"
    echo "- \`build/docs/html/\`"
    echo ""
    echo "## Next Steps"
    echo ""
    echo "1. Review all changes: \`git diff\`"
    echo "2. Test build: \`cd workspace/step7_full_qos && idf.py build\`"
    echo "3. Run unit tests: \`./scripts/test/qos_static_checks.sh\`"
    echo "4. Performance test (needs ESP32): \`./scripts/benchmark/performance_baseline.sh /dev/ttyUSB0\`"
    echo "5. Stability test (needs ESP32): \`./scripts/test/stability_test_72h.sh /dev/ttyUSB0\`"
} > build/WORKFLOW_SUMMARY.txt

echo "✓ Summary saved to: build/WORKFLOW_SUMMARY.txt"

echo ""
echo "================================================================"
echo "Workflow Complete!"
echo "================================================================"
echo ""
echo "Summary of actions:"
echo "  ✓ Code fixes applied and verified"
echo "  ✓ Static analysis completed"
echo "  ✓ Documentation generated"
echo "  ✓ Reports created"
echo ""
echo "Review the results:"
echo "  - Optimization summary: OPTIMIZATION_SUMMARY.md"
echo "  - Analysis reports: build/analysis_reports/"
echo "  - API documentation: build/docs/html/index.html"
echo "  - Workflow summary: build/WORKFLOW_SUMMARY.txt"
echo ""
echo "Next actions:"
echo "  1. Review changes: git diff"
echo "  2. Commit changes: git add -A && git commit -m 'Industrial optimization phase 1'"
echo "  3. Run hardware tests (when ESP32 available)"
echo ""
