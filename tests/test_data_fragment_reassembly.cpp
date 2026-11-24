#include "rtps/messages/DataFragmentReassembly.h"
#include "rtps/messages/MessageTypes.h"

#include <array>
#include <cstdio>
#include <cstring>

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

rtps::Guid_t makeGuid(uint8_t seed) {
  rtps::Guid_t guid{};
  guid.prefix.id[0] = seed;
  guid.entityId.entityKey[0] = seed;
  guid.entityId.entityKind =
      rtps::EntityKind_t::USER_DEFINED_WRITER_WITHOUT_KEY;
  return guid;
}

void testInOrderWithPadding() {
  rtps::DataFragmentReassembler<32, 2, 8> reassembler;
  const auto guid = makeGuid(1);
  const rtps::SequenceNumber_t sequence{0, 1};
  const std::array<uint8_t, 10> sample{0, 1, 2, 3, 4, 5, 6, 7, 8, 9};
  rtps::ReassembledSample completed;

  check(reassembler.addFragment(guid, sequence, 1, 1, 4, sample.size(),
                                sample.data(), 4, completed) ==
            rtps::FragmentReassemblyResult::ACCEPTED_INCOMPLETE,
        "first in-order fragment is retained");
  check(reassembler.addFragment(guid, sequence, 2, 1, 4, sample.size(),
                                sample.data() + 4, 4, completed) ==
            rtps::FragmentReassemblyResult::ACCEPTED_INCOMPLETE,
        "second in-order fragment is retained");
  const std::array<uint8_t, 4> paddedTail{8, 9, 0, 0};
  check(reassembler.addFragment(guid, sequence, 3, 1, 4, sample.size(),
                                paddedTail.data(), paddedTail.size(),
                                completed) ==
            rtps::FragmentReassemblyResult::COMPLETE,
        "padded final fragment completes the sample");
  check(completed.size == sample.size() &&
            std::memcmp(completed.data, sample.data(), sample.size()) == 0,
        "in-order sample bytes are exact");
}

void testOutOfOrderAndDuplicate() {
  rtps::DataFragmentReassembler<32, 2, 8> reassembler;
  const auto guid = makeGuid(2);
  const rtps::SequenceNumber_t sequence{0, 2};
  const std::array<uint8_t, 12> sample{10, 11, 12, 13, 14, 15,
                                       16, 17, 18, 19, 20, 21};
  rtps::ReassembledSample completed;

  check(reassembler.addFragment(guid, sequence, 3, 1, 4, sample.size(),
                                sample.data() + 8, 4, completed) ==
            rtps::FragmentReassemblyResult::ACCEPTED_INCOMPLETE,
        "out-of-order tail is retained");
  check(reassembler.addFragment(guid, sequence, 3, 1, 4, sample.size(),
                                sample.data() + 8, 4, completed) ==
            rtps::FragmentReassemblyResult::ACCEPTED_INCOMPLETE,
        "duplicate fragment does not advance completion");
  check(reassembler.addFragment(guid, sequence, 1, 1, 4, sample.size(),
                                sample.data(), 4, completed) ==
            rtps::FragmentReassemblyResult::ACCEPTED_INCOMPLETE,
        "out-of-order head is retained");
  check(reassembler.addFragment(guid, sequence, 2, 1, 4, sample.size(),
                                sample.data() + 4, 4, completed) ==
            rtps::FragmentReassemblyResult::COMPLETE,
        "missing middle fragment completes the sample");
  check(std::memcmp(completed.data, sample.data(), sample.size()) == 0,
        "out-of-order sample bytes are exact");
}

void testConflictingDuplicatePreservesSample() {
  rtps::DataFragmentReassembler<16, 2, 4> reassembler;
  const auto guid = makeGuid(8);
  const std::array<uint8_t, 8> sample{1, 2, 3, 4, 5, 6, 7, 8};
  const std::array<uint8_t, 4> conflict{9, 9, 9, 9};
  rtps::ReassembledSample completed;

  check(reassembler.addFragment(guid, {0, 8}, 1, 1, 4, sample.size(),
                                sample.data(), 4, completed) ==
            rtps::FragmentReassemblyResult::ACCEPTED_INCOMPLETE,
        "valid head precedes a conflicting duplicate");
  check(reassembler.addFragment(guid, {0, 8}, 1, 1, 4, sample.size(),
                                conflict.data(), conflict.size(), completed) ==
            rtps::FragmentReassemblyResult::REJECTED,
        "conflicting duplicate fragment is rejected");
  check(reassembler.addFragment(guid, {0, 8}, 2, 1, 4, sample.size(),
                                sample.data() + 4, 4, completed) ==
            rtps::FragmentReassemblyResult::COMPLETE &&
            std::memcmp(completed.data, sample.data(), sample.size()) == 0,
        "duplicate conflict does not corrupt the valid partial sample");
}

void testMultiFragmentConflictCommitsNothing() {
  rtps::DataFragmentReassembler<16, 2, 4> reassembler;
  const auto guid = makeGuid(11);
  const std::array<uint8_t, 8> sample{1, 2, 3, 4, 5, 6, 7, 8};
  const std::array<uint8_t, 8> mixed{1, 2, 3, 4, 9, 9, 9, 9};
  rtps::ReassembledSample completed;

  check(reassembler.addFragment(guid, {0, 11}, 2, 1, 4, sample.size(),
                                sample.data() + 4, 4, completed) ==
            rtps::FragmentReassemblyResult::ACCEPTED_INCOMPLETE,
        "tail exists before multi-fragment duplicate conflict");
  check(reassembler.addFragment(guid, {0, 11}, 1, 2, 4, sample.size(),
                                mixed.data(), mixed.size(), completed) ==
            rtps::FragmentReassemblyResult::REJECTED,
        "multi-fragment conflict rejects the whole submessage");
  check(reassembler.addFragment(guid, {0, 11}, 2, 1, 4, sample.size(),
                                sample.data() + 4, 4, completed) ==
            rtps::FragmentReassemblyResult::ACCEPTED_INCOMPLETE,
        "rejected submessage did not partially commit its new head");
  check(reassembler.addFragment(guid, {0, 11}, 1, 1, 4, sample.size(),
                                sample.data(), 4, completed) ==
            rtps::FragmentReassemblyResult::COMPLETE &&
            std::memcmp(completed.data, sample.data(), sample.size()) == 0,
        "valid head completes after atomic conflict rejection");
}

void testSameSequenceDifferentWritersStayIsolated() {
  rtps::DataFragmentReassembler<16, 2, 4> reassembler;
  const auto firstGuid = makeGuid(9);
  const auto secondGuid = makeGuid(10);
  const rtps::SequenceNumber_t sequence{0, 1};
  const std::array<uint8_t, 8> first{1, 2, 3, 4, 5, 6, 7, 8};
  const std::array<uint8_t, 8> second{9, 10, 11, 12, 13, 14, 15, 16};
  rtps::ReassembledSample completed;

  check(reassembler.addFragment(firstGuid, sequence, 1, 1, 4, first.size(),
                                first.data(), 4, completed) ==
            rtps::FragmentReassemblyResult::ACCEPTED_INCOMPLETE &&
            reassembler.addFragment(secondGuid, sequence, 1, 1, 4,
                                    second.size(), second.data(), 4,
                                    completed) ==
            rtps::FragmentReassemblyResult::ACCEPTED_INCOMPLETE,
        "same sequence from two Writers occupies separate slots");
  check(reassembler.addFragment(firstGuid, sequence, 2, 1, 4, first.size(),
                                first.data() + 4, 4, completed) ==
            rtps::FragmentReassemblyResult::COMPLETE &&
            std::memcmp(completed.data, first.data(), first.size()) == 0,
        "first Writer completes without second Writer bytes");
  check(reassembler.addFragment(secondGuid, sequence, 2, 1, 4, second.size(),
                                second.data() + 4, 4, completed) ==
            rtps::FragmentReassemblyResult::COMPLETE &&
            std::memcmp(completed.data, second.data(), second.size()) == 0,
        "second Writer completes without first Writer bytes");
}

void testMultipleFragmentsAndInterleaving() {
  rtps::DataFragmentReassembler<32, 2, 8> reassembler;
  const auto firstGuid = makeGuid(3);
  const auto secondGuid = makeGuid(4);
  const rtps::SequenceNumber_t firstSequence{0, 3};
  const rtps::SequenceNumber_t secondSequence{0, 4};
  const std::array<uint8_t, 8> first{1, 2, 3, 4, 5, 6, 7, 8};
  const std::array<uint8_t, 8> second{9, 10, 11, 12, 13, 14, 15, 16};
  rtps::ReassembledSample completed;

  check(reassembler.addFragment(firstGuid, firstSequence, 1, 1, 4,
                                first.size(), first.data(), 4, completed) ==
            rtps::FragmentReassemblyResult::ACCEPTED_INCOMPLETE,
        "first interleaved sample is retained");
  check(reassembler.addFragment(secondGuid, secondSequence, 1, 2, 4,
                                second.size(), second.data(), second.size(),
                                completed) ==
            rtps::FragmentReassemblyResult::COMPLETE,
        "two fragments in one submessage complete independently");
  check(std::memcmp(completed.data, second.data(), second.size()) == 0,
        "multi-fragment submessage bytes are exact");
  check(reassembler.addFragment(firstGuid, firstSequence, 2, 1, 4,
                                first.size(), first.data() + 4, 4,
                                completed) ==
            rtps::FragmentReassemblyResult::COMPLETE,
        "interleaved sample completes in its own slot");
}

void testMalformedFragmentsAreRejected() {
  rtps::DataFragmentReassembler<16, 1, 4> reassembler;
  const auto guid = makeGuid(5);
  const rtps::SequenceNumber_t sequence{0, 5};
  const std::array<uint8_t, 8> bytes{};
  rtps::ReassembledSample completed;

  check(reassembler.addFragment(guid, sequence, 0, 1, 4, 8, bytes.data(), 4,
                                completed) ==
            rtps::FragmentReassemblyResult::REJECTED,
        "fragment numbering starts at one");
  check(reassembler.addFragment(guid, sequence, 1, 1, 4, 17, bytes.data(), 4,
                                completed) ==
            rtps::FragmentReassemblyResult::REJECTED,
        "oversized samples are rejected");
  check(reassembler.addFragment(guid, sequence, 3, 1, 4, 8, bytes.data(), 4,
                                completed) ==
            rtps::FragmentReassemblyResult::REJECTED,
        "fragment numbers beyond the sample are rejected");
  check(reassembler.addFragment(guid, sequence, 1, 1, 4, 8, bytes.data(), 3,
                                completed) ==
            rtps::FragmentReassemblyResult::REJECTED,
        "short fragment payloads are rejected");
}

void testBoundedSlotEvictionDoesNotMixSamples() {
  rtps::DataFragmentReassembler<16, 1, 4> reassembler;
  const auto guid = makeGuid(6);
  const std::array<uint8_t, 8> first{1, 2, 3, 4, 5, 6, 7, 8};
  const std::array<uint8_t, 8> second{9, 10, 11, 12, 13, 14, 15, 16};
  rtps::ReassembledSample completed;

  check(reassembler.addFragment(guid, {0, 1}, 1, 1, 4, first.size(),
                                first.data(), 4, completed) ==
            rtps::FragmentReassemblyResult::ACCEPTED_INCOMPLETE,
        "single reassembly slot retains the first partial sample");
  check(reassembler.addFragment(guid, {0, 2}, 1, 1, 4, second.size(),
                                second.data(), 4, completed) ==
            rtps::FragmentReassemblyResult::ACCEPTED_INCOMPLETE,
        "new sequence deterministically evicts the bounded partial slot");
  check(reassembler.addFragment(guid, {0, 2}, 2, 1, 4, second.size(),
                                second.data() + 4, 4, completed) ==
            rtps::FragmentReassemblyResult::COMPLETE &&
            std::memcmp(completed.data, second.data(), second.size()) == 0,
        "replacement sample completes without bytes from the evicted sample");
  check(reassembler.addFragment(guid, {0, 1}, 2, 1, 4, first.size(),
                                first.data() + 4, 4, completed) ==
            rtps::FragmentReassemblyResult::ACCEPTED_INCOMPLETE,
        "evicted sample tail cannot falsely complete from stale slot state");
}

void testReusedSlotDoesNotBecomeImmediateEvictionVictim() {
  rtps::DataFragmentReassembler<16, 2, 4> reassembler;
  const auto guid = makeGuid(12);
  const std::array<uint8_t, 8> first{1, 2, 3, 4, 5, 6, 7, 8};
  const std::array<uint8_t, 8> second{11, 12, 13, 14, 15, 16, 17, 18};
  const std::array<uint8_t, 8> third{21, 22, 23, 24, 25, 26, 27, 28};
  const std::array<uint8_t, 8> fourth{31, 32, 33, 34, 35, 36, 37, 38};
  rtps::ReassembledSample completed;

  reassembler.addFragment(guid, {0, 1}, 1, 1, 4, first.size(),
                          first.data(), 4, completed);
  reassembler.addFragment(guid, {0, 2}, 1, 1, 4, second.size(),
                          second.data(), 4, completed);
  check(reassembler.addFragment(guid, {0, 1}, 2, 1, 4, first.size(),
                                first.data() + 4, 4, completed) ==
            rtps::FragmentReassemblyResult::COMPLETE,
        "completed slot becomes available for bounded reuse");
  check(reassembler.addFragment(guid, {0, 3}, 1, 1, 4, third.size(),
                                third.data(), 4, completed) ==
            rtps::FragmentReassemblyResult::ACCEPTED_INCOMPLETE,
        "new partial sample reuses the completed slot");
  check(reassembler.addFragment(guid, {0, 4}, 1, 1, 4, fourth.size(),
                                fourth.data(), 4, completed) ==
            rtps::FragmentReassemblyResult::ACCEPTED_INCOMPLETE,
        "full pool accepts another sample by round-robin eviction");
  check(reassembler.addFragment(guid, {0, 3}, 2, 1, 4, third.size(),
                                third.data() + 4, 4, completed) ==
            rtps::FragmentReassemblyResult::COMPLETE &&
            std::memcmp(completed.data, third.data(), third.size()) == 0,
        "recently reused slot is not the immediate eviction victim");
  check(reassembler.addFragment(guid, {0, 2}, 2, 1, 4, second.size(),
                                second.data() + 4, 4, completed) ==
            rtps::FragmentReassemblyResult::ACCEPTED_INCOMPLETE,
        "older partial slot was selected for eviction");
}

void testMetadataConflictPreservesValidPartialSample() {
  rtps::DataFragmentReassembler<16, 1, 4> reassembler;
  const auto guid = makeGuid(7);
  const std::array<uint8_t, 8> sample{1, 2, 3, 4, 5, 6, 7, 8};
  rtps::ReassembledSample completed;

  check(reassembler.addFragment(guid, {0, 3}, 1, 1, 4, sample.size(),
                                sample.data(), 4, completed) ==
            rtps::FragmentReassemblyResult::ACCEPTED_INCOMPLETE,
        "valid partial sample is retained before metadata conflict");
  check(reassembler.addFragment(guid, {0, 3}, 2, 1, 2, sample.size(),
                                sample.data() + 2, 2, completed) ==
            rtps::FragmentReassemblyResult::REJECTED,
        "same-sequence fragment with conflicting dimensions is rejected");
  check(reassembler.addFragment(guid, {0, 3}, 2, 1, 4, sample.size(),
                                sample.data() + 4, 4, completed) ==
            rtps::FragmentReassemblyResult::COMPLETE &&
            std::memcmp(completed.data, sample.data(), sample.size()) == 0,
        "metadata conflict does not corrupt the valid partial sample");
}

void writeLe16(uint8_t *target, uint16_t value) {
  target[0] = static_cast<uint8_t>(value & 0xffU);
  target[1] = static_cast<uint8_t>((value >> 8U) & 0xffU);
}

void writeLe32(uint8_t *target, uint32_t value) {
  target[0] = static_cast<uint8_t>(value & 0xffU);
  target[1] = static_cast<uint8_t>((value >> 8U) & 0xffU);
  target[2] = static_cast<uint8_t>((value >> 16U) & 0xffU);
  target[3] = static_cast<uint8_t>((value >> 24U) & 0xffU);
}

void writeBe16(uint8_t *target, uint16_t value) {
  target[0] = static_cast<uint8_t>((value >> 8U) & 0xffU);
  target[1] = static_cast<uint8_t>(value & 0xffU);
}

void writeBe32(uint8_t *target, uint32_t value) {
  target[0] = static_cast<uint8_t>((value >> 24U) & 0xffU);
  target[1] = static_cast<uint8_t>((value >> 16U) & 0xffU);
  target[2] = static_cast<uint8_t>((value >> 8U) & 0xffU);
  target[3] = static_cast<uint8_t>(value & 0xffU);
}

void testDataFragDeserialization() {
  std::array<uint8_t, rtps::SubmessageDataFrag::getRawSize()> bytes{};
  bytes[0] = static_cast<uint8_t>(rtps::SubmessageKind::DATA_FRAG);
  bytes[1] = rtps::FLAG_LITTLE_ENDIAN;
  writeLe16(bytes.data() + 2, 0);
  writeLe16(bytes.data() + 6, 28);
  bytes[8] = 1;
  bytes[11] =
      static_cast<uint8_t>(rtps::EntityKind_t::USER_DEFINED_READER_WITHOUT_KEY);
  bytes[12] = 2;
  bytes[15] =
      static_cast<uint8_t>(rtps::EntityKind_t::USER_DEFINED_WRITER_WITHOUT_KEY);
  writeLe32(bytes.data() + 16, 3);
  writeLe32(bytes.data() + 20, 4);
  writeLe32(bytes.data() + 24, 5);
  writeLe16(bytes.data() + 28, 2);
  writeLe16(bytes.data() + 30, 1024);
  writeLe32(bytes.data() + 32, 2056);

  rtps::MessageProcessingInfo info(bytes.data(), bytes.size());
  rtps::SubmessageDataFrag dataFrag{};
  check(rtps::deserializeMessage(info, dataFrag),
        "DATA_FRAG fixed header deserializes with zero trailing length");
  check(dataFrag.fragStartingNumber == 5 &&
            dataFrag.fragmentsInSubmessage == 2 &&
            dataFrag.fragmentSize == 1024 && dataFrag.sampleSize == 2056 &&
            dataFrag.writerSN.high == 3 && dataFrag.writerSN.low == 4,
        "DATA_FRAG fields retain their wire values");

  bytes[1] = rtps::FLAG_BIG_ENDIAN;
  writeBe16(bytes.data() + 2,
            rtps::SubmessageDataFrag::getRawSize() -
                rtps::SubmessageHeader::getRawSize());
  writeBe16(bytes.data() + 6, 28);
  writeBe32(bytes.data() + 16, 3);
  writeBe32(bytes.data() + 20, 4);
  writeBe32(bytes.data() + 24, 5);
  writeBe16(bytes.data() + 28, 2);
  writeBe16(bytes.data() + 30, 1024);
  writeBe32(bytes.data() + 32, 2056);
  rtps::MessageProcessingInfo bigEndianInfo(bytes.data(), bytes.size());
  check(rtps::deserializeMessage(bigEndianInfo, dataFrag) &&
            dataFrag.fragStartingNumber == 5 &&
            dataFrag.fragmentsInSubmessage == 2 &&
            dataFrag.fragmentSize == 1024 &&
            dataFrag.sampleSize == 2056 &&
            dataFrag.writerSN == rtps::SequenceNumber_t{3, 4},
        "big-endian DATA_FRAG numeric fields deserialize");

  rtps::MessageProcessingInfo truncated(bytes.data(), bytes.size() - 1);
  check(!rtps::deserializeMessage(truncated, dataFrag),
        "truncated DATA_FRAG fixed header is rejected");
}

} // namespace

int main() {
  testInOrderWithPadding();
  testOutOfOrderAndDuplicate();
  testConflictingDuplicatePreservesSample();
  testMultiFragmentConflictCommitsNothing();
  testSameSequenceDifferentWritersStayIsolated();
  testMultipleFragmentsAndInterleaving();
  testMalformedFragmentsAreRejected();
  testBoundedSlotEvictionDoesNotMixSamples();
  testReusedSlotDoesNotBecomeImmediateEvictionVictim();
  testMetadataConflictPreservesValidPartialSample();
  testDataFragDeserialization();
  std::printf("=== DataFrag reassembly: %d/%d passed ===\n", total - failed,
              total);
  return failed == 0 ? 0 : 1;
}
