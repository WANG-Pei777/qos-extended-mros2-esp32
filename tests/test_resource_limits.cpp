/* Host-side writer resource and history-capacity policy tests. */

#include "rtps/entities/ResourceLimits.h"
#include "rtps/entities/EndpointQosValidation.h"

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
  check(rtps::evaluateResourceLimits(
            0, static_cast<uint64_t>(UINT32_MAX) + 1, 0, 0, UINT32_MAX) ==
            ResourceLimitDecision::BYTE_LIMIT,
        "64-bit retained-byte accounting rejects totals above wire limit");
  check(rtps::evaluateResourceLimitsAfterEviction(
            3, 150, 80, 1, 100, 3, 130) ==
            ResourceLimitDecision::ACCEPT,
        "post-eviction projection uses the exact removed byte prefix");
  check(rtps::evaluateResourceLimitsAfterEviction(
            3, 150, 81, 1, 100, 3, 130) ==
            ResourceLimitDecision::BYTE_LIMIT,
        "post-eviction projection rejects the first byte over its bound");
  check(rtps::evaluateResourceLimitsAfterEviction(
            2, 100, 1, 3, 100, 0, 0) ==
            ResourceLimitDecision::SAMPLE_LIMIT,
        "invalid eviction count fails closed without sample underflow");
  check(rtps::evaluateResourceLimitsAfterEviction(
            2, 100, 1, 1, 101, 0, 0) ==
            ResourceLimitDecision::BYTE_LIMIT,
        "invalid eviction bytes fail closed without byte underflow");
  check(rtps::evaluateHistoryCapacity(false, true) ==
            HistoryCapacityDecision::ACCEPT,
        "non-full history accepts independently of policy");
  check(rtps::evaluateHistoryCapacity(true, true) ==
            HistoryCapacityDecision::REJECT,
        "KEEP_ALL rejects when capacity is full");
  check(rtps::evaluateHistoryCapacity(true, false) ==
            HistoryCapacityDecision::EVICT_OLDEST,
        "KEEP_LAST evicts the oldest sample when capacity is full");
  check(rtps::plannedKeepLastEvictions(2, 2, false, false) == 1,
        "KEEP_LAST depth plans one replacement eviction");
  check(rtps::plannedKeepLastEvictions(4, 2, false, false) == 3,
        "KEEP_LAST repairs an over-depth retained window atomically");
  check(rtps::plannedKeepLastEvictions(3, 0, true, false) == 1,
        "physical capacity plans one KEEP_LAST eviction");
  check(rtps::plannedKeepLastEvictions(3, 2, true, true) == 0,
        "KEEP_ALL never plans a destructive eviction");
  const uint32_t projectedSamples =
      2 - rtps::plannedKeepLastEvictions(2, 2, false, false);
  check(rtps::evaluateResourceLimits(projectedSamples, 64, 64, 2, 128) ==
            ResourceLimitDecision::ACCEPT,
        "resource limits evaluate the post-eviction KEEP_LAST projection");
  check(rtps::normalizedHistoryDepth(
            rtps::HISTORY_KIND_KEEP_LAST, 0) == 1,
        "legacy KEEP_LAST depth zero normalizes to one");
  check(rtps::embeddedWriterQosSupported(
            true, rtps::ReliabilityKind_t::RELIABLE,
            rtps::DurabilityKind_t::TRANSIENT_LOCAL,
            rtps::HISTORY_KIND_KEEP_LAST, 4, 4, 4, 10, 20, 30),
        "bounded Reliable Writer QoS is accepted");
  check(!rtps::embeddedWriterQosSupported(
             true, rtps::ReliabilityKind_t::BEST_EFFORT,
             rtps::DurabilityKind_t::VOLATILE,
             rtps::HISTORY_KIND_KEEP_LAST, 1, 4, 0, 0, 0, 0),
        "Writer reliability selector mismatch is rejected");
  check(!rtps::embeddedWriterQosSupported(
             false, rtps::ReliabilityKind_t::BEST_EFFORT,
             rtps::DurabilityKind_t::VOLATILE,
             rtps::HISTORY_KIND_KEEP_LAST, 5, 4, 0, 0, 0, 0),
        "Writer depth above physical capacity is rejected");
  check(!rtps::embeddedWriterQosSupported(
             false, rtps::ReliabilityKind_t::BEST_EFFORT,
             rtps::DurabilityKind_t::VOLATILE,
             rtps::HISTORY_KIND_KEEP_LAST, 2, 4, 1, 0, 0, 0),
        "Writer max_samples below KEEP_LAST depth is rejected");
  check(!rtps::embeddedWriterQosSupported(
             false, rtps::ReliabilityKind_t::BEST_EFFORT,
             rtps::DurabilityKind_t::VOLATILE,
             rtps::HISTORY_KIND_KEEP_LAST, 1, 4, 0, 1, 0, 0),
        "Best Effort Writer finite time policy is rejected");
  check(rtps::embeddedReaderQosSupported(
            true, rtps::ReliabilityKind_t::RELIABLE,
            rtps::DurabilityKind_t::VOLATILE,
            rtps::HISTORY_KIND_KEEP_ALL, 255, 1, 2, 3),
        "Reliable Reader supported QoS subset is accepted");
  check(!rtps::embeddedReaderQosSupported(
             false, rtps::ReliabilityKind_t::BEST_EFFORT,
             rtps::DurabilityKind_t::VOLATILE,
             rtps::HISTORY_KIND_KEEP_LAST, 1, 0, 0, 1),
        "Best Effort Reader finite time policy is rejected");
  check(!rtps::embeddedReaderQosSupported(
             true, rtps::ReliabilityKind_t::RELIABLE,
             rtps::DurabilityKind_t::PERSISTENT,
             rtps::HISTORY_KIND_KEEP_LAST, 1, 0, 0, 0),
        "unsupported Reader durability is rejected");
  check(!rtps::embeddedWriterQosSupported(
             true, rtps::ReliabilityKind_t::RELIABLE,
             rtps::DurabilityKind_t::VOLATILE,
             rtps::HISTORY_KIND_KEEP_ALL, 256, 4, 0, 0, 0, 0),
        "Writer rejects unrepresentable KEEP_ALL depth metadata");
  check(!rtps::embeddedReaderQosSupported(
             true, rtps::ReliabilityKind_t::RELIABLE,
             rtps::DurabilityKind_t::VOLATILE,
             rtps::HISTORY_KIND_KEEP_ALL, 256, 0, 0, 0),
        "Reader rejects unrepresentable KEEP_ALL depth metadata");

  std::printf("Resource limits: %d/%d passed\n", total - failed, total);
  return failed == 0 ? 0 : 1;
}
