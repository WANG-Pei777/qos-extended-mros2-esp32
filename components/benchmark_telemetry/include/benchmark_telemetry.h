#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

#define BENCHMARK_TELEMETRY_SCHEMA_VERSION 1U
#define BENCHMARK_TELEMETRY_PERIOD_MS 100U
#define BENCHMARK_TELEMETRY_WINDOW_MS 20000U
#define BENCHMARK_TELEMETRY_INTERVAL_COUNT 200U
#define BENCHMARK_TELEMETRY_MAX_TASKS 48U
#define BENCHMARK_TELEMETRY_TASK_NAME_BYTES 16U

typedef enum {
  BENCHMARK_TELEMETRY_UNINITIALIZED = 0,
  BENCHMARK_TELEMETRY_READY,
  BENCHMARK_TELEMETRY_STARTING,
  BENCHMARK_TELEMETRY_ACTIVE,
  BENCHMARK_TELEMETRY_COMPLETE,
} benchmark_telemetry_state_t;

enum {
  BENCHMARK_TELEMETRY_FAULT_NONE = 0,
  BENCHMARK_TELEMETRY_FAULT_TIMER_REGRESSION = 1U << 0,
  BENCHMARK_TELEMETRY_FAULT_IDLE_DELTA = 1U << 1,
  BENCHMARK_TELEMETRY_FAULT_MISSED_INTERVAL = 1U << 2,
  BENCHMARK_TELEMETRY_FAULT_TASK_LIST_TRUNCATED = 1U << 3,
  BENCHMARK_TELEMETRY_FAULT_TASK_LIST_CHANGED = 1U << 4,
  BENCHMARK_TELEMETRY_FAULT_MARKER_GPIO = 1U << 5,
  BENCHMARK_TELEMETRY_FAULT_CORE_SAMPLE_TIMEOUT = 1U << 6,
};

typedef struct {
  int marker_gpio;
  int telemetry_task_core;
  uint32_t telemetry_task_priority;
} benchmark_telemetry_config_t;

typedef struct {
  int64_t capture_begin_us;
  int64_t board_time_us;
  int64_t idle_core0_capture_us;
  int64_t idle_core1_capture_us;
  uint32_t idle_core0_us;
  uint32_t idle_core1_us;
  uint32_t busy_core0_ppm;
  uint32_t busy_core1_ppm;
  uint32_t free_internal_heap_bytes;
  uint32_t free_total_heap_bytes;
  uint32_t minimum_internal_heap_bytes;
  uint32_t minimum_total_heap_bytes;
  uint32_t largest_internal_block_bytes;
  uint32_t allocation_failure_count;
  int32_t boundary_lateness_us;
  uint32_t fault_flags;
} benchmark_telemetry_snapshot_t;

typedef struct {
  char name[BENCHMARK_TELEMETRY_TASK_NAME_BYTES];
  uint32_t task_number;
  uint32_t runtime_counter_us;
  uint32_t stack_high_watermark_bytes;
  uint32_t current_priority;
  int32_t core_affinity;
  uint32_t state;
} benchmark_telemetry_task_record_t;

typedef struct {
  benchmark_telemetry_snapshot_t application_entry;
  benchmark_telemetry_snapshot_t window_start;
  benchmark_telemetry_snapshot_t intervals[BENCHMARK_TELEMETRY_INTERVAL_COUNT];
  benchmark_telemetry_snapshot_t window_end;
  benchmark_telemetry_task_record_t tasks[BENCHMARK_TELEMETRY_MAX_TASKS];
  uint32_t task_count;
  uint32_t task_count_before_snapshot;
  uint32_t missed_interval_count;
  uint32_t fault_flags;
  int64_t marker_start_pre_us;
  int64_t marker_start_post_us;
  int64_t marker_end_pre_us;
  int64_t marker_end_post_us;
  uint32_t first_allocation_failure_size;
  uint32_t first_allocation_failure_caps;
  int64_t first_allocation_failure_time_us;
  uint32_t allocation_failure_count;
  bool first_allocation_failure_present;
} benchmark_telemetry_result_t;

typedef bool (*benchmark_telemetry_record_sink_t)(const char *record,
                                                   size_t length,
                                                   void *context);

typedef struct {
  uint32_t next_record_seq;
  uint32_t record_count;
  uint32_t crc32;
} benchmark_telemetry_stream_state_t;

esp_err_t benchmark_telemetry_init(const benchmark_telemetry_config_t *config);
esp_err_t benchmark_telemetry_start(void);
esp_err_t benchmark_telemetry_wait_started(uint32_t timeout_ms);
esp_err_t benchmark_telemetry_wait_finished(uint32_t timeout_ms);
benchmark_telemetry_state_t benchmark_telemetry_state(void);
const benchmark_telemetry_result_t *benchmark_telemetry_result(void);

/*
 * Emits only telemetry-owned records after the window. The caller owns
 * BENCH_CONFIG, BENCH_FINAL, and BENCH_DUMP_END and can continue the returned
 * sequence/CRC state to cover the complete canonical serial stream.
 */
esp_err_t benchmark_telemetry_emit_records(
    const char *run_token,
    benchmark_telemetry_stream_state_t *stream,
    benchmark_telemetry_record_sink_t sink,
    void *sink_context);

#ifdef __cplusplus
}
#endif
