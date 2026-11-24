/* Host-side ownership and failure tests for SimpleHistoryCache. */

#include "rtps/storages/SimpleHistoryCache.h"

#include <array>
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

void test_fragment_serializer_reset_contract() {
  uint32_t cursor = 7;
  std::array<uint8_t, 2> fragments{11, 22};
  rtps::CacheChange change;
  change.serializerCallback = [&cursor, &fragments](
      rtps::CacheChange::SerializerOperation operation) {
    if (operation == rtps::CacheChange::SerializerOperation::RESET) {
      cursor = 0;
      return rtps::CacheChange::SerializedBuf{nullptr, 0};
    }
    if (cursor >= fragments.size()) {
      return rtps::CacheChange::SerializedBuf{nullptr, 0};
    }
    return rtps::CacheChange::SerializedBuf{&fragments[cursor++], 1};
  };
  change.resetSerializer();
  check(cursor == 0,
        "fragment serializer reset restores the first-fragment cursor");
  const auto firstAttempt = change.serializerCallback(
      rtps::CacheChange::SerializerOperation::NEXT_FRAGMENT);
  change.resetSerializer();
  const auto retry = change.serializerCallback(
      rtps::CacheChange::SerializerOperation::NEXT_FRAGMENT);
  check(firstAttempt.second == 1 && retry.second == 1 &&
            *firstAttempt.first == 11 && *retry.first == 11,
        "aborted fragmented send restarts from the identical first fragment");

  rtps::CacheChange noReset;
  noReset.resetSerializer();
  check(true, "missing fragment reset callback is a safe no-op");
}

void test_fragment_byte_accounting_does_not_wrap() {
  rtps::SimpleHistoryCache<2> history;
  auto serializer = [](rtps::CacheChange::SerializerOperation) {
    return rtps::CacheChange::SerializedBuf{nullptr, 0};
  };
  history.addChange(serializer, UINT32_MAX);
  history.addChange(serializer, 1);
  check(history.getTotalDataBytes() ==
            static_cast<uint64_t>(UINT32_MAX) + 1,
        "fragmented History byte accounting remains exact above UINT32_MAX");
}

void test_oldest_byte_projection_is_exact() {
  rtps::PBufWrapper::resetTestState();
  const uint8_t first[3] = {1, 1, 1};
  const uint8_t second[5] = {2, 2, 2, 2, 2};
  const uint8_t third[7] = {3, 3, 3, 3, 3, 3, 3};
  rtps::SimpleHistoryCache<4> history;
  history.addChange(first, sizeof(first));
  history.addChange(second, sizeof(second));
  history.addChange(third, sizeof(third));

  check(history.getTotalDataBytes() == 15,
        "variable-size History reports its exact retained bytes");
  check(history.getOldestDataBytes(0) == 0 &&
            history.getOldestDataBytes(1) == 3 &&
            history.getOldestDataBytes(2) == 8 &&
            history.getOldestDataBytes(99) == 15,
        "oldest-byte projection follows the exact retained prefix");

  history.removeUntilIncl({0, 2});
  check(history.getChangeCount() == 1 &&
            history.getTotalDataBytes() == 7 &&
            rtps::PBufWrapper::liveBytes() == 7,
        "prefix eviction leaves exact logical and owned byte totals");
}

void test_invalid_fragment_contract_does_not_consume_history() {
  rtps::SimpleHistoryCache<2> history;
  rtps::CacheChange::SerializerCallback empty;
  auto serializer = [](rtps::CacheChange::SerializerOperation) {
    return rtps::CacheChange::SerializedBuf{nullptr, 0};
  };

  check(history.addChange(empty, 16) == nullptr,
        "History rejects an empty fragment serializer");
  check(history.addChange(serializer, 0) == nullptr,
        "History rejects a zero-size fragmented sample");
  rtps::CacheChange invalidKind;
  check(history.commitPreparedChange(std::move(invalidKind)) == nullptr,
        "prepared History rejects an INVALID ChangeKind");
  rtps::CacheChange missingSerializer;
  missingSerializer.kind = rtps::ChangeKind_t::ALIVE;
  missingSerializer.sizeToBeSerialized = 16;
  check(history.commitPreparedChange(std::move(missingSerializer)) == nullptr,
        "prepared History rejects size without a fragment serializer");
  rtps::CacheChange zeroSizeSerializer;
  zeroSizeSerializer.kind = rtps::ChangeKind_t::ALIVE;
  zeroSizeSerializer.serializerCallback = serializer;
  check(history.commitPreparedChange(std::move(zeroSizeSerializer)) == nullptr,
        "prepared History rejects a fragment serializer without size");
  check(history.getChangeCount() == 0 &&
            history.getLastUsedSequenceNumber() ==
                rtps::SequenceNumber_t{0, 0},
        "invalid fragment contracts consume no slot or sequence");
  const auto *accepted = history.addChange(serializer, 1);
  check(accepted != nullptr &&
            accepted->sequenceNumber == rtps::SequenceNumber_t{0, 1},
        "first valid fragment contract receives the first sequence");
}

void test_invalid_inline_contract_does_not_consume_history() {
  rtps::SimpleHistoryCache<2> history;
  const uint8_t payload = 7;

  check(history.addChange(nullptr, 1) == nullptr,
        "History rejects a null inline payload");
  check(history.addChange(&payload, 0) == nullptr,
        "History rejects a zero-size inline payload");
  rtps::CacheChange emptyPrepared;
  emptyPrepared.kind = rtps::ChangeKind_t::ALIVE;
  check(history.commitPreparedChange(std::move(emptyPrepared)) == nullptr,
        "prepared History rejects an empty inline payload");
  check(history.getChangeCount() == 0 &&
            history.getLastUsedSequenceNumber() ==
                rtps::SequenceNumber_t{0, 0},
        "invalid inline contracts consume no slot or sequence");
  const auto *accepted = history.addChange(&payload, 1);
  check(accepted != nullptr &&
            accepted->sequenceNumber == rtps::SequenceNumber_t{0, 1},
        "first valid inline payload receives the first sequence");
}

class BoundaryHistory : public rtps::SimpleHistoryCache<2> {
public:
  explicit BoundaryHistory(rtps::SequenceNumber_t last)
      : rtps::SimpleHistoryCache<2>(last) {}
};

void test_sequence_low_word_wrap_lookup() {
  rtps::PBufWrapper::resetTestState();
  const uint8_t payload[2] = {4, 2};
  BoundaryHistory history({0, UINT32_MAX - 1});

  const auto *beforeWrap = history.addChange(payload, sizeof(payload));
  const auto *afterWrap = history.addChange(payload, sizeof(payload));
  check(beforeWrap != nullptr &&
            beforeWrap->sequenceNumber ==
                rtps::SequenceNumber_t{0, UINT32_MAX},
        "History assigns the final low-word sequence");
  check(afterWrap != nullptr &&
            afterWrap->sequenceNumber == rtps::SequenceNumber_t{1, 0},
        "History increments the high word after low-word wrap");
  check(history.getChangeBySN({0, UINT32_MAX}) != nullptr &&
            history.getChangeBySN({1, 0}) != nullptr,
        "History lookup spans a low-word sequence wrap");
  history.removeUntilIncl({0, UINT32_MAX});
  check(history.getChangeBySN({0, UINT32_MAX}) == nullptr &&
            history.getChangeBySN({1, 0}) != nullptr,
        "History removal preserves the post-wrap suffix");
}

void test_sequence_exhaustion_is_non_destructive() {
  rtps::PBufWrapper::resetTestState();
  const uint8_t payload[2] = {1, 2};
  BoundaryHistory history({INT32_MAX, UINT32_MAX - 1});

  const auto *last = history.addChange(payload, sizeof(payload));
  check(last != nullptr &&
            last->sequenceNumber ==
                rtps::SequenceNumber_t{INT32_MAX, UINT32_MAX},
        "last representable sequence is accepted");
  check(!history.canAddChange(),
        "history reports sequence exhaustion at the wire maximum");
  check(history.addChange(payload, sizeof(payload)) == nullptr,
        "publish beyond the sequence maximum is rejected");
  check(history.getChangeCount() == 1 &&
            history.getSeqNumMin() ==
                rtps::SequenceNumber_t{INT32_MAX, UINT32_MAX},
        "sequence exhaustion leaves retained history unchanged");
  check(rtps::PBufWrapper::liveBytes() == sizeof(payload),
        "sequence-exhaustion rejection releases its prepared payload");
}

}  // namespace

int main() {
  test_remove_releases_payloads();
  test_failures_do_not_advance_history();
  test_wraparound_releases_evicted_slot();
  test_keep_last_window_order();
  test_fragment_serializer_reset_contract();
  test_fragment_byte_accounting_does_not_wrap();
  test_oldest_byte_projection_is_exact();
  test_invalid_fragment_contract_does_not_consume_history();
  test_invalid_inline_contract_does_not_consume_history();
  test_sequence_low_word_wrap_lookup();
  test_sequence_exhaustion_is_non_destructive();

  std::printf("Simple history ownership: %d/%d passed\n",
              total - failed, total);
  return failed == 0 ? 0 : 1;
}
