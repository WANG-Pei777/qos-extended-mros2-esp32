#ifndef RTPS_READER_SEQUENCE_H
#define RTPS_READER_SEQUENCE_H

#include "rtps/common/types.h"

namespace rtps {

enum class ReaderSequenceAdmission {
  STALE,
  EXPECTED,
  AHEAD,
};

inline bool readerPayloadSupported(const uint8_t *data, DataSize_t size) {
  return data != nullptr && size >= 4;
}

inline bool mros2UserCdrPayloadSupported(
    const uint8_t *data, DataSize_t size) {
  // Generated mros2 message types currently deserialize by native little-
  // endian memcpy and do not dispatch on the DDS CDR representation id.
  return readerPayloadSupported(data, size) &&
         data[0] == 0 && data[1] == 1;
}

inline bool readerSequenceIsTerminal(const SequenceNumber_t &sequence) {
  return sequence.high == INT32_MAX && sequence.low == UINT32_MAX;
}

inline void advanceReaderExpected(const SequenceNumber_t &received,
                                  SequenceNumber_t &expected,
                                  bool &exhausted) {
  expected = received;
  exhausted = readerSequenceIsTerminal(received);
  if (!exhausted) {
    ++expected;
  }
}

inline ReaderSequenceAdmission classifyReaderSequence(
    const SequenceNumber_t &expected, const SequenceNumber_t &received) {
  if (expected == SEQUENCENUMBER_UNKNOWN || received == expected) {
    return ReaderSequenceAdmission::EXPECTED;
  }
  return received < expected ? ReaderSequenceAdmission::STALE
                             : ReaderSequenceAdmission::AHEAD;
}

inline bool readerSequenceIsFresh(const SequenceNumber_t &expected,
                                  const SequenceNumber_t &received) {
  return classifyReaderSequence(expected, received) !=
         ReaderSequenceAdmission::STALE;
}

inline bool admitReliableSequence(const SequenceNumber_t &received,
                                  SequenceNumber_t &expected,
                                  bool &exhausted) {
  if (exhausted ||
      classifyReaderSequence(expected, received) !=
          ReaderSequenceAdmission::EXPECTED) {
    return false;
  }
  advanceReaderExpected(received, expected, exhausted);
  return true;
}

inline bool admitBestEffortSequence(const SequenceNumber_t &received,
                                    SequenceNumber_t &expected,
                                    bool &exhausted) {
  if (exhausted || !readerSequenceIsFresh(expected, received)) {
    return false;
  }
  advanceReaderExpected(received, expected, exhausted);
  return true;
}

inline void recordHighestObserved(SequenceNumber_t &highest,
                                  const SequenceNumber_t &observed) {
  if (highest == SEQUENCENUMBER_UNKNOWN || highest < observed) {
    highest = observed;
  }
}

inline bool readerNeedsRepair(const SequenceNumber_t &expected,
                              const SequenceNumber_t &highestObserved) {
  return expected != SEQUENCENUMBER_UNKNOWN &&
         highestObserved != SEQUENCENUMBER_UNKNOWN &&
         !(highestObserved < expected);
}

inline void recordHeartbeatHigh(SequenceNumber_t &highestObserved,
                                const SequenceNumber_t &firstAvailable,
                                const SequenceNumber_t &lastAvailable) {
  if (!(lastAvailable < firstAvailable)) {
    recordHighestObserved(highestObserved, lastAvailable);
  }
}

inline SequenceNumber_t readerExpectedAfterGap(
    SequenceNumber_t expected, const SequenceNumber_t &gapStart,
    const SequenceNumberSet &gapList, bool *exhausted = nullptr) {
  if (expected == SEQUENCENUMBER_UNKNOWN) {
    return expected;
  }
  if (!(expected < gapStart) && expected < gapList.base) {
    expected = gapList.base;
  }

  SequenceNumber_t candidate = gapList.base;
  const uint32_t boundedBits =
      gapList.numBits < SNS_NUM_BITS ? gapList.numBits : SNS_NUM_BITS;
  for (uint32_t bit = 0; bit < boundedBits; ++bit) {
    if (expected < candidate) {
      break;
    }
    if (expected == candidate && gapList.isSet(bit)) {
      if (readerSequenceIsTerminal(expected)) {
        if (exhausted != nullptr) {
          *exhausted = true;
        }
      } else {
        ++expected;
      }
    }
    if (bit + 1U < boundedBits) {
      if (readerSequenceIsTerminal(candidate)) {
        break;
      }
      ++candidate;
    }
  }
  return expected;
}

}  // namespace rtps

#endif  // RTPS_READER_SEQUENCE_H
