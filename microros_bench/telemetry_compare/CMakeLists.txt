cmake_minimum_required(VERSION 3.16)

option(MATCHED_BENCH_TELEMETRY_ENABLED
  "Compile full matched-workload telemetry" ON)
option(MATCHED_BENCH_RELIABLE
  "Use Reliable QoS for the matched workload" OFF)

set(MATCHED_BENCH_PAYLOAD_BYTES 64 CACHE STRING
  "Application payload bytes for the matched workload")
set(MATCHED_BENCH_PUBLISH_RATE_HZ 10 CACHE STRING
  "Application publish rate in Hz for the matched workload")
set(MATCHED_BENCH_WINDOW_MS 20000 CACHE STRING
  "Steady-state matched-workload window in milliseconds")
set(MATCHED_BENCH_IMPAIRMENT clean CACHE STRING
  "Token-safe impairment profile recorded in BENCH_CONFIG")

set(IDF_TARGET esp32s3 CACHE STRING "ESP-IDF target")
set(EXTRA_COMPONENT_DIRS
    "${CMAKE_CURRENT_LIST_DIR}/../micro_ros_espidf_component"
    "${CMAKE_CURRENT_LIST_DIR}/../../components/benchmark_telemetry")

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(microros_telemetry_compare)
