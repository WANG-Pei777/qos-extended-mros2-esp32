cmake_minimum_required(VERSION 3.16)

set(EXTRA_COMPONENT_DIRS ../../components)
add_compile_options(-w)

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(step10_best_effort)
