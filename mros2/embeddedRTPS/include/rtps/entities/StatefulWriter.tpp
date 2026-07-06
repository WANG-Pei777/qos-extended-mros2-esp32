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

#include "lwip/sys.h"
#include "rtps/entities/StatefulWriter.h"
#include "rtps/messages/MessageFactory.h"
#include "rtps/utils/Log.h"
#include "rtps/utils/sysFunctions.h"
#include <cstring>
#include <stdio.h>

using rtps::StatefulWriterT;

#if SFW_VERBOSE && RTPS_GLOBAL_VERBOSE
#include "rtps/utils/printutils.h"
#define SFW_LOG(...)                                                           \
  if (true) {                                                                  \
    printf("[Stateful Writer %s] ", this->m_attributes.topicName);             \
    printf(__VA_ARGS__);                                                       \
    printf("\n");                                                              \
  }
#else
#define SFW_LOG(...) //
#endif

template <class NetworkDriver>
StatefulWriterT<NetworkDriver>::~StatefulWriterT() {
  m_running = false;
  while (m_thread_running) {
    sys_msleep(500); // Required for tests/ Join currently not available /
    //  increased because Segfault in Tests if(sys_mutex_valid(&m_mutex)){
    //    sys_mutex_free(&m_mutex);
    //  }
  }
}

template <class NetworkDriver>
bool StatefulWriterT<NetworkDriver>::init(TopicData attributes,
                                          TopicKind_t topicKind,
                                          ThreadPool *threadPool,
                                          NetworkDriver &driver,
                                          bool enfUnicast) {
  if (sys_mutex_new(&m_mutex) != ERR_OK) {

    SFW_LOG("Failed to create mutex.\n");

    return false;
  }

  m_transport = &driver;
  m_attributes = attributes;
  m_topicKind = topicKind;
  m_packetInfo.srcPort = attributes.unicastLocator.port;
  m_enforceUnicast = enfUnicast;
  mp_threadPool = threadPool;
  if (m_attributes.endpointGuid.entityId ==
      ENTITYID_SEDP_BUILTIN_PUBLICATIONS_WRITER) {
    m_heartbeatThread = sys_thread_new("HBThreadPub", hbFunctionJumppad, this,
                                       Config::HEARTBEAT_STACKSIZE,
                                       Config::THREAD_POOL_WRITER_PRIO);
  } else if (m_attributes.endpointGuid.entityId ==
             ENTITYID_SEDP_BUILTIN_SUBSCRIPTIONS_WRITER) {
    m_heartbeatThread = sys_thread_new("HBThreadSub", hbFunctionJumppad, this,
                                       Config::HEARTBEAT_STACKSIZE,
                                       Config::THREAD_POOL_WRITER_PRIO);
  } else {
    m_heartbeatThread = sys_thread_new("HBThread", hbFunctionJumppad, this,
                                       Config::HEARTBEAT_STACKSIZE,
                                       Config::THREAD_POOL_WRITER_PRIO);
  }

  m_is_initialized_ = true;
  return true;
}

template <class NetworkDriver>
bool StatefulWriterT<NetworkDriver>::addNewMatchedReader(
    const ReaderProxy &newProxy) {
#if SFW_VERBOSE && RTPS_GLOBAL_VERBOSE
  SFW_LOG("New reader added with id: ");
  printGuid(newProxy.remoteReaderGuid);
#endif

  bool success = m_proxies.add(newProxy);
  if (!m_enforceUnicast) {
    manageSendOptions();
  }

  // Durability TRANSIENT_LOCAL: send HEARTBEAT then cached history to new reader.
  // The HEARTBEAT announces the available sequence number range so the remote
  // reader can process the subsequent DATA submessages correctly.
  if (success && m_attributes.durabilityKind == DurabilityKind_t::TRANSIENT_LOCAL) {
    Lock lock(m_mutex);
    SequenceNumber_t firstSN = m_history.getSeqNumMin();
    SequenceNumber_t lastSN = m_history.getSeqNumMax();

    if (firstSN != SEQUENCENUMBER_UNKNOWN && lastSN != SEQUENCENUMBER_UNKNOWN) {
      // Step 1: Send HEARTBEAT to announce available data range
      PacketInfo hbInfo;
      hbInfo.srcPort = m_packetInfo.srcPort;
      hbInfo.destAddr = newProxy.remoteLocator.getIp4Address();
      hbInfo.destPort = (Ip4Port_t)newProxy.remoteLocator.port;
      MessageFactory::addHeader(hbInfo.buffer, m_attributes.endpointGuid.prefix);
      MessageFactory::addHeartbeat(hbInfo.buffer,
          m_attributes.endpointGuid.entityId,
          newProxy.remoteReaderGuid.entityId,
          firstSN, lastSN, m_hbCount);
      m_transport->sendPacket(hbInfo);
      m_hbCount.value++;

      // Step 2: Send cached DATA as hint (reader may also ACKNACK)
      SequenceNumber_t sn = firstSN;
      while (sn <= lastSN) {
        const CacheChange *change = m_history.getChangeBySN(sn);
        if (change != nullptr) {
          PacketInfo info;
          info.srcPort = m_packetInfo.srcPort;
          info.destAddr = newProxy.remoteLocator.getIp4Address();
          info.destPort = (Ip4Port_t)newProxy.remoteLocator.port;
          MessageFactory::addHeader(info.buffer, m_attributes.endpointGuid.prefix);
          MessageFactory::addSubMessageTimeStamp(info.buffer);
          MessageFactory::addSubMessageData(
              info.buffer, change->data, false, change->sequenceNumber,
              m_attributes.endpointGuid.entityId,
              newProxy.remoteReaderGuid.entityId);
          m_transport->sendPacket(info);
        }
        ++sn;
      }
    }
  }

  return success;
}

template <class NetworkDriver>
void StatefulWriterT<NetworkDriver>::manageSendOptions() {

  SFW_LOG("Search for Multicast Partners!\n");

  for (auto &proxy : m_proxies) {
    if (proxy.remoteMulticastLocator.kind ==
        LocatorKind_t::LOCATOR_KIND_INVALID) {
      proxy.suppressUnicast = false;
      proxy.useMulticast = false;
    } else {
      bool found = false;
      for (auto &avproxy : m_proxies) {
        if (avproxy.remoteMulticastLocator.kind ==
                LocatorKind_t::LOCATOR_KIND_UDPv4 &&
            avproxy.remoteMulticastLocator.getIp4Address().addr ==
                proxy.remoteMulticastLocator.getIp4Address().addr &&
            avproxy.remoteLocator.getIp4Address().addr !=
                proxy.remoteLocator.getIp4Address().addr) {
          if (avproxy.suppressUnicast == false) {
            avproxy.useMulticast = false;
            avproxy.suppressUnicast = true;
            proxy.useMulticast = true;
            proxy.suppressUnicast = true;

            SFW_LOG("Found Multicast Partner!\n");

            if (avproxy.remoteReaderGuid.entityId !=
                proxy.remoteReaderGuid.entityId) {
              proxy.unknown_eid = true;

              SFW_LOG("Found different EntityIds, using UNKNOWN_ENTITYID\n");
            }
          }
          found = true;
        }
      }
      if (!found) {
        proxy.useMulticast = false;
        proxy.suppressUnicast = false;
      }
    }
  }
}

template <class NetworkDriver>
void StatefulWriterT<NetworkDriver>::resetSendOptions() {
  for (auto &proxy : m_proxies) {
    proxy.suppressUnicast = false;
    proxy.useMulticast = false;
    proxy.unknown_eid = false;
  }
  manageSendOptions();
}

// TODO: manage Multicast Options again...
template <class NetworkDriver>
void StatefulWriterT<NetworkDriver>::removeReader(const Guid_t &guid) {
  Lock lock(m_mutex);
  auto isElementToRemove = [&](const ReaderProxy &proxy) {
    return proxy.remoteReaderGuid == guid;
  };
  auto thunk = [](void *arg, const ReaderProxy &value) {
    return (*static_cast<decltype(isElementToRemove) *>(arg))(value);
  };

  m_proxies.remove(thunk, &isElementToRemove);
  resetSendOptions();
}

template <class NetworkDriver>
void StatefulWriterT<NetworkDriver>::removeReaderOfParticipant(
    const GuidPrefix_t &guidPrefix) {
  Lock lock(m_mutex);
  auto isElementToRemove = [&](const ReaderProxy &proxy) {
    return proxy.remoteReaderGuid.prefix == guidPrefix;
  };
  auto thunk = [](void *arg, const ReaderProxy &value) {
    return (*static_cast<decltype(isElementToRemove) *>(arg))(value);
  };

  m_proxies.remove(thunk, &isElementToRemove);
  resetSendOptions();
}

template <class NetworkDriver>
const rtps::CacheChange *StatefulWriterT<NetworkDriver>::newChangeCallback(
    ChangeKind_t kind, CacheChange::SerializerCallback func, FragDataSize_t size){
  if (isIrrelevant(kind)) {
    return nullptr;
  }

  Lock lock{m_mutex};

  if (!m_keepAll && m_historyDepth > 0) {
    while (m_history.getChangeCount() >= m_historyDepth) {
      m_history.dropOldest();
      SequenceNumber_t newMin = m_history.getSeqNumMin();
      if (newMin != SEQUENCENUMBER_UNKNOWN &&
          m_nextSequenceNumberToSend < newMin) {
        m_nextSequenceNumberToSend = newMin;
      }
    }
  }

  if (m_maxSamples > 0 && m_history.getChangeCount() >= m_maxSamples) {
    m_resourceRejectCount++;
    return nullptr;
  }
  if (m_maxBytes > 0 && m_history.getTotalDataBytes() + size > m_maxBytes) {
    m_resourceRejectCount++;
    return nullptr;
  }

  if (m_history.isFull()) {
    if (m_keepAll) {
      m_resourceRejectCount++;
      return nullptr;
    }
    SequenceNumber_t newMin = ++SequenceNumber_t(m_history.getSeqNumMin());
    if (m_nextSequenceNumberToSend < newMin) {
      m_nextSequenceNumberToSend = newMin;
    }
  }

  auto *result = m_history.addChange(func, size);

  if (result != nullptr) {
    uint32_t now = rtps::getCurrentTimeMs();
    const_cast<CacheChange*>(result)->timestampMs = now;
    m_lastPublishTimeMs = now;
    m_nextDeadlineTimeMs = m_deadlineMs > 0 ? now + m_deadlineMs : 0;
  }

  if (mp_threadPool != nullptr) {
    mp_threadPool->addWorkload(this);
  }

  return result;
}

template <class NetworkDriver>
const rtps::CacheChange *StatefulWriterT<NetworkDriver>::newChange(
    ChangeKind_t kind, const uint8_t *data, DataSize_t size) {
  if (isIrrelevant(kind)) {
    return nullptr;
  }

  Lock lock{m_mutex};

  if (!m_keepAll && m_historyDepth > 0) {
    while (m_history.getChangeCount() >= m_historyDepth) {
      m_history.dropOldest();
      SequenceNumber_t newMin = m_history.getSeqNumMin();
      if (newMin != SEQUENCENUMBER_UNKNOWN &&
          m_nextSequenceNumberToSend < newMin) {
        m_nextSequenceNumberToSend = newMin;
      }
    }
  }

  // Resource Limits: reject if limits exceeded after KEEP_LAST cleanup.
  if (m_maxSamples > 0 && m_history.getChangeCount() >= m_maxSamples) {
    m_resourceRejectCount++;
    return nullptr;
  }
  if (m_maxBytes > 0 && m_history.getTotalDataBytes() + size > m_maxBytes) {
    m_resourceRejectCount++;
    return nullptr;
  }

  if (m_history.isFull()) {
    if (m_keepAll) {
      // History KEEP_ALL: don't overwrite, reject new message
      m_resourceRejectCount++;
      return nullptr;
    }
    // History KEEP_LAST: drop oldest (existing behavior)
    SequenceNumber_t newMin = ++SequenceNumber_t(m_history.getSeqNumMin());
    if (m_nextSequenceNumberToSend < newMin) {
      m_nextSequenceNumberToSend = newMin;
    }
  }

  auto *result = m_history.addChange(data, size);

  // Set timestamp for Lifespan QoS and update Deadline timer
  if (result != nullptr) {
    uint32_t now = rtps::getCurrentTimeMs();
    const_cast<CacheChange*>(result)->timestampMs = now;
    m_lastPublishTimeMs = now;
    m_nextDeadlineTimeMs = m_deadlineMs > 0 ? now + m_deadlineMs : 0;
  }

  if (mp_threadPool != nullptr) {
    mp_threadPool->addWorkload(this);
  }

  SFW_LOG("Adding new data.\n");

  return result;
}

template <class NetworkDriver> void StatefulWriterT<NetworkDriver>::progress() {
  // Lifespan check: skip expired messages before sending
  if (m_lifespanMs > 0) {
    Lock lock(m_mutex);
    const CacheChange *change = m_history.getChangeBySN(m_nextSequenceNumberToSend);
    if (change != nullptr) {
      uint32_t now = rtps::getCurrentTimeMs();
      if (change->timestampMs > 0 && (now - change->timestampMs) > m_lifespanMs) {
        m_lifespanDropCount++;
        printf("[RTPS Lifespan] Dropped SN(%u,%u) age=%ums > %ums (total drops=%u)\n",
               (unsigned int)change->sequenceNumber.high,
               (unsigned int)change->sequenceNumber.low,
               (unsigned int)(now - change->timestampMs),
               (unsigned int)m_lifespanMs,
               (unsigned int)m_lifespanDropCount);
        ++m_nextSequenceNumberToSend;
        return;
      }
    }
  }

  if (m_proxies.getNumElements() > 0) {
    // Normal path: send to all matched readers.
    for (const auto &proxy : m_proxies) {
      bool success;
      if (!m_enforceUnicast) {
        success = sendDataWRMulticast(proxy, m_nextSequenceNumberToSend);
      } else {
        success = sendData(proxy, m_nextSequenceNumberToSend);
      }

      if (!success) {
        continue;
      }
    }
  } else {
    // Fallback path: no matched readers yet, send to the multicast address.
    // Create a temporary proxy for multicast transmission.
    ReaderProxy tempProxy;
    tempProxy.remoteReaderGuid = Guid_t{GUIDPREFIX_UNKNOWN, ENTITYID_UNKNOWN};
    tempProxy.remoteLocator = LocatorIPv4{};
    tempProxy.remoteMulticastLocator = LocatorIPv4{};
    tempProxy.useMulticast = true;
    tempProxy.suppressUnicast = false;

    // Send to the multicast address.
    sendDataWRMulticast(tempProxy, m_nextSequenceNumberToSend);
  }

  ++m_nextSequenceNumberToSend;
}

template <typename NetworkDriver>
bool StatefulWriterT<NetworkDriver>::isIrrelevant(ChangeKind_t kind) const {
  // Right now we only allow alive changes
  // return kind == ChangeKind_t::INVALID || (m_topicKind == TopicKind_t::NO_KEY
  // && kind != ChangeKind_t::ALIVE);
  return kind != ChangeKind_t::ALIVE;
}

template <class NetworkDriver>
void StatefulWriterT<NetworkDriver>::setAllChangesToUnsent() {
  Lock lock(m_mutex);

  m_nextSequenceNumberToSend = m_history.getSeqNumMin();

  if (mp_threadPool != nullptr) {
    mp_threadPool->addWorkload(this);
  }
}

template <class NetworkDriver>
void StatefulWriterT<NetworkDriver>::onNewAckNack(
    const SubmessageAckNack &msg, const GuidPrefix_t &sourceGuidPrefix) {
  ReaderProxy *reader = nullptr;
  for (auto &proxy : m_proxies) {
    if (proxy.remoteReaderGuid.prefix == sourceGuidPrefix &&
        proxy.remoteReaderGuid.entityId == msg.readerId) {
      reader = &proxy;
      break;
    }
  }

  if (reader == nullptr) {
#if SFW_VERBOSE && RTPS_GLOBAL_VERBOSE
    SFW_LOG("No proxy found with id: ");
    printEntityId(msg.readerId);
    SFW_LOG(" Dropping acknack.\n");
#endif
    return;
  }

  uint8_t hash = 0;
  for (unsigned int i = 0; i < sourceGuidPrefix.id.size(); i++) {
    hash += sourceGuidPrefix.id.at(i);
  }

  char bfr[20];
  size_t size = snprintf(bfr, sizeof(bfr), "%u <= %u", msg.count.value,
                         reader->ackNackCount.value);
  if (!(size < sizeof(bfr))) {
    while (1)
      ;
  }

  if (msg.count.value <= reader->ackNackCount.value) {

    SFW_LOG("Count too small. Dropping acknack.\n");

    return;
  }

  reader->ackNackCount = msg.count;

  // Send missing packets
  SequenceNumber_t nextSN = msg.readerSNState.base;

  if (nextSN.low == 0 && nextSN.high == 0) {
    SFW_LOG("Received preemptive acknack. Ignored.\n");
  } else {
    SFW_LOG("Received non-preemptive acknack.\n");
  }

  for (uint32_t i = 0; i < msg.readerSNState.numBits; ++i, ++nextSN) {
    if (msg.readerSNState.isSet(i)) {

      SFW_LOG("Send Packet on acknack.\n");

      sendData(*reader, nextSN);
    }
  }
  // Check for sequence numbers after defined range
  SequenceNumber_t maxSN;
  {
    Lock lock(m_mutex);
    maxSN = m_history.getSeqNumMax();
  }
  while (nextSN <= maxSN) {
    sendData(*reader, nextSN);
    ++nextSN;
  }
}

template <class NetworkDriver>
bool StatefulWriterT<NetworkDriver>::sendData(
    const ReaderProxy &reader, const SequenceNumber_t &snMissing) {

  Lock lock(m_mutex);
  const CacheChange *next = m_history.getChangeBySN(snMissing);
  if (next == nullptr) {
    SFW_LOG("Couldn't get a CacheChange with SN (%i,%u)\n", snMissing.high,
            snMissing.low);
    return false;
  }

  const LocatorIPv4 &locator = reader.remoteLocator;

  if (next->serializerCallback) {
    // Fragmented path: call serializer to get data chunks, send as DATA_FRAG
    FragDataSize_t sampleSize = next->sizeToBeSerialized;
    CacheChange::SerializedBuf serialized_buf;
    int fragment_start_number = 1;
    while (1) {
      serialized_buf = next->serializerCallback();
      if (0 == serialized_buf.second) break;

      PBufWrapper fragData;
      fragData.reserve(serialized_buf.second);
      fragData.append(serialized_buf.first, serialized_buf.second);

      PacketInfo info;
      info.srcPort = m_packetInfo.srcPort;
      info.destAddr = locator.getIp4Address();
      info.destPort = (Ip4Port_t)locator.port;
      MessageFactory::addHeader(info.buffer, m_attributes.endpointGuid.prefix);
      MessageFactory::addSubMessageTimeStamp(info.buffer);
      MessageFactory::addSubMessageDataFrag(
          info.buffer, fragData, false, next->sequenceNumber,
          fragment_start_number++, serialized_buf.second, sampleSize,
          m_attributes.endpointGuid.entityId,
          reader.remoteReaderGuid.entityId);
      m_transport->sendPacket(info);
    }
  } else {
    // Normal path: single DATA submessage
    PacketInfo info;
    info.srcPort = m_packetInfo.srcPort;
    info.destAddr = locator.getIp4Address();
    info.destPort = (Ip4Port_t)locator.port;
    MessageFactory::addHeader(info.buffer, m_attributes.endpointGuid.prefix);
    MessageFactory::addSubMessageTimeStamp(info.buffer);
    MessageFactory::addSubMessageData(
        info.buffer, next->data, false, next->sequenceNumber,
        m_attributes.endpointGuid.entityId, reader.remoteReaderGuid.entityId);
    m_transport->sendPacket(info);
  }
  return true;
}

template <class NetworkDriver>
bool StatefulWriterT<NetworkDriver>::sendDataWRMulticast(
    const ReaderProxy &reader, const SequenceNumber_t &snMissing) {

  if (reader.useMulticast || reader.suppressUnicast == false) {
    PacketInfo info;
    info.srcPort = m_packetInfo.srcPort;

    MessageFactory::addHeader(info.buffer, m_attributes.endpointGuid.prefix);
    MessageFactory::addSubMessageTimeStamp(info.buffer);

    // Deceide whether multicast or not
    if (reader.useMulticast) {
      const LocatorIPv4 &locator = reader.remoteMulticastLocator;
      info.destAddr = locator.getIp4Address();
      info.destPort = (Ip4Port_t)locator.port;
    } else {
      const LocatorIPv4 &locator = reader.remoteLocator;
      info.destAddr = locator.getIp4Address();
      info.destPort = (Ip4Port_t)locator.port;
    }

    {
      Lock lock(m_mutex);
      const CacheChange *next = m_history.getChangeBySN(snMissing);
      if (next == nullptr) {

        SFW_LOG("Couldn't get a CacheChange with SN (%i,%u)\n", snMissing.high,
                snMissing.low);

        return false;
      }

      EntityId_t reid;
      if (reader.useMulticast) {
        reid = ENTITYID_UNKNOWN;
      } else {
        reid = reader.remoteReaderGuid.entityId;
      }

      MessageFactory::addSubMessageData(
          info.buffer, next->data, false, next->sequenceNumber,
          m_attributes.endpointGuid.entityId, reid);
    }

    m_transport->sendPacket(info);
  }
  return true;
}

template <class NetworkDriver>
void StatefulWriterT<NetworkDriver>::hbFunctionJumppad(void *thisPointer) {
  auto *writer = static_cast<StatefulWriterT<NetworkDriver> *>(thisPointer);
  writer->sendHeartBeatLoop();
}

template <class NetworkDriver>
void StatefulWriterT<NetworkDriver>::sendHeartBeatLoop() {
  m_thread_running = true;
  while (m_running) {
    // Deadline check: count each missed period once and advance the baseline.
    if (m_deadlineMs > 0 && m_nextDeadlineTimeMs > 0) {
      uint32_t now = rtps::getCurrentTimeMs();
      if (now > m_nextDeadlineTimeMs) {
        uint32_t missed = 1 + static_cast<uint32_t>(
            (now - m_nextDeadlineTimeMs) / m_deadlineMs);
        m_deadlineMissedCount += missed;
        m_nextDeadlineTimeMs += static_cast<uint64_t>(missed) * m_deadlineMs;
      }
    }
    sendHeartBeat();
#ifdef OS_IS_FREERTOS
    vTaskDelay(pdMS_TO_TICKS(Config::SF_WRITER_HB_PERIOD_MS));
#else
    sys_msleep(Config::SF_WRITER_HB_PERIOD_MS);
#endif
  }
  m_thread_running = false;
}

template <class NetworkDriver>
void StatefulWriterT<NetworkDriver>::sendHeartBeat() {
  if (m_proxies.isEmpty()) {

    SFW_LOG("Skipping heartbeat. No proxies.\n");
    return;
  }

  for (auto &proxy : m_proxies) {

    PacketInfo info;
    info.srcPort = m_packetInfo.srcPort;

    SequenceNumber_t firstSN;
    SequenceNumber_t lastSN;
    MessageFactory::addHeader(info.buffer, m_attributes.endpointGuid.prefix);
    {
      Lock lock(m_mutex);
      firstSN = m_history.getSeqNumMin();
      lastSN = m_history.getSeqNumMax();
    }
    if (firstSN == SEQUENCENUMBER_UNKNOWN || lastSN == SEQUENCENUMBER_UNKNOWN) {

      if (strlen(&this->m_attributes.typeName[0]) != 0) {
        SFW_LOG("Skipping heartbeat. No data.\n");
      }
      return;
    }

    MessageFactory::addHeartbeat(
        info.buffer, m_attributes.endpointGuid.entityId,
        proxy.remoteReaderGuid.entityId, firstSN, lastSN, m_hbCount);

    info.destAddr = proxy.remoteLocator.getIp4Address();
    info.destPort = proxy.remoteLocator.port;
    m_transport->sendPacket(info);
  }
  m_hbCount.value++;
}

#undef SFW_VERBOSE
