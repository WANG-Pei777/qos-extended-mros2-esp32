/*
The MIT License
Copyright (c) 2019 Lehrstuhl Informatik 11 - RWTH Aachen University
*/

#ifndef RTPS_DATAFRAGMENTREASSEMBLY_H
#define RTPS_DATAFRAGMENTREASSEMBLY_H

#include "rtps/common/types.h"

#include <array>
#include <cstddef>
#include <cstdint>
#include <cstring>

namespace rtps {

enum class FragmentReassemblyResult : uint8_t {
  REJECTED,
  ACCEPTED_INCOMPLETE,
  COMPLETE
};

struct ReassembledSample {
  const uint8_t *data = nullptr;
  DataSize_t size = 0;
};

template <size_t MaxSampleSize = MAX_FRAGMENTED_SAMPLE_SIZE,
          size_t SlotCount = 2,
          size_t MaxFragments = MAX_FRAGMENTS_PER_SAMPLE>
class DataFragmentReassembler {
  static_assert(MaxSampleSize > 0 && MaxSampleSize <= UINT16_MAX,
                "reassembled samples must fit DataSize_t");
  static_assert(SlotCount > 0, "at least one reassembly slot is required");
  static_assert(MaxFragments > 0, "at least one fragment is required");

public:
  FragmentReassemblyResult addFragment(
      const Guid_t &writerGuid, const SequenceNumber_t &writerSN,
      uint32_t fragmentStartingNumber, uint16_t fragmentsInSubmessage,
      uint16_t fragmentSize, uint32_t sampleSize, const uint8_t *payload,
      DataSize_t payloadSize, ReassembledSample &completed) {
    completed = {};
    if (payload == nullptr || fragmentStartingNumber == 0 ||
        fragmentsInSubmessage == 0 || fragmentSize == 0 || sampleSize == 0 ||
        sampleSize > MaxSampleSize) {
      return FragmentReassemblyResult::REJECTED;
    }

    const uint32_t totalFragments =
        (sampleSize + static_cast<uint32_t>(fragmentSize) - 1U) /
        static_cast<uint32_t>(fragmentSize);
    const uint64_t lastFragment =
        static_cast<uint64_t>(fragmentStartingNumber) +
        static_cast<uint64_t>(fragmentsInSubmessage) - 1U;
    if (totalFragments == 0 || totalFragments > MaxFragments ||
        lastFragment > totalFragments) {
      return FragmentReassemblyResult::REJECTED;
    }

    size_t expectedPayloadSize = 0;
    for (uint32_t fragment = fragmentStartingNumber;
         fragment <= lastFragment; ++fragment) {
      const size_t offset =
          static_cast<size_t>(fragment - 1U) * fragmentSize;
      const size_t remaining = static_cast<size_t>(sampleSize) - offset;
      expectedPayloadSize +=
          remaining < fragmentSize ? remaining : fragmentSize;
    }
    if (payloadSize < expectedPayloadSize ||
        payloadSize > expectedPayloadSize + 3U) {
      return FragmentReassemblyResult::REJECTED;
    }

    Slot *slot = findSlot(writerGuid, writerSN);
    if (slot == nullptr) {
      slot = allocateSlot();
      initializeSlot(*slot, writerGuid, writerSN, fragmentSize, sampleSize,
                     static_cast<uint16_t>(totalFragments));
    } else if (slot->fragmentSize != fragmentSize ||
               slot->sampleSize != sampleSize ||
               slot->totalFragments != totalFragments) {
      return FragmentReassemblyResult::REJECTED;
    }

    // Validate every duplicate before mutating the slot. A multi-fragment
    // submessage with one conflicting duplicate must not partially commit
    // earlier new fragments.
    size_t payloadOffset = 0;
    for (uint32_t fragment = fragmentStartingNumber;
         fragment <= lastFragment; ++fragment) {
      const size_t sampleOffset =
          static_cast<size_t>(fragment - 1U) * fragmentSize;
      const size_t remaining = static_cast<size_t>(sampleSize) - sampleOffset;
      const size_t bytes = remaining < fragmentSize ? remaining : fragmentSize;
      const size_t bitmapIndex = static_cast<size_t>(fragment - 1U);
      if (slot->received[bitmapIndex] &&
          std::memcmp(slot->data.data() + sampleOffset,
                      payload + payloadOffset, bytes) != 0) {
        return FragmentReassemblyResult::REJECTED;
      }
      payloadOffset += bytes;
    }

    payloadOffset = 0;
    for (uint32_t fragment = fragmentStartingNumber;
         fragment <= lastFragment; ++fragment) {
      const size_t sampleOffset =
          static_cast<size_t>(fragment - 1U) * fragmentSize;
      const size_t remaining = static_cast<size_t>(sampleSize) - sampleOffset;
      const size_t bytes = remaining < fragmentSize ? remaining : fragmentSize;
      const size_t bitmapIndex = static_cast<size_t>(fragment - 1U);
      if (!slot->received[bitmapIndex]) {
        std::memcpy(slot->data.data() + sampleOffset,
                    payload + payloadOffset, bytes);
        slot->received[bitmapIndex] = true;
        ++slot->receivedCount;
      }
      payloadOffset += bytes;
    }

    if (slot->receivedCount != slot->totalFragments) {
      return FragmentReassemblyResult::ACCEPTED_INCOMPLETE;
    }

    completed.data = slot->data.data();
    completed.size = static_cast<DataSize_t>(slot->sampleSize);
    slot->active = false;
    return FragmentReassemblyResult::COMPLETE;
  }

private:
  struct Slot {
    bool active = false;
    Guid_t writerGuid{};
    SequenceNumber_t writerSN{};
    uint32_t sampleSize = 0;
    uint16_t fragmentSize = 0;
    uint16_t totalFragments = 0;
    uint16_t receivedCount = 0;
    std::array<bool, MaxFragments> received{};
    std::array<uint8_t, MaxSampleSize> data{};
  };

  Slot *findSlot(const Guid_t &writerGuid,
                 const SequenceNumber_t &writerSN) {
    for (auto &slot : m_slots) {
      if (slot.active && slot.writerGuid == writerGuid &&
          slot.writerSN == writerSN) {
        return &slot;
      }
    }
    return nullptr;
  }

  Slot *allocateSlot() {
    for (size_t offset = 0; offset < SlotCount; ++offset) {
      const size_t index = (m_nextEviction + offset) % SlotCount;
      if (!m_slots[index].active) {
        m_nextEviction = (index + 1U) % SlotCount;
        return &m_slots[index];
      }
    }
    Slot &slot = m_slots[m_nextEviction];
    m_nextEviction = (m_nextEviction + 1U) % SlotCount;
    return &slot;
  }

  static void initializeSlot(Slot &slot, const Guid_t &writerGuid,
                             const SequenceNumber_t &writerSN,
                             uint16_t fragmentSize, uint32_t sampleSize,
                             uint16_t totalFragments) {
    slot.active = true;
    slot.writerGuid = writerGuid;
    slot.writerSN = writerSN;
    slot.sampleSize = sampleSize;
    slot.fragmentSize = fragmentSize;
    slot.totalFragments = totalFragments;
    slot.receivedCount = 0;
    slot.received.fill(false);
  }

  std::array<Slot, SlotCount> m_slots{};
  size_t m_nextEviction = 0;
};

using DefaultDataFragmentReassembler = DataFragmentReassembler<>;

} // namespace rtps

#endif // RTPS_DATAFRAGMENTREASSEMBLY_H
