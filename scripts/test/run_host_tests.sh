#!/usr/bin/env bash
#
# Host-side unit tests for the QoS extension. Needs only g++ (C++17) and
# python3; no ESP-IDF, ROS 2, or board. Every test compiles the same headers
# the firmware uses, with small stubs under tests/stubs replacing lwIP.
#
#   ./scripts/test/run_host_tests.sh          # run everything
#   ./scripts/test/run_host_tests.sh qos      # run tests whose name contains "qos"
#
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT="${ROOT}/build/host_tests"
FILTER="${1:-}"
CXX="${CXX:-g++}"
mkdir -p "${OUT}"

RTPS_INC=(-I"${ROOT}/mros2/embeddedRTPS/include" -I"${ROOT}/tests/stubs")
PLATFORM_INC=(-I"${ROOT}/platform" -I"${ROOT}/mros2/embeddedRTPS/thirdparty/Micro-CDR/include")
OVERRIDE=(-include "${ROOT}/tests/stubs/udp_driver_override.h")

pass=0
fail=0
skipped=0

# run NAME [compiler args...]
run() {
  local name="$1"; shift
  if [[ -n "${FILTER}" && "${name}" != *"${FILTER}"* ]]; then
    skipped=$((skipped + 1)); return
  fi
  local bin="${OUT}/${name}"
  if ! "${CXX}" -std=c++17 -pthread -w "$@" -o "${bin}" 2>"${bin}.build.log"; then
    echo "[BUILD FAIL] ${name} (see ${bin}.build.log)"
    fail=$((fail + 1)); return
  fi
  if "${bin}" >"${bin}.log" 2>&1; then
    echo "[PASS] ${name}: $(grep -m1 -E 'passed|Results' "${bin}.log" || echo ok)"
    pass=$((pass + 1))
  else
    echo "[FAIL] ${name} (see ${bin}.log)"
    grep -E '\[FAIL\]' "${bin}.log" | head -5
    fail=$((fail + 1))
  fi
}

T="${ROOT}/tests"
run test_qos                     -I"${ROOT}/mros2/include" -I"${ROOT}/tests/stubs" "${T}/test_qos.cpp"
run test_qos_compatibility       "${RTPS_INC[@]}" "${T}/test_qos_compatibility.cpp"
run test_qos_time                "${RTPS_INC[@]}" "${T}/test_qos_time.cpp"
run test_lifespan                "${RTPS_INC[@]}" "${T}/test_lifespan.cpp"
run test_liveliness_state        "${RTPS_INC[@]}" "${T}/test_liveliness_state.cpp"
run test_reliability_state       "${RTPS_INC[@]}" "${T}/test_reliability_state.cpp"
run test_reader_sequence         "${OVERRIDE[@]}" "${PLATFORM_INC[@]}" "${RTPS_INC[@]}" "${T}/test_reader_sequence.cpp"
run test_simple_history_cache    -I"${ROOT}/tests/history_stubs" "${RTPS_INC[@]}" -I"${ROOT}/platform" "${T}/test_simple_history_cache.cpp"
run test_data_fragment_reassembly "${RTPS_INC[@]}" "${T}/test_data_fragment_reassembly.cpp" "${ROOT}/mros2/embeddedRTPS/src/messages/MessageTypes.cpp"
run test_fragmentation_capability "${RTPS_INC[@]}" "${T}/test_fragmentation_capability.cpp"
run test_rtps_messages           "${RTPS_INC[@]}" "${PLATFORM_INC[@]}" "${T}/test_rtps_messages.cpp"
MC="${ROOT}/mros2/embeddedRTPS/thirdparty/Micro-CDR"
run test_topic_data_roundtrip     "${OVERRIDE[@]}" "${PLATFORM_INC[@]}" "${RTPS_INC[@]}" -I"${MC}/src/c" "${T}/test_topic_data_roundtrip.cpp" \
    "${ROOT}/mros2/embeddedRTPS/src/discovery/TopicData.cpp" "${ROOT}/mros2/embeddedRTPS/src/messages/MessageTypes.cpp" \
    "${MC}/src/c/common.c" "${MC}/src/c/types/basic.c" "${MC}/src/c/types/array.c" "${MC}/src/c/types/string.c" "${MC}/src/c/types/sequence.c"
run test_benchmark_telemetry_math -I"${ROOT}/components/benchmark_telemetry/include" -I"${ROOT}/components/benchmark_telemetry" "${T}/test_benchmark_telemetry_math.cpp"

echo
echo "=== Python harness tests ==="
if (cd "${ROOT}" && python3 -m unittest discover -s tests/experiment -t . 2>"${OUT}/python.log" >/dev/null); then
  echo "[PASS] tests/experiment ($(grep -m1 -E '^Ran ' "${OUT}/python.log"))"
  pass=$((pass + 1))
else
  echo "[FAIL] tests/experiment (see ${OUT}/python.log)"
  tail -3 "${OUT}/python.log"
  fail=$((fail + 1))
fi

echo
echo "host tests: ${pass} passed, ${fail} failed, ${skipped} filtered out"
[[ ${fail} -eq 0 ]]
