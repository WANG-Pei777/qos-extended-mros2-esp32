#ifndef RTPS_DURABILITY_STATE_H
#define RTPS_DURABILITY_STATE_H

#include "rtps/common/types.h"

namespace rtps {

inline bool shouldDiscardUnmatchedHistoryOnReaderMatch(
    DurabilityKind_t durability, bool hadMatchedReaders) {
  return durability == DurabilityKind_t::VOLATILE && !hadMatchedReaders;
}

inline bool shouldReleaseHistoryAfterReaderRemoval(
    DurabilityKind_t durability, uint32_t remainingReaders) {
  return durability == DurabilityKind_t::VOLATILE &&
         remainingReaders == 0;
}

inline bool shouldReleaseHistoryAfterBestEffortSend(
    DurabilityKind_t durability, bool sendBoundaryComplete) {
  return durability == DurabilityKind_t::VOLATILE &&
         sendBoundaryComplete;
}

inline bool shouldReleaseUnmatchedBestEffortHistory(
    DurabilityKind_t durability, uint32_t snapshottedReaders,
    uint32_t currentReaders, bool sequenceStillRetained) {
  return durability == DurabilityKind_t::VOLATILE &&
         snapshottedReaders == 0 && currentReaders == 0 &&
         sequenceStillRetained;
}

inline bool shouldReleaseUnmatchedReliableFallbackHistory(
    DurabilityKind_t durability, uint32_t snapshottedReaders,
    uint32_t currentReaders, bool sequenceStillRetained,
    bool fallbackSendComplete) {
  return durability == DurabilityKind_t::VOLATILE &&
         snapshottedReaders == 0 && currentReaders == 0 &&
         sequenceStillRetained && fallbackSendComplete;
}

inline bool mayAdvanceGlobalCursorForVolatileMatch(bool hadMatchedReaders) {
  return !hadMatchedReaders;
}

inline bool mayAdvanceGlobalCursorAfterDirectedReplay(
    bool hadMatchedReaders) {
  return !hadMatchedReaders;
}

inline bool shouldScheduleOrdinaryReplayRecovery(
    bool replaySucceeded, bool hadMatchedReaders) {
  return !replaySucceeded && !hadMatchedReaders;
}

inline bool allReadersSkipSequence(uint32_t readerCount,
                                   bool anyReaderMayReceive) {
  return readerCount > 0 && !anyReaderMayReceive;
}

inline void initializeVolatileReaderBoundary(
    const SequenceNumber_t &lastWritten,
    SequenceNumber_t &firstRelevantSequence,
    bool &noRelevantSequence) {
  if (lastWritten.high < 0) {
    firstRelevantSequence = {0, 1};
    noRelevantSequence = false;
    return;
  }
  if (lastWritten.high == INT32_MAX && lastWritten.low == UINT32_MAX) {
    firstRelevantSequence = lastWritten;
    noRelevantSequence = true;
    return;
  }
  firstRelevantSequence = lastWritten;
  ++firstRelevantSequence;
  noRelevantSequence = false;
}

inline bool readerMayReceiveSequence(
    DurabilityKind_t readerDurability, const SequenceNumber_t &sequence,
    const SequenceNumber_t &firstRelevantSequence,
    bool noRelevantSequence = false) {
  if (noRelevantSequence) {
    return false;
  }
  return readerDurability == DurabilityKind_t::TRANSIENT_LOCAL ||
         firstRelevantSequence == SEQUENCENUMBER_UNKNOWN ||
         !(sequence < firstRelevantSequence);
}

}  // namespace rtps

#endif  // RTPS_DURABILITY_STATE_H
