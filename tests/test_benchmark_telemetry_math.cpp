#include <cstdint>
#include <iostream>
#include <limits>

#include "benchmark_telemetry_math.h"

namespace {

int checks = 0;
int failures = 0;

void expect(bool condition, const char *name)
{
  ++checks;
  if (!condition) {
    ++failures;
    std::cerr << "[FAIL] " << name << '\n';
  }
}

}  // namespace

int main()
{
  expect(benchmark_telemetry_u32_delta(100, 150) == 50,
         "ordinary unsigned delta");
  expect(benchmark_telemetry_u32_delta(UINT32_MAX - 9, 20) == 30,
         "unsigned delta handles one wrap");

  uint32_t ppm = 0;
  expect(benchmark_telemetry_cpu_busy_ppm(100000, 10, 100010, &ppm) &&
             ppm == 0,
         "fully idle interval is zero busy");
  expect(benchmark_telemetry_cpu_busy_ppm(100000, 10, 50010, &ppm) &&
             ppm == 500000,
         "half idle interval is half busy");
  expect(benchmark_telemetry_cpu_busy_ppm(100000, 10, 10, &ppm) &&
             ppm == 1000000,
         "no idle interval is fully busy");
  expect(benchmark_telemetry_cpu_busy_ppm(
             100, UINT32_MAX - 49, 50, &ppm) && ppm == 0,
         "CPU calculation handles idle counter wrap");
  expect(!benchmark_telemetry_cpu_busy_ppm(100, 0, 101, &ppm),
         "idle delta greater than wall time is rejected");
  expect(!benchmark_telemetry_cpu_busy_ppm(0, 0, 0, &ppm),
         "zero wall interval is rejected");
  expect(!benchmark_telemetry_cpu_busy_ppm(
             (uint64_t)UINT32_MAX + 1, 0, 0, &ppm),
         "ambiguous multi-wrap interval is rejected");
  expect(!benchmark_telemetry_cpu_busy_ppm(100, 0, 0, nullptr),
         "null result pointer is rejected");

  if (failures == 0) {
    std::cout << "[PASS] benchmark telemetry math: " << checks << '/' << checks
              << " checks\n";
    return 0;
  }
  std::cerr << "[FAIL] benchmark telemetry math: " << failures << '/' << checks
            << " checks failed\n";
  return 1;
}
