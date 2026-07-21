/* Host-side ownership and failure tests for SimpleHistoryCache. */

#include "rtps/storages/SimpleHistoryCache.h"

#include <cstdint>
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

void test_remove_releases_payloads() {
  rtps::PBufWrapper::resetTestState();
  const uint8_t payload[4] = {1, 2, 3, 4};

  {
    rtps::SimpleHistoryCache<3> history;
    const auto *first = history.addChange(payload, sizeof(payload));
    const auto first_sn = first->sequenceNumber;
    history.addChange(payload, sizeof(payload));
    history.addChange(payload, sizeof(payload));

    check(history.getChangeCount() == 3, "three changes are retained");
    check(rtps::PBufWrapper::liveBytes() == 12,
          "three payload buffers are owned");

    history.removeUntilIncl(first_sn);
    check(history.getChangeCount() == 2, "partial remove updates history count");
    check(rtps::PBufWrapper::liveBytes() == 8,
          "partial remove releases the removed payload");

    history.removeUntilIncl(history.getSeqNumMax());
    check(history.getChangeCount() == 0, "remove-all empties history");
    check(rtps::PBufWrapper::liveBytes() == 0,
          "remove-all releases every payload immediately");
  }

  check(rtps::PBufWrapper::liveBytes() == 0,
        "history destruction leaves no payload ownership");
}

void test_failures_do_not_advance_history() {
  rtps::PBufWrapper::resetTestState();
  const uint8_t payload[4] = {1, 2, 3, 4};
  rtps::SimpleHistoryCache<3> history;

  rtps::PBufWrapper::failNextReserve();
  check(history.addChange(payload, sizeof(payload)) == nullptr,
        "reserve failure rejects the change");
  check(history.getChangeCount() == 0,
        "reserve failure does not advance history");
  check(rtps::PBufWrapper::liveBytes() == 0,
        "reserve failure retains no payload");

  rtps::PBufWrapper::failNextAppend();
  check(history.addChange(payload, sizeof(payload)) == nullptr,
        "append failure rejects the change");
  check(history.getChangeCount() == 0,
        "append failure does not advance history");
  check(rtps::PBufWrapper::liveBytes() == 0,
        "append failure releases temporary allocation");

  const auto *accepted = history.addChange(payload, sizeof(payload));
  check(accepted != nullptr, "change succeeds after injected failures");
  check(accepted != nullptr && accepted->sequenceNumber.low == 1,
        "failed changes do not consume sequence numbers");
}

void test_wraparound_releases_evicted_slot() {
  rtps::PBufWrapper::resetTestState();
  const uint8_t payload[4] = {1, 2, 3, 4};

  {
    rtps::SimpleHistoryCache<3> history;
    history.addChange(payload, sizeof(payload));
    history.addChange(payload, sizeof(payload));
    history.addChange(payload, sizeof(payload));
    history.addChange(payload, sizeof(payload));

    check(history.getChangeCount() == 3,
          "capacity overflow retains exactly three changes");
    check(history.getSeqNumMin().low == 2,
          "capacity overflow evicts the oldest sequence");
    check(rtps::PBufWrapper::liveBytes() == 12,
          "capacity overflow releases the evicted payload");
  }

  check(rtps::PBufWrapper::liveBytes() == 0,
        "wrapped history destruction releases all payloads");
}

void test_keep_last_window_order() {
  rtps::PBufWrapper::resetTestState();
  const uint8_t payload[4] = {1, 2, 3, 4};
  rtps::SimpleHistoryCache<5> history;
  constexpr uint16_t depth = 2;

  for (int index = 0; index < 4; ++index) {
    while (history.getChangeCount() >= depth) {
      history.dropOldest();
    }
    history.addChange(payload, sizeof(payload));
  }

  check(history.getChangeCount() == depth,
        "KEEP_LAST retains exactly the configured depth");
  check(history.getSeqNumMin() == rtps::SequenceNumber_t{0, 3} &&
            history.getSeqNumMax() == rtps::SequenceNumber_t{0, 4},
        "KEEP_LAST retains the newest sequence window");
  const auto *third = history.getChangeBySN({0, 3});
  const auto *fourth = history.getChangeBySN({0, 4});
  check(third != nullptr && fourth != nullptr &&
            third->sequenceNumber < fourth->sequenceNumber,
        "retained history is retrievable in ascending sequence order");
}

}  // namespace

int main() {
  test_remove_releases_payloads();
  test_failures_do_not_advance_history();
  test_wraparound_releases_evicted_slot();
  test_keep_last_window_order();

  std::printf("Simple history ownership: %d/%d passed\n",
              total - failed, total);
  return failed == 0 ? 0 : 1;
}
