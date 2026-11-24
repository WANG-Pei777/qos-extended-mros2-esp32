/* Excluded Seven-QoS performance telemetry-path pilot for the current system. */

#include "mros2.h"
#include "mros2-platform.h"
#include "std_msgs/msg/string.hpp"

#include "cmsis_os2.h"
#include "benchmark_control_probe.h"
#include "esp_log.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"

#include <array>
#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <inttypes.h>
#include <limits>

#ifdef MATCHED_BENCH_TELEMETRY_ENABLED
#include "benchmark_telemetry.h"
#include "esp_crc.h"
#endif

namespace {

#ifndef MATCHED_BENCH_PAYLOAD_BYTES
#define MATCHED_BENCH_PAYLOAD_BYTES 64
#endif
#ifndef MATCHED_BENCH_PUBLISH_RATE_HZ
#define MATCHED_BENCH_PUBLISH_RATE_HZ 10
#endif
#ifndef MATCHED_BENCH_WINDOW_MS
#define MATCHED_BENCH_WINDOW_MS 20000
#endif
#ifndef MATCHED_BENCH_REPLY_GRACE_MS
#define MATCHED_BENCH_REPLY_GRACE_MS 5000
#endif
#ifndef MATCHED_BENCH_RDH_DEPTH
#define MATCHED_BENCH_RDH_DEPTH 10
#endif
#ifndef MATCHED_BENCH_HISTORY_DEPTH
#define MATCHED_BENCH_HISTORY_DEPTH 10
#endif
#ifndef MATCHED_BENCH_IMPAIRMENT
#define MATCHED_BENCH_IMPAIRMENT clean
#endif
#ifndef SEVEN_QOS_PERFORMANCE_FAMILY
#define SEVEN_QOS_PERFORMANCE_FAMILY "common"
#endif
#ifndef SEVEN_QOS_PERFORMANCE_FAMILY_CODE
#define SEVEN_QOS_PERFORMANCE_FAMILY_CODE 0
#endif
#ifndef SEVEN_QOS_PERFORMANCE_CELL_ID
#define SEVEN_QOS_PERFORMANCE_CELL_ID "COMMON"
#endif
#ifndef SEVEN_QOS_PERFORMANCE_RUN_TOKEN
#define SEVEN_QOS_PERFORMANCE_RUN_TOKEN "mros2qos-telemetry-smoke-001"
#endif
#ifndef SEVEN_QOS_PERFORMANCE_DEADLINE_MS
#define SEVEN_QOS_PERFORMANCE_DEADLINE_MS 0
#endif
#ifndef SEVEN_QOS_PERFORMANCE_LIFESPAN_MS
#define SEVEN_QOS_PERFORMANCE_LIFESPAN_MS 0
#endif
#ifndef SEVEN_QOS_PERFORMANCE_RELEASE_DELAY_MS
#define SEVEN_QOS_PERFORMANCE_RELEASE_DELAY_MS 0
#endif
#ifndef SEVEN_QOS_PERFORMANCE_RESOURCE_MAX_SAMPLES
#define SEVEN_QOS_PERFORMANCE_RESOURCE_MAX_SAMPLES 0
#endif
#ifndef SEVEN_QOS_PERFORMANCE_RESOURCE_PROBE_EXTRA
#define SEVEN_QOS_PERFORMANCE_RESOURCE_PROBE_EXTRA 0
#endif
#ifndef SEVEN_QOS_PERFORMANCE_RESOURCE_ACK_SUPPRESSION_MS
#define SEVEN_QOS_PERFORMANCE_RESOURCE_ACK_SUPPRESSION_MS 0
#endif
#ifndef SEVEN_QOS_PERFORMANCE_HISTORY_DEPTH
#define SEVEN_QOS_PERFORMANCE_HISTORY_DEPTH 0
#endif
#ifndef SEVEN_QOS_PERFORMANCE_HISTORY_BURST_SIZE
#define SEVEN_QOS_PERFORMANCE_HISTORY_BURST_SIZE 0
#endif
#ifndef SEVEN_QOS_PERFORMANCE_DURABILITY
#define SEVEN_QOS_PERFORMANCE_DURABILITY "none"
#endif
#ifndef SEVEN_QOS_PERFORMANCE_DURABILITY_CODE
#define SEVEN_QOS_PERFORMANCE_DURABILITY_CODE 0
#endif
#ifndef SEVEN_QOS_PERFORMANCE_DURABILITY_CACHE_DEPTH
#define SEVEN_QOS_PERFORMANCE_DURABILITY_CACHE_DEPTH 0
#endif
#ifndef SEVEN_QOS_PERFORMANCE_DURABILITY_PREJOIN_SAMPLES
#define SEVEN_QOS_PERFORMANCE_DURABILITY_PREJOIN_SAMPLES 0
#endif
#ifndef SEVEN_QOS_PERFORMANCE_LIVELINESS_LEASE_MS
#define SEVEN_QOS_PERFORMANCE_LIVELINESS_LEASE_MS 0
#endif
#ifndef SEVEN_QOS_PERFORMANCE_LIVELINESS_OUTAGE_MS
#define SEVEN_QOS_PERFORMANCE_LIVELINESS_OUTAGE_MS 0
#endif

#if defined(MATCHED_BENCH_RELIABLE) && !defined(MROS2_QOS_CURRENT)
#error "upstream mros2-esp32 does not expose Reliable user-endpoint creation"
#endif

#ifdef MROS2_QOS_CURRENT
constexpr char kSystemName[] = "mros2qos";
#else
constexpr char kSystemName[] = "upstream";
#endif
#ifdef MATCHED_BENCH_TELEMETRY_ENABLED
constexpr char kRunToken[] = SEVEN_QOS_PERFORMANCE_RUN_TOKEN;
#endif
#ifdef MATCHED_BENCH_RELIABLE
constexpr char kQosName[] = "RELIABLE";
#else
constexpr char kQosName[] = "BEST_EFFORT";
#endif
#ifdef MATCHED_BENCH_TELEMETRY_ENABLED
constexpr char kTelemetryMode[] = "on";
#else
constexpr char kTelemetryMode[] = "off";
#endif
constexpr uint32_t kPayloadBytes = MATCHED_BENCH_PAYLOAD_BYTES;
constexpr uint32_t kPublishRateHz = MATCHED_BENCH_PUBLISH_RATE_HZ;
constexpr uint32_t kMeasurementWindowMs = MATCHED_BENCH_WINDOW_MS;
constexpr char kPolicyFamily[] = SEVEN_QOS_PERFORMANCE_FAMILY;
constexpr uint32_t kPolicyFamilyCode = SEVEN_QOS_PERFORMANCE_FAMILY_CODE;
constexpr char kPolicyCellId[] = SEVEN_QOS_PERFORMANCE_CELL_ID;
constexpr uint32_t kDeadlineMs = SEVEN_QOS_PERFORMANCE_DEADLINE_MS;
constexpr uint32_t kLifespanMs = SEVEN_QOS_PERFORMANCE_LIFESPAN_MS;
constexpr uint32_t kReleaseDelayMs = SEVEN_QOS_PERFORMANCE_RELEASE_DELAY_MS;
constexpr uint32_t kResourceMaxSamples =
    SEVEN_QOS_PERFORMANCE_RESOURCE_MAX_SAMPLES;
constexpr uint32_t kResourceProbeExtra =
    SEVEN_QOS_PERFORMANCE_RESOURCE_PROBE_EXTRA;
constexpr uint32_t kResourceAckSuppressionMs =
    SEVEN_QOS_PERFORMANCE_RESOURCE_ACK_SUPPRESSION_MS;
constexpr uint32_t kHistoryDepth = SEVEN_QOS_PERFORMANCE_HISTORY_DEPTH;
constexpr uint32_t kHistoryBurstSize =
    SEVEN_QOS_PERFORMANCE_HISTORY_BURST_SIZE;
constexpr char kDurability[] = SEVEN_QOS_PERFORMANCE_DURABILITY;
constexpr uint32_t kDurabilityCode = SEVEN_QOS_PERFORMANCE_DURABILITY_CODE;
constexpr uint32_t kDurabilityCacheDepth =
    SEVEN_QOS_PERFORMANCE_DURABILITY_CACHE_DEPTH;
constexpr uint32_t kDurabilityPrejoinSamples =
    SEVEN_QOS_PERFORMANCE_DURABILITY_PREJOIN_SAMPLES;
constexpr uint32_t kLivelinessLeaseMs =
    SEVEN_QOS_PERFORMANCE_LIVELINESS_LEASE_MS;
constexpr uint32_t kLivelinessOutageMs =
    SEVEN_QOS_PERFORMANCE_LIVELINESS_OUTAGE_MS;
#define MATCHED_BENCH_STRINGIFY_INNER(value) #value
#define MATCHED_BENCH_STRINGIFY(value) MATCHED_BENCH_STRINGIFY_INNER(value)
constexpr char kImpairment[] = MATCHED_BENCH_STRINGIFY(MATCHED_BENCH_IMPAIRMENT);
constexpr uint32_t kMeasurementMessages =
    kPublishRateHz * kMeasurementWindowMs / 1000U;
constexpr uint32_t kPublishPeriodMs = 1000U / kPublishRateHz;
constexpr uint32_t kWarmupPeriodMs = 500;
constexpr uint32_t kReadySettleMs = 1000;
constexpr uint32_t kReplyGraceMs = MATCHED_BENCH_REPLY_GRACE_MS;
constexpr uint32_t kRdhDepth = MATCHED_BENCH_RDH_DEPTH;
constexpr uint32_t kMatchedHistoryDepth = MATCHED_BENCH_HISTORY_DEPTH;
constexpr int kMarkerGpio = 4;
static_assert(kPayloadBytes >= 32U && kPayloadBytes <= 2048U);
static_assert(kPublishRateHz > 0U && 1000U % kPublishRateHz == 0U);
static_assert(kMeasurementWindowMs >= 500U &&
              kMeasurementWindowMs <= 20000U);
static_assert(kMeasurementWindowMs > 0U &&
              kPublishRateHz * kMeasurementWindowMs % 1000U == 0U);
static_assert(kMatchedHistoryDepth >= 1U && kMatchedHistoryDepth <= 40U);
static_assert(kMeasurementMessages * kPublishPeriodMs == kMeasurementWindowMs);
static_assert(kReplyGraceMs >= 1000U && kReplyGraceMs <= 30000U);
static_assert(kRdhDepth >= 1U && kRdhDepth <= 40U);
static_assert(kPolicyFamilyCode <= 6U);
static_assert(kResourceAckSuppressionMs <= 30000U);

mros2::Subscriber subscriber;
mros2::Publisher publisher;
std::atomic<int64_t> ready_ms{-1};
std::atomic<uint32_t> warmup_reply_count{0};
std::atomic<uint32_t> prime_reply_count{0};
std::atomic<uint32_t> rx_count{0};
std::atomic<uint32_t> publish_failures{0};
SemaphoreHandle_t stats_mutex = nullptr;
std::array<bool, kMeasurementMessages> received{};
std::array<uint32_t, kMeasurementMessages> rtt_by_sequence{};
std::array<uint32_t, kMeasurementMessages> arrival_rank_by_sequence{};
std::array<uint32_t, kMeasurementMessages> tx_offset_by_sequence{};
std::array<uint32_t, kMeasurementMessages> rx_offset_by_sequence{};
std::array<char, kPayloadBytes + 1U> publish_payload{};
int64_t boot_us = 0;
std::atomic<int64_t> measurement_epoch_us{-1};
std::atomic<bool> accepting_measurements{false};
uint64_t rtt_sum_us = 0;
uint64_t rtt_sum_sq_us2 = 0;
uint32_t rtt_min_us = std::numeric_limits<uint32_t>::max();
uint32_t rtt_max_us = 0;
uint32_t duplicate_count = 0;
uint32_t malformed_count = 0;
uint32_t arrival_inversions = 0;
uint32_t highest_sequence_seen = 0;
bool have_sequence = false;
std::atomic<int64_t> policy_window_start_us{-1};
std::atomic<uint32_t> policy_deadline_callbacks{0};
std::atomic<int64_t> first_deadline_callback_offset_us{-1};
std::atomic<uint32_t> policy_lifespan_probe_replies{0};
std::atomic<uint32_t> policy_resource_probe_replies{0};
std::atomic<uint32_t> policy_history_probe_replies{0};
std::atomic<uint64_t> policy_history_probe_reply_mask{0};
std::atomic<uint32_t> policy_durability_probe_replies{0};
std::atomic<uint64_t> policy_durability_probe_reply_mask{0};
std::atomic<int64_t> policy_liveliness_window_start_us{-1};
std::atomic<uint32_t> policy_liveliness_lost_callbacks{0};
std::atomic<uint32_t> policy_liveliness_recovered_callbacks{0};
std::atomic<int64_t> first_liveliness_lost_offset_us{-1};
std::atomic<int64_t> first_liveliness_recovered_offset_us{-1};

void deadline_missed_callback(void *)
{
  const int64_t window_start_us = policy_window_start_us.load();
  if (window_start_us < 0) {
    return;
  }
  const int64_t offset_us = esp_timer_get_time() - window_start_us;
  policy_deadline_callbacks.fetch_add(1);
  int64_t unset = -1;
  first_deadline_callback_offset_us.compare_exchange_strong(unset, offset_us);
}

void liveliness_lost_callback(void *)
{
  const int64_t window_start_us = policy_liveliness_window_start_us.load();
  if (window_start_us < 0) {
    return;
  }
  const int64_t offset_us = esp_timer_get_time() - window_start_us;
  policy_liveliness_lost_callbacks.fetch_add(1);
  int64_t unset = -1;
  first_liveliness_lost_offset_us.compare_exchange_strong(unset, offset_us);
}

void liveliness_recovered_callback(void *)
{
  const int64_t window_start_us = policy_liveliness_window_start_us.load();
  if (window_start_us < 0) {
    return;
  }
  const int64_t offset_us = esp_timer_get_time() - window_start_us;
  policy_liveliness_recovered_callbacks.fetch_add(1);
  int64_t unset = -1;
  first_liveliness_recovered_offset_us.compare_exchange_strong(unset, offset_us);
}

uint32_t counter_delta(uint32_t before, uint32_t after)
{
  return after >= before ? after - before : 0U;
}

struct LifespanProbe {
  uint32_t drops_before = 0;
  uint32_t drops_after = 0;
  bool accepted = false;
  int64_t hold_start_us = -1;
  int64_t hold_end_us = -1;
};

struct ResourceProbe {
  uint32_t attempts_before = 0;
  uint32_t attempts_after = 0;
  uint32_t accepted_before = 0;
  uint32_t accepted_after = 0;
  uint32_t rejected_before = 0;
  uint32_t rejected_after = 0;
  uint32_t allocation_failures_before = 0;
  uint32_t allocation_failures_after = 0;
  uint32_t history_peak = 0;
  uint32_t history_after_release = 0;
};

struct HistoryProbe {
  uint32_t attempts_before = 0;
  uint32_t attempts_after = 0;
  uint32_t accepted_before = 0;
  uint32_t accepted_after = 0;
  uint32_t rejected_before = 0;
  uint32_t rejected_after = 0;
  uint32_t allocation_failures_before = 0;
  uint32_t allocation_failures_after = 0;
  uint32_t history_peak = 0;
  uint32_t history_after_release = 0;
};

struct DurabilityProbe {
  uint32_t attempts_before = 0;
  uint32_t attempts_after = 0;
  uint32_t accepted_before = 0;
  uint32_t accepted_after = 0;
  uint32_t rejected_before = 0;
  uint32_t rejected_after = 0;
  uint32_t allocation_failures_before = 0;
  uint32_t allocation_failures_after = 0;
  uint32_t history_prejoin = 0;
  uint32_t history_after_join = 0;
};

struct LivelinessProbe {
  uint32_t lost_before = 0;
  uint32_t lost_after = 0;
  uint32_t recovered_before = 0;
  uint32_t recovered_after = 0;
  bool writer_alive_final = false;
};

void emit_policy_final(uint32_t deadline_before, uint32_t deadline_after,
                       const LifespanProbe &lifespan,
                       const ResourceProbe &resource,
                       const HistoryProbe &history,
                       const DurabilityProbe &durability,
                       const LivelinessProbe &liveliness)
{
  const uint32_t lifespan_drops_final =
      mros2::publisher_lifespan_drop_count();
  const int64_t hold_duration_us =
      lifespan.hold_start_us >= 0 && lifespan.hold_end_us >= lifespan.hold_start_us
          ? lifespan.hold_end_us - lifespan.hold_start_us
          : -1;
  std::printf(
      "PERF_POLICY_FINAL schema=1 family=%s family_code=%" PRIu32
      " cell_id=%s deadline_ms=%" PRIu32 " publish_period_ms=%" PRIu32
      " deadline_missed_before=%" PRIu32 " deadline_missed_after=%" PRIu32
      " deadline_missed_delta=%" PRIu32 " deadline_callbacks=%" PRIu32
      " first_deadline_callback_offset_us=%" PRId64
      " lifespan_ms=%" PRIu32 " release_delay_ms=%" PRIu32
      " lifespan_drop_before=%" PRIu32 " lifespan_drop_after=%" PRIu32
      " lifespan_drop_delta=%" PRIu32 " lifespan_drop_final=%" PRIu32
      " lifespan_total_drop_delta=%" PRIu32
      " lifespan_probe_accepted=%u"
      " lifespan_probe_replies=%" PRIu32
      " hold_start_us=%" PRId64 " hold_end_us=%" PRId64
      " hold_duration_us=%" PRId64
      " resource_max_samples=%" PRIu32
      " resource_probe_extra=%" PRIu32
      " resource_ack_suppression_ms=%" PRIu32
      " resource_attempt_delta=%" PRIu32
      " resource_accept_delta=%" PRIu32
      " resource_reject_delta=%" PRIu32
      " resource_allocation_failure_delta=%" PRIu32
      " resource_history_peak=%" PRIu32
      " resource_history_after_release=%" PRIu32
      " resource_probe_replies=%" PRIu32
      " history_depth=%" PRIu32
      " history_burst_size=%" PRIu32
      " history_attempt_delta=%" PRIu32
      " history_accept_delta=%" PRIu32
      " history_reject_delta=%" PRIu32
      " history_allocation_failure_delta=%" PRIu32
      " history_peak=%" PRIu32
      " history_after_release=%" PRIu32
      " history_probe_replies=%" PRIu32
      " history_probe_reply_mask=0x%016" PRIx64
      " durability=%s durability_code=%" PRIu32
      " durability_cache_depth=%" PRIu32
      " durability_prejoin_samples=%" PRIu32
      " durability_attempt_delta=%" PRIu32
      " durability_accept_delta=%" PRIu32
      " durability_reject_delta=%" PRIu32
      " durability_allocation_failure_delta=%" PRIu32
      " durability_history_prejoin=%" PRIu32
      " durability_history_after_join=%" PRIu32
      " durability_probe_replies=%" PRIu32
      " durability_probe_reply_mask=0x%016" PRIx64
      " durability_reader_matched=%u"
      " liveliness_lease_ms=%" PRIu32
      " liveliness_outage_ms=%" PRIu32
      " liveliness_lost_before=%" PRIu32
      " liveliness_lost_after=%" PRIu32
      " liveliness_lost_delta=%" PRIu32
      " liveliness_recovered_before=%" PRIu32
      " liveliness_recovered_after=%" PRIu32
      " liveliness_recovered_delta=%" PRIu32
      " liveliness_lost_callbacks=%" PRIu32
      " liveliness_recovered_callbacks=%" PRIu32
      " first_liveliness_lost_offset_us=%" PRId64
      " first_liveliness_recovered_offset_us=%" PRId64
      " liveliness_writer_alive_final=%u\n",
      kPolicyFamily,
      kPolicyFamilyCode,
      kPolicyCellId,
      kDeadlineMs,
      kPublishPeriodMs,
      deadline_before,
      deadline_after,
      counter_delta(deadline_before, deadline_after),
      policy_deadline_callbacks.load(),
      first_deadline_callback_offset_us.load(),
      kLifespanMs,
      kReleaseDelayMs,
      lifespan.drops_before,
      lifespan.drops_after,
      counter_delta(lifespan.drops_before, lifespan.drops_after),
      lifespan_drops_final,
      counter_delta(lifespan.drops_before, lifespan_drops_final),
      lifespan.accepted ? 1U : 0U,
      policy_lifespan_probe_replies.load(),
      lifespan.hold_start_us,
      lifespan.hold_end_us,
      hold_duration_us,
      kResourceMaxSamples,
      kResourceProbeExtra,
      kResourceAckSuppressionMs,
      counter_delta(resource.attempts_before, resource.attempts_after),
      counter_delta(resource.accepted_before, resource.accepted_after),
      counter_delta(resource.rejected_before, resource.rejected_after),
      counter_delta(resource.allocation_failures_before,
                    resource.allocation_failures_after),
      resource.history_peak,
      resource.history_after_release,
      policy_resource_probe_replies.load(),
      kHistoryDepth,
      kHistoryBurstSize,
      counter_delta(history.attempts_before, history.attempts_after),
      counter_delta(history.accepted_before, history.accepted_after),
      counter_delta(history.rejected_before, history.rejected_after),
      counter_delta(history.allocation_failures_before,
                    history.allocation_failures_after),
      history.history_peak,
      history.history_after_release,
      policy_history_probe_replies.load(),
      policy_history_probe_reply_mask.load(),
      kDurability,
      kDurabilityCode,
      kDurabilityCacheDepth,
      kDurabilityPrejoinSamples,
      counter_delta(durability.attempts_before, durability.attempts_after),
      counter_delta(durability.accepted_before, durability.accepted_after),
      counter_delta(durability.rejected_before, durability.rejected_after),
      counter_delta(durability.allocation_failures_before,
                    durability.allocation_failures_after),
      durability.history_prejoin,
      durability.history_after_join,
      policy_durability_probe_replies.load(),
      policy_durability_probe_reply_mask.load(),
      mros2::publisher_has_matched_reader() ? 1U : 0U,
      kLivelinessLeaseMs,
      kLivelinessOutageMs,
      liveliness.lost_before,
      liveliness.lost_after,
      counter_delta(liveliness.lost_before, liveliness.lost_after),
      liveliness.recovered_before,
      liveliness.recovered_after,
      counter_delta(liveliness.recovered_before, liveliness.recovered_after),
      policy_liveliness_lost_callbacks.load(),
      policy_liveliness_recovered_callbacks.load(),
      first_liveliness_lost_offset_us.load(),
      first_liveliness_recovered_offset_us.load(),
      liveliness.writer_alive_final ? 1U : 0U);
  std::fflush(stdout);
}

struct DeliveryShape {
  uint32_t missing = 0;
  uint32_t missing_runs = 0;
  uint32_t max_missing_run = 0;
};

DeliveryShape summarize_delivery_shape()
{
  DeliveryShape shape;
  uint32_t current_run = 0;
  for (bool delivered : received) {
    if (!delivered) {
      ++shape.missing;
      ++current_run;
      if (current_run > shape.max_missing_run) {
        shape.max_missing_run = current_run;
      }
    } else if (current_run != 0) {
      ++shape.missing_runs;
      current_run = 0;
    }
  }
  if (current_run != 0) {
    ++shape.missing_runs;
  }
  return shape;
}

void emit_missing_sequences()
{
  std::printf("COMPARE_MISSING system=%s count=%" PRIu32 " sequences=",
              kSystemName, kMeasurementMessages - rx_count.load());
  bool first = true;
  for (uint32_t sequence = 0; sequence < kMeasurementMessages; ++sequence) {
    if (!received[sequence]) {
      std::printf("%s%" PRIu32, first ? "" : ",", sequence);
      first = false;
    }
  }
  std::printf("\n");
  std::fflush(stdout);
}

void emit_rtt_samples()
{
  for (uint32_t sequence = 0; sequence < kMeasurementMessages; ++sequence) {
    if (!received[sequence]) {
      continue;
    }
    std::printf(
        "COMPARE_RTT system=%s seq=%" PRIu32 " rtt_us=%" PRIu32
        " arrival_rank=%" PRIu32 " tx_offset_us=%" PRIu32
        " rx_offset_us=%" PRIu32 "\n",
        kSystemName,
        sequence,
        rtt_by_sequence[sequence],
        arrival_rank_by_sequence[sequence],
        tx_offset_by_sequence[sequence],
        rx_offset_by_sequence[sequence]);
  }
  std::fflush(stdout);
}

#ifdef MATCHED_BENCH_TELEMETRY_ENABLED
bool uart_sink(const char *record, size_t length, void *)
{
  const bool written = std::fwrite(record, 1, length, stdout) == length &&
                       std::fputc('\n', stdout) != EOF;
  std::fflush(stdout);
  vTaskDelay(1);
  return written;
}

bool emit_owned_record(benchmark_telemetry_stream_state_t &stream,
                       const char *record)
{
  const size_t length = std::strlen(record);
  if (!uart_sink(record, length, nullptr)) {
    return false;
  }
  stream.crc32 = esp_crc32_le(
      stream.crc32, reinterpret_cast<const uint8_t *>(record),
      static_cast<uint32_t>(length));
  static const uint8_t newline = '\n';
  stream.crc32 = esp_crc32_le(stream.crc32, &newline, 1);
  ++stream.next_record_seq;
  ++stream.record_count;
  return true;
}
#endif

void emit_control_probe(const benchmark_control_probe_result_t &result)
{
  std::printf(
      "COMPARE_CPU_CONTROL schema=1 system=%s telemetry=%s"
      " start_begin_us=%" PRId64 " end_end_us=%" PRId64
      " wall0_us=%" PRIu64 " wall1_us=%" PRIu64
      " idle0_delta_us=%" PRIu32 " idle1_delta_us=%" PRIu32
      " busy0_ppm=%" PRIu32 " busy1_ppm=%" PRIu32
      " busy_mean_ppm=%" PRIu32 " fault_flags=0x%08" PRIx32 "\n",
      kSystemName,
      kTelemetryMode,
      result.start.capture_begin_us,
      result.end.capture_end_us,
      result.wall_core0_us,
      result.wall_core1_us,
      result.idle_core0_delta_us,
      result.idle_core1_delta_us,
      result.busy_core0_ppm,
      result.busy_core1_ppm,
      result.busy_mean_ppm,
      result.fault_flags);
  std::fflush(stdout);
}

void publish_message(std_msgs::msg::String &message, bool measurement)
{
#ifdef MROS2_QOS_CURRENT
  if (!publisher.publish(message) && measurement) {
    publish_failures.fetch_add(1);
  }
#else
  (void)measurement;
  publisher.publish(message);
#endif
}

void format_payload(char *buffer, char phase, uint32_t sequence, int64_t now_us)
{
  int length = std::snprintf(
      buffer,
      kPayloadBytes + 1,
      "%c:%03" PRIu32 " T:%016" PRId64 " ",
      phase,
      sequence,
      now_us);
  if (length < 0) {
    length = 0;
  }
  while (length < static_cast<int>(kPayloadBytes)) {
    buffer[length++] = 'x';
  }
  buffer[kPayloadBytes] = '\0';
}

LifespanProbe run_lifespan_probe(std_msgs::msg::String &message, char *payload)
{
  LifespanProbe probe;
  if (kPolicyFamilyCode != 2U) {
    return probe;
  }
  probe.drops_before = mros2::publisher_lifespan_drop_count();
  if (!mros2::publisher_set_transmission_held(true)) {
    return probe;
  }
  probe.hold_start_us = esp_timer_get_time();
  format_payload(payload, 'P', 0, probe.hold_start_us);
  message.data = payload;
#ifdef MROS2_QOS_CURRENT
  probe.accepted = publisher.publish(message);
#else
  publisher.publish(message);
  probe.accepted = true;
#endif
  osDelay(kReleaseDelayMs);
  probe.hold_end_us = esp_timer_get_time();
  if (!mros2::publisher_set_transmission_held(false)) {
    probe.accepted = false;
  }
  osDelay(500);
  probe.drops_after = mros2::publisher_lifespan_drop_count();
  return probe;
}

ResourceProbe run_resource_probe(std_msgs::msg::String &message, char *payload)
{
  ResourceProbe probe;
  if (kPolicyFamilyCode != 3U) {
    return probe;
  }
  const int64_t prerequisite_deadline_us =
      esp_timer_get_time() + 10000000;
  while (esp_timer_get_time() < prerequisite_deadline_us &&
         mros2::publisher_history_count() != 0U) {
    osDelay(10);
  }
  probe.attempts_before = mros2::publisher_publish_attempt_count();
  probe.accepted_before = mros2::publisher_publish_accept_count();
  probe.rejected_before = mros2::publisher_resource_reject_count();
  probe.allocation_failures_before =
      mros2::publisher_allocation_failure_count();
  const bool network_ack_suppression = kResourceAckSuppressionMs > 0U;
  if (network_ack_suppression) {
    std::printf(
        "PERF_RESOURCE_ACK_SUPPRESSION_READY schema=1 cell_id=%s"
        " duration_ms=%" PRIu32 "\n",
        kPolicyCellId, kResourceAckSuppressionMs);
    std::fflush(stdout);
    osDelay(250);
  } else if (!mros2::publisher_set_transmission_held(true)) {
    return probe;
  }
  const uint32_t attempts = kResourceMaxSamples + kResourceProbeExtra;
  for (uint32_t index = 0; index < attempts; ++index) {
    format_payload(payload, 'R', index, esp_timer_get_time());
    message.data = payload;
#ifdef MROS2_QOS_CURRENT
    (void)publisher.publish(message);
#else
    publisher.publish(message);
#endif
  }
  probe.attempts_after = mros2::publisher_publish_attempt_count();
  probe.accepted_after = mros2::publisher_publish_accept_count();
  probe.rejected_after = mros2::publisher_resource_reject_count();
  probe.allocation_failures_after =
      mros2::publisher_allocation_failure_count();
  probe.history_peak = mros2::publisher_history_count();
  if (network_ack_suppression) {
    osDelay(kResourceAckSuppressionMs + 500U);
  } else {
    (void)mros2::publisher_set_transmission_held(false);
  }

  const uint32_t expected_replies =
      counter_delta(probe.accepted_before, probe.accepted_after);
  const int64_t wait_deadline_us = esp_timer_get_time() + 5000000;
  while (esp_timer_get_time() < wait_deadline_us &&
         (policy_resource_probe_replies.load() < expected_replies ||
          mros2::publisher_history_count() != 0U)) {
    osDelay(10);
  }
  probe.history_after_release = mros2::publisher_history_count();
  return probe;
}

HistoryProbe run_history_probe(std_msgs::msg::String &message, char *payload)
{
  HistoryProbe probe;
  if (kPolicyFamilyCode != 4U) {
    return probe;
  }
  const int64_t prerequisite_deadline_us =
      esp_timer_get_time() + 10000000;
  while (esp_timer_get_time() < prerequisite_deadline_us &&
         mros2::publisher_history_count() != 0U) {
    osDelay(10);
  }
  probe.attempts_before = mros2::publisher_publish_attempt_count();
  probe.accepted_before = mros2::publisher_publish_accept_count();
  probe.rejected_before = mros2::publisher_resource_reject_count();
  probe.allocation_failures_before =
      mros2::publisher_allocation_failure_count();
  if (!mros2::publisher_set_transmission_held(true)) {
    return probe;
  }
  for (uint32_t index = 0; index < kHistoryBurstSize; ++index) {
    format_payload(payload, 'H', index, esp_timer_get_time());
    message.data = payload;
#ifdef MROS2_QOS_CURRENT
    (void)publisher.publish(message);
#else
    publisher.publish(message);
#endif
  }
  probe.attempts_after = mros2::publisher_publish_attempt_count();
  probe.accepted_after = mros2::publisher_publish_accept_count();
  probe.rejected_after = mros2::publisher_resource_reject_count();
  probe.allocation_failures_after =
      mros2::publisher_allocation_failure_count();
  probe.history_peak = mros2::publisher_history_count();
  (void)mros2::publisher_set_transmission_held(false);

  const uint32_t expected_replies =
      kHistoryBurstSize < kHistoryDepth ? kHistoryBurstSize : kHistoryDepth;
  const int64_t wait_deadline_us = esp_timer_get_time() + 3000000;
  while (esp_timer_get_time() < wait_deadline_us &&
         (policy_history_probe_replies.load() < expected_replies ||
          mros2::publisher_history_count() != 0U)) {
    osDelay(10);
  }
  probe.history_after_release = mros2::publisher_history_count();
  return probe;
}

DurabilityProbe run_durability_prejoin_probe(
    std_msgs::msg::String &message, char *payload)
{
  DurabilityProbe probe;
  if (kPolicyFamilyCode != 5U) {
    return probe;
  }
  osDelay(500);
  probe.attempts_before = mros2::publisher_publish_attempt_count();
  probe.accepted_before = mros2::publisher_publish_accept_count();
  probe.rejected_before = mros2::publisher_resource_reject_count();
  probe.allocation_failures_before =
      mros2::publisher_allocation_failure_count();
  for (uint32_t index = 0; index < kDurabilityPrejoinSamples; ++index) {
    format_payload(payload, 'D', index, esp_timer_get_time());
    message.data = payload;
#ifdef MROS2_QOS_CURRENT
    (void)publisher.publish(message);
#else
    publisher.publish(message);
#endif
  }
  osDelay(100);
  probe.attempts_after = mros2::publisher_publish_attempt_count();
  probe.accepted_after = mros2::publisher_publish_accept_count();
  probe.rejected_after = mros2::publisher_resource_reject_count();
  probe.allocation_failures_after =
      mros2::publisher_allocation_failure_count();
  probe.history_prejoin = mros2::publisher_history_count();
  std::printf(
      "PERF_DURABILITY_PREJOIN_READY schema=1 cell_id=%s durability=%s"
      " samples=%" PRIu32 " history=%" PRIu32 "\n",
      kPolicyCellId,
      kDurability,
      kDurabilityPrejoinSamples,
      probe.history_prejoin);
  std::fflush(stdout);
  return probe;
}

void finish_durability_probe(DurabilityProbe &probe)
{
  if (kPolicyFamilyCode != 5U) {
    return;
  }
  const uint32_t expected_replies =
      kDurabilityCode == 1U
          ? (kDurabilityPrejoinSamples < kDurabilityCacheDepth
                 ? kDurabilityPrejoinSamples
                 : kDurabilityCacheDepth)
          : 0U;
  const uint32_t expected_history =
      kDurabilityCode == 1U ? expected_replies : 0U;
  const int64_t wait_deadline_us = esp_timer_get_time() + 3000000;
  while (esp_timer_get_time() < wait_deadline_us &&
         (policy_durability_probe_replies.load() < expected_replies ||
          mros2::publisher_history_count() != expected_history)) {
    osDelay(10);
  }
  probe.history_after_join = mros2::publisher_history_count();
}

LivelinessProbe run_liveliness_probe(std_msgs::msg::String &message,
                                     char *payload)
{
  LivelinessProbe probe;
  if (kPolicyFamilyCode != 6U) {
    return probe;
  }

  uint32_t sequence = 0;
  int64_t next_publish_us = esp_timer_get_time();
  const int64_t baseline_end_us = next_publish_us + 300000;
  while (esp_timer_get_time() < baseline_end_us) {
    const int64_t now_us = esp_timer_get_time();
    if (now_us >= next_publish_us) {
      format_payload(payload, 'V', sequence++, now_us);
      message.data = payload;
      publish_message(message, false);
      next_publish_us = now_us + 100000;
    }
    mros2::subscriber_check_liveliness();
    osDelay(5);
  }
  if (!mros2::subscriber_writer_alive()) {
    std::printf("BENCH_SMOKE_ERROR stage=liveliness_baseline err=not_alive\n");
    std::fflush(stdout);
    vTaskSuspend(nullptr);
  }
  probe.lost_before = mros2::subscriber_liveliness_lost_count();
  probe.recovered_before = mros2::subscriber_liveliness_recovered_count();
  policy_liveliness_lost_callbacks.store(0);
  policy_liveliness_recovered_callbacks.store(0);
  first_liveliness_lost_offset_us.store(-1);
  first_liveliness_recovered_offset_us.store(-1);
  const int64_t window_start_us = esp_timer_get_time();
  policy_liveliness_window_start_us.store(window_start_us);
  std::printf(
      "PERF_LIVELINESS_OUTAGE_READY schema=1 cell_id=%s"
      " lease_ms=%" PRIu32 " outage_ms=%" PRIu32 "\n",
      kPolicyCellId, kLivelinessLeaseMs, kLivelinessOutageMs);
  std::fflush(stdout);

  const int64_t probe_end_us =
      window_start_us +
      static_cast<int64_t>(kLivelinessOutageMs + kLivelinessLeaseMs + 2500U) *
          1000;
  next_publish_us = window_start_us;
  while (esp_timer_get_time() < probe_end_us) {
    const int64_t now_us = esp_timer_get_time();
    if (now_us >= next_publish_us) {
      format_payload(payload, 'V', sequence++, now_us);
      message.data = payload;
      publish_message(message, false);
      next_publish_us = now_us + 100000;
    }
    mros2::subscriber_check_liveliness();
    osDelay(5);
  }
  mros2::subscriber_check_liveliness();
  probe.lost_after = mros2::subscriber_liveliness_lost_count();
  probe.recovered_after = mros2::subscriber_liveliness_recovered_count();
  probe.writer_alive_final = mros2::subscriber_writer_alive();
  policy_liveliness_window_start_us.store(-1);
  return probe;
}

void subscription_callback(std_msgs::msg::String *message)
{
  const char *payload = message->data.c_str();
  if (payload[0] == 'D' && payload[1] == ':') {
    unsigned int sequence = 0;
    if (std::sscanf(payload, "D:%u", &sequence) == 1 && sequence < 64U) {
      const uint64_t bit = UINT64_C(1) << sequence;
      const uint64_t previous =
          policy_durability_probe_reply_mask.fetch_or(bit);
      if ((previous & bit) == 0U) {
        policy_durability_probe_replies.fetch_add(1);
      }
    }
    return;
  }
  if (payload[0] == 'H' && payload[1] == ':') {
    unsigned int sequence = 0;
    if (std::sscanf(payload, "H:%u", &sequence) == 1 && sequence < 64U) {
      const uint64_t bit = UINT64_C(1) << sequence;
      const uint64_t previous =
          policy_history_probe_reply_mask.fetch_or(bit);
      if ((previous & bit) == 0U) {
        policy_history_probe_replies.fetch_add(1);
      }
    }
    return;
  }
  if (payload[0] == 'R' && payload[1] == ':') {
    policy_resource_probe_replies.fetch_add(1);
    return;
  }
  if (payload[0] == 'P' && payload[1] == ':') {
    policy_lifespan_probe_replies.fetch_add(1);
    return;
  }
  if (payload[0] == 'W' && payload[1] == ':') {
    warmup_reply_count.fetch_add(1);
    const int64_t candidate_ms = (esp_timer_get_time() - boot_us) / 1000;
    int64_t expected = -1;
    if (ready_ms.compare_exchange_strong(expected, candidate_ms)) {
      std::printf("COMPARE_READY system=%s ready_ms=%" PRId64 "\n",
                  kSystemName, candidate_ms);
    }
    return;
  }
  if (payload[0] == 'Q' && payload[1] == ':') {
    prime_reply_count.fetch_add(1);
    return;
  }

  unsigned int sequence = 0;
  long long sent_us = 0;
  if (!accepting_measurements) {
    return;
  }
  if (std::sscanf(payload, "M:%u T:%lld", &sequence, &sent_us) != 2 ||
      sequence >= kMeasurementMessages) {
    ++malformed_count;
    return;
  }
  const int64_t received_us = esp_timer_get_time();
  const int64_t rtt_us = received_us - sent_us;
  if (rtt_us <= 0 || rtt_us >= 10000000) {
    ++malformed_count;
    return;
  }

  const uint32_t value = static_cast<uint32_t>(rtt_us);
  xSemaphoreTake(stats_mutex, portMAX_DELAY);
  if (!accepting_measurements) {
    xSemaphoreGive(stats_mutex);
    return;
  }
  if (received[sequence]) {
    ++duplicate_count;
    xSemaphoreGive(stats_mutex);
    return;
  }
  received[sequence] = true;
  rtt_by_sequence[sequence] = value;
  arrival_rank_by_sequence[sequence] = rx_count.load();
  const int64_t epoch_us = measurement_epoch_us.load();
  rx_offset_by_sequence[sequence] = static_cast<uint32_t>(
      epoch_us < 0 ? 0 : received_us - epoch_us);
  if (have_sequence && sequence < highest_sequence_seen) {
    ++arrival_inversions;
  } else {
    highest_sequence_seen = sequence;
    have_sequence = true;
  }
  rtt_sum_us += value;
  rtt_sum_sq_us2 += static_cast<uint64_t>(value) * value;
  if (value < rtt_min_us) {
    rtt_min_us = value;
  }
  if (value > rtt_max_us) {
    rtt_max_us = value;
  }
  rx_count.fetch_add(1);
  xSemaphoreGive(stats_mutex);
}

#ifdef MATCHED_BENCH_TELEMETRY_ENABLED
bool start_telemetry(benchmark_telemetry_stream_state_t &stream)
{
  char record[512] = {};
  std::snprintf(
      record,
      sizeof(record),
      "BENCH_CONFIG schema=%u run_token=%s record_seq=%" PRIu32
      " system=%s qos=%s payload_bytes=%" PRIu32
      " rate_hz=%" PRIu32 " target_tx=%" PRIu32
      " impairment=%s window_ms=%u period_ms=%u interval_count=%u"
      " marker_gpio=%d",
      BENCHMARK_TELEMETRY_SCHEMA_VERSION,
      kRunToken,
      stream.next_record_seq,
      kSystemName,
      kQosName,
      kPayloadBytes,
      1000U / kPublishPeriodMs,
      kMeasurementMessages,
      kImpairment,
      BENCHMARK_TELEMETRY_WINDOW_MS,
      BENCHMARK_TELEMETRY_PERIOD_MS,
      BENCHMARK_TELEMETRY_INTERVAL_COUNT,
      kMarkerGpio);
  if (!emit_owned_record(stream, record)) {
    return false;
  }
  esp_err_t status = benchmark_telemetry_start();
  if (status == ESP_OK) {
    status = benchmark_telemetry_wait_started(1000);
  }
  if (status != ESP_OK) {
    std::printf("BENCH_SMOKE_ERROR stage=start err=0x%08" PRIx32 "\n",
                static_cast<uint32_t>(status));
    return false;
  }
  return true;
}

void finish_telemetry(benchmark_telemetry_stream_state_t &stream,
                      uint32_t samples,
                      uint64_t average,
                      uint32_t min_us,
                      uint32_t max_us,
                      uint64_t sum_us,
                      uint64_t sum_sq_us2,
                      const DeliveryShape &shape,
                      uint32_t inversions)
{
  esp_err_t status = benchmark_telemetry_emit_records(
      kRunToken, &stream, uart_sink, nullptr);
  const benchmark_telemetry_result_t *result = benchmark_telemetry_result();
  if (status != ESP_OK || result == nullptr) {
    std::printf("BENCH_SMOKE_ERROR stage=dump err=0x%08" PRIx32 "\n",
                static_cast<uint32_t>(status));
    return;
  }

  std::printf(
      "COMPARE_FINAL system=%s tx=%" PRIu32 " rx=%" PRIu32
      " samples=%" PRIu32 " min_us=%" PRIu32 " avg_us=%" PRIu64
      " max_us=%" PRIu32 " ready_ms=%" PRId64
      " payload_bytes=%" PRIu32 " period_ms=%" PRIu32
      " grace_ms=%" PRIu32 " telemetry=%s"
      " missing=%" PRIu32 " missing_runs=%" PRIu32
      " max_missing_run=%" PRIu32 " arrival_inversions=%" PRIu32
      " rtt_sum_us=%" PRIu64 " rtt_sum_sq_us2=%" PRIu64 "\n",
      kSystemName,
      kMeasurementMessages,
      samples,
      samples,
      samples == 0 ? 0 : min_us,
      average,
      max_us,
      ready_ms.load(),
      kPayloadBytes,
      kPublishPeriodMs,
      kReplyGraceMs,
      kTelemetryMode,
      shape.missing,
      shape.missing_runs,
      shape.max_missing_run,
      inversions,
      sum_us,
      sum_sq_us2);

  const char *completion =
      result->fault_flags == 0 && result->missed_interval_count == 0
          ? "complete"
          : "instrumentation_fault";
  char record[512] = {};
  std::snprintf(
      record,
      sizeof(record),
      "BENCH_FINAL schema=%u run_token=%s record_seq=%" PRIu32
      " completion=%s samples=%u tasks=%" PRIu32
      " missed_intervals=%" PRIu32 " fault_flags=0x%08" PRIx32
      " alloc_failures=%" PRIu32 " attempted_tx=%" PRIu32
      " publish_failures=%" PRIu32 " rx=%" PRIu32
      " duplicates=%" PRIu32
      " malformed=%" PRIu32 " rtt_samples=%" PRIu32
      " missing=%" PRIu32 " missing_runs=%" PRIu32
      " max_missing_run=%" PRIu32 " arrival_inversions=%" PRIu32
      " rtt_sum_us=%" PRIu64 " rtt_sum_sq_us2=%" PRIu64,
      BENCHMARK_TELEMETRY_SCHEMA_VERSION,
      kRunToken,
      stream.next_record_seq,
      completion,
      BENCHMARK_TELEMETRY_INTERVAL_COUNT,
      result->task_count,
      result->missed_interval_count,
      result->fault_flags,
      result->allocation_failure_count,
      kMeasurementMessages,
      publish_failures.load(),
      samples,
      duplicate_count,
      malformed_count,
      samples,
      shape.missing,
      shape.missing_runs,
      shape.max_missing_run,
      inversions,
      sum_us,
      sum_sq_us2);
  if (!emit_owned_record(stream, record)) {
    return;
  }
  std::printf(
      "BENCH_DUMP_END schema=%u run_token=%s record_seq=%" PRIu32
      " record_count=%" PRIu32 " crc32=0x%08" PRIx32 "\n",
      BENCHMARK_TELEMETRY_SCHEMA_VERSION,
      kRunToken,
      stream.next_record_seq,
      stream.record_count,
      stream.crc32);
  std::fflush(stdout);
}
#endif

void publisher_task(void *)
{
  char *const payload = publish_payload.data();
  std_msgs::msg::String message;
  policy_durability_probe_replies.store(0);
  policy_durability_probe_reply_mask.store(0);
  DurabilityProbe durability_probe =
      run_durability_prejoin_probe(message, payload);
  if (kPolicyFamilyCode == 5U) {
    const int64_t match_deadline_us = esp_timer_get_time() + 30000000;
    while (esp_timer_get_time() < match_deadline_us &&
           (!mros2::publisher_has_matched_reader() ||
            !mros2::subscriber_matched())) {
      osDelay(10);
    }
    if (!mros2::publisher_has_matched_reader() ||
        !mros2::subscriber_matched()) {
      std::printf(
          "BENCH_SMOKE_ERROR stage=durability_bidirectional_match"
          " err=timeout\n");
      vTaskSuspend(nullptr);
    }
    std::printf(
        "PERF_DURABILITY_BIDIRECTIONAL_READY schema=1 cell_id=%s\n",
        kPolicyCellId);
    std::fflush(stdout);
    // The gate sample shares the application topic with the retained samples.
    // Give the matched reader time to drain the N replay callbacks before the
    // (N + 1)th live gate sample arrives; otherwise a reader configured with
    // depth N can legitimately evict the oldest retained sample before its
    // executor observes it.  This is probe synchronization only and does not
    // change either endpoint's History depth.
    osDelay(300);
    format_payload(payload, 'G', 0, esp_timer_get_time());
    message.data = payload;
    publish_message(message, false);
    osDelay(100);
  }
  uint32_t warmup_sequence = 0;
  int64_t next_warmup_us = esp_timer_get_time();
  while (ready_ms.load() < 0) {
    const int64_t now_us = esp_timer_get_time();
    if (now_us >= next_warmup_us) {
      format_payload(payload, 'W', warmup_sequence++, now_us);
      message.data = payload;
      publish_message(message, false);
      next_warmup_us =
          now_us + static_cast<int64_t>(kWarmupPeriodMs) * 1000;
    }
    osDelay(20);
  }

  if (kPolicyFamilyCode != 6U) {
    osDelay(kReadySettleMs);
  }
  finish_durability_probe(durability_probe);
  const LivelinessProbe liveliness_probe =
      run_liveliness_probe(message, payload);
  policy_lifespan_probe_replies.store(0);
  const LifespanProbe lifespan_probe = run_lifespan_probe(message, payload);
  policy_resource_probe_replies.store(0);
  const ResourceProbe resource_probe = run_resource_probe(message, payload);
  policy_history_probe_replies.store(0);
  policy_history_probe_reply_mask.store(0);
  const HistoryProbe history_probe = run_history_probe(message, payload);
  const uint32_t prime_before = prime_reply_count.load();
  format_payload(payload, 'Q', warmup_sequence++, esp_timer_get_time());
  message.data = payload;
  publish_message(message, false);
  const int64_t prime_deadline_us = esp_timer_get_time() + 2000000;
  while (prime_reply_count.load() == prime_before &&
         esp_timer_get_time() < prime_deadline_us) {
    osDelay(5);
  }
  if (prime_reply_count.load() == prime_before) {
    std::printf(
        "COMPARE_READER_DIAG system=%s received=%" PRIu32
        " accepted_before_match=%" PRIu32 " out_of_order_drops=%" PRIu32
        " unmatched_writer_drops=%" PRIu32
        " unsupported_payload_drops=%" PRIu32 " gaps=%" PRIu32
        " control_send_failures=%" PRIu32 " warmup_replies=%" PRIu32
        " prime_replies=%" PRIu32 "\n",
        kSystemName, mros2::subscriber_received_count(),
        mros2::subscriber_accepted_before_match_count(),
        mros2::subscriber_out_of_order_drop_count(),
        mros2::subscriber_unmatched_writer_drop_count(),
        mros2::subscriber_unsupported_payload_drop_count(),
        mros2::subscriber_gap_received_count(),
        mros2::subscriber_control_send_failure_count(),
        warmup_reply_count.load(), prime_reply_count.load());
    std::printf("BENCH_SMOKE_ERROR stage=measurement_prime err=timeout\n");
    std::fflush(stdout);
    vTaskSuspend(nullptr);
  }
  std::printf("COMPARE_MEASUREMENT_PRIME system=%s status=PASS\n",
              kSystemName);
  std::fflush(stdout);
  osDelay(100);
  benchmark_control_probe_state_t control_probe = {};
  benchmark_control_probe_result_t control_result = {};
  esp_err_t control_status = benchmark_control_probe_init(&control_probe);
  if (control_status != ESP_OK) {
    std::printf("BENCH_SMOKE_ERROR stage=control_init err=0x%08" PRIx32 "\n",
                static_cast<uint32_t>(control_status));
    vTaskSuspend(nullptr);
  }
  // The canonical telemetry stream requires BENCH_CONFIG to be the final UART
  // record before BENCH_WINDOW_START.  Emit the human-readable phase marker
  // first, then start the telemetry-only window.
  std::printf(
      "COMPARE_MEASUREMENT_START schema=1 system=%s target_tx=%" PRIu32
      " period_ms=%" PRIu32 "\n",
      kSystemName, kMeasurementMessages, kPublishPeriodMs);
  std::fflush(stdout);
  osDelay(20);
#ifdef MATCHED_BENCH_TELEMETRY_ENABLED
  benchmark_telemetry_stream_state_t stream = {};
  if (!start_telemetry(stream)) {
    vTaskSuspend(nullptr);
  }
#endif

  const uint32_t deadline_count_before =
      mros2::subscriber_deadline_missed_count();
  policy_deadline_callbacks.store(0);
  first_deadline_callback_offset_us.store(-1);
  control_status = benchmark_control_probe_start(&control_probe);
  if (control_status != ESP_OK) {
    std::printf("BENCH_SMOKE_ERROR stage=control_start err=0x%08" PRIx32 "\n",
                static_cast<uint32_t>(control_status));
    vTaskSuspend(nullptr);
  }
  const int64_t measurement_start_us = esp_timer_get_time();
  measurement_epoch_us.store(measurement_start_us);
  policy_window_start_us.store(measurement_start_us);
  accepting_measurements = true;
  int64_t next_publish_us = measurement_start_us;
  for (uint32_t sequence = 0; sequence < kMeasurementMessages; ++sequence) {
    while (esp_timer_get_time() < next_publish_us) {
      osDelay(1);
    }
    const int64_t sent_us = esp_timer_get_time();
    tx_offset_by_sequence[sequence] =
        static_cast<uint32_t>(sent_us - measurement_start_us);
    format_payload(payload, 'M', sequence, sent_us);
    message.data = payload;
    publish_message(message, true);
    next_publish_us += static_cast<int64_t>(kPublishPeriodMs) * 1000;
  }

#ifdef MATCHED_BENCH_TELEMETRY_ENABLED
  esp_err_t status = benchmark_telemetry_wait_finished(
      BENCHMARK_TELEMETRY_WINDOW_MS + 2000);
  if (status != ESP_OK) {
    std::printf("BENCH_SMOKE_ERROR stage=window err=0x%08" PRIx32 "\n",
                static_cast<uint32_t>(status));
    vTaskSuspend(nullptr);
  }
#else
  const int64_t measurement_end_us =
      measurement_start_us + static_cast<int64_t>(kMeasurementWindowMs) * 1000;
  while (esp_timer_get_time() < measurement_end_us) {
    osDelay(1);
  }
#endif
  policy_window_start_us.store(-1);
  const uint32_t deadline_count_after =
      mros2::subscriber_deadline_missed_count();
  control_status =
      benchmark_control_probe_finish(&control_probe, &control_result);
  if (control_status != ESP_OK) {
    std::printf("BENCH_SMOKE_ERROR stage=control_finish err=0x%08" PRIx32 "\n",
                static_cast<uint32_t>(control_status));
    vTaskSuspend(nullptr);
  }

  const int64_t deadline_us =
      esp_timer_get_time() + static_cast<int64_t>(kReplyGraceMs) * 1000;
  while (rx_count.load() < kMeasurementMessages &&
         esp_timer_get_time() < deadline_us) {
    osDelay(20);
  }

  xSemaphoreTake(stats_mutex, portMAX_DELAY);
  accepting_measurements = false;
  const uint32_t samples = rx_count.load();
  const uint64_t sum_us = rtt_sum_us;
  const uint64_t sum_sq_us2 = rtt_sum_sq_us2;
  const uint32_t min_us = rtt_min_us;
  const uint32_t max_us = rtt_max_us;
  const DeliveryShape shape = summarize_delivery_shape();
  const uint32_t inversions = arrival_inversions;
  xSemaphoreGive(stats_mutex);
  const uint64_t average = samples == 0 ? 0 : sum_us / samples;
#ifdef MATCHED_BENCH_TELEMETRY_ENABLED
  finish_telemetry(stream, samples, average, min_us, max_us, sum_us,
                   sum_sq_us2, shape, inversions);
  emit_rtt_samples();
  emit_missing_sequences();
  emit_control_probe(control_result);
  emit_policy_final(deadline_count_before, deadline_count_after,
                    lifespan_probe, resource_probe, history_probe,
                    durability_probe, liveliness_probe);
#else
  emit_rtt_samples();
  emit_missing_sequences();
  emit_control_probe(control_result);
  std::printf(
      "COMPARE_FINAL system=%s tx=%" PRIu32 " rx=%" PRIu32
      " samples=%" PRIu32 " min_us=%" PRIu32 " avg_us=%" PRIu64
      " max_us=%" PRIu32 " ready_ms=%" PRId64
      " payload_bytes=%" PRIu32 " period_ms=%" PRIu32
      " grace_ms=%" PRIu32 " telemetry=off publish_failures=%" PRIu32
      " duplicates=%" PRIu32 " malformed=%" PRIu32
      " missing=%" PRIu32 " missing_runs=%" PRIu32
      " max_missing_run=%" PRIu32 " arrival_inversions=%" PRIu32
      " rtt_sum_us=%" PRIu64 " rtt_sum_sq_us2=%" PRIu64 "\n",
      kSystemName,
      kMeasurementMessages,
      samples,
      samples,
      samples == 0 ? 0 : min_us,
      average,
      max_us,
      ready_ms.load(),
      kPayloadBytes,
      kPublishPeriodMs,
      kReplyGraceMs,
      publish_failures.load(),
      duplicate_count,
      malformed_count,
      shape.missing,
      shape.missing_runs,
      shape.max_missing_run,
      inversions,
      sum_us,
      sum_sq_us2);
  emit_policy_final(deadline_count_before, deadline_count_after,
                    lifespan_probe, resource_probe, history_probe,
                    durability_probe, liveliness_probe);
  std::fflush(stdout);
#endif

  while (true) {
    osDelay(1000);
  }
}

}  // namespace

extern "C" void app_main(void)
{
  boot_us = esp_timer_get_time();
#ifdef MATCHED_BENCH_TELEMETRY_ENABLED
  const benchmark_telemetry_config_t telemetry_config = {
      .marker_gpio = kMarkerGpio,
      .telemetry_task_core = 1,
      .telemetry_task_priority = configMAX_PRIORITIES - 1,
  };
  esp_err_t status = benchmark_telemetry_init(&telemetry_config);
  if (status != ESP_OK) {
    std::printf("BENCH_SMOKE_ERROR stage=init err=0x%08" PRIx32 "\n",
                static_cast<uint32_t>(status));
    return;
  }
#endif

  stats_mutex = xSemaphoreCreateMutex();
  if (stats_mutex == nullptr) {
    std::printf("BENCH_SMOKE_ERROR stage=mutex err=no_mem\n");
    return;
  }
  if (!mros2_platform_network_connect()) {
    std::printf("BENCH_SMOKE_ERROR stage=network err=connect\n");
    return;
  }
  esp_log_level_set("*", ESP_LOG_NONE);

  mros2::init(0, nullptr);
  mros2::Node node = mros2::Node::create_node(
#ifdef MROS2_QOS_CURRENT
      "telemetry_compare_mros2qos"
#else
      "telemetry_compare_upstream"
#endif
  );
#ifdef MROS2_QOS_CURRENT
  mros2::QoSProfile endpoint_qos;
#ifdef MATCHED_BENCH_RELIABLE
  endpoint_qos.reliability = rtps::ReliabilityKind_t::RELIABLE;
#else
  endpoint_qos.reliability = rtps::ReliabilityKind_t::BEST_EFFORT;
#endif
  endpoint_qos.durability = rtps::DurabilityKind_t::VOLATILE;
  endpoint_qos.history = mros2::HistoryKind::KEEP_LAST;
  endpoint_qos.depth = kMatchedHistoryDepth;
#ifdef MATCHED_BENCH_RDH_ENABLED
  endpoint_qos.durability = rtps::DurabilityKind_t::TRANSIENT_LOCAL;
  endpoint_qos.depth = kRdhDepth;
#endif
  mros2::QoSProfile publisher_qos = endpoint_qos;
  mros2::QoSProfile subscriber_qos = endpoint_qos;
  if (kDeadlineMs != 0U) {
    subscriber_qos.deadline = mros2::Duration::from_ms(kDeadlineMs);
  }
  if (kLifespanMs != 0U) {
    publisher_qos.lifespan = mros2::Duration::from_ms(kLifespanMs);
  }
  if (kPolicyFamilyCode == 3U) {
    publisher_qos.history = mros2::HistoryKind::KEEP_ALL;
    publisher_qos.depth = 1;
    publisher_qos.max_samples = kResourceMaxSamples;
  }
  if (kPolicyFamilyCode == 4U) {
    publisher_qos.history = mros2::HistoryKind::KEEP_LAST;
    publisher_qos.depth = kHistoryDepth;
  }
  if (kPolicyFamilyCode == 5U) {
    const rtps::DurabilityKind_t probe_durability =
        kDurabilityCode == 1U
            ? rtps::DurabilityKind_t::TRANSIENT_LOCAL
            : rtps::DurabilityKind_t::VOLATILE;
    publisher_qos.durability = probe_durability;
    publisher_qos.history = mros2::HistoryKind::KEEP_LAST;
    publisher_qos.depth = kDurabilityCacheDepth;
    // The subscriber must carry the cell's Durability too. The
    // MATCHED_BENCH_RDH_ENABLED block above sets BOTH endpoints Transient
    // Local, and this block used to override only the publisher. For the
    // Transient Local cells that is invisible - the override reasserts what the
    // endpoint already was. For a Volatile cell it left the board offering a
    // Volatile writer while still requesting a Transient Local reader, and no
    // host configuration can satisfy both at once: a Transient Local host fails
    // to match the writer, a Volatile host fails to match the reader, and
    // publisher_task's bidirectional gate times out either way. That is why the
    // Volatile late-join control could not be run at all.
    //
    // Depth is deliberately left alone: the subscriber's depth governs how many
    // host replies it buffers, which is not the quantity under test.
    subscriber_qos.durability = probe_durability;
  }
  if (kPolicyFamilyCode == 6U) {
    subscriber_qos.liveliness = mros2::LivelinessKind::AUTOMATIC;
    subscriber_qos.liveliness_lease_duration =
        mros2::Duration::from_ms(kLivelinessLeaseMs);
  }
  publisher = node.create_publisher<std_msgs::msg::String>(
      "system_compare", publisher_qos);
  subscriber = node.create_subscription<std_msgs::msg::String>(
      "system_compare_reply", subscriber_qos, subscription_callback);
  if (kPolicyFamilyCode == 1U &&
      !mros2::register_subscriber_deadline_missed_callback(
          deadline_missed_callback, nullptr)) {
    std::printf("BENCH_SMOKE_ERROR stage=deadline_callback err=register\n");
    return;
  }
  if (kPolicyFamilyCode == 6U &&
      (!mros2::register_subscriber_liveliness_lost_callback(
           liveliness_lost_callback, nullptr) ||
       !mros2::register_subscriber_liveliness_recovered_callback(
           liveliness_recovered_callback, nullptr))) {
    std::printf("BENCH_SMOKE_ERROR stage=liveliness_callback err=register\n");
    return;
  }
#else
  publisher = node.create_publisher<std_msgs::msg::String>(
      "system_compare", 10);
  subscriber = node.create_subscription<std_msgs::msg::String>(
      "system_compare_reply", 10, subscription_callback);
#endif

  std::printf(
      "COMPARE_CONFIG system=%s qos=%s payload_bytes=%" PRIu32
      " messages=%" PRIu32 " period_ms=%" PRIu32
      " settle_ms=%" PRIu32 " grace_ms=%" PRIu32
      " telemetry=%s endpoint_durability=%s endpoint_history=%s"
      " endpoint_history_depth=%" PRIu32
      " family=%s cell_id=%s deadline_ms=%" PRIu32
      " lifespan_ms=%" PRIu32 " release_delay_ms=%" PRIu32
      " resource_max_samples=%" PRIu32
      " resource_probe_extra=%" PRIu32
      " resource_ack_suppression_ms=%" PRIu32
      " history_depth=%" PRIu32
      " history_burst_size=%" PRIu32
      " durability=%s durability_cache_depth=%" PRIu32
      " durability_prejoin_samples=%" PRIu32
      " rdh_enabled=%u rdh_depth=%" PRIu32
      " rdh_reliability=%s rdh_durability=%s rdh_history=%s"
      " liveliness_lease_ms=%" PRIu32
      " liveliness_outage_ms=%" PRIu32 "\n",
      kSystemName,
      kQosName,
      kPayloadBytes,
      kMeasurementMessages,
      kPublishPeriodMs,
      kReadySettleMs,
      kReplyGraceMs,
      kTelemetryMode,
#ifdef MATCHED_BENCH_RDH_ENABLED
      // Report what the endpoints were actually given, not what the RDH block
      // defaulted to. The durability family overrides both endpoints to the
      // cell's own Durability, so a Volatile control configures VOLATILE while
      // this line used to keep announcing TRANSIENT_LOCAL - a manifest that
      // disagrees with the hardware is worse than a failing gate.
      (kPolicyFamilyCode == 5U && kDurabilityCode != 1U) ? "VOLATILE"
                                                         : "TRANSIENT_LOCAL",
      "KEEP_LAST",
      kRdhDepth,
#else
      "VOLATILE",
      "KEEP_LAST",
      kMatchedHistoryDepth,
#endif
      kPolicyFamily,
      kPolicyCellId,
      kDeadlineMs,
      kLifespanMs,
      kReleaseDelayMs,
      kResourceMaxSamples,
      kResourceProbeExtra,
      kResourceAckSuppressionMs,
      kHistoryDepth,
      kHistoryBurstSize,
      kDurability,
      kDurabilityCacheDepth,
      kDurabilityPrejoinSamples,
#ifdef MATCHED_BENCH_RDH_ENABLED
      1U,
#else
      0U,
#endif
      kRdhDepth,
#ifdef MATCHED_BENCH_RDH_ENABLED
      "RELIABLE",
      "TRANSIENT_LOCAL",
      "KEEP_LAST",
#else
      "NONE",
      "NONE",
      "NONE",
#endif
      kLivelinessLeaseMs,
      kLivelinessOutageMs);
  std::printf("COMPARE_RESOURCE system=%s free_heap_bytes=%lu\n",
              kSystemName,
              static_cast<unsigned long>(esp_get_free_heap_size()));

  osThreadAttr_t attributes{};
  attributes.name = "compare_pub";
  attributes.stack_size = 4096;
  attributes.priority = osPriorityNormal;
  if (osThreadNew(publisher_task, nullptr, &attributes) == nullptr) {
    std::printf("BENCH_SMOKE_ERROR stage=publisher_task err=no_mem\n");
    return;
  }
  mros2::spin();
}
