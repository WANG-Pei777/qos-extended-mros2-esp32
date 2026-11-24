cmake_minimum_required(VERSION 3.16)

option(MATCHED_BENCH_TELEMETRY_ENABLED
  "Compile full matched-workload telemetry" ON)
option(MATCHED_BENCH_RELIABLE
  "Use Reliable QoS for the pilot workload" ON)
option(MATCHED_BENCH_RDH_ENABLED
  "Enable Reliable + Transient Local + Keep Last for the pilot workload" OFF)
set(MATCHED_BENCH_RDH_DEPTH 10 CACHE STRING
  "Keep Last depth used when the combined RDH mode is enabled")
set(MATCHED_BENCH_HISTORY_DEPTH 10 CACHE STRING
  "Keep Last depth used by the matched workload in every durability mode")

set(SEVEN_QOS_PERFORMANCE_FAMILY common CACHE STRING
  "Policy family implemented by the excluded pilot")
set(SEVEN_QOS_PERFORMANCE_CELL_ID COMMON CACHE STRING
  "Machine-safe policy cell identifier")
set(SEVEN_QOS_PERFORMANCE_RUN_TOKEN mros2qos-telemetry-smoke-001 CACHE STRING
  "Machine-safe run identity emitted in every telemetry record")
set(SEVEN_QOS_PERFORMANCE_DEADLINE_MS 0 CACHE STRING
  "Requested subscriber deadline in milliseconds; zero disables it")
set(SEVEN_QOS_PERFORMANCE_LIFESPAN_MS 0 CACHE STRING
  "Requested publisher lifespan in milliseconds; zero disables it")
set(SEVEN_QOS_PERFORMANCE_RELEASE_DELAY_MS 0 CACHE STRING
  "Pre-window publisher transmission hold in milliseconds")
set(SEVEN_QOS_PERFORMANCE_RESOURCE_MAX_SAMPLES 0 CACHE STRING
  "Resource Limits writer sample cap; zero outside that family")
set(SEVEN_QOS_PERFORMANCE_RESOURCE_PROBE_EXTRA 0 CACHE STRING
  "Resource probe attempts beyond the cap; zero or one")
set(SEVEN_QOS_PERFORMANCE_RESOURCE_ACK_SUPPRESSION_MS 0 CACHE STRING
  "External host-to-board ACK suppression episode in milliseconds")
set(SEVEN_QOS_PERFORMANCE_HISTORY_DEPTH 0 CACHE STRING
  "History/Depth KEEP_LAST depth; zero outside that family")
set(SEVEN_QOS_PERFORMANCE_HISTORY_BURST_SIZE 0 CACHE STRING
  "History/Depth pre-window burst size; zero outside that family")
set(SEVEN_QOS_PERFORMANCE_DURABILITY none CACHE STRING
  "Durability family mode: none, volatile, or transient_local")
set(SEVEN_QOS_PERFORMANCE_DURABILITY_CACHE_DEPTH 0 CACHE STRING
  "Durability writer cache depth; zero outside that family")
set(SEVEN_QOS_PERFORMANCE_DURABILITY_PREJOIN_SAMPLES 0 CACHE STRING
  "Durability samples emitted before host start")
set(SEVEN_QOS_PERFORMANCE_LIVELINESS_LEASE_MS 0 CACHE STRING
  "Liveliness lease in milliseconds; zero outside that family")
set(SEVEN_QOS_PERFORMANCE_LIVELINESS_OUTAGE_MS 0 CACHE STRING
  "Bounded host-egress outage in milliseconds; zero outside that family")
set(MATCHED_BENCH_PAYLOAD_BYTES 512 CACHE STRING
  "Application payload bytes for the pilot workload")
set(MATCHED_BENCH_PUBLISH_RATE_HZ 50 CACHE STRING
  "Application publish rate in Hz for the pilot workload")
set(MATCHED_BENCH_WINDOW_MS 20000 CACHE STRING
  "Steady-state pilot window in milliseconds")
set(MATCHED_BENCH_REPLY_GRACE_MS 5000 CACHE STRING
  "Post-window time allowed for Reliable replies in milliseconds")
set(MATCHED_BENCH_IMPAIRMENT clean CACHE STRING
  "Token-safe impairment profile recorded in telemetry")

if(MATCHED_BENCH_RDH_ENABLED AND NOT MATCHED_BENCH_RELIABLE)
  message(FATAL_ERROR "combined RDH mode requires Reliable QoS")
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

if(NOT SEVEN_QOS_PERFORMANCE_FAMILY MATCHES
   "^(common|deadline|lifespan|resource_limits|history_depth|durability|liveliness)$")
  message(FATAL_ERROR "unsupported SEVEN_QOS_PERFORMANCE_FAMILY")
endif()
if(NOT SEVEN_QOS_PERFORMANCE_CELL_ID MATCHES "^[A-Za-z0-9_.-]+$")
  message(FATAL_ERROR "SEVEN_QOS_PERFORMANCE_CELL_ID is not machine-safe")
endif()
if(NOT SEVEN_QOS_PERFORMANCE_RUN_TOKEN MATCHES "^[A-Za-z0-9_.-]+$")
  message(FATAL_ERROR "SEVEN_QOS_PERFORMANCE_RUN_TOKEN is not machine-safe")
endif()
if(NOT SEVEN_QOS_PERFORMANCE_DEADLINE_MS MATCHES "^[0-9]+$")
  message(FATAL_ERROR "SEVEN_QOS_PERFORMANCE_DEADLINE_MS must be unsigned")
endif()
if(NOT SEVEN_QOS_PERFORMANCE_LIFESPAN_MS MATCHES "^[0-9]+$")
  message(FATAL_ERROR "SEVEN_QOS_PERFORMANCE_LIFESPAN_MS must be unsigned")
endif()
if(NOT SEVEN_QOS_PERFORMANCE_RELEASE_DELAY_MS MATCHES "^[0-9]+$")
  message(FATAL_ERROR "SEVEN_QOS_PERFORMANCE_RELEASE_DELAY_MS must be unsigned")
endif()
if(NOT SEVEN_QOS_PERFORMANCE_RESOURCE_MAX_SAMPLES MATCHES "^[0-9]+$")
  message(FATAL_ERROR "resource max samples must be unsigned")
endif()
if(NOT SEVEN_QOS_PERFORMANCE_RESOURCE_PROBE_EXTRA MATCHES "^[01]$")
  message(FATAL_ERROR "resource probe extra must be zero or one")
endif()
if(NOT SEVEN_QOS_PERFORMANCE_RESOURCE_ACK_SUPPRESSION_MS MATCHES "^[0-9]+$")
  message(FATAL_ERROR "resource ACK suppression duration must be unsigned")
endif()
if(NOT SEVEN_QOS_PERFORMANCE_HISTORY_DEPTH MATCHES "^[0-9]+$" OR
   NOT SEVEN_QOS_PERFORMANCE_HISTORY_BURST_SIZE MATCHES "^[0-9]+$")
  message(FATAL_ERROR "History/Depth parameters must be unsigned")
endif()
if(NOT SEVEN_QOS_PERFORMANCE_DURABILITY MATCHES
   "^(none|volatile|transient_local)$")
  message(FATAL_ERROR "unsupported Durability mode")
endif()
if(NOT SEVEN_QOS_PERFORMANCE_DURABILITY_CACHE_DEPTH MATCHES "^[0-9]+$" OR
   NOT SEVEN_QOS_PERFORMANCE_DURABILITY_PREJOIN_SAMPLES MATCHES "^[0-9]+$")
  message(FATAL_ERROR "Durability parameters must be unsigned")
endif()
if(NOT SEVEN_QOS_PERFORMANCE_LIVELINESS_LEASE_MS MATCHES "^[0-9]+$" OR
   NOT SEVEN_QOS_PERFORMANCE_LIVELINESS_OUTAGE_MS MATCHES "^[0-9]+$")
  message(FATAL_ERROR "Liveliness parameters must be unsigned")
endif()
if(SEVEN_QOS_PERFORMANCE_FAMILY STREQUAL "common" AND
   NOT SEVEN_QOS_PERFORMANCE_DEADLINE_MS EQUAL 0)
  message(FATAL_ERROR "the common pilot must keep deadline disabled")
endif()
if(NOT SEVEN_QOS_PERFORMANCE_FAMILY STREQUAL "deadline" AND
   NOT SEVEN_QOS_PERFORMANCE_DEADLINE_MS EQUAL 0)
  message(FATAL_ERROR "only the Deadline family may set a deadline")
endif()
if(NOT SEVEN_QOS_PERFORMANCE_FAMILY STREQUAL "lifespan" AND
   (NOT SEVEN_QOS_PERFORMANCE_LIFESPAN_MS EQUAL 0 OR
    NOT SEVEN_QOS_PERFORMANCE_RELEASE_DELAY_MS EQUAL 0))
  message(FATAL_ERROR "only the Lifespan family may configure a release hold")
endif()
if(SEVEN_QOS_PERFORMANCE_FAMILY STREQUAL "resource_limits")
  if(SEVEN_QOS_PERFORMANCE_RESOURCE_MAX_SAMPLES LESS 1)
    message(FATAL_ERROR "Resource Limits requires a positive sample cap")
  endif()
  if(SEVEN_QOS_PERFORMANCE_RESOURCE_ACK_SUPPRESSION_MS GREATER 30000)
    message(FATAL_ERROR "Resource Limits ACK suppression exceeds 30 seconds")
  endif()
elseif(NOT SEVEN_QOS_PERFORMANCE_RESOURCE_MAX_SAMPLES EQUAL 0 OR
       NOT SEVEN_QOS_PERFORMANCE_RESOURCE_PROBE_EXTRA EQUAL 0 OR
       NOT SEVEN_QOS_PERFORMANCE_RESOURCE_ACK_SUPPRESSION_MS EQUAL 0)
  message(FATAL_ERROR "only Resource Limits may configure a resource probe")
endif()
if(SEVEN_QOS_PERFORMANCE_FAMILY STREQUAL "history_depth")
  if(SEVEN_QOS_PERFORMANCE_HISTORY_DEPTH LESS 1 OR
     SEVEN_QOS_PERFORMANCE_HISTORY_DEPTH GREATER 40 OR
     SEVEN_QOS_PERFORMANCE_HISTORY_BURST_SIZE LESS 1 OR
     SEVEN_QOS_PERFORMANCE_HISTORY_BURST_SIZE GREATER 40)
    message(FATAL_ERROR "History/Depth values must be in 1..40")
  endif()
elseif(NOT SEVEN_QOS_PERFORMANCE_HISTORY_DEPTH EQUAL 0 OR
       NOT SEVEN_QOS_PERFORMANCE_HISTORY_BURST_SIZE EQUAL 0)
  message(FATAL_ERROR "only History/Depth may configure a burst probe")
endif()
if(SEVEN_QOS_PERFORMANCE_FAMILY STREQUAL "durability")
  if(SEVEN_QOS_PERFORMANCE_DURABILITY STREQUAL "none" OR
     SEVEN_QOS_PERFORMANCE_DURABILITY_CACHE_DEPTH LESS 1 OR
     SEVEN_QOS_PERFORMANCE_DURABILITY_CACHE_DEPTH GREATER 40 OR
     SEVEN_QOS_PERFORMANCE_DURABILITY_PREJOIN_SAMPLES LESS 1 OR
     SEVEN_QOS_PERFORMANCE_DURABILITY_PREJOIN_SAMPLES GREATER 40)
    message(FATAL_ERROR "Durability requires a bounded pre-join cache probe")
  endif()
elseif(NOT SEVEN_QOS_PERFORMANCE_DURABILITY STREQUAL "none" OR
       NOT SEVEN_QOS_PERFORMANCE_DURABILITY_CACHE_DEPTH EQUAL 0 OR
       NOT SEVEN_QOS_PERFORMANCE_DURABILITY_PREJOIN_SAMPLES EQUAL 0)
  message(FATAL_ERROR "only Durability may configure a pre-join cache")
endif()
if(SEVEN_QOS_PERFORMANCE_FAMILY STREQUAL "liveliness")
  if(SEVEN_QOS_PERFORMANCE_LIVELINESS_LEASE_MS LESS 1 OR
     SEVEN_QOS_PERFORMANCE_LIVELINESS_LEASE_MS GREATER 10000 OR
     SEVEN_QOS_PERFORMANCE_LIVELINESS_OUTAGE_MS LESS 1 OR
     SEVEN_QOS_PERFORMANCE_LIVELINESS_OUTAGE_MS GREATER 15000)
    message(FATAL_ERROR "Liveliness lease/outage must be in bounded ranges")
  endif()
elseif(NOT SEVEN_QOS_PERFORMANCE_LIVELINESS_LEASE_MS EQUAL 0 OR
       NOT SEVEN_QOS_PERFORMANCE_LIVELINESS_OUTAGE_MS EQUAL 0)
  message(FATAL_ERROR "only Liveliness may configure an outage probe")
endif()

set(SEVEN_QOS_PERFORMANCE_FAMILY_CODE 0)
if(SEVEN_QOS_PERFORMANCE_FAMILY STREQUAL "deadline")
  set(SEVEN_QOS_PERFORMANCE_FAMILY_CODE 1)
elseif(SEVEN_QOS_PERFORMANCE_FAMILY STREQUAL "lifespan")
  set(SEVEN_QOS_PERFORMANCE_FAMILY_CODE 2)
elseif(SEVEN_QOS_PERFORMANCE_FAMILY STREQUAL "resource_limits")
  set(SEVEN_QOS_PERFORMANCE_FAMILY_CODE 3)
elseif(SEVEN_QOS_PERFORMANCE_FAMILY STREQUAL "history_depth")
  set(SEVEN_QOS_PERFORMANCE_FAMILY_CODE 4)
elseif(SEVEN_QOS_PERFORMANCE_FAMILY STREQUAL "durability")
  set(SEVEN_QOS_PERFORMANCE_FAMILY_CODE 5)
elseif(SEVEN_QOS_PERFORMANCE_FAMILY STREQUAL "liveliness")
  set(SEVEN_QOS_PERFORMANCE_FAMILY_CODE 6)
endif()

set(SEVEN_QOS_PERFORMANCE_DURABILITY_CODE 0)
if(SEVEN_QOS_PERFORMANCE_DURABILITY STREQUAL "transient_local")
  set(SEVEN_QOS_PERFORMANCE_DURABILITY_CODE 1)
endif()

set(IDF_TARGET esp32s3 CACHE STRING "ESP-IDF target")
set(MROS2_RTPS_HISTORY_CAPACITY 40 CACHE STRING "RTPS history capacity")
set(MROS2_RTPS_HEARTBEAT_PERIOD_MS 100 CACHE STRING "Heartbeat period")
set(MROS2_QOS_MONITOR_PERIOD_MS 5 CACHE STRING "QoS monitor period")
set(MROS2_WIFI_INITIAL_CONNECT_TIMEOUT_MS 180000 CACHE STRING
  "Wi-Fi startup timeout")
set(EXTRA_COMPONENT_DIRS ../../components)

add_compile_definitions(MROS2_LOG_MIN_SEVERITY=5)

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(seven_qos_performance_pilot)
