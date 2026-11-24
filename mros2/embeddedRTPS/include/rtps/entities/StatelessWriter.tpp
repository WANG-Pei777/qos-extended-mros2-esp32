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

#include <rtps/entities/ReaderProxy.h>

#include "lwip/sys.h"
#include "lwip/tcpip.h"
#include "rtps/ThreadPool.h"
#include "rtps/communication/UdpDriver.h"
#include "rtps/messages/MessageFactory.h"
#include "rtps/storages/PBufWrapper.h"
#include "rtps/utils/Log.h"
#include "rtps/utils/udpUtils.h"

using rtps::CacheChange;
using rtps::SequenceNumber_t;
using rtps::StatelessWriterT;

#if SLW_VERBOSE && RTPS_GLOBAL_VERBOSE
#include "rtps/utils/printutils.h"
#define SLW_LOG(...)                                                           \
  if (true) {                                                                  \
    printf("[StatelessWriter %s] ", &this->m_attributes.topicName[0]);         \
    printf(__VA_ARGS__);                                                       \
    printf("\n");                                                              \
  }
#else
#define SLW_LOG(...) //
#endif

template <class NetworkDriver>
StatelessWriterT<NetworkDriver>::~StatelessWriterT() {
  //  if(sys_mutex_valid(&m_mutex)){
  //    sys_mutex_free(&m_mutex);
  //  }
}

template <typename NetworkDriver>
bool StatelessWriterT<NetworkDriver>::init(TopicData attributes,
                                           TopicKind_t topicKind,
                                           ThreadPool *threadPool,
                                           NetworkDriver &driver,
                                           bool enfUnicast) {
  if (sys_mutex_new(&m_mutex) != ERR_OK) {
#if SLW_VERBOSE
    SLW_LOG("Failed to create mutex \n");
#endif
    return false;
  }

  m_attributes = attributes;
  m_packetInfo.srcPort = attributes.unicastLocator.port;
  m_topicKind = topicKind;
  mp_threadPool = threadPool;
  m_transport = &driver;
  m_enforceUnicast = enfUnicast;

  m_is_initialized_ = true;
  return true;
}

template <class NetworkDriver>
bool StatelessWriterT<NetworkDriver>::addNewMatchedReader(
    const ReaderProxy &newProxy) {
#if SLW_VERBOSE && RTPS_GLOBAL_VERBOSE
  SLW_LOG("New reader added with id: ");
  printGuid(newProxy.remoteReaderGuid);
#endif
  bool success = false;
  bool hasHistoricalReplay = false;
  bool scheduleOrdinaryReplayRecovery = false;
  SequenceNumber_t replayFirst = SEQUENCENUMBER_UNKNOWN;
  SequenceNumber_t replayLast = SEQUENCENUMBER_UNKNOWN;
  ReaderProxy matchedProxy = newProxy;
  {
    Lock lock(m_mutex);
    for (const auto &proxy : m_proxies) {
      if (proxy.remoteReaderGuid == matchedProxy.remoteReaderGuid) {
        return false;
      }
    }
    if (!readerRequestsHistoricalData(matchedProxy.durabilityKind)) {
      initializeVolatileReaderBoundary(
          m_history.getLastUsedSequenceNumber(),
          matchedProxy.firstRelevantSequence,
          matchedProxy.noRelevantSequence);
    }
    const bool hadMatchedReaders = !m_proxies.isEmpty();
    success = m_proxies.add(matchedProxy);
    if (success && shouldDiscardUnmatchedHistoryOnReaderMatch(
                       m_attributes.durabilityKind, hadMatchedReaders)) {
      const SequenceNumber_t lastSN = m_history.getSeqNumMax();
      if (lastSN != SEQUENCENUMBER_UNKNOWN) {
        m_history.removeUntilIncl(lastSN);
        advanceSendCursorAfterSnapshot(m_nextSequenceNumberToSend,
                                       m_sendCursorExhausted, lastSN);
      }
    }
    if (success && !m_transmissionHeld &&
        m_attributes.durabilityKind == DurabilityKind_t::TRANSIENT_LOCAL &&
        readerRequestsHistoricalData(matchedProxy.durabilityKind)) {
      const SequenceNumber_t firstSN = m_history.getSeqNumMin();
      const SequenceNumber_t lastSN = m_history.getSeqNumMax();
      if (firstSN != SEQUENCENUMBER_UNKNOWN &&
          lastSN != SEQUENCENUMBER_UNKNOWN && !(lastSN < firstSN)) {
        replayFirst = firstSN;
        replayLast = lastSN;
        hasHistoricalReplay = true;
      }
    } else if (success &&
               !readerRequestsHistoricalData(matchedProxy.durabilityKind) &&
               mayAdvanceGlobalCursorForVolatileMatch(hadMatchedReaders) &&
               matchedProxy.firstRelevantSequence != SEQUENCENUMBER_UNKNOWN &&
               m_nextSequenceNumberToSend <
                   matchedProxy.firstRelevantSequence) {
      m_nextSequenceNumberToSend = matchedProxy.firstRelevantSequence;
    }
    // Linearize Transient Local replay with matching. Keeping the Writer lock
    // across the bounded replay prevents a racing Keep Last publication from
    // evicting a later item in the frozen window.
    if (hasHistoricalReplay) {
      SequenceNumber_t sn = replayFirst;
      bool replaySucceeded = true;
      SequenceNumber_t firstFailed = SEQUENCENUMBER_UNKNOWN;
      while (sn <= replayLast) {
        bool replaySent = false;
        for (uint8_t attempt = 0;
             attempt <= SEND_RETRY_LIMIT && !replaySent; ++attempt) {
          replaySent = sendDataLocked(matchedProxy, sn);
        }
        if (!replaySent &&
            firstFailed == SEQUENCENUMBER_UNKNOWN) {
          firstFailed = sn;
          replaySucceeded = false;
          break;
        }
        replaySucceeded = replaySent && replaySucceeded;
        if (sn == replayLast) {
          break;
        }
        ++sn;
      }
      if (replaySucceeded &&
          mayAdvanceGlobalCursorAfterDirectedReplay(hadMatchedReaders)) {
        advanceSendCursorAfterSnapshot(m_nextSequenceNumberToSend,
                                       m_sendCursorExhausted, replayLast);
      }
      scheduleOrdinaryReplayRecovery =
          shouldScheduleOrdinaryReplayRecovery(replaySucceeded,
                                               hadMatchedReaders);
      if (scheduleOrdinaryReplayRecovery) {
        ++m_localSendFailureCount;
        retainEarliestSendCursorForRecovery(
            firstFailed, m_nextSequenceNumberToSend,
            m_sendCursorExhausted);
        clearSendRetryBudget(m_retrySequence, m_sendRetryCount);
      }
    }
  }
  if (scheduleOrdinaryReplayRecovery) {
    if (mp_threadPool == nullptr || !mp_threadPool->addWorkload(this)) {
      progress();
    }
  }
  if (!m_enforceUnicast) {
    Lock lock(m_mutex);
    manageSendOptions();
  }
  return success;
}

template <class NetworkDriver>
bool StatelessWriterT<NetworkDriver>::sendData(
    const ReaderProxy &reader, const SequenceNumber_t &sn) {
  Lock lock(m_mutex);
  return sendDataLocked(reader, sn);
}

template <class NetworkDriver>
bool StatelessWriterT<NetworkDriver>::sendDataLocked(
    const ReaderProxy &reader, const SequenceNumber_t &sn) {
  if (m_transmissionHeld) {
    return false;
  }
  if (!readerMayReceiveSequence(reader.durabilityKind, sn,
                                reader.firstRelevantSequence,
                                reader.noRelevantSequence)) {
    return false;
  }
  const CacheChange *change = m_history.getChangeBySN(sn);
  if (change == nullptr || m_transport == nullptr) {
    return false;
  }

  const LocatorIPv4 &locator = reader.remoteLocator;
  if (change->serializerCallback) {
    change->resetSerializer();
    const FragDataSize_t sampleSize = change->sizeToBeSerialized;
    uint32_t fragmentStartNumber = 1;
    uint16_t nominalFragmentSize = 0;
    bool sentFragment = false;
    uint64_t serializedBytes = 0;
    while (true) {
      const auto serialized = change->serializerCallback(
          CacheChange::SerializerOperation::NEXT_FRAGMENT);
      if (serialized.second == 0) {
        break;
      }
      if (nominalFragmentSize == 0) {
        nominalFragmentSize = serialized.second;
      } else if (serialized.second > nominalFragmentSize) {
        return false;
      }
      if (!serializedFragmentPositionValid(
              nominalFragmentSize, fragmentStartNumber, serializedBytes)) {
        return false;
      }
      if (!accountSerializedFragment(
              sampleSize, serialized.second, serializedBytes)) {
        return false;
      }

      PBufWrapper fragment;
      if (!fragment.reserve(serialized.second) ||
          !fragment.append(serialized.first, serialized.second)) {
        return false;
      }
      PacketInfo info;
      info.srcPort = m_packetInfo.srcPort;
      info.destAddr = locator.getIp4Address();
      info.destPort = static_cast<Ip4Port_t>(locator.port);
      if (!MessageFactory::addHeader(
              info.buffer, m_attributes.endpointGuid.prefix) ||
          !MessageFactory::addSubMessageTimeStamp(info.buffer) ||
          !MessageFactory::addSubMessageDataFrag(
              info.buffer, fragment, false, change->sequenceNumber,
              fragmentStartNumber, nominalFragmentSize, sampleSize,
              m_attributes.endpointGuid.entityId,
              reader.remoteReaderGuid.entityId)) {
        return false;
      }
      ++fragmentStartNumber;
      if (!m_transport->sendPacket(info)) {
        return false;
      }
      sentFragment = true;
    }
    return serializedSampleComplete(
        sampleSize, serializedBytes, sentFragment);
  }

  PacketInfo info;
  info.srcPort = m_packetInfo.srcPort;
  info.destAddr = locator.getIp4Address();
  info.destPort = static_cast<Ip4Port_t>(locator.port);
  if (!MessageFactory::addHeader(
          info.buffer, m_attributes.endpointGuid.prefix) ||
      !MessageFactory::addSubMessageTimeStamp(info.buffer) ||
      !MessageFactory::addSubMessageData(
          info.buffer, change->data, false, change->sequenceNumber,
          m_attributes.endpointGuid.entityId,
          reader.remoteReaderGuid.entityId)) {
    return false;
  }
  return m_transport->sendPacket(info);
}

template <class NetworkDriver>
void StatelessWriterT<NetworkDriver>::manageSendOptions() {
  SLW_LOG("Search for Multicast Partners!\n");
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
            SLW_LOG("Found Multicast Partner!\n");
            if (avproxy.remoteReaderGuid.entityId !=
                proxy.remoteReaderGuid.entityId) {
              proxy.unknown_eid = true;
              SLW_LOG("Found different EntityIds, using UNKNOWN_ENTITYID\n");
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
void StatelessWriterT<NetworkDriver>::resetSendOptions() {
  for (auto &proxy : m_proxies) {
    proxy.suppressUnicast = false;
    proxy.useMulticast = false;
    proxy.unknown_eid = false;
  }
  manageSendOptions();
}

template <class NetworkDriver>
void StatelessWriterT<NetworkDriver>::removeReader(const Guid_t &guid) {
  Lock lock(m_mutex);
  auto isElementToRemove = [&](const ReaderProxy &proxy) {
    return proxy.remoteReaderGuid == guid;
  };
  auto thunk = [](void *arg, const ReaderProxy &value) {
    return (*static_cast<decltype(isElementToRemove) *>(arg))(value);
  };

  m_proxies.remove(thunk, &isElementToRemove);
  resetSendOptions();
  releaseUnmatchedVolatileHistoryLocked();
}

template <class NetworkDriver>
void StatelessWriterT<NetworkDriver>::removeReaderOfParticipant(
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
  releaseUnmatchedVolatileHistoryLocked();
}

template <class NetworkDriver>
void StatelessWriterT<NetworkDriver>::
    releaseUnmatchedVolatileHistoryLocked() {
  if (!shouldReleaseHistoryAfterReaderRemoval(
          m_attributes.durabilityKind, m_proxies.getNumElements())) {
    return;
  }
  const SequenceNumber_t lastRetained = m_history.getSeqNumMax();
  if (lastRetained == SEQUENCENUMBER_UNKNOWN) {
    return;
  }
  m_history.removeUntilIncl(lastRetained);
  advanceSendCursorAfterSnapshot(
      m_nextSequenceNumberToSend, m_sendCursorExhausted, lastRetained);
  clearSendRetryBudget(m_retrySequence, m_sendRetryCount);
}

template <typename NetworkDriver>
const CacheChange *StatelessWriterT<NetworkDriver>::newChangeCallback(
    rtps::ChangeKind_t kind, CacheChange::SerializerCallback func,
    FragDataSize_t size) {
  if (isIrrelevant(kind)) {
    return nullptr;
  }
  Lock lock(m_mutex);

  ++m_publishAttemptCount;
  if (!fragmentedPublicationValid(static_cast<bool>(func), size)) {
    ++m_resourceRejectCount;
    return nullptr;
  }
  if (!m_history.canAddChange()) {
    ++m_resourceRejectCount;
    return nullptr;
  }
  const auto capacityDecision =
      evaluateHistoryCapacity(m_history.isFull(), m_keepAll);
  if (capacityDecision == HistoryCapacityDecision::REJECT) {
    ++m_resourceRejectCount;
    return nullptr;
  }
  const uint32_t currentCount = m_history.getChangeCount();
  const uint32_t evictions = plannedKeepLastEvictions(
      currentCount, m_historyDepth, m_history.isFull(), m_keepAll);
  const uint64_t currentBytes = m_history.getTotalDataBytes();
  if (evaluateResourceLimitsAfterEviction(
          currentCount, currentBytes, size, evictions,
          m_history.getOldestDataBytes(evictions),
          m_maxSamples, m_maxBytes) !=
      ResourceLimitDecision::ACCEPT) {
    ++m_resourceRejectCount;
    return nullptr;
  }

  CacheChange prepared;
  prepared.kind = ChangeKind_t::ALIVE;
  prepared.sizeToBeSerialized = size;
  prepared.serializerCallback = std::move(func);
  for (uint32_t index = 0; index < evictions; ++index) {
    m_history.dropOldest();
  }
  const SequenceNumber_t newMin = m_history.getSeqNumMin();
  if (newMin != SEQUENCENUMBER_UNKNOWN &&
      m_nextSequenceNumberToSend < newMin) {
    m_nextSequenceNumberToSend = newMin;
  }

  auto *result = m_history.commitPreparedChange(std::move(prepared));
  if (result != nullptr) {
    ++m_publishAcceptCount;
  } else {
    ++m_allocationFailureCount;
  }
  if (result != nullptr && mp_threadPool != nullptr) {
    if (!mp_threadPool->addWorkload(this)) {
      lock.release();
      progress();
    }
  }

  SLW_LOG("Adding new data as a callback function.\n");
  return result;
}

template <typename NetworkDriver>
const CacheChange *StatelessWriterT<NetworkDriver>::newChange(
    rtps::ChangeKind_t kind, const uint8_t *data, DataSize_t size) {
  if (isIrrelevant(kind)) {
    return nullptr;
  }
  Lock lock(m_mutex);

  ++m_publishAttemptCount;
  if (!inlinePublicationValid(data, size)) {
    ++m_resourceRejectCount;
    return nullptr;
  }
  if (!m_history.canAddChange()) {
    ++m_resourceRejectCount;
    return nullptr;
  }
  const auto capacityDecision =
      evaluateHistoryCapacity(m_history.isFull(), m_keepAll);
  if (capacityDecision == HistoryCapacityDecision::REJECT) {
    ++m_resourceRejectCount;
    return nullptr;
  }
  const uint32_t currentCount = m_history.getChangeCount();
  const uint32_t evictions = plannedKeepLastEvictions(
      currentCount, m_historyDepth, m_history.isFull(), m_keepAll);
  const uint64_t currentBytes = m_history.getTotalDataBytes();
  if (evaluateResourceLimitsAfterEviction(
          currentCount, currentBytes, size, evictions,
          m_history.getOldestDataBytes(evictions),
          m_maxSamples, m_maxBytes) !=
      ResourceLimitDecision::ACCEPT) {
    ++m_resourceRejectCount;
    return nullptr;
  }

  CacheChange prepared;
  prepared.kind = ChangeKind_t::ALIVE;
  if (!prepared.data.reserve(size) || !prepared.data.append(data, size)) {
    ++m_allocationFailureCount;
    return nullptr;
  }
  for (uint32_t index = 0; index < evictions; ++index) {
    m_history.dropOldest();
  }
  const SequenceNumber_t newMin = m_history.getSeqNumMin();
  if (newMin != SEQUENCENUMBER_UNKNOWN &&
      m_nextSequenceNumberToSend < newMin) {
    m_nextSequenceNumberToSend = newMin;
  }

  auto *result = m_history.commitPreparedChange(std::move(prepared));
  if (result != nullptr) {
    ++m_publishAcceptCount;
  } else {
    ++m_allocationFailureCount;
  }
  if (result != nullptr && mp_threadPool != nullptr) {
    if (!mp_threadPool->addWorkload(this)) {
      lock.release();
      progress();
    }
  }

  SLW_LOG("Adding new data.\n");
  return result;
}

template <typename NetworkDriver>
void StatelessWriterT<NetworkDriver>::setAllChangesToUnsent() {
  Lock lock(m_mutex);

  resetSendCursorToHistory(
      m_history.getSeqNumMin(), m_history.getLastUsedSequenceNumber(),
      m_nextSequenceNumberToSend, m_sendCursorExhausted);
  clearSendRetryBudget(m_retrySequence, m_sendRetryCount);

  if (mp_threadPool != nullptr) {
    if (!mp_threadPool->addWorkload(this)) {
      lock.release();
      progress();
    }
  }
}

template <class NetworkDriver>
void StatelessWriterT<NetworkDriver>::setTransmissionHeld(bool held) {
  bool hasWork = false;
  {
    Lock lock(m_mutex);
    const TransmissionHoldTransition transition =
        applyTransmissionHold(held, m_transmissionHeld);
    if (transition == TransmissionHoldTransition::NO_CHANGE) {
      return;
    }
    if (transition == TransmissionHoldTransition::RELEASED) {
      resetSendCursorToHistory(
          m_history.getSeqNumMin(), m_history.getLastUsedSequenceNumber(),
          m_nextSequenceNumberToSend, m_sendCursorExhausted);
      clearSendRetryBudget(m_retrySequence, m_sendRetryCount);
      hasWork = m_history.getChangeCount() != 0;
    }
  }
  if (!held && hasWork &&
      (mp_threadPool == nullptr || !mp_threadPool->addWorkload(this))) {
    progress();
  }
}

template <typename NetworkDriver>
void StatelessWriterT<NetworkDriver>::onNewAckNack(
    const SubmessageAckNack & /*msg*/,
    const GuidPrefix_t & /*sourceGuidPrefix*/) {
  // Too lazy to respond
}

template <typename NetworkDriver>
void StatelessWriterT<NetworkDriver>::sendRawPacket(PacketInfo &info) {
  if (m_transport != nullptr) {
    m_transport->sendPacket(info);
  }
}

template <typename NetworkDriver>
bool StatelessWriterT<NetworkDriver>::isIrrelevant(ChangeKind_t kind) const {
  // Right now we only allow alive changes
  // return kind == ChangeKind_t::INVALID || (m_topicKind == TopicKind_t::NO_KEY
  // && kind != ChangeKind_t::ALIVE);
  return kind != ChangeKind_t::ALIVE;
}

template <typename NetworkDriver>
void StatelessWriterT<NetworkDriver>::progress() {
  while (true) {
  // TODO smarter packaging e.g. by creating MessageStruct and serialize after
  // adjusting values Reusing the pbuf is not possible. See
  // https://www.nongnu.org/lwip/2_1_x/raw_api.html (Zero-Copy MACs)

  bool sent = false;
  bool anyReaderMayReceive = false;
  std::array<ReaderProxy, Config::NUM_READER_PROXIES_PER_WRITER> readers{};
  uint32_t readerCount = 0;
  SequenceNumber_t sequenceToSend = SEQUENCENUMBER_UNKNOWN;
  auto scheduleRetryLocked = [&]() {
    ++m_localSendFailureCount;
    if (mp_threadPool != nullptr &&
        sendSnapshotStillPending(
            m_nextSequenceNumberToSend, m_sendCursorExhausted,
            sequenceToSend) &&
        consumeSendRetryBudget(
            sequenceToSend, m_retrySequence, m_sendRetryCount) &&
        !mp_threadPool->addRetryWorkload(this)) {
      --m_sendRetryCount;
    }
  };
  {
    Lock lock(m_mutex);
    if (m_transmissionHeld) {
      return;
    }
    if (m_sendCursorExhausted) {
      return;
    }
    sequenceToSend = m_nextSequenceNumberToSend;
    for (const auto &proxy : m_proxies) {
      if (readerCount < readers.size()) {
        readers[readerCount++] = proxy;
      }
    }
  }
  if (readerCount == 0) {
    SLW_LOG("No Proxy!\n");
  }

  for (uint32_t readerIndex = 0; readerIndex < readerCount; ++readerIndex) {
    const ReaderProxy &proxy = readers[readerIndex];
    SLW_LOG("Progess.\n");
    const bool readerMayReceive =
        readerMayReceiveSequence(proxy.durabilityKind, sequenceToSend,
                                 proxy.firstRelevantSequence,
                                 proxy.noRelevantSequence);
    anyReaderMayReceive = anyReaderMayReceive || readerMayReceive;
    if (!readerMayReceive) {
      continue;
    }
    // Do nothing, if someone else sends for me... (Multicast)
    if (proxy.useMulticast || !proxy.suppressUnicast || m_enforceUnicast) {

      {
        Lock lock(m_mutex);
        if (m_transmissionHeld) {
          return;
        }
        const CacheChange *next =
            m_history.getChangeBySN(sequenceToSend);
        if (next == nullptr) {
          SLW_LOG("Couldn't get a new CacheChange with SN "
                  "(%i,%i)\n",
                  sequenceToSend.high,
                  sequenceToSend.low);
          return;
        } else {
          SLW_LOG("Sending change with SN (%i,%i)\n",
                  m_nextSequenceNumberToSend.high,
                  m_nextSequenceNumberToSend.low);
        }
        // Set EntityId to UNKNOWN if using multicast, because there might be
        // different ones...
        // TODO: mybe enhance by using UNKNOWN only if ids are really different
        EntityId_t reid;
        if (proxy.useMulticast && !m_enforceUnicast && proxy.unknown_eid) {
          reid = ENTITYID_UNKNOWN;
        } else {
          reid = proxy.remoteReaderGuid.entityId;
        }

        if (next->serializerCallback) {
          next->resetSerializer();
          uint32_t fragment_start_number = 1;
          uint16_t nominal_fragment_size = 0;
          FragDataSize_t sampleSize = next->sizeToBeSerialized;
          CacheChange::SerializedBuf serialized_buf;
          uint64_t serializedBytes = 0;
          bool sentFragment = false;
          while(1) {
            serialized_buf = next->serializerCallback(
                CacheChange::SerializerOperation::NEXT_FRAGMENT);
            if (0 != serialized_buf.second) {
              if (nominal_fragment_size == 0) {
                nominal_fragment_size = serialized_buf.second;
              } else if (serialized_buf.second > nominal_fragment_size) {
                scheduleRetryLocked();
                return;
              }
              if (!serializedFragmentPositionValid(
                      nominal_fragment_size, fragment_start_number,
                      serializedBytes)) {
                scheduleRetryLocked();
                return;
              }
              if (!accountSerializedFragment(
                      sampleSize, serialized_buf.second, serializedBytes)) {
                scheduleRetryLocked();
                return;
              }
              PBufWrapper data;
              PacketInfo info;
              info.srcPort = m_packetInfo.srcPort;

              if (!data.reserve(serialized_buf.second) ||
                  !data.append(serialized_buf.first, serialized_buf.second)) {
                scheduleRetryLocked();
                return;
              }
              if (!MessageFactory::addHeader(
                      info.buffer, m_attributes.endpointGuid.prefix) ||
                  !MessageFactory::addSubMessageTimeStamp(info.buffer) ||
                  !MessageFactory::addSubMessageDataFrag(
                      info.buffer, data, false, next->sequenceNumber,
                      fragment_start_number, nominal_fragment_size,
                      sampleSize, m_attributes.endpointGuid.entityId,
                      reid)) { // TODO
                scheduleRetryLocked();
                return;
              }
              ++fragment_start_number;
              // Just usable for IPv4
              // Decide which locator to be used unicast/multicast
              if (proxy.useMulticast && !m_enforceUnicast) {
                info.destAddr = proxy.remoteMulticastLocator.getIp4Address();
                info.destPort = (Ip4Port_t)proxy.remoteMulticastLocator.port;
              } else {
                info.destAddr = proxy.remoteLocator.getIp4Address();
                info.destPort = (Ip4Port_t)proxy.remoteLocator.port;
              }

              if (!m_transport->sendPacket(info)) {
                scheduleRetryLocked();
                return;
              }
              sent = true;
              sentFragment = true;
            } else {
              break;
            }
          }
          if (!serializedSampleComplete(
                  sampleSize, serializedBytes, sentFragment)) {
            scheduleRetryLocked();
            return;
          }
        } else {
          PacketInfo info;
          info.srcPort = m_packetInfo.srcPort;

          if (!MessageFactory::addHeader(
                  info.buffer, m_attributes.endpointGuid.prefix) ||
              !MessageFactory::addSubMessageTimeStamp(info.buffer) ||
              !MessageFactory::addSubMessageData(
                  info.buffer, next->data, false, next->sequenceNumber,
                  m_attributes.endpointGuid.entityId, reid)) { // TODO
            scheduleRetryLocked();
            return;
          }
          // Just usable for IPv4
          // Decide which locator to be used unicast/multicast
          if (proxy.useMulticast && !m_enforceUnicast) {
            info.destAddr = proxy.remoteMulticastLocator.getIp4Address();
            info.destPort = (Ip4Port_t)proxy.remoteMulticastLocator.port;
          } else {
            info.destAddr = proxy.remoteLocator.getIp4Address();
            info.destPort = (Ip4Port_t)proxy.remoteLocator.port;
          }

          if (!m_transport->sendPacket(info)) {
            scheduleRetryLocked();
            return;
          }
          sent = true;
        }
      }
    }
  }

  // A matched flag can precede a usable proxy. Keep one unicast fallback and
  // retain the history entry until at least one route actually sends it.
  if (!sent) {
    const ReaderProxy *fallbackProxy = nullptr;
    if (readerCount > 0) {
      fallbackProxy = &readers[0];
    }

    const EntityKind_t writerKind =
        m_attributes.endpointGuid.entityId.entityKind;
    const bool userWriter =
        writerKind == EntityKind_t::USER_DEFINED_WRITER_WITH_KEY ||
        writerKind == EntityKind_t::USER_DEFINED_WRITER_WITHOUT_KEY;

    Lock lock(m_mutex);
    if (m_transmissionHeld) {
      return;
    }
    const CacheChange *next =
        m_history.getChangeBySN(sequenceToSend);
    const bool fallbackMayReceive =
        fallbackProxy == nullptr ||
        readerMayReceiveSequence(fallbackProxy->durabilityKind,
                                 sequenceToSend,
                                 fallbackProxy->firstRelevantSequence,
                                 fallbackProxy->noRelevantSequence);
    if (next != nullptr && !next->serializerCallback && fallbackMayReceive &&
        (fallbackProxy != nullptr || !userWriter)) {
      PacketInfo info;
      info.srcPort = m_packetInfo.srcPort;
      EntityId_t remoteReaderId = ENTITYID_UNKNOWN;
      if (fallbackProxy != nullptr) {
        info.destAddr = fallbackProxy->remoteLocator.getIp4Address();
        info.destPort = fallbackProxy->remoteLocator.port;
        remoteReaderId = fallbackProxy->remoteReaderGuid.entityId;
      } else {
        IP4_ADDR(&info.destAddr, Config::REMOTE_PARTICIPANT_IP[0],
                 Config::REMOTE_PARTICIPANT_IP[1],
                 Config::REMOTE_PARTICIPANT_IP[2],
                 Config::REMOTE_PARTICIPANT_IP[3]);
        info.destPort = Config::REMOTE_USER_DATA_PORT;
      }
      if (!MessageFactory::addHeader(
              info.buffer, m_attributes.endpointGuid.prefix) ||
          !MessageFactory::addSubMessageTimeStamp(info.buffer) ||
          !MessageFactory::addSubMessageData(
              info.buffer, next->data, false, next->sequenceNumber,
              m_attributes.endpointGuid.entityId, remoteReaderId)) {
        scheduleRetryLocked();
        return;
      }
      if (!m_transport->sendPacket(info)) {
        scheduleRetryLocked();
        return;
      }
      sent = true;
    }
  }

  bool scheduleNext = false;
  {
    Lock lock(m_mutex);
    const bool skippedByEveryReader =
        allReadersSkipSequence(readerCount, anyReaderMayReceive);
    const bool releaseWithoutReaders =
        shouldReleaseUnmatchedBestEffortHistory(
            m_attributes.durabilityKind, readerCount,
            m_proxies.getNumElements(),
            m_history.getChangeBySN(sequenceToSend) != nullptr);
    if (sent || skippedByEveryReader || releaseWithoutReaders) {
      clearSendRetryBudget(m_retrySequence, m_sendRetryCount);
      advanceSendCursorAfterSnapshot(m_nextSequenceNumberToSend,
                                     m_sendCursorExhausted, sequenceToSend);
      if (releaseWithoutReaders ||
          shouldReleaseHistoryAfterBestEffortSend(
              m_attributes.durabilityKind, sent || skippedByEveryReader)) {
        m_history.removeUntilIncl(sequenceToSend);
      }
      scheduleNext = sendCursorTargetsRetainedHistory(
          m_nextSequenceNumberToSend, m_sendCursorExhausted,
          m_history.getSeqNumMin(), m_history.getSeqNumMax());
    } else if (anyReaderMayReceive) {
      scheduleRetryLocked();
    }
  }
  if (scheduleNext &&
      (mp_threadPool == nullptr || !mp_threadPool->addWorkload(this))) {
    continue;
  }
  return;
  }
}
