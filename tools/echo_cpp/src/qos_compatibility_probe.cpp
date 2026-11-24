/** Machine-readable ROS 2 endpoint probe for Seven-QoS compatibility cases. */

#include <algorithm>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <thread>

#include "rclcpp/rclcpp.hpp"
#include "std_msgs/msg/string.hpp"

using namespace std::chrono_literals;

namespace {

struct Options {
  std::string case_id;
  std::string role;
  std::string topic = "/seven_qos_compatibility";
  std::string reliability;
  std::string durability;
  std::string deadline_ms = "infinite";
  std::string liveliness_lease_ms = "infinite";
  bool expected_match = false;
  uint32_t wait_ms = 10000;
  uint32_t post_match_ms = 3000;
  uint32_t message_count = 10;
  uint32_t history_depth = 100;
  uint32_t period_ms = 100;
  uint32_t pre_publish_ms = 0;
  int64_t expected_rx_count = -1;
  std::string endpoint_gate = "none";
  std::string publish_gate = "none";
  uint32_t endpoint_gate_timeout_ms = 60000;
};

bool token_is_safe(const std::string & value)
{
  return !value.empty() && value.find_first_of(" \t\r\n=") == std::string::npos;
}

uint32_t fnv1a(const std::string & value)
{
  uint32_t hash = 2166136261U;
  for (const unsigned char byte : value) {
    hash ^= byte;
    hash *= 16777619U;
  }
  return hash;
}

uint32_t parse_u32(const std::string & value, const char * name)
{
  std::size_t consumed = 0;
  const unsigned long parsed = std::stoul(value, &consumed, 10);
  if (consumed != value.size() || parsed > UINT32_MAX) {
    throw std::invalid_argument(std::string("invalid ") + name);
  }
  return static_cast<uint32_t>(parsed);
}

std::string option_value(int argc, char * argv[], int & index, const std::string & name)
{
  const std::string argument(argv[index]);
  const std::string prefix = name + "=";
  if (argument.compare(0, prefix.size(), prefix) == 0) {
    return argument.substr(prefix.size());
  }
  if (argument == name && index + 1 < argc) {
    return argv[++index];
  }
  throw std::invalid_argument(name + " requires a value");
}

bool is_option(const std::string & argument, const std::string & name)
{
  return argument == name || argument.compare(0, name.size() + 1, name + "=") == 0;
}

Options parse_options(int argc, char * argv[])
{
  Options options;
  for (int index = 1; index < argc; ++index) {
    const std::string argument(argv[index]);
    if (argument == "--help") {
      std::cout
        << "Usage: qos_compatibility_probe --case-id ID --role publisher|subscriber "
        << "--reliability reliable|best_effort --durability volatile|transient_local "
        << "--deadline-ms N|infinite --liveliness-lease-ms N|infinite "
        << "--expected-match 0|1 [--topic NAME] [--wait-ms N] "
        << "[--post-match-ms N] [--message-count N] [--period-ms N] "
        << "[--history-depth N] "
        << "[--pre-publish-ms N] [--expected-rx-count N|any] "
        << "[--endpoint-gate PATH] [--publish-gate PATH] "
        << "[--endpoint-gate-timeout-ms N]\n";
      std::exit(0);
    } else if (is_option(argument, "--case-id")) {
      options.case_id = option_value(argc, argv, index, "--case-id");
    } else if (is_option(argument, "--role")) {
      options.role = option_value(argc, argv, index, "--role");
    } else if (is_option(argument, "--topic")) {
      options.topic = option_value(argc, argv, index, "--topic");
    } else if (is_option(argument, "--reliability")) {
      options.reliability = option_value(argc, argv, index, "--reliability");
    } else if (is_option(argument, "--durability")) {
      options.durability = option_value(argc, argv, index, "--durability");
    } else if (is_option(argument, "--deadline-ms")) {
      options.deadline_ms = option_value(argc, argv, index, "--deadline-ms");
    } else if (is_option(argument, "--liveliness-lease-ms")) {
      options.liveliness_lease_ms =
        option_value(argc, argv, index, "--liveliness-lease-ms");
    } else if (is_option(argument, "--expected-match")) {
      const std::string value = option_value(argc, argv, index, "--expected-match");
      if (value != "0" && value != "1") {
        throw std::invalid_argument("--expected-match must be 0 or 1");
      }
      options.expected_match = value == "1";
    } else if (is_option(argument, "--wait-ms")) {
      options.wait_ms = parse_u32(
        option_value(argc, argv, index, "--wait-ms"), "--wait-ms");
    } else if (is_option(argument, "--post-match-ms")) {
      options.post_match_ms = parse_u32(
        option_value(argc, argv, index, "--post-match-ms"), "--post-match-ms");
    } else if (is_option(argument, "--message-count")) {
      options.message_count = parse_u32(
        option_value(argc, argv, index, "--message-count"), "--message-count");
    } else if (is_option(argument, "--history-depth")) {
      options.history_depth = parse_u32(
        option_value(argc, argv, index, "--history-depth"), "--history-depth");
    } else if (is_option(argument, "--period-ms")) {
      options.period_ms = parse_u32(
        option_value(argc, argv, index, "--period-ms"), "--period-ms");
    } else if (is_option(argument, "--pre-publish-ms")) {
      options.pre_publish_ms = parse_u32(
        option_value(argc, argv, index, "--pre-publish-ms"),
        "--pre-publish-ms");
    } else if (is_option(argument, "--expected-rx-count")) {
      const std::string value = option_value(
        argc, argv, index, "--expected-rx-count");
      options.expected_rx_count = value == "any" ? -1 :
        static_cast<int64_t>(parse_u32(value, "--expected-rx-count"));
    } else if (is_option(argument, "--endpoint-gate")) {
      options.endpoint_gate = option_value(argc, argv, index, "--endpoint-gate");
    } else if (is_option(argument, "--publish-gate")) {
      options.publish_gate = option_value(argc, argv, index, "--publish-gate");
    } else if (is_option(argument, "--endpoint-gate-timeout-ms")) {
      options.endpoint_gate_timeout_ms = parse_u32(
        option_value(argc, argv, index, "--endpoint-gate-timeout-ms"),
        "--endpoint-gate-timeout-ms");
    } else {
      throw std::invalid_argument("unknown argument: " + argument);
    }
  }

  if (!token_is_safe(options.case_id)) {
    throw std::invalid_argument("--case-id must be a nonempty machine-safe token");
  }
  if (options.role != "publisher" && options.role != "subscriber") {
    throw std::invalid_argument("--role must be publisher or subscriber");
  }
  if (options.reliability != "reliable" && options.reliability != "best_effort") {
    throw std::invalid_argument("invalid --reliability");
  }
  if (options.durability != "volatile" && options.durability != "transient_local") {
    throw std::invalid_argument("invalid --durability");
  }
  if (options.topic.empty() || options.topic[0] != '/' || !token_is_safe(options.topic)) {
    throw std::invalid_argument("--topic must be an absolute machine-safe ROS name");
  }
  if (options.wait_ms == 0 || options.period_ms == 0 ||
    options.history_depth == 0 || options.history_depth > 1000 ||
    options.endpoint_gate_timeout_ms == 0)
  {
    throw std::invalid_argument(
            "wait, period, history-depth, and gate-timeout values are invalid");
  }
  if (options.endpoint_gate != "none" && !token_is_safe(options.endpoint_gate)) {
    throw std::invalid_argument("--endpoint-gate must be a machine-safe path");
  }
  if (options.publish_gate != "none" && !token_is_safe(options.publish_gate)) {
    throw std::invalid_argument("--publish-gate must be a machine-safe path");
  }
  if (options.deadline_ms != "infinite") {
    parse_u32(options.deadline_ms, "--deadline-ms");
  }
  if (options.liveliness_lease_ms != "infinite") {
    parse_u32(options.liveliness_lease_ms, "--liveliness-lease-ms");
  }
  return options;
}

rclcpp::QoS make_qos(const Options & options)
{
  auto qos = rclcpp::QoS(rclcpp::KeepLast(options.history_depth));
  qos.reliability(
    options.reliability == "reliable" ?
    rclcpp::ReliabilityPolicy::Reliable : rclcpp::ReliabilityPolicy::BestEffort);
  qos.durability(
    options.durability == "transient_local" ?
    rclcpp::DurabilityPolicy::TransientLocal : rclcpp::DurabilityPolicy::Volatile);
  qos.liveliness(rclcpp::LivelinessPolicy::Automatic);
  if (options.deadline_ms != "infinite") {
    qos.deadline(std::chrono::milliseconds(parse_u32(options.deadline_ms, "deadline")));
  }
  if (options.liveliness_lease_ms != "infinite") {
    qos.liveliness_lease_duration(
      std::chrono::milliseconds(
        parse_u32(options.liveliness_lease_ms, "liveliness lease")));
  }
  return qos;
}

class CompatibilityProbe : public rclcpp::Node
{
public:
  explicit CompatibilityProbe(const Options & options)
  : Node("seven_qos_compatibility_probe"), options_(options)
  {
  }

  void create_endpoint()
  {
    endpoint_created_at_ = std::chrono::steady_clock::now();
    const auto qos = make_qos(options_);
    if (options_.role == "publisher") {
      publisher_ = create_publisher<std_msgs::msg::String>(options_.topic, qos);
    } else {
      subscription_ = create_subscription<std_msgs::msg::String>(
        options_.topic, qos,
        [this](const std_msgs::msg::String::SharedPtr message) {
          const auto received_at = std::chrono::steady_clock::now();
          const auto elapsed_us =
            std::chrono::duration_cast<std::chrono::microseconds>(
            received_at - endpoint_created_at_).count();
          if (rx_count_ == 0) {
            first_rx_us_ = elapsed_us;
          }
          last_rx_us_ = elapsed_us;
          ++rx_count_;
          const unsigned first = message->data.empty() ? 0U :
            static_cast<unsigned>(static_cast<unsigned char>(message->data.front()));
          const unsigned last = message->data.empty() ? 0U :
            static_cast<unsigned>(static_cast<unsigned char>(message->data.back()));
          std::cout
            << "QOS_HOST_RX schema=1 case_id=" << options_.case_id
            << " ordinal=" << rx_count_
            << " bytes=" << message->data.size()
            << " first=" << first
            << " last=" << last
            << " hash=" << fnv1a(message->data)
            << " elapsed_us=" << elapsed_us
            << std::endl;
        });
    }
  }

  std::size_t match_count() const
  {
    if (publisher_) {
      return publisher_->get_subscription_count();
    }
    return subscription_ ? subscription_->get_publisher_count() : 0;
  }

  void publish(uint32_t sequence)
  {
    if (!publisher_) {
      return;
    }
    std_msgs::msg::String message;
    message.data = options_.case_id + ":" + std::to_string(sequence);
    publisher_->publish(message);
    ++tx_count_;
  }

  uint32_t tx_count() const {return tx_count_;}
  uint32_t rx_count() const {return rx_count_;}
  int64_t first_rx_us() const {return first_rx_us_;}
  int64_t last_rx_us() const {return last_rx_us_;}
  int64_t rx_span_us() const
  {
    return rx_count_ > 0 ? last_rx_us_ - first_rx_us_ : -1;
  }

private:
  Options options_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr publisher_;
  rclcpp::Subscription<std_msgs::msg::String>::SharedPtr subscription_;
  uint32_t tx_count_ = 0;
  uint32_t rx_count_ = 0;
  std::chrono::steady_clock::time_point endpoint_created_at_{};
  int64_t first_rx_us_ = -1;
  int64_t last_rx_us_ = -1;
};

}  // namespace

int main(int argc, char * argv[])
{
  Options options;
  try {
    options = parse_options(argc, argv);
  } catch (const std::exception & error) {
    std::cerr << "QOS_HOST_ERROR schema=1 reason=invalid_arguments detail="
              << error.what() << '\n';
    return 2;
  }

  rclcpp::init(argc, argv);
  auto node = std::make_shared<CompatibilityProbe>(options);
  std::cout
    << "QOS_HOST_CONFIG schema=1 case_id=" << options.case_id
    << " role=" << options.role
    << " topic=" << options.topic
    << " reliability=" << options.reliability
    << " durability=" << options.durability
    << " deadline_ms=" << options.deadline_ms
    << " liveliness=automatic"
    << " liveliness_lease_ms=" << options.liveliness_lease_ms
    << " expected_match=" << (options.expected_match ? 1 : 0)
    << " wait_ms=" << options.wait_ms
    << " post_match_ms=" << options.post_match_ms
    << " message_count=" << options.message_count
    << " history=keep_last"
    << " history_depth=" << options.history_depth
    << " period_ms=" << options.period_ms
    << " pre_publish_ms=" << options.pre_publish_ms
    << " expected_rx_count=" << options.expected_rx_count
    << " endpoint_gate=" << options.endpoint_gate
    << " publish_gate=" << options.publish_gate
    << " endpoint_gate_timeout_ms=" << options.endpoint_gate_timeout_ms
    << std::endl;

  std::cout
    << "QOS_HOST_PARTICIPANT_READY schema=1 case_id=" << options.case_id
    << std::endl;
  if (options.endpoint_gate != "none") {
    const auto gate_started = std::chrono::steady_clock::now();
    while (rclcpp::ok() && !std::ifstream(options.endpoint_gate).good()) {
      rclcpp::spin_some(node);
      const auto gate_elapsed_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now() - gate_started).count();
      if (gate_elapsed_ms >= options.endpoint_gate_timeout_ms) {
        std::cerr
          << "QOS_HOST_ERROR schema=1 case_id=" << options.case_id
          << " reason=endpoint_gate_timeout" << std::endl;
        rclcpp::shutdown();
        return 3;
      }
      std::this_thread::sleep_for(10ms);
    }
  }
  node->create_endpoint();
  std::cout
    << "QOS_HOST_ENDPOINT_READY schema=1 case_id=" << options.case_id
    << " role=" << options.role << std::endl;

  const auto started = std::chrono::steady_clock::now();
  auto matched_at = std::chrono::steady_clock::time_point{};
  auto next_publish = started;
  std::size_t maximum_match_count = 0;
  while (rclcpp::ok()) {
    rclcpp::spin_some(node);
    const auto now = std::chrono::steady_clock::now();
    const auto elapsed_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
      now - started).count();
    const std::size_t current_match_count = node->match_count();
    maximum_match_count = std::max(maximum_match_count, current_match_count);
    if (current_match_count > 0 && matched_at == std::chrono::steady_clock::time_point{}) {
      matched_at = now;
      next_publish = now + std::chrono::milliseconds(options.pre_publish_ms);
      std::cout
        << "QOS_HOST_MATCHED schema=1 case_id=" << options.case_id
        << " role=" << options.role
        << " match_count=" << current_match_count
        << std::endl;
    }
    if (current_match_count > 0 && options.role == "publisher" &&
      node->tx_count() < options.message_count && now >= next_publish &&
      (options.publish_gate == "none" || std::ifstream(options.publish_gate).good()))
    {
      node->publish(node->tx_count());
      next_publish = now + std::chrono::milliseconds(options.period_ms);
    }

    bool finished = elapsed_ms >= options.wait_ms;
    if (options.expected_match && matched_at != std::chrono::steady_clock::time_point{}) {
      const auto post_match_elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
        now - matched_at).count();
      const bool io_goal_met = options.role == "publisher" ?
        node->tx_count() == options.message_count :
        (options.expected_rx_count >= 0 ?
        node->rx_count() == static_cast<uint32_t>(options.expected_rx_count) :
        node->rx_count() > 0);
      finished = finished ||
        (post_match_elapsed >= options.post_match_ms && io_goal_met);
    }
    if (finished) {
      break;
    }
    std::this_thread::sleep_for(10ms);
  }

  rclcpp::spin_some(node);
  const bool actual_match = maximum_match_count > 0;
  bool passed = actual_match == options.expected_match;
  if (options.expected_match) {
    if (options.role == "publisher") {
      passed = passed && node->tx_count() == options.message_count;
    } else if (options.expected_rx_count >= 0) {
      passed = passed && node->rx_count() ==
        static_cast<uint32_t>(options.expected_rx_count);
    } else {
      passed = passed && node->rx_count() > 0;
    }
  } else {
    passed = passed && node->tx_count() == 0 && node->rx_count() == 0;
  }
  std::cout
    << "QOS_HOST_FINAL schema=1 case_id=" << options.case_id
    << " role=" << options.role
    << " expected_match=" << (options.expected_match ? 1 : 0)
    << " actual_match=" << (actual_match ? 1 : 0)
    << " max_match_count=" << maximum_match_count
    << " tx=" << node->tx_count()
    << " rx=" << node->rx_count()
    << " first_rx_us=" << node->first_rx_us()
    << " last_rx_us=" << node->last_rx_us()
    << " rx_span_us=" << node->rx_span_us()
    << " status=" << (passed ? "PASS" : "FAIL") << std::endl;
  rclcpp::shutdown();
  return passed ? 0 : 1;
}
