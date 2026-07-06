/* mROS2 Step 9b: KEEP_ALL Bidirectional Test
 *
 * Extended version of step9 with bidirectional communication:
 * - ESP32 publishes to /from_esp32 (KEEP_ALL)
 * - ESP32 subscribes from /to_esp32 (KEEP_ALL)
 * - Tests KEEP_ALL history management in both directions
 * - Verifies resource rejection when cache is full
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

static uint32_t rx_count = 0;

void subscriber_callback(std_msgs::msg::String *msg)
{
  rx_count++;
  if (rx_count <= 5 || rx_count % 5 == 0) {
    MROS2_INFO("  RX from ROS2 [%u]: %s", rx_count, msg->data.c_str());
  }
}

extern "C" void app_main(void)
{
  turn_off_onboard_rgb();

  printf("\n\n");
  printf("============================================\n");
  printf("  Step 9b: KEEP_ALL Bidirectional Test\n");
  printf("============================================\n");
  printf("Tests KEEP_ALL history in both directions:\n");
  printf("  ESP32 → ROS2: Publish with KEEP_ALL\n");
  printf("  ROS2 → ESP32: Subscribe with KEEP_ALL\n");
  printf("============================================\n\n");

  /* Phase 1: Network + Init */
  MROS2_INFO("[Phase 1] Connecting to network...");
  if (!mros2_platform_network_connect()) {
    MROS2_ERROR("Network failed!");
    return;
  }
  MROS2_INFO("  Network OK");

  mros2::init(0, NULL);
  mros2::Node node = mros2::Node::create_node("mros2_step9b_node");
  MROS2_INFO("  mROS2 node created");

  /* Create KEEP_ALL QoS */
  mros2::QoSProfile qos;
  qos.reliability = rtps::ReliabilityKind_t::RELIABLE;
  qos.durability = rtps::DurabilityKind_t::VOLATILE;
  qos.history = mros2::HistoryKind::KEEP_ALL;
  qos.depth = 0;  // KEEP_ALL ignores depth
  qos.max_samples = 30;
  qos.max_bytes = 12288;

  /* Phase 2: Create subscriber */
  MROS2_INFO("\n=== Phase 2: Create subscriber ===");
  mros2::Subscriber sub = node.create_subscription<std_msgs::msg::String>(
      "to_esp32", qos, subscriber_callback);
  MROS2_INFO("  Subscriber: /to_esp32 (KEEP_ALL, RELIABLE)");

  /* Phase 3: Create publisher and test KEEP_ALL */
  MROS2_INFO("\n=== Phase 3: Publishing with KEEP_ALL ===");
  mros2::Publisher pub = node.create_publisher<std_msgs::msg::String>(
      "from_esp32", qos);
  MROS2_INFO("  Publisher: /from_esp32 (KEEP_ALL, RELIABLE)");

  // Publish 15 messages to test KEEP_ALL resource limits
  uint32_t accepted = 0;
  uint32_t rejected = 0;
  uint32_t prev_reject = 0;

  for (int i = 0; i < 15; i++) {
    auto msg = std_msgs::msg::String();
    msg.data = "[KEEPALL] #" + std::to_string(i) + " T:" + std::to_string(esp_timer_get_time());
    pub.publish(msg);
    delay_ms(50);

    uint32_t curr_reject = mros2::publisher_resource_reject_count();
    if (i < 5 || curr_reject != prev_reject) {
      MROS2_INFO("  Published #%d: cache=%u, rejected=%u",
                 i,
                 mros2::publisher_history_count(),
                 curr_reject);
    }

    if (curr_reject > prev_reject) {
      rejected++;
      prev_reject = curr_reject;
    } else {
      accepted++;
    }
  }

  MROS2_INFO("  KEEP_ALL publication results:");
  MROS2_INFO("    Accepted: %u", accepted);
  MROS2_INFO("    Rejected: %u", rejected);

  /* Phase 4: Wait for subscriber matching and receive messages */
  MROS2_INFO("\n=== Phase 4: Receiving from ROS2 ===");
  MROS2_INFO("  Waiting for messages from ROS2 (KEEP_ALL)...");

  for (int i = 0; i < 30; i++) {
    mros2::spin_once();
    delay_ms(100);
  }

  /* Final Report */
  MROS2_INFO("\n============================================");
  MROS2_INFO("  KEEP_ALL BIDIRECTIONAL TEST RESULTS");
  MROS2_INFO("============================================");
  MROS2_INFO("ESP32 → ROS2:");
  MROS2_INFO("  History kind: KEEP_ALL");
  MROS2_INFO("  Messages accepted: %u", accepted);
  MROS2_INFO("  Messages rejected: %u", rejected);
  MROS2_INFO("  History cache: %u/%u samples, %u bytes",
             mros2::publisher_history_count(),
             mros2::publisher_history_depth(),
             mros2::publisher_history_bytes());
  MROS2_INFO("  Resource reject count: %u",
             mros2::publisher_resource_reject_count());
  MROS2_INFO("");
  MROS2_INFO("ROS2 → ESP32:");
  MROS2_INFO("  Messages received: %u", rx_count);
  MROS2_INFO("");
  MROS2_INFO("Memory: %u bytes free", esp_get_free_heap_size());
  MROS2_INFO("============================================");

  bool pub_ok = (rejected > 0);  // Should reject when cache full
  bool sub_ok = (rx_count > 0);

  if (pub_ok && sub_ok) {
    MROS2_INFO("\n✅ BIDIRECTIONAL KEEP_ALL TEST PASSED!");
    MROS2_INFO("   Both directions working correctly.");
    MROS2_INFO("   KEEP_ALL correctly rejected messages when cache full.");
  } else {
    if (!pub_ok) {
      MROS2_ERROR("\n⚠️  KEEP_ALL publisher test inconclusive");
      MROS2_ERROR("   Expected some rejections when cache full, got 0");
    }
    if (!sub_ok) {
      MROS2_ERROR("\n❌ KEEP_ALL subscriber test failed");
      MROS2_ERROR("   Expected messages from ROS2, got 0");
    }
  }

  MROS2_INFO("\nEntering idle spin.");
  while (1) {
    mros2::spin();
  }
}
