#ifndef RTPS_RELIABILITY_STATE_H
#define RTPS_RELIABILITY_STATE_H

#include "rtps/common/types.h"

#include <atomic>
#include <cstring>

namespace rtps {

inline constexpr uint8_t SEND_RETRY_LIMIT = 3;

#ifndef MROS2_RTPS_READER_REPAIR_SILENCE_MS
#define MROS2_RTPS_READER_REPAIR_SILENCE_MS 150
#endif
#ifndef MROS2_RTPS_READER_REPAIR_PERIOD_MS
#define MROS2_RTPS_READER_REPAIR_PERIOD_MS 250
#endif
#ifndef MROS2_RTPS_READER_REPAIR_WINDOW_MS
#define MROS2_RTPS_READER_REPAIR_WINDOW_MS 5000
#endif
inline constexpr uint32_t READER_REPAIR_SILENCE_MS =
    MROS2_RTPS_READER_REPAIR_SILENCE_MS;
inline constexpr uint32_t READER_REPAIR_PERIOD_MS =
    MROS2_RTPS_READER_REPAIR_PERIOD_MS;
inline constexpr uint32_t READER_REPAIR_WINDOW_MS =
    MROS2_RTPS_READER_REPAIR_WINDOW_MS;
static_assert(READER_REPAIR_SILENCE_MS > 0);
static_assert(READER_REPAIR_PERIOD_MS >= READER_REPAIR_SILENCE_MS);
static_assert(READER_REPAIR_WINDOW_MS >= READER_REPAIR_PERIOD_MS);

inline bool readerRepairProbeDue(
    bool reliable, bool hasReceiveActivity, bool sequenceExhausted,
    bool hasKnownMissingSequence, uint32_t nowMs, uint32_t lastReceiveMs,
    bool hasPreviousProbe, uint32_t lastProbeMs) {
  // Silence alone does not prove loss. Requesting the next, not-yet-announced
  // sequence makes a conforming Writer answer GAP and can incorrectly skip a
  // future live sample. Probe only after DATA/HEARTBEAT established a hole.
  if (!reliable || !hasReceiveActivity || sequenceExhausted ||
      !hasKnownMissingSequence) {
    return false;
  }
  const uint32_t silenceMs = nowMs - lastReceiveMs;
  if (silenceMs < READER_REPAIR_SILENCE_MS ||
      silenceMs > READER_REPAIR_WINDOW_MS) {
    return false;
  }
  return !hasPreviousProbe ||
         nowMs - lastProbeMs >= READER_REPAIR_PERIOD_MS;
}

inline bool readerHeartbeatSolicitationDue(
    bool reliable, bool hasReceiveActivity, bool sequenceExhausted,
    bool hasKnownMissingSequence, bool heartbeatStateConfirmed,
    uint32_t nowMs, uint32_t lastReceiveMs, bool hasPreviousProbe,
    uint32_t lastProbeMs) {
  // A tail outage has no later DATA with which to expose the missing range.
  // In that case a preemptive, empty, non-final ACKNACK is used only to
  // solicit the Writer's current HEARTBEAT. It neither acknowledges nor
  // requests the unannounced expected sequence, so it cannot make the Writer
  // GAP a future live sample.
  if (!reliable || !hasReceiveActivity || sequenceExhausted ||
      hasKnownMissingSequence || heartbeatStateConfirmed) {
    return false;
  }
  const uint32_t silenceMs = nowMs - lastReceiveMs;
  if (silenceMs < READER_REPAIR_SILENCE_MS ||
      silenceMs > READER_REPAIR_WINDOW_MS) {
    return false;
  }
  return !hasPreviousProbe ||
         nowMs - lastProbeMs >= READER_REPAIR_PERIOD_MS;
}

class RetryQueueClaim {
public:
  bool tryClaim() {
    bool expected = false;
    return m_claimed.compare_exchange_strong(expected, true);
  }
  void release() { m_claimed.store(false); }

private:
  std::atomic<bool> m_claimed{false};
};
// DATA's 16-bit octetsToNextHeader contains the 20-byte fixed body plus
// payload. Larger samples must use DATA_FRAG.
inline constexpr DataSize_t MAX_UNFRAGMENTED_DATA_PAYLOAD =
    static_cast<DataSize_t>(UINT16_MAX - 20);

enum class RequestedSequenceAvailability {
  AVAILABLE,
  NO_HISTORY,
  NO_LONGER_AVAILABLE,
  NOT_YET_WRITTEN,
};

enum class TransmissionHoldTransition {
  NO_CHANGE,
  HELD,
  RELEASED,
};

inline bool shouldCountRepairSendFailure(
    bool transmissionHeld,
    RequestedSequenceAvailability currentAvailability) {
  return !transmissionHeld &&
         currentAvailability == RequestedSequenceAvailability::AVAILABLE;
}

// Bound the synchronous recovery burst caused by one remote ACKNACK. Requests
// beyond this budget remain missing at the Reader and are requested again
// after a later HEARTBEAT. This bounds per-round sequence processing without
// allocating a repair queue or losing the Reader's protocol state. A
// fragmented sequence can still produce multiple DATA_FRAG datagrams.
#ifndef MROS2_RTPS_ACKNACK_SEQUENCE_RESPONSE_BUDGET
#define MROS2_RTPS_ACKNACK_SEQUENCE_RESPONSE_BUDGET 4
#endif
static_assert(MROS2_RTPS_ACKNACK_SEQUENCE_RESPONSE_BUDGET > 0 &&
                  MROS2_RTPS_ACKNACK_SEQUENCE_RESPONSE_BUDGET <=
                      SNS_NUM_BITS,
              "ACKNACK sequence-response budget must fit its bitmap");
inline constexpr uint32_t ACKNACK_SEQUENCE_RESPONSE_BUDGET =
    MROS2_RTPS_ACKNACK_SEQUENCE_RESPONSE_BUDGET;

inline bool ackNackSequenceResponseBudgetAvailable(
    uint32_t attemptedResponses) {
  return attemptedResponses < ACKNACK_SEQUENCE_RESPONSE_BUDGET;
}

inline bool tryReserveAckNackSequenceResponse(
    uint32_t &attemptedResponses) {
  if (!ackNackSequenceResponseBudgetAvailable(attemptedResponses)) {
    return false;
  }
  ++attemptedResponses;
  return true;
}

inline TransmissionHoldTransition applyTransmissionHold(
    bool requestedHeld, bool &currentHeld) {
  if (requestedHeld == currentHeld) {
    return TransmissionHoldTransition::NO_CHANGE;
  }
  currentHeld = requestedHeld;
  return requestedHeld ? TransmissionHoldTransition::HELD
                       : TransmissionHoldTransition::RELEASED;
}

inline bool readerUsesReliabilityProtocol(ReliabilityKind_t reliabilityKind) {
  return reliabilityKind == ReliabilityKind_t::RELIABLE;
}

inline bool sequenceNumberSetRequestsRepair(
    const SequenceNumberSet &sequenceSet) {
  const uint32_t boundedBits =
      sequenceSet.numBits < SNS_NUM_BITS
          ? sequenceSet.numBits
          : SNS_NUM_BITS;
  for (uint32_t bit = 0; bit < boundedBits; ++bit) {
    if (sequenceSet.isSet(bit)) {
      return true;
    }
  }
  return false;
}

inline bool readerRequestsHistoricalData(DurabilityKind_t durabilityKind) {
  return durabilityKind == DurabilityKind_t::TRANSIENT_LOCAL;
}

inline bool readerMayDeliverBeforeMatch(
    DurabilityKind_t durabilityKind,
    ReliabilityKind_t reliabilityKind) {
  return !readerRequestsHistoricalData(durabilityKind) ||
         !readerUsesReliabilityProtocol(reliabilityKind);
}

inline bool inlinePublicationValid(const uint8_t *data, DataSize_t size) {
  return data != nullptr && size != 0 &&
         size <= MAX_UNFRAGMENTED_DATA_PAYLOAD;
}

inline uint32_t countBits(Count_t count) {
  uint32_t bits = 0;
  static_assert(sizeof(bits) == sizeof(count.value),
                "RTPS Count_t must remain 32 bits");
  std::memcpy(&bits, &count.value, sizeof(bits));
  return bits;
}

inline bool countIsNewer(Count_t candidate, Count_t previous) {
  const uint32_t distance = countBits(candidate) - countBits(previous);
  return distance != 0 && distance < (uint32_t{1} << 31);
}

inline bool countIsAdmissible(bool hasPrevious, Count_t candidate,
                              Count_t previous) {
  return !hasPrevious || countIsNewer(candidate, previous);
}

inline Count_t nextCount(Count_t current) {
  uint32_t bits = countBits(current) + 1;
  Count_t result{};
  std::memcpy(&result.value, &bits, sizeof(bits));
  return result;
}

inline void incrementCount(Count_t &count) {
  count = nextCount(count);
}

inline bool rollbackCountIfCurrent(
    Count_t admitted, bool previousPresent, Count_t previous,
    bool &currentPresent, Count_t &current) {
  if (!currentPresent || countBits(current) != countBits(admitted)) {
    return false;
  }
  currentPresent = previousPresent;
  current = previous;
  return true;
}

inline bool sequenceAfter(const SequenceNumber_t &sequence,
                          SequenceNumber_t &result) {
  if (sequence.high < 0 ||
      (sequence.high == INT32_MAX && sequence.low == UINT32_MAX)) {
    return false;
  }
  result = sequence;
  ++result;
  return true;
}

inline bool accountSerializedFragment(uint64_t sampleSize,
                                      uint64_t fragmentSize,
                                      uint64_t &serializedBytes) {
  if (fragmentSize == 0 || serializedBytes > sampleSize ||
      fragmentSize > sampleSize - serializedBytes) {
    return false;
  }
  serializedBytes += fragmentSize;
  return true;
}

inline bool fragmentedPublicationValid(bool hasSerializer,
                                       uint64_t sampleSize) {
  return hasSerializer && sampleSize != 0 &&
         sampleSize <= MAX_FRAGMENTED_SAMPLE_SIZE;
}

inline bool serializedFragmentPositionValid(uint64_t nominalFragmentSize,
                                            uint32_t fragmentStartNumber,
                                            uint64_t serializedBytes) {
  return nominalFragmentSize != 0 && fragmentStartNumber != 0 &&
         fragmentStartNumber <= MAX_FRAGMENTS_PER_SAMPLE &&
         serializedBytes ==
             uint64_t{fragmentStartNumber - 1} * nominalFragmentSize;
}

inline bool serializedSampleComplete(uint64_t sampleSize,
                                     uint64_t serializedBytes,
                                     bool sentFragment) {
  return sentFragment && serializedBytes == sampleSize;
}

inline bool ordinarySendSnapshotComplete(bool sent,
                                         bool allEligibleReadersSent) {
  return sent && allEligibleReadersSent;
}

inline bool sendSnapshotStillPending(const SequenceNumber_t &cursor,
                                     bool cursorExhausted,
                                     const SequenceNumber_t &snapshot) {
  return !cursorExhausted && cursor <= snapshot;
}

inline bool sendCursorTargetsRetainedHistory(
    const SequenceNumber_t &cursor, bool cursorExhausted,
    const SequenceNumber_t &historyMin, const SequenceNumber_t &historyMax) {
  return !cursorExhausted && historyMin != SEQUENCENUMBER_UNKNOWN &&
         historyMax != SEQUENCENUMBER_UNKNOWN && !(cursor < historyMin) &&
         !(historyMax < cursor);
}

inline bool consumeSendRetryBudget(const SequenceNumber_t &sequence,
                                   SequenceNumber_t &retrySequence,
                                   uint8_t &retryCount,
                                   uint8_t maxRetries = SEND_RETRY_LIMIT) {
  if (maxRetries == 0) {
    return false;
  }
  if (retrySequence != sequence) {
    retrySequence = sequence;
    retryCount = 0;
  }
  if (retryCount >= maxRetries) {
    return false;
  }
  ++retryCount;
  return true;
}

inline void clearSendRetryBudget(SequenceNumber_t &retrySequence,
                                 uint8_t &retryCount) {
  retrySequence = SEQUENCENUMBER_UNKNOWN;
  retryCount = 0;
}

inline void retainEarliestSendCursorForRecovery(
    const SequenceNumber_t &failedSequence, SequenceNumber_t &cursor,
    bool &cursorExhausted) {
  if (failedSequence == SEQUENCENUMBER_UNKNOWN) {
    return;
  }
  if (cursorExhausted || failedSequence < cursor) {
    cursor = failedSequence;
    cursorExhausted = false;
  }
}

inline void advanceSendCursorAfterSnapshot(
    SequenceNumber_t &cursor, bool &cursorExhausted,
    const SequenceNumber_t &sentSequence) {
  // History eviction can move the live cursor while a frozen work item is
  // being transmitted. Do not regress or double-advance that newer cursor.
  if (!cursorExhausted && cursor <= sentSequence) {
    SequenceNumber_t next;
    if (sequenceAfter(sentSequence, next)) {
      cursor = next;
    } else {
      cursor = sentSequence;
      cursorExhausted = true;
    }
  }
}

inline void resetSendCursorToHistory(
    const SequenceNumber_t &historyMin,
    const SequenceNumber_t &lastWritten,
    SequenceNumber_t &cursor, bool &cursorExhausted) {
  if (historyMin != SEQUENCENUMBER_UNKNOWN) {
    cursor = historyMin;
    cursorExhausted = false;
    return;
  }
  if (lastWritten.high < 0) {
    cursor = {0, 1};
    cursorExhausted = false;
    return;
  }
  SequenceNumber_t next;
  if (sequenceAfter(lastWritten, next)) {
    cursor = next;
    cursorExhausted = false;
    return;
  }
  cursor = lastWritten;
  cursorExhausted = true;
}

inline bool heartbeatSequenceRange(
    const SequenceNumber_t &historyMin, const SequenceNumber_t &historyMax,
    const SequenceNumber_t &lastWritten, SequenceNumber_t &firstSN,
    SequenceNumber_t &lastSN) {
  const bool historyIsEmpty =
      historyMin == SEQUENCENUMBER_UNKNOWN &&
      historyMax == SEQUENCENUMBER_UNKNOWN;
  if (!historyIsEmpty) {
    if (historyMin == SEQUENCENUMBER_UNKNOWN ||
        historyMax == SEQUENCENUMBER_UNKNOWN || historyMax < historyMin) {
      return false;
    }
    firstSN = historyMin;
    lastSN = lastWritten;
    return !(lastSN < historyMax);
  }

  // DDSI-RTPS 2.3 section 8.3.7.5 represents an empty Writer cache with
  // firstSN equal to the next sequence number and lastSN equal to the last
  // sequence number ever written. A never-written Writer therefore uses 1,0.
  if (lastWritten.high < 0 ||
      (lastWritten.high == INT32_MAX && lastWritten.low == UINT32_MAX)) {
    return false;
  }
  firstSN = lastWritten;
  ++firstSN;
  lastSN = lastWritten;
  return true;
}

inline RequestedSequenceAvailability classifyRequestedSequence(
    const SequenceNumber_t &requested, const SequenceNumber_t &historyMin,
    const SequenceNumber_t &historyMax) {
  if (historyMin == SEQUENCENUMBER_UNKNOWN ||
      historyMax == SEQUENCENUMBER_UNKNOWN) {
    return RequestedSequenceAvailability::NO_HISTORY;
  }
  if (requested < historyMin) {
    return RequestedSequenceAvailability::NO_LONGER_AVAILABLE;
  }
  if (historyMax < requested) {
    return RequestedSequenceAvailability::NOT_YET_WRITTEN;
  }
  return RequestedSequenceAvailability::AVAILABLE;
}

inline RequestedSequenceAvailability classifyRequestedSequence(
    const SequenceNumber_t &requested, const SequenceNumber_t &historyMin,
    const SequenceNumber_t &historyMax,
    const SequenceNumber_t &lastWritten) {
  if (historyMin == SEQUENCENUMBER_UNKNOWN ||
      historyMax == SEQUENCENUMBER_UNKNOWN) {
    return requested <= lastWritten
               ? RequestedSequenceAvailability::NO_LONGER_AVAILABLE
               : RequestedSequenceAvailability::NOT_YET_WRITTEN;
  }
  return classifyRequestedSequence(requested, historyMin, historyMax);
}

inline RequestedSequenceAvailability classifyRequestedSequenceForReader(
    const SequenceNumber_t &requested, const SequenceNumber_t &historyMin,
    const SequenceNumber_t &historyMax, const SequenceNumber_t &lastWritten,
    const SequenceNumber_t &firstRelevantSequence,
    bool noRelevantSequence = false) {
  if (noRelevantSequence) {
    return RequestedSequenceAvailability::NO_LONGER_AVAILABLE;
  }
  if (firstRelevantSequence != SEQUENCENUMBER_UNKNOWN &&
      requested < firstRelevantSequence) {
    return RequestedSequenceAvailability::NO_LONGER_AVAILABLE;
  }
  return classifyRequestedSequence(
      requested, historyMin, historyMax, lastWritten);
}

inline bool heartbeatSequenceRangeForReader(
    const SequenceNumber_t &historyMin, const SequenceNumber_t &historyMax,
    const SequenceNumber_t &lastWritten,
    const SequenceNumber_t &firstRelevantSequence, SequenceNumber_t &firstSN,
    SequenceNumber_t &lastSN, bool noRelevantSequence = false) {
  if (noRelevantSequence) {
    return false;
  }
  if (!heartbeatSequenceRange(
          historyMin, historyMax, lastWritten, firstSN, lastSN)) {
    return false;
  }
  if (firstRelevantSequence != SEQUENCENUMBER_UNKNOWN &&
      firstSN < firstRelevantSequence) {
    firstSN = firstRelevantSequence;
  }
  if (!(lastSN < firstSN)) {
    return true;
  }
  SequenceNumber_t next;
  return sequenceAfter(lastSN, next) && next == firstSN;
}

inline bool readerNeedsPeriodicHeartbeat(
    const SequenceNumber_t &lastWritten,
    const SequenceNumber_t &firstRelevantSequence, bool noRelevantSequence,
    bool hasAcknowledgedThrough,
    const SequenceNumber_t &acknowledgedThrough) {
  if (noRelevantSequence || lastWritten == SEQUENCENUMBER_UNKNOWN) {
    return false;
  }
  if (firstRelevantSequence != SEQUENCENUMBER_UNKNOWN &&
      lastWritten < firstRelevantSequence) {
    return false;
  }
  return !hasAcknowledgedThrough || acknowledgedThrough < lastWritten;
}

inline bool cumulativeAckThrough(const SequenceNumberSet &state,
                                 SequenceNumber_t &result) {
  if (state.base == SequenceNumber_t{0, 0}) {
    return false;
  }
  result = state.base;
  if (result.low == 0) {
    --result.high;
    result.low = UINT32_MAX;
  } else {
    --result.low;
  }
  return true;
}

inline bool advanceCumulativeAck(const SequenceNumberSet &state,
                                 bool &hasAcknowledgedThrough,
                                 SequenceNumber_t &acknowledgedThrough) {
  SequenceNumber_t candidate;
  if (!cumulativeAckThrough(state, candidate)) {
    return false;
  }
  if (!hasAcknowledgedThrough || acknowledgedThrough < candidate) {
    acknowledgedThrough = candidate;
    hasAcknowledgedThrough = true;
    return true;
  }
  return false;
}

inline bool advanceCumulativeAckBounded(
    const SequenceNumberSet &state, const SequenceNumber_t &lastWritten,
    bool &hasAcknowledgedThrough, SequenceNumber_t &acknowledgedThrough) {
  if (lastWritten == SEQUENCENUMBER_UNKNOWN) {
    return false;
  }
  SequenceNumber_t candidate;
  if (!cumulativeAckThrough(state, candidate)) {
    return false;
  }
  if (lastWritten < candidate) {
    candidate = lastWritten;
  }
  if (!hasAcknowledgedThrough || acknowledgedThrough < candidate) {
    acknowledgedThrough = candidate;
    hasAcknowledgedThrough = true;
    return true;
  }
  return false;
}

inline bool ackNackRequestedSequence(const SequenceNumberSet &state,
                                     uint32_t bitIndex,
                                     SequenceNumber_t &result) {
  if (bitIndex >= state.numBits || !state.isSet(bitIndex)) {
    return false;
  }
  result = state.base;
  for (uint32_t index = 0; index < bitIndex; ++index) {
    SequenceNumber_t next;
    if (!sequenceAfter(result, next)) {
      return false;
    }
    result = next;
  }
  return true;
}

template <class ReaderRange>
inline bool reliableReaderReleaseBoundary(
    ReaderRange &readers, const SequenceNumber_t &bestEffortSentThrough,
    SequenceNumber_t &result) {
  bool initialized = false;
  bool hasBestEffortReader = false;
  for (const auto &reader : readers) {
    if (reader.reliabilityKind != ReliabilityKind_t::RELIABLE) {
      hasBestEffortReader = true;
      continue;
    }
    if (!reader.hasAcknowledgedThrough) {
      return false;
    }
    if (!initialized || reader.acknowledgedThrough < result) {
      result = reader.acknowledgedThrough;
      initialized = true;
    }
  }
  if (hasBestEffortReader) {
    if (bestEffortSentThrough == SEQUENCENUMBER_UNKNOWN) {
      return false;
    }
    if (!initialized || bestEffortSentThrough < result) {
      result = bestEffortSentThrough;
    }
    initialized = true;
  }
  return initialized;
}

}  // namespace rtps

#endif  // RTPS_RELIABILITY_STATE_H
