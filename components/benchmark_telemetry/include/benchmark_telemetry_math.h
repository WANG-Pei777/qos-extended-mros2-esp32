#pragma once

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

static inline uint32_t benchmark_telemetry_u32_delta(uint32_t before,
                                                      uint32_t after)
{
  return after - before;
}

static inline bool benchmark_telemetry_cpu_busy_ppm(uint64_t wall_delta_us,
                                                     uint32_t idle_before,
                                                     uint32_t idle_after,
                                                     uint32_t *busy_ppm)
{
  if (busy_ppm == 0 || wall_delta_us == 0 || wall_delta_us > UINT32_MAX) {
    return false;
  }

  const uint64_t idle_delta_us =
      benchmark_telemetry_u32_delta(idle_before, idle_after);
  if (idle_delta_us > wall_delta_us) {
    return false;
  }

  const uint64_t busy_delta_us = wall_delta_us - idle_delta_us;
  *busy_ppm = (uint32_t)((busy_delta_us * UINT64_C(1000000)) /
                         wall_delta_us);
  return true;
}

#ifdef __cplusplus
}
#endif
