/* mROS2 Step 8b: TRANSIENT_LOCAL Bidirectional Test
 *
 * Extended version of step8 with bidirectional communication:
 * - ESP32 publishes to /from_esp32 (TRANSIENT_LOCAL)
 * - ESP32 subscribes from /to_esp32 (TRANSIENT_LOCAL)
 * - ROS2 publishes cached messages BEFORE ESP32 starts
 * - ESP32 should receive all cached messages as a late-joiner
 *
 * Tests both directions:
 * 1. ESP32 → ROS2: ESP32 publishes cached messages
 * 2. ROS2 → ESP32: ESP32 receives cached messages as late-joiner
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
static uint32_t cached_msg_count = 0;
static uint32_t fresh_msg_count = 0;

void subscriber_callback(std_msgs::msg::String *msg)
{
  rx_count++;

  // Check if this is a cached message from ROS2
  if (strstr(msg->data.c_str(), "[CACHED]")) {
    cached_msg_count++;
    MROS2_INFO("  RX CACHED [%u]: %s", cached_msg_count, msg->data.c_str());
  } else {
    fresh_msg_count++;
    if (fresh_msg_count <= 3) {
      MROS2_INFO("  RX FRESH [%u]: %s", fresh_msg_count, msg->data.c_str());
    }
  }
}

extern "C" void app_main(void)
{
  turn_off_onboard_rgb();

  printf("\n\n");
  printf("============================================\n");
  printf("  Step 8b: TRANSIENT_LOCAL Bidirectional\n");
  printf("============================================\n");
  printf("This test verifies TRANSIENT_LOCAL in both directions:\n");
  printf("  ESP32 → ROS2: ESP32 publishes cached messages\n");
  printf("  ROS2 → ESP32: ESP32 receives cached messages\n");
  printf("============================================\n\n");

  /* Phase 1: Network + Init */
  MROS2_INFO("[Phase 1] Connecting to network...");
  if (!mros2_platform_network_connect()) {
    MROS2_ERROR("Network failed!");
    return;
  }
  MROS2_INFO("  Network OK");

  mros2::init(0, NULL);
  mros2::Node node = mros2::Node::create_node("mros2_step8b_node");
  MROS2_INFO("  mROS2 node created");

  /* Create TRANSIENT_LOCAL QoS */
  mros2::QoSProfile qos;
  qos.reliability = rtps::ReliabilityKind_t::RELIABLE;
  qos.durability = rtps::DurabilityKind_t::TRANSIENT_LOCAL;
  qos.history = mros2::HistoryKind::KEEP_LAST;
  qos.depth = 10;

  /* Phase 2: Create subscriber FIRST (late-joiner test) */
  MROS2_INFO("\n=== Phase 2: Create subscriber (late-joiner) ===");
  mros2::Subscriber sub = node.create_subscription<std_msgs::msg::String>(
      "to_esp32", qos, subscriber_callback);
  MROS2_INFO("  Subscriber: /to_esp32 (TRANSIENT_LOCAL)");
  MROS2_INFO("  Waiting to receive cached messages from ROS2...");

  // Wait a bit for cached messages to arrive
  delay_ms(5000);

  MROS2_INFO("  Received %u cached messages from ROS2", cached_msg_count);

  /* Phase 3: Create publisher and send cached messages */
  MROS2_INFO("\n=== Phase 3: Publishing cached messages ===");
  mros2::Publisher pub = node.create_publisher<std_msgs::msg::String>(
      "from_esp32", qos);
  MROS2_INFO("  Publisher: /from_esp32 (TRANSIENT_LOCAL)");

  // Publish 8 cached messages
  for (uint32_t i = 0; i < 8; i++) {
    auto msg = std_msgs::msg::String();
    msg.data = "[CACHED] #" + std::to_string(i) + " T:" + std::to_string(esp_timer_get_time());
    pub.publish(msg);
    MROS2_INFO("  Published cached msg #%u", i);
    delay_ms(100);
  }
  MROS2_INFO("  All cached messages published");

  /* Phase 4: Wait for ROS2 subscriber */
  MROS2_INFO("\n=== Phase 4: Waiting for ROS2 subscriber ===");
  uint32_t wait_ms = 0;
  while (!mros2::publisher_matched() && wait_ms < 60000) {
    delay_ms(500);
    wait_ms += 500;
    if (wait_ms % 5000 == 0) {
      MROS2_INFO("  Still waiting... (%ums elapsed)", wait_ms);
    }
  }

  if (mros2::publisher_matched()) {
    MROS2_INFO("  ROS2 subscriber matched after %ums!", wait_ms);
  } else {
    MROS2_ERROR("  No subscriber joined within timeout.");
  }

  /* Phase 5: Continue publishing */
  MROS2_INFO("\n=== Phase 5: Continued publishing ===");
  for (int i = 0; i < 10; i++) {
    auto msg = std_msgs::msg::String();
    msg.data = "[POST_MATCH] #" + std::to_string(i) + " T:" + std::to_string(esp_timer_get_time());
    pub.publish(msg);
    delay_ms(500);
  }

  /* Final Report */
  MROS2_INFO("\n============================================");
  MROS2_INFO("  TRANSIENT_LOCAL BIDIRECTIONAL TEST RESULTS");
  MROS2_INFO("============================================");
  MROS2_INFO("ESP32 → ROS2:");
  MROS2_INFO("  Cached messages published: 8");
  MROS2_INFO("  ROS2 subscriber matched: %s", mros2::publisher_matched() ? "YES" : "NO");
  MROS2_INFO("  History cache: %u/%u samples, %u bytes",
             mros2::publisher_history_count(),
             mros2::publisher_history_depth(),
             mros2::publisher_history_bytes());
  MROS2_INFO("");
  MROS2_INFO("ROS2 → ESP32:");
  MROS2_INFO("  Total RX: %u messages", rx_count);
  MROS2_INFO("  Cached RX: %u messages", cached_msg_count);
  MROS2_INFO("  Fresh RX: %u messages", fresh_msg_count);
  MROS2_INFO("");
  MROS2_INFO("Memory: %u bytes free", esp_get_free_heap_size());
  MROS2_INFO("============================================");

  // Validate bidirectional functionality
  bool esp32_to_ros2_ok = mros2::publisher_matched();
  bool ros2_to_esp32_ok = (cached_msg_count > 0);

  if (esp32_to_ros2_ok && ros2_to_esp32_ok) {
    MROS2_INFO("\n✅ BIDIRECTIONAL TEST PASSED!");
    MROS2_INFO("   Both directions working correctly.");
  } else {
    if (!esp32_to_ros2_ok) {
      MROS2_ERROR("\n❌ ESP32 → ROS2 direction failed!");
    }
    if (!ros2_to_esp32_ok) {
      MROS2_ERROR("\n❌ ROS2 → ESP32 direction failed!");
      MROS2_ERROR("   Expected cached messages from ROS2, got 0");
    }
  }

  MROS2_INFO("\nEntering idle spin.");
  while (1) {
    mros2::spin();
  }
}
