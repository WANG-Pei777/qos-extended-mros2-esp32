#include <cstdint>
#include <iostream>

#include "rtps/entities/Lifespan.h"

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
  expect(!rtps::lifespanExpired(100, 0, 100000),
         "disabled lifespan never expires");
  expect(!rtps::lifespanExpired(100, 50, 149),
         "sample remains valid before boundary");
  expect(rtps::lifespanExpired(100, 50, 150),
         "sample expires at boundary");
  expect(rtps::lifespanExpired(100, 50, 151),
         "sample remains expired after boundary");
  expect(!rtps::lifespanExpired(0, 50, 49),
         "boot-time timestamp is valid");
  expect(rtps::lifespanExpired(0, 50, 50),
         "boot-time sample expires normally");
  expect(!rtps::lifespanExpired(UINT32_MAX - 9, 20, 5),
         "clock wrap preserves pre-boundary age");
  expect(rtps::lifespanExpired(UINT32_MAX - 9, 20, 10),
         "clock wrap preserves expiry boundary");

  std::cout << "Lifespan tests: " << passed << " passed, " << failed
            << " failed\n";
  return failed == 0 ? 0 : 1;
}
