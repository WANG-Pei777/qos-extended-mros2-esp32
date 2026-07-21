/* Host-side StatefulReader sequence admission tests. */

#include "rtps/entities/ReaderSequence.h"

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
  check(!rtps::readerSequenceIsFresh({0, 6}, {0, 5}),
        "a duplicate sequence below expected is rejected");
  check(rtps::readerSequenceIsFresh({0, 6}, {0, 6}),
        "the exact next sequence is accepted");
  check(rtps::readerSequenceIsFresh({0, 6}, {0, 9}),
        "a forward gap resynchronizes without an invalid history read");
  check(rtps::readerSequenceIsFresh(rtps::SEQUENCENUMBER_UNKNOWN, {0, 1}),
        "an unknown initial sequence accepts the first sample");

  std::printf("Reader sequence: %d/%d passed\n", total - failed, total);
  return failed == 0 ? 0 : 1;
}
