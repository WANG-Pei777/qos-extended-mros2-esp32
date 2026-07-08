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

# Install targets
install(TARGETS
  echo_node
  echo_node_lossy
  DESTINATION lib/${PROJECT_NAME})

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
