/* mros2 Step 8: TRANSIENT_LOCAL Durability Verification
 *
 * Tests TRANSIENT_LOCAL late-joiner behavior:
 * 1. Publish N messages with TRANSIENT_LOCAL durability before any subscriber exists.
 * 2. Wait for a ROS2 subscriber to join.
 * 3. Verify the late-joining subscriber receives cached messages.
 *
 * This firmware requires a ROS2 subscriber running on the host side:
 *   ros2 topic echo /step8_transient_local --qos-reliability RELIABLE \
 *     --qos-durability TRANSIENT_LOCAL
 *
 * The test is manual: the human operator starts the ROS2 subscriber
 * after ESP32 has published, and checks whether cached messages appear.
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

static constexpr uint32_t CACHED_MSG_COUNT = 10;
static constexpr uint32_t WAIT_FOR_SUBSCRIBER_MS = 60000;

extern "C" void app_main(void)
{
  turn_off_onboard_rgb();

  printf("\n\n");
  printf("============================================\n");
  printf("  Step 8: TRANSIENT_LOCAL Durability Test\n");
  printf("============================================\n");
  printf("Policy:\n");
  printf("  Reliability : RELIABLE\n");
  printf("  Durability  : TRANSIENT_LOCAL\n");
  printf("  History     : KEEP_LAST(10)\n");
  printf("  Cached msgs : %u (published before subscriber joins)\n", CACHED_MSG_COUNT);
  printf("============================================\n\n");

  /* Phase 1: Network + Init */
  MROS2_INFO("[Phase 1] Connecting to network...");
  if (!mros2_platform_network_connect()) {
    MROS2_ERROR("Network failed!");
    return;
  }
  MROS2_INFO("  Network OK");

  mros2::init(0, NULL);
  mros2::Node node = mros2::Node::create_node("mros2_step8_node");
  MROS2_INFO("  mROS2 node created");

  /* Phase 2: Create publisher with TRANSIENT_LOCAL */
  mros2::QoSProfile pub_qos;
  pub_qos.reliability = rtps::ReliabilityKind_t::RELIABLE;
  pub_qos.durability = rtps::DurabilityKind_t::TRANSIENT_LOCAL;
  pub_qos.history = mros2::HistoryKind::KEEP_LAST;
  pub_qos.depth = 10;

  mros2::Publisher pub = node.create_publisher<std_msgs::msg::String>(
      "step8_transient_local", pub_qos);
  MROS2_INFO("  Publisher: /step8_transient_local (TRANSIENT_LOCAL)");

  /* Phase 3: Publish cached messages before any subscriber joins */
  MROS2_INFO("\n=== Phase 3: Publishing %u cached messages ===", CACHED_MSG_COUNT);
  for (uint32_t i = 0; i < CACHED_MSG_COUNT; i++) {
    auto msg = std_msgs::msg::String();
    msg.data = "[CACHED] #" + std::to_string(i) + " T:" + std::to_string(esp_timer_get_time());
    pub.publish(msg);
    MROS2_INFO("  Published cached msg #%u", i);
    delay_ms(100);
  }
  MROS2_INFO("  All cached messages published.");

  /* Phase 4: Wait for subscriber */
  MROS2_INFO("\n=== Phase 4: Waiting for ROS2 subscriber to join ===");
  MROS2_INFO("  Run on host:");
  MROS2_INFO("    ros2 topic echo /step8_transient_local --qos-reliability RELIABLE \\");
  MROS2_INFO("      --qos-durability TRANSIENT_LOCAL");
  MROS2_INFO("  Waiting up to %ums...", WAIT_FOR_SUBSCRIBER_MS);

  uint32_t wait_ms = 0;
  while (!mros2::publisher_matched() && wait_ms < WAIT_FOR_SUBSCRIBER_MS) {
    delay_ms(500);
    wait_ms += 500;
    if (wait_ms % 5000 == 0) {
      MROS2_INFO("  Still waiting... (%ums elapsed)", wait_ms);
    }
  }

  if (mros2::publisher_matched()) {
    MROS2_INFO("  Subscriber matched after %ums!", wait_ms);
    MROS2_INFO("  If ROS2 host received the %u cached messages, TRANSIENT_LOCAL is working.",
               CACHED_MSG_COUNT);
  } else {
    MROS2_ERROR("  No subscriber joined within timeout.");
    MROS2_ERROR("  Start the ROS2 subscriber and reset ESP32 to retry.");
  }

  /* Phase 5: Continue publishing after match */
  MROS2_INFO("\n=== Phase 5: Continued publishing (10 msgs @ 500ms) ===");
  for (int i = 0; i < 10; i++) {
    auto msg = std_msgs::msg::String();
    msg.data = "[POST_MATCH] #" + std::to_string(i) + " T:" + std::to_string(esp_timer_get_time());
    pub.publish(msg);
    MROS2_INFO("  Published post-match msg #%d", i);
    delay_ms(500);
  }

  MROS2_INFO("\n============================================");
  MROS2_INFO("  TRANSIENT_LOCAL TEST COMPLETE");
  MROS2_INFO("============================================");
  MROS2_INFO("  Cached messages published: %u", CACHED_MSG_COUNT);
  MROS2_INFO("  Subscriber matched: %s", mros2::publisher_matched() ? "yes" : "no");
  MROS2_INFO("  RTPS history cache: %u/%u samples, %u bytes",
             mros2::publisher_history_count(),
             mros2::publisher_history_depth(),
             mros2::publisher_history_bytes());
  MROS2_INFO("  Memory: %u bytes free", esp_get_free_heap_size());
  MROS2_INFO("============================================");
  MROS2_INFO("  Check ROS2 host for received cached messages.");
  MROS2_INFO("  If cached messages appear, TRANSIENT_LOCAL durability is working.");

  /* Idle spin */
  MROS2_INFO("Entering idle spin.");
  while (1) {
    mros2::spin();
  }
}
