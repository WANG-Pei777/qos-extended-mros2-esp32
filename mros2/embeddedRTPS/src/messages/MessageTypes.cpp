/*
The MIT License
Copyright (c) 2019 Lehrstuhl Informatik 11 - RWTH Aachen University
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE

This file is part of embeddedRTPS.

Author: i11 - Embedded Software, RWTH Aachen University
*/

#include "rtps/messages/MessageTypes.h"
#include <cstring>

#include <stdio.h>
using namespace rtps;

void doCopyAndMoveOn(uint8_t *dst, const uint8_t *&src, size_t size) {
  memcpy(dst, src, size);
  src += size;
}

namespace {
template <typename T>
void readWireValue(T &target, const uint8_t *&source, bool wireLittleEndian) {
  static_assert(sizeof(T) == 2 || sizeof(T) == 4,
                "RTPS numeric wire helper supports 16/32-bit values");
  auto *destination = reinterpret_cast<uint8_t *>(&target);
  const uint16_t endianProbe = 1;
  const bool hostLittleEndian =
      *reinterpret_cast<const uint8_t *>(&endianProbe) == 1;
  const bool reverse = hostLittleEndian != wireLittleEndian;
  if (reverse) {
    for (size_t index = 0; index < sizeof(T); ++index) {
      destination[index] = source[sizeof(T) - index - 1U];
    }
  } else {
    std::memcpy(destination, source, sizeof(T));
  }
  source += sizeof(T);
}

bool declaredBodyContains(const SubmessageHeader &header,
                          DataSize_t requiredTotal, DataSize_t remaining) {
  const DataSize_t headerSize = SubmessageHeader::getRawSize();
  if (remaining < requiredTotal || requiredTotal < headerSize) {
    return false;
  }
  if (header.octetsToNextHeader == 0) {
    return true;
  }
  return header.octetsToNextHeader >= requiredTotal - headerSize &&
         remaining >= headerSize + header.octetsToNextHeader;
}

bool declaredBodyMatches(const SubmessageHeader &header,
                         DataSize_t requiredTotal, DataSize_t remaining) {
  const DataSize_t headerSize = SubmessageHeader::getRawSize();
  if (remaining < requiredTotal || requiredTotal < headerSize) {
    return false;
  }
  return header.octetsToNextHeader == 0
             ? remaining == requiredTotal
             : header.octetsToNextHeader == requiredTotal - headerSize;
}

bool isPositiveSequence(const SequenceNumber_t &sequence) {
  return sequence.high > 0 || (sequence.high == 0 && sequence.low > 0);
}

bool isNonnegativeSequence(const SequenceNumber_t &sequence) {
  return sequence.high >= 0;
}

bool isImmediateSuccessor(const SequenceNumber_t &candidate,
                          const SequenceNumber_t &previous) {
  if (!isNonnegativeSequence(previous) ||
      (previous.high == INT32_MAX && previous.low == UINT32_MAX)) {
    return false;
  }
  SequenceNumber_t next = previous;
  ++next;
  return candidate == next;
}

bool sequenceSetRangeRepresentable(const SequenceNumber_t &base,
                                   uint32_t numBits) {
  if (!isNonnegativeSequence(base) || numBits > SNS_NUM_BITS) {
    return false;
  }
  SequenceNumber_t sequence = base;
  for (uint32_t bit = 1; bit < numBits; ++bit) {
    if (sequence.high == INT32_MAX && sequence.low == UINT32_MAX) {
      return false;
    }
    ++sequence;
  }
  return true;
}
} // namespace

bool rtps::deserializeMessage(const MessageProcessingInfo &info,
                              Header &header) {
  if (info.getRemainingSize() < Header::getRawSize()) {
    return false;
  }

  const uint8_t *currentPos = info.getPointerToCurrentPos();
  doCopyAndMoveOn(header.protocolName.data(), currentPos,
                  sizeof(std::array<uint8_t, 4>));
  doCopyAndMoveOn(reinterpret_cast<uint8_t *>(&header.protocolVersion),
                  currentPos, sizeof(ProtocolVersion_t));
  doCopyAndMoveOn(header.vendorId.vendorId.data(), currentPos,
                  header.vendorId.vendorId.size());
  doCopyAndMoveOn(header.guidPrefix.id.data(), currentPos,
                  header.guidPrefix.id.size());
  return true;
}

bool rtps::deserializeMessage(const MessageProcessingInfo &info,
                              SubmessageHeader &header) {
  if (info.getRemainingSize() < SubmessageHeader::getRawSize()) {
    return false;
  }

  const uint8_t *currentPos = info.getPointerToCurrentPos();
  header.submessageId = static_cast<SubmessageKind>(*currentPos++);
  header.flags = *(currentPos++);
  readWireValue(
      header.octetsToNextHeader, currentPos,
      (header.flags & FLAG_ENDIANESS) != 0);
  return true;
}

bool rtps::deserializeMessage(const MessageProcessingInfo &info,
                              SubmessageInfoDST &msg) {
  if (info.getRemainingSize() < SubmessageInfoDST::getRawSize() ||
      !deserializeMessage(info, msg.header) ||
      !declaredBodyMatches(msg.header, SubmessageInfoDST::getRawSize(),
                           info.getRemainingSize())) {
    return false;
  }
  const uint8_t *currentPos =
      info.getPointerToCurrentPos() + SubmessageHeader::getRawSize();
  doCopyAndMoveOn(msg.guidPrefix.id.data(), currentPos,
                  msg.guidPrefix.id.size());
  return true;
}

bool rtps::deserializeMessage(const MessageProcessingInfo &info,
                              SubmessageData &msg) {
  if (info.getRemainingSize() < SubmessageData::getRawSize()) {
    return false;
  }
  if (!deserializeMessage(info, msg.header)) {
    return false;
  }

  if (!declaredBodyContains(msg.header, SubmessageData::getRawSize(),
                            info.getRemainingSize())) {
    return false;
  }

  const uint8_t *currentPos =
      info.getPointerToCurrentPos() + SubmessageHeader::getRawSize();

  const bool littleEndian = (msg.header.flags & FLAG_ENDIANESS) != 0;
  readWireValue(msg.extraFlags, currentPos, littleEndian);
  readWireValue(msg.octetsToInlineQos, currentPos, littleEndian);
  doCopyAndMoveOn(msg.readerId.entityKey.data(), currentPos,
                  msg.readerId.entityKey.size());
  msg.readerId.entityKind = static_cast<EntityKind_t>(*currentPos++);
  doCopyAndMoveOn(msg.writerId.entityKey.data(), currentPos,
                  msg.writerId.entityKey.size());
  msg.writerId.entityKind = static_cast<EntityKind_t>(*currentPos++);
  readWireValue(msg.writerSN.high, currentPos, littleEndian);
  readWireValue(msg.writerSN.low, currentPos, littleEndian);
  return isPositiveSequence(msg.writerSN);
}

bool rtps::deserializeMessage(const MessageProcessingInfo &info,
                              SubmessageDataFrag &msg) {
  if (info.getRemainingSize() < SubmessageDataFrag::getRawSize()) {
    return false;
  }
  if (!deserializeMessage(info, msg.header)) {
    return false;
  }

  if (!declaredBodyContains(msg.header, SubmessageDataFrag::getRawSize(),
                            info.getRemainingSize())) {
    return false;
  }

  const uint8_t *currentPos =
      info.getPointerToCurrentPos() + SubmessageHeader::getRawSize();
  const bool littleEndian = (msg.header.flags & FLAG_ENDIANESS) != 0;
  readWireValue(msg.extraFlags, currentPos, littleEndian);
  readWireValue(msg.octetsToInlineQos, currentPos, littleEndian);
  doCopyAndMoveOn(msg.readerId.entityKey.data(), currentPos,
                  msg.readerId.entityKey.size());
  msg.readerId.entityKind = static_cast<EntityKind_t>(*currentPos++);
  doCopyAndMoveOn(msg.writerId.entityKey.data(), currentPos,
                  msg.writerId.entityKey.size());
  msg.writerId.entityKind = static_cast<EntityKind_t>(*currentPos++);
  readWireValue(msg.writerSN.high, currentPos, littleEndian);
  readWireValue(msg.writerSN.low, currentPos, littleEndian);
  readWireValue(msg.fragStartingNumber, currentPos, littleEndian);
  readWireValue(msg.fragmentsInSubmessage, currentPos, littleEndian);
  readWireValue(msg.fragmentSize, currentPos, littleEndian);
  readWireValue(msg.sampleSize, currentPos, littleEndian);
  return isPositiveSequence(msg.writerSN) &&
         msg.fragStartingNumber > 0 &&
         msg.fragmentsInSubmessage > 0 && msg.fragmentSize > 0 &&
         msg.sampleSize > 0;
}

bool rtps::deserializeMessage(const MessageProcessingInfo &info,
                              SubmessageHeartbeat &msg) {
  if (info.getRemainingSize() < SubmessageHeartbeat::getRawSize()) {
    return false;
  }
  if (!deserializeMessage(info, msg.header)) {
    return false;
  }
  if (!declaredBodyMatches(msg.header, SubmessageHeartbeat::getRawSize(),
                           info.getRemainingSize())) {
    return false;
  }

  const uint8_t *currentPos =
      info.getPointerToCurrentPos() + SubmessageHeader::getRawSize();
  const bool littleEndian = (msg.header.flags & FLAG_ENDIANESS) != 0;

  doCopyAndMoveOn(msg.readerId.entityKey.data(), currentPos,
                  msg.readerId.entityKey.size());
  msg.readerId.entityKind = static_cast<EntityKind_t>(*currentPos++);
  doCopyAndMoveOn(msg.writerId.entityKey.data(), currentPos,
                  msg.writerId.entityKey.size());
  msg.writerId.entityKind = static_cast<EntityKind_t>(*currentPos++);
  readWireValue(msg.firstSN.high, currentPos, littleEndian);
  readWireValue(msg.firstSN.low, currentPos, littleEndian);
  readWireValue(msg.lastSN.high, currentPos, littleEndian);
  readWireValue(msg.lastSN.low, currentPos, littleEndian);
  readWireValue(msg.count.value, currentPos, littleEndian);
  const bool nonempty =
      isPositiveSequence(msg.firstSN) && !(msg.lastSN < msg.firstSN);
  const bool empty =
      isPositiveSequence(msg.firstSN) &&
      isImmediateSuccessor(msg.firstSN, msg.lastSN);
  return nonempty || empty;
}

bool rtps::deserializeMessage(const MessageProcessingInfo &info,
                              SubmessageGap &msg) {
  const DataSize_t remainingSizeAtBeginning = info.getRemainingSize();
  constexpr DataSize_t fixedSize =
      SubmessageHeader::getRawSize() + (2 * sizeof(EntityId_t)) +
      sizeof(SequenceNumber_t) + sizeof(SequenceNumber_t) + sizeof(uint32_t);
  if (remainingSizeAtBeginning < fixedSize ||
      !deserializeMessage(info, msg.header)) {
    return false;
  }

  const uint8_t *currentPos =
      info.getPointerToCurrentPos() + SubmessageHeader::getRawSize();
  const bool littleEndian = (msg.header.flags & FLAG_ENDIANESS) != 0;
  doCopyAndMoveOn(msg.readerId.entityKey.data(), currentPos,
                  msg.readerId.entityKey.size());
  msg.readerId.entityKind = static_cast<EntityKind_t>(*currentPos++);
  doCopyAndMoveOn(msg.writerId.entityKey.data(), currentPos,
                  msg.writerId.entityKey.size());
  msg.writerId.entityKind = static_cast<EntityKind_t>(*currentPos++);
  readWireValue(msg.gapStart.high, currentPos, littleEndian);
  readWireValue(msg.gapStart.low, currentPos, littleEndian);
  readWireValue(msg.gapList.base.high, currentPos, littleEndian);
  readWireValue(msg.gapList.base.low, currentPos, littleEndian);
  readWireValue(msg.gapList.numBits, currentPos, littleEndian);
  if (msg.gapList.numBits > SNS_NUM_BITS ||
      !declaredBodyMatches(msg.header, SubmessageGap::getRawSize(msg.gapList),
                           remainingSizeAtBeginning)) {
    return false;
  }
  if (msg.gapList.numBits != 0) {
    const uint32_t bitmapWords = (msg.gapList.numBits + 31) / 32;
    for (uint32_t word = 0; word < bitmapWords; ++word) {
      readWireValue(msg.gapList.bitMap[word], currentPos, littleEndian);
    }
  }
  return isPositiveSequence(msg.gapStart) &&
         isPositiveSequence(msg.gapList.base) &&
         sequenceSetRangeRepresentable(
             msg.gapList.base, msg.gapList.numBits) &&
         !(msg.gapList.base < msg.gapStart);
}

bool rtps::deserializeMessage(const MessageProcessingInfo &info,
                              SubmessageAckNack &msg) {
  const DataSize_t remainingSizeAtBeginning = info.getRemainingSize();
  if (remainingSizeAtBeginning <
      SubmessageAckNack::
          getRawSizeWithoutSNSet()) { // Size of SequenceNumberSet unknown
    return false;
  }
  if (!deserializeMessage(info, msg.header)) {
    return false;
  }

  const uint8_t *currentPos =
      info.getPointerToCurrentPos() + SubmessageHeader::getRawSize();
  const bool littleEndian = (msg.header.flags & FLAG_ENDIANESS) != 0;

  doCopyAndMoveOn(msg.readerId.entityKey.data(), currentPos,
                  msg.readerId.entityKey.size());
  msg.readerId.entityKind = static_cast<EntityKind_t>(*currentPos++);
  doCopyAndMoveOn(msg.writerId.entityKey.data(), currentPos,
                  msg.writerId.entityKey.size());
  msg.writerId.entityKind = static_cast<EntityKind_t>(*currentPos++);
  readWireValue(msg.readerSNState.base.high, currentPos, littleEndian);
  readWireValue(msg.readerSNState.base.low, currentPos, littleEndian);
  readWireValue(msg.readerSNState.numBits, currentPos, littleEndian);

  // Now we can check for full size
  if (msg.readerSNState.numBits > SNS_NUM_BITS ||
      !declaredBodyMatches(
          msg.header, SubmessageAckNack::getRawSize(msg.readerSNState),
          remainingSizeAtBeginning)) {
    return false;
  }

  if (msg.readerSNState.numBits != 0) {
    const uint32_t bitmapWords =
        (msg.readerSNState.numBits + 31) / 32;
    for (uint32_t word = 0; word < bitmapWords; ++word) {
      readWireValue(
          msg.readerSNState.bitMap[word], currentPos, littleEndian);
    }
  }
  readWireValue(msg.count.value, currentPos, littleEndian);
  return sequenceSetRangeRepresentable(
      msg.readerSNState.base, msg.readerSNState.numBits);
}
