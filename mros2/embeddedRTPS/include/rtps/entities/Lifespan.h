#ifndef RTPS_LIFESPAN_H
#define RTPS_LIFESPAN_H

#include <cstdint>

namespace rtps {

inline bool lifespanExpired(uint32_t createdAtMs, uint32_t lifespanMs,
                            uint32_t nowMs) {
  return lifespanMs != 0 &&
         static_cast<uint32_t>(nowMs - createdAtMs) >= lifespanMs;
}

} // namespace rtps

#endif // RTPS_LIFESPAN_H
