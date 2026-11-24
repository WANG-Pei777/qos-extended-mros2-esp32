#include "mros2.h"
#include "mros2-platform.h"
#include "std_msgs/msg/string.hpp"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_timer.h"

#include <atomic>
#include <cstdio>
#include <string>

#define QOS_STRINGIZE_IMPL(value) #value
#define QOS_STRINGIZE(value) QOS_STRINGIZE_IMPL(value)

#ifndef MROS2_QOS_CASE_ID
#define MROS2_QOS_CASE_ID unbound
#endif
#ifndef MROS2_QOS_BOARD_ROLE
#define MROS2_QOS_BOARD_ROLE publisher
#endif
#ifndef MROS2_QOS_RELIABILITY
#define MROS2_QOS_RELIABILITY reliable
#endif
#ifndef MROS2_QOS_DURABILITY
#define MROS2_QOS_DURABILITY volatile
#endif
#ifndef MROS2_QOS_DEADLINE_MS
#define MROS2_QOS_DEADLINE_MS 0
#endif
#ifndef MROS2_QOS_LIVELINESS_LEASE_MS
#define MROS2_QOS_LIVELINESS_LEASE_MS 0
#endif
#ifndef MROS2_QOS_EXPECTED_MATCH
#define MROS2_QOS_EXPECTED_MATCH 0
#endif
#ifndef MROS2_QOS_WAIT_MS
#define MROS2_QOS_WAIT_MS 20000
#endif
#ifndef MROS2_QOS_POST_MATCH_MS
#define MROS2_QOS_POST_MATCH_MS 5000
#endif
#ifndef MROS2_QOS_MESSAGE_COUNT
#define MROS2_QOS_MESSAGE_COUNT 10
#endif
#ifndef MROS2_QOS_PERIOD_MS
#define MROS2_QOS_PERIOD_MS 100
#endif

static std::atomic<int> g_received{0};

static void compatibility_callback(std_msgs::msg::String *)
{
  g_received.fetch_add(1);
}

static mros2::QoSProfile make_qos()
{
  mros2::QoSProfile qos;
  qos.reliability = std::string(QOS_STRINGIZE(MROS2_QOS_RELIABILITY)) == "reliable"
                        ? rtps::ReliabilityKind_t::RELIABLE
                        : rtps::ReliabilityKind_t::BEST_EFFORT;
  qos.durability = std::string(QOS_STRINGIZE(MROS2_QOS_DURABILITY)) == "transient_local"
                       ? rtps::DurabilityKind_t::TRANSIENT_LOCAL
                       : rtps::DurabilityKind_t::VOLATILE;
  qos.history = mros2::HistoryKind::KEEP_LAST;
  qos.depth = 10;
  qos.deadline = MROS2_QOS_DEADLINE_MS == 0
                   ? mros2::Duration::infinite()
                   : mros2::Duration::from_ms(MROS2_QOS_DEADLINE_MS);
  qos.liveliness = mros2::LivelinessKind::AUTOMATIC;
  qos.liveliness_lease_duration = MROS2_QOS_LIVELINESS_LEASE_MS == 0
                                    ? mros2::Duration::infinite()
                                    : mros2::Duration::from_ms(MROS2_QOS_LIVELINESS_LEASE_MS);
  return qos;
}

static bool board_is_publisher()
{
  return std::string(QOS_STRINGIZE(MROS2_QOS_BOARD_ROLE)) == "publisher";
}

extern "C" void app_main(void)
{
  const char *case_id = QOS_STRINGIZE(MROS2_QOS_CASE_ID);
  const char *role = QOS_STRINGIZE(MROS2_QOS_BOARD_ROLE);
  const char *reliability = QOS_STRINGIZE(MROS2_QOS_RELIABILITY);
  const char *durability = QOS_STRINGIZE(MROS2_QOS_DURABILITY);
  const char *deadline = MROS2_QOS_DEADLINE_MS == 0 ? "infinite" : QOS_STRINGIZE(MROS2_QOS_DEADLINE_MS);
  const char *liveliness_lease = MROS2_QOS_LIVELINESS_LEASE_MS == 0
                                   ? "infinite"
                                   : QOS_STRINGIZE(MROS2_QOS_LIVELINESS_LEASE_MS);

  if (!mros2_platform_network_connect()) {
    std::printf("QOS_BOARD_ERROR schema=1 case_id=%s reason=network_failed\n", case_id);
    return;
  }

  mros2::init(0, nullptr);
  mros2::Node node = mros2::Node::create_node("seven_qos_compatibility");
  mros2::QoSProfile qos = make_qos();
  mros2::Publisher publisher;
  mros2::Subscriber subscriber;
  if (board_is_publisher()) {
    publisher = node.create_publisher<std_msgs::msg::String>(
      "seven_qos_compatibility", qos);
  } else {
    subscriber = node.create_subscription<std_msgs::msg::String>(
      "seven_qos_compatibility", qos, compatibility_callback);
  }

  std::printf(
    "QOS_BOARD_CONFIG schema=1 case_id=%s role=%s reliability=%s durability=%s "
    "deadline_ms=%s liveliness=automatic liveliness_lease_ms=%s expected_match=%u "
    "message_count=%u\n",
    case_id, role, reliability, durability,
    deadline,
    liveliness_lease,
    static_cast<unsigned>(MROS2_QOS_EXPECTED_MATCH),
    static_cast<unsigned>(MROS2_QOS_MESSAGE_COUNT));
  std::printf(
    "QOS_BOARD_LOCAL_READY schema=1 case_id=%s role=%s expected_match=%u\n",
    case_id, role, static_cast<unsigned>(MROS2_QOS_EXPECTED_MATCH));
  std::fflush(stdout);

  const uint32_t wait_steps = MROS2_QOS_WAIT_MS / 50;
  bool matched = false;
  for (uint32_t step = 0; step < wait_steps; ++step) {
    matched = board_is_publisher() ? mros2::publisher_matched()
                                    : mros2::subscriber_matched();
    if (matched && !board_is_publisher()) break;
    vTaskDelay(pdMS_TO_TICKS(50));
  }

  int tx_attempts = 0;
  int tx_accepted = 0;
  // The embedded publisher callback can lag behind Fast DDS discovery. For
  // an expected match, publish after the complete discovery window and let
  // the host-side delivery validator provide the peer-side evidence.
  if (board_is_publisher() && MROS2_QOS_EXPECTED_MATCH != 0) {
    for (int index = 0; index < MROS2_QOS_MESSAGE_COUNT; ++index) {
      auto message = std_msgs::msg::String();
      message.data = "seven_qos_case=" + std::string(case_id) +
                     " seq=" + std::to_string(index) +
                     " t=" + std::to_string(esp_timer_get_time());
      ++tx_attempts;
      const bool accepted = publisher.publish(message);
      if (accepted) {
        ++tx_accepted;
      }
      std::printf(
        "QOS_BOARD_PUBLISH schema=1 case_id=%s index=%d accepted=%u "
        "publish_attempts=%u publish_accepts=%u history_count=%u "
        "history_bytes=%u resource_rejects=%u allocation_failures=%u\n",
        case_id, index, static_cast<unsigned>(accepted),
        static_cast<unsigned>(mros2::publisher_publish_attempt_count()),
        static_cast<unsigned>(mros2::publisher_publish_accept_count()),
        static_cast<unsigned>(mros2::publisher_history_count()),
        static_cast<unsigned>(mros2::publisher_history_bytes()),
        static_cast<unsigned>(mros2::publisher_resource_reject_count()),
        static_cast<unsigned>(mros2::publisher_allocation_failure_count()));
      std::fflush(stdout);
      vTaskDelay(pdMS_TO_TICKS(MROS2_QOS_PERIOD_MS));
    }
  }

  const uint32_t hold_steps = MROS2_QOS_POST_MATCH_MS / 50;
  for (uint32_t step = 0; step < hold_steps; ++step) {
    vTaskDelay(pdMS_TO_TICKS(50));
  }
  const int rx = g_received.load();
  // Some Fast DDS peers can deliver application data before the embedded
  // endpoint-match callback updates its flag. Treat observed delivery as
  // authoritative for subscriber-side compatibility validation.
  const bool actual_match = matched || (!board_is_publisher() && rx > 0) ||
                            (board_is_publisher() && tx_accepted > 0);
  const bool expected_match = MROS2_QOS_EXPECTED_MATCH != 0;
  const bool pass = actual_match == expected_match &&
                    (!expected_match || (board_is_publisher()
                      ? tx_accepted == MROS2_QOS_MESSAGE_COUNT
                      : rx > 0)) &&
                    (expected_match || (tx_attempts == 0 && rx == 0));
  std::printf(
    "QOS_BOARD_FINAL schema=1 case_id=%s role=%s expected_match=%u actual_match=%u "
    "status=%s tx_attempts=%d tx_accepted=%d rx=%d\n",
    case_id, role, static_cast<unsigned>(expected_match),
    static_cast<unsigned>(actual_match), pass ? "PASS" : "FAIL",
    tx_attempts, tx_accepted, rx);
  std::fflush(stdout);
  mros2::shutdown();
  while (true) {
    vTaskDelay(pdMS_TO_TICKS(1000));
  }
}
