/* Instrumented matched-workload smoke for the micro-ROS XRCE-DDS baseline. */

#include <stdbool.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

#include "esp_log.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "benchmark_control_probe.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include <rcl/error_handling.h>
#include <rcl/rcl.h>
#include <rclc/executor.h>
#include <rclc/rclc.h>
#include <std_msgs/msg/string.h>
#include <uros_network_interfaces.h>

#ifdef MATCHED_BENCH_TELEMETRY_ENABLED
#include "benchmark_telemetry.h"
#include "esp_crc.h"
#endif

#ifdef CONFIG_MICRO_ROS_ESP_XRCE_DDS_MIDDLEWARE
#include <rmw_microros/rmw_microros.h>
#endif

#define RCCHECK(fn) do { \
  rcl_ret_t rc_ = (fn); \
  if (rc_ != RCL_RET_OK) { \
    printf("BENCH_SMOKE_ERROR stage=rcl line=%d rc=%d\n", __LINE__, (int)rc_); \
    vTaskDelete(NULL); \
  } \
} while (0)

#ifndef MATCHED_BENCH_PAYLOAD_BYTES
#define MATCHED_BENCH_PAYLOAD_BYTES 64U
#endif
#ifndef MATCHED_BENCH_PUBLISH_RATE_HZ
#define MATCHED_BENCH_PUBLISH_RATE_HZ 10U
#endif
#ifndef MATCHED_BENCH_WINDOW_MS
#define MATCHED_BENCH_WINDOW_MS 20000U
#endif
#ifndef MATCHED_BENCH_IMPAIRMENT
#define MATCHED_BENCH_IMPAIRMENT clean
#endif

#define PAYLOAD_BYTES ((uint32_t)MATCHED_BENCH_PAYLOAD_BYTES)
#define PAYLOAD_CAPACITY (PAYLOAD_BYTES + 1U)
#define PUBLISH_RATE_HZ ((uint32_t)MATCHED_BENCH_PUBLISH_RATE_HZ)
#define MEASUREMENT_WINDOW_MS ((uint32_t)MATCHED_BENCH_WINDOW_MS)
#define MATCHED_BENCH_STRINGIFY_INNER(value) #value
#define MATCHED_BENCH_STRINGIFY(value) MATCHED_BENCH_STRINGIFY_INNER(value)
#define IMPAIRMENT_PROFILE MATCHED_BENCH_STRINGIFY(MATCHED_BENCH_IMPAIRMENT)
#define MEASUREMENT_MESSAGES \
  ((PUBLISH_RATE_HZ * MEASUREMENT_WINDOW_MS) / 1000U)
#define PUBLISH_PERIOD_MS (1000U / PUBLISH_RATE_HZ)
#define WARMUP_PERIOD_MS 500U
#define READY_SETTLE_MS 1000U
#define REPLY_GRACE_MS 5000U
#define MARKER_GPIO 4

#ifdef MATCHED_BENCH_RELIABLE
static const char QOS_NAME[] = "RELIABLE";
#else
static const char QOS_NAME[] = "BEST_EFFORT";
#endif

_Static_assert(MATCHED_BENCH_PAYLOAD_BYTES >= 32U &&
               MATCHED_BENCH_PAYLOAD_BYTES <= 2048U,
               "payload size is outside the pilot envelope");
_Static_assert(MATCHED_BENCH_PUBLISH_RATE_HZ > 0U &&
               1000U % MATCHED_BENCH_PUBLISH_RATE_HZ == 0U,
               "publish rate must divide 1000 Hz");
_Static_assert(MATCHED_BENCH_WINDOW_MS == 20000U,
               "telemetry workload window must remain 20 seconds");
_Static_assert((MATCHED_BENCH_PUBLISH_RATE_HZ * MATCHED_BENCH_WINDOW_MS) %
                   1000U == 0U,
               "window must contain an integral message count");

#ifdef MATCHED_BENCH_TELEMETRY_ENABLED
static const char RUN_TOKEN[] = "microros-telemetry-smoke-001";
static const char TELEMETRY_MODE[] = "on";
#else
static const char TELEMETRY_MODE[] = "off";
#endif
static rcl_publisher_t publisher;
static rcl_subscription_t subscriber;
static std_msgs__msg__String pub_msg;
static std_msgs__msg__String sub_msg;
static char pub_buffer[PAYLOAD_CAPACITY];
static char sub_buffer[PAYLOAD_CAPACITY];
static char parse_buffer[PAYLOAD_CAPACITY];
static bool received[MEASUREMENT_MESSAGES];
static bool accepting_measurements = true;
static int64_t boot_us;
static int64_t ready_ms = -1;
static uint32_t attempted_tx;
static uint32_t rx_count;
static uint32_t duplicate_count;
static uint32_t malformed_count;
static uint32_t publish_failures;
static uint64_t rtt_sum_us;
static uint64_t rtt_sum_sq_us2;
static uint32_t rtt_min_us = UINT32_MAX;
static uint32_t rtt_max_us;
static uint32_t arrival_inversions;
static uint32_t highest_sequence_seen;
static bool have_sequence;

typedef struct {
  uint32_t missing;
  uint32_t missing_runs;
  uint32_t max_missing_run;
} delivery_shape_t;

static delivery_shape_t summarize_delivery_shape(uint32_t expected)
{
  delivery_shape_t shape = {0};
  uint32_t current_run = 0;
  for (uint32_t sequence = 0; sequence < expected; ++sequence) {
    if (!received[sequence]) {
      shape.missing++;
      current_run++;
      if (current_run > shape.max_missing_run) {
        shape.max_missing_run = current_run;
      }
    } else if (current_run != 0) {
      shape.missing_runs++;
      current_run = 0;
    }
  }
  if (current_run != 0) {
    shape.missing_runs++;
  }
  return shape;
}

#ifdef MATCHED_BENCH_TELEMETRY_ENABLED
static bool uart_sink(const char *record, size_t length, void *context)
{
  (void)context;
  bool written = fwrite(record, 1, length, stdout) == length &&
                 fputc('\n', stdout) != EOF;
  fflush(stdout);
  vTaskDelay(1);
  return written;
}

static bool emit_owned_record(benchmark_telemetry_stream_state_t *stream,
                              const char *record)
{
  size_t length = strlen(record);
  if (!uart_sink(record, length, NULL)) {
    return false;
  }
  stream->crc32 = esp_crc32_le(
      stream->crc32, (const uint8_t *)record, (uint32_t)length);
  static const uint8_t newline = '\n';
  stream->crc32 = esp_crc32_le(stream->crc32, &newline, 1);
  stream->next_record_seq++;
  stream->record_count++;
  return true;
}
#endif

static void emit_control_probe(
    const benchmark_control_probe_result_t *result)
{
  printf(
      "COMPARE_CPU_CONTROL schema=1 system=microros telemetry=%s"
      " start_begin_us=%" PRId64 " end_end_us=%" PRId64
      " wall0_us=%" PRIu64 " wall1_us=%" PRIu64
      " idle0_delta_us=%" PRIu32 " idle1_delta_us=%" PRIu32
      " busy0_ppm=%" PRIu32 " busy1_ppm=%" PRIu32
      " busy_mean_ppm=%" PRIu32 " fault_flags=0x%08" PRIx32 "\n",
      TELEMETRY_MODE,
      result->start.capture_begin_us,
      result->end.capture_end_us,
      result->wall_core0_us,
      result->wall_core1_us,
      result->idle_core0_delta_us,
      result->idle_core1_delta_us,
      result->busy_core0_ppm,
      result->busy_core1_ppm,
      result->busy_mean_ppm,
      result->fault_flags);
  fflush(stdout);
}

static void format_payload(char phase, uint32_t sequence, int64_t now_us)
{
  int length = snprintf(
      pub_buffer,
      PAYLOAD_CAPACITY,
      "%c:%03" PRIu32 " T:%016lld ",
      phase,
      sequence,
      (long long)now_us);
  if (length < 0) {
    length = 0;
  }
  while (length < (int)PAYLOAD_BYTES) {
    pub_buffer[length++] = 'x';
  }
  pub_buffer[PAYLOAD_BYTES] = '\0';
  pub_msg.data.size = PAYLOAD_BYTES;
}

static void publish_payload(char phase, uint32_t sequence)
{
  format_payload(phase, sequence, esp_timer_get_time());
  if (phase == 'M') {
    attempted_tx++;
  }
  rcl_ret_t rc = rcl_publish(&publisher, &pub_msg, NULL);
  if (rc != RCL_RET_OK) {
    publish_failures++;
    if (phase != 'M') {
      printf("COMPARE_PUBLISH_ERROR system=microros phase=%c seq=%" PRIu32
             " rc=%d\n", phase, sequence, (int)rc);
    }
  }
}

static void subscription_callback(const void *message_input)
{
  const std_msgs__msg__String *message =
      (const std_msgs__msg__String *)message_input;
  size_t length = message->data.size;
  if (length > PAYLOAD_BYTES) {
    malformed_count++;
    length = PAYLOAD_BYTES;
  }
  memcpy(parse_buffer, message->data.data, length);
  parse_buffer[length] = '\0';

  if (parse_buffer[0] == 'W' && parse_buffer[1] == ':') {
    if (ready_ms < 0) {
      ready_ms = (esp_timer_get_time() - boot_us) / 1000;
      printf("COMPARE_READY system=microros ready_ms=%lld\n",
             (long long)ready_ms);
    }
    return;
  }

  unsigned int sequence = 0;
  long long sent_us = 0;
  if (!accepting_measurements) {
    return;
  }
  if (sscanf(parse_buffer, "M:%u T:%lld", &sequence, &sent_us) != 2 ||
      sequence >= MEASUREMENT_MESSAGES) {
    malformed_count++;
    return;
  }
  if (received[sequence]) {
    duplicate_count++;
    return;
  }
  int64_t rtt_us = esp_timer_get_time() - sent_us;
  if (rtt_us <= 0 || rtt_us >= 10000000) {
    malformed_count++;
    return;
  }

  received[sequence] = true;
  if (have_sequence && sequence < highest_sequence_seen) {
    arrival_inversions++;
  } else {
    highest_sequence_seen = sequence;
    have_sequence = true;
  }
  rx_count++;
  uint32_t value = (uint32_t)rtt_us;
  rtt_sum_us += value;
  rtt_sum_sq_us2 += (uint64_t)value * value;
  if (value < rtt_min_us) {
    rtt_min_us = value;
  }
  if (value > rtt_max_us) {
    rtt_max_us = value;
  }
}

static void spin_until(rclc_executor_t *executor, int64_t deadline_us)
{
  while (esp_timer_get_time() < deadline_us) {
    rclc_executor_spin_some(executor, RCL_MS_TO_NS(20));
    usleep(2000);
  }
}

#ifdef MATCHED_BENCH_TELEMETRY_ENABLED
static esp_err_t start_telemetry(benchmark_telemetry_stream_state_t *stream)
{
  char record[512];
  snprintf(
      record,
      sizeof(record),
      "BENCH_CONFIG schema=%u run_token=%s record_seq=%" PRIu32
      " system=microros qos=%s payload_bytes=%" PRIu32
      " rate_hz=%" PRIu32 " target_tx=%" PRIu32
      " impairment=%s window_ms=%u period_ms=%u"
      " interval_count=%u marker_gpio=%d",
      BENCHMARK_TELEMETRY_SCHEMA_VERSION,
      RUN_TOKEN,
      stream->next_record_seq,
      QOS_NAME,
      PAYLOAD_BYTES,
      1000U / PUBLISH_PERIOD_MS,
      MEASUREMENT_MESSAGES,
      IMPAIRMENT_PROFILE,
      BENCHMARK_TELEMETRY_WINDOW_MS,
      BENCHMARK_TELEMETRY_PERIOD_MS,
      BENCHMARK_TELEMETRY_INTERVAL_COUNT,
      MARKER_GPIO);
  if (!emit_owned_record(stream, record)) {
    return ESP_FAIL;
  }
  esp_err_t status = benchmark_telemetry_start();
  if (status == ESP_OK) {
    status = benchmark_telemetry_wait_started(1000);
  }
  return status;
}

static void finish_telemetry(benchmark_telemetry_stream_state_t *stream)
{
  const benchmark_telemetry_result_t *result = benchmark_telemetry_result();
  if (result == NULL) {
    printf("BENCH_SMOKE_ERROR stage=result err=missing\n");
    vTaskDelete(NULL);
  }
  esp_err_t status = benchmark_telemetry_emit_records(
      RUN_TOKEN, stream, uart_sink, NULL);
  if (status != ESP_OK) {
    printf("BENCH_SMOKE_ERROR stage=dump err=0x%08" PRIx32 "\n",
           (uint32_t)status);
    vTaskDelete(NULL);
  }

  uint64_t average_us = rx_count == 0 ? 0 : rtt_sum_us / rx_count;
  delivery_shape_t shape = summarize_delivery_shape(attempted_tx);
  printf(
      "COMPARE_FINAL system=microros tx=%" PRIu32 " rx=%" PRIu32
      " samples=%" PRIu32 " min_us=%" PRIu32 " avg_us=%" PRIu64
      " max_us=%" PRIu32 " ready_ms=%lld payload_bytes=%" PRIu32
      " period_ms=%" PRIu32
      " grace_ms=%u telemetry=%s publish_failures=%" PRIu32
      " missing=%" PRIu32 " missing_runs=%" PRIu32
      " max_missing_run=%" PRIu32 " arrival_inversions=%" PRIu32
      " rtt_sum_us=%" PRIu64 " rtt_sum_sq_us2=%" PRIu64 "\n",
      attempted_tx,
      rx_count,
      rx_count,
      rx_count == 0 ? 0 : rtt_min_us,
      average_us,
      rtt_max_us,
      (long long)ready_ms,
      PAYLOAD_BYTES,
      PUBLISH_PERIOD_MS,
      REPLY_GRACE_MS,
      TELEMETRY_MODE,
      publish_failures,
      shape.missing,
      shape.missing_runs,
      shape.max_missing_run,
      arrival_inversions,
      rtt_sum_us,
      rtt_sum_sq_us2);

  char record[512];
  const char *completion =
      result->fault_flags == 0 && result->missed_interval_count == 0
          ? "complete"
          : "instrumentation_fault";
  snprintf(
      record,
      sizeof(record),
      "BENCH_FINAL schema=%u run_token=%s record_seq=%" PRIu32
      " completion=%s samples=%u tasks=%" PRIu32
      " missed_intervals=%" PRIu32 " fault_flags=0x%08" PRIx32
      " alloc_failures=%" PRIu32 " attempted_tx=%" PRIu32
      " publish_failures=%" PRIu32 " rx=%" PRIu32
      " duplicates=%" PRIu32 " malformed=%" PRIu32
      " rtt_samples=%" PRIu32
      " missing=%" PRIu32 " missing_runs=%" PRIu32
      " max_missing_run=%" PRIu32 " arrival_inversions=%" PRIu32
      " rtt_sum_us=%" PRIu64 " rtt_sum_sq_us2=%" PRIu64,
      BENCHMARK_TELEMETRY_SCHEMA_VERSION,
      RUN_TOKEN,
      stream->next_record_seq,
      completion,
      BENCHMARK_TELEMETRY_INTERVAL_COUNT,
      result->task_count,
      result->missed_interval_count,
      result->fault_flags,
      result->allocation_failure_count,
      attempted_tx,
      publish_failures,
      rx_count,
      duplicate_count,
      malformed_count,
      rx_count,
      shape.missing,
      shape.missing_runs,
      shape.max_missing_run,
      arrival_inversions,
      rtt_sum_us,
      rtt_sum_sq_us2);
  if (!emit_owned_record(stream, record)) {
    vTaskDelete(NULL);
  }
  printf(
      "BENCH_DUMP_END schema=%u run_token=%s record_seq=%" PRIu32
      " record_count=%" PRIu32 " crc32=0x%08" PRIx32 "\n",
      BENCHMARK_TELEMETRY_SCHEMA_VERSION,
      RUN_TOKEN,
      stream->next_record_seq,
      stream->record_count,
      stream->crc32);
  fflush(stdout);
}
#endif

static void micro_ros_task(void *argument)
{
  (void)argument;
  rcl_allocator_t allocator = rcl_get_default_allocator();
  rclc_support_t support;
  rcl_init_options_t init_options = rcl_get_zero_initialized_init_options();
  RCCHECK(rcl_init_options_init(&init_options, allocator));

#ifdef CONFIG_MICRO_ROS_ESP_XRCE_DDS_MIDDLEWARE
  rmw_init_options_t *rmw_options =
      rcl_init_options_get_rmw_init_options(&init_options);
  RCCHECK(rmw_uros_options_set_udp_address(
      CONFIG_MICRO_ROS_AGENT_IP,
      CONFIG_MICRO_ROS_AGENT_PORT,
      rmw_options));
#endif

  RCCHECK(rclc_support_init_with_options(
      &support, 0, NULL, &init_options, &allocator));
  printf("COMPARE_SESSION system=microros established_ms=%lld\n",
         (long long)((esp_timer_get_time() - boot_us) / 1000));

  rcl_node_t node;
  RCCHECK(rclc_node_init_default(
      &node, "telemetry_compare_microros", "", &support));
#ifdef MATCHED_BENCH_RELIABLE
  RCCHECK(rclc_publisher_init_default(
      &publisher,
      &node,
      ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, String),
      "system_compare"));
  RCCHECK(rclc_subscription_init_default(
      &subscriber,
      &node,
      ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, String),
      "system_compare_reply"));
#else
  RCCHECK(rclc_publisher_init_best_effort(
      &publisher,
      &node,
      ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, String),
      "system_compare"));
  RCCHECK(rclc_subscription_init_best_effort(
      &subscriber,
      &node,
      ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, String),
      "system_compare_reply"));
#endif

  pub_msg.data.data = pub_buffer;
  pub_msg.data.capacity = PAYLOAD_CAPACITY;
  pub_msg.data.size = 0;
  sub_msg.data.data = sub_buffer;
  sub_msg.data.capacity = PAYLOAD_CAPACITY;
  sub_msg.data.size = 0;

  rclc_executor_t executor;
  RCCHECK(rclc_executor_init(&executor, &support.context, 1, &allocator));
  RCCHECK(rclc_executor_add_subscription(
      &executor, &subscriber, &sub_msg, &subscription_callback, ON_NEW_DATA));

  printf(
      "COMPARE_CONFIG system=microros qos=%s payload_bytes=%" PRIu32
      " messages=%" PRIu32 " period_ms=%" PRIu32
      " settle_ms=%u grace_ms=%u telemetry=%s\n",
      QOS_NAME,
      PAYLOAD_BYTES,
      MEASUREMENT_MESSAGES,
      PUBLISH_PERIOD_MS,
      READY_SETTLE_MS,
      REPLY_GRACE_MS,
      TELEMETRY_MODE);
  printf("COMPARE_RESOURCE system=microros free_heap_bytes=%lu\n",
         (unsigned long)esp_get_free_heap_size());

  uint32_t warmup_sequence = 0;
  int64_t next_publish_us = esp_timer_get_time();
  while (ready_ms < 0) {
    int64_t now_us = esp_timer_get_time();
    if (now_us >= next_publish_us) {
      publish_payload('W', warmup_sequence++);
      next_publish_us = now_us + (int64_t)WARMUP_PERIOD_MS * 1000;
    }
    rclc_executor_spin_some(&executor, RCL_MS_TO_NS(20));
    usleep(2000);
  }

  spin_until(&executor,
             esp_timer_get_time() + (int64_t)READY_SETTLE_MS * 1000);
  benchmark_control_probe_state_t control_probe = {0};
  benchmark_control_probe_result_t control_result = {0};
  esp_err_t control_status = benchmark_control_probe_init(&control_probe);
  if (control_status != ESP_OK) {
    printf("BENCH_SMOKE_ERROR stage=control_init err=0x%08" PRIx32 "\n",
           (uint32_t)control_status);
    vTaskDelete(NULL);
  }
#ifdef MATCHED_BENCH_TELEMETRY_ENABLED
  benchmark_telemetry_stream_state_t stream = {0};
  esp_err_t status = start_telemetry(&stream);
  if (status != ESP_OK) {
    printf("BENCH_SMOKE_ERROR stage=start err=0x%08" PRIx32 "\n",
           (uint32_t)status);
    vTaskDelete(NULL);
  }
#endif

  control_status = benchmark_control_probe_start(&control_probe);
  if (control_status != ESP_OK) {
    printf("BENCH_SMOKE_ERROR stage=control_start err=0x%08" PRIx32 "\n",
           (uint32_t)control_status);
    vTaskDelete(NULL);
  }
  const int64_t measurement_start_us = esp_timer_get_time();
  next_publish_us = measurement_start_us;
  for (uint32_t sequence = 0; sequence < MEASUREMENT_MESSAGES; ++sequence) {
    spin_until(&executor, next_publish_us);
    publish_payload('M', sequence);
    // Reliable publication can overrun the nominal period. Drain callbacks
    // once so an overdue send loop cannot starve the subscription executor.
    rclc_executor_spin_some(&executor, 0);
    next_publish_us += (int64_t)PUBLISH_PERIOD_MS * 1000;
  }

#ifdef MATCHED_BENCH_TELEMETRY_ENABLED
  status = benchmark_telemetry_wait_finished(
      BENCHMARK_TELEMETRY_WINDOW_MS + 2000);
  if (status != ESP_OK) {
    printf("BENCH_SMOKE_ERROR stage=window err=0x%08" PRIx32 "\n",
           (uint32_t)status);
    vTaskDelete(NULL);
  }
#else
  spin_until(
      &executor,
      measurement_start_us + (int64_t)MEASUREMENT_WINDOW_MS * 1000);
#endif
  control_status =
      benchmark_control_probe_finish(&control_probe, &control_result);
  if (control_status != ESP_OK) {
    printf("BENCH_SMOKE_ERROR stage=control_finish err=0x%08" PRIx32 "\n",
           (uint32_t)control_status);
    vTaskDelete(NULL);
  }

  int64_t reply_deadline_us =
      esp_timer_get_time() + (int64_t)REPLY_GRACE_MS * 1000;
  while (rx_count < MEASUREMENT_MESSAGES &&
         esp_timer_get_time() < reply_deadline_us) {
    rclc_executor_spin_some(&executor, RCL_MS_TO_NS(20));
    usleep(2000);
  }
  accepting_measurements = false;
#ifdef MATCHED_BENCH_TELEMETRY_ENABLED
  finish_telemetry(&stream);
  emit_control_probe(&control_result);
#else
  emit_control_probe(&control_result);
  uint64_t average_us = rx_count == 0 ? 0 : rtt_sum_us / rx_count;
  delivery_shape_t shape = summarize_delivery_shape(attempted_tx);
  printf(
      "COMPARE_FINAL system=microros tx=%" PRIu32 " rx=%" PRIu32
      " samples=%" PRIu32 " min_us=%" PRIu32 " avg_us=%" PRIu64
      " max_us=%" PRIu32 " ready_ms=%lld payload_bytes=%" PRIu32
      " period_ms=%" PRIu32
      " grace_ms=%u telemetry=off publish_failures=%" PRIu32
      " duplicates=%" PRIu32 " malformed=%" PRIu32
      " missing=%" PRIu32 " missing_runs=%" PRIu32
      " max_missing_run=%" PRIu32 " arrival_inversions=%" PRIu32
      " rtt_sum_us=%" PRIu64 " rtt_sum_sq_us2=%" PRIu64 "\n",
      attempted_tx,
      rx_count,
      rx_count,
      rx_count == 0 ? 0 : rtt_min_us,
      average_us,
      rtt_max_us,
      (long long)ready_ms,
      PAYLOAD_BYTES,
      PUBLISH_PERIOD_MS,
      REPLY_GRACE_MS,
      publish_failures,
      duplicate_count,
      malformed_count,
      shape.missing,
      shape.missing_runs,
      shape.max_missing_run,
      arrival_inversions,
      rtt_sum_us,
      rtt_sum_sq_us2);
  fflush(stdout);
#endif

  while (true) {
    vTaskDelay(pdMS_TO_TICKS(1000));
  }
}

void app_main(void)
{
  boot_us = esp_timer_get_time();
#ifdef MATCHED_BENCH_TELEMETRY_ENABLED
  const benchmark_telemetry_config_t telemetry_config = {
      .marker_gpio = MARKER_GPIO,
      .telemetry_task_core = 1,
      .telemetry_task_priority = configMAX_PRIORITIES - 1,
  };
  esp_err_t status = benchmark_telemetry_init(&telemetry_config);
  if (status != ESP_OK) {
    printf("BENCH_SMOKE_ERROR stage=init err=0x%08" PRIx32 "\n",
           (uint32_t)status);
    return;
  }
#endif

#if defined(CONFIG_MICRO_ROS_ESP_NETIF_WLAN) || \
    defined(CONFIG_MICRO_ROS_ESP_NETIF_ENET)
  ESP_ERROR_CHECK(uros_network_interface_initialize());
#endif
  esp_log_level_set("*", ESP_LOG_NONE);
  if (xTaskCreate(micro_ros_task, "uros_task", 16000, NULL, 5, NULL) != pdPASS) {
    printf("BENCH_SMOKE_ERROR stage=task err=no_mem\n");
  }
}
