/* mROS2 Step 11: QoS Mismatch Testing
 *
 * Tests DDS QoS compatibility rules:
 * 1. RELIABLE pub + BEST_EFFORT sub → should match ✅
 * 2. BEST_EFFORT pub + RELIABLE sub → should reject ❌
 * 3. VOLATILE pub + TRANSIENT_LOCAL sub → should match ⚠️
 * 4. TRANSIENT_LOCAL pub + VOLATILE sub → should match (no cache) ⚠️
 *
 * This firmware tests ESP32 as both publisher and subscriber with various
 * QoS combinations to verify DDS compatibility rules.
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

// Test result tracking
struct TestResult {
  const char* test_name;
  bool expected_match;
  bool actual_matched;
  uint32_t messages_sent;
  uint32_t messages_received;
  bool passed;
};

static TestResult test_results[4];
static uint32_t test_index = 0;
static uint32_t rx_count = 0;

void subscriber_callback(std_msgs::msg::String *msg)
{
  rx_count++;
  if (rx_count <= 3) {
    MROS2_INFO("  RX [%u]: %s", rx_count, msg->data.c_str());
  }
}

static void run_test(const char* test_name,
                     mros2::Node& node,
                     const char* pub_topic,
                     const char* sub_topic,
                     mros2::QoSProfile& pub_qos,
                     mros2::QoSProfile& sub_qos,
                     bool should_match,
                     uint32_t test_duration_ms)
{
  MROS2_INFO("\n========================================");
  MROS2_INFO("Test: %s", test_name);
  MROS2_INFO("========================================");
  MROS2_INFO("Publisher QoS:");
  MROS2_INFO("  Reliability: %s",
             pub_qos.reliability == rtps::ReliabilityKind_t::RELIABLE ? "RELIABLE" : "BEST_EFFORT");
  MROS2_INFO("  Durability: %s",
             pub_qos.durability == rtps::DurabilityKind_t::VOLATILE ? "VOLATILE" : "TRANSIENT_LOCAL");
  MROS2_INFO("Subscriber QoS:");
  MROS2_INFO("  Reliability: %s",
             sub_qos.reliability == rtps::ReliabilityKind_t::RELIABLE ? "RELIABLE" : "BEST_EFFORT");
  MROS2_INFO("  Durability: %s",
             sub_qos.durability == rtps::DurabilityKind_t::VOLATILE ? "VOLATILE" : "TRANSIENT_LOCAL");
  MROS2_INFO("Expected: %s", should_match ? "MATCH" : "REJECT");

  // Create publisher and subscriber
  auto pub = node.create_publisher<std_msgs::msg::String>(pub_topic, pub_qos);
  auto sub = node.create_subscription<std_msgs::msg::String>(
      sub_topic, sub_qos, subscriber_callback);

  rx_count = 0;

  // Wait for matching
  MROS2_INFO("Waiting for endpoint discovery...");
  uint32_t wait_ms = 0;
  const uint32_t max_wait = 10000;
  while (!mros2::publisher_matched() && wait_ms < max_wait) {
    delay_ms(500);
    wait_ms += 500;
  }

  bool matched = mros2::publisher_matched();
  MROS2_INFO("Publisher matched: %s (after %ums)", matched ? "YES" : "NO", wait_ms);

  // Publish test messages
  uint32_t tx_count = 0;
  if (matched || !should_match) {
    MROS2_INFO("Publishing 10 test messages...");
    for (int i = 0; i < 10; i++) {
      auto msg = std_msgs::msg::String();
      msg.data = "[TEST] #" + std::to_string(i) + " T:" + std::to_string(esp_timer_get_time());
      pub.publish(msg);
      tx_count++;
      delay_ms(100);
    }

    // Wait for messages to be received
    delay_ms(test_duration_ms);
  }

  // Record results
  test_results[test_index].test_name = test_name;
  test_results[test_index].expected_match = should_match;
  test_results[test_index].actual_matched = matched;
  test_results[test_index].messages_sent = tx_count;
  test_results[test_index].messages_received = rx_count;

  // Determine if test passed
  bool test_passed = false;
  if (should_match) {
    // Should match: expect matched=true and messages received
    test_passed = matched && (rx_count > 0);
  } else {
    // Should NOT match: expect matched=false or no messages received
    test_passed = !matched || (rx_count == 0);
  }

  test_results[test_index].passed = test_passed;

  MROS2_INFO("----------------------------------------");
  MROS2_INFO("Test Result: %s", test_passed ? "PASS ✅" : "FAIL ❌");
  MROS2_INFO("  TX: %u, RX: %u", tx_count, rx_count);
  MROS2_INFO("========================================\n");

  test_index++;
  delay_ms(2000);
}

extern "C" void app_main(void)
{
  turn_off_onboard_rgb();

  printf("\n\n");
  printf("============================================\n");
  printf("  Step 11: QoS Mismatch Testing\n");
  printf("============================================\n");
  printf("This test validates DDS QoS compatibility rules:\n");
  printf("  Test 1: RELIABLE pub + BEST_EFFORT sub\n");
  printf("  Test 2: BEST_EFFORT pub + RELIABLE sub\n");
  printf("  Test 3: VOLATILE pub + TRANSIENT_LOCAL sub\n");
  printf("  Test 4: TRANSIENT_LOCAL pub + VOLATILE sub\n");
  printf("============================================\n\n");

  /* Phase 1: Network + Init */
  MROS2_INFO("[Phase 1] Connecting to network...");
  if (!mros2_platform_network_connect()) {
    MROS2_ERROR("Network failed!");
    return;
  }
  MROS2_INFO("  Network OK");

  mros2::init(0, NULL);
  mros2::Node node = mros2::Node::create_node("mros2_step11_node");
  MROS2_INFO("  mROS2 node created");

  delay_ms(3000);

  /* Test 1: RELIABLE pub + BEST_EFFORT sub → should MATCH ✅ */
  mros2::QoSProfile test1_pub_qos;
  test1_pub_qos.reliability = rtps::ReliabilityKind_t::RELIABLE;
  test1_pub_qos.durability = rtps::DurabilityKind_t::VOLATILE;
  test1_pub_qos.history = mros2::HistoryKind::KEEP_LAST;
  test1_pub_qos.depth = 5;

  mros2::QoSProfile test1_sub_qos;
  test1_sub_qos.reliability = rtps::ReliabilityKind_t::BEST_EFFORT;
  test1_sub_qos.durability = rtps::DurabilityKind_t::VOLATILE;
  test1_sub_qos.history = mros2::HistoryKind::KEEP_LAST;
  test1_sub_qos.depth = 5;

  run_test("Test 1: RELIABLE pub + BEST_EFFORT sub",
           node, "/test1_pub", "/test1_sub",
           test1_pub_qos, test1_sub_qos, true, 3000);

  /* Test 2: BEST_EFFORT pub + RELIABLE sub → should REJECT ❌ */
  mros2::QoSProfile test2_pub_qos;
  test2_pub_qos.reliability = rtps::ReliabilityKind_t::BEST_EFFORT;
  test2_pub_qos.durability = rtps::DurabilityKind_t::VOLATILE;
  test2_pub_qos.history = mros2::HistoryKind::KEEP_LAST;
  test2_pub_qos.depth = 5;

  mros2::QoSProfile test2_sub_qos;
  test2_sub_qos.reliability = rtps::ReliabilityKind_t::RELIABLE;
  test2_sub_qos.durability = rtps::DurabilityKind_t::VOLATILE;
  test2_sub_qos.history = mros2::HistoryKind::KEEP_LAST;
  test2_sub_qos.depth = 5;

  run_test("Test 2: BEST_EFFORT pub + RELIABLE sub",
           node, "/test2_pub", "/test2_sub",
           test2_pub_qos, test2_sub_qos, false, 3000);

  /* Test 3: VOLATILE pub + TRANSIENT_LOCAL sub → should MATCH (degraded) ⚠️ */
  mros2::QoSProfile test3_pub_qos;
  test3_pub_qos.reliability = rtps::ReliabilityKind_t::RELIABLE;
  test3_pub_qos.durability = rtps::DurabilityKind_t::VOLATILE;
  test3_pub_qos.history = mros2::HistoryKind::KEEP_LAST;
  test3_pub_qos.depth = 5;

  mros2::QoSProfile test3_sub_qos;
  test3_sub_qos.reliability = rtps::ReliabilityKind_t::RELIABLE;
  test3_sub_qos.durability = rtps::DurabilityKind_t::TRANSIENT_LOCAL;
  test3_sub_qos.history = mros2::HistoryKind::KEEP_LAST;
  test3_sub_qos.depth = 5;

  run_test("Test 3: VOLATILE pub + TRANSIENT_LOCAL sub",
           node, "/test3_pub", "/test3_sub",
           test3_pub_qos, test3_sub_qos, true, 3000);

  /* Test 4: TRANSIENT_LOCAL pub + VOLATILE sub → should MATCH (no cache) ⚠️ */
  mros2::QoSProfile test4_pub_qos;
  test4_pub_qos.reliability = rtps::ReliabilityKind_t::RELIABLE;
  test4_pub_qos.durability = rtps::DurabilityKind_t::TRANSIENT_LOCAL;
  test4_pub_qos.history = mros2::HistoryKind::KEEP_LAST;
  test4_pub_qos.depth = 5;

  mros2::QoSProfile test4_sub_qos;
  test4_sub_qos.reliability = rtps::ReliabilityKind_t::RELIABLE;
  test4_sub_qos.durability = rtps::DurabilityKind_t::VOLATILE;
  test4_sub_qos.history = mros2::HistoryKind::KEEP_LAST;
  test4_sub_qos.depth = 5;

  run_test("Test 4: TRANSIENT_LOCAL pub + VOLATILE sub",
           node, "/test4_pub", "/test4_sub",
           test4_pub_qos, test4_sub_qos, true, 3000);

  /* Final Report */
  MROS2_INFO("\n\n");
  MROS2_INFO("============================================");
  MROS2_INFO("  QoS MISMATCH TEST RESULTS");
  MROS2_INFO("============================================");

  uint32_t passed = 0;
  uint32_t failed = 0;

  for (uint32_t i = 0; i < test_index; i++) {
    MROS2_INFO("%s:", test_results[i].test_name);
    MROS2_INFO("  Expected: %s", test_results[i].expected_match ? "MATCH" : "REJECT");
    MROS2_INFO("  Actual: %s", test_results[i].actual_matched ? "MATCHED" : "REJECTED");
    MROS2_INFO("  TX: %u, RX: %u",
               test_results[i].messages_sent,
               test_results[i].messages_received);
    MROS2_INFO("  Result: %s", test_results[i].passed ? "PASS ✅" : "FAIL ❌");
    MROS2_INFO("");

    if (test_results[i].passed) {
      passed++;
    } else {
      failed++;
    }
  }

  MROS2_INFO("============================================");
  MROS2_INFO("  SUMMARY: %u/%u tests passed", passed, test_index);
  MROS2_INFO("============================================");
  MROS2_INFO("  Memory: %u bytes free", esp_get_free_heap_size());
  MROS2_INFO("============================================");

  if (failed == 0) {
    MROS2_INFO("\n✅ ALL QoS MISMATCH TESTS PASSED!");
    MROS2_INFO("   DDS compatibility rules correctly implemented.");
  } else {
    MROS2_ERROR("\n❌ %u QoS MISMATCH TESTS FAILED!", failed);
    MROS2_ERROR("   DDS compatibility rules may not be correct.");
  }

  MROS2_INFO("\nEntering idle spin.");
  while (1) {
    mros2::spin();
  }
}
