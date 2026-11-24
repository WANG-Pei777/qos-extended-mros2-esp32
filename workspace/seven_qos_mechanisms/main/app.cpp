/** One-case-per-boot ESP32 harness for deterministic Seven-QoS mechanisms. */

#include <array>
#include <cstdint>
#include <cstdio>
#include <string>

#include "cmsis_os.h"
#include "esp_heap_caps.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "lwip/pbuf.h"
#include "mros2-platform.h"
#include "mros2.h"
#include "nvs.h"
#include "nvs_flash.h"
#include "rtps/storages/CacheChange.h"
#include "rtps/utils/sysFunctions.h"
#include "std_msgs/msg/string.hpp"

#ifndef MROS2_MECHANISM_CASE_ID
#define MROS2_MECHANISM_CASE_ID "UNBOUND"
#endif
#ifndef MROS2_MECHANISM_KIND
#define MROS2_MECHANISM_KIND "unbound"
#endif
#ifndef MROS2_MECHANISM_KIND_CODE
#define MROS2_MECHANISM_KIND_CODE 0
#endif
#ifndef MROS2_MECHANISM_TOPIC
#define MROS2_MECHANISM_TOPIC "seven_qos_mechanism"
#endif
#ifndef MROS2_MECHANISM_PAYLOAD_BYTES
#define MROS2_MECHANISM_PAYLOAD_BYTES 64
#endif
#ifndef MROS2_MECHANISM_SAMPLE_LIMIT
#define MROS2_MECHANISM_SAMPLE_LIMIT 5
#endif
#ifndef MROS2_MECHANISM_TIMEOUT_MS
#define MROS2_MECHANISM_TIMEOUT_MS 20000
#endif
#ifndef MROS2_MECHANISM_HISTORY_CAPACITY
#define MROS2_MECHANISM_HISTORY_CAPACITY 100
#endif

namespace {

uint32_t pressurePbufs = 0;
uint64_t holdStartUs = 0;
uint64_t holdEndUs = 0;
uint32_t heapAfterPressure = 0;
volatile uint32_t applicationRx = 0;
volatile uint32_t applicationRxBytes = 0;
volatile uint32_t applicationRxHash = 0;
volatile uint32_t firstRxHash = 0;
volatile uint32_t secondRxHash = 0;
volatile uint64_t firstRxUs = 0;
volatile uint64_t secondRxUs = 0;
volatile uint32_t firstRxClockMs = 0;
volatile uint32_t secondRxClockMs = 0;
volatile uint32_t deadlineCallbacks = 0;
volatile uint64_t firstDeadlineCallbackUs = 0;
volatile uint64_t secondDeadlineCallbackUs = 0;
volatile uint32_t firstDeadlineCallbackClockMs = 0;
volatile uint32_t livelinessLostCallbacks = 0;
volatile uint32_t livelinessRecoveredCallbacks = 0;
volatile bool terminalFinalizing = false;
uint32_t mechanismBootEpoch = 0;

void delay_ms(uint32_t milliseconds) { osDelay(milliseconds); }

bool advance_persistent_boot_epoch() {
  esp_err_t status = nvs_flash_init();
  if (status == ESP_ERR_NVS_NO_FREE_PAGES ||
      status == ESP_ERR_NVS_NEW_VERSION_FOUND) {
    if (nvs_flash_erase() != ESP_OK) return false;
    status = nvs_flash_init();
  }
  if (status != ESP_OK) return false;

  nvs_handle_t handle;
  if (nvs_open("qos_mech", NVS_READWRITE, &handle) != ESP_OK) return false;
  uint32_t previous = 0;
  status = nvs_get_u32(handle, "boot_epoch", &previous);
  if (status != ESP_OK && status != ESP_ERR_NVS_NOT_FOUND) {
    nvs_close(handle);
    return false;
  }
  mechanismBootEpoch = previous == UINT32_MAX ? 1U : previous + 1U;
  const bool stored = nvs_set_u32(handle, "boot_epoch", mechanismBootEpoch) == ESP_OK &&
      nvs_commit(handle) == ESP_OK;
  nvs_close(handle);
  return stored;
}

uint32_t fnv1a(const std::string &value) {
  uint32_t hash = 2166136261U;
  for (const unsigned char byte : value) {
    hash ^= byte;
    hash *= 16777619U;
  }
  return hash;
}

void subscription_callback(std_msgs::msg::String *message) {
  if (terminalFinalizing) return;
  const uint64_t nowUs = static_cast<uint64_t>(esp_timer_get_time());
  const uint32_t ordinal = applicationRx + 1U;
  if (ordinal == 1) {
    firstRxUs = nowUs;
    firstRxClockMs = rtps::getCurrentTimeMs();
  } else if (ordinal == 2) {
    secondRxUs = nowUs;
    secondRxClockMs = rtps::getCurrentTimeMs();
  }
  applicationRxBytes += static_cast<uint32_t>(message->data.size());
  applicationRxHash = fnv1a(message->data);
  if (ordinal == 1) {
    firstRxHash = applicationRxHash;
  } else if (ordinal == 2) {
    secondRxHash = applicationRxHash;
  }
  applicationRx = ordinal;
  const unsigned first = message->data.empty()
      ? 0U
      : static_cast<unsigned>(static_cast<unsigned char>(message->data.front()));
  const unsigned last = message->data.empty()
      ? 0U
      : static_cast<unsigned>(static_cast<unsigned char>(message->data.back()));
  std::printf(
      "MECH_BOARD_RX schema=1 case_id=%s ordinal=%u bytes=%u first=%u "
      "last=%u hash=%u board_time_us=%llu\n",
      MROS2_MECHANISM_CASE_ID, static_cast<unsigned>(ordinal),
      static_cast<unsigned>(message->data.size()), first, last,
      static_cast<unsigned>(applicationRxHash),
      static_cast<unsigned long long>(nowUs));
}

void deadline_callback(void *) {
  if (terminalFinalizing) return;
  const uint64_t nowUs = static_cast<uint64_t>(esp_timer_get_time());
  const uint32_t ordinal = deadlineCallbacks + 1U;
  if (ordinal == 1) {
    firstDeadlineCallbackUs = nowUs;
    firstDeadlineCallbackClockMs = rtps::getCurrentTimeMs();
  } else if (ordinal == 2) {
    secondDeadlineCallbackUs = nowUs;
  }
  deadlineCallbacks = ordinal;
  std::printf(
      "MECH_BOARD_EVENT schema=1 case_id=%s event=deadline_missed "
      "ordinal=%u total=%u board_time_us=%llu\n",
      MROS2_MECHANISM_CASE_ID, static_cast<unsigned>(ordinal),
      static_cast<unsigned>(mros2::subscriber_deadline_missed_count()),
      static_cast<unsigned long long>(nowUs));
}

void liveliness_lost_callback(void *) {
  if (terminalFinalizing) return;
  ++livelinessLostCallbacks;
  std::printf(
      "MECH_BOARD_EVENT schema=1 case_id=%s event=liveliness_lost "
      "ordinal=%u board_time_us=%llu\n",
      MROS2_MECHANISM_CASE_ID,
      static_cast<unsigned>(livelinessLostCallbacks),
      static_cast<unsigned long long>(esp_timer_get_time()));
}

void liveliness_recovered_callback(void *) {
  if (terminalFinalizing) return;
  ++livelinessRecoveredCallbacks;
  std::printf(
      "MECH_BOARD_EVENT schema=1 case_id=%s event=liveliness_recovered "
      "ordinal=%u board_time_us=%llu\n",
      MROS2_MECHANISM_CASE_ID,
      static_cast<unsigned>(livelinessRecoveredCallbacks),
      static_cast<unsigned long long>(esp_timer_get_time()));
}

std_msgs::msg::String make_message(uint32_t index) {
  std_msgs::msg::String message;
  if (MROS2_MECHANISM_KIND_CODE == 23) {
    index += mechanismBootEpoch * 5U;
  }
  message.data.assign(MROS2_MECHANISM_PAYLOAD_BYTES,
                      static_cast<char>('A' + index % 26));
  return message;
}

uint32_t serialized_bytes() {
  auto message = make_message(0);
  std::array<uint8_t, MROS2_MECHANISM_PAYLOAD_BYTES + 32U> scratch{};
  message.copyToBuf(&scratch[4]);
  message.memAlign(&scratch[4]);
  return static_cast<uint32_t>(message.getTotalSize()) + 4U;
}

bool is_reader_case() {
  return (MROS2_MECHANISM_KIND_CODE >= 12 &&
          MROS2_MECHANISM_KIND_CODE <= 14) ||
         MROS2_MECHANISM_KIND_CODE == 17 ||
         MROS2_MECHANISM_KIND_CODE == 18 ||
         MROS2_MECHANISM_KIND_CODE == 57 ||
         (MROS2_MECHANISM_KIND_CODE >= 30 &&
          MROS2_MECHANISM_KIND_CODE <= 34) ||
         (MROS2_MECHANISM_KIND_CODE >= 50 &&
          MROS2_MECHANISM_KIND_CODE <= 54);
}

mros2::QoSProfile make_qos(uint32_t sampleBytes) {
  mros2::QoSProfile qos;
  qos.reliability = rtps::ReliabilityKind_t::RELIABLE;
  qos.durability = rtps::DurabilityKind_t::VOLATILE;
  qos.history = mros2::HistoryKind::KEEP_LAST;
  qos.depth = 10;
  qos.deadline = mros2::Duration::infinite();
  qos.lifespan = mros2::Duration::infinite();
  qos.liveliness = mros2::LivelinessKind::AUTOMATIC;
  qos.liveliness_lease_duration = mros2::Duration::infinite();
  qos.max_samples = 0;
  qos.max_bytes = 0;

  if (MROS2_MECHANISM_KIND_CODE >= 1 && MROS2_MECHANISM_KIND_CODE <= 6) {
    qos.history = mros2::HistoryKind::KEEP_ALL;
    qos.depth = 1;
  }
  if (MROS2_MECHANISM_KIND_CODE == 7) {
    qos.reliability = rtps::ReliabilityKind_t::BEST_EFFORT;
    qos.history = mros2::HistoryKind::KEEP_LAST;
    qos.depth = 2;
  } else if (MROS2_MECHANISM_KIND_CODE == 8) {
    qos.reliability = rtps::ReliabilityKind_t::BEST_EFFORT;
    qos.history = mros2::HistoryKind::KEEP_ALL;
    qos.depth = 1;
  } else if (MROS2_MECHANISM_KIND_CODE == 9) {
    // This case verifies atomic KeepLast replacement under a transport
    // allocation failure.  Retain the seed independently of whether a
    // Volatile writer currently has a matched Reader.
    qos.durability = rtps::DurabilityKind_t::TRANSIENT_LOCAL;
    qos.history = mros2::HistoryKind::KEEP_LAST;
    qos.depth = 1;
  }
  if (MROS2_MECHANISM_KIND_CODE == 18) {
    qos.reliability = rtps::ReliabilityKind_t::BEST_EFFORT;
  }
  if (MROS2_MECHANISM_KIND_CODE == 1 || MROS2_MECHANISM_KIND_CODE == 2 ||
      MROS2_MECHANISM_KIND_CODE == 5 || MROS2_MECHANISM_KIND_CODE == 6) {
    qos.max_samples = MROS2_MECHANISM_SAMPLE_LIMIT;
  } else if (MROS2_MECHANISM_KIND_CODE == 3) {
    qos.max_bytes = sampleBytes * 2U;
  } else if (MROS2_MECHANISM_KIND_CODE == 10) {
    qos.durability = rtps::DurabilityKind_t::TRANSIENT_LOCAL;
    qos.depth = 3;
  } else if (MROS2_MECHANISM_KIND_CODE == 11 ||
             MROS2_MECHANISM_KIND_CODE == 15) {
    qos.history = mros2::HistoryKind::KEEP_ALL;
    qos.depth = 1;
  } else if (MROS2_MECHANISM_KIND_CODE == 16) {
    qos.durability = rtps::DurabilityKind_t::TRANSIENT_LOCAL;
    qos.depth = 2;
  } else if (MROS2_MECHANISM_KIND_CODE == 17) {
    qos.durability = rtps::DurabilityKind_t::TRANSIENT_LOCAL;
    qos.depth = 3;
  } else if (MROS2_MECHANISM_KIND_CODE == 21 ||
             MROS2_MECHANISM_KIND_CODE == 23 ||
             MROS2_MECHANISM_KIND_CODE == 24) {
    qos.durability = rtps::DurabilityKind_t::TRANSIENT_LOCAL;
    qos.depth = 3;
  } else if (MROS2_MECHANISM_KIND_CODE == 22) {
    qos.durability = rtps::DurabilityKind_t::TRANSIENT_LOCAL;
    qos.depth = 2;
  } else if (MROS2_MECHANISM_KIND_CODE == 25 ||
             MROS2_MECHANISM_KIND_CODE == 29 ||
             MROS2_MECHANISM_KIND_CODE == 35 ||
             MROS2_MECHANISM_KIND_CODE == 36 ||
             MROS2_MECHANISM_KIND_CODE == 37 ||
             MROS2_MECHANISM_KIND_CODE == 38) {
    qos.durability = rtps::DurabilityKind_t::TRANSIENT_LOCAL;
    qos.depth = 1;
    if (MROS2_MECHANISM_KIND_CODE == 37 ||
        MROS2_MECHANISM_KIND_CODE == 38) {
      qos.reliability = rtps::ReliabilityKind_t::BEST_EFFORT;
    }
  } else if (MROS2_MECHANISM_KIND_CODE >= 31 &&
             MROS2_MECHANISM_KIND_CODE <= 34) {
    qos.deadline = mros2::Duration::from_ms(50);
  } else if (MROS2_MECHANISM_KIND_CODE == 41) {
    qos.lifespan = mros2::Duration::from_ms(200);
  } else if (MROS2_MECHANISM_KIND_CODE == 42 ||
             MROS2_MECHANISM_KIND_CODE == 43) {
    qos.lifespan = mros2::Duration::from_ms(100);
    if (MROS2_MECHANISM_KIND_CODE == 43) {
      qos.durability = rtps::DurabilityKind_t::TRANSIENT_LOCAL;
    }
  } else if (MROS2_MECHANISM_KIND_CODE == 44) {
    qos.lifespan = mros2::Duration::from_ms(300);
  } else if (MROS2_MECHANISM_KIND_CODE >= 50 &&
             MROS2_MECHANISM_KIND_CODE <= 53) {
    qos.liveliness_lease_duration = mros2::Duration::from_ms(500);
  }
  return qos;
}

struct Snapshot {
  uint32_t attempts;
  uint32_t accepted;
  uint32_t rejected;
  uint32_t allocationFailures;
  uint32_t historyCount;
  uint32_t historyBytes;
};

Snapshot snapshot() {
  return {
      mros2::publisher_publish_attempt_count(),
      mros2::publisher_publish_accept_count(),
      mros2::publisher_resource_reject_count(),
      mros2::publisher_allocation_failure_count(),
      mros2::publisher_history_count(),
      mros2::publisher_history_bytes(),
  };
}

bool publish_one(mros2::Publisher &publisher, uint32_t index) {
  auto message = make_message(index);
  return publisher.publish(message);
}

void publish_attempts(mros2::Publisher &publisher, uint32_t count) {
  for (uint32_t index = 0; index < count; ++index) {
    const bool accepted = publish_one(publisher, index);
    std::printf(
        "MECH_BOARD_PUBLISH schema=1 case_id=%s index=%u accepted=%d "
        "history_count=%u history_bytes=%u\n",
        MROS2_MECHANISM_CASE_ID, static_cast<unsigned>(index), accepted ? 1 : 0,
        static_cast<unsigned>(mros2::publisher_history_count()),
        static_cast<unsigned>(mros2::publisher_history_bytes()));
    delay_ms(5);
  }
}

bool wait_for_publisher_match(uint32_t timeoutMs) {
  const uint64_t deadlineUs = esp_timer_get_time() +
      static_cast<uint64_t>(timeoutMs) * 1000U;
  while (esp_timer_get_time() < deadlineUs) {
    if (mros2::publisher_matched()) return true;
    delay_ms(5);
  }
  return false;
}

bool wait_for_subscriber_match(uint32_t timeoutMs) {
  const uint64_t deadlineUs = esp_timer_get_time() +
      static_cast<uint64_t>(timeoutMs) * 1000U;
  while (esp_timer_get_time() < deadlineUs) {
    if (mros2::subscriber_matched()) return true;
    delay_ms(5);
  }
  return false;
}

bool wait_for_rx(uint32_t count, uint32_t timeoutMs) {
  const uint64_t deadlineUs = esp_timer_get_time() +
      static_cast<uint64_t>(timeoutMs) * 1000U;
  while (esp_timer_get_time() < deadlineUs) {
    if (applicationRx >= count) return true;
    delay_ms(2);
  }
  return false;
}

bool wait_for_deadline_count(uint32_t count, uint32_t timeoutMs) {
  const uint64_t deadlineUs = esp_timer_get_time() +
      static_cast<uint64_t>(timeoutMs) * 1000U;
  while (esp_timer_get_time() < deadlineUs) {
    if (mros2::subscriber_deadline_missed_count() >= count) return true;
    delay_ms(2);
  }
  return false;
}

bool wait_for_liveliness(uint32_t lost, uint32_t recovered,
                         uint32_t timeoutMs) {
  const uint64_t deadlineUs = esp_timer_get_time() +
      static_cast<uint64_t>(timeoutMs) * 1000U;
  while (esp_timer_get_time() < deadlineUs) {
    if (mros2::subscriber_liveliness_lost_count() >= lost &&
        mros2::subscriber_liveliness_recovered_count() >= recovered) {
      return true;
    }
    delay_ms(5);
  }
  return false;
}

[[noreturn]] void finish(bool passed, uint32_t sampleBytes,
                         uint32_t heapBefore, bool recoveryObserved) {
  terminalFinalizing = true;
  const Snapshot state = snapshot();
  const uint32_t heapAfter = esp_get_free_heap_size();
  const uint32_t minimumHeap = esp_get_minimum_free_heap_size();
  const UBaseType_t stackWatermark = uxTaskGetStackHighWaterMark(nullptr);
  const bool heapIntegrity = heap_caps_check_integrity_all(false);
  const uint64_t deadlineBaselineUs =
      MROS2_MECHANISM_KIND_CODE == 33 ? secondRxUs : firstRxUs;
  const uint32_t deadlineBaselineClockMs =
      MROS2_MECHANISM_KIND_CODE == 33 ? secondRxClockMs : firstRxClockMs;
  const uint64_t deadlineLatencyUs =
      firstDeadlineCallbackUs >= deadlineBaselineUs
          ? firstDeadlineCallbackUs - deadlineBaselineUs
          : 0;
  const uint32_t deadlineLatencyMs =
      firstDeadlineCallbackClockMs == 0 || deadlineBaselineClockMs == 0
          ? 0
          : firstDeadlineCallbackClockMs - deadlineBaselineClockMs;
  passed = passed && heapIntegrity && stackWatermark > 0;
  std::printf(
      "MECH_BOARD_FINAL schema=1 case_id=%s kind=%s sample_bytes=%u "
      "attempts=%u accepted=%u rejected=%u allocation_failures=%u "
      "history_count=%u history_bytes=%u heap_before=%u heap_after=%u "
      "acknack_received=%u acknack_accepted=%u acknack_stale_drops=%u "
      "acknack_unknown_reader_drops=%u acknack_best_effort_drops=%u "
      "acknack_gap_responses=%u acknack_data_responses=%u "
      "acknack_deferred_responses=%u "
      "writer_control_send_failures=%u "
      "minimum_free_heap=%u stack_high_watermark=%u heap_integrity=%d "
      "pressure_pbufs=%u matched=%d recovery_observed=%d "
      "app_rx=%u app_rx_bytes=%u app_rx_hash=%u reader_received=%u "
      "unsupported_payload_drops=%u "
      "first_rx_hash=%u second_rx_hash=%u boot_epoch=%u "
      "out_of_order_drops=%u gap_received=%u control_send_failures=%u "
      "deadline_missed=%u "
      "deadline_callbacks=%u "
      "deadline_latency_us=%llu deadline_latency_ms=%u liveliness_lost=%u "
      "liveliness_recovered=%u liveliness_lost_callbacks=%u "
      "liveliness_recovered_callbacks=%u lifespan_drops=%u "
      "hold_start_us=%llu hold_end_us=%llu heap_after_pressure=%u status=%s\n",
      MROS2_MECHANISM_CASE_ID, MROS2_MECHANISM_KIND,
      static_cast<unsigned>(sampleBytes), static_cast<unsigned>(state.attempts),
      static_cast<unsigned>(state.accepted), static_cast<unsigned>(state.rejected),
      static_cast<unsigned>(state.allocationFailures),
      static_cast<unsigned>(state.historyCount),
      static_cast<unsigned>(state.historyBytes), static_cast<unsigned>(heapBefore),
      static_cast<unsigned>(heapAfter),
      static_cast<unsigned>(mros2::publisher_acknack_receive_count()),
      static_cast<unsigned>(mros2::publisher_acknack_accept_count()),
      static_cast<unsigned>(mros2::publisher_acknack_stale_drop_count()),
      static_cast<unsigned>(mros2::publisher_acknack_unknown_reader_drop_count()),
      static_cast<unsigned>(mros2::publisher_acknack_best_effort_drop_count()),
      static_cast<unsigned>(mros2::publisher_acknack_gap_response_count()),
      static_cast<unsigned>(mros2::publisher_acknack_data_response_count()),
      static_cast<unsigned>(mros2::publisher_acknack_deferred_response_count()),
      static_cast<unsigned>(mros2::publisher_control_send_failure_count()),
      static_cast<unsigned>(minimumHeap),
      static_cast<unsigned>(stackWatermark), heapIntegrity ? 1 : 0,
      static_cast<unsigned>(pressurePbufs),
      (is_reader_case() ? mros2::subscriber_matched()
                        : mros2::publisher_matched()) ? 1 : 0,
      recoveryObserved ? 1 : 0, static_cast<unsigned>(applicationRx),
      static_cast<unsigned>(applicationRxBytes),
      static_cast<unsigned>(applicationRxHash),
      static_cast<unsigned>(mros2::subscriber_received_count()),
      static_cast<unsigned>(
          mros2::subscriber_unsupported_payload_drop_count()),
      static_cast<unsigned>(firstRxHash),
      static_cast<unsigned>(secondRxHash),
      static_cast<unsigned>(mechanismBootEpoch),
      static_cast<unsigned>(mros2::subscriber_out_of_order_drop_count()),
      static_cast<unsigned>(mros2::subscriber_gap_received_count()),
      static_cast<unsigned>(mros2::subscriber_control_send_failure_count()),
      static_cast<unsigned>(mros2::subscriber_deadline_missed_count()),
      static_cast<unsigned>(deadlineCallbacks),
      static_cast<unsigned long long>(deadlineLatencyUs),
      static_cast<unsigned>(deadlineLatencyMs),
      static_cast<unsigned>(mros2::subscriber_liveliness_lost_count()),
      static_cast<unsigned>(mros2::subscriber_liveliness_recovered_count()),
      static_cast<unsigned>(livelinessLostCallbacks),
      static_cast<unsigned>(livelinessRecoveredCallbacks),
      static_cast<unsigned>(mros2::publisher_lifespan_drop_count()),
      static_cast<unsigned long long>(holdStartUs),
      static_cast<unsigned long long>(holdEndUs),
      static_cast<unsigned>(heapAfterPressure), passed ? "PASS" : "FAIL");
  while (true) delay_ms(1000);
}

void run_resource_case(mros2::Publisher &publisher, uint32_t sampleBytes,
                       uint32_t heapBefore) {
  const bool admissionOnlyCase =
      (MROS2_MECHANISM_KIND_CODE >= 1 &&
       MROS2_MECHANISM_KIND_CODE <= 3) ||
      (MROS2_MECHANISM_KIND_CODE >= 6 &&
       MROS2_MECHANISM_KIND_CODE <= 8);
  if (admissionOnlyCase) {
    // These cases measure History admission and resource limits, not delivery.
    // Holding transmission makes their snapshots independent of the worker
    // schedule and the correct no-Reader Volatile release policy.
    mros2::publisher_set_transmission_held(true);
  }
  if (MROS2_MECHANISM_KIND_CODE == 1) {
    publish_attempts(publisher, MROS2_MECHANISM_SAMPLE_LIMIT);
    const Snapshot state = snapshot();
    finish(state.attempts == MROS2_MECHANISM_SAMPLE_LIMIT &&
               state.accepted == MROS2_MECHANISM_SAMPLE_LIMIT &&
               state.rejected == 0 && state.allocationFailures == 0 &&
               state.historyCount == MROS2_MECHANISM_SAMPLE_LIMIT,
           sampleBytes, heapBefore, false);
  }
  if (MROS2_MECHANISM_KIND_CODE == 2) {
    publish_attempts(publisher, MROS2_MECHANISM_SAMPLE_LIMIT + 1U);
    const Snapshot state = snapshot();
    finish(state.attempts == MROS2_MECHANISM_SAMPLE_LIMIT + 1U &&
               state.accepted == MROS2_MECHANISM_SAMPLE_LIMIT &&
               state.rejected == 1 && state.allocationFailures == 0 &&
               state.historyCount == MROS2_MECHANISM_SAMPLE_LIMIT,
           sampleBytes, heapBefore, false);
  }
  if (MROS2_MECHANISM_KIND_CODE == 3) {
    publish_attempts(publisher, 3);
    const Snapshot state = snapshot();
    finish(state.attempts == 3 && state.accepted == 2 && state.rejected == 1 &&
               state.allocationFailures == 0 &&
               state.historyBytes == sampleBytes * 2U,
           sampleBytes, heapBefore, false);
  }
  if (MROS2_MECHANISM_KIND_CODE == 4) {
    std::array<struct pbuf *, 256> heldPbufs{};
    while (pressurePbufs < heldPbufs.size()) {
      struct pbuf *held =
          pbuf_alloc(PBUF_TRANSPORT, static_cast<u16_t>(sampleBytes), PBUF_POOL);
      if (held == nullptr) break;
      heldPbufs[pressurePbufs++] = held;
    }
    std::printf(
        "MECH_BOARD_PHASE schema=1 case_id=%s phase=pbuf_pool_exhausted "
        "pressure_pbufs=%u free_heap=%u\n",
        MROS2_MECHANISM_CASE_ID, static_cast<unsigned>(pressurePbufs),
        static_cast<unsigned>(esp_get_free_heap_size()));
    const bool accepted = publish_one(publisher, 0);
    for (uint32_t index = 0; index < pressurePbufs; ++index) {
      pbuf_free(heldPbufs[index]);
    }
    delay_ms(20);
    const Snapshot state = snapshot();
    finish(!accepted && pressurePbufs > 0 && state.attempts == 1 &&
               state.accepted == 0 && state.rejected == 0 &&
               state.allocationFailures == 1 && state.historyCount == 0,
           sampleBytes, heapBefore, false);
  }
  if (MROS2_MECHANISM_KIND_CODE == 5) {
    const bool matched = wait_for_publisher_match(MROS2_MECHANISM_TIMEOUT_MS);
    if (!matched) finish(false, sampleBytes, heapBefore, false);
    mros2::publisher_set_transmission_held(true);
    publish_attempts(publisher, MROS2_MECHANISM_SAMPLE_LIMIT + 1U);
    mros2::publisher_set_transmission_held(false);
    std::printf(
        "MECH_BOARD_PHASE schema=1 case_id=%s phase=awaiting_reader_ack\n",
        MROS2_MECHANISM_CASE_ID);
    const uint64_t deadlineUs = esp_timer_get_time() +
        static_cast<uint64_t>(MROS2_MECHANISM_TIMEOUT_MS) * 1000U;
    bool recovered = false;
    while (esp_timer_get_time() < deadlineUs) {
      if (mros2::publisher_matched() && mros2::publisher_history_count() == 0) {
        recovered = true;
        break;
      }
      delay_ms(10);
    }
    const bool resumed = recovered && publish_one(publisher, 99);
    const Snapshot state = snapshot();
    finish(recovered && resumed && state.attempts ==
               MROS2_MECHANISM_SAMPLE_LIMIT + 2U &&
               state.accepted == MROS2_MECHANISM_SAMPLE_LIMIT + 1U &&
               state.rejected == 1 && state.allocationFailures == 0,
           sampleBytes, heapBefore, recovered);
  }
  if (MROS2_MECHANISM_KIND_CODE == 6) {
    publish_attempts(publisher, MROS2_MECHANISM_SAMPLE_LIMIT + 20U);
    const Snapshot state = snapshot();
    finish(state.attempts == MROS2_MECHANISM_SAMPLE_LIMIT + 20U &&
               state.accepted == MROS2_MECHANISM_SAMPLE_LIMIT &&
               state.rejected == 20 && state.allocationFailures == 0 &&
               state.historyCount == MROS2_MECHANISM_SAMPLE_LIMIT,
           sampleBytes, heapBefore, false);
  }
  if (MROS2_MECHANISM_KIND_CODE == 7) {
    publish_attempts(publisher, 3);
    const Snapshot state = snapshot();
    finish(state.attempts == 3 && state.accepted == 3 &&
               state.rejected == 0 && state.allocationFailures == 0 &&
               state.historyCount == 2,
           sampleBytes, heapBefore, false);
  }
  if (MROS2_MECHANISM_KIND_CODE == 8) {
    publish_attempts(publisher, MROS2_MECHANISM_HISTORY_CAPACITY + 1U);
    const Snapshot state = snapshot();
    finish(state.attempts == MROS2_MECHANISM_HISTORY_CAPACITY + 1U &&
               state.accepted == MROS2_MECHANISM_HISTORY_CAPACITY &&
               state.rejected == 1 && state.allocationFailures == 0 &&
               state.historyCount == MROS2_MECHANISM_HISTORY_CAPACITY,
           sampleBytes, heapBefore, false);
  }
  if (MROS2_MECHANISM_KIND_CODE == 9) {
    const bool seeded = publish_one(publisher, 0);
    std::array<struct pbuf *, 256> heldPbufs{};
    while (pressurePbufs < heldPbufs.size()) {
      struct pbuf *held =
          pbuf_alloc(PBUF_TRANSPORT, static_cast<u16_t>(sampleBytes), PBUF_POOL);
      if (held == nullptr) break;
      heldPbufs[pressurePbufs++] = held;
    }
    const bool replacementAccepted = publish_one(publisher, 1);
    for (uint32_t index = 0; index < pressurePbufs; ++index) {
      pbuf_free(heldPbufs[index]);
    }
    delay_ms(20);
    const Snapshot state = snapshot();
    finish(seeded && !replacementAccepted && pressurePbufs > 0 &&
               state.attempts == 2 && state.accepted == 1 &&
               state.rejected == 0 && state.allocationFailures == 1 &&
               state.historyCount == 1 && state.historyBytes == sampleBytes,
           sampleBytes, heapBefore, false);
  }
}

void run_history_or_durability_writer_case(mros2::Publisher &publisher,
                                            uint32_t sampleBytes,
                                            uint32_t heapBefore) {
  if (MROS2_MECHANISM_KIND_CODE == 10) {
    publish_attempts(publisher, 5);
    std::printf("MECH_BOARD_PHASE schema=1 case_id=%s phase=history_seeded\n",
                MROS2_MECHANISM_CASE_ID);
    const bool matched = wait_for_publisher_match(MROS2_MECHANISM_TIMEOUT_MS);
    delay_ms(1000);
    const Snapshot state = snapshot();
    finish(matched && state.attempts == 5 && state.accepted == 5 &&
               state.rejected == 0 && state.historyCount == 3,
           sampleBytes, heapBefore, false);
  }
  if (MROS2_MECHANISM_KIND_CODE == 11) {
    publish_attempts(publisher, MROS2_MECHANISM_HISTORY_CAPACITY + 1U);
    const Snapshot state = snapshot();
    finish(state.attempts == MROS2_MECHANISM_HISTORY_CAPACITY + 1U &&
               state.accepted == MROS2_MECHANISM_HISTORY_CAPACITY &&
               state.rejected == 1 &&
               state.historyCount == MROS2_MECHANISM_HISTORY_CAPACITY,
           sampleBytes, heapBefore, false);
  }
  if (MROS2_MECHANISM_KIND_CODE == 15) {
    const bool matched = wait_for_publisher_match(MROS2_MECHANISM_TIMEOUT_MS);
    if (!matched) finish(false, sampleBytes, heapBefore, false);
    mros2::publisher_set_transmission_held(true);
    publish_attempts(publisher, 5);
    heapAfterPressure = esp_get_free_heap_size();
    std::printf(
        "MECH_BOARD_PHASE schema=1 case_id=%s phase=awaiting_history_release "
        "heap_after_pressure=%u\n",
        MROS2_MECHANISM_CASE_ID, static_cast<unsigned>(heapAfterPressure));
    mros2::publisher_set_transmission_held(false);
    const uint64_t deadlineUs = esp_timer_get_time() +
        static_cast<uint64_t>(MROS2_MECHANISM_TIMEOUT_MS) * 1000U;
    while (esp_timer_get_time() < deadlineUs &&
           (!mros2::publisher_matched() ||
            mros2::publisher_history_count() != 0)) {
      delay_ms(10);
    }
    const uint32_t recoveredHeap = esp_get_free_heap_size();
    finish(mros2::publisher_matched() &&
               mros2::publisher_history_count() == 0 &&
               recoveredHeap > heapAfterPressure,
           sampleBytes, heapBefore, true);
  }
  if (MROS2_MECHANISM_KIND_CODE == 16) {
    const bool matched = wait_for_publisher_match(MROS2_MECHANISM_TIMEOUT_MS);
    if (!matched) finish(false, sampleBytes, heapBefore, false);
    publish_attempts(publisher, 3);
    std::printf(
        "MECH_BOARD_PHASE schema=1 case_id=%s "
        "phase=awaiting_directed_acknack history_count=%u\n",
        MROS2_MECHANISM_CASE_ID,
        static_cast<unsigned>(mros2::publisher_history_count()));
    delay_ms(15000);
    const Snapshot state = snapshot();
    finish(state.attempts == 3 && state.accepted == 3 &&
               state.rejected == 0 && state.allocationFailures == 0 &&
               state.historyCount == 2 && mros2::publisher_matched(),
           sampleBytes, heapBefore, false);
  }
  if (MROS2_MECHANISM_KIND_CODE == 18) {
    const bool matched = wait_for_publisher_match(MROS2_MECHANISM_TIMEOUT_MS);
    if (!matched) finish(false, sampleBytes, heapBefore, false);
    const bool accepted = publish_one(publisher, 0);
    std::printf(
        "MECH_BOARD_PHASE schema=1 case_id=%s "
        "phase=awaiting_empty_history history_count=%u\n",
        MROS2_MECHANISM_CASE_ID,
        static_cast<unsigned>(mros2::publisher_history_count()));
    const uint64_t deadlineUs = esp_timer_get_time() +
        static_cast<uint64_t>(MROS2_MECHANISM_TIMEOUT_MS) * 1000U;
    while (esp_timer_get_time() < deadlineUs &&
           mros2::publisher_history_count() != 0) {
      delay_ms(5);
    }
    const bool released = mros2::publisher_history_count() == 0;
    std::printf(
        "MECH_BOARD_PHASE schema=1 case_id=%s "
        "phase=empty_history_released history_count=%u\n",
        MROS2_MECHANISM_CASE_ID,
        static_cast<unsigned>(mros2::publisher_history_count()));
    delay_ms(600);
    const Snapshot state = snapshot();
    finish(accepted && released && state.attempts == 1 &&
               state.accepted == 1 && state.historyCount == 0,
           sampleBytes, heapBefore, released);
  }
  if (MROS2_MECHANISM_KIND_CODE == 19 ||
      MROS2_MECHANISM_KIND_CODE == 26) {
    const uint64_t matchDeadlineUs = esp_timer_get_time() +
        static_cast<uint64_t>(MROS2_MECHANISM_TIMEOUT_MS) * 1000U;
    while (esp_timer_get_time() < matchDeadlineUs &&
           mros2::publisher_matched_reader_count() < 2) {
      delay_ms(5);
    }
    const uint32_t matchedReaders =
        mros2::publisher_matched_reader_count();
    if (matchedReaders < 2) finish(false, sampleBytes, heapBefore, false);
    std::printf(
        "MECH_BOARD_PHASE schema=1 case_id=%s "
        "phase=two_readers_matched matched_readers=%u\n",
        MROS2_MECHANISM_CASE_ID,
        static_cast<unsigned>(matchedReaders));
    delay_ms(2000);
    const bool accepted = publish_one(publisher, 0);
    delay_ms(1200);
    const bool heldForSlowReader =
        mros2::publisher_history_count() == 1;
    std::printf(
        "MECH_BOARD_PHASE schema=1 case_id=%s "
        "phase=fast_reader_ack_only history_count=%u\n",
        MROS2_MECHANISM_CASE_ID,
        static_cast<unsigned>(mros2::publisher_history_count()));
    const uint64_t deadlineUs = esp_timer_get_time() +
        static_cast<uint64_t>(MROS2_MECHANISM_TIMEOUT_MS) * 1000U;
    while (esp_timer_get_time() < deadlineUs &&
           mros2::publisher_history_count() != 0) {
      delay_ms(5);
    }
    const bool releasedAfterSlowReader =
        mros2::publisher_history_count() == 0;
    std::printf(
        "MECH_BOARD_PHASE schema=1 case_id=%s "
        "phase=%s history_count=%u matched_readers=%u\n",
        MROS2_MECHANISM_CASE_ID,
        MROS2_MECHANISM_KIND_CODE == 26
            ? "departed_reader_released"
            : "slow_reader_ack_released",
        static_cast<unsigned>(mros2::publisher_history_count()),
        static_cast<unsigned>(mros2::publisher_matched_reader_count()));
    delay_ms(300);
    const Snapshot state = snapshot();
    finish(accepted && heldForSlowReader && releasedAfterSlowReader &&
               state.attempts == 1 && state.accepted == 1 &&
               state.historyCount == 0 &&
               (MROS2_MECHANISM_KIND_CODE != 26 ||
                mros2::publisher_matched_reader_count() == 1),
           sampleBytes, heapBefore, releasedAfterSlowReader);
  }
  if (MROS2_MECHANISM_KIND_CODE == 27) {
    const uint64_t matchDeadlineUs = esp_timer_get_time() +
        static_cast<uint64_t>(MROS2_MECHANISM_TIMEOUT_MS) * 1000U;
    while (esp_timer_get_time() < matchDeadlineUs &&
           mros2::publisher_matched_reader_count() < 2) {
      delay_ms(5);
    }
    const bool matchedBoth =
        mros2::publisher_matched_reader_count() == 2;
    if (!matchedBoth) finish(false, sampleBytes, heapBefore, false);
    std::printf(
        "MECH_BOARD_PHASE schema=1 case_id=%s "
        "phase=mixed_readers_matched matched_readers=2\n",
        MROS2_MECHANISM_CASE_ID);
    delay_ms(500);
    const bool accepted = publish_one(publisher, 0);
    const uint64_t releaseDeadlineUs = esp_timer_get_time() +
        static_cast<uint64_t>(MROS2_MECHANISM_TIMEOUT_MS) * 1000U;
    while (esp_timer_get_time() < releaseDeadlineUs &&
           mros2::publisher_history_count() != 0) {
      delay_ms(5);
    }
    const bool released = mros2::publisher_history_count() == 0;
    std::printf(
        "MECH_BOARD_PHASE schema=1 case_id=%s "
        "phase=mixed_reliability_released history_count=%u "
        "matched_readers=%u\n",
        MROS2_MECHANISM_CASE_ID,
        static_cast<unsigned>(mros2::publisher_history_count()),
        static_cast<unsigned>(mros2::publisher_matched_reader_count()));
    delay_ms(500);
    const Snapshot state = snapshot();
    finish(accepted && released && state.attempts == 1 &&
               state.accepted == 1 && state.historyCount == 0 &&
               mros2::publisher_matched_reader_count() == 2,
           sampleBytes, heapBefore, released);
  }
  if (MROS2_MECHANISM_KIND_CODE == 28) {
    const bool matched = wait_for_publisher_match(MROS2_MECHANISM_TIMEOUT_MS);
    if (!matched) finish(false, sampleBytes, heapBefore, false);
    std::printf(
        "MECH_BOARD_PHASE schema=1 case_id=%s "
        "phase=best_effort_reader_matched matched_readers=%u\n",
        MROS2_MECHANISM_CASE_ID,
        static_cast<unsigned>(mros2::publisher_matched_reader_count()));
    delay_ms(300);
    const bool accepted = publish_one(publisher, 0);
    const uint64_t releaseDeadlineUs = esp_timer_get_time() +
        static_cast<uint64_t>(MROS2_MECHANISM_TIMEOUT_MS) * 1000U;
    while (esp_timer_get_time() < releaseDeadlineUs &&
           mros2::publisher_history_count() != 0) {
      delay_ms(5);
    }
    const bool released = mros2::publisher_history_count() == 0;
    std::printf(
        "MECH_BOARD_PHASE schema=1 case_id=%s "
        "phase=best_effort_only_released history_count=%u "
        "matched_readers=%u\n",
        MROS2_MECHANISM_CASE_ID,
        static_cast<unsigned>(mros2::publisher_history_count()),
        static_cast<unsigned>(mros2::publisher_matched_reader_count()));
    delay_ms(500);
    const Snapshot state = snapshot();
    finish(accepted && released && state.attempts == 1 &&
               state.accepted == 1 && state.historyCount == 0 &&
               mros2::publisher_matched_reader_count() == 1,
           sampleBytes, heapBefore, released);
  }
  if (MROS2_MECHANISM_KIND_CODE == 25 ||
      MROS2_MECHANISM_KIND_CODE == 29 ||
      MROS2_MECHANISM_KIND_CODE == 35 ||
      MROS2_MECHANISM_KIND_CODE == 36 ||
      MROS2_MECHANISM_KIND_CODE == 37 ||
      MROS2_MECHANISM_KIND_CODE == 38) {
    const bool accepted = publish_one(publisher, 0);
    const bool seeded = mros2::publisher_history_count() == 1;
    std::printf(
        "MECH_BOARD_PHASE schema=1 case_id=%s "
        "phase=transient_late_reader_history_seeded history_count=%u\n",
        MROS2_MECHANISM_CASE_ID,
        static_cast<unsigned>(mros2::publisher_history_count()));
    const bool matched = wait_for_publisher_match(MROS2_MECHANISM_TIMEOUT_MS);
    delay_ms(800);
    const bool retained = mros2::publisher_history_count() == 1;
    std::printf(
        "MECH_BOARD_PHASE schema=1 case_id=%s "
        "phase=%s history_count=%u "
        "matched_readers=%u\n",
        MROS2_MECHANISM_CASE_ID,
        (MROS2_MECHANISM_KIND_CODE == 25 ||
         MROS2_MECHANISM_KIND_CODE == 35 ||
         MROS2_MECHANISM_KIND_CODE == 37)
            ? "transient_best_effort_volatile_not_replayed"
            : "transient_best_effort_replayed",
        static_cast<unsigned>(mros2::publisher_history_count()),
        static_cast<unsigned>(mros2::publisher_matched_reader_count()));
    const Snapshot state = snapshot();
    finish(accepted && seeded && matched && retained &&
               state.attempts == 1 && state.accepted == 1 &&
               state.historyCount == 1 &&
               mros2::publisher_matched_reader_count() == 1,
           sampleBytes, heapBefore, matched);
  }
  if (MROS2_MECHANISM_KIND_CODE == 20) {
    publish_attempts(publisher, 3);
    std::printf("MECH_BOARD_PHASE schema=1 case_id=%s phase=volatile_seeded\n",
                MROS2_MECHANISM_CASE_ID);
    const bool matched = wait_for_publisher_match(MROS2_MECHANISM_TIMEOUT_MS);
    delay_ms(200);
    const bool postJoin = matched && publish_one(publisher, 25);
    delay_ms(800);
    finish(matched && postJoin, sampleBytes, heapBefore, false);
  }
  if (MROS2_MECHANISM_KIND_CODE >= 21 &&
      MROS2_MECHANISM_KIND_CODE <= 24) {
    const uint32_t count = MROS2_MECHANISM_KIND_CODE == 24 ? 1U : 5U;
    publish_attempts(publisher, count);
    std::printf(
        "MECH_BOARD_PHASE schema=1 case_id=%s phase=transient_history_seeded\n",
        MROS2_MECHANISM_CASE_ID);
    const bool matched = wait_for_publisher_match(MROS2_MECHANISM_TIMEOUT_MS);
    delay_ms(1200);
    const uint32_t expectedDepth = MROS2_MECHANISM_KIND_CODE == 22 ? 2U :
        (MROS2_MECHANISM_KIND_CODE == 24 ? 1U : 3U);
    finish(matched && mros2::publisher_history_count() == expectedDepth,
           sampleBytes, heapBefore, false);
  }
}

void run_lifespan_writer_case(mros2::Publisher &publisher,
                              uint32_t sampleBytes, uint32_t heapBefore) {
  const bool lateReader = MROS2_MECHANISM_KIND_CODE == 43;
  bool matched = lateReader ? true :
      wait_for_publisher_match(MROS2_MECHANISM_TIMEOUT_MS);
  if (!matched) finish(false, sampleBytes, heapBefore, false);
  mros2::publisher_set_transmission_held(true);
  holdStartUs = static_cast<uint64_t>(esp_timer_get_time());
  const bool accepted = publish_one(publisher, 0);
  const uint32_t holdMs =
      (MROS2_MECHANISM_KIND_CODE == 42 || lateReader) ? 150U : 100U;
  std::printf(
      "MECH_BOARD_PHASE schema=1 case_id=%s phase=release_hold_start "
      "hold_ms=%u board_time_us=%llu\n",
      MROS2_MECHANISM_CASE_ID, static_cast<unsigned>(holdMs),
      static_cast<unsigned long long>(holdStartUs));
  delay_ms(holdMs);
  holdEndUs = static_cast<uint64_t>(esp_timer_get_time());
  mros2::publisher_set_transmission_held(false);
  std::printf(
      "MECH_BOARD_PHASE schema=1 case_id=%s phase=release_hold_end "
      "hold_ms=%u board_time_us=%llu\n",
      MROS2_MECHANISM_CASE_ID, static_cast<unsigned>(holdMs),
      static_cast<unsigned long long>(holdEndUs));
  if (lateReader) {
    std::printf(
        "MECH_BOARD_PHASE schema=1 case_id=%s phase=awaiting_late_reader\n",
        MROS2_MECHANISM_CASE_ID);
    matched = wait_for_publisher_match(MROS2_MECHANISM_TIMEOUT_MS);
  }
  delay_ms(500);
  const uint32_t drops = mros2::publisher_lifespan_drop_count();
  const uint64_t measuredHoldUs = holdEndUs - holdStartUs;
  bool passed = accepted && matched && measuredHoldUs >= holdMs * 1000ULL &&
      measuredHoldUs <= (holdMs + 20ULL) * 1000ULL;
  if (MROS2_MECHANISM_KIND_CODE == 42 || lateReader) {
    passed = passed && drops == 1 && mros2::publisher_history_count() == 0;
  } else {
    passed = passed && drops == 0;
  }
  finish(passed, sampleBytes, heapBefore, false);
}

void run_reader_case(uint32_t sampleBytes, uint32_t heapBefore) {
  mros2::register_subscriber_deadline_missed_callback(deadline_callback, nullptr);
  mros2::register_subscriber_liveliness_lost_callback(
      liveliness_lost_callback, nullptr);
  mros2::register_subscriber_liveliness_recovered_callback(
      liveliness_recovered_callback, nullptr);

  if (MROS2_MECHANISM_KIND_CODE == 12 ||
      MROS2_MECHANISM_KIND_CODE == 18) {
    const bool received = wait_for_rx(1, MROS2_MECHANISM_TIMEOUT_MS);
    delay_ms(1000);
    finish(received && applicationRx == 1 &&
               mros2::subscriber_received_count() == 1 &&
               mros2::subscriber_out_of_order_drop_count() >= 1,
           sampleBytes, heapBefore, false);
  }
  if (MROS2_MECHANISM_KIND_CODE == 57) {
    const bool firstReceived =
        wait_for_rx(1, MROS2_MECHANISM_TIMEOUT_MS);
    std::printf(
        "MECH_BOARD_PHASE schema=1 case_id=%s "
        "phase=awaiting_malformed_string_retry\n",
        MROS2_MECHANISM_CASE_ID);
    const bool secondReceived =
        firstReceived && wait_for_rx(2, MROS2_MECHANISM_TIMEOUT_MS);
    delay_ms(300);
    finish(secondReceived && applicationRx == 2 &&
               mros2::subscriber_received_count() == 2 &&
               mros2::subscriber_unsupported_payload_drop_count() == 1 &&
               mros2::subscriber_out_of_order_drop_count() == 0,
           sampleBytes, heapBefore, true);
  }
  if (MROS2_MECHANISM_KIND_CODE == 13) {
    const bool received = wait_for_rx(3, MROS2_MECHANISM_TIMEOUT_MS);
    delay_ms(500);
    finish(received && applicationRx == 3 &&
               mros2::subscriber_received_count() == 3 &&
               mros2::subscriber_out_of_order_drop_count() >= 1,
           sampleBytes, heapBefore, false);
  }
  if (MROS2_MECHANISM_KIND_CODE == 14) {
    const bool received = wait_for_rx(2, MROS2_MECHANISM_TIMEOUT_MS);
    delay_ms(500);
    finish(received && applicationRx == 2 && firstRxHash != secondRxHash,
           sampleBytes, heapBefore, true);
  }
  if (MROS2_MECHANISM_KIND_CODE == 17) {
    const bool firstReceived = wait_for_rx(1, MROS2_MECHANISM_TIMEOUT_MS);
    const bool writerMatched =
        firstReceived && wait_for_subscriber_match(MROS2_MECHANISM_TIMEOUT_MS);
    std::printf(
        "MECH_BOARD_PHASE schema=1 case_id=%s phase=awaiting_host_gap "
        "app_rx=%u gap_received=%u matched=%u\n",
        MROS2_MECHANISM_CASE_ID, static_cast<unsigned>(applicationRx),
        static_cast<unsigned>(mros2::subscriber_gap_received_count()),
        writerMatched ? 1U : 0U);
    const bool secondReceived =
        writerMatched && wait_for_rx(2, MROS2_MECHANISM_TIMEOUT_MS);
    delay_ms(500);
    finish(secondReceived && applicationRx == 2 &&
               mros2::subscriber_gap_received_count() == 1 &&
               mros2::subscriber_out_of_order_drop_count() == 0,
           sampleBytes, heapBefore, false);
  }
  if (MROS2_MECHANISM_KIND_CODE == 30) {
    const bool received = wait_for_rx(1, MROS2_MECHANISM_TIMEOUT_MS);
    const bool matched = received && wait_for_subscriber_match(200);
    delay_ms(150);
    finish(received && matched &&
               mros2::subscriber_deadline_missed_count() == 0 &&
               deadlineCallbacks == 0,
           sampleBytes, heapBefore, false);
  }
  if (MROS2_MECHANISM_KIND_CODE == 31 ||
      MROS2_MECHANISM_KIND_CODE == 34) {
    const bool received = wait_for_rx(1, MROS2_MECHANISM_TIMEOUT_MS);
    const bool matched = received && wait_for_subscriber_match(200);
    const bool missed = matched && wait_for_deadline_count(1, 200);
    const uint32_t latencyMs =
        firstDeadlineCallbackClockMs - firstRxClockMs;
    const uint32_t upperMs = MROS2_MECHANISM_KIND_CODE == 34 ? 65U : 70U;
    finish(missed && matched &&
               mros2::subscriber_deadline_missed_count() == 1 &&
               deadlineCallbacks == 1 && latencyMs >= 50U &&
               latencyMs <= upperMs,
           sampleBytes, heapBefore, false);
  }
  if (MROS2_MECHANISM_KIND_CODE == 32) {
    const bool received = wait_for_rx(1, MROS2_MECHANISM_TIMEOUT_MS);
    const bool matched = received && wait_for_subscriber_match(200);
    if (received) delay_ms(180);
    finish(received && matched &&
               mros2::subscriber_deadline_missed_count() == 3 &&
               deadlineCallbacks == 3,
           sampleBytes, heapBefore, false);
  }
  if (MROS2_MECHANISM_KIND_CODE == 33) {
    const bool received = wait_for_rx(2, MROS2_MECHANISM_TIMEOUT_MS);
    const bool matched = received && wait_for_subscriber_match(200);
    const bool missedTwice = matched && wait_for_deadline_count(2, 200);
    finish(missedTwice && applicationRx == 2 &&
               mros2::subscriber_deadline_missed_count() == 2 &&
               deadlineCallbacks == 2 && secondRxUs > firstRxUs,
           sampleBytes, heapBefore, true);
  }
  if (MROS2_MECHANISM_KIND_CODE == 50) {
    delay_ms(700);
    finish(!mros2::subscriber_matched() &&
               mros2::subscriber_liveliness_lost_count() == 0 &&
               mros2::subscriber_liveliness_recovered_count() == 0,
           sampleBytes, heapBefore, false);
  }
  if (MROS2_MECHANISM_KIND_CODE == 51 ||
      MROS2_MECHANISM_KIND_CODE == 52) {
    const bool received = wait_for_rx(1, MROS2_MECHANISM_TIMEOUT_MS);
    const bool lost = received && wait_for_liveliness(1, 0, 3000);
    if (MROS2_MECHANISM_KIND_CODE == 52) delay_ms(1000);
    finish(lost && mros2::subscriber_liveliness_lost_count() == 1 &&
               mros2::subscriber_liveliness_recovered_count() == 0 &&
               livelinessLostCallbacks == 1,
           sampleBytes, heapBefore, false);
  }
  if (MROS2_MECHANISM_KIND_CODE == 53) {
    const bool received = wait_for_rx(1, MROS2_MECHANISM_TIMEOUT_MS);
    const bool lost = received && wait_for_liveliness(1, 0, 3000);
    const bool recovered = lost && wait_for_liveliness(
        1, 1, MROS2_MECHANISM_TIMEOUT_MS);
    finish(recovered && mros2::subscriber_liveliness_lost_count() == 1 &&
               mros2::subscriber_liveliness_recovered_count() == 1 &&
               livelinessLostCallbacks == 1 &&
               livelinessRecoveredCallbacks == 1,
           sampleBytes, heapBefore, recovered);
  }
  if (MROS2_MECHANISM_KIND_CODE == 54) {
    const bool received = wait_for_rx(1, MROS2_MECHANISM_TIMEOUT_MS);
    if (received) delay_ms(1000);
    finish(received && mros2::subscriber_liveliness_lost_count() == 0 &&
               mros2::subscriber_liveliness_recovered_count() == 0 &&
               mros2::subscriber_writer_alive(),
           sampleBytes, heapBefore, false);
  }
  finish(false, sampleBytes, heapBefore, false);
}

}  // namespace

extern "C" void app_main(void) {
  if (MROS2_MECHANISM_KIND_CODE == 23 && !advance_persistent_boot_epoch()) {
    std::printf(
        "MECH_BOARD_ERROR schema=1 case_id=%s reason=boot_epoch_store\n",
        MROS2_MECHANISM_CASE_ID);
    return;
  }
  const uint32_t sampleBytes = serialized_bytes();
  std::printf(
      "MECH_BOARD_CONFIG schema=1 case_id=%s kind=%s kind_code=%d topic=%s "
      "payload_bytes=%u sample_bytes=%u sample_limit=%u "
      "history_capacity=%u acknack_sequence_budget=%u "
      "unmatched_user_reader_fallback=%u "
      "timeout_ms=%u monitor_period_ms=5 tick_hz=1000 "
      "cache_change_bytes=%u boot_epoch=%u boot_epoch_store=%s\n",
      MROS2_MECHANISM_CASE_ID, MROS2_MECHANISM_KIND,
      MROS2_MECHANISM_KIND_CODE, MROS2_MECHANISM_TOPIC,
      static_cast<unsigned>(MROS2_MECHANISM_PAYLOAD_BYTES),
      static_cast<unsigned>(sampleBytes),
      static_cast<unsigned>(MROS2_MECHANISM_SAMPLE_LIMIT),
      static_cast<unsigned>(MROS2_MECHANISM_HISTORY_CAPACITY),
      static_cast<unsigned>(
          MROS2_RTPS_ACKNACK_SEQUENCE_RESPONSE_BUDGET),
      static_cast<unsigned>(
          MROS2_ALLOW_UNMATCHED_USER_READER_FALLBACK),
      static_cast<unsigned>(MROS2_MECHANISM_TIMEOUT_MS),
      static_cast<unsigned>(sizeof(rtps::CacheChange)),
      static_cast<unsigned>(mechanismBootEpoch),
      MROS2_MECHANISM_KIND_CODE == 23 ? "nvs" : "none");
  if (!mros2_platform_network_connect()) {
    std::printf("MECH_BOARD_ERROR schema=1 case_id=%s reason=network_connect\n",
                MROS2_MECHANISM_CASE_ID);
    return;
  }

  mros2::init(0, nullptr);
  auto node = mros2::Node::create_node("seven_qos_mechanism_board");
  auto qos = make_qos(sampleBytes);
  if (is_reader_case()) {
    auto subscriber = node.create_subscription<std_msgs::msg::String>(
        MROS2_MECHANISM_TOPIC, qos, subscription_callback);
    (void)subscriber;
    const uint32_t heapBefore = esp_get_free_heap_size();
    std::printf(
        "MECH_BOARD_LOCAL_READY schema=1 case_id=%s role=subscriber "
        "board_time_us=%llu heap_before=%u\n",
        MROS2_MECHANISM_CASE_ID,
        static_cast<unsigned long long>(esp_timer_get_time()),
        static_cast<unsigned>(heapBefore));
    run_reader_case(sampleBytes, heapBefore);
  }

  auto publisher =
      node.create_publisher<std_msgs::msg::String>(MROS2_MECHANISM_TOPIC, qos);
  if constexpr (MROS2_MECHANISM_KIND_CODE < 0) {
    auto unused = node.create_subscription<std_msgs::msg::String>(
        MROS2_MECHANISM_TOPIC, qos, subscription_callback);
    (void)unused;
  }
  const uint32_t heapBefore = esp_get_free_heap_size();
  std::printf(
      "MECH_BOARD_LOCAL_READY schema=1 case_id=%s role=publisher "
      "board_time_us=%llu heap_before=%u\n",
      MROS2_MECHANISM_CASE_ID,
      static_cast<unsigned long long>(esp_timer_get_time()),
      static_cast<unsigned>(heapBefore));

  if (MROS2_MECHANISM_KIND_CODE >= 1 && MROS2_MECHANISM_KIND_CODE <= 9) {
    run_resource_case(publisher, sampleBytes, heapBefore);
  }
  if ((MROS2_MECHANISM_KIND_CODE >= 10 &&
      MROS2_MECHANISM_KIND_CODE <= 11) ||
      MROS2_MECHANISM_KIND_CODE == 15 ||
      MROS2_MECHANISM_KIND_CODE == 16 ||
      MROS2_MECHANISM_KIND_CODE == 18 ||
      MROS2_MECHANISM_KIND_CODE == 19 ||
      MROS2_MECHANISM_KIND_CODE == 26 ||
      MROS2_MECHANISM_KIND_CODE == 27 ||
      MROS2_MECHANISM_KIND_CODE == 28 ||
      MROS2_MECHANISM_KIND_CODE == 25 ||
      MROS2_MECHANISM_KIND_CODE == 29 ||
      MROS2_MECHANISM_KIND_CODE == 35 ||
      MROS2_MECHANISM_KIND_CODE == 36 ||
      MROS2_MECHANISM_KIND_CODE == 37 ||
      MROS2_MECHANISM_KIND_CODE == 38 ||
      (MROS2_MECHANISM_KIND_CODE >= 20 &&
       MROS2_MECHANISM_KIND_CODE <= 24)) {
    run_history_or_durability_writer_case(publisher, sampleBytes, heapBefore);
  }
  if (MROS2_MECHANISM_KIND_CODE >= 40 &&
      MROS2_MECHANISM_KIND_CODE <= 44) {
    run_lifespan_writer_case(publisher, sampleBytes, heapBefore);
  }
  finish(false, sampleBytes, heapBefore, false);
}
