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

#ifndef RTPS_MESSAGEFACTORY_H
#define RTPS_MESSAGEFACTORY_H

#include "rtps/common/types.h"
#include "rtps/config.h"
#include "rtps/messages/MessageTypes.h"
#include "rtps/utils/sysFunctions.h"

#include <array>
#include <cstdint>

namespace rtps {
namespace MessageFactory {
const std::array<uint8_t, 4> PROTOCOL_TYPE{'R', 'T', 'P', 'S'};
const uint8_t numBytesUntilEndOfLength =
    4; // The first bytes incl. submessagelength don't count

template <class Buffer>
bool addHeader(Buffer &buffer, const GuidPrefix_t &guidPrefix) {

  Header header;
  header.protocolName = PROTOCOL_TYPE;
  header.protocolVersion = PROTOCOLVERSION;
  header.vendorId = Config::VENDOR_ID;
  header.guidPrefix = guidPrefix;

  return serializeMessage(buffer, header);
}

template <class Buffer>
bool addSubMessageInfoDST(Buffer &buffer, GuidPrefix_t &dst) {
  SubmessageInfoDST msg;
  msg.header.submessageId = SubmessageKind::INFO_DST;

#if IS_LITTLE_ENDIAN
  msg.header.flags = FLAG_LITTLE_ENDIAN;
#else
  msg.header.flags = FLAG_BIG_ENDIAN;
#endif

  msg.header.octetsToNextHeader = sizeof(GuidPrefix_t);
  msg.guidPrefix = dst;

  return serializeMessage(buffer, msg);
}

template <class Buffer>
bool addSubMessageTimeStamp(Buffer &buffer, bool setInvalid = false) {
  SubmessageHeader header;
  header.submessageId = SubmessageKind::INFO_TS;

#if IS_LITTLE_ENDIAN
  header.flags = FLAG_LITTLE_ENDIAN;
#else
  header.flags = FLAG_BIG_ENDIAN;
#endif

  if (setInvalid) {
    header.flags |= FLAG_INVALIDATE;
    header.octetsToNextHeader = 0;
  } else {
    header.octetsToNextHeader = sizeof(Time_t);
  }

  if (!serializeMessage(buffer, header)) {
    return false;
  }

  if (!setInvalid) {
    if (!buffer.reserve(header.octetsToNextHeader)) {
      return false;
    }
    Time_t now = getCurrentTimeStamp();
    return buffer.append(reinterpret_cast<uint8_t *>(&now.seconds),
                         sizeof(Time_t::seconds)) &&
           buffer.append(reinterpret_cast<uint8_t *>(&now.fraction),
                         sizeof(Time_t::fraction));
  }
  return true;
}

template <class Buffer>
bool addSubMessageDataFrag(Buffer &buffer, const Buffer &filledPayload,
                       bool containsInlineQos, const SequenceNumber_t &SN,
                       uint32_t fragStartingNumber,
                       uint16_t fragSize,
                       uint32_t sampleSize,
                       const EntityId_t &writerID, const EntityId_t &readerID) {
  const uint64_t payloadSize =
      static_cast<uint64_t>(filledPayload.spaceUsed());
  const uint64_t fragmentOffset =
      fragStartingNumber == 0
          ? UINT64_MAX
          : static_cast<uint64_t>(fragStartingNumber - 1U) * fragSize;
  if (containsInlineQos || !filledPayload.isValid() || payloadSize == 0 ||
      fragStartingNumber == 0 || fragSize == 0 || sampleSize == 0 ||
      fragmentOffset >= sampleSize ||
      payloadSize !=
          ((sampleSize - fragmentOffset) < fragSize
               ? sampleSize - fragmentOffset
               : fragSize)) {
    return false;
  }

  SubmessageDataFrag msg;
  msg.header.submessageId = SubmessageKind::DATA_FRAG;
#if IS_LITTLE_ENDIAN
  msg.header.flags = FLAG_LITTLE_ENDIAN;
#else
  msg.header.flags = FLAG_BIG_ENDIAN;
#endif

  msg.header.octetsToNextHeader = 0;

  msg.writerSN = SN;
  msg.extraFlags = 0;
  msg.readerId = readerID;
  msg.writerId = writerID;
  msg.fragStartingNumber = fragStartingNumber;
  msg.fragmentsInSubmessage = 1;
  msg.fragmentSize = fragSize;
  msg.sampleSize = sampleSize;

  constexpr uint16_t octetsToInlineQoS =
         4  + 4    + 8              + 4              + 2                     + 2            + 4;
      // EntityIds + SequenceNumber + FragmentNumber + fragmentsInSubmessage + fragmentSize + sampleSize
  msg.octetsToInlineQos = octetsToInlineQoS;

  if (!serializeMessage(buffer, msg)) {
    return false;
  }

  Buffer shallowCopy = filledPayload;
  buffer.append(std::move(shallowCopy));
  return true;
}

template <class Buffer>
bool addSubMessageData(Buffer &buffer, const Buffer &filledPayload,
                       bool containsInlineQos, const SequenceNumber_t &SN,
                       const EntityId_t &writerID, const EntityId_t &readerID) {
  constexpr uint32_t fixedBodySize =
      SubmessageData::getRawSize() - numBytesUntilEndOfLength;
  if (containsInlineQos || !filledPayload.isValid() ||
      filledPayload.spaceUsed() == 0) {
    return false;
  }
  const uint32_t payloadSize =
      static_cast<uint32_t>(filledPayload.spaceUsed());
  if (payloadSize > UINT16_MAX - fixedBodySize) {
    return false;
  }

  SubmessageData msg;
  msg.header.submessageId = SubmessageKind::DATA;
#if IS_LITTLE_ENDIAN
  msg.header.flags = FLAG_LITTLE_ENDIAN;
#else
  msg.header.flags = FLAG_BIG_ENDIAN;
#endif

  msg.header.octetsToNextHeader =
      static_cast<uint16_t>(fixedBodySize + payloadSize);

  msg.header.flags |= FLAG_DATA_PAYLOAD;

  msg.writerSN = SN;
  msg.extraFlags = 0;
  msg.readerId = readerID;
  msg.writerId = writerID;

  constexpr uint16_t octetsToInlineQoS =
      4 + 4 + 8; // EntityIds + SequenceNumber
  msg.octetsToInlineQos = octetsToInlineQoS;

  if (!serializeMessage(buffer, msg)) {
    return false;
  }

  Buffer shallowCopy = filledPayload;
  buffer.append(std::move(shallowCopy));
  return true;
}

template <class Buffer>
bool addHeartbeat(Buffer &buffer, EntityId_t writerId, EntityId_t readerId,
                  SequenceNumber_t firstSN, SequenceNumber_t lastSN,
                  Count_t count) {
  SubmessageHeartbeat subMsg;
  subMsg.header.submessageId = SubmessageKind::HEARTBEAT;
  subMsg.header.octetsToNextHeader =
      SubmessageHeartbeat::getRawSize() - numBytesUntilEndOfLength;
#if IS_LITTLE_ENDIAN
  subMsg.header.flags = FLAG_LITTLE_ENDIAN;
#else
  subMsg.header.flags = FLAG_BIG_ENDIAN;
#endif
  // Force response by not setting final flag.

  subMsg.writerId = writerId;
  subMsg.readerId = readerId;
  subMsg.firstSN = firstSN;
  subMsg.lastSN = lastSN;
  subMsg.count = count;

  return serializeMessage(buffer, subMsg);
}

template <class Buffer>
bool addGap(Buffer &buffer, EntityId_t writerId, EntityId_t readerId,
            SequenceNumber_t unavailableSN) {
  SubmessageGap subMsg;
  subMsg.header.submessageId = SubmessageKind::GAP;
#if IS_LITTLE_ENDIAN
  subMsg.header.flags = FLAG_LITTLE_ENDIAN;
#else
  subMsg.header.flags = FLAG_BIG_ENDIAN;
#endif
  subMsg.readerId = readerId;
  subMsg.writerId = writerId;
  subMsg.gapStart = unavailableSN;
  subMsg.gapList.base = unavailableSN;
  if (unavailableSN.high == INT32_MAX &&
      unavailableSN.low == UINT32_MAX) {
    subMsg.gapList.numBits = 1;
    subMsg.gapList.bitMap[0] = uint32_t{1} << 31;
  } else {
    ++subMsg.gapList.base;
    subMsg.gapList.numBits = 0;
  }
  subMsg.header.octetsToNextHeader =
      SubmessageGap::getRawSize(subMsg.gapList) - numBytesUntilEndOfLength;

  return serializeMessage(buffer, subMsg);
}

template <class Buffer>
bool addAckNack(Buffer &buffer, EntityId_t writerId, EntityId_t readerId,
                SequenceNumberSet readerSNState, Count_t count,
                bool final_flag) {
  SubmessageAckNack subMsg;
  subMsg.header.submessageId = SubmessageKind::ACKNACK;
#if IS_LITTLE_ENDIAN
  subMsg.header.flags = FLAG_LITTLE_ENDIAN;
#else
  subMsg.header.flags = FLAG_BIG_ENDIAN;
#endif
  if (final_flag) {
    subMsg.header.flags |= FLAG_FINAL; // For now, we don't want any response
  } else {
    subMsg.header.flags &= ~FLAG_FINAL; // For now, we don't want any response
  }
  subMsg.header.octetsToNextHeader =
      SubmessageAckNack::getRawSize(readerSNState) - numBytesUntilEndOfLength;

  subMsg.writerId = writerId;
  subMsg.readerId = readerId;
  subMsg.readerSNState = readerSNState;
  subMsg.count = count;

  return serializeMessage(buffer, subMsg);
}
} // namespace MessageFactory
} // namespace rtps

#endif // RTPS_MESSAGEFACTORY_H
