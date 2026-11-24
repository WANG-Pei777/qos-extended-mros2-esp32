cmake_minimum_required(VERSION 3.8)
project(echo_cpp)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# Find dependencies
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(std_msgs REQUIRED)

# Echo node executables
add_executable(echo_node src/echo_node.cpp)
ament_target_dependencies(echo_node rclcpp std_msgs)

add_executable(echo_node_lossy src/echo_node_lossy.cpp)
ament_target_dependencies(echo_node_lossy rclcpp std_msgs)

add_executable(qos_compatibility_probe src/qos_compatibility_probe.cpp)
ament_target_dependencies(qos_compatibility_probe rclcpp std_msgs)

add_executable(native_rtt_probe src/native_rtt_probe.cpp)
ament_target_dependencies(native_rtt_probe rclcpp std_msgs)

add_executable(native_rdh_late_join_probe src/native_rdh_late_join_probe.cpp)
ament_target_dependencies(native_rdh_late_join_probe rclcpp std_msgs)

add_executable(upstream_mros2_late_join_probe
  src/upstream_mros2_late_join_probe.cpp)
ament_target_dependencies(upstream_mros2_late_join_probe rclcpp std_msgs)

# Install targets
install(TARGETS
  echo_node
  echo_node_lossy
  qos_compatibility_probe
  native_rtt_probe
  native_rdh_late_join_probe
  upstream_mros2_late_join_probe
  DESTINATION lib/${PROJECT_NAME})

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
