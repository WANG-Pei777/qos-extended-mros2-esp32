/* Host-side writer resource and history-capacity policy tests. */

#include "rtps/entities/ResourceLimits.h"

#include <cstdint>
#include <cstdio>

namespace {

int total = 0;
int failed = 0;

void check(bool condition, const char *label) {
  ++total;
  if (condition) {
    std::printf("[PASS] %s\n", label);
  } else {
    ++failed;
    std::printf("[FAIL] %s\n", label);
  }
}

}  // namespace

int main() {
  using rtps::HistoryCapacityDecision;
  using rtps::ResourceLimitDecision;

  check(rtps::evaluateResourceLimits(100, 1000, 1000, 0, 0) ==
            ResourceLimitDecision::ACCEPT,
        "disabled resource limits accept a sample");
  check(rtps::evaluateResourceLimits(4, 0, 64, 5, 0) ==
            ResourceLimitDecision::ACCEPT,
        "sample count below max_samples is accepted");
  check(rtps::evaluateResourceLimits(5, 0, 64, 5, 0) ==
            ResourceLimitDecision::SAMPLE_LIMIT,
        "sample count at max_samples rejects the next sample");
  check(rtps::evaluateResourceLimits(0, 64, 64, 0, 128) ==
            ResourceLimitDecision::ACCEPT,
        "max_bytes accepts the exact boundary");
  check(rtps::evaluateResourceLimits(0, 65, 64, 0, 128) ==
            ResourceLimitDecision::BYTE_LIMIT,
        "max_bytes rejects the first excess byte");
  check(rtps::evaluateResourceLimits(0, UINT32_MAX - 4, 8, 0, UINT32_MAX) ==
            ResourceLimitDecision::BYTE_LIMIT,
        "byte accounting rejects unsigned addition overflow");
  check(rtps::evaluateHistoryCapacity(false, true) ==
            HistoryCapacityDecision::ACCEPT,
        "non-full history accepts independently of policy");
  check(rtps::evaluateHistoryCapacity(true, true) ==
            HistoryCapacityDecision::REJECT,
        "KEEP_ALL rejects when capacity is full");
  check(rtps::evaluateHistoryCapacity(true, false) ==
            HistoryCapacityDecision::EVICT_OLDEST,
        "KEEP_LAST evicts the oldest sample when capacity is full");

  std::printf("Resource limits: %d/%d passed\n", total - failed, total);
  return failed == 0 ? 0 : 1;
}
