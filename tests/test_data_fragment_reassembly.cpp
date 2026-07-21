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

  rtps::MessageProcessingInfo truncated(bytes.data(), bytes.size() - 1);
  check(!rtps::deserializeMessage(truncated, dataFrag),
        "truncated DATA_FRAG fixed header is rejected");
}

} // namespace

int main() {
  testInOrderWithPadding();
  testOutOfOrderAndDuplicate();
  testMultipleFragmentsAndInterleaving();
  testMalformedFragmentsAreRejected();
  testDataFragDeserialization();
  std::printf("=== DataFrag reassembly: %d/%d passed ===\n", total - failed,
              total);
  return failed == 0 ? 0 : 1;
}
