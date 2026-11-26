#ifndef RTPS_ENDPOINT_QOS_VALIDATION_H
#define RTPS_ENDPOINT_QOS_VALIDATION_H

#include "rtps/common/types.h"

#include <cstdint>

namespace rtps {

inline constexpr uint32_t HISTORY_KIND_KEEP_LAST = 0;
inline constexpr uint32_t HISTORY_KIND_KEEP_ALL = 1;
inline constexpr uint32_t MAX_EMBEDDED_HISTORY_DEPTH = UINT8_MAX;

inline uint32_t normalizedHistoryDepth(uint32_t historyKind,
                                       uint32_t historyDepth) {
  return historyKind == HISTORY_KIND_KEEP_LAST && historyDepth == 0
             ? 1
             : historyDepth;
}

inline bool endpointReliabilitySelectionConsistent(
    bool reliable, ReliabilityKind_t reliabilityKind) {
  return reliable
             ? reliabilityKind == ReliabilityKind_t::RELIABLE
             : reliabilityKind == ReliabilityKind_t::BEST_EFFORT;
}

inline bool endpointDurabilitySupported(DurabilityKind_t durabilityKind) {
  return durabilityKind == DurabilityKind_t::VOLATILE ||
         durabilityKind == DurabilityKind_t::TRANSIENT_LOCAL;
}

inline bool endpointHistoryKindSupported(uint32_t historyKind) {
  return historyKind == HISTORY_KIND_KEEP_LAST ||
         historyKind == HISTORY_KIND_KEEP_ALL;
}

inline bool embeddedWriterQosSupported(
    bool reliable, ReliabilityKind_t reliabilityKind,
    DurabilityKind_t durabilityKind, uint32_t historyKind,
    uint32_t historyDepth, uint32_t physicalCapacity,
    uint32_t maxSamples, uint32_t deadlineMs, uint32_t lifespanMs,
    uint32_t livelinessLeaseMs) {
  const uint32_t depth =
      normalizedHistoryDepth(historyKind, historyDepth);
  return endpointReliabilitySelectionConsistent(
             reliable, reliabilityKind) &&
         endpointDurabilitySupported(durabilityKind) &&
         endpointHistoryKindSupported(historyKind) &&
         historyDepth <= MAX_EMBEDDED_HISTORY_DEPTH &&
         physicalCapacity != 0 &&
         (historyKind != HISTORY_KIND_KEEP_LAST ||
          depth <= physicalCapacity) &&
         maxSamples <= physicalCapacity &&
         (historyKind != HISTORY_KIND_KEEP_LAST || maxSamples == 0 ||
          maxSamples >= depth) &&
         (reliable ||
          (deadlineMs == 0 && lifespanMs == 0 &&
           livelinessLeaseMs == 0));
}

inline bool embeddedReaderQosSupported(
    bool reliable, ReliabilityKind_t reliabilityKind,
    DurabilityKind_t durabilityKind, uint32_t historyKind,
    uint32_t historyDepth, uint32_t deadlineMs, uint32_t lifespanMs,
    uint32_t livelinessLeaseMs) {
  return endpointReliabilitySelectionConsistent(
             reliable, reliabilityKind) &&
         endpointDurabilitySupported(durabilityKind) &&
         endpointHistoryKindSupported(historyKind) &&
         historyDepth <= MAX_EMBEDDED_HISTORY_DEPTH &&
         (reliable ||
          (deadlineMs == 0 && lifespanMs == 0 &&
           livelinessLeaseMs == 0));
}

}  // namespace rtps

#endif  // RTPS_ENDPOINT_QOS_VALIDATION_H
