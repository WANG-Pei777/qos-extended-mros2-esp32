idf_component_register(SRCS "app.cpp"
                    INCLUDE_DIRS "."
                    PRIV_REQUIRES "mros2-esp32" "esp_timer" "driver")

if("$ENV{MROS2_QOS_FULL_RELIABLE_REPLY}" STREQUAL "1")
  target_compile_definitions(${COMPONENT_LIB} PRIVATE MROS2_QOS_FULL_RELIABLE_REPLY=1)
endif()

if("$ENV{MROS2_QOS_MODE}" STREQUAL "best_effort")
  target_compile_definitions(${COMPONENT_LIB} PRIVATE MROS2_QOS_BEST_EFFORT=1)
endif()
