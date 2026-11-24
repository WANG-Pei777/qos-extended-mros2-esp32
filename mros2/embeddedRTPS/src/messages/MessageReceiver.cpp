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

#include "rtps/messages/MessageReceiver.h"
#include <rtps/entities/Participant.h>

#include "rtps/entities/Reader.h"
#include "rtps/entities/Writer.h"
#include "rtps/messages/MessageTypes.h"
#include "rtps/utils/Log.h"

using rtps::MessageReceiver;

#if RECV_VERBOSE && RTPS_GLOBAL_VERBOSE
#include "rtps/utils/printutils.h"
#define RECV_LOG(...)                                                          \
  if (true) {                                                                  \
    printf("[RECV] ");                                                         \
    printf(__VA_ARGS__);                                                       \
    printf("\n");                                                              \
  }
#else
#define RECV_LOG(...) //
#endif

MessageReceiver::MessageReceiver(Participant *part) : mp_part(part) {}

void MessageReceiver::resetState() {
  sourceGuidPrefix = GUIDPREFIX_UNKNOWN;
  sourceVersion = PROTOCOLVERSION;
  sourceVendor = VENDOR_UNKNOWN;
  haveTimeStamp = false;
  m_destinationMatches = true;
}

bool MessageReceiver::processMessage(const uint8_t *data, DataSize_t size) {
  // Validate minimum packet size: RTPS Header is 20 bytes minimum
  if (data == nullptr || size < Header::getRawSize()) {
    return false;
  }

  resetState();
  MessageProcessingInfo msgInfo(data, size);

  if (!processHeader(msgInfo)) {
    return false;
  }
  SubmessageHeader submsgHeader;
  while (msgInfo.nextPos < msgInfo.size) {
    if (!deserializeMessage(msgInfo, submsgHeader)) {
      return false;
    }
    if (!processSubmessage(msgInfo, submsgHeader)) {
      return false;
    }
  }

  return true;
}

bool MessageReceiver::processHeader(MessageProcessingInfo &msgInfo) {
  Header header;
  if (!deserializeMessage(msgInfo, header)) {
    return false;
  }

  if (header.guidPrefix.id == mp_part->m_guidPrefix.id) {
    RECV_LOG("[MessageReceiver]: Received own message.\n");
    return false; // Don't process our own packet
  }

  if (header.protocolName != RTPS_PROTOCOL_NAME ||
      header.protocolVersion.major != PROTOCOLVERSION.major) {
    return false;
  }

  sourceGuidPrefix = header.guidPrefix;
  sourceVendor = header.vendorId;
  sourceVersion = header.protocolVersion;

  msgInfo.nextPos += Header::getRawSize();
  return true;
}

bool MessageReceiver::processSubmessage(MessageProcessingInfo &msgInfo,
                                        const SubmessageHeader &submsgHeader) {
  const uint32_t remaining = msgInfo.getRemainingSize();
  const bool invalidInfoTimestamp =
      submsgHeader.submessageId == SubmessageKind::INFO_TS &&
      (submsgHeader.flags & FLAG_INVALIDATE) != 0;
  if (submsgHeader.submessageId == SubmessageKind::INFO_TS &&
      !infoTimestampLengthValid(
          submsgHeader.flags, submsgHeader.octetsToNextHeader)) {
    return false;
  }
  const uint32_t totalSubmsgSize =
      invalidInfoTimestamp
          ? SubmessageHeader::getRawSize()
          : (submsgHeader.octetsToNextHeader == 0
                 ? remaining
                 : static_cast<uint32_t>(
                       submsgHeader.octetsToNextHeader) +
                       SubmessageHeader::getRawSize());
  if (totalSubmsgSize < SubmessageHeader::getRawSize() ||
      totalSubmsgSize > remaining) {
    return false;
  }

  SubmessageHeader effectiveHeader = submsgHeader;
  effectiveHeader.octetsToNextHeader = static_cast<uint16_t>(
      totalSubmsgSize - SubmessageHeader::getRawSize());
  bool success = false;

  if (!m_destinationMatches &&
      effectiveHeader.submessageId != SubmessageKind::INFO_DST) {
    success = true;
  } else switch (effectiveHeader.submessageId) {
  case SubmessageKind::ACKNACK:
    RECV_LOG("Processing AckNack submessage\n");
    success = processAckNackSubmessage(msgInfo);
    break;
  case SubmessageKind::DATA:
    RECV_LOG("Processing Data submessage\n");
    success = processDataSubmessage(msgInfo, effectiveHeader);
    break;
  case SubmessageKind::DATA_FRAG:
    RECV_LOG("Processing DataFrag submessage\n");
    success = processDataFragSubmessage(msgInfo, effectiveHeader);
    break;
  case SubmessageKind::HEARTBEAT:
    RECV_LOG("Processing Heartbeat submessage\n");
    success = processHeartbeatSubmessage(msgInfo);
    break;
  case SubmessageKind::GAP:
    RECV_LOG("Processing Gap submessage\n");
    success = processGapSubmessage(msgInfo);
    break;
  case SubmessageKind::INFO_DST:
    success = processInfoDestinationSubmessage(msgInfo);
    break;
  case SubmessageKind::INFO_TS:
    haveTimeStamp = !invalidInfoTimestamp;
    success = true;
    break;
  default:
    RECV_LOG("Submessage of type %u currently not supported. Skipping..\n",
             static_cast<uint8_t>(effectiveHeader.submessageId));
    success = true;
  }

  if (!msgInfo.advance(static_cast<DataSize_t>(totalSubmsgSize))) {
    return false;
  }

  return success;
}

bool MessageReceiver::processInfoDestinationSubmessage(
    MessageProcessingInfo &msgInfo) {
  SubmessageInfoDST infoDestination;
  if (!deserializeMessage(msgInfo, infoDestination)) {
    return false;
  }
  m_destinationMatches =
      infoDestination.guidPrefix == GUIDPREFIX_UNKNOWN ||
      infoDestination.guidPrefix == mp_part->m_guidPrefix;
  return true;
}

bool MessageReceiver::processDataSubmessage(
    MessageProcessingInfo &msgInfo, const SubmessageHeader &submsgHeader) {
  SubmessageData dataSubmsg;
  if (!deserializeMessage(msgInfo, dataSubmsg)) {
    return false;
  }
  // Bounds check: ensure enough data remains for the payload
  constexpr uint16_t dataHeaderSize = SubmessageData::getRawSize();
  constexpr uint16_t fixedBodySize =
      dataHeaderSize - SubmessageHeader::getRawSize();
  if (submsgHeader.octetsToNextHeader < fixedBodySize) {
    return false;
  }

  const uint8_t *serializedData =
      msgInfo.getPointerToCurrentPos() + dataHeaderSize;

  const DataSize_t size =
      submsgHeader.octetsToNextHeader - fixedBodySize;
  if (!dataPayloadContractSupported(dataSubmsg, size)) {
    return false;
  }

  RECV_LOG("Received data message size %u", (int)size);

  Guid_t writerGuid{sourceGuidPrefix, dataSubmsg.writerId};
  ReaderCacheChange change{ChangeKind_t::ALIVE, writerGuid,
                           dataSubmsg.writerSN, serializedData, size};
  if (dataSubmsg.readerId == ENTITYID_UNKNOWN) {
    mp_part->deliverChangeToReaders(change);
  } else {
    Reader *reader = findReader(dataSubmsg.readerId, dataSubmsg.writerId);
    if (reader != nullptr) {
    reader->newChange(change);
    } else {
#if RECV_VERBOSE && RTPS_GLOBAL_VERBOSE
      RECV_LOG("Couldn't find a reader with id: ");
      printEntityId(dataSubmsg.readerId);
      printf("\n");
#endif
    }
  }

  return true;
}

bool MessageReceiver::processDataFragSubmessage(
    MessageProcessingInfo &msgInfo, const SubmessageHeader &submsgHeader) {
  SubmessageDataFrag dataFrag;
  if (!deserializeMessage(msgInfo, dataFrag)) {
    return false;
  }

  constexpr uint16_t fixedBodySize =
      SubmessageDataFrag::getRawSize() - SubmessageHeader::getRawSize();
  if (submsgHeader.octetsToNextHeader < fixedBodySize ||
      !dataFragPayloadContractSupported(dataFrag)) {
    return false;
  }

  const DataSize_t payloadSize = static_cast<DataSize_t>(
      submsgHeader.octetsToNextHeader - fixedBodySize);
  const uint8_t *payload =
      msgInfo.getPointerToCurrentPos() + SubmessageDataFrag::getRawSize();
  Guid_t writerGuid{sourceGuidPrefix, dataFrag.writerId};
  ReassembledSample completed;
  const auto result = m_fragmentReassembler.addFragment(
      writerGuid, dataFrag.writerSN, dataFrag.fragStartingNumber,
      dataFrag.fragmentsInSubmessage, dataFrag.fragmentSize,
      dataFrag.sampleSize, payload, payloadSize, completed);
  if (result == FragmentReassemblyResult::REJECTED) {
    return false;
  }
  if (result == FragmentReassemblyResult::ACCEPTED_INCOMPLETE) {
    return true;
  }

  ReaderCacheChange change{ChangeKind_t::ALIVE, writerGuid, dataFrag.writerSN,
                           completed.data, completed.size};
  if (dataFrag.readerId == ENTITYID_UNKNOWN) {
    mp_part->deliverChangeToReaders(change);
    return true;
  }
  Reader *reader = findReader(dataFrag.readerId, dataFrag.writerId);
  if (reader != nullptr) {
    reader->newChange(change);
  }
  return true;
}

rtps::Reader *MessageReceiver::findReader(const EntityId_t &readerId,
                                          const EntityId_t &writerId) const {
  Reader *reader;
  if (readerId == ENTITYID_UNKNOWN) {
#if RECV_VERBOSE && RTPS_GLOBAL_VERBOSE
    RECV_LOG("Received ENTITYID_UNKNOWN readerID, searching for writer ID = ");
    printGuid(Guid_t{sourceGuidPrefix, writerId});
    printf("\n");
#endif
    reader = mp_part->getReaderByWriterId(Guid_t{sourceGuidPrefix, writerId});
    if (reader != nullptr)
      RECV_LOG("Found reader!");
  } else {
    reader = mp_part->getReader(readerId);
#if RECV_VERBOSE && RTPS_GLOBAL_VERBOSE
    auto reader_by_writer =
        mp_part->getReaderByWriterId(Guid_t{sourceGuidPrefix, writerId});

    if (reader_by_writer == nullptr && reader != nullptr) {
      RECV_LOG("FOUND By READER ID, NOT BY WRITER ID =");
      printGuid(Guid_t{sourceGuidPrefix, writerId});
      printf("\n");
    }
#endif
  }
  return reader;
}

bool MessageReceiver::processHeartbeatSubmessage(
    MessageProcessingInfo &msgInfo) {
  SubmessageHeartbeat submsgHB;
  if (!deserializeMessage(msgInfo, submsgHB)) {
    return false;
  }

  if (submsgHB.readerId == ENTITYID_UNKNOWN) {
    const uint32_t delivered =
        mp_part->deliverHeartbeatToReaders(submsgHB, sourceGuidPrefix);
    if (delivered != 0) {
      mp_part->addHeartbeat(sourceGuidPrefix);
    }
    return true;
  }
  Reader *reader = findReader(submsgHB.readerId, submsgHB.writerId);
  if (reader != nullptr) {
    reader->onNewHeartbeat(submsgHB, sourceGuidPrefix);
    mp_part->addHeartbeat(sourceGuidPrefix);
    return true;
  } else {
    return true;
  }
}

bool MessageReceiver::processAckNackSubmessage(MessageProcessingInfo &msgInfo) {
  SubmessageAckNack submsgAckNack;
  if (!deserializeMessage(msgInfo, submsgAckNack)) {
    return false;
  }

  Writer *writer = mp_part->getWriter(submsgAckNack.writerId);
  if (writer != nullptr) {
    writer->onNewAckNack(submsgAckNack, sourceGuidPrefix);
    return true;
  } else {
    return true;
  }
}

bool MessageReceiver::processGapSubmessage(MessageProcessingInfo &msgInfo) {
  SubmessageGap submsgGap;
  if (!deserializeMessage(msgInfo, submsgGap)) {
    return false;
  }

  if (submsgGap.readerId == ENTITYID_UNKNOWN) {
    mp_part->deliverGapToReaders(submsgGap, sourceGuidPrefix);
    return true;
  }
  Reader *reader = findReader(submsgGap.readerId, submsgGap.writerId);
  if (reader != nullptr) {
    reader->onNewGap(submsgGap, sourceGuidPrefix);
  }
  return true;
}

#undef RECV_VERBOSE
