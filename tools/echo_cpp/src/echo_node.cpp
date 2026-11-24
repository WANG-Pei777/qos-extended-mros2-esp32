/**
 * @file echo_node.cpp
 * @brief High-performance C++ echo node for RTT measurement
 *
 * Replaces Python rclpy echo to eliminate Python processing latency from RTT.
 * Subscribes to /qos_eval, echoes back to /qos_eval_reply with minimal latency.
 *
 * Usage:
 *   ros2 run echo_cpp echo_node [--reliable|--best-effort]
 *       [--transient-local] [--history-depth N]
 *       [--rdh-only]
 *       [--wait-for-reply-reader] [--buffer-durability-probe]
 *       [--defer-subscription-until-spin]
 *       [--reply-liveliness-lease-ms N]
 *       [--topic-base /qos_eval]
 */

#include <chrono>
#include <cstdint>
#include <cstdio>
#include <memory>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

#include "rclcpp/rclcpp.hpp"
#include "std_msgs/msg/string.hpp"

using namespace std::chrono_literals;

class EchoNode : public rclcpp::Node
{
public:
  EchoNode(
    rclcpp::QoS qos_profile, bool use_reliable, bool use_transient_local,
    bool rdh_only,
    bool wait_for_reply_reader, bool buffer_durability_probe,
    bool defer_subscription_until_spin, uint32_t reply_liveliness_lease_ms,
    uint32_t history_depth, const std::string & topic_base)
  : Node("echo_cpp_node"), qos_profile_(qos_profile), topic_base_(topic_base),
    echo_count_(0),
    wait_for_reply_reader_(wait_for_reply_reader),
    buffer_durability_probe_(buffer_durability_probe)
  {
    const std::string reply_topic = topic_base + "_reply";
    // Publisher to /qos_eval_reply. Hardware-facing mros2 runs need the
    // compatibility QoS below. Native ROS 2 equal-semantics experiments pass
    // --rdh-only so Reliability, Durability, and History are the only
    // non-default policies under comparison.
    auto reply_qos = qos_profile;
    if (!rdh_only) {
      // The board's reply subscription requests deadline = 23283064 ns on the
      // wire (mros2 SEDP encodes 100 ms that way); DDS requires offered <=
      // requested, so offer exactly that value.
      reply_qos.deadline(std::chrono::nanoseconds(23283064));
      reply_qos.lifespan(std::chrono::milliseconds(2000));
    }
    if (reply_liveliness_lease_ms != 0) {
      reply_qos.liveliness_lease_duration(
        std::chrono::milliseconds(reply_liveliness_lease_ms));
    }
    publisher_ = this->create_publisher<std_msgs::msg::String>(
      reply_topic,
      reply_qos);

    if (defer_subscription_until_spin) {
      subscription_start_timer_ = this->create_wall_timer(100ms, [this]() {
        this->create_subscription_endpoint();
        subscription_start_timer_->cancel();
      });
    } else {
      create_subscription_endpoint();
    }

    RCLCPP_INFO(this->get_logger(),
                "Echo reply node started, input=%s output=%s qos=%s durability=%s"
                " reply_reader_gate=%s durability_buffer=%s"
                " subscription_start=%s reply_liveliness_lease_ms=%u"
                " history=KEEP_LAST depth=%u extra_qos=%s",
                topic_base.c_str(), reply_topic.c_str(),
                use_reliable ? "RELIABLE" : "BEST_EFFORT",
                use_transient_local ? "TRANSIENT_LOCAL" : "VOLATILE",
                wait_for_reply_reader ? "ON" : "OFF",
                buffer_durability_probe ? "ON" : "OFF",
                defer_subscription_until_spin ? "DEFERRED" : "IMMEDIATE",
                static_cast<unsigned>(reply_liveliness_lease_ms),
                static_cast<unsigned>(history_depth),
                rdh_only ? "DISABLED_RDH_ONLY" : "MROS2_COMPATIBILITY");
  }

private:
  void create_subscription_endpoint()
  {
    if (subscription_) {
      return;
    }
    subscription_ = this->create_subscription<std_msgs::msg::String>(
      topic_base_,
      qos_profile_,
      [this](const std_msgs::msg::String::SharedPtr msg) {
        this->echo_callback(msg);
      });
    RCLCPP_INFO(this->get_logger(), "Echo input subscription active");
  }

  void echo_callback(const std_msgs::msg::String::SharedPtr msg)
  {
    if (buffer_durability_probe_ && msg->data.rfind("D:", 0) == 0) {
      durability_probe_buffer_.push_back(*msg);
      return;
    }

    if (buffer_durability_probe_ && msg->data.rfind("G:", 0) == 0) {
      if (!wait_for_reply_reader()) {
        return;
      }
      for (const auto & buffered : durability_probe_buffer_) {
        publisher_->publish(buffered);
        ++echo_count_;
      }
      RCLCPP_INFO(
        this->get_logger(), "Durability probe replies released: %zu",
        durability_probe_buffer_.size());
      durability_probe_buffer_.clear();
      return;
    }

    if (!wait_for_reply_reader()) {
      return;
    }
    publisher_->publish(*msg);
    echo_count_++;

    // Log periodically (every 10 echoes to reduce overhead)
    if (echo_count_ % 10 == 0) {
      RCLCPP_INFO(this->get_logger(), "Echo replies sent: %zu", echo_count_);
    }
  }

  bool wait_for_reply_reader()
  {
    if (wait_for_reply_reader_ && publisher_->get_subscription_count() == 0) {
      const auto deadline = std::chrono::steady_clock::now() + 5s;
      while (rclcpp::ok() && publisher_->get_subscription_count() == 0 &&
             std::chrono::steady_clock::now() < deadline) {
        std::this_thread::sleep_for(5ms);
      }
      if (publisher_->get_subscription_count() == 0) {
        RCLCPP_ERROR(this->get_logger(), "Reply reader gate timed out");
        return false;
      }
    }
    return true;
  }

  rclcpp::Subscription<std_msgs::msg::String>::SharedPtr subscription_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr publisher_;
  rclcpp::TimerBase::SharedPtr subscription_start_timer_;
  rclcpp::QoS qos_profile_;
  std::string topic_base_;
  size_t echo_count_;
  bool wait_for_reply_reader_;
  bool buffer_durability_probe_;
  std::vector<std_msgs::msg::String> durability_probe_buffer_;
};

int main(int argc, char * argv[])
{
  rclcpp::init(argc, argv);

  // Parse QoS from command line
  bool use_reliable = true;
  bool use_transient_local = false;
  bool rdh_only = false;
  bool wait_for_reply_reader = false;
  bool buffer_durability_probe = false;
  bool defer_subscription_until_spin = false;
  uint32_t reply_liveliness_lease_ms = 0;
  uint32_t history_depth = 10;
  std::string topic_base = "/qos_eval";
  for (int i = 1; i < argc; ++i) {
    std::string arg(argv[i]);
    if (arg == "--best-effort" || arg == "-b") {
      use_reliable = false;
    } else if (arg == "--reliable" || arg == "-r") {
      use_reliable = true;
    } else if (arg == "--transient-local") {
      use_transient_local = true;
    } else if (arg == "--rdh-only") {
      rdh_only = true;
    } else if (arg == "--wait-for-reply-reader") {
      wait_for_reply_reader = true;
    } else if (arg == "--buffer-durability-probe") {
      buffer_durability_probe = true;
    } else if (arg == "--defer-subscription-until-spin") {
      defer_subscription_until_spin = true;
    } else if (arg == "--reply-liveliness-lease-ms") {
      if (i + 1 >= argc) {
        std::fprintf(stderr, "--reply-liveliness-lease-ms requires a value\n");
        rclcpp::shutdown();
        return 2;
      }
      try {
        const unsigned long value = std::stoul(argv[++i]);
        if (value == 0 || value > 10000) {
          throw std::out_of_range("lease");
        }
        reply_liveliness_lease_ms = static_cast<uint32_t>(value);
      } catch (const std::exception &) {
        std::fprintf(stderr, "reply liveliness lease must be in 1..10000 ms\n");
        rclcpp::shutdown();
        return 2;
      }
    } else if (arg == "--history-depth") {
      if (i + 1 >= argc) {
        std::fprintf(stderr, "--history-depth requires a value\n");
        rclcpp::shutdown();
        return 2;
      }
      try {
        const unsigned long value = std::stoul(argv[++i]);
        if (value == 0 || value > 1000) {
          throw std::out_of_range("history depth");
        }
        history_depth = static_cast<uint32_t>(value);
      } catch (const std::exception &) {
        std::fprintf(stderr, "history depth must be in 1..1000\n");
        rclcpp::shutdown();
        return 2;
      }
    } else if (arg == "--topic-base") {
      if (i + 1 >= argc) {
        std::fprintf(stderr, "--topic-base requires a value\n");
        rclcpp::shutdown();
        return 2;
      }
      topic_base = argv[++i];
    } else if (arg.rfind("--topic-base=", 0) == 0) {
      topic_base = arg.substr(std::string("--topic-base=").size());
    }
  }
  if (topic_base.empty()) {
    std::fprintf(stderr, "topic base must not be empty\n");
    rclcpp::shutdown();
    return 2;
  }
  if (topic_base.front() != '/') {
    topic_base.insert(topic_base.begin(), '/');
  }
  while (topic_base.size() > 1 && topic_base.back() == '/') {
    topic_base.pop_back();
  }

  // Configure QoS to match ESP32 expectations
  auto qos_profile = rclcpp::QoS(rclcpp::KeepLast(history_depth))
    .reliability(use_reliable ? rclcpp::ReliabilityPolicy::Reliable : rclcpp::ReliabilityPolicy::BestEffort)
    .durability(
      use_transient_local ? rclcpp::DurabilityPolicy::TransientLocal :
      rclcpp::DurabilityPolicy::Volatile)
    .history(rclcpp::HistoryPolicy::KeepLast)
    .liveliness(rclcpp::LivelinessPolicy::Automatic);

  auto node = std::make_shared<EchoNode>(
    qos_profile, use_reliable, use_transient_local, rdh_only,
    wait_for_reply_reader,
    buffer_durability_probe, defer_subscription_until_spin,
    reply_liveliness_lease_ms, history_depth, topic_base);

  rclcpp::spin(node);
  rclcpp::shutdown();

  return 0;
}
