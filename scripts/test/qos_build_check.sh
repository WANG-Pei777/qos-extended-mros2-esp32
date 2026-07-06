#!/usr/bin/env bash
#
# Firmware build gate.
#
# This is the ONLY check that actually compiles the mROS2 core library and
# embeddedRTPS. The host unit tests (scripts/test/qos_static_checks.sh) use stub
# headers and never compile mros2/src/mros2.cpp, so signature/template/overload
# errors are invisible to them -- only a real ESP-IDF build catches them.
#
# Requires ESP-IDF (idf.py). If ESP-IDF is unavailable, this gate SKIPS with a
# clear message instead of passing silently, so CI without the toolchain does
# not get a false green.
#
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APP_DIR="${PROJECT_ROOT}/workspace/step7_full_qos"

# Bring ESP-IDF into the environment if idf.py is not already on PATH.
if ! command -v idf.py >/dev/null 2>&1; then
  IDF_EXPORT=""
  if [ -n "${IDF_PATH:-}" ] && [ -f "${IDF_PATH}/export.sh" ]; then
    IDF_EXPORT="${IDF_PATH}/export.sh"
  elif [ -f "${HOME}/esp-idf/export.sh" ]; then
    IDF_EXPORT="${HOME}/esp-idf/export.sh"
  fi
  if [ -z "${IDF_EXPORT}" ]; then
    echo "[SKIP] ESP-IDF not found (no idf.py on PATH, no \$IDF_PATH, no ~/esp-idf/export.sh)."
    echo "       Firmware build gate skipped. Install/activate ESP-IDF to enable it."
    exit 0
  fi
  set +u
  # shellcheck disable=SC1090
  source "${IDF_EXPORT}" >/dev/null 2>&1
  set -u
fi

if [ ! -f "${APP_DIR}/main/app.cpp" ]; then
  echo "[FAIL] validation app not found at ${APP_DIR}"
  exit 1
fi

echo "=== Firmware build gate: idf.py build (${APP_DIR}) ==="
if ( cd "${APP_DIR}" && idf.py build ); then
  echo "[PASS] firmware builds cleanly"
else
  echo "[FAIL] firmware build failed (see log above)"
  exit 1
fi
