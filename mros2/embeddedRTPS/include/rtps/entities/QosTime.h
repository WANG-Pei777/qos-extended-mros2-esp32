#ifndef RTPS_QOS_TIME_H
#define RTPS_QOS_TIME_H

#include <cstdint>

namespace rtps {

constexpr uint32_t rtpsFractionFromMilliseconds(uint32_t milliseconds) {
  return static_cast<uint32_t>(
      (static_cast<uint64_t>(milliseconds % 1000) * (UINT64_C(1) << 32) +
       500) /
      1000);
}

inline bool qosTimeReached(uint32_t nowMs, uint32_t targetMs) {
  return static_cast<int32_t>(nowMs - targetMs) >= 0;
}

inline uint32_t deadlineMissedPeriods(uint32_t nowMs, uint32_t nextDeadlineMs,
                                      uint32_t periodMs) {
  if (periodMs == 0 || !qosTimeReached(nowMs, nextDeadlineMs)) {
    return 0;
  }
  return 1 + static_cast<uint32_t>((nowMs - nextDeadlineMs) / periodMs);
}

inline bool qosLeaseAlive(uint32_t lastActivityMs, uint32_t leaseMs,
                          uint32_t nowMs) {
  return leaseMs == 0 ||
         static_cast<uint32_t>(nowMs - lastActivityMs) < leaseMs;
}

} // namespace rtps

#endif // RTPS_QOS_TIME_H
