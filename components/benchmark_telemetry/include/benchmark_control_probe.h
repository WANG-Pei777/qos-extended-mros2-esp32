#pragma once

#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#include "esp_err.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#ifdef __cplusplus
extern "C" {
#endif

enum {
  BENCHMARK_CONTROL_PROBE_FAULT_NONE = 0,
  BENCHMARK_CONTROL_PROBE_FAULT_STATE = 1U << 0,
  BENCHMARK_CONTROL_PROBE_FAULT_TIMER_REGRESSION = 1U << 1,
  BENCHMARK_CONTROL_PROBE_FAULT_IDLE_DELTA = 1U << 2,
};

typedef struct {
  int64_t capture_begin_us;
  int64_t idle_core0_capture_us;
  int64_t idle_core1_capture_us;
  int64_t capture_end_us;
  uint32_t idle_core0_us;
  uint32_t idle_core1_us;
} benchmark_control_probe_boundary_t;

typedef struct {
  TaskHandle_t idle_core0;
  TaskHandle_t idle_core1;
  benchmark_control_probe_boundary_t start;
  bool initialized;
  bool started;
  bool finished;
} benchmark_control_probe_state_t;

typedef struct {
  benchmark_control_probe_boundary_t start;
  benchmark_control_probe_boundary_t end;
  uint64_t wall_core0_us;
  uint64_t wall_core1_us;
  uint32_t idle_core0_delta_us;
  uint32_t idle_core1_delta_us;
  uint32_t busy_core0_ppm;
  uint32_t busy_core1_ppm;
  uint32_t busy_mean_ppm;
  uint32_t fault_flags;
} benchmark_control_probe_result_t;

static inline void benchmark_control_probe_capture(
    TaskHandle_t idle_core0,
    TaskHandle_t idle_core1,
    benchmark_control_probe_boundary_t *boundary)
{
  TaskStatus_t idle0 = {0};
  TaskStatus_t idle1 = {0};
  boundary->capture_begin_us = esp_timer_get_time();
  boundary->idle_core0_capture_us = esp_timer_get_time();
  vTaskGetInfo(idle_core0, &idle0, pdFALSE, eInvalid);
  boundary->idle_core0_us = idle0.ulRunTimeCounter;
  boundary->idle_core1_capture_us = esp_timer_get_time();
  vTaskGetInfo(idle_core1, &idle1, pdFALSE, eInvalid);
  boundary->idle_core1_us = idle1.ulRunTimeCounter;
  boundary->capture_end_us = esp_timer_get_time();
}

static inline esp_err_t benchmark_control_probe_init(
    benchmark_control_probe_state_t *state)
{
  if (state == NULL) {
    return ESP_ERR_INVALID_ARG;
  }
  memset(state, 0, sizeof(*state));
  state->idle_core0 = xTaskGetIdleTaskHandleForCPU(0);
  state->idle_core1 = xTaskGetIdleTaskHandleForCPU(1);
  if (state->idle_core0 == NULL || state->idle_core1 == NULL) {
    return ESP_ERR_INVALID_STATE;
  }
  state->initialized = true;
  return ESP_OK;
}

static inline esp_err_t benchmark_control_probe_start(
    benchmark_control_probe_state_t *state)
{
  if (state == NULL || !state->initialized || state->started) {
    return ESP_ERR_INVALID_STATE;
  }
  benchmark_control_probe_capture(
      state->idle_core0, state->idle_core1, &state->start);
  state->started = true;
  return ESP_OK;
}

static inline uint32_t benchmark_control_probe_busy_ppm(
    uint64_t wall_us,
    uint32_t idle_delta_us,
    uint32_t *fault_flags)
{
  if (wall_us == 0 || idle_delta_us > wall_us) {
    *fault_flags |= BENCHMARK_CONTROL_PROBE_FAULT_IDLE_DELTA;
    return 0;
  }
  return (uint32_t)(((wall_us - idle_delta_us) * UINT64_C(1000000)) /
                    wall_us);
}

static inline esp_err_t benchmark_control_probe_finish(
    benchmark_control_probe_state_t *state,
    benchmark_control_probe_result_t *result)
{
  if (state == NULL || result == NULL || !state->initialized ||
      !state->started || state->finished) {
    return ESP_ERR_INVALID_STATE;
  }
  memset(result, 0, sizeof(*result));
  result->start = state->start;
  benchmark_control_probe_capture(
      state->idle_core0, state->idle_core1, &result->end);
  state->finished = true;

  if (result->end.idle_core0_capture_us <=
          result->start.idle_core0_capture_us ||
      result->end.idle_core1_capture_us <=
          result->start.idle_core1_capture_us) {
    result->fault_flags |= BENCHMARK_CONTROL_PROBE_FAULT_TIMER_REGRESSION;
    return ESP_OK;
  }

  result->wall_core0_us = (uint64_t)(
      result->end.idle_core0_capture_us -
      result->start.idle_core0_capture_us);
  result->wall_core1_us = (uint64_t)(
      result->end.idle_core1_capture_us -
      result->start.idle_core1_capture_us);
  result->idle_core0_delta_us =
      result->end.idle_core0_us - result->start.idle_core0_us;
  result->idle_core1_delta_us =
      result->end.idle_core1_us - result->start.idle_core1_us;
  result->busy_core0_ppm = benchmark_control_probe_busy_ppm(
      result->wall_core0_us,
      result->idle_core0_delta_us,
      &result->fault_flags);
  result->busy_core1_ppm = benchmark_control_probe_busy_ppm(
      result->wall_core1_us,
      result->idle_core1_delta_us,
      &result->fault_flags);
  result->busy_mean_ppm =
      (result->busy_core0_ppm + result->busy_core1_ppm) / 2U;
  return ESP_OK;
}

#ifdef __cplusplus
}
#endif
