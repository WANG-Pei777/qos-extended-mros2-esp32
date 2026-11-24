#ifndef RTPS_RESOURCE_LIMITS_H
#define RTPS_RESOURCE_LIMITS_H

#include <cstdint>

namespace rtps {

enum class ResourceLimitDecision {
  ACCEPT,
  SAMPLE_LIMIT,
  BYTE_LIMIT,
};

enum class HistoryCapacityDecision {
  ACCEPT,
  REJECT,
  EVICT_OLDEST,
};

inline ResourceLimitDecision evaluateResourceLimits(
    uint32_t currentSamples, uint64_t currentBytes, uint64_t incomingBytes,
    uint32_t maxSamples, uint32_t maxBytes) {
  if (maxSamples > 0 && currentSamples >= maxSamples) {
    return ResourceLimitDecision::SAMPLE_LIMIT;
  }
  if (maxBytes > 0 &&
      (incomingBytes > maxBytes || currentBytes > maxBytes - incomingBytes)) {
    return ResourceLimitDecision::BYTE_LIMIT;
  }
  return ResourceLimitDecision::ACCEPT;
}

inline ResourceLimitDecision evaluateResourceLimitsAfterEviction(
    uint32_t currentSamples, uint64_t currentBytes, uint64_t incomingBytes,
    uint32_t plannedEvictions, uint64_t plannedEvictedBytes,
    uint32_t maxSamples, uint32_t maxBytes) {
  // Fail closed if History accounting and the proposed eviction window do not
  // agree. In particular, never allow unsigned projection underflow to turn a
  // corrupted/invalid plan into apparent spare capacity.
  if (plannedEvictions > currentSamples) {
    return ResourceLimitDecision::SAMPLE_LIMIT;
  }
  if (plannedEvictedBytes > currentBytes) {
    return ResourceLimitDecision::BYTE_LIMIT;
  }
  return evaluateResourceLimits(
      currentSamples - plannedEvictions,
      currentBytes - plannedEvictedBytes,
      incomingBytes, maxSamples, maxBytes);
}

inline HistoryCapacityDecision evaluateHistoryCapacity(bool full,
                                                       bool keepAll) {
  if (!full) {
    return HistoryCapacityDecision::ACCEPT;
  }
  return keepAll ? HistoryCapacityDecision::REJECT
                 : HistoryCapacityDecision::EVICT_OLDEST;
}

inline uint32_t plannedKeepLastEvictions(uint32_t currentSamples,
                                        uint32_t historyDepth,
                                        bool historyFull, bool keepAll) {
  if (keepAll) {
    return 0;
  }
  uint32_t evictions =
      historyDepth > 0 && currentSamples >= historyDepth
          ? currentSamples - historyDepth + 1
          : 0;
  if (historyFull && evictions == 0) {
    evictions = 1;
  }
  return evictions;
}

}  // namespace rtps

#endif  // RTPS_RESOURCE_LIMITS_H
