/**
 * @file app_lossy.cpp
 * @brief Loss-tolerant workload for E2/E6 experiments
 *
 * Unlike qos_eval (validation mode), this app continues even if some packets drop.
 * Used for RELIABLE QoS testing under controlled packet loss.
 */

#include "mros2.h"
#include "mros2-platform.h"
#include "std_msgs/msg/string.hpp"
#include <atomic>
#include <string>
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

extern "C" {
void app_main(void);
}

#define delay_ms(ms) vTaskDelay(pdMS_TO_TICKS(ms))

std::atomic<uint32_t> msg_count{0};
std::atomic<uint32_t> reply_count{0};

struct PerfStats {
  uint64_t first_tx_us = 0;
  uint64_t last_tx_us = 0;
  uint32_t tx_count = 0;
  uint32_t min_latency_us = UINT32_MAX;
  uint32_t max_latency_us = 0;
  uint64_t total_latency_us = 0;
  uint32_t latency_samples = 0;
} perf;

void subscription_callback(std_msgs::msg::String *msg) {
  // Parse timestamp
  const char *ts_found = strstr(msg->data.c_str(), "T:");
  if (!ts_found) return;

  uint64_t now = esp_timer_get_time();
  uint64_t msg_us = strtoull(ts_found + 2, nullptr, 10);

  // Calculate RTT
  if (msg_us > 0 && now > msg_us) {
    uint32_t rtt_us = (uint32_t)(now - msg_us);
    if (rtt_us < perf.min_latency_us) perf.min_latency_us = rtt_us;
    if (rtt_us > perf.max_latency_us) perf.max_latency_us = rtt_us;
    perf.total_latency_us += rtt_us;
    perf.latency_samples++;
  }

  reply_count++;
}

void app_main(void) {
  MROS2_INFO("========================================");
  MROS2_INFO("app_lossy: Loss-Tolerant Workload");
  MROS2_INFO("========================================");

  mros2::init(0, nullptr);
  mros2::Node node = mros2::Node::create_node("mros2_node");

  // RELIABLE QoS (using same API as app.cpp)
  auto qos = mros2::QOS_DEFAULT;

  mros2::Publisher pub = node.create_publisher<std_msgs::msg::String>("qos_eval", qos);
  mros2::Subscriber sub = node.create_subscription<std_msgs::msg::String>(
      "qos_eval_reply", qos, subscription_callback);

  MROS2_INFO("  Waiting for endpoint discovery...");
  uint32_t wait_ms = 0;
  while (!(mros2::publisher_matched() && mros2::subscriber_matched()) && wait_ms < 30000) {
    delay_ms(100);
    wait_ms += 100;
  }
  MROS2_INFO("  Match state: publisher=%s subscriber=%s wait=%ums",
             mros2::publisher_matched() ? "yes" : "no",
             mros2::subscriber_matched() ? "yes" : "no", wait_ms);

  if (!(mros2::publisher_matched() && mros2::subscriber_matched())) {
    MROS2_ERROR("  Match failed, stopping");
    osDelay(osWaitForever);
  }

  delay_ms(5000);

  // Send 40 messages @ 100ms (no warm-up validation)
  MROS2_INFO("\n=== Starting test (40 msgs @ 100ms) ===");
  perf.first_tx_us = esp_timer_get_time();

  for (int i = 0; i < 40; i++) {
    auto msg = std_msgs::msg::String();
    uint64_t tx_us = esp_timer_get_time();
    msg.data = "[TEST] #" + std::to_string(i) + " T:" + std::to_string(tx_us);
    pub.publish(msg);
    msg_count++;
    perf.tx_count++;
    delay_ms(100);
  }

  perf.last_tx_us = esp_timer_get_time();
  delay_ms(5000); // Wait for replies

  // Print results
  MROS2_INFO("============================================");
  MROS2_INFO("Test Complete");
  MROS2_INFO("============================================");
  MROS2_INFO("  TX: %u msgs", msg_count.load());
  MROS2_INFO("  RX: %u msgs", reply_count.load());

  if (perf.first_tx_us > 0 && perf.last_tx_us > perf.first_tx_us) {
    float tx_duration_s = (perf.last_tx_us - perf.first_tx_us) / 1000000.0f;
    MROS2_INFO("  TX throughput: %.1f msg/s", perf.tx_count / tx_duration_s);
  }

  if (perf.latency_samples > 0) {
    MROS2_INFO("  Latency (round-trip):");
    MROS2_INFO("    Min: %u us", perf.min_latency_us);
    MROS2_INFO("    Max: %u us", perf.max_latency_us);
    MROS2_INFO("    Avg: %u us", (uint32_t)(perf.total_latency_us / perf.latency_samples));
    MROS2_INFO("    Samples: %u", perf.latency_samples);
  } else {
    MROS2_INFO("  Latency: no echo replies received");
  }

  MROS2_INFO("Memory: %u bytes free", esp_get_free_heap_size());
  MROS2_INFO("============================================");

  // Print RX stats
  MROS2_INFO("=== Receive Path Statistics ===");
  mros2::printRxStats();

  MROS2_INFO("Test complete.");

  osDelay(osWaitForever);
}
