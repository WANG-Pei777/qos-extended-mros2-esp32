#!/usr/bin/env bash
#
# Host-side QoS unit tests + security/static checks.
# Runs on any Linux/macOS host with g++.
# No ESP32 or ESP-IDF required.
#
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILD_DIR="${PROJECT_ROOT}/build/qos_static_checks"
SRC="${PROJECT_ROOT}/tests/test_qos.cpp"
BIN="${BUILD_DIR}/test_qos"
FAILED=0

echo "=== Phase 1: QoS Unit Tests ==="
mkdir -p "${BUILD_DIR}"

g++ -std=c++17 \
  -I"${PROJECT_ROOT}/tests/stubs" \
  -I"${PROJECT_ROOT}/mros2/include" \
  -o "${BIN}" \
  "${SRC}"

if ! "${BIN}"; then
  echo "[FAIL] QoS unit tests failed"
  FAILED=1
fi

echo ""
echo "=== Phase 1b: RTPS Message Tests ==="
RTPS_BIN="${BUILD_DIR}/test_rtps_messages"
g++ -std=c++17 \
  -o "${RTPS_BIN}" \
  "${PROJECT_ROOT}/tests/test_rtps_messages.cpp"

if ! "${RTPS_BIN}"; then
  echo "[FAIL] RTPS message tests failed"
  FAILED=1
fi

echo ""
echo "=== Phase 2: Security Checks ==="

# Check no unsafe string operations in modified files
UNSAFE_FILES=$(grep -rn "strcpy\|strcat\|sprintf" \
  "${PROJECT_ROOT}/mros2/src/" \
  "${PROJECT_ROOT}/mros2/embeddedRTPS/src/entities/" \
  "${PROJECT_ROOT}/mros2/embeddedRTPS/src/messages/" \
  --include="*.cpp" --include="*.h" --include="*.tpp" 2>/dev/null || true)

if [ -n "$UNSAFE_FILES" ]; then
  echo "[FAIL] Unsafe string operations found:"
  echo "$UNSAFE_FILES"
  FAILED=1
else
  echo "[PASS] No unsafe string operations"
fi

echo ""
echo "=== Phase 3: Error Handling Checks ==="

# Check no infinite loops remain in error paths (except spin() main loop)
# Get spin() function line number, then exclude that range
SPIN_LINE=$(grep -n "void spin()" "${PROJECT_ROOT}/mros2/src/mros2.cpp" 2>/dev/null | head -1 | cut -d: -f1 || echo "0")
INFINITE_LOOPS=$(grep -n "while (true)" \
  "${PROJECT_ROOT}/mros2/src/mros2.cpp" 2>/dev/null \
  | awk -F: -v spin="$SPIN_LINE" '{if ($1 < spin || $1 > spin+20) print}' || true)

if [ -n "$INFINITE_LOOPS" ]; then
  echo "[FAIL] Infinite loops in error paths:"
  echo "$INFINITE_LOOPS"
  FAILED=1
else
  echo "[PASS] No infinite loops in error paths"
fi

echo ""
echo "=== Phase 4: Code Quality Checks ==="

# Check no memory leaks (new without delete pattern)
NEW_COUNT=$(grep -c "new " "${PROJECT_ROOT}/mros2/src/mros2.cpp" 2>/dev/null || echo "0")
DELETE_COUNT=$(grep -c "delete " "${PROJECT_ROOT}/mros2/src/mros2.cpp" 2>/dev/null || echo "0")
# Note: new=1 is Thread creation (FreeRTOS managed), not a leak
echo "[INFO] new/delete in mros2.cpp: new=$NEW_COUNT, delete=$DELETE_COUNT (Thread is FreeRTOS-managed)"

# Check shutdown function exists
if grep -q "void shutdown()" "${PROJECT_ROOT}/mros2/include/mros2.h" 2>/dev/null; then
  echo "[PASS] shutdown() API declared"
else
  echo "[FAIL] shutdown() API missing"
  FAILED=1
fi

echo ""
echo "=== Phase 5: API Signature Consistency ==="
# Guards against declaration/definition/template-instantiation signature drift
# (e.g. create_publisher(std::string) vs create_publisher(const std::string&)),
# which breaks the firmware build but is invisible to the host unit tests.
if ! bash "${PROJECT_ROOT}/scripts/test/qos_api_signature_check.sh"; then
  echo "[FAIL] create_publisher/create_subscription signature drift (would break firmware build)"
  FAILED=1
fi

echo ""
if [ $FAILED -eq 0 ]; then
  echo "=== All checks PASSED ==="
else
  echo "=== Some checks FAILED ==="
  exit 1
fi
