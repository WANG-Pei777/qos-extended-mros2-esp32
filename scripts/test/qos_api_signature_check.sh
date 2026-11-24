#!/usr/bin/env bash
#
# API signature consistency gate (no ESP-IDF required).
#
# The RTPS create_publisher/create_subscription templates are declared in
# mros2/include/mros2.h, defined out-of-line in mros2/src/mros2.cpp, and
# explicitly instantiated from platform/templates.hpp (generated from
# mros2/mros2_header_generator/templates.tpl).
#
# If the topic_name parameter type drifts between these sources
# (e.g. `std::string` by value vs `const std::string&`), the out-of-line
# definition no longer matches the in-class declaration and the firmware fails
# to compile/link. The host unit tests never compile mros2.cpp, so such a break
# is invisible until a full `idf.py build`. This gate catches the drift cheaply.
#
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HDR="${PROJECT_ROOT}/mros2/include/mros2.h"
DEF="${PROJECT_ROOT}/mros2/src/mros2.cpp"
TPL="${PROJECT_ROOT}/mros2/mros2_header_generator/templates.tpl"
HPP="${PROJECT_ROOT}/platform/templates.hpp"
FAILED=0

# Extract how the QoSProfile overload of function $2 passes topic_name in
# file $1. Prints one of: ref | value | missing
extract_ref() {
  local file="$1" fn="$2" sig
  sig=$(grep -Pzo "${fn}\s*(<[^>]*>)?\s*\([^;{]*QoSProfile[^;{]*" "$file" 2>/dev/null \
        | tr '\0\n' '  ' || true)
  if [ -z "$sig" ]; then
    echo "missing"
  elif echo "$sig" | grep -q 'const std::string *&'; then
    echo "ref"
  else
    echo "value"
  fi
}

check_fn() {
  local fn="$1" h d t p
  h=$(extract_ref "$HDR" "$fn")
  d=$(extract_ref "$DEF" "$fn")
  t=$(extract_ref "$TPL" "$fn")
  p=$(extract_ref "$HPP" "$fn")
  if [ "$h" = missing ] || [ "$d" = missing ] || [ "$t" = missing ] || [ "$p" = missing ]; then
    echo "[FAIL] ${fn}: QoSProfile overload not found in a source (h=$h def=$d tpl=$t hpp=$p)"
    FAILED=1
  elif [ "$h" = "$d" ] && [ "$h" = "$t" ] && [ "$h" = "$p" ]; then
    echo "[PASS] ${fn}: topic_name is '${h}' consistently across header/def/tpl/hpp"
  else
    echo "[FAIL] ${fn}: topic_name type MISMATCH -> mros2.h=$h mros2.cpp=$d templates.tpl=$t templates.hpp=$p"
    echo "       out-of-line definition will not match declaration -> firmware build error"
    FAILED=1
  fi
}

echo "=== API signature consistency (create_publisher / create_subscription) ==="
check_fn create_publisher
check_fn create_subscription

if [ "$FAILED" -ne 0 ]; then
  echo "=== API signature check FAILED ==="
  exit 1
fi
echo "[OK] API signatures consistent"
