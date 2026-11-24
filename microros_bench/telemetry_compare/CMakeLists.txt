cmake_minimum_required(VERSION 3.16)

option(MATCHED_BENCH_TELEMETRY_ENABLED
  "Compile full matched-workload telemetry" ON)
option(MATCHED_BENCH_RELIABLE
  "Use Reliable QoS for the matched workload" OFF)
option(MATCHED_BENCH_RDH_ENABLED
  "Enable Reliable + Transient Local + Keep Last for the matched workload" OFF)
option(MATCHED_BENCH_RDH_LATE_JOIN
  "Build the small Reliable/Transient-Local/Keep-Last late-join pilot" OFF)
set(MATCHED_BENCH_RDH_DEPTH 10 CACHE STRING
  "Keep Last depth used by the combined RDH matched workload")
set(MATCHED_BENCH_HISTORY_DEPTH 10 CACHE STRING
  "Keep Last depth used by the matched workload in every durability mode")
set(MATCHED_BENCH_RDH_SAMPLE_COUNT 5 CACHE STRING
  "Samples seeded before the late reader starts")

set(MATCHED_BENCH_PAYLOAD_BYTES 64 CACHE STRING
  "Application payload bytes for the matched workload")
set(MATCHED_BENCH_PUBLISH_RATE_HZ 10 CACHE STRING
  "Application publish rate in Hz for the matched workload")
set(MATCHED_BENCH_WINDOW_MS 20000 CACHE STRING
  "Steady-state matched-workload window in milliseconds")
set(MATCHED_BENCH_REPLY_GRACE_MS 5000 CACHE STRING
  "Post-window time allowed for Reliable replies in milliseconds")
set(MATCHED_BENCH_IMPAIRMENT clean CACHE STRING
  "Token-safe impairment profile recorded in BENCH_CONFIG")

if(MATCHED_BENCH_RDH_ENABLED AND NOT MATCHED_BENCH_RELIABLE)
  message(FATAL_ERROR "combined RDH mode requires Reliable QoS")
endif()
if(MATCHED_BENCH_RDH_ENABLED AND MATCHED_BENCH_RDH_LATE_JOIN)
  message(FATAL_ERROR "combined RDH workload and late-join-only modes are exclusive")
endif()
if(NOT MATCHED_BENCH_RDH_DEPTH MATCHES "^[0-9]+$" OR
   MATCHED_BENCH_RDH_DEPTH LESS 1 OR MATCHED_BENCH_RDH_DEPTH GREATER 40)
  message(FATAL_ERROR "MATCHED_BENCH_RDH_DEPTH must be in 1..40")
endif()
if(NOT MATCHED_BENCH_HISTORY_DEPTH MATCHES "^[0-9]+$" OR
   MATCHED_BENCH_HISTORY_DEPTH LESS 1 OR
   MATCHED_BENCH_HISTORY_DEPTH GREATER 40)
  message(FATAL_ERROR "MATCHED_BENCH_HISTORY_DEPTH must be in 1..40")
endif()
if(NOT MATCHED_BENCH_RDH_SAMPLE_COUNT MATCHES "^[0-9]+$" OR
   MATCHED_BENCH_RDH_SAMPLE_COUNT LESS 1 OR
   MATCHED_BENCH_RDH_SAMPLE_COUNT GREATER 40)
  message(FATAL_ERROR "MATCHED_BENCH_RDH_SAMPLE_COUNT must be in 1..40")
endif()

set(IDF_TARGET esp32s3 CACHE STRING "ESP-IDF target")
set(EXTRA_COMPONENT_DIRS
    "${CMAKE_CURRENT_LIST_DIR}/../micro_ros_espidf_component"
    "${CMAKE_CURRENT_LIST_DIR}/../../components/benchmark_telemetry")

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(microros_telemetry_compare)
