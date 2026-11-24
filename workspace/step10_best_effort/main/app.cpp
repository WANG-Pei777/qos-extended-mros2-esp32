/* Step 10: BEST_EFFORT Performance Benchmark
 *
 * Measures throughput and latency with BEST_EFFORT QoS.
 * Compare with step7 (RELIABLE) results.
 */

#include "mros2.h"
#include "mros2-platform.h"
#include "std_msgs/msg/string.hpp"
#include "driver/gpio.h"
#include "driver/rmt_tx.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <cstring>
#include <atomic>

static void turn_off_onboard_rgb()
{
  constexpr gpio_num_t rgb_gpio = GPIO_NUM_48;
  constexpr uint32_t rmt_resolution_hz = 10 * 1000 * 1000;
  rmt_channel_handle_t channel = nullptr;
  rmt_tx_channel_config_t ch_cfg = {};
  ch_cfg.gpio_num = rgb_gpio;
  ch_cfg.clk_src = RMT_CLK_SRC_DEFAULT;
  ch_cfg.resolution_hz = rmt_resolution_hz;
  ch_cfg.mem_block_symbols = 64;
  ch_cfg.trans_queue_depth = 1;
  if (rmt_new_tx_channel(&ch_cfg, &channel) == ESP_OK) {
    rmt_encoder_handle_t encoder = nullptr;
    rmt_copy_encoder_config_t ec = {};
    if (rmt_new_copy_encoder(&ec, &encoder) == ESP_OK) {
      rmt_symbol_word_t off[24] = {};
      for (auto &s : off) { s.level0 = 1; s.duration0 = 3; s.level1 = 0; s.duration1 = 9; }
      rmt_enable(channel);
      rmt_transmit_config_t tc = {}; tc.loop_count = 0;
      rmt_transmit(channel, encoder, off, sizeof(off), &tc);
      rmt_tx_wait_all_done(channel, 100);
      rmt_del_encoder(encoder);
    }
    rmt_disable(channel);
    rmt_del_channel(channel);
  }
  gpio_reset_pin(rgb_gpio);
  gpio_set_direction(rgb_gpio, GPIO_MODE_OUTPUT);
  gpio_set_level(rgb_gpio, 0);
}

static void delay_ms(uint32_t ms) { osDelay(ms); }

static std::atomic<uint32_t> rx_count{0};
static uint64_t first_rx_us = 0, last_rx_us = 0;
static uint32_t min_rtt = 0xFFFFFFFF, max_rtt = 0;
static uint64_t total_rtt = 0;
static uint32_t rtt_samples = 0;

void sub_callback(std_msgs::msg::String *msg)
{
  uint64_t now = esp_timer_get_time();
  if (first_rx_us == 0) first_rx_us = now;
  last_rx_us = now;
  rx_count++;

  const char *ts = strstr(msg->data.c_str(), "T:");
  if (ts) {
    uint64_t msg_us = strtoull(ts + 2, nullptr, 10);
    if (msg_us > 0 && now > msg_us) {
      uint32_t rtt = (uint32_t)(now - msg_us);
      if (rtt < min_rtt) min_rtt = rtt;
      if (rtt > max_rtt) max_rtt = rtt;
      total_rtt += rtt;
      rtt_samples++;
    }
  }
}

extern "C" void app_main(void)
{
  turn_off_onboard_rgb();

  printf("\n============================================\n");
  printf("  Step 10: BEST_EFFORT Performance Benchmark\n");
  printf("============================================\n");
  printf("  Reliability: BEST_EFFORT\n");
  printf("  Durability:  VOLATILE\n");
  printf("  History:     KEEP_LAST(5)\n");
  printf("============================================\n\n");

  MROS2_INFO("[Phase 1] Connecting to network...");
  if (!mros2_platform_network_connect()) { MROS2_ERROR("Network failed!"); return; }
  MROS2_INFO("  Network OK");

  mros2::init(0, NULL);
  mros2::Node node = mros2::Node::create_node("mros2_step10_node");

  mros2::QoSProfile pub_qos;
  pub_qos.reliability = rtps::ReliabilityKind_t::BEST_EFFORT;
  pub_qos.durability = rtps::DurabilityKind_t::VOLATILE;
  pub_qos.history = mros2::HistoryKind::KEEP_LAST;
  pub_qos.depth = 5;

  mros2::QoSProfile sub_qos = pub_qos;

  mros2::Publisher pub = node.create_publisher<std_msgs::msg::String>("step10_best_effort", pub_qos);
  mros2::Subscriber sub = node.create_subscription<std_msgs::msg::String>("step10_best_effort_reply", sub_qos, sub_callback);
  MROS2_INFO("  Publisher: /step10_best_effort (BEST_EFFORT)");
  MROS2_INFO("  Subscriber: /step10_best_effort_reply (BEST_EFFORT)");

  MROS2_INFO("  Waiting for endpoint match...");
  uint32_t wait_ms = 0;
  while (!mros2::publisher_matched() && wait_ms < 70000) { delay_ms(100); wait_ms += 100; }
  MROS2_INFO("  Matched after %ums", wait_ms);
  delay_ms(3000);

  // Publish 40 messages at 100ms interval
  MROS2_INFO("\n=== Publishing 40 messages ===");
  uint64_t tx_start = esp_timer_get_time();
  uint32_t tx_count = 0;
  for (int i = 0; i < 40; i++) {
    auto msg = std_msgs::msg::String();
    uint64_t tx_us = esp_timer_get_time();
    msg.data = "[BE] #" + std::to_string(i) + " T:" + std::to_string(tx_us);
    pub.publish(msg);
    tx_count++;
    delay_ms(100);
  }
  uint64_t tx_end = esp_timer_get_time();
  MROS2_INFO("  TX done. Waiting for replies...");
  delay_ms(5000);

  // Report
  MROS2_INFO("\n============================================");
  MROS2_INFO("  BEST_EFFORT RESULTS");
  MROS2_INFO("============================================");
  MROS2_INFO("  TX: %u msgs", tx_count);
  MROS2_INFO("  RX: %u msgs", rx_count.load());
  float tx_dur = (tx_end - tx_start) / 1000000.0f;
  MROS2_INFO("  TX throughput: %.1f msg/s", tx_count / tx_dur);
  if (rtt_samples > 0) {
    MROS2_INFO("  RTT latency:");
    MROS2_INFO("    Min: %u us", min_rtt);
    MROS2_INFO("    Max: %u us", max_rtt);
    MROS2_INFO("    Avg: %u us", (uint32_t)(total_rtt / rtt_samples));
  }
  MROS2_INFO("  Memory: %u bytes free", esp_get_free_heap_size());
  MROS2_INFO("============================================");

  while (1) { mros2::spin(); }
}
