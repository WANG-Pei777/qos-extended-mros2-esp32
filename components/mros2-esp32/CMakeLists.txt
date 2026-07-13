set(MROS2_QOS_ROOT "${CMAKE_CURRENT_LIST_DIR}/../..")

set(SRCS
        "${MROS2_QOS_ROOT}/mros2/src/mros2.cpp"
        "${MROS2_QOS_ROOT}/mros2/embeddedRTPS/src/communication/UdpDriver.cpp"
        "${MROS2_QOS_ROOT}/mros2/embeddedRTPS/src/messages/MessageTypes.cpp"
        "${MROS2_QOS_ROOT}/mros2/embeddedRTPS/src/messages/MessageReceiver.cpp"
        "${MROS2_QOS_ROOT}/mros2/embeddedRTPS/src/discovery/TopicData.cpp"
        "${MROS2_QOS_ROOT}/mros2/embeddedRTPS/src/discovery/ParticipantProxyData.cpp"
        "${MROS2_QOS_ROOT}/mros2/embeddedRTPS/src/discovery/SEDPAgent.cpp"
        "${MROS2_QOS_ROOT}/mros2/embeddedRTPS/src/discovery/SPDPAgent.cpp"
        "${MROS2_QOS_ROOT}/mros2/embeddedRTPS/src/storages/PBufWrapper.cpp"
        "${MROS2_QOS_ROOT}/mros2/embeddedRTPS/src/ThreadPool.cpp"
        "${MROS2_QOS_ROOT}/mros2/embeddedRTPS/src/entities/Participant.cpp"
        "${MROS2_QOS_ROOT}/mros2/embeddedRTPS/src/entities/Domain.cpp"
        "${MROS2_QOS_ROOT}/mros2/embeddedRTPS/src/entities/StatelessReader.cpp"
        "${MROS2_QOS_ROOT}/mros2/embeddedRTPS/thirdparty/Micro-CDR/src/c/common.c"
        "${MROS2_QOS_ROOT}/mros2/embeddedRTPS/thirdparty/Micro-CDR/src/c/types/basic.c"
        "${MROS2_QOS_ROOT}/mros2/embeddedRTPS/thirdparty/Micro-CDR/src/c/types/string.c"
        "${MROS2_QOS_ROOT}/mros2/embeddedRTPS/thirdparty/Micro-CDR/src/c/types/sequence.c"
        "${MROS2_QOS_ROOT}/mros2/embeddedRTPS/thirdparty/Micro-CDR/src/c/types/array.c"
        "${MROS2_QOS_ROOT}/mros2/embeddedRTPS/thirdparty/lwip/default_netif.c"
        "${MROS2_QOS_ROOT}/cmsis-esp32/lwip.c"
        "${MROS2_QOS_ROOT}/cmsis-esp32/cmsis-esp.c"
        "${MROS2_QOS_ROOT}/platform/wifi/wifi.c"
        "${MROS2_QOS_ROOT}/platform/mros2-platform.cpp"
        )

set(INCS
        "${MROS2_QOS_ROOT}/mros2/include"
        "${MROS2_QOS_ROOT}/mros2/include/mros2"
        "${MROS2_QOS_ROOT}/mros2/mros2_msgs"
        "${MROS2_QOS_ROOT}/mros2/embeddedRTPS/include"
        "${MROS2_QOS_ROOT}/mros2/embeddedRTPS/thirdparty/lwip"
        "${MROS2_QOS_ROOT}/mros2/embeddedRTPS/thirdparty/Micro-CDR/include"
        "${MROS2_QOS_ROOT}/cmsis-esp32/include"
        "${MROS2_QOS_ROOT}/platform"
        "${MROS2_QOS_ROOT}/platform/wifi"
        "${CMAKE_SOURCE_DIR}/main"
        )

if(NOT CMAKE_BUILD_EARLY_EXPANSION)
        add_compile_options(-w)
endif()

idf_component_register(
        SRCS ${SRCS}
        INCLUDE_DIRS ${INCS}
        REQUIRES nvs_flash esp_wifi)

target_compile_definitions(${COMPONENT_LIB} PRIVATE
        MROS2_RTPS_HISTORY_CAPACITY=${MROS2_RTPS_HISTORY_CAPACITY}
        MROS2_RTPS_HEARTBEAT_PERIOD_MS=${MROS2_RTPS_HEARTBEAT_PERIOD_MS})

set(MROS2_TEMPLATES_HPP "${MROS2_QOS_ROOT}/platform/templates.hpp")

add_custom_command(
        OUTPUT "${MROS2_TEMPLATES_HPP}"
        COMMAND python3 "${MROS2_QOS_ROOT}/mros2/mros2_header_generator/templates_generator.py" --outdir "${MROS2_QOS_ROOT}/platform" --indir "${CMAKE_SOURCE_DIR}/main")
add_custom_target(Template SOURCES "${MROS2_TEMPLATES_HPP}")
add_dependencies(${COMPONENT_LIB} Template)

message(STATUS "PROJECT=${PROJECT_NAME}")
add_custom_command(
        OUTPUT sdkconfig
        COMMAND grep -q CONFIG_LWIP_IPV6=y "${CMAKE_SOURCE_DIR}/sdkconfig" || exit 0 && sed -i 's/CONFIG_LWIP_IPV6=y/CONFIG_LWIP_IPV6=n/g' "${CMAKE_SOURCE_DIR}/sdkconfig")
add_custom_target(Sdkconfig SOURCES sdkconfig)
add_dependencies(${COMPONENT_LIB} Sdkconfig)
