/**
 * @file echo_node.cpp
 * @brief High-performance C++ echo node for RTT measurement
 *
 * Replaces Python rclpy echo to eliminate Python processing latency from RTT.
 * Subscribes to /qos_eval, echoes back to /qos_eval_reply with minimal latency.
 *
 * Usage:
 *   ros2 run echo_cpp echo_node [--reliable|--best-effort]
 */

#include <chrono>
#include <memory>
#include <string>

#include "rclcpp/rclcpp.hpp"
#include "std_msgs/msg/string.hpp"

using namespace std::chrono_literals;

class EchoNode : public rclcpp::Node
{
public:
  explicit EchoNode(rclcpp::QoS qos_profile)
  : Node("echo_cpp_node"), echo_count_(0)
  {
    // Subscriber to /qos_eval
    subscription_ = this->create_subscription<std_msgs::msg::String>(
      "/qos_eval",
      qos_profile,
      [this](const std_msgs::msg::String::SharedPtr msg) {
        this->echo_callback(msg);
      });

    // Publisher to /qos_eval_reply - MUST match ESP32 QoS exactly
    // F2 fix: Remove deadline/lifespan to avoid "incompatible QoS" warnings
    publisher_ = this->create_publisher<std_msgs::msg::String>(
      "/qos_eval_reply",
      qos_profile);

    RCLCPP_INFO(this->get_logger(),
                "Echo node started, listening on /qos_eval, reply=RELIABLE");
  }

private:
  void echo_callback(const std_msgs::msg::String::SharedPtr msg)
  {
    // Immediate echo back with minimal processing
    publisher_->publish(*msg);
    echo_count_++;

    // Log periodically (every 10 echoes to reduce overhead)
    if (echo_count_ % 10 == 0) {
      RCLCPP_INFO(this->get_logger(), "Echo replies sent: %zu", echo_count_);
    }
  }

  rclcpp::Subscription<std_msgs::msg::String>::SharedPtr subscription_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr publisher_;
  size_t echo_count_;
};

int main(int argc, char * argv[])
{
  rclcpp::init(argc, argv);

  // Parse QoS from command line
  bool use_reliable = true;
  for (int i = 1; i < argc; ++i) {
    std::string arg(argv[i]);
    if (arg == "--best-effort" || arg == "-b") {
      use_reliable = false;
    } else if (arg == "--reliable" || arg == "-r") {
      use_reliable = true;
    }
  }

  // Configure QoS to match ESP32 expectations
  auto qos_profile = rclcpp::QoS(10)
    .reliability(use_reliable ? rclcpp::ReliabilityPolicy::Reliable : rclcpp::ReliabilityPolicy::BestEffort)
    .durability(rclcpp::DurabilityPolicy::Volatile)
    .history(rclcpp::HistoryPolicy::KeepLast)
    .liveliness(rclcpp::LivelinessPolicy::Automatic);

  auto node = std::make_shared<EchoNode>(qos_profile);

  rclcpp::spin(node);
  rclcpp::shutdown();

  return 0;
}
