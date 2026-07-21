/* Host-side Liveliness transition-state tests. */

#include "rtps/entities/LivelinessState.h"

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
  using rtps::LivelinessTransition;
  check(rtps::evaluateLivelinessTransition(true, false, false, false, false) ==
            LivelinessTransition::NONE,
        "startup before first activity emits no transition");
  check(rtps::evaluateLivelinessTransition(true, true, true, true, true) ==
            LivelinessTransition::NONE,
        "an alive writer before the lease boundary emits no transition");
  check(rtps::evaluateLivelinessTransition(true, true, true, true, false) ==
            LivelinessTransition::LOST,
        "alive-to-dead crossing emits one lost transition");
  check(rtps::evaluateLivelinessTransition(true, true, true, false, false) ==
            LivelinessTransition::NONE,
        "repeated outage checks emit no duplicate lost transition");
  check(rtps::evaluateLivelinessTransition(true, true, true, false, true) ==
            LivelinessTransition::RECOVERED,
        "first post-outage activity emits one recovered transition");
  check(rtps::evaluateLivelinessTransition(false, true, true, true, false) ==
            LivelinessTransition::NONE,
        "an infinite lease disables liveliness transitions");

  std::printf("Liveliness state: %d/%d passed\n", total - failed, total);
  return failed == 0 ? 0 : 1;
}
