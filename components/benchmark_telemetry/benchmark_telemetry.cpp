#include "benchmark_telemetry.h"

#include <atomic>
#include <cstdio>
#include <cstring>
#include <inttypes.h>

#include "benchmark_telemetry_math.h"
#include "driver/gpio.h"
#include "esp_crc.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"

#if CONFIG_FREERTOS_USE_TRACE_FACILITY && \
    CONFIG_FREERTOS_GENERATE_RUN_TIME_STATS && \
    CONFIG_FREERTOS_RUN_TIME_STATS_USING_ESP_TIMER

namespace {

constexpr uint32_t kTelemetryTaskStackBytes = 4096;
constexpr uint32_t kCoreSamplerTaskStackBytes = 2048;
constexpr uint32_t kMaximumBoundaryLatenessUs =
    BENCHMARK_TELEMETRY_PERIOD_MS * 1000U;
constexpr size_t kRecordBufferBytes = 768;
constexpr uint32_t kHeapInternalCaps = MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT;
constexpr uint32_t kHeapTotalCaps = MALLOC_CAP_8BIT;

static_assert(std::atomic<uint32_t>::is_always_lock_free,
              "allocation-failure counter must be lock-free");
static_assert(BENCHMARK_TELEMETRY_WINDOW_MS / BENCHMARK_TELEMETRY_PERIOD_MS ==
                  BENCHMARK_TELEMETRY_INTERVAL_COUNT,
              "telemetry interval count must cover the complete window");

benchmark_telemetry_config_t g_config = {};
benchmark_telemetry_result_t g_result = {};
TaskStatus_t g_task_status[BENCHMARK_TELEMETRY_MAX_TASKS] = {};
StaticTask_t g_telemetry_task_storage = {};
StackType_t g_telemetry_task_stack[kTelemetryTaskStackBytes] = {};
TaskHandle_t g_telemetry_task = nullptr;
StaticTask_t g_core0_sampler_task_storage = {};
StackType_t g_core0_sampler_task_stack[kCoreSamplerTaskStackBytes] = {};
TaskHandle_t g_core0_sampler_task = nullptr;
StaticSemaphore_t g_core0_sample_done_storage = {};
SemaphoreHandle_t g_core0_sample_done = nullptr;
TaskHandle_t g_idle_core0 = nullptr;
TaskHandle_t g_idle_core1 = nullptr;
portMUX_TYPE g_marker_lock = portMUX_INITIALIZER_UNLOCKED;

std::atomic<uint32_t> g_state{BENCHMARK_TELEMETRY_UNINITIALIZED};
std::atomic<uint32_t> g_allocation_failure_count{0};
std::atomic<uint32_t> g_first_failure_claimed{0};
std::atomic<uint32_t> g_first_failure_ready{0};
uint32_t g_first_failure_size = 0;
uint32_t g_first_failure_caps = 0;
int64_t g_first_failure_time_us = 0;
uint32_t g_core0_idle_us = 0;
int64_t g_core0_idle_capture_us = 0;

bool valid_config(const benchmark_telemetry_config_t &config)
{
  return GPIO_IS_VALID_OUTPUT_GPIO(config.marker_gpio) &&
         (config.telemetry_task_core == 0 || config.telemetry_task_core == 1) &&
         config.telemetry_task_priority > tskIDLE_PRIORITY &&
         config.telemetry_task_priority < configMAX_PRIORITIES;
}

void allocation_failed(size_t size, uint32_t caps, const char *)
{
  g_allocation_failure_count.fetch_add(1, std::memory_order_relaxed);

  uint32_t expected = 0;
  if (g_first_failure_claimed.compare_exchange_strong(
          expected, 1, std::memory_order_relaxed, std::memory_order_relaxed)) {
    g_first_failure_size = size > UINT32_MAX ? UINT32_MAX : (uint32_t)size;
    g_first_failure_caps = caps;
    g_first_failure_time_us = esp_timer_get_time();
    g_first_failure_ready.store(1, std::memory_order_release);
  }
}

void core0_sampler_task(void *)
{
  for (;;) {
    ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
    TaskStatus_t idle0 = {};
    g_core0_idle_capture_us = esp_timer_get_time();
    vTaskGetInfo(g_idle_core0, &idle0, pdFALSE, eInvalid);
    g_core0_idle_us = idle0.ulRunTimeCounter;
    xSemaphoreGive(g_core0_sample_done);
  }
}

benchmark_telemetry_snapshot_t capture_snapshot(int64_t target_time_us,
                                                bool synchronized_idle)
{
  benchmark_telemetry_snapshot_t snapshot = {};
  snapshot.capture_begin_us = esp_timer_get_time();

  TaskStatus_t idle0 = {};
  TaskStatus_t idle1 = {};
  if (synchronized_idle) {
    xTaskNotifyGive(g_core0_sampler_task);
    snapshot.idle_core1_capture_us = esp_timer_get_time();
    vTaskGetInfo(g_idle_core1, &idle1, pdFALSE, eInvalid);
    if (xSemaphoreTake(
            g_core0_sample_done,
            pdMS_TO_TICKS(BENCHMARK_TELEMETRY_PERIOD_MS / 2)) != pdTRUE) {
      snapshot.fault_flags |=
          BENCHMARK_TELEMETRY_FAULT_CORE_SAMPLE_TIMEOUT;
    }
    snapshot.idle_core0_capture_us = g_core0_idle_capture_us;
    snapshot.idle_core0_us = g_core0_idle_us;
  } else {
    snapshot.idle_core0_capture_us = esp_timer_get_time();
    vTaskGetInfo(g_idle_core0, &idle0, pdFALSE, eInvalid);
    snapshot.idle_core0_us = idle0.ulRunTimeCounter;
    snapshot.idle_core1_capture_us = esp_timer_get_time();
    vTaskGetInfo(g_idle_core1, &idle1, pdFALSE, eInvalid);
  }
  snapshot.idle_core1_us = idle1.ulRunTimeCounter;

  snapshot.free_internal_heap_bytes =
      (uint32_t)heap_caps_get_free_size(kHeapInternalCaps);
  snapshot.free_total_heap_bytes =
      (uint32_t)heap_caps_get_free_size(kHeapTotalCaps);
  snapshot.minimum_internal_heap_bytes =
      (uint32_t)heap_caps_get_minimum_free_size(kHeapInternalCaps);
  snapshot.minimum_total_heap_bytes =
      (uint32_t)heap_caps_get_minimum_free_size(kHeapTotalCaps);
  snapshot.largest_internal_block_bytes =
      (uint32_t)heap_caps_get_largest_free_block(kHeapInternalCaps);
  snapshot.allocation_failure_count =
      g_allocation_failure_count.load(std::memory_order_relaxed);
  snapshot.board_time_us = esp_timer_get_time();

  if (target_time_us != 0) {
    const int64_t lateness = snapshot.board_time_us - target_time_us;
    if (lateness > INT32_MAX) {
      snapshot.boundary_lateness_us = INT32_MAX;
    } else if (lateness < INT32_MIN) {
      snapshot.boundary_lateness_us = INT32_MIN;
    } else {
      snapshot.boundary_lateness_us = (int32_t)lateness;
    }
  }
  return snapshot;
}

void calculate_cpu(benchmark_telemetry_snapshot_t &current,
                   const benchmark_telemetry_snapshot_t &previous)
{
  if (current.board_time_us <= previous.board_time_us ||
      current.idle_core0_capture_us <= previous.idle_core0_capture_us ||
      current.idle_core1_capture_us <= previous.idle_core1_capture_us) {
    current.fault_flags |= BENCHMARK_TELEMETRY_FAULT_TIMER_REGRESSION;
    return;
  }

  const uint64_t core0_wall_delta_us = (uint64_t)(
      current.idle_core0_capture_us - previous.idle_core0_capture_us);
  const uint64_t core1_wall_delta_us = (uint64_t)(
      current.idle_core1_capture_us - previous.idle_core1_capture_us);
  uint32_t core0_ppm = 0;
  uint32_t core1_ppm = 0;
  const bool core0_valid = benchmark_telemetry_cpu_busy_ppm(
      core0_wall_delta_us, previous.idle_core0_us, current.idle_core0_us,
      &core0_ppm);
  const bool core1_valid = benchmark_telemetry_cpu_busy_ppm(
      core1_wall_delta_us, previous.idle_core1_us, current.idle_core1_us,
      &core1_ppm);
  if (!core0_valid || !core1_valid) {
    current.fault_flags |= BENCHMARK_TELEMETRY_FAULT_IDLE_DELTA;
    return;
  }

  current.busy_core0_ppm = core0_ppm;
  current.busy_core1_ppm = core1_ppm;
}

void copy_token_task_name(char *destination,
                          size_t destination_size,
                          const char *source)
{
  size_t index = 0;
  for (; index + 1 < destination_size && source[index] != '\0'; ++index) {
    const char value = source[index];
    const bool valid = (value >= 'a' && value <= 'z') ||
                       (value >= 'A' && value <= 'Z') ||
                       (value >= '0' && value <= '9') || value == '_' ||
                       value == '-' || value == '.';
    destination[index] = valid ? value : '_';
  }
  destination[index] = '\0';
}

void set_marker(int level, int64_t &pre_us, int64_t &post_us)
{
  taskENTER_CRITICAL(&g_marker_lock);
  pre_us = esp_timer_get_time();
  if (gpio_set_level((gpio_num_t)g_config.marker_gpio, level) != ESP_OK) {
    g_result.fault_flags |= BENCHMARK_TELEMETRY_FAULT_MARKER_GPIO;
  }
  post_us = esp_timer_get_time();
  taskEXIT_CRITICAL(&g_marker_lock);
}

void collect_task_records()
{
  g_result.task_count_before_snapshot = uxTaskGetNumberOfTasks();
  if (g_result.task_count_before_snapshot > BENCHMARK_TELEMETRY_MAX_TASKS) {
    g_result.fault_flags |= BENCHMARK_TELEMETRY_FAULT_TASK_LIST_TRUNCATED;
    return;
  }

  uint32_t ignored_total_runtime = 0;
  const UBaseType_t count = uxTaskGetSystemState(
      g_task_status, BENCHMARK_TELEMETRY_MAX_TASKS, &ignored_total_runtime);
  if (count == 0) {
    g_result.fault_flags |= BENCHMARK_TELEMETRY_FAULT_TASK_LIST_TRUNCATED;
    return;
  }
  if (count != g_result.task_count_before_snapshot) {
    g_result.fault_flags |= BENCHMARK_TELEMETRY_FAULT_TASK_LIST_CHANGED;
  }

  g_result.task_count = count;
  for (UBaseType_t i = 0; i < count; ++i) {
    benchmark_telemetry_task_record_t &record = g_result.tasks[i];
    const TaskStatus_t &status = g_task_status[i];
    copy_token_task_name(record.name, sizeof(record.name), status.pcTaskName);
    record.task_number = status.xTaskNumber;
    record.runtime_counter_us = status.ulRunTimeCounter;
    record.stack_high_watermark_bytes =
        (uint32_t)status.usStackHighWaterMark * sizeof(StackType_t);
    record.current_priority = status.uxCurrentPriority;
    record.core_affinity = xTaskGetAffinity(status.xHandle);
    record.state = (uint32_t)status.eCurrentState;
  }
}

void telemetry_task(void *)
{
  for (;;) {
    ulTaskNotifyTake(pdTRUE, portMAX_DELAY);

    set_marker(1, g_result.marker_start_pre_us, g_result.marker_start_post_us);
    g_result.window_start = capture_snapshot(0, true);
    g_state.store(BENCHMARK_TELEMETRY_ACTIVE, std::memory_order_release);

    const int64_t period_us =
        (int64_t)BENCHMARK_TELEMETRY_PERIOD_MS * 1000;
    const int64_t first_target_us =
        g_result.window_start.board_time_us + period_us;
    TickType_t last_wake_tick = xTaskGetTickCount();
    const TickType_t period_ticks =
        pdMS_TO_TICKS(BENCHMARK_TELEMETRY_PERIOD_MS);
    benchmark_telemetry_snapshot_t previous = g_result.window_start;

    for (uint32_t i = 0; i < BENCHMARK_TELEMETRY_INTERVAL_COUNT; ++i) {
      vTaskDelayUntil(&last_wake_tick, period_ticks);
      const int64_t target_us = first_target_us + (int64_t)i * period_us;
      benchmark_telemetry_snapshot_t &sample = g_result.intervals[i];
      sample = capture_snapshot(target_us, true);
      calculate_cpu(sample, previous);
      if (sample.boundary_lateness_us >=
          (int32_t)kMaximumBoundaryLatenessUs) {
        sample.fault_flags |= BENCHMARK_TELEMETRY_FAULT_MISSED_INTERVAL;
        ++g_result.missed_interval_count;
      }
      g_result.fault_flags |= sample.fault_flags;
      previous = sample;
    }

    set_marker(0, g_result.marker_end_pre_us, g_result.marker_end_post_us);
    g_result.window_end = capture_snapshot(0, true);
    calculate_cpu(g_result.window_end, previous);
    g_result.fault_flags |= g_result.window_end.fault_flags;
    collect_task_records();

    g_result.allocation_failure_count =
        g_allocation_failure_count.load(std::memory_order_relaxed);
    if (g_first_failure_ready.load(std::memory_order_acquire) != 0) {
      g_result.first_allocation_failure_present = true;
      g_result.first_allocation_failure_size = g_first_failure_size;
      g_result.first_allocation_failure_caps = g_first_failure_caps;
      g_result.first_allocation_failure_time_us = g_first_failure_time_us;
    }

    g_state.store(BENCHMARK_TELEMETRY_COMPLETE, std::memory_order_release);
  }
}

bool valid_run_token(const char *run_token)
{
  if (run_token == nullptr) {
    return false;
  }
  const size_t length = std::strlen(run_token);
  if (length == 0 || length > 64) {
    return false;
  }
  for (size_t i = 0; i < length; ++i) {
    const char c = run_token[i];
    const bool valid = (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
                       (c >= '0' && c <= '9') || c == '-' || c == '_' ||
                       c == '.';
    if (!valid) {
      return false;
    }
  }
  return true;
}

bool emit_record(benchmark_telemetry_stream_state_t &stream,
                 benchmark_telemetry_record_sink_t sink,
                 void *sink_context,
                 const char *record,
                 int length)
{
  if (length < 0 || (size_t)length >= kRecordBufferBytes) {
    return false;
  }
  if (!sink(record, (size_t)length, sink_context)) {
    return false;
  }
  stream.crc32 = esp_crc32_le(
      stream.crc32, reinterpret_cast<const uint8_t *>(record), (uint32_t)length);
  static const uint8_t newline = '\n';
  stream.crc32 = esp_crc32_le(stream.crc32, &newline, 1);
  ++stream.next_record_seq;
  ++stream.record_count;
  return true;
}

int format_snapshot(char *buffer,
                    const char *family,
                    const char *run_token,
                    uint32_t record_seq,
                    int32_t index,
                    const benchmark_telemetry_snapshot_t &snapshot)
{
  return std::snprintf(
      buffer, kRecordBufferBytes,
      "%s schema=%u run_token=%s record_seq=%" PRIu32 " index=%" PRId32 " "
      "capture_begin_us=%" PRId64 " board_time_us=%" PRId64
      " idle0_capture_us=%" PRId64 " idle1_capture_us=%" PRId64
      " idle0_us=%" PRIu32 " idle1_us=%" PRIu32
      " busy0_ppm=%" PRIu32 " busy1_ppm=%" PRIu32
      " free_internal=%" PRIu32 " free_total=%" PRIu32
      " min_internal=%" PRIu32 " min_total=%" PRIu32
      " largest_internal=%" PRIu32 " alloc_failures=%" PRIu32
      " lateness_us=%" PRId32 " fault_flags=0x%08" PRIx32,
      family, BENCHMARK_TELEMETRY_SCHEMA_VERSION, run_token, record_seq,
      index, snapshot.capture_begin_us, snapshot.board_time_us,
      snapshot.idle_core0_capture_us, snapshot.idle_core1_capture_us,
      snapshot.idle_core0_us,
      snapshot.idle_core1_us, snapshot.busy_core0_ppm,
      snapshot.busy_core1_ppm, snapshot.free_internal_heap_bytes,
      snapshot.free_total_heap_bytes, snapshot.minimum_internal_heap_bytes,
      snapshot.minimum_total_heap_bytes, snapshot.largest_internal_block_bytes,
      snapshot.allocation_failure_count, snapshot.boundary_lateness_us,
      snapshot.fault_flags);
}

int format_window_snapshot(char *buffer,
                           const char *family,
                           const char *run_token,
                           uint32_t record_seq,
                           uint32_t marker_state,
                           int64_t marker_pre_us,
                           int64_t marker_post_us,
                           const benchmark_telemetry_snapshot_t &snapshot)
{
  return std::snprintf(
      buffer, kRecordBufferBytes,
      "%s schema=%u run_token=%s record_seq=%" PRIu32
      " marker_state=%" PRIu32 " marker_pre_us=%" PRId64
      " marker_post_us=%" PRId64 " capture_begin_us=%" PRId64
      " board_time_us=%" PRId64 " idle0_capture_us=%" PRId64
      " idle1_capture_us=%" PRId64 " idle0_us=%" PRIu32
      " idle1_us=%" PRIu32 " busy0_ppm=%" PRIu32
      " busy1_ppm=%" PRIu32 " free_internal=%" PRIu32
      " free_total=%" PRIu32 " min_internal=%" PRIu32
      " min_total=%" PRIu32 " largest_internal=%" PRIu32
      " alloc_failures=%" PRIu32 " fault_flags=0x%08" PRIx32,
      family, BENCHMARK_TELEMETRY_SCHEMA_VERSION, run_token, record_seq,
      marker_state, marker_pre_us, marker_post_us, snapshot.capture_begin_us,
      snapshot.board_time_us,
      snapshot.idle_core0_capture_us, snapshot.idle_core1_capture_us,
      snapshot.idle_core0_us, snapshot.idle_core1_us,
      snapshot.busy_core0_ppm, snapshot.busy_core1_ppm,
      snapshot.free_internal_heap_bytes, snapshot.free_total_heap_bytes,
      snapshot.minimum_internal_heap_bytes, snapshot.minimum_total_heap_bytes,
      snapshot.largest_internal_block_bytes,
      snapshot.allocation_failure_count, snapshot.fault_flags);
}

}  // namespace

extern "C" esp_err_t benchmark_telemetry_init(
    const benchmark_telemetry_config_t *config)
{
  if (config == nullptr || !valid_config(*config)) {
    return ESP_ERR_INVALID_ARG;
  }
  uint32_t expected = BENCHMARK_TELEMETRY_UNINITIALIZED;
  if (!g_state.compare_exchange_strong(expected, BENCHMARK_TELEMETRY_READY)) {
    return ESP_ERR_INVALID_STATE;
  }

  g_config = *config;
  gpio_config_t marker_config = {};
  marker_config.pin_bit_mask = UINT64_C(1) << config->marker_gpio;
  marker_config.mode = GPIO_MODE_OUTPUT;
  marker_config.pull_up_en = GPIO_PULLUP_DISABLE;
  marker_config.pull_down_en = GPIO_PULLDOWN_ENABLE;
  marker_config.intr_type = GPIO_INTR_DISABLE;
  esp_err_t result = gpio_config(&marker_config);
  if (result == ESP_OK) {
    result = gpio_set_level((gpio_num_t)config->marker_gpio, 0);
  }
  if (result != ESP_OK) {
    g_state.store(BENCHMARK_TELEMETRY_UNINITIALIZED);
    return result;
  }

  result = heap_caps_register_failed_alloc_callback(allocation_failed);
  if (result != ESP_OK) {
    g_state.store(BENCHMARK_TELEMETRY_UNINITIALIZED);
    return result;
  }

  g_idle_core0 = xTaskGetIdleTaskHandleForCPU(0);
  g_idle_core1 = xTaskGetIdleTaskHandleForCPU(1);
  if (g_idle_core0 == nullptr || g_idle_core1 == nullptr) {
    g_state.store(BENCHMARK_TELEMETRY_UNINITIALIZED);
    return ESP_ERR_INVALID_STATE;
  }

  g_result.application_entry = capture_snapshot(0, false);
  g_core0_sample_done =
      xSemaphoreCreateBinaryStatic(&g_core0_sample_done_storage);
  if (g_core0_sample_done == nullptr) {
    g_state.store(BENCHMARK_TELEMETRY_UNINITIALIZED);
    return ESP_ERR_NO_MEM;
  }
  g_core0_sampler_task = xTaskCreateStaticPinnedToCore(
      core0_sampler_task, "bench_core0", kCoreSamplerTaskStackBytes, nullptr,
      config->telemetry_task_priority, g_core0_sampler_task_stack,
      &g_core0_sampler_task_storage, 0);
  if (g_core0_sampler_task == nullptr) {
    g_state.store(BENCHMARK_TELEMETRY_UNINITIALIZED);
    return ESP_ERR_NO_MEM;
  }
  g_telemetry_task = xTaskCreateStaticPinnedToCore(
      telemetry_task, "bench_telemetry", kTelemetryTaskStackBytes, nullptr,
      config->telemetry_task_priority, g_telemetry_task_stack,
      &g_telemetry_task_storage, config->telemetry_task_core);
  if (g_telemetry_task == nullptr) {
    vTaskDelete(g_core0_sampler_task);
    g_core0_sampler_task = nullptr;
    g_state.store(BENCHMARK_TELEMETRY_UNINITIALIZED);
    return ESP_ERR_NO_MEM;
  }
  return ESP_OK;
}

extern "C" esp_err_t benchmark_telemetry_start(void)
{
  uint32_t expected = BENCHMARK_TELEMETRY_READY;
  if (!g_state.compare_exchange_strong(expected, BENCHMARK_TELEMETRY_STARTING)) {
    return ESP_ERR_INVALID_STATE;
  }
  xTaskNotifyGive(g_telemetry_task);
  return ESP_OK;
}

extern "C" esp_err_t benchmark_telemetry_wait_started(uint32_t timeout_ms)
{
  const TickType_t start_tick = xTaskGetTickCount();
  const TickType_t timeout_ticks = pdMS_TO_TICKS(timeout_ms);
  for (;;) {
    const benchmark_telemetry_state_t state = benchmark_telemetry_state();
    if (state == BENCHMARK_TELEMETRY_ACTIVE ||
        state == BENCHMARK_TELEMETRY_COMPLETE) {
      return ESP_OK;
    }
    if (state != BENCHMARK_TELEMETRY_STARTING) {
      return ESP_ERR_INVALID_STATE;
    }
    if ((xTaskGetTickCount() - start_tick) >= timeout_ticks) {
      return ESP_ERR_TIMEOUT;
    }
    vTaskDelay(1);
  }
}

extern "C" esp_err_t benchmark_telemetry_wait_finished(uint32_t timeout_ms)
{
  const TickType_t start_tick = xTaskGetTickCount();
  const TickType_t timeout_ticks = pdMS_TO_TICKS(timeout_ms);
  for (;;) {
    const benchmark_telemetry_state_t state = benchmark_telemetry_state();
    if (state == BENCHMARK_TELEMETRY_COMPLETE) {
      return ESP_OK;
    }
    if (state != BENCHMARK_TELEMETRY_STARTING &&
        state != BENCHMARK_TELEMETRY_ACTIVE) {
      return ESP_ERR_INVALID_STATE;
    }
    if ((xTaskGetTickCount() - start_tick) >= timeout_ticks) {
      return ESP_ERR_TIMEOUT;
    }
    vTaskDelay(1);
  }
}

extern "C" benchmark_telemetry_state_t benchmark_telemetry_state(void)
{
  return (benchmark_telemetry_state_t)g_state.load(std::memory_order_acquire);
}

extern "C" const benchmark_telemetry_result_t *benchmark_telemetry_result(void)
{
  return benchmark_telemetry_state() == BENCHMARK_TELEMETRY_COMPLETE
             ? &g_result
             : nullptr;
}

extern "C" esp_err_t benchmark_telemetry_emit_records(
    const char *run_token,
    benchmark_telemetry_stream_state_t *stream,
    benchmark_telemetry_record_sink_t sink,
    void *sink_context)
{
  if (!valid_run_token(run_token) || stream == nullptr || sink == nullptr) {
    return ESP_ERR_INVALID_ARG;
  }
  if (benchmark_telemetry_state() != BENCHMARK_TELEMETRY_COMPLETE) {
    return ESP_ERR_INVALID_STATE;
  }

  char buffer[kRecordBufferBytes] = {};
  int length = format_window_snapshot(
      buffer, "BENCH_WINDOW_START", run_token, stream->next_record_seq, 1,
      g_result.marker_start_pre_us, g_result.marker_start_post_us,
      g_result.window_start);
  if (!emit_record(*stream, sink, sink_context, buffer, length)) {
    return ESP_FAIL;
  }

  for (uint32_t i = 0; i < BENCHMARK_TELEMETRY_INTERVAL_COUNT; ++i) {
    length = format_snapshot(buffer, "BENCH_SAMPLE", run_token,
                             stream->next_record_seq, (int32_t)i,
                             g_result.intervals[i]);
    if (!emit_record(*stream, sink, sink_context, buffer, length)) {
      return ESP_FAIL;
    }
  }

  length = format_window_snapshot(
      buffer, "BENCH_WINDOW_END", run_token, stream->next_record_seq, 0,
      g_result.marker_end_pre_us, g_result.marker_end_post_us,
      g_result.window_end);
  if (!emit_record(*stream, sink, sink_context, buffer, length)) {
    return ESP_FAIL;
  }

  for (uint32_t i = 0; i < g_result.task_count; ++i) {
    const benchmark_telemetry_task_record_t &task = g_result.tasks[i];
    length = std::snprintf(
        buffer, kRecordBufferBytes,
        "BENCH_TASK schema=%u run_token=%s record_seq=%" PRIu32
        " index=%" PRIu32 " name=%s task_number=%" PRIu32
        " runtime_us=%" PRIu32 " stack_hwm_bytes=%" PRIu32
        " priority=%" PRIu32 " core_affinity=%" PRId32
        " state=%" PRIu32,
        BENCHMARK_TELEMETRY_SCHEMA_VERSION, run_token, stream->next_record_seq, i,
        task.name, task.task_number, task.runtime_counter_us,
        task.stack_high_watermark_bytes, task.current_priority,
        task.core_affinity, task.state);
    if (!emit_record(*stream, sink, sink_context, buffer, length)) {
      return ESP_FAIL;
    }
  }

  length = std::snprintf(
      buffer, kRecordBufferBytes,
      "BENCH_ALLOC_FAIL schema=%u run_token=%s record_seq=%" PRIu32
      " present=%u count=%" PRIu32 " first_size=%" PRIu32
      " first_caps=0x%08" PRIx32 " first_time_us=%" PRId64,
      BENCHMARK_TELEMETRY_SCHEMA_VERSION, run_token, stream->next_record_seq,
      g_result.first_allocation_failure_present ? 1U : 0U,
      g_result.allocation_failure_count, g_result.first_allocation_failure_size,
      g_result.first_allocation_failure_caps,
      g_result.first_allocation_failure_time_us);
  if (!emit_record(*stream, sink, sink_context, buffer, length)) {
    return ESP_FAIL;
  }

  return ESP_OK;
}

#else

extern "C" esp_err_t benchmark_telemetry_init(
    const benchmark_telemetry_config_t *)
{
  return ESP_ERR_NOT_SUPPORTED;
}

extern "C" esp_err_t benchmark_telemetry_start(void)
{
  return ESP_ERR_NOT_SUPPORTED;
}

extern "C" esp_err_t benchmark_telemetry_wait_started(uint32_t)
{
  return ESP_ERR_NOT_SUPPORTED;
}

extern "C" esp_err_t benchmark_telemetry_wait_finished(uint32_t)
{
  return ESP_ERR_NOT_SUPPORTED;
}

extern "C" benchmark_telemetry_state_t benchmark_telemetry_state(void)
{
  return BENCHMARK_TELEMETRY_UNINITIALIZED;
}

extern "C" const benchmark_telemetry_result_t *benchmark_telemetry_result(void)
{
  return nullptr;
}

extern "C" esp_err_t benchmark_telemetry_emit_records(
    const char *,
    benchmark_telemetry_stream_state_t *,
    benchmark_telemetry_record_sink_t,
    void *)
{
  return ESP_ERR_NOT_SUPPORTED;
}

#endif
