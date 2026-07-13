# The following lines of boilerplate have to be in your project's
# CMakeLists in this exact order for cmake to work correctly
cmake_minimum_required(VERSION 3.16)

function(mros2_define_uint_parameter name default minimum maximum description)
  set(${name} "${default}" CACHE STRING "${description}")
  if(NOT "${${name}}" MATCHES "^[0-9]+$")
    message(FATAL_ERROR "${name} must be an unsigned integer, got '${${name}}'")
  endif()
  if(${${name}} LESS ${minimum} OR ${${name}} GREATER ${maximum})
    message(FATAL_ERROR
      "${name}=${${name}} is outside the supported range ${minimum}..${maximum}")
  endif()
endfunction()

mros2_define_uint_parameter(
  MROS2_QOS_HISTORY_DEPTH 5 1 255 "Runtime KEEP_LAST depth")
mros2_define_uint_parameter(
  MROS2_RTPS_HISTORY_CAPACITY 10 1 255 "Compile-time stateful RTPS history capacity")
mros2_define_uint_parameter(
  MROS2_RTPS_HEARTBEAT_PERIOD_MS 4000 1 65535 "Reliable writer heartbeat period")
mros2_define_uint_parameter(
  MROS2_QOS_RESOURCE_MAX_SAMPLES 30 1 4294967295 "Publisher sample resource limit")
mros2_define_uint_parameter(
  MROS2_QOS_RESOURCE_MAX_BYTES 12288 1 4294967295 "Publisher byte resource limit")

if(MROS2_QOS_HISTORY_DEPTH GREATER MROS2_RTPS_HISTORY_CAPACITY)
  message(FATAL_ERROR
    "MROS2_QOS_HISTORY_DEPTH (${MROS2_QOS_HISTORY_DEPTH}) must not exceed "
    "MROS2_RTPS_HISTORY_CAPACITY (${MROS2_RTPS_HISTORY_CAPACITY})")
endif()
if(MROS2_QOS_RESOURCE_MAX_SAMPLES LESS MROS2_RTPS_HISTORY_CAPACITY)
  message(FATAL_ERROR
    "MROS2_QOS_RESOURCE_MAX_SAMPLES (${MROS2_QOS_RESOURCE_MAX_SAMPLES}) must "
    "be at least MROS2_RTPS_HISTORY_CAPACITY (${MROS2_RTPS_HISTORY_CAPACITY})")
endif()

set(EXTRA_COMPONENT_DIRS ../../components)
add_compile_options(-w)

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(qos_eval)

message(STATUS
  "mROS2 mechanism controls: depth=${MROS2_QOS_HISTORY_DEPTH}, "
  "capacity=${MROS2_RTPS_HISTORY_CAPACITY}, "
  "heartbeat_ms=${MROS2_RTPS_HEARTBEAT_PERIOD_MS}, "
  "max_samples=${MROS2_QOS_RESOURCE_MAX_SAMPLES}, "
  "max_bytes=${MROS2_QOS_RESOURCE_MAX_BYTES}")
