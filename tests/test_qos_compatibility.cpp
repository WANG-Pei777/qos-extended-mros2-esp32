/* Host-side requested/offered compatibility tests for endpoint discovery. */

#include "rtps/discovery/QoSCompatibility.h"
#include "rtps/entities/QosTime.h"

#include <cstdint>
#include <cstdio>

namespace {

constexpr uint32_t kInfiniteSec = 0x7FFFFFFF;
constexpr uint32_t kInfiniteFraction = 0xFFFFFFFF;

struct EndpointQos {
  rtps::ReliabilityKind_t reliabilityKind =
      rtps::ReliabilityKind_t::BEST_EFFORT;
  rtps::DurabilityKind_t durabilityKind = rtps::DurabilityKind_t::VOLATILE;
  uint32_t deadlineSec = kInfiniteSec;
  uint32_t deadlineFraction = kInfiniteFraction;
  uint32_t livelinessSec = kInfiniteSec;
  uint32_t livelinessFraction = kInfiniteFraction;
};

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

EndpointQos endpoint(rtps::ReliabilityKind_t reliability,
                     rtps::DurabilityKind_t durability) {
  EndpointQos value;
  value.reliabilityKind = reliability;
  value.durabilityKind = durability;
  return value;
}

void test_reliability() {
  using rtps::DurabilityKind_t;
  using rtps::ReliabilityKind_t;

  const auto best_effort = endpoint(ReliabilityKind_t::BEST_EFFORT,
                                    DurabilityKind_t::VOLATILE);
  const auto reliable = endpoint(ReliabilityKind_t::RELIABLE,
                                 DurabilityKind_t::VOLATILE);

  check(rtps::qosPoliciesCompatible(best_effort, best_effort),
        "BEST_EFFORT offered satisfies BEST_EFFORT request");
  check(rtps::qosPoliciesCompatible(reliable, best_effort),
        "RELIABLE offered satisfies BEST_EFFORT request");
  check(!rtps::qosPoliciesCompatible(best_effort, reliable),
        "BEST_EFFORT offered rejects RELIABLE request");
  check(rtps::qosPoliciesCompatible(reliable, reliable),
        "RELIABLE offered satisfies RELIABLE request");
}

void test_durability() {
  using rtps::DurabilityKind_t;
  using rtps::ReliabilityKind_t;

  const auto volatile_qos = endpoint(ReliabilityKind_t::RELIABLE,
                                     DurabilityKind_t::VOLATILE);
  const auto transient = endpoint(ReliabilityKind_t::RELIABLE,
                                  DurabilityKind_t::TRANSIENT_LOCAL);

  check(rtps::qosPoliciesCompatible(volatile_qos, volatile_qos),
        "VOLATILE offered satisfies VOLATILE request");
  check(rtps::qosPoliciesCompatible(transient, volatile_qos),
        "TRANSIENT_LOCAL offered satisfies VOLATILE request");
  check(!rtps::qosPoliciesCompatible(volatile_qos, transient),
        "VOLATILE offered rejects TRANSIENT_LOCAL request");
  check(rtps::qosPoliciesCompatible(transient, transient),
        "TRANSIENT_LOCAL offered satisfies TRANSIENT_LOCAL request");
}

void test_deadline() {
  auto offered = EndpointQos{};
  auto requested = EndpointQos{};

  offered.deadlineSec = 0;
  offered.deadlineFraction = rtps::rtpsFractionFromMilliseconds(50);
  requested.deadlineSec = 0;
  requested.deadlineFraction = rtps::rtpsFractionFromMilliseconds(100);
  check(rtps::qosPoliciesCompatible(offered, requested),
        "50ms offered deadline satisfies 100ms request");

  offered.deadlineFraction = rtps::rtpsFractionFromMilliseconds(100);
  requested.deadlineFraction = rtps::rtpsFractionFromMilliseconds(50);
  check(!rtps::qosPoliciesCompatible(offered, requested),
        "100ms offered deadline rejects 50ms request");

  offered.deadlineSec = kInfiniteSec;
  offered.deadlineFraction = kInfiniteFraction;
  check(!rtps::qosPoliciesCompatible(offered, requested),
        "infinite offered deadline rejects finite request");
}

void test_liveliness() {
  auto offered = EndpointQos{};
  auto requested = EndpointQos{};

  offered.livelinessSec = 0;
  offered.livelinessFraction = rtps::rtpsFractionFromMilliseconds(500);
  requested.livelinessSec = 2;
  requested.livelinessFraction = 0;
  check(rtps::qosPoliciesCompatible(offered, requested),
        "500ms offered lease satisfies 2s request");

  offered.livelinessSec = 2;
  offered.livelinessFraction = 0;
  requested.livelinessSec = 0;
  requested.livelinessFraction = rtps::rtpsFractionFromMilliseconds(500);
  check(!rtps::qosPoliciesCompatible(offered, requested),
        "2s offered lease rejects 500ms request");

  requested.livelinessSec = kInfiniteSec;
  requested.livelinessFraction = kInfiniteFraction;
  check(rtps::qosPoliciesCompatible(offered, requested),
        "finite offered lease satisfies infinite request");
}

}  // namespace

int main() {
  test_reliability();
  test_durability();
  test_deadline();
  test_liveliness();

  std::printf("Discovery QoS compatibility: %d/%d passed\n",
              total - failed, total);
  return failed == 0 ? 0 : 1;
}
