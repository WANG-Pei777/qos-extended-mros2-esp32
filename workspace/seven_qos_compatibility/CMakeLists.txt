cmake_minimum_required(VERSION 3.16)

if(NOT DEFINED IDF_TARGET)
  set(IDF_TARGET "esp32s3")
endif()

set(EXTRA_COMPONENT_DIRS ../../components)

set(MROS2_QOS_CASE_ID "unbound" CACHE STRING "Seven-QoS compatibility case ID")
set(MROS2_QOS_BOARD_ROLE "publisher" CACHE STRING "Board endpoint role")
set(MROS2_QOS_RELIABILITY "reliable" CACHE STRING "Board reliability")
set(MROS2_QOS_DURABILITY "volatile" CACHE STRING "Board durability")
set(MROS2_QOS_DEADLINE_MS 0 CACHE STRING "Board deadline in milliseconds")
set(MROS2_QOS_LIVELINESS_LEASE_MS 0 CACHE STRING "Board liveliness lease in milliseconds")
set(MROS2_QOS_EXPECTED_MATCH 0 CACHE STRING "Expected endpoint match")
set(MROS2_QOS_WAIT_MS 20000 CACHE STRING "Endpoint wait timeout")
set(MROS2_QOS_POST_MATCH_MS 5000 CACHE STRING "Post-match hold")
set(MROS2_QOS_MESSAGE_COUNT 10 CACHE STRING "Application message count")
set(MROS2_QOS_PERIOD_MS 100 CACHE STRING "Application publish period")
set(MROS2_RTPS_HISTORY_CAPACITY 10 CACHE STRING "RTPS history capacity")
set(MROS2_RTPS_HEARTBEAT_PERIOD_MS 4000 CACHE STRING "Reliable writer heartbeat")

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(seven_qos_compatibility)
