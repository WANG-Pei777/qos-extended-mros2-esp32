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
  rtps::ReliabilityKind_t reliabilityKind;
};

}  // namespace

int main() {
  using rtps::RequestedSequenceAvailability;

  check(!rtps::readerRepairProbeDue(
            true, true, false, false, 1149, 1000, false, 0),
        "Reader repair probe stays silent during ordinary inter-sample gaps");
  check(!rtps::readerRepairProbeDue(
            true, true, false, false, 2000, 1000, false, 0),
        "Reader never requests a future sequence that was not announced");
  check(rtps::readerRepairProbeDue(
            true, true, false, true, 1150, 1000, false, 0),
        "Reader probes a known hole after the bounded silence threshold");
  check(!rtps::readerRepairProbeDue(
            true, true, false, true, 1300, 1000, true, 1150),
        "Reader repair probes are rate limited");
  check(rtps::readerRepairProbeDue(
            true, true, false, true, 1400, 1000, true, 1150),
        "Reader repair probe repeats at the configured period");
  check(!rtps::readerRepairProbeDue(
            true, true, false, true,
            1000 + rtps::READER_REPAIR_WINDOW_MS + 1, 1000, false, 0),
        "Reader repair probing stops after its bounded recovery window");
  check(!rtps::readerRepairProbeDue(
            false, true, false, true, 2000, 1000, false, 0) &&
            !rtps::readerRepairProbeDue(
                true, false, false, true, 2000, 1000, false, 0) &&
            !rtps::readerRepairProbeDue(
                true, true, true, true, 2000, 1000, false, 0),
        "Best Effort, inactive, and exhausted Readers never probe");

  check(rtps::readerHeartbeatSolicitationDue(
            true, true, false, false, false, 1150, 1000, false, 0),
        "silent Reliable Reader solicits a HEARTBEAT without requesting DATA");
  check(!rtps::readerHeartbeatSolicitationDue(
            true, true, false, true, false, 1150, 1000, false, 0),
        "known hole uses the repair bitmap instead of heartbeat solicitation");
  check(!rtps::readerHeartbeatSolicitationDue(
            true, true, false, false, false, 1300, 1000, true, 1150) &&
            rtps::readerHeartbeatSolicitationDue(
                true, true, false, false, false, 1400, 1000, true, 1150),
        "heartbeat solicitations use the same bounded rate limit");
  check(!rtps::readerHeartbeatSolicitationDue(
            true, true, false, false, false,
            1000 + rtps::READER_REPAIR_WINDOW_MS + 1, 1000, false, 0),
        "heartbeat solicitation stops after the recovery window");
  check(!rtps::readerHeartbeatSolicitationDue(
            false, true, false, false, false, 2000, 1000, false, 0) &&
            !rtps::readerHeartbeatSolicitationDue(
                true, false, false, false, false, 2000, 1000, false, 0) &&
            !rtps::readerHeartbeatSolicitationDue(
                true, true, true, false, false, 2000, 1000, false, 0),
        "Best Effort, inactive, and exhausted Readers never solicit");
  check(!rtps::readerHeartbeatSolicitationDue(
            true, true, false, false, true, 2000, 1000, false, 0),
        "a solicited caught-up HEARTBEAT suppresses further idle probes");

  check(!rtps::readerNeedsPeriodicHeartbeat(
            rtps::SEQUENCENUMBER_UNKNOWN,
            rtps::SEQUENCENUMBER_UNKNOWN, false, false,
            rtps::SEQUENCENUMBER_UNKNOWN),
        "never-written Writer emits no periodic heartbeat");
  check(rtps::readerNeedsPeriodicHeartbeat(
            {0, 7}, rtps::SEQUENCENUMBER_UNKNOWN, false, false,
            rtps::SEQUENCENUMBER_UNKNOWN),
        "new Reliable Reader receives a heartbeat for retained data");
  check(rtps::readerNeedsPeriodicHeartbeat(
            {0, 7}, rtps::SEQUENCENUMBER_UNKNOWN, false, true, {0, 6}),
        "Reader behind the Writer continues receiving heartbeats");
  check(!rtps::readerNeedsPeriodicHeartbeat(
             {0, 7}, rtps::SEQUENCENUMBER_UNKNOWN, false, true, {0, 7}),
        "fully acknowledged Reader suppresses idle heartbeats");
  check(!rtps::readerNeedsPeriodicHeartbeat(
             {0, 7}, {0, 8}, false, false,
             rtps::SEQUENCENUMBER_UNKNOWN),
        "Volatile Reader with no relevant sample emits no heartbeat");
  check(!rtps::readerNeedsPeriodicHeartbeat(
             {INT32_MAX, UINT32_MAX}, {INT32_MAX, UINT32_MAX}, true, false,
             rtps::SEQUENCENUMBER_UNKNOWN),
        "sequence-exhausted Reader emits no heartbeat");

  bool transmissionHeld = false;
  check(rtps::applyTransmissionHold(true, transmissionHeld) ==
            rtps::TransmissionHoldTransition::HELD &&
            transmissionHeld,
        "first hold request enters the held state");
  check(rtps::applyTransmissionHold(true, transmissionHeld) ==
            rtps::TransmissionHoldTransition::NO_CHANGE &&
            transmissionHeld,
        "repeated hold request is idempotent");
  check(rtps::applyTransmissionHold(false, transmissionHeld) ==
            rtps::TransmissionHoldTransition::RELEASED &&
            !transmissionHeld,
        "release request reports the held-to-running transition");
  check(rtps::applyTransmissionHold(false, transmissionHeld) ==
            rtps::TransmissionHoldTransition::NO_CHANGE &&
            !transmissionHeld,
        "repeated release cannot rewind retained delivery");
  check(rtps::ackNackSequenceResponseBudgetAvailable(0) &&
            rtps::ackNackSequenceResponseBudgetAvailable(
                rtps::ACKNACK_SEQUENCE_RESPONSE_BUDGET - 1) &&
            !rtps::ackNackSequenceResponseBudgetAvailable(
                rtps::ACKNACK_SEQUENCE_RESPONSE_BUDGET),
        "one ACKNACK has an explicit bounded sequence-response budget");
  uint32_t ackNackResponseAttempts = 0;
  bool reservedAllBudgetedResponses = true;
  for (uint32_t index = 0;
       index < rtps::ACKNACK_SEQUENCE_RESPONSE_BUDGET; ++index) {
    reservedAllBudgetedResponses &=
        rtps::tryReserveAckNackSequenceResponse(ackNackResponseAttempts);
  }
  check(reservedAllBudgetedResponses &&
            ackNackResponseAttempts ==
                rtps::ACKNACK_SEQUENCE_RESPONSE_BUDGET &&
            !rtps::tryReserveAckNackSequenceResponse(
                ackNackResponseAttempts) &&
            ackNackResponseAttempts ==
                rtps::ACKNACK_SEQUENCE_RESPONSE_BUDGET,
        "ACKNACK reservation admits the configured budget and defers the next");

  check(rtps::countIsNewer({1}, {0}),
        "Count accepts the ordinary next value");
  check(!rtps::countIsNewer({0}, {0}),
        "Count rejects a duplicate value");
  check(!rtps::countIsNewer({9}, {10}),
        "Count rejects the ordinary previous value");
  check(rtps::countIsNewer({INT32_MIN}, {INT32_MAX}),
        "Count accepts INT32_MAX to INT32_MIN wrap");
  check(!rtps::countIsNewer({INT32_MAX}, {INT32_MIN}),
        "Count rejects the pre-wrap value after wrap");
  check(rtps::nextCount({INT32_MAX}).value == INT32_MIN,
        "Count increment wraps without signed overflow");
  check(rtps::countIsAdmissible(false, {INT32_MIN}, {0}),
        "first observed Count establishes a baseline at any wire value");
  check(!rtps::countIsAdmissible(true, {INT32_MIN}, {0}),
        "half-range Count remains ambiguous after a baseline exists");
  bool hasCount = true;
  rtps::Count_t currentCount{11};
  check(rtps::rollbackCountIfCurrent(
            {11}, true, {10}, hasCount, currentCount) &&
            hasCount && currentCount.value == 10,
        "failed control send rolls back its admitted Count");
  hasCount = true;
  currentCount = {12};
  check(!rtps::rollbackCountIfCurrent(
             {11}, true, {10}, hasCount, currentCount) &&
            hasCount && currentCount.value == 12,
        "Count rollback cannot overwrite a newer concurrent heartbeat");
  hasCount = true;
  currentCount = {INT32_MIN};
  check(rtps::rollbackCountIfCurrent(
            {INT32_MIN}, true, {INT32_MAX}, hasCount, currentCount) &&
            currentCount.value == INT32_MAX,
        "failed wrapped Count admission rolls back exactly");
  hasCount = true;
  currentCount = {7};
  check(rtps::rollbackCountIfCurrent(
            {7}, false, {0}, hasCount, currentCount) &&
            !hasCount,
        "failed first Count restores the no-baseline state");
  check(rtps::sequenceNumberSetBitmapWords(0) == 0 &&
            rtps::sequenceNumberSetBitmapWords(1) == 1 &&
            rtps::sequenceNumberSetBitmapWords(rtps::SNS_NUM_BITS) == 1 &&
            rtps::sequenceNumberSetBitmapWords(rtps::SNS_NUM_BITS + 1) == 0,
        "bitmap word sizing is bounded by fixed SequenceNumberSet storage");
  rtps::SequenceNumberSet invalidBitmap;
  invalidBitmap.numBits = rtps::SNS_NUM_BITS + 1;
  invalidBitmap.bitMap[0] = UINT32_MAX;
  check(!invalidBitmap.isSet(rtps::SNS_NUM_BITS),
        "bitmap access beyond fixed storage is never treated as requested");
  rtps::SequenceNumberSet finalAck{{0, 4}};
  check(!rtps::sequenceNumberSetRequestsRepair(finalAck),
        "empty ACKNACK set requires no Writer response");
  finalAck.numBits = 1;
  check(!rtps::sequenceNumberSetRequestsRepair(finalAck),
        "clear ACKNACK bitmap requires no repair");
  finalAck.bitMap[0] = uint32_t{1} << 31;
  check(rtps::sequenceNumberSetRequestsRepair(finalAck),
        "set ACKNACK bitmap requests repair");
  uint64_t serializedBytes = 0;
  check(rtps::fragmentedPublicationValid(true, 512),
        "nonempty fragmented publication contract is valid");
  check(!rtps::fragmentedPublicationValid(false, 512),
        "empty serializer callback is rejected before History admission");
  check(!rtps::fragmentedPublicationValid(true, 0),
        "zero-size fragmented publication is rejected before History admission");
  check(rtps::fragmentedPublicationValid(
            true, rtps::MAX_FRAGMENTED_SAMPLE_SIZE) &&
            !rtps::fragmentedPublicationValid(
                true, uint64_t{rtps::MAX_FRAGMENTED_SAMPLE_SIZE} + 1),
        "fragmented publication accepts the exact 4096-byte bound and rejects excess");
  const uint8_t inlineByte = 0;
  check(rtps::inlinePublicationValid(&inlineByte, 1),
        "nonempty inline publication contract is valid");
  check(!rtps::inlinePublicationValid(nullptr, 1) &&
            !rtps::inlinePublicationValid(&inlineByte, 0),
        "null and zero-size inline publications are rejected");
  check(rtps::inlinePublicationValid(
            &inlineByte, rtps::MAX_UNFRAGMENTED_DATA_PAYLOAD) &&
            !rtps::inlinePublicationValid(
                &inlineByte,
                static_cast<rtps::DataSize_t>(
                    rtps::MAX_UNFRAGMENTED_DATA_PAYLOAD + 1)),
        "inline publication is bounded by RTPS DATA length");
  check(rtps::accountSerializedFragment(512, 256, serializedBytes) &&
            serializedBytes == 256,
        "fragment accounting accepts bytes inside the declared sample");
  check(rtps::serializedFragmentPositionValid(256, 2, serializedBytes),
        "full preceding fragment produces the next nominal wire offset");
  check(!rtps::serializedFragmentPositionValid(256, 3, 384),
        "a short non-final fragment cannot create a wire offset hole");
  check(!rtps::serializedFragmentPositionValid(256, 0, 0),
        "fragment numbering zero is rejected");
  check(rtps::serializedFragmentPositionValid(
            1, rtps::MAX_FRAGMENTS_PER_SAMPLE,
            rtps::MAX_FRAGMENTS_PER_SAMPLE - 1) &&
            !rtps::serializedFragmentPositionValid(
                1, rtps::MAX_FRAGMENTS_PER_SAMPLE + 1,
                rtps::MAX_FRAGMENTS_PER_SAMPLE),
        "fragment numbering accepts 128 and rejects fragment 129 before send");
  check(rtps::accountSerializedFragment(512, 256, serializedBytes) &&
            rtps::serializedSampleComplete(512, serializedBytes, true),
        "fragment accounting recognizes an exact complete sample");
  check(!rtps::accountSerializedFragment(512, 1, serializedBytes),
        "fragment accounting rejects bytes beyond the declared sample");
  check(!rtps::serializedSampleComplete(513, serializedBytes, true),
        "premature serializer termination is not a complete sample");
  check(!rtps::serializedSampleComplete(512, serializedBytes, false),
        "zero-fragment serialization is not a complete sample");
  check(rtps::ordinarySendSnapshotComplete(true, true),
        "all eligible Reader sends complete an ordinary snapshot");
  check(!rtps::ordinarySendSnapshotComplete(true, false),
        "one eligible Reader failure retains the ordinary snapshot");
  check(!rtps::ordinarySendSnapshotComplete(false, true),
        "local UDP rejection cannot complete an ordinary snapshot");
  check(rtps::shouldCountRepairSendFailure(
            false, rtps::RequestedSequenceAvailability::AVAILABLE),
        "available ACKNACK repair failure is counted locally");
  check(!rtps::shouldCountRepairSendFailure(
            true, rtps::RequestedSequenceAvailability::AVAILABLE),
        "held ACKNACK repair is intentional deferral");
  check(!rtps::shouldCountRepairSendFailure(
            false,
            rtps::RequestedSequenceAvailability::NO_LONGER_AVAILABLE),
        "concurrent History eviction converts repair to GAP without failure");
  check(rtps::sendSnapshotStillPending({0, 5}, false, {0, 5}),
        "live cursor still owns its current failed snapshot");
  check(!rtps::sendSnapshotStillPending({0, 6}, false, {0, 5}),
        "concurrent cursor progress suppresses a stale retry");
  check(!rtps::sendSnapshotStillPending(
            {INT32_MAX, UINT32_MAX}, true, {INT32_MAX, UINT32_MAX}),
        "exhausted terminal cursor cannot schedule a stale retry");
  check(rtps::sendCursorTargetsRetainedHistory(
            {0, 6}, false, {0, 6}, {0, 9}),
        "next retained cursor schedules continued History draining");
  check(!rtps::sendCursorTargetsRetainedHistory(
            {0, 10}, false, {0, 6}, {0, 9}),
        "cursor beyond retained History schedules no extra workload");
  check(!rtps::sendCursorTargetsRetainedHistory(
            {INT32_MAX, UINT32_MAX}, true,
            {INT32_MAX, UINT32_MAX}, {INT32_MAX, UINT32_MAX}),
        "exhausted cursor cannot self-schedule terminal History");

  rtps::SequenceNumber_t recoveryCursor{0, 8};
  bool recoveryExhausted = false;
  rtps::retainEarliestSendCursorForRecovery(
      {0, 5}, recoveryCursor, recoveryExhausted);
  check(recoveryCursor == rtps::SequenceNumber_t{0, 5} &&
            !recoveryExhausted,
        "failed first-Reader replay rewinds later ordinary work");
  rtps::retainEarliestSendCursorForRecovery(
      {0, 7}, recoveryCursor, recoveryExhausted);
  check(recoveryCursor == rtps::SequenceNumber_t{0, 5},
        "replay recovery never skips an earlier owned cursor");
  recoveryExhausted = true;
  rtps::retainEarliestSendCursorForRecovery(
      {0, 9}, recoveryCursor, recoveryExhausted);
  check(recoveryCursor == rtps::SequenceNumber_t{0, 9} &&
            !recoveryExhausted,
        "failed replay revives an exhausted cursor at its failed sequence");
  rtps::SequenceNumber_t retrySequence = rtps::SEQUENCENUMBER_UNKNOWN;
  uint8_t retryCount = 0;
  check(rtps::consumeSendRetryBudget(
            {0, 5}, retrySequence, retryCount, 2) &&
            retryCount == 1,
        "first transient send failure consumes one bounded retry");
  check(rtps::consumeSendRetryBudget(
            {0, 5}, retrySequence, retryCount, 2) &&
            retryCount == 2,
        "same sequence may consume its final bounded retry");
  check(!rtps::consumeSendRetryBudget(
            {0, 5}, retrySequence, retryCount, 2),
        "persistent failure cannot schedule an unbounded retry loop");
  check(rtps::consumeSendRetryBudget(
            {0, 6}, retrySequence, retryCount, 2) &&
            retryCount == 1,
        "a new sequence receives a fresh retry budget");
  rtps::clearSendRetryBudget(retrySequence, retryCount);
  check(retrySequence == rtps::SEQUENCENUMBER_UNKNOWN && retryCount == 0,
        "successful progress clears the send retry state");

  check(rtps::readerUsesReliabilityProtocol(
            rtps::ReliabilityKind_t::RELIABLE),
        "RELIABLE Reader uses HEARTBEAT/ACKNACK");
  check(!rtps::readerUsesReliabilityProtocol(
             rtps::ReliabilityKind_t::BEST_EFFORT),
        "BEST_EFFORT Reader skips HEARTBEAT/ACKNACK");
  check(rtps::readerRequestsHistoricalData(
            rtps::DurabilityKind_t::TRANSIENT_LOCAL),
        "TRANSIENT_LOCAL Reader requests historical DATA");
  check(!rtps::readerRequestsHistoricalData(
             rtps::DurabilityKind_t::VOLATILE),
        "VOLATILE Reader does not request historical DATA");
  check(rtps::mayAdvanceGlobalCursorForVolatileMatch(false),
        "first Volatile Reader may advance an otherwise unowned send cursor");
  check(!rtps::mayAdvanceGlobalCursorForVolatileMatch(true),
        "later Volatile Reader cannot skip an existing Reader's send cursor");
  check(rtps::mayAdvanceGlobalCursorAfterDirectedReplay(false),
        "first directed replay may advance an unowned send cursor");
  check(!rtps::mayAdvanceGlobalCursorAfterDirectedReplay(true),
        "later directed replay cannot skip an existing Reader's send cursor");
  check(rtps::shouldScheduleOrdinaryReplayRecovery(false, false),
        "failed first-Reader replay schedules ordinary recovery");
  check(!rtps::shouldScheduleOrdinaryReplayRecovery(false, true),
        "failed later-Reader replay cannot rewind shared ordinary work");
  rtps::SequenceNumber_t firstRelevant = rtps::SEQUENCENUMBER_UNKNOWN;
  bool noRelevant = true;
  rtps::initializeVolatileReaderBoundary(
      {0, 0}, firstRelevant, noRelevant);
  check(firstRelevant == rtps::SequenceNumber_t{0, 1} && !noRelevant,
        "never-written Writer exposes sequence one to a Volatile Reader");
  rtps::initializeVolatileReaderBoundary(
      rtps::SEQUENCENUMBER_UNKNOWN, firstRelevant, noRelevant);
  check(firstRelevant == rtps::SequenceNumber_t{0, 1} && !noRelevant,
        "defensive unknown last-written state also normalizes to sequence one");
  rtps::initializeVolatileReaderBoundary({0, 5}, firstRelevant, noRelevant);
  check(firstRelevant == rtps::SequenceNumber_t{0, 6} && !noRelevant,
        "Volatile Reader boundary starts after an ordinary last sequence");
  rtps::initializeVolatileReaderBoundary(
      {INT32_MAX, UINT32_MAX}, firstRelevant, noRelevant);
  check(firstRelevant ==
            rtps::SequenceNumber_t{INT32_MAX, UINT32_MAX} &&
            noRelevant,
        "only a sequence-exhausted Writer has no future Volatile boundary");
  check(rtps::allReadersSkipSequence(2, false),
        "invisible sequence may advance past two skipping Readers");
  check(!rtps::allReadersSkipSequence(0, false),
        "no matched Reader is not a visibility skip");
  check(!rtps::allReadersSkipSequence(2, true),
        "one eligible Reader prevents visibility-only cursor advance");
  check(rtps::readerMayDeliverBeforeMatch(
            rtps::DurabilityKind_t::VOLATILE,
            rtps::ReliabilityKind_t::RELIABLE),
        "Reliable Volatile Reader may deliver live DATA before matching");
  check(!rtps::readerMayDeliverBeforeMatch(
            rtps::DurabilityKind_t::TRANSIENT_LOCAL,
            rtps::ReliabilityKind_t::RELIABLE),
        "Reliable Transient Local Reader waits for matched replay");
  check(rtps::readerMayDeliverBeforeMatch(
            rtps::DurabilityKind_t::TRANSIENT_LOCAL,
            rtps::ReliabilityKind_t::BEST_EFFORT),
        "Best Effort Transient Local Reader preserves one-shot early replay");
  check(rtps::readerMayReceiveSequence(
            rtps::DurabilityKind_t::TRANSIENT_LOCAL, {0, 4}, {0, 6}),
        "Transient Local Reader may receive pre-match history");
  check(!rtps::readerMayReceiveSequence(
             rtps::DurabilityKind_t::VOLATILE, {0, 4}, {0, 6}),
        "Volatile Reader rejects a pre-match sequence");
  check(rtps::readerMayReceiveSequence(
            rtps::DurabilityKind_t::VOLATILE, {0, 6}, {0, 6}),
        "Volatile Reader accepts its first relevant sequence");
  check(!rtps::readerMayReceiveSequence(
             rtps::DurabilityKind_t::VOLATILE,
             {INT32_MAX, UINT32_MAX}, rtps::SEQUENCENUMBER_UNKNOWN, true),
        "sequence-exhausted Volatile Reader sees no retained sequence");
  check(rtps::shouldReleaseHistoryAfterReaderRemoval(
            rtps::DurabilityKind_t::VOLATILE, 0) &&
            !rtps::shouldReleaseHistoryAfterReaderRemoval(
                rtps::DurabilityKind_t::VOLATILE, 1) &&
            !rtps::shouldReleaseHistoryAfterReaderRemoval(
                rtps::DurabilityKind_t::TRANSIENT_LOCAL, 0),
        "only the last Volatile Reader removal releases old History");
  check(rtps::shouldReleaseHistoryAfterBestEffortSend(
            rtps::DurabilityKind_t::VOLATILE, true) &&
            !rtps::shouldReleaseHistoryAfterBestEffortSend(
                rtps::DurabilityKind_t::VOLATILE, false) &&
            !rtps::shouldReleaseHistoryAfterBestEffortSend(
                rtps::DurabilityKind_t::TRANSIENT_LOCAL, true),
        "only a completed Volatile Best Effort send releases its History");
  check(rtps::shouldReleaseUnmatchedBestEffortHistory(
            rtps::DurabilityKind_t::VOLATILE, 0, 0, true) &&
            !rtps::shouldReleaseUnmatchedBestEffortHistory(
                rtps::DurabilityKind_t::VOLATILE, 0, 1, true) &&
            !rtps::shouldReleaseUnmatchedBestEffortHistory(
                rtps::DurabilityKind_t::VOLATILE, 1, 0, true) &&
            !rtps::shouldReleaseUnmatchedBestEffortHistory(
                rtps::DurabilityKind_t::TRANSIENT_LOCAL, 0, 0, true),
        "unmatched Volatile Best Effort History releases only after a live recheck");
  check(!rtps::shouldReleaseUnmatchedBestEffortHistory(
            rtps::DurabilityKind_t::VOLATILE, 0, 0, false),
        "stale no-Reader workload cannot advance an unretained sequence");
  check(rtps::shouldReleaseUnmatchedReliableFallbackHistory(
            rtps::DurabilityKind_t::VOLATILE, 0, 0, true, true) &&
            !rtps::shouldReleaseUnmatchedReliableFallbackHistory(
                rtps::DurabilityKind_t::VOLATILE, 0, 0, true, false) &&
            !rtps::shouldReleaseUnmatchedReliableFallbackHistory(
                rtps::DurabilityKind_t::VOLATILE, 0, 1, true, true) &&
            !rtps::shouldReleaseUnmatchedReliableFallbackHistory(
                rtps::DurabilityKind_t::TRANSIENT_LOCAL, 0, 0, true, true),
        "unmatched Reliable Volatile fallback releases only after successful send");

  rtps::SequenceNumber_t firstSN{};
  rtps::SequenceNumber_t lastSN{};
  check(rtps::sequenceAfter({0, 1}, firstSN) &&
            firstSN == rtps::SequenceNumber_t{0, 2},
        "Volatile Reader boundary starts after the last written sequence");
  check(rtps::heartbeatSequenceRangeForReader(
            {0, 1}, {0, 1}, {0, 1}, {0, 2}, firstSN, lastSN) &&
            firstSN == rtps::SequenceNumber_t{0, 2} &&
            lastSN == rtps::SequenceNumber_t{0, 1},
        "late Volatile Reader receives an empty HEARTBEAT range");
  check(rtps::heartbeatSequenceRangeForReader(
            {0, 1}, {0, 2}, {0, 2}, {0, 2}, firstSN, lastSN) &&
            firstSN == rtps::SequenceNumber_t{0, 2} &&
            lastSN == rtps::SequenceNumber_t{0, 2},
        "Volatile Reader HEARTBEAT begins at its first relevant sequence");
  check(!rtps::heartbeatSequenceRangeForReader(
             {0, 1}, {0, 2}, {0, 2}, {0, 4}, firstSN, lastSN),
        "invalid far-future Reader boundary cannot form a HEARTBEAT range");
  check(rtps::classifyRequestedSequenceForReader(
            {0, 1}, {0, 1}, {0, 2}, {0, 2}, {0, 2}) ==
            RequestedSequenceAvailability::NO_LONGER_AVAILABLE,
        "Volatile Reader cannot repair a pre-match retained sequence");
  check(rtps::classifyRequestedSequenceForReader(
            {0, 2}, {0, 1}, {0, 2}, {0, 2}, {0, 2}) ==
            RequestedSequenceAvailability::AVAILABLE,
        "Volatile Reader can repair a post-match retained sequence");
  check(rtps::classifyRequestedSequenceForReader(
            {INT32_MAX, UINT32_MAX}, {0, 1}, {INT32_MAX, UINT32_MAX},
            {INT32_MAX, UINT32_MAX}, rtps::SEQUENCENUMBER_UNKNOWN, true) ==
            RequestedSequenceAvailability::NO_LONGER_AVAILABLE,
        "sequence-exhausted Volatile Reader cannot repair retained history");
  check(!rtps::heartbeatSequenceRangeForReader(
            {0, 1}, {INT32_MAX, UINT32_MAX}, {INT32_MAX, UINT32_MAX},
            rtps::SEQUENCENUMBER_UNKNOWN, firstSN, lastSN, true),
        "sequence-exhausted Volatile Reader emits no invalid HEARTBEAT range");
  check(rtps::heartbeatSequenceRange(
            {0, 6}, {0, 10}, {0, 10}, firstSN, lastSN) &&
            firstSN == rtps::SequenceNumber_t{0, 6} &&
            lastSN == rtps::SequenceNumber_t{0, 10},
        "HEARTBEAT announces retained minimum through last written");
  check(rtps::heartbeatSequenceRange(
            rtps::SEQUENCENUMBER_UNKNOWN, rtps::SEQUENCENUMBER_UNKNOWN,
            {0, 0}, firstSN, lastSN) &&
            firstSN == rtps::SequenceNumber_t{0, 1} &&
            lastSN == rtps::SequenceNumber_t{0, 0},
        "never-written Writer announces the DDSI-RTPS empty range 1,0");
  check(rtps::heartbeatSequenceRange(
            rtps::SEQUENCENUMBER_UNKNOWN, rtps::SEQUENCENUMBER_UNKNOWN,
            {0, 10}, firstSN, lastSN) &&
            firstSN == rtps::SequenceNumber_t{0, 11} &&
            lastSN == rtps::SequenceNumber_t{0, 10},
        "released history announces next sequence and last written");
  check(rtps::heartbeatSequenceRange(
            rtps::SEQUENCENUMBER_UNKNOWN, rtps::SEQUENCENUMBER_UNKNOWN,
            {1, UINT32_MAX}, firstSN, lastSN) &&
            firstSN == rtps::SequenceNumber_t{2, 0} &&
            lastSN == rtps::SequenceNumber_t{1, UINT32_MAX},
        "empty HEARTBEAT range handles low-word wrap");
  check(!rtps::heartbeatSequenceRange(
            {0, 6}, rtps::SEQUENCENUMBER_UNKNOWN, {0, 10},
            firstSN, lastSN),
        "inconsistent retained history cannot form a HEARTBEAT range");
  check(!rtps::heartbeatSequenceRange(
            rtps::SEQUENCENUMBER_UNKNOWN, rtps::SEQUENCENUMBER_UNKNOWN,
            {INT32_MAX, UINT32_MAX}, firstSN, lastSN),
        "unrepresentable next sequence cannot form a HEARTBEAT range");

  check(rtps::classifyRequestedSequence(
            {0, 3}, rtps::SEQUENCENUMBER_UNKNOWN,
            rtps::SEQUENCENUMBER_UNKNOWN) ==
            RequestedSequenceAvailability::NO_HISTORY,
        "request against empty history is classified explicitly");
  check(rtps::classifyRequestedSequence({0, 2}, {0, 3}, {0, 5}) ==
            RequestedSequenceAvailability::NO_LONGER_AVAILABLE,
        "request below retained window is no longer available");
  check(rtps::classifyRequestedSequence({0, 4}, {0, 3}, {0, 5}) ==
            RequestedSequenceAvailability::AVAILABLE,
        "request inside retained window is available");
  check(rtps::classifyRequestedSequence({0, 6}, {0, 3}, {0, 5}) ==
            RequestedSequenceAvailability::NOT_YET_WRITTEN,
        "request above retained window is not yet written");
  check(rtps::classifyRequestedSequence(
            {0, 3}, rtps::SEQUENCENUMBER_UNKNOWN,
            rtps::SEQUENCENUMBER_UNKNOWN, {0, 5}) ==
            RequestedSequenceAvailability::NO_LONGER_AVAILABLE,
        "empty retained history still identifies an old written sequence");
  check(rtps::classifyRequestedSequence(
            {0, 6}, rtps::SEQUENCENUMBER_UNKNOWN,
            rtps::SEQUENCENUMBER_UNKNOWN, {0, 5}) ==
            RequestedSequenceAvailability::NOT_YET_WRITTEN,
        "empty retained history does not GAP a future sequence");

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

  bool hasAck = false;
  rtps::SequenceNumber_t monotonicAck = rtps::SEQUENCENUMBER_UNKNOWN;
  check(!rtps::advanceCumulativeAckBounded(
            rtps::SequenceNumberSet{{0, 100}},
            rtps::SEQUENCENUMBER_UNKNOWN, hasAck, monotonicAck) &&
            !hasAck &&
            monotonicAck == rtps::SEQUENCENUMBER_UNKNOWN,
        "ACK before first publication establishes no cumulative boundary");
  check(rtps::advanceCumulativeAck(
            rtps::SequenceNumberSet{{0, 6}}, hasAck, monotonicAck) &&
            hasAck && monotonicAck == rtps::SequenceNumber_t{0, 5},
        "first cumulative ACK establishes the Reader release boundary");
  check(!rtps::advanceCumulativeAck(
            rtps::SequenceNumberSet{}, hasAck, monotonicAck) &&
            hasAck && monotonicAck == rtps::SequenceNumber_t{0, 5},
        "later preemptive ACKNACK cannot clear an established boundary");
  check(!rtps::advanceCumulativeAck(
            rtps::SequenceNumberSet{{0, 4}}, hasAck, monotonicAck) &&
            monotonicAck == rtps::SequenceNumber_t{0, 5},
        "cumulative Reader boundary cannot move backwards");
  check(rtps::advanceCumulativeAck(
            rtps::SequenceNumberSet{{0, 8}}, hasAck, monotonicAck) &&
            monotonicAck == rtps::SequenceNumber_t{0, 7},
        "cumulative Reader boundary advances on a higher ACK base");

  bool hasBoundedAck = false;
  rtps::SequenceNumber_t boundedAck = rtps::SEQUENCENUMBER_UNKNOWN;
  check(rtps::advanceCumulativeAckBounded(
            rtps::SequenceNumberSet{{0, 100}}, {0, 3},
            hasBoundedAck, boundedAck) &&
            boundedAck == rtps::SequenceNumber_t{0, 3},
        "future cumulative ACK is capped at the last written sequence");
  check(boundedAck == rtps::SequenceNumber_t{0, 3},
        "old future ACK does not pre-ack a subsequently written sequence");
  check(rtps::advanceCumulativeAckBounded(
            rtps::SequenceNumberSet{{0, 5}}, {0, 4},
            hasBoundedAck, boundedAck) &&
            boundedAck == rtps::SequenceNumber_t{0, 4},
        "a later ACK explicitly confirms the new written sequence");

  rtps::SequenceNumberSet sparse{{0, 10}};
  sparse.numBits = 4;
  sparse.bitMap[0] = 0x50000000U;
  check(rtps::ackNackRequestedSequence(sparse, 1, result) &&
            result == rtps::SequenceNumber_t{0, 11},
        "ACKNACK set bit maps to exactly base plus bitmap index");
  check(!rtps::ackNackRequestedSequence(sparse, 0, result),
        "ACKNACK clear bitmap bit does not request repair");
  check(rtps::ackNackRequestedSequence(sparse, 3, result) &&
            result == rtps::SequenceNumber_t{0, 13},
        "ACKNACK sparse high bit maps without requesting intervening samples");
  check(!rtps::ackNackRequestedSequence(sparse, 4, result),
        "ACKNACK index at numBits boundary is rejected");
  rtps::SequenceNumberSet bitmap_wrap{{1, UINT32_MAX}};
  bitmap_wrap.numBits = 2;
  bitmap_wrap.bitMap[0] = 0x40000000U;
  check(rtps::ackNackRequestedSequence(bitmap_wrap, 1, result) &&
            result == rtps::SequenceNumber_t{2, 0},
        "ACKNACK bitmap sequence mapping handles low-word wrap");
  rtps::SequenceNumberSet terminalBitmap{{INT32_MAX, UINT32_MAX}};
  terminalBitmap.numBits = 2;
  terminalBitmap.bitMap[0] = uint32_t{0xC0000000};
  check(rtps::ackNackRequestedSequence(terminalBitmap, 0, result) &&
            result == rtps::SequenceNumber_t{INT32_MAX, UINT32_MAX},
        "ACKNACK bit zero may request the final representable sequence");
  check(!rtps::ackNackRequestedSequence(terminalBitmap, 1, result),
        "ACKNACK offset beyond the final sequence is unrepresentable");

  std::vector<ReaderAckState> readers;
  check(!rtps::reliableReaderReleaseBoundary(
            readers, rtps::SEQUENCENUMBER_UNKNOWN, result),
        "empty reader set with no sent sample has no release boundary");
  readers = {
      {{0, 8}, true, rtps::ReliabilityKind_t::RELIABLE},
      {{0, 4}, false, rtps::ReliabilityKind_t::RELIABLE},
  };
  check(!rtps::reliableReaderReleaseBoundary(
            readers, {0, 8}, result),
        "history waits until every reader has acknowledged");
  readers[1].hasAcknowledgedThrough = true;
  check(rtps::reliableReaderReleaseBoundary(readers, {0, 8}, result),
        "fully acknowledged reader set has a release boundary");
  check(result == rtps::SequenceNumber_t{0, 4},
        "history release uses the slowest reader boundary");
  readers[1] = {
      rtps::SEQUENCENUMBER_UNKNOWN, false,
      rtps::ReliabilityKind_t::BEST_EFFORT,
  };
  check(!rtps::reliableReaderReleaseBoundary(
            readers, rtps::SEQUENCENUMBER_UNKNOWN, result),
        "mixed readers wait until Best Effort ordinary send completes");
  check(rtps::reliableReaderReleaseBoundary(readers, {0, 8}, result) &&
            result == rtps::SequenceNumber_t{0, 8},
        "equal Reliable ACK and Best Effort sent-through release together");
  check(rtps::reliableReaderReleaseBoundary(readers, {0, 6}, result) &&
            result == rtps::SequenceNumber_t{0, 6},
        "mixed release uses the earlier Best Effort sent-through boundary");
  readers = {{
      rtps::SEQUENCENUMBER_UNKNOWN, false,
      rtps::ReliabilityKind_t::BEST_EFFORT,
  }};
  check(rtps::reliableReaderReleaseBoundary(readers, {0, 3}, result) &&
            result == rtps::SequenceNumber_t{0, 3},
        "BEST_EFFORT-only release advances through the sent sequence");

  check(rtps::shouldDiscardUnmatchedHistoryOnReaderMatch(
            rtps::DurabilityKind_t::VOLATILE, false),
        "first Volatile reader discards unmatched history");
  check(!rtps::shouldDiscardUnmatchedHistoryOnReaderMatch(
             rtps::DurabilityKind_t::TRANSIENT_LOCAL, false),
        "Transient Local reader retains unmatched history");
  check(!rtps::shouldDiscardUnmatchedHistoryOnReaderMatch(
             rtps::DurabilityKind_t::VOLATILE, true),
        "additional Volatile reader preserves active-reader history");

  rtps::SequenceNumber_t cursor{0, 5};
  bool cursorExhausted = false;
  rtps::advanceSendCursorAfterSnapshot(cursor, cursorExhausted, {0, 5});
  check(cursor == rtps::SequenceNumber_t{0, 6},
        "completed snapshot advances the send cursor once");
  cursor = {0, 9};
  rtps::advanceSendCursorAfterSnapshot(cursor, cursorExhausted, {0, 5});
  check(cursor == rtps::SequenceNumber_t{0, 9},
        "concurrent History eviction preserves its newer cursor");
  cursor = {0, 4};
  rtps::advanceSendCursorAfterSnapshot(cursor, cursorExhausted, {0, 5});
  check(cursor == rtps::SequenceNumber_t{0, 6},
        "stale send cursor catches up to the completed snapshot");
  cursor = {INT32_MAX, UINT32_MAX};
  rtps::advanceSendCursorAfterSnapshot(
      cursor, cursorExhausted, {INT32_MAX, UINT32_MAX});
  check(cursorExhausted &&
            cursor == rtps::SequenceNumber_t{INT32_MAX, UINT32_MAX},
        "terminal send marks the Writer cursor exhausted without wrapping");

  cursor = rtps::SEQUENCENUMBER_UNKNOWN;
  cursorExhausted = true;
  rtps::resetSendCursorToHistory(
      rtps::SEQUENCENUMBER_UNKNOWN, {0, 0}, cursor, cursorExhausted);
  check(cursor == rtps::SequenceNumber_t{0, 1} && !cursorExhausted,
        "empty never-written History resets the cursor to sequence one");
  rtps::resetSendCursorToHistory(
      rtps::SEQUENCENUMBER_UNKNOWN, {0, 9}, cursor, cursorExhausted);
  check(cursor == rtps::SequenceNumber_t{0, 10} && !cursorExhausted,
        "released empty History resets after the last written sequence");
  rtps::resetSendCursorToHistory(
      {0, 7}, {0, 9}, cursor, cursorExhausted);
  check(cursor == rtps::SequenceNumber_t{0, 7} && !cursorExhausted,
        "nonempty History reset targets its oldest retained sequence");
  rtps::resetSendCursorToHistory(
      rtps::SEQUENCENUMBER_UNKNOWN, {INT32_MAX, UINT32_MAX},
      cursor, cursorExhausted);
  check(cursor == rtps::SequenceNumber_t{INT32_MAX, UINT32_MAX} &&
            cursorExhausted,
        "empty terminal History reset preserves sequence exhaustion");

  rtps::RetryQueueClaim retryClaim;
  check(retryClaim.tryClaim(),
        "first failed-send retry claims one dedicated queue slot");
  check(!retryClaim.tryClaim(),
        "duplicate failed-send retry is coalesced while queued");
  retryClaim.release();
  check(retryClaim.tryClaim(),
        "dequeued retry releases its Writer claim for later failures");
  retryClaim.release();

  std::printf("Reliability state: %d/%d passed\n", total - failed, total);
  return failed == 0 ? 0 : 1;
}
