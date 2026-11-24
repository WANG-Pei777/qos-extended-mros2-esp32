/**
 * @file native_rtt_probe.cpp
 * @brief Native ROS 2 publisher/subscriber probe for controlled RTT baselines.
 */

#include <algorithm>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

#include "rclcpp/rclcpp.hpp"
#include "std_msgs/msg/string.hpp"

using namespace std::chrono_literals;

namespace
{

struct Options
{
  bool reliable = true;
  bool transient_local = false;
  uint32_t history_depth = 10;
  uint32_t payload_bytes = 512;
  uint32_t rate_hz = 50;
  uint32_t target_tx = 1000;
  uint32_t grace_ms = 5000;
  std::string run_token = "native-baseline-smoke";
  std::string topic_base = "/native_baseline";
};

uint32_t parse_uint(const char * option, const char * value)
{
  try {
    const unsigned long parsed = std::stoul(value);
    if (parsed > UINT32_MAX) {
      throw std::out_of_range(option);
    }
    return static_cast<uint32_t>(parsed);
  } catch (const std::exception &) {
    throw std::invalid_argument(std::string(option) + " requires an unsigned integer");
  }
}

Options parse_options(int argc, char * argv[])
{
  Options options;
  for (int i = 1; i < argc; ++i) {
    const std::string argument(argv[i]);
    if (argument == "--reliable") {
      options.reliable = true;
    } else if (argument == "--best-effort") {
      options.reliable = false;
    } else if (argument == "--transient-local") {
      options.transient_local = true;
    } else if (argument == "--volatile") {
      options.transient_local = false;
    } else if (
      argument == "--payload-bytes" || argument == "--rate-hz" ||
      argument == "--target-tx" || argument == "--grace-ms" ||
      argument == "--history-depth" ||
      argument == "--run-token" || argument == "--topic-base")
    {
      if (i + 1 >= argc) {
        throw std::invalid_argument(argument + " requires a value");
      }
      const char * value = argv[++i];
      if (argument == "--payload-bytes") {
        options.payload_bytes = parse_uint(argument.c_str(), value);
      } else if (argument == "--rate-hz") {
        options.rate_hz = parse_uint(argument.c_str(), value);
      } else if (argument == "--target-tx") {
        options.target_tx = parse_uint(argument.c_str(), value);
      } else if (argument == "--grace-ms") {
        options.grace_ms = parse_uint(argument.c_str(), value);
      } else if (argument == "--history-depth") {
        options.history_depth = parse_uint(argument.c_str(), value);
      } else if (argument == "--run-token") {
        options.run_token = value;
      } else {
        options.topic_base = value;
      }
    } else {
      throw std::invalid_argument("unknown option: " + argument);
    }
  }

  if (options.payload_bytes < 32 || options.payload_bytes > 2048) {
    throw std::invalid_argument("payload bytes must be in 32..2048");
  }
  if (options.rate_hz == 0 || 1000 % options.rate_hz != 0) {
    throw std::invalid_argument("rate must be a positive divisor of 1000 Hz");
  }
  if (options.target_tx == 0 || options.target_tx > 1000000) {
    throw std::invalid_argument("target TX must be in 1..1000000");
  }
  if (options.grace_ms > 30000) {
    throw std::invalid_argument("grace must be at most 30000 ms");
  }
  if (options.history_depth == 0 || options.history_depth > 1000) {
    throw std::invalid_argument("history depth must be in 1..1000");
  }
  if (options.run_token.empty()) {
    throw std::invalid_argument("run token must not be empty");
  }
  if (options.topic_base.empty()) {
    throw std::invalid_argument("topic base must not be empty");
  }
  if (options.topic_base.front() != '/') {
    options.topic_base.insert(options.topic_base.begin(), '/');
  }
  while (options.topic_base.size() > 1 && options.topic_base.back() == '/') {
    options.topic_base.pop_back();
  }
  return options;
}

int64_t steady_us()
{
  return std::chrono::duration_cast<std::chrono::microseconds>(
    std::chrono::steady_clock::now().time_since_epoch()).count();
}

std::string payload(
  char kind, uint32_t sequence, int64_t timestamp_us, uint32_t payload_bytes)
{
  char prefix[96] = {};
  const int length = std::snprintf(
    prefix, sizeof(prefix), "%c:%u T:%lld ", kind, sequence,
    static_cast<long long>(timestamp_us));
  if (length <= 0 || static_cast<uint32_t>(length) > payload_bytes) {
    throw std::runtime_error("payload prefix exceeds configured payload size");
  }
  std::string result(prefix, static_cast<size_t>(length));
  result.resize(payload_bytes, 'x');
  return result;
}

class NativeRttProbe : public rclcpp::Node
{
public:
  explicit NativeRttProbe(const Options & options)
  : Node("native_rtt_probe"), options_(options),
    seen_(options.target_tx, false), rtt_by_sequence_(options.target_tx, 0),
    tx_offset_by_sequence_(options.target_tx, 0),
    rx_offset_by_sequence_(options.target_tx, 0)
  {
    auto qos = rclcpp::QoS(rclcpp::KeepLast(options.history_depth))
      .reliability(
        options.reliable ? rclcpp::ReliabilityPolicy::Reliable :
        rclcpp::ReliabilityPolicy::BestEffort)
      .durability(
        options.transient_local ? rclcpp::DurabilityPolicy::TransientLocal :
        rclcpp::DurabilityPolicy::Volatile)
      .history(rclcpp::HistoryPolicy::KeepLast)
      .liveliness(rclcpp::LivelinessPolicy::Automatic);
    publisher_ = create_publisher<std_msgs::msg::String>(
      options.topic_base, qos);
    subscription_ = create_subscription<std_msgs::msg::String>(
      options.topic_base + "_reply", qos,
      [this](const std_msgs::msg::String::SharedPtr message) {
        receive(message->data);
      });
  }

  bool wait_for_endpoints(std::chrono::seconds timeout)
  {
    const auto deadline = std::chrono::steady_clock::now() + timeout;
    while (
      rclcpp::ok() && std::chrono::steady_clock::now() < deadline &&
      (publisher_->get_subscription_count() == 0 ||
      subscription_->get_publisher_count() == 0))
    {
      std::this_thread::sleep_for(20ms);
    }
    return publisher_->get_subscription_count() > 0 &&
           subscription_->get_publisher_count() > 0;
  }

  bool warmup(std::chrono::seconds timeout)
  {
    const auto started = std::chrono::steady_clock::now();
    const auto deadline = started + timeout;
    uint32_t sequence = 0;
    while (rclcpp::ok() && std::chrono::steady_clock::now() < deadline) {
      std_msgs::msg::String message;
      message.data = payload('W', sequence++, steady_us(), options_.payload_bytes);
      publisher_->publish(message);
      std::unique_lock<std::mutex> lock(mutex_);
      if (condition_.wait_for(lock, 100ms, [this]() {return ready_;})) {
        ready_ms_ = std::chrono::duration_cast<std::chrono::milliseconds>(
          std::chrono::steady_clock::now() - started).count();
        return true;
      }
    }
    return false;
  }

  void measure()
  {
    {
      std::lock_guard<std::mutex> lock(mutex_);
      accepting_ = true;
    }
    std::printf(
      "NATIVE_MEASUREMENT_START schema=1 run_token=%s target_tx=%u"
      " period_ms=%u durability=%s history=KEEP_LAST depth=%u\n",
      options_.run_token.c_str(), options_.target_tx, 1000 / options_.rate_hz,
      options_.transient_local ? "TRANSIENT_LOCAL" : "VOLATILE",
      options_.history_depth);
    std::fflush(stdout);
    measurement_start_us_ = steady_us();
    const auto period = std::chrono::milliseconds(1000 / options_.rate_hz);
    auto next = std::chrono::steady_clock::now();
    for (uint32_t sequence = 0; sequence < options_.target_tx; ++sequence) {
      std::this_thread::sleep_until(next);
      std_msgs::msg::String message;
      const int64_t sent_us = steady_us();
      tx_offset_by_sequence_[sequence] =
        static_cast<uint64_t>(sent_us - measurement_start_us_);
      message.data = payload('M', sequence, sent_us, options_.payload_bytes);
      publisher_->publish(message);
      next += period;
    }

    std::unique_lock<std::mutex> lock(mutex_);
    condition_.wait_for(
      lock, std::chrono::milliseconds(options_.grace_ms),
      [this]() {return received_ == options_.target_tx;});
    accepting_ = false;
  }

  int report() const
  {
    std::vector<uint64_t> samples;
    uint32_t duplicates = 0;
    uint32_t malformed = 0;
    uint32_t inversions = 0;
    int64_t ready_ms = -1;
    {
      std::lock_guard<std::mutex> lock(mutex_);
      duplicates = duplicates_;
      malformed = malformed_;
      inversions = inversions_;
      ready_ms = ready_ms_;
      for (uint32_t sequence = 0; sequence < options_.target_tx; ++sequence) {
        if (seen_[sequence]) {
          samples.push_back(rtt_by_sequence_[sequence]);
          std::printf(
            "NATIVE_RTT_SAMPLE schema=1 run_token=%s seq=%u rtt_us=%llu"
            " tx_offset_us=%llu rx_offset_us=%llu\n",
            options_.run_token.c_str(), sequence,
            static_cast<unsigned long long>(rtt_by_sequence_[sequence]),
            static_cast<unsigned long long>(tx_offset_by_sequence_[sequence]),
            static_cast<unsigned long long>(rx_offset_by_sequence_[sequence]));
        }
      }
    }

    std::sort(samples.begin(), samples.end());
    uint64_t sum = 0;
    for (const uint64_t value : samples) {
      sum += value;
    }
    const uint64_t minimum = samples.empty() ? 0 : samples.front();
    const uint64_t maximum = samples.empty() ? 0 : samples.back();
    const uint64_t average = samples.empty() ? 0 : sum / samples.size();
    const size_t p95_index = samples.empty() ? 0 :
      (95 * samples.size() + 99) / 100 - 1;
    const uint64_t p95 = samples.empty() ? 0 : samples[p95_index];
    const uint32_t missing =
      options_.target_tx - static_cast<uint32_t>(samples.size());
    std::printf(
      "NATIVE_FINAL schema=1 run_token=%s qos=%s payload_bytes=%u"
      " rate_hz=%u target_tx=%u tx=%u rx=%zu missing=%u duplicates=%u"
      " malformed=%u arrival_inversions=%u min_us=%llu avg_us=%llu"
      " p95_us=%llu max_us=%llu rtt_sum_us=%llu ready_ms=%lld"
      " durability=%s history=KEEP_LAST depth=%u\n",
      options_.run_token.c_str(),
      options_.reliable ? "RELIABLE" : "BEST_EFFORT",
      options_.payload_bytes, options_.rate_hz, options_.target_tx,
      options_.target_tx, samples.size(), missing, duplicates, malformed,
      inversions, static_cast<unsigned long long>(minimum),
      static_cast<unsigned long long>(average),
      static_cast<unsigned long long>(p95),
      static_cast<unsigned long long>(maximum),
      static_cast<unsigned long long>(sum),
      static_cast<long long>(ready_ms),
      options_.transient_local ? "TRANSIENT_LOCAL" : "VOLATILE",
      options_.history_depth);
    std::fflush(stdout);
    return 0;
  }

private:
  void receive(const std::string & message)
  {
    if (message.rfind("W:", 0) == 0) {
      std::lock_guard<std::mutex> lock(mutex_);
      ready_ = true;
      condition_.notify_all();
      return;
    }
    if (message.rfind("M:", 0) != 0) {
      return;
    }

    unsigned int sequence = 0;
    long long sent_us = 0;
    if (std::sscanf(message.c_str(), "M:%u T:%lld", &sequence, &sent_us) != 2) {
      std::lock_guard<std::mutex> lock(mutex_);
      ++malformed_;
      return;
    }
    const int64_t received_us = steady_us();
    const int64_t elapsed = received_us - sent_us;
    std::lock_guard<std::mutex> lock(mutex_);
    if (!accepting_) {
      return;
    }
    if (sequence >= options_.target_tx || elapsed <= 0 || elapsed >= 10000000) {
      ++malformed_;
      return;
    }
    if (seen_[sequence]) {
      ++duplicates_;
      return;
    }
    seen_[sequence] = true;
    rtt_by_sequence_[sequence] = static_cast<uint64_t>(elapsed);
    rx_offset_by_sequence_[sequence] =
      static_cast<uint64_t>(received_us - measurement_start_us_);
    if (have_sequence_ && sequence < highest_sequence_) {
      ++inversions_;
    } else {
      highest_sequence_ = sequence;
      have_sequence_ = true;
    }
    ++received_;
    condition_.notify_all();
  }

  Options options_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr publisher_;
  rclcpp::Subscription<std_msgs::msg::String>::SharedPtr subscription_;
  mutable std::mutex mutex_;
  std::condition_variable condition_;
  bool ready_ = false;
  bool accepting_ = false;
  bool have_sequence_ = false;
  uint32_t received_ = 0;
  uint32_t duplicates_ = 0;
  uint32_t malformed_ = 0;
  uint32_t inversions_ = 0;
  uint32_t highest_sequence_ = 0;
  int64_t ready_ms_ = -1;
  int64_t measurement_start_us_ = -1;
  std::vector<bool> seen_;
  std::vector<uint64_t> rtt_by_sequence_;
  std::vector<uint64_t> tx_offset_by_sequence_;
  std::vector<uint64_t> rx_offset_by_sequence_;
};

}  // namespace

int main(int argc, char * argv[])
{
  Options options;
  try {
    options = parse_options(argc, argv);
  } catch (const std::exception & exception) {
    std::fprintf(stderr, "native_rtt_probe: %s\n", exception.what());
    return 2;
  }

  rclcpp::init(argc, argv);
  auto node = std::make_shared<NativeRttProbe>(options);
  rclcpp::executors::SingleThreadedExecutor executor;
  executor.add_node(node);
  std::thread spin_thread([&executor]() {executor.spin();});

  int status = 0;
  if (!node->wait_for_endpoints(15s)) {
    std::fprintf(stderr, "native_rtt_probe: endpoint match timed out\n");
    status = 3;
  } else if (!node->warmup(10s)) {
    std::fprintf(stderr, "native_rtt_probe: warmup echo timed out\n");
    status = 4;
  } else {
    std::this_thread::sleep_for(1s);
    node->measure();
    status = node->report();
  }

  rclcpp::shutdown();
  spin_thread.join();
  return status;
}
