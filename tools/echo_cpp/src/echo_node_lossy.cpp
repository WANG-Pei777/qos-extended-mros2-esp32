/**
 * @file echo_node_lossy.cpp
 * @brief C++ echo node with configurable packet drop for testing RELIABLE QoS
 *
 * Application-layer packet loss injection when tc netem is not available.
 * Drops packets probabilistically before echoing back.
 *
 * Usage:
 *   ros2 run echo_cpp echo_node_lossy --loss 0.05  # 5% loss
 */

#include <chrono>
#include <memory>
#include <random>
#include <string>

#include "rclcpp/rclcpp.hpp"
#include "std_msgs/msg/string.hpp"

using namespace std::chrono_literals;

class EchoNodeLossy : public rclcpp::Node
{
public:
  EchoNodeLossy(rclcpp::QoS qos_profile, double loss_rate)
  : Node("echo_cpp_lossy"), echo_count_(0), drop_count_(0), loss_rate_(loss_rate),
    rng_(std::random_device{}()), dist_(0.0, 1.0)
  {
    subscription_ = this->create_subscription<std_msgs::msg::String>(
      "/qos_eval",
      qos_profile,
      [this](const std_msgs::msg::String::SharedPtr msg) {
        this->echo_callback(msg);
      });

    auto reply_qos = qos_profile;
    reply_qos.deadline(std::chrono::milliseconds(100));
    reply_qos.lifespan(std::chrono::milliseconds(2000));

    publisher_ = this->create_publisher<std_msgs::msg::String>("/qos_eval_reply", reply_qos);

    RCLCPP_INFO(this->get_logger(),
                "Echo node (lossy) started, listening on /qos_eval, loss_rate=%.1f%%",
                loss_rate_ * 100.0);
  }

private:
  void echo_callback(const std_msgs::msg::String::SharedPtr msg)
  {
    // Probabilistic drop
    if (dist_(rng_) < loss_rate_) {
      drop_count_++;
      // Silently drop (simulates network loss)
      return;
    }

    // Echo back
    publisher_->publish(*msg);
    echo_count_++;

    if ((echo_count_ + drop_count_) % 10 == 0) {
      RCLCPP_INFO(this->get_logger(),
                  "Echoed: %zu, Dropped: %zu (%.1f%%)",
                  echo_count_, drop_count_,
                  100.0 * drop_count_ / (echo_count_ + drop_count_));
    }
  }

  rclcpp::Subscription<std_msgs::msg::String>::SharedPtr subscription_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr publisher_;
  size_t echo_count_;
  size_t drop_count_;
  double loss_rate_;
  std::mt19937 rng_;
  std::uniform_real_distribution<double> dist_;
};

int main(int argc, char * argv[])
{
  rclcpp::init(argc, argv);

  bool use_reliable = true;
  double loss_rate = 0.0;

  for (int i = 1; i < argc; ++i) {
    std::string arg(argv[i]);
    if (arg == "--best-effort" || arg == "-b") {
      use_reliable = false;
    } else if (arg == "--reliable" || arg == "-r") {
      use_reliable = true;
    } else if (arg == "--loss" || arg == "-l") {
      if (i + 1 < argc) {
        loss_rate = std::stod(argv[++i]);
      }
    }
  }

  auto qos_profile = rclcpp::QoS(10)
    .reliability(use_reliable ? rclcpp::ReliabilityPolicy::Reliable : rclcpp::ReliabilityPolicy::BestEffort)
    .durability(rclcpp::DurabilityPolicy::Volatile)
    .history(rclcpp::HistoryPolicy::KeepLast)
    .liveliness(rclcpp::LivelinessPolicy::Automatic);

  auto node = std::make_shared<EchoNodeLossy>(qos_profile, loss_rate);

  rclcpp::spin(node);
  rclcpp::shutdown();

  return 0;
}
