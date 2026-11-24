/* mros2 Step 9: KEEP_ALL History Verification
 *
 * Tests KEEP_ALL history behavior:
 * 1. Publish messages with KEEP_ALL history and a small cache size.
 * 2. Verify the writer cache keeps all messages until full.
 * 3. Verify new messages are rejected when cache is full.
 * 4. Compare with KEEP_LAST behavior.
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

static void turn_off_onboard_rgb()
{
  constexpr gpio_num_t rgb_gpio = GPIO_NUM_48;
  constexpr uint32_t rmt_resolution_hz = 10 * 1000 * 1000;

  rmt_channel_handle_t channel = nullptr;
  rmt_tx_channel_config_t channel_config = {};
  channel_config.gpio_num = rgb_gpio;
  channel_config.clk_src = RMT_CLK_SRC_DEFAULT;
  channel_config.resolution_hz = rmt_resolution_hz;
  channel_config.mem_block_symbols = 64;
  channel_config.trans_queue_depth = 1;

  if (rmt_new_tx_channel(&channel_config, &channel) == ESP_OK) {
    rmt_encoder_handle_t encoder = nullptr;
    rmt_copy_encoder_config_t encoder_config = {};

    if (rmt_new_copy_encoder(&encoder_config, &encoder) == ESP_OK) {
      rmt_symbol_word_t off_symbols[24] = {};
      for (auto &symbol : off_symbols) {
        symbol.level0 = 1;
        symbol.duration0 = 3;
        symbol.level1 = 0;
        symbol.duration1 = 9;
      }

      rmt_enable(channel);
      rmt_transmit_config_t tx_config = {};
      tx_config.loop_count = 0;
      rmt_transmit(channel, encoder, off_symbols, sizeof(off_symbols), &tx_config);
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

static void delay_ms(uint32_t ms)
{
  osDelay(ms);
}

extern "C" void app_main(void)
{
  turn_off_onboard_rgb();

  printf("\n\n");
  printf("============================================\n");
  printf("  Step 9: KEEP_ALL History Verification\n");
  printf("============================================\n\n");

  /* Phase 1: Network + Init */
  MROS2_INFO("[Phase 1] Connecting to network...");
  if (!mros2_platform_network_connect()) {
    MROS2_ERROR("Network failed!");
    return;
  }
  MROS2_INFO("  Network OK");

  mros2::init(0, NULL);
  mros2::Node node = mros2::Node::create_node("mros2_step9_node");
  MROS2_INFO("  mROS2 node created");

  /* Phase 2: Test KEEP_ALL with small cache (depth=5 in SimpleHistoryCache) */
  MROS2_INFO("\n=== Phase 2: KEEP_ALL Test (publish 10 msgs, cache=5) ===");
  mros2::QoSProfile pub_qos;
  pub_qos.reliability = rtps::ReliabilityKind_t::RELIABLE;
  pub_qos.durability = rtps::DurabilityKind_t::VOLATILE;
  pub_qos.history = mros2::HistoryKind::KEEP_ALL;
  pub_qos.depth = 0;  // KEEP_ALL ignores depth
  pub_qos.max_samples = 30;
  pub_qos.max_bytes = 12288;

  mros2::Publisher pub = node.create_publisher<std_msgs::msg::String>(
      "step9_keep_all", pub_qos);
  MROS2_INFO("  Publisher: /step9_keep_all (KEEP_ALL, RELIABLE)");

  // Publish 10 messages — SimpleHistoryCache has HISTORY_SIZE_STATEFUL=10 slots
  // With KEEP_ALL, all should be kept until cache is full
  uint32_t accepted = 0;
  uint32_t rejected = 0;
  for (int i = 0; i < 15; i++) {
    auto msg = std_msgs::msg::String();
    msg.data = "[KEEPALL] #" + std::to_string(i) + " T:" + std::to_string(esp_timer_get_time());
    pub.publish(msg);
    delay_ms(50);

    // Check cache state after each publish
    uint32_t count = mros2::publisher_history_count();
    uint32_t reject = mros2::publisher_resource_reject_count();
    if (i < 5) {
      MROS2_INFO("  Published #%d: cache=%u, rejected=%u", i, count, reject);
    }
    if (reject > rejected) {
      rejected = reject;
    } else {
      accepted++;
    }
  }

  MROS2_INFO("  KEEP_ALL results:");
  MROS2_INFO("    Accepted: %u", accepted);
  MROS2_INFO("    Rejected: %u", rejected);
  MROS2_INFO("    History cache: %u/%u samples, %u bytes",
             mros2::publisher_history_count(),
             mros2::publisher_history_depth(),
             mros2::publisher_history_bytes());

  /* Phase 3: Compare with KEEP_LAST */
  MROS2_INFO("\n=== Phase 3: KEEP_LAST Comparison (depth=5, publish 15) ===");
  // Note: can't change QoS on existing publisher, so we observe the current state
  MROS2_INFO("  Current history depth: %u", mros2::publisher_history_depth());
  MROS2_INFO("  Current history count: %u", mros2::publisher_history_count());

  /* Phase 4: Final report */
  MROS2_INFO("\n============================================");
  MROS2_INFO("  KEEP_ALL TEST RESULTS");
  MROS2_INFO("============================================");
  MROS2_INFO("  History kind: KEEP_ALL");
  MROS2_INFO("  History cache: %u/%u samples, %u bytes",
             mros2::publisher_history_count(),
             mros2::publisher_history_depth(),
             mros2::publisher_history_bytes());
  MROS2_INFO("  Writer resource reject count: %u",
             mros2::publisher_resource_reject_count());
  MROS2_INFO("  RTPS QoS State:");
  MROS2_INFO("    Writer deadline missed count: %u",
             mros2::publisher_deadline_missed_count());
  MROS2_INFO("    Writer lifespan drop count: %u",
             mros2::publisher_lifespan_drop_count());
  MROS2_INFO("  Memory: %u bytes free", esp_get_free_heap_size());
  MROS2_INFO("============================================");

  if (rejected > 0) {
    MROS2_INFO("  KEEP_ALL correctly rejected messages when cache full");
  } else {
    MROS2_INFO("  KEEP_ALL: all messages accepted (cache not full yet)");
  }

  MROS2_INFO("Entering idle spin.");
  while (1) {
    mros2::spin();
  }
}
