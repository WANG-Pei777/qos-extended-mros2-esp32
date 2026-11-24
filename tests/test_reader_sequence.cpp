/* Host-side StatefulReader sequence admission tests. */

#include "rtps/entities/ReaderSequence.h"
#include "rtps/entities/WriterProxy.h"

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
  using rtps::ReaderSequenceAdmission;

  const uint8_t cdrHeader[4] = {0, 1, 0, 0};
  const uint8_t unsupportedCdrHeader[4] = {0, 0, 0, 0};
  check(rtps::mros2UserCdrPayloadSupported(cdrHeader, sizeof(cdrHeader)),
        "Reader admits the supported CDR little-endian encapsulation");
  check(!rtps::readerPayloadSupported(cdrHeader, 3) &&
            !rtps::readerPayloadSupported(nullptr, 4),
        "Reader rejects short or null payload before sequence admission");
  check(!rtps::mros2UserCdrPayloadSupported(
            unsupportedCdrHeader, sizeof(unsupportedCdrHeader)),
        "Reader rejects unsupported CDR representation before admission");
  check(rtps::readerPayloadSupported(
            unsupportedCdrHeader, sizeof(unsupportedCdrHeader)),
        "built-in Reader storage gate remains representation-neutral");

  check(rtps::classifyReaderSequence({0, 6}, {0, 5}) ==
            ReaderSequenceAdmission::STALE,
        "matched Reliable Reader classifies an old sequence as stale");
  check(rtps::classifyReaderSequence({0, 6}, {0, 6}) ==
            ReaderSequenceAdmission::EXPECTED,
        "matched Reliable Reader accepts only its exact expected sequence");
  check(rtps::classifyReaderSequence({0, 6}, {0, 9}) ==
            ReaderSequenceAdmission::AHEAD,
        "matched Reliable Reader preserves a forward gap for repair");
  rtps::SequenceNumber_t highest = rtps::SEQUENCENUMBER_UNKNOWN;
  rtps::recordHighestObserved(highest, {0, 9});
  rtps::recordHighestObserved(highest, {0, 7});
  check(highest == rtps::SequenceNumber_t{0, 9},
        "ahead tracking retains the highest observed sequence");
  check(rtps::readerNeedsRepair({0, 6}, highest),
        "Reader requests its missing expected sequence after ahead DATA");
  check(!rtps::readerNeedsRepair({0, 10}, highest),
        "Reader stops repair after advancing beyond the observed high");
  rtps::SequenceNumber_t terminalExpected = rtps::SEQUENCENUMBER_UNKNOWN;
  bool terminalExhausted = false;
  rtps::advanceReaderExpected({INT32_MAX, UINT32_MAX}, terminalExpected,
                              terminalExhausted);
  check(terminalExhausted &&
            terminalExpected == rtps::SequenceNumber_t{INT32_MAX, UINT32_MAX},
        "Reader records exhaustion after the final representable sequence");
  rtps::SequenceNumber_t ordinaryExpected = rtps::SEQUENCENUMBER_UNKNOWN;
  bool ordinaryExhausted = false;
  rtps::advanceReaderExpected({0, 9}, ordinaryExpected, ordinaryExhausted);
  check(!ordinaryExhausted &&
            ordinaryExpected == rtps::SequenceNumber_t{0, 10},
        "ordinary Reader admission advances to the next sequence");
  rtps::SequenceNumber_t bestEffortExpected{0, 1};
  bool bestEffortExhausted = false;
  check(rtps::admitBestEffortSequence(
            {0, 3}, bestEffortExpected, bestEffortExhausted) &&
            bestEffortExpected == rtps::SequenceNumber_t{0, 4},
        "Best Effort Reader accepts a fresh forward jump without repair");
  check(!rtps::admitBestEffortSequence(
             {0, 2}, bestEffortExpected, bestEffortExhausted) &&
            bestEffortExpected == rtps::SequenceNumber_t{0, 4},
        "Best Effort Reader suppresses a late lower sequence");
  check(rtps::admitBestEffortSequence(
            {INT32_MAX, UINT32_MAX}, bestEffortExpected,
            bestEffortExhausted) &&
            bestEffortExhausted,
        "Best Effort Reader accepts the terminal sequence once");
  check(!rtps::admitBestEffortSequence(
             {INT32_MAX, UINT32_MAX}, bestEffortExpected,
             bestEffortExhausted),
        "Best Effort Reader suppresses a terminal retransmission");
  rtps::SequenceNumber_t heartbeatHigh = rtps::SEQUENCENUMBER_UNKNOWN;
  rtps::recordHeartbeatHigh(heartbeatHigh, {0, 4}, {0, 8});
  check(heartbeatHigh == rtps::SequenceNumber_t{0, 8},
        "nonempty HEARTBEAT records its repair high watermark");
  rtps::recordHeartbeatHigh(heartbeatHigh, {0, 9}, {0, 8});
  check(heartbeatHigh == rtps::SequenceNumber_t{0, 8},
        "empty HEARTBEAT does not create a repair watermark");
  check(!rtps::readerSequenceIsFresh({0, 6}, {0, 5}),
        "a duplicate sequence below expected is rejected");
  check(rtps::readerSequenceIsFresh({0, 6}, {0, 6}),
        "the exact next sequence is accepted");
  check(rtps::readerSequenceIsFresh({0, 6}, {0, 9}),
        "a forward sequence remains fresh even though it is not yet admissible");
  check(rtps::readerSequenceIsFresh(rtps::SEQUENCENUMBER_UNKNOWN, {0, 1}),
        "an unknown initial sequence accepts the first sample");

  rtps::SequenceNumber_t pendingReliable = rtps::SEQUENCENUMBER_UNKNOWN;
  bool pendingReliableExhausted = false;
  check(rtps::admitReliableSequence(
            {0, 5}, pendingReliable, pendingReliableExhausted) &&
            pendingReliable == rtps::SequenceNumber_t{0, 6},
        "pre-match Reliable Reader establishes its first sequence epoch");
  check(!rtps::admitReliableSequence(
             {0, 7}, pendingReliable, pendingReliableExhausted) &&
            pendingReliable == rtps::SequenceNumber_t{0, 6},
        "pre-match Reliable Reader does not deliver across a gap");
  check(rtps::admitReliableSequence(
            {0, 6}, pendingReliable, pendingReliableExhausted) &&
            pendingReliable == rtps::SequenceNumber_t{0, 7},
        "pre-match Reliable Reader admits the exact missing sequence");
  check(!rtps::admitReliableSequence(
             {0, 6}, pendingReliable, pendingReliableExhausted),
        "pre-match Reliable Reader suppresses a duplicate sequence");

  rtps::SequenceNumberSet contiguous;
  contiguous.base = {0, 4};
  contiguous.numBits = 0;
  check(rtps::readerExpectedAfterGap({0, 2}, {0, 2}, contiguous) ==
            rtps::SequenceNumber_t{0, 4},
        "contiguous GAP advances expected sequence to gapList base");
  check(rtps::readerNeedsRepair(
            rtps::readerExpectedAfterGap({0, 2}, {0, 2}, contiguous),
            {0, 6}),
        "GAP advancement continues repair below the observed high");
  check(!rtps::readerNeedsRepair(
            rtps::readerExpectedAfterGap({0, 2}, {0, 2}, contiguous),
            {0, 3}),
        "GAP advancement stops repair beyond the observed high");
  check(rtps::readerExpectedAfterGap({0, 1}, {0, 2}, contiguous) ==
            rtps::SequenceNumber_t{0, 1},
        "GAP does not skip an earlier still-missing sequence");

  rtps::SequenceNumberSet bitmap;
  bitmap.base = {0, 4};
  bitmap.numBits = 2;
  bitmap.bitMap[0] = uint32_t{0xC0000000};
  check(rtps::readerExpectedAfterGap({0, 4}, {0, 4}, bitmap) ==
            rtps::SequenceNumber_t{0, 6},
        "GAP bitmap advances through consecutive irrelevant sequences");
  bitmap.base = {1, UINT32_MAX};
  bitmap.numBits = 2;
  bitmap.bitMap[0] = uint32_t{0xC0000000};
  check(rtps::readerExpectedAfterGap(
            {1, UINT32_MAX}, {1, UINT32_MAX}, bitmap) ==
            rtps::SequenceNumber_t{2, 1},
        "GAP bitmap advancement crosses the low-word boundary");
  check(rtps::readerExpectedAfterGap(rtps::SEQUENCENUMBER_UNKNOWN,
                                     {0, 2}, contiguous) ==
            rtps::SEQUENCENUMBER_UNKNOWN,
        "GAP preserves unknown pre-discovery sequence state");
  rtps::SequenceNumberSet terminalGap;
  terminalGap.base = {INT32_MAX, UINT32_MAX};
  terminalGap.numBits = 1;
  terminalGap.bitMap[0] = uint32_t{1} << 31;
  bool gapExhausted = false;
  check(rtps::readerExpectedAfterGap(
            {INT32_MAX, UINT32_MAX}, {INT32_MAX, UINT32_MAX},
            terminalGap, &gapExhausted) ==
            rtps::SequenceNumber_t{INT32_MAX, UINT32_MAX} &&
            gapExhausted,
        "terminal GAP marks the Reader sequence state exhausted");

  rtps::WriterProxy writer;
  writer.expectedSN = {0, 3};
  rtps::SequenceNumberSet missing = writer.getMissing({0, 1}, {0, 5});
  check(missing.base == rtps::SequenceNumber_t{0, 3} &&
            missing.numBits == 1 && missing.isSet(0),
        "HEARTBEAT requests exactly the next missing sequence");
  missing = writer.getMissing({0, 6}, {0, 5});
  check(writer.expectedSN == rtps::SequenceNumber_t{0, 6} &&
            missing.base == rtps::SequenceNumber_t{0, 6} &&
            missing.numBits == 0,
        "empty HEARTBEAT advances the cumulative ACK boundary");
  writer.expectedSN = {0, 2};
  missing = writer.getMissing({0, 4}, {0, 8});
  check(writer.expectedSN == rtps::SequenceNumber_t{0, 4} &&
            missing.base == rtps::SequenceNumber_t{0, 4} &&
            missing.numBits == 1 && missing.isSet(0),
        "HEARTBEAT firstSN skips unavailable History then requests repair");
  writer.expectedSN = {INT32_MAX, UINT32_MAX};
  writer.expectedSequenceExhausted = true;
  missing = writer.getMissing({INT32_MAX, UINT32_MAX},
                              {INT32_MAX, UINT32_MAX});
  check(missing.base ==
                rtps::SequenceNumber_t{INT32_MAX, UINT32_MAX} &&
            missing.numBits == 0,
        "exhausted Reader emits no terminal-sequence repair request");

  std::printf("Reader sequence: %d/%d passed\n", total - failed, total);
  return failed == 0 ? 0 : 1;
}
