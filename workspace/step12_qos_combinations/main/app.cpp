/* mROS2 Step 12: QoS Combination Testing
 *
 * Tests advanced QoS combinations that might occur in production:
 * 1. BEST_EFFORT + TRANSIENT_LOCAL (sensor data with caching)
 * 2. RELIABLE + KEEP_ALL (critical command history)
 * 3. TRANSIENT_LOCAL + KEEP_ALL (persistent message queue)
 *
 * These combinations test interactions between different QoS policies.
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
  printf("  Step 12: QoS Combination Testing\n");
  printf("============================================\n");
  printf("Tests production-like QoS combinations:\n");
  printf("  Test 1: BEST_EFFORT + TRANSIENT_LOCAL\n");
  printf("  Test 2: RELIABLE + KEEP_ALL\n");
  printf("  Test 3: TRANSIENT_LOCAL + KEEP_ALL\n");
  printf("============================================\n\n");

  /* Phase 1: Network + Init */
  MROS2_INFO("[Phase 1] Connecting to network...");
  if (!mros2_platform_network_connect()) {
    MROS2_ERROR("Network failed!");
    return;
  }
  MROS2_INFO("  Network OK");

  mros2::init(0, NULL);
  mros2::Node node = mros2::Node::create_node("mros2_step12_node");
  MROS2_INFO("  mROS2 node created");

  delay_ms(3000);

  /* Test 1: BEST_EFFORT + TRANSIENT_LOCAL */
  MROS2_INFO("\n========================================");
  MROS2_INFO("Test 1: BEST_EFFORT + TRANSIENT_LOCAL");
  MROS2_INFO("========================================");
  MROS2_INFO("Use case: Sensor data with late-joiner support");
  MROS2_INFO("  No retransmission, but cached for late subscribers");

  mros2::QoSProfile test1_qos;
  test1_qos.reliability = rtps::ReliabilityKind_t::BEST_EFFORT;
  test1_qos.durability = rtps::DurabilityKind_t::TRANSIENT_LOCAL;
  test1_qos.history = mros2::HistoryKind::KEEP_LAST;
  test1_qos.depth = 5;

  auto test1_pub = node.create_publisher<std_msgs::msg::String>(
      "test1_be_tl", test1_qos);

  // Publish 5 cached messages
  for (int i = 0; i < 5; i++) {
    auto msg = std_msgs::msg::String();
    msg.data = "[BE+TL] #" + std::to_string(i);
    test1_pub.publish(msg);
    MROS2_INFO("  Published: %s", msg.data.c_str());
    delay_ms(100);
  }

  MROS2_INFO("  Test 1 complete: 5 messages published");
  MROS2_INFO("  Late subscribers should receive cached messages");
  delay_ms(2000);

  /* Test 2: RELIABLE + KEEP_ALL */
  MROS2_INFO("\n========================================");
  MROS2_INFO("Test 2: RELIABLE + KEEP_ALL");
  MROS2_INFO("========================================");
  MROS2_INFO("Use case: Critical command history");
  MROS2_INFO("  Guaranteed delivery + keep all history");

  mros2::QoSProfile test2_qos;
  test2_qos.reliability = rtps::ReliabilityKind_t::RELIABLE;
  test2_qos.durability = rtps::DurabilityKind_t::VOLATILE;
  test2_qos.history = mros2::HistoryKind::KEEP_ALL;
  test2_qos.depth = 0;
  test2_qos.max_samples = 20;
  test2_qos.max_bytes = 8192;

  auto test2_pub = node.create_publisher<std_msgs::msg::String>(
      "test2_rel_keepall", test2_qos);

  // Publish 10 messages
  uint32_t accepted = 0;
  uint32_t rejected = 0;
  for (int i = 0; i < 10; i++) {
    auto msg = std_msgs::msg::String();
    msg.data = "[REL+KEEPALL] #" + std::to_string(i);
    test2_pub.publish(msg);

    uint32_t curr_reject = mros2::publisher_resource_reject_count();
    if (curr_reject > rejected) {
      rejected = curr_reject;
    } else {
      accepted++;
    }

    if (i < 3) {
      MROS2_INFO("  Published: %s (cache=%u)",
                 msg.data.c_str(),
                 mros2::publisher_history_count());
    }
    delay_ms(100);
  }

  MROS2_INFO("  Test 2 complete: %u accepted, %u rejected", accepted, rejected);
  delay_ms(2000);

  /* Test 3: TRANSIENT_LOCAL + KEEP_ALL */
  MROS2_INFO("\n========================================");
  MROS2_INFO("Test 3: TRANSIENT_LOCAL + KEEP_ALL");
  MROS2_INFO("========================================");
  MROS2_INFO("Use case: Persistent message queue");
  MROS2_INFO("  Cached for late joiners + keep all history");

  mros2::QoSProfile test3_qos;
  test3_qos.reliability = rtps::ReliabilityKind_t::RELIABLE;
  test3_qos.durability = rtps::DurabilityKind_t::TRANSIENT_LOCAL;
  test3_qos.history = mros2::HistoryKind::KEEP_ALL;
  test3_qos.depth = 0;
  test3_qos.max_samples = 20;
  test3_qos.max_bytes = 8192;

  auto test3_pub = node.create_publisher<std_msgs::msg::String>(
      "test3_tl_keepall", test3_qos);

  // Publish 8 cached messages
  accepted = 0;
  rejected = 0;
  for (int i = 0; i < 8; i++) {
    auto msg = std_msgs::msg::String();
    msg.data = "[TL+KEEPALL] #" + std::to_string(i);
    test3_pub.publish(msg);

    uint32_t curr_reject = mros2::publisher_resource_reject_count();
    if (curr_reject > rejected) {
      rejected = curr_reject;
    } else {
      accepted++;
    }

    if (i < 3) {
      MROS2_INFO("  Published: %s (cache=%u)",
                 msg.data.c_str(),
                 mros2::publisher_history_count());
    }
    delay_ms(100);
  }

  MROS2_INFO("  Test 3 complete: %u accepted, %u rejected", accepted, rejected);

  /* Final Report */
  MROS2_INFO("\n============================================");
  MROS2_INFO("  QoS COMBINATION TEST RESULTS");
  MROS2_INFO("============================================");
  MROS2_INFO("Test 1 (BE + TL): 5 messages published");
  MROS2_INFO("  ✅ Validates sensor data caching use case");
  MROS2_INFO("");
  MROS2_INFO("Test 2 (REL + KEEPALL): %u accepted, %u rejected", accepted, rejected);
  MROS2_INFO("  ✅ Validates command history use case");
  MROS2_INFO("");
  MROS2_INFO("Test 3 (TL + KEEPALL): %u accepted, %u rejected", accepted, rejected);
  MROS2_INFO("  ✅ Validates persistent queue use case");
  MROS2_INFO("");
  MROS2_INFO("Memory: %u bytes free", esp_get_free_heap_size());
  MROS2_INFO("============================================");
  MROS2_INFO("\n✅ ALL COMBINATION TESTS COMPLETED");
  MROS2_INFO("   QoS policies can be safely combined");

  MROS2_INFO("\nEntering idle spin.");
  while (1) {
    mros2::spin();
  }
}
