#ifndef RTPS_DISCOVERY_QOSCOMPATIBILITY_H
#define RTPS_DISCOVERY_QOSCOMPATIBILITY_H

#include "rtps/common/types.h"

#include <cstdint>

namespace rtps {

inline bool isSupportedReliabilityKind(ReliabilityKind_t kind) {
  return kind == ReliabilityKind_t::BEST_EFFORT ||
         kind == ReliabilityKind_t::RELIABLE;
}

inline bool isSupportedDurabilityKind(DurabilityKind_t kind) {
  return kind == DurabilityKind_t::VOLATILE ||
         kind == DurabilityKind_t::TRANSIENT_LOCAL;
}

inline bool qosDurationNoGreaterThan(uint32_t offeredSec,
                                     uint32_t offeredFraction,
                                     uint32_t requestedSec,
                                     uint32_t requestedFraction) {
  return offeredSec < requestedSec ||
         (offeredSec == requestedSec &&
          offeredFraction <= requestedFraction);
}

template <typename OfferedEndpoint, typename RequestedEndpoint>
bool qosPoliciesCompatible(const OfferedEndpoint &offered,
                           const RequestedEndpoint &requested) {
  // Never interpret an unsupported numeric policy rank as a stronger offer.
  if (!isSupportedReliabilityKind(offered.reliabilityKind) ||
      !isSupportedReliabilityKind(requested.reliabilityKind) ||
      !isSupportedDurabilityKind(offered.durabilityKind) ||
      !isSupportedDurabilityKind(requested.durabilityKind)) {
    return false;
  }

  if (requested.reliabilityKind == ReliabilityKind_t::RELIABLE &&
      offered.reliabilityKind != ReliabilityKind_t::RELIABLE) {
    return false;
  }

  if (static_cast<uint32_t>(offered.durabilityKind) <
      static_cast<uint32_t>(requested.durabilityKind)) {
    return false;
  }

  if (!qosDurationNoGreaterThan(
          offered.deadlineSec, offered.deadlineFraction,
          requested.deadlineSec, requested.deadlineFraction)) {
    return false;
  }

  if (!qosDurationNoGreaterThan(
          offered.livelinessSec, offered.livelinessFraction,
          requested.livelinessSec, requested.livelinessFraction)) {
    return false;
  }

  return true;
}

} // namespace rtps

#endif // RTPS_DISCOVERY_QOSCOMPATIBILITY_H
