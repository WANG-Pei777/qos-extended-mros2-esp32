/* Host-side cumulative ACK boundary tests. */

#include "rtps/entities/ReliabilityState.h"
#include "rtps/entities/DurabilityState.h"

#include <cstdint>
#include <cstdio>
#include <vector>

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

struct ReaderAckState {
  rtps::SequenceNumber_t acknowledgedThrough;
  bool hasAcknowledgedThrough;
};

}  // namespace

int main() {
  rtps::SequenceNumber_t result{};
  rtps::SequenceNumberSet preemptive;
  check(!rtps::cumulativeAckThrough(preemptive, result),
        "preemptive ACKNACK has no cumulative ACK boundary");

  rtps::SequenceNumberSet first_missing{{0, 6}};
  check(rtps::cumulativeAckThrough(first_missing, result),
        "nonzero base has a cumulative ACK boundary");
  check(result == rtps::SequenceNumber_t{0, 5},
        "base 6 cumulatively acknowledges through sequence 5");

  rtps::SequenceNumberSet low_wrap{{2, 0}};
  check(rtps::cumulativeAckThrough(low_wrap, result),
        "wrapped base has a cumulative ACK boundary");
  check(result == rtps::SequenceNumber_t{1, UINT32_MAX},
        "cumulative ACK predecessor handles low-word wrap");

  std::vector<ReaderAckState> readers;
  check(!rtps::minimumAcknowledgedThrough(readers, result),
        "empty reader set has no release boundary");
  readers = {{{0, 8}, true}, {{0, 4}, false}};
  check(!rtps::minimumAcknowledgedThrough(readers, result),
        "history waits until every reader has acknowledged");
  readers[1].hasAcknowledgedThrough = true;
  check(rtps::minimumAcknowledgedThrough(readers, result),
        "fully acknowledged reader set has a release boundary");
  check(result == rtps::SequenceNumber_t{0, 4},
        "history release uses the slowest reader boundary");

  check(rtps::shouldDiscardUnmatchedHistoryOnReaderMatch(
            rtps::DurabilityKind_t::VOLATILE, false),
        "first Volatile reader discards unmatched history");
  check(!rtps::shouldDiscardUnmatchedHistoryOnReaderMatch(
             rtps::DurabilityKind_t::TRANSIENT_LOCAL, false),
        "Transient Local reader retains unmatched history");
  check(!rtps::shouldDiscardUnmatchedHistoryOnReaderMatch(
             rtps::DurabilityKind_t::VOLATILE, true),
        "additional Volatile reader preserves active-reader history");

  std::printf("Reliability state: %d/%d passed\n", total - failed, total);
  return failed == 0 ? 0 : 1;
}
