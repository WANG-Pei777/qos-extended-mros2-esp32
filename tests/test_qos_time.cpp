#include <cstdint>
#include <iostream>

#include "rtps/entities/QosTime.h"

namespace {
int passed = 0;
int failed = 0;

void expect(bool condition, const char *name) {
  if (condition) {
    ++passed;
    std::cout << "[PASS] " << name << '\n';
  } else {
    ++failed;
    std::cout << "[FAIL] " << name << '\n';
  }
}
} // namespace

int main() {
  expect(rtps::rtpsFractionFromMilliseconds(0) == 0,
         "zero milliseconds has zero RTPS fraction");
  expect(rtps::rtpsFractionFromMilliseconds(50) == 214748365,
         "50ms rounds to the Fast DDS RTPS fraction");
  expect(rtps::rtpsFractionFromMilliseconds(100) == 429496730,
         "100ms rounds to the Fast DDS RTPS fraction");
  expect(rtps::rtpsFractionFromMilliseconds(500) == 2147483648U,
         "500ms has an exact half-second RTPS fraction");
  expect(rtps::rtpsFractionFromMilliseconds(1000) == 0,
         "whole seconds have zero RTPS fraction");

  expect(rtps::deadlineMissedPeriods(99, 100, 50) == 0,
         "deadline remains pending before boundary");
  expect(rtps::deadlineMissedPeriods(100, 100, 50) == 1,
         "deadline misses at exact boundary");
  expect(rtps::deadlineMissedPeriods(249, 100, 50) == 3,
         "deadline catch-up counts every complete period");
  expect(rtps::deadlineMissedPeriods(1000, 100, 0) == 0,
         "disabled deadline never reports a miss");
  expect(rtps::deadlineMissedPeriods(2, UINT32_MAX - 5, 10) == 1,
         "deadline boundary survives clock wrap");

  expect(rtps::qosLeaseAlive(100, 50, 149),
         "liveliness remains alive before lease boundary");
  expect(!rtps::qosLeaseAlive(100, 50, 150),
         "liveliness is lost at lease boundary");
  expect(rtps::qosLeaseAlive(UINT32_MAX - 9, 20, 5),
         "liveliness age survives clock wrap");
  expect(!rtps::qosLeaseAlive(UINT32_MAX - 9, 20, 10),
         "wrapped liveliness reaches lease boundary");
  expect(rtps::qosLeaseAlive(100, 0, 100000),
         "infinite lease remains alive");

  std::cout << "QoS time tests: " << passed << " passed, " << failed
            << " failed\n";
  return failed == 0 ? 0 : 1;
}
