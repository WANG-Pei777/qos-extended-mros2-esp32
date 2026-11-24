#ifndef QOS_TEST_RTPS_TYPES_H
#define QOS_TEST_RTPS_TYPES_H

#include <cstdint>

namespace rtps {

enum class ReliabilityKind_t : uint32_t {
  BEST_EFFORT = 1,
  RELIABLE = 2
};

enum class DurabilityKind_t : uint32_t {
  VOLATILE = 0,
  TRANSIENT_LOCAL = 1,
  TRANSIENT = 2,
  PERSISTENT = 3
};

} // namespace rtps

#endif // QOS_TEST_RTPS_TYPES_H
