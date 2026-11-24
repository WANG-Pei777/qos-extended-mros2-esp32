cmake_minimum_required(VERSION 3.16)

if(NOT DEFINED IDF_TARGET)
  set(IDF_TARGET "esp32s3")
endif()

set(MROS2_MECHANISM_CASE_ID "UNBOUND" CACHE STRING "Machine-safe mechanism case ID")
set(MROS2_MECHANISM_KIND "resource_sample_reject" CACHE STRING "Mechanism scenario")
set(MROS2_MECHANISM_TOPIC "seven_qos_mechanism" CACHE STRING "Topic without leading slash")
set(MROS2_MECHANISM_PAYLOAD_BYTES "64" CACHE STRING "String payload bytes")
set(MROS2_MECHANISM_SAMPLE_LIMIT "5" CACHE STRING "KEEP_ALL max_samples")
set(MROS2_MECHANISM_TIMEOUT_MS "20000" CACHE STRING "Scenario timeout")
set(MROS2_RTPS_HISTORY_CAPACITY "100" CACHE STRING "Compile-time history capacity")
set(MROS2_RTPS_HEARTBEAT_PERIOD_MS "100" CACHE STRING "Reliable heartbeat period")
set(MROS2_RTPS_ACKNACK_SEQUENCE_RESPONSE_BUDGET "4" CACHE STRING
    "Requested sequence responses processed per ACKNACK")
set(MROS2_ALLOW_UNMATCHED_USER_READER_FALLBACK "0" CACHE STRING
    "Legacy pre-SEDP sole-user-Reader fallback (0 fail closed, 1 enabled)")
set(MROS2_QOS_MONITOR_PERIOD_MS "5" CACHE STRING "QoS monitor period")
set(MROS2_WIFI_INITIAL_CONNECT_TIMEOUT_MS "180000" CACHE STRING "Wi-Fi timeout")

if(NOT MROS2_MECHANISM_CASE_ID MATCHES "^[A-Za-z0-9_.-]+$")
  message(FATAL_ERROR "MROS2_MECHANISM_CASE_ID is not machine-safe")
endif()
if(NOT MROS2_MECHANISM_KIND MATCHES
    "^(resource_|history_|durability_|deadline_|lifespan_|liveliness_)[A-Za-z0-9_]+$")
  message(FATAL_ERROR "unsupported MROS2_MECHANISM_KIND")
endif()
if(NOT MROS2_MECHANISM_TOPIC MATCHES "^[A-Za-z0-9_]+(/[A-Za-z0-9_]+)*$")
  message(FATAL_ERROR "MROS2_MECHANISM_TOPIC must omit the leading slash")
endif()
foreach(name IN ITEMS
    MROS2_MECHANISM_PAYLOAD_BYTES MROS2_MECHANISM_SAMPLE_LIMIT
    MROS2_MECHANISM_TIMEOUT_MS MROS2_RTPS_HISTORY_CAPACITY
    MROS2_RTPS_HEARTBEAT_PERIOD_MS
    MROS2_RTPS_ACKNACK_SEQUENCE_RESPONSE_BUDGET
    MROS2_ALLOW_UNMATCHED_USER_READER_FALLBACK
    MROS2_QOS_MONITOR_PERIOD_MS
    MROS2_WIFI_INITIAL_CONNECT_TIMEOUT_MS)
  if(NOT "${${name}}" MATCHES "^[0-9]+$")
    message(FATAL_ERROR "${name} must be an unsigned integer")
  endif()
endforeach()
if(NOT MROS2_ALLOW_UNMATCHED_USER_READER_FALLBACK EQUAL 0 AND
   NOT MROS2_ALLOW_UNMATCHED_USER_READER_FALLBACK EQUAL 1)
  message(FATAL_ERROR
    "MROS2_ALLOW_UNMATCHED_USER_READER_FALLBACK must be 0 or 1")
endif()
if(MROS2_RTPS_ACKNACK_SEQUENCE_RESPONSE_BUDGET LESS 1 OR
   MROS2_RTPS_ACKNACK_SEQUENCE_RESPONSE_BUDGET GREATER 32)
  message(FATAL_ERROR
    "MROS2_RTPS_ACKNACK_SEQUENCE_RESPONSE_BUDGET must be in 1..32")
endif()
if(MROS2_MECHANISM_SAMPLE_LIMIT GREATER MROS2_RTPS_HISTORY_CAPACITY)
  message(FATAL_ERROR "sample limit must not exceed history capacity")
endif()
if(MROS2_MECHANISM_KIND MATCHES "^resource_" AND
   MROS2_RTPS_HISTORY_CAPACITY LESS 100)
  message(FATAL_ERROR "resource mechanisms require the capacity-100 build family")
elseif(NOT MROS2_MECHANISM_KIND MATCHES "^resource_" AND
       MROS2_RTPS_HISTORY_CAPACITY LESS 40)
  message(FATAL_ERROR "non-resource mechanisms require at least capacity 40")
endif()

set(EXTRA_COMPONENT_DIRS ../../components)
add_compile_options(-w)

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(seven_qos_mechanisms)

message(STATUS
  "Seven-QoS mechanism case=${MROS2_MECHANISM_CASE_ID}, "
  "kind=${MROS2_MECHANISM_KIND}, payload=${MROS2_MECHANISM_PAYLOAD_BYTES}, "
  "sample_limit=${MROS2_MECHANISM_SAMPLE_LIMIT}, "
  "capacity=${MROS2_RTPS_HISTORY_CAPACITY}, "
  "acknack_sequence_budget=${MROS2_RTPS_ACKNACK_SEQUENCE_RESPONSE_BUDGET}, "
  "unmatched_user_reader_fallback=${MROS2_ALLOW_UNMATCHED_USER_READER_FALLBACK}")
