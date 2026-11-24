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
  m_running.store(false, std::memory_order_release);
  while (m_thread_running.load(std::memory_order_acquire)) {
    sys_msleep(10); // lwIP has no portable thread join API.
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
#ifdef MROS2_TEST_DISABLE_BACKGROUND_THREADS
  // Deterministic production-path integration tests exercise directed
  // HEARTBEAT/GAP behavior separately from the dedicated periodic-thread test.
    m_running.store(false, std::memory_order_release);
    m_thread_running.store(false, std::memory_order_release);
    m_heartbeatThread = nullptr;
    m_is_initialized_ = true;
    return true;
#endif
  // Publish the active state before creating the task. Otherwise destruction
  // can observe "not running" before the new task reaches its entry point.
  m_running.store(true, std::memory_order_release);
  m_thread_running.store(true, std::memory_order_release);
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
#ifdef OS_IS_FREERTOS
  if (m_heartbeatThread == nullptr) {
    m_thread_running.store(false, std::memory_order_release);
    return false;
  }
#endif

  m_is_initialized_ = true;
  return true;
}

template <class NetworkDriver>
bool StatefulWriterT<NetworkDriver>::addNewMatchedReader(
    const ReaderProxy &newProxy) {
  static_assert(fragmentedTransientLocalReplaySupported(),
                "Transient-local replay capability declaration drifted");
#if SFW_VERBOSE && RTPS_GLOBAL_VERBOSE
  SFW_LOG("New reader added with id: ");
  printGuid(newProxy.remoteReaderGuid);
#endif

  bool success = false;
  bool scheduleOrdinaryReplayRecovery = false;
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
      // Linearize matching, HEARTBEAT range, and bounded historical replay
      // against publication, Lifespan purge, and Keep Last eviction.
      purgeExpiredChangesLocked(rtps::getCurrentTimeMs());
      const SequenceNumber_t historyMin = m_history.getSeqNumMin();
      const SequenceNumber_t historyMax = m_history.getSeqNumMax();
      SequenceNumber_t firstSN;
      SequenceNumber_t lastSN;
      if (heartbeatSequenceRange(
              historyMin, historyMax, m_history.getLastUsedSequenceNumber(),
              firstSN, lastSN)) {
        if (readerUsesReliabilityProtocol(matchedProxy.reliabilityKind)) {
          const Count_t heartbeatCount = m_hbCount;
          incrementCount(m_hbCount);
          PacketInfo hbInfo;
          hbInfo.srcPort = m_packetInfo.srcPort;
          hbInfo.destAddr = matchedProxy.remoteLocator.getIp4Address();
          hbInfo.destPort = (Ip4Port_t)matchedProxy.remoteLocator.port;
          const bool constructed =
              MessageFactory::addHeader(
                  hbInfo.buffer, m_attributes.endpointGuid.prefix) &&
              MessageFactory::addHeartbeat(
                  hbInfo.buffer, m_attributes.endpointGuid.entityId,
                  matchedProxy.remoteReaderGuid.entityId, firstSN, lastSN,
                  heartbeatCount);
          if (!constructed || m_transport == nullptr ||
              !m_transport->sendPacket(hbInfo)) {
            ++m_controlSendFailureCount;
          }
        }
        if (historyMin != SEQUENCENUMBER_UNKNOWN &&
            historyMax != SEQUENCENUMBER_UNKNOWN) {
          SequenceNumber_t sn = firstSN;
          SequenceNumber_t firstFailed = SEQUENCENUMBER_UNKNOWN;
          while (sn <= lastSN) {
            bool replaySent = false;
            for (uint8_t attempt = 0;
                 attempt <= SEND_RETRY_LIMIT && !replaySent; ++attempt) {
              replaySent = sendDataLocked(matchedProxy, sn);
            }
            if (!replaySent &&
                firstFailed == SEQUENCENUMBER_UNKNOWN) {
              firstFailed = sn;
              break;
            }
            if (sn == lastSN) {
              break;
            }
            ++sn;
          }
          if (firstFailed == SEQUENCENUMBER_UNKNOWN &&
              mayAdvanceGlobalCursorAfterDirectedReplay(
                  hadMatchedReaders)) {
            advanceSendCursorAfterSnapshot(
                m_nextSequenceNumberToSend, m_sendCursorExhausted, lastSN);
          }
          scheduleOrdinaryReplayRecovery =
              shouldScheduleOrdinaryReplayRecovery(
                  firstFailed == SEQUENCENUMBER_UNKNOWN,
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
    } else if (
        success &&
        !readerRequestsHistoricalData(matchedProxy.durabilityKind) &&
        mayAdvanceGlobalCursorForVolatileMatch(hadMatchedReaders) &&
        matchedProxy.firstRelevantSequence != SEQUENCENUMBER_UNKNOWN &&
        m_nextSequenceNumberToSend < matchedProxy.firstRelevantSequence) {
      m_nextSequenceNumberToSend = matchedProxy.firstRelevantSequence;
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
  {
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
  releaseAcknowledgedChanges();
}

template <class NetworkDriver>
void StatefulWriterT<NetworkDriver>::removeReaderOfParticipant(
    const GuidPrefix_t &guidPrefix) {
  {
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
  releaseAcknowledgedChanges();
}

template <class NetworkDriver>
const rtps::CacheChange *StatefulWriterT<NetworkDriver>::newChangeCallback(
    ChangeKind_t kind, CacheChange::SerializerCallback func,
    FragDataSize_t size){
  if (isIrrelevant(kind)) {
    return nullptr;
  }

  Lock lock{m_mutex};
  purgeExpiredChangesLocked(rtps::getCurrentTimeMs());
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
    m_resourceRejectCount++;
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
    uint32_t now = rtps::getCurrentTimeMs();
    const_cast<CacheChange*>(result)->timestampMs = now;
    m_lastPublishTimeMs = now;
    m_nextDeadlineTimeMs = m_deadlineMs > 0 ? now + m_deadlineMs : 0;
    m_hasDeadlineBaseline = m_deadlineMs > 0;
  }

  else {
    ++m_allocationFailureCount;
  }

  if (result != nullptr && mp_threadPool != nullptr) {
    if (!mp_threadPool->addWorkload(this)) {
      lock.release();
      progress();
    }
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
  purgeExpiredChangesLocked(rtps::getCurrentTimeMs());
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
    m_resourceRejectCount++;
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

  // Set timestamp for Lifespan QoS and update Deadline timer
  if (result != nullptr) {
    ++m_publishAcceptCount;
    uint32_t now = rtps::getCurrentTimeMs();
    const_cast<CacheChange*>(result)->timestampMs = now;
    m_lastPublishTimeMs = now;
    m_nextDeadlineTimeMs = m_deadlineMs > 0 ? now + m_deadlineMs : 0;
    m_hasDeadlineBaseline = m_deadlineMs > 0;
  }

  else {
    ++m_allocationFailureCount;
  }

  if (result != nullptr && mp_threadPool != nullptr) {
    if (!mp_threadPool->addWorkload(this)) {
      lock.release();
      progress();
    }
  }

  SFW_LOG("Adding new data.\n");

  return result;
}

template <class NetworkDriver> void StatefulWriterT<NetworkDriver>::progress() {
  while (true) {
  std::array<ReaderProxy, Config::NUM_READER_PROXIES_PER_WRITER> readers{};
  uint32_t readerCount = 0;
  SequenceNumber_t sequenceToSend = SEQUENCENUMBER_UNKNOWN;
  {
    Lock lock(m_mutex);
    if (m_transmissionHeld) {
      return;
    }
    if (m_sendCursorExhausted) {
      return;
    }
    purgeExpiredChangesLocked(rtps::getCurrentTimeMs());
    const SequenceNumber_t firstSN = m_history.getSeqNumMin();
    if (firstSN == SEQUENCENUMBER_UNKNOWN) {
      return;
    }
    if (m_nextSequenceNumberToSend < firstSN) {
      m_nextSequenceNumberToSend = firstSN;
    }
    sequenceToSend = m_nextSequenceNumberToSend;
    for (const auto &proxy : m_proxies) {
      if (readerCount < readers.size()) {
        readers[readerCount++] = proxy;
      }
    }
  }

  bool sent = false;
  bool anyReaderMayReceive = false;
  bool hasBestEffortReader = false;
  bool allEligibleReadersSent = true;
  if (readerCount > 0) {
    // Normal path: send to all matched readers.
    for (uint32_t index = 0; index < readerCount; ++index) {
      const ReaderProxy &proxy = readers[index];
      const bool bestEffort =
          !readerUsesReliabilityProtocol(proxy.reliabilityKind);
      hasBestEffortReader = hasBestEffortReader || bestEffort;
      if (!readerMayReceiveSequence(
              proxy.durabilityKind, sequenceToSend,
              proxy.firstRelevantSequence, proxy.noRelevantSequence)) {
        continue;
      }
      anyReaderMayReceive = true;
      bool success;
      if (!m_enforceUnicast) {
        success = sendDataWRMulticast(proxy, sequenceToSend);
      } else {
        success = sendData(proxy, sequenceToSend);
      }

      if (!success) {
        allEligibleReadersSent = false;
        continue;
      }
      sent = true;
    }
  } else {
    // The endpoint match flag can become visible before the SEDP reader proxy.
    // Retain one configured unicast route so the first queued sample is not
    // lost while discovery finishes.
    ReaderProxy tempProxy;
    tempProxy.remoteReaderGuid = Guid_t{GUIDPREFIX_UNKNOWN, ENTITYID_UNKNOWN};
    tempProxy.remoteLocator.kind = LocatorKind_t::LOCATOR_KIND_UDPv4;
    tempProxy.remoteLocator.address = {Config::REMOTE_PARTICIPANT_IP[0],
                                       Config::REMOTE_PARTICIPANT_IP[1],
                                       Config::REMOTE_PARTICIPANT_IP[2],
                                       Config::REMOTE_PARTICIPANT_IP[3]};
    tempProxy.remoteLocator.port = Config::REMOTE_USER_DATA_PORT;
    tempProxy.remoteMulticastLocator = LocatorIPv4{};
    tempProxy.useMulticast = false;
    tempProxy.suppressUnicast = false;
    sent = sendDataWRMulticast(tempProxy, sequenceToSend);
  }

  const bool skippedByEveryReader =
      allReadersSkipSequence(readerCount, anyReaderMayReceive);
  const bool snapshotComplete =
      ordinarySendSnapshotComplete(sent, allEligibleReadersSent);
  bool scheduleNext = false;
  if (snapshotComplete || skippedByEveryReader) {
    {
      Lock lock(m_mutex);
      clearSendRetryBudget(m_retrySequence, m_sendRetryCount);
      if (snapshotComplete && hasBestEffortReader &&
          (m_lastSequenceNumberSent == SEQUENCENUMBER_UNKNOWN ||
           m_lastSequenceNumberSent < sequenceToSend)) {
        m_lastSequenceNumberSent = sequenceToSend;
      }
      advanceSendCursorAfterSnapshot(m_nextSequenceNumberToSend,
                                     m_sendCursorExhausted, sequenceToSend);
      if (shouldReleaseUnmatchedReliableFallbackHistory(
              m_attributes.durabilityKind, readerCount,
              m_proxies.getNumElements(),
              m_history.getChangeBySN(sequenceToSend) != nullptr,
              snapshotComplete)) {
        m_history.removeUntilIncl(sequenceToSend);
      }
      scheduleNext = sendCursorTargetsRetainedHistory(
          m_nextSequenceNumberToSend, m_sendCursorExhausted,
          m_history.getSeqNumMin(), m_history.getSeqNumMax());
    }
    releaseAcknowledgedChanges();
    if (scheduleNext &&
        (mp_threadPool == nullptr || !mp_threadPool->addWorkload(this))) {
      continue;
    }
  } else if (readerCount == 0 || anyReaderMayReceive) {
    bool scheduleAfterEviction = false;
    {
      Lock lock(m_mutex);
      if (m_transmissionHeld) {
        return;
      }
      if (!sendSnapshotStillPending(
              m_nextSequenceNumberToSend, m_sendCursorExhausted,
              sequenceToSend)) {
        clearSendRetryBudget(m_retrySequence, m_sendRetryCount);
        scheduleAfterEviction = sendCursorTargetsRetainedHistory(
            m_nextSequenceNumberToSend, m_sendCursorExhausted,
            m_history.getSeqNumMin(), m_history.getSeqNumMax());
      } else {
        ++m_localSendFailureCount;
        if (mp_threadPool != nullptr &&
            consumeSendRetryBudget(
                sequenceToSend, m_retrySequence, m_sendRetryCount) &&
            !mp_threadPool->addRetryWorkload(this)) {
          --m_sendRetryCount;
        }
      }
    }
    if (scheduleAfterEviction) {
      if (mp_threadPool == nullptr || !mp_threadPool->addWorkload(this)) {
        continue;
      }
    }
  }
  return;
  }
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

  purgeExpiredChangesLocked(rtps::getCurrentTimeMs());
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
void StatefulWriterT<NetworkDriver>::setTransmissionHeld(bool held) {
  bool hasWork = false;
  {
    Lock lock(m_mutex);
    const TransmissionHoldTransition transition =
        applyTransmissionHold(held, m_transmissionHeld);
    if (transition == TransmissionHoldTransition::NO_CHANGE) {
      return;
    }
    if (transition == TransmissionHoldTransition::RELEASED) {
      purgeExpiredChangesLocked(rtps::getCurrentTimeMs());
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

template <class NetworkDriver>
void StatefulWriterT<NetworkDriver>::onNewAckNack(
    const SubmessageAckNack &msg, const GuidPrefix_t &sourceGuidPrefix) {
  ReaderProxy reader;
  bool found = false;
  const bool heartbeatSolicited =
      msg.readerSNState.numBits == 0 &&
      (msg.header.flags & FLAG_FINAL) == 0;
  {
    Lock lock(m_mutex);
    ++m_ackNackReceiveCount;
    for (auto &proxy : m_proxies) {
      if (proxy.remoteReaderGuid.prefix == sourceGuidPrefix &&
          proxy.remoteReaderGuid.entityId == msg.readerId) {
        if (!readerUsesReliabilityProtocol(proxy.reliabilityKind)) {
          ++m_ackNackBestEffortDropCount;
          SFW_LOG("Ignoring ACKNACK from BEST_EFFORT reader.\n");
          return;
        }
        if (!countIsAdmissible(proxy.hasAckNackCount, msg.count,
                               proxy.ackNackCount)) {
          ++m_ackNackStaleDropCount;
          SFW_LOG("Count too small. Dropping acknack.\n");
          return;
        }
        proxy.ackNackCount = msg.count;
        proxy.hasAckNackCount = true;
        proxy.ackNackSet = msg.readerSNState;
        advanceCumulativeAckBounded(
            msg.readerSNState, m_history.getLastUsedSequenceNumber(),
            proxy.hasAcknowledgedThrough,
            proxy.acknowledgedThrough);
        reader = proxy;
        ++m_ackNackAcceptCount;
        found = true;
        break;
      }
    }
  }

  if (!found) {
    {
      Lock lock(m_mutex);
      ++m_ackNackUnknownReaderDropCount;
    }
#if SFW_VERBOSE && RTPS_GLOBAL_VERBOSE
    SFW_LOG("No proxy found with id: ");
    printEntityId(msg.readerId);
    SFW_LOG(" Dropping acknack.\n");
#endif
    return;
  }

  // Send missing packets
  SequenceNumber_t nextSN = msg.readerSNState.base;

  if (nextSN.low == 0 && nextSN.high == 0) {
    SFW_LOG("Received preemptive acknack. Ignored.\n");
  } else {
    SFW_LOG("Received non-preemptive acknack.\n");
  }

  uint32_t attemptedResponses = 0;
  for (uint32_t i = 0; i < msg.readerSNState.numBits; ++i) {
    if (ackNackRequestedSequence(msg.readerSNState, i, nextSN)) {

      SFW_LOG("Send Packet on acknack.\n");
      SequenceNumber_t historyMin;
      SequenceNumber_t historyMax;
      SequenceNumber_t lastWritten;
      {
        Lock lock(m_mutex);
        purgeExpiredChangesLocked(rtps::getCurrentTimeMs());
        historyMin = m_history.getSeqNumMin();
        historyMax = m_history.getSeqNumMax();
        lastWritten = m_history.getLastUsedSequenceNumber();
      }
      const RequestedSequenceAvailability availability =
          classifyRequestedSequenceForReader(
              nextSN, historyMin, historyMax, lastWritten,
              reader.firstRelevantSequence, reader.noRelevantSequence);
      const bool responseEligible =
          availability == RequestedSequenceAvailability::AVAILABLE ||
          availability ==
              RequestedSequenceAvailability::NO_LONGER_AVAILABLE;
      if (responseEligible &&
          !tryReserveAckNackSequenceResponse(attemptedResponses)) {
        Lock lock(m_mutex);
        ++m_ackNackDeferredResponseCount;
        continue;
      }
      if (availability == RequestedSequenceAvailability::AVAILABLE) {
        if (sendData(reader, nextSN)) {
          Lock lock(m_mutex);
          ++m_ackNackDataResponseCount;
        } else {
          // History may have advanced between classification and send.
          RequestedSequenceAvailability retryAvailability;
          bool held = false;
          {
            Lock lock(m_mutex);
            held = m_transmissionHeld;
            retryAvailability = classifyRequestedSequenceForReader(
                nextSN, m_history.getSeqNumMin(), m_history.getSeqNumMax(),
                m_history.getLastUsedSequenceNumber(),
                reader.firstRelevantSequence, reader.noRelevantSequence);
            if (shouldCountRepairSendFailure(held, retryAvailability)) {
              ++m_localSendFailureCount;
            }
          }
          if (held) {
            break;
          }
          if (retryAvailability ==
              RequestedSequenceAvailability::NO_LONGER_AVAILABLE) {
            if (sendGap(reader, nextSN)) {
              Lock lock(m_mutex);
              ++m_ackNackGapResponseCount;
            }
          }
        }
      } else if (availability ==
                 RequestedSequenceAvailability::NO_LONGER_AVAILABLE) {
        if (sendGap(reader, nextSN)) {
          Lock lock(m_mutex);
          ++m_ackNackGapResponseCount;
        }
      }
    }
  }
  releaseAcknowledgedChanges();
  if (heartbeatSolicited) {
    // A non-final ACKNACK with an empty bitmap requests current Writer state,
    // not a DATA/GAP for an unannounced future sequence. sendHeartBeat()
    // retains its per-Reader acknowledgement filter, so a caught-up idle
    // Reader does not re-enable permanent periodic control traffic.
    sendHeartBeat();
  }
}

template <class NetworkDriver>
bool StatefulWriterT<NetworkDriver>::sendGap(
    const ReaderProxy &reader, const SequenceNumber_t &sn) {
  Lock lock(m_mutex);
  if (m_transmissionHeld) {
    return false;
  }
  PacketInfo info;
  info.srcPort = m_packetInfo.srcPort;
  info.destAddr = reader.remoteLocator.getIp4Address();
  info.destPort = static_cast<Ip4Port_t>(reader.remoteLocator.port);
  if (!MessageFactory::addHeader(
          info.buffer, m_attributes.endpointGuid.prefix) ||
      !MessageFactory::addGap(
          info.buffer, m_attributes.endpointGuid.entityId,
          reader.remoteReaderGuid.entityId, sn)) {
    ++m_controlSendFailureCount;
    return false;
  }
  if (m_transport == nullptr || !m_transport->sendPacket(info)) {
    ++m_controlSendFailureCount;
    return false;
  }
  return true;
}

template <class NetworkDriver>
bool StatefulWriterT<NetworkDriver>::sendData(
    const ReaderProxy &reader, const SequenceNumber_t &snMissing) {

  Lock lock(m_mutex);
  return sendDataLocked(reader, snMissing);
}

template <class NetworkDriver>
bool StatefulWriterT<NetworkDriver>::sendDataLocked(
    const ReaderProxy &reader, const SequenceNumber_t &snMissing) {
  if (m_transmissionHeld) {
    return false;
  }
  if (reader.firstRelevantSequence != SEQUENCENUMBER_UNKNOWN &&
      snMissing < reader.firstRelevantSequence) {
    return false;
  }
  if (reader.noRelevantSequence) {
    return false;
  }
  purgeExpiredChangesLocked(rtps::getCurrentTimeMs());
  const CacheChange *next = m_history.getChangeBySN(snMissing);
  if (next == nullptr) {
    SFW_LOG("Couldn't get a CacheChange with SN (%i,%u)\n", snMissing.high,
            snMissing.low);
    return false;
  }

  const LocatorIPv4 &locator = reader.remoteLocator;

  if (next->serializerCallback) {
    next->resetSerializer();
    // Fragmented path: call serializer to get data chunks, send as DATA_FRAG
    FragDataSize_t sampleSize = next->sizeToBeSerialized;
    CacheChange::SerializedBuf serialized_buf;
    uint32_t fragment_start_number = 1;
    uint16_t nominal_fragment_size = 0;
    bool sentFragment = false;
    uint64_t serializedBytes = 0;
    while (1) {
      serialized_buf = next->serializerCallback(
          CacheChange::SerializerOperation::NEXT_FRAGMENT);
      if (0 == serialized_buf.second) break;
      if (nominal_fragment_size == 0) {
        nominal_fragment_size = serialized_buf.second;
      } else if (serialized_buf.second > nominal_fragment_size) {
        return false;
      }
      if (!serializedFragmentPositionValid(
              nominal_fragment_size, fragment_start_number,
              serializedBytes)) {
        return false;
      }
      if (!accountSerializedFragment(
              sampleSize, serialized_buf.second, serializedBytes)) {
        return false;
      }

      PBufWrapper fragData;
      if (!fragData.reserve(serialized_buf.second) ||
          !fragData.append(serialized_buf.first, serialized_buf.second)) {
        return false;
      }

      PacketInfo info;
      info.srcPort = m_packetInfo.srcPort;
      info.destAddr = locator.getIp4Address();
      info.destPort = (Ip4Port_t)locator.port;
      if (!MessageFactory::addHeader(
              info.buffer, m_attributes.endpointGuid.prefix) ||
          !MessageFactory::addSubMessageTimeStamp(info.buffer) ||
          !MessageFactory::addSubMessageDataFrag(
              info.buffer, fragData, false, next->sequenceNumber,
              fragment_start_number, nominal_fragment_size, sampleSize,
              m_attributes.endpointGuid.entityId,
              reader.remoteReaderGuid.entityId)) {
        return false;
      }
      ++fragment_start_number;
      if (!m_transport->sendPacket(info)) {
        return false;
      }
      sentFragment = true;
    }
    if (!serializedSampleComplete(
            sampleSize, serializedBytes, sentFragment)) {
      return false;
    }
  } else {
    // Normal path: single DATA submessage
    PacketInfo info;
    info.srcPort = m_packetInfo.srcPort;
    info.destAddr = locator.getIp4Address();
    info.destPort = (Ip4Port_t)locator.port;
    if (!MessageFactory::addHeader(
            info.buffer, m_attributes.endpointGuid.prefix) ||
        !MessageFactory::addSubMessageTimeStamp(info.buffer) ||
        !MessageFactory::addSubMessageData(
            info.buffer, next->data, false, next->sequenceNumber,
            m_attributes.endpointGuid.entityId,
            reader.remoteReaderGuid.entityId)) {
      return false;
    }
    if (!m_transport->sendPacket(info)) {
      return false;
    }
  }
  return true;
}

template <class NetworkDriver>
bool StatefulWriterT<NetworkDriver>::sendDataWRMulticast(
    const ReaderProxy &reader, const SequenceNumber_t &snMissing) {

  if (!readerMayReceiveSequence(reader.durabilityKind, snMissing,
                                reader.firstRelevantSequence,
                                reader.noRelevantSequence)) {
    return false;
  }
  if (reader.useMulticast || reader.suppressUnicast == false) {
    PacketInfo info;
    info.srcPort = m_packetInfo.srcPort;

    const bool prefixBuilt =
        MessageFactory::addHeader(
            info.buffer, m_attributes.endpointGuid.prefix) &&
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
      if (m_transmissionHeld) {
        return false;
      }
      purgeExpiredChangesLocked(rtps::getCurrentTimeMs());
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

      if (next->serializerCallback) {
        next->resetSerializer();
        const FragDataSize_t sampleSize = next->sizeToBeSerialized;
        uint32_t fragmentStartNumber = 1;
        uint16_t nominalFragmentSize = 0;
        bool sentFragment = false;
        uint64_t serializedBytes = 0;
        while (true) {
          const auto serialized = next->serializerCallback(
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
                  nominalFragmentSize, fragmentStartNumber,
                  serializedBytes)) {
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

          PacketInfo fragmentInfo;
          fragmentInfo.srcPort = m_packetInfo.srcPort;
          fragmentInfo.destAddr = info.destAddr;
          fragmentInfo.destPort = info.destPort;
          if (!MessageFactory::addHeader(
                  fragmentInfo.buffer, m_attributes.endpointGuid.prefix) ||
              !MessageFactory::addSubMessageTimeStamp(fragmentInfo.buffer) ||
              !MessageFactory::addSubMessageDataFrag(
                  fragmentInfo.buffer, fragment, false,
                  next->sequenceNumber, fragmentStartNumber,
                  nominalFragmentSize, sampleSize,
                  m_attributes.endpointGuid.entityId, reid)) {
            return false;
          }
          ++fragmentStartNumber;
          if (!m_transport->sendPacket(fragmentInfo)) {
            return false;
          }
          sentFragment = true;
        }
        return serializedSampleComplete(
            sampleSize, serializedBytes, sentFragment);
      }

      if (!prefixBuilt ||
          !MessageFactory::addSubMessageData(
              info.buffer, next->data, false, next->sequenceNumber,
              m_attributes.endpointGuid.entityId, reid)) {
        return false;
      }
      return m_transport->sendPacket(info);
    }
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
  while (m_running.load(std::memory_order_acquire)) {
    sendHeartBeat();
    uint32_t remaining = Config::SF_WRITER_HB_PERIOD_MS;
    while (remaining != 0 &&
           m_running.load(std::memory_order_acquire)) {
      const uint32_t slice = remaining < 10 ? remaining : 10;
#ifdef OS_IS_FREERTOS
      const TickType_t delayTicks = pdMS_TO_TICKS(slice);
      vTaskDelay(delayTicks == 0 ? 1 : delayTicks);
#else
      sys_msleep(slice);
#endif
      remaining -= slice;
    }
  }
  m_thread_running.store(false, std::memory_order_release);
}

template <class NetworkDriver>
void StatefulWriterT<NetworkDriver>::sendHeartBeat() {
  std::array<ReaderProxy, Config::NUM_READER_PROXIES_PER_WRITER> readers{};
  uint32_t readerCount = 0;
  Count_t heartbeatCount;
  {
    Lock lock(m_mutex);
    // Lifespan is a History-retention rule, not a transmission action.
    // Periodic housekeeping must continue while held and with no Readers.
    purgeExpiredChangesLocked(rtps::getCurrentTimeMs());
    if (m_transmissionHeld) {
      return;
    }
    const SequenceNumber_t lastWritten =
        m_history.getLastUsedSequenceNumber();
    for (const auto &proxy : m_proxies) {
      if (readerUsesReliabilityProtocol(proxy.reliabilityKind) &&
          readerNeedsPeriodicHeartbeat(
              lastWritten, proxy.firstRelevantSequence,
              proxy.noRelevantSequence, proxy.hasAcknowledgedThrough,
              proxy.acknowledgedThrough) &&
          readerCount < readers.size()) {
        readers[readerCount++] = proxy;
      }
    }
    if (readerCount == 0) {
      return;
    }
    heartbeatCount = m_hbCount;
    incrementCount(m_hbCount);
  }

  for (uint32_t index = 0; index < readerCount; ++index) {
    const ReaderProxy &proxy = readers[index];
    PacketInfo info;
    info.srcPort = m_packetInfo.srcPort;

    SequenceNumber_t firstSN;
    SequenceNumber_t lastSN;
    bool hasHeartbeatRange = false;
    Lock lock(m_mutex);
    if (m_transmissionHeld) {
      return;
    }
    purgeExpiredChangesLocked(rtps::getCurrentTimeMs());
    hasHeartbeatRange = heartbeatSequenceRangeForReader(
        m_history.getSeqNumMin(), m_history.getSeqNumMax(),
        m_history.getLastUsedSequenceNumber(), proxy.firstRelevantSequence,
        firstSN, lastSN, proxy.noRelevantSequence);
    if (!hasHeartbeatRange) {
      if (strlen(&this->m_attributes.typeName[0]) != 0) {
        SFW_LOG("Skipping heartbeat. Invalid sequence range.\n");
      }
      continue;
    }

    if (!MessageFactory::addHeader(
            info.buffer, m_attributes.endpointGuid.prefix) ||
        !MessageFactory::addHeartbeat(
            info.buffer, m_attributes.endpointGuid.entityId,
            proxy.remoteReaderGuid.entityId, firstSN, lastSN,
            heartbeatCount)) {
      ++m_controlSendFailureCount;
      continue;
    }

    info.destAddr = proxy.remoteLocator.getIp4Address();
    info.destPort = proxy.remoteLocator.port;
    if (m_transport == nullptr || !m_transport->sendPacket(info)) {
      ++m_controlSendFailureCount;
    }
  }
}

template <class NetworkDriver>
void StatefulWriterT<NetworkDriver>::setDeadlineMissedCallback(
    void (*cb)(void *), void *arg) {
  Lock lock{m_mutex};
  m_deadlineMissedCb = cb;
  m_deadlineMissedArg = arg;
}

template <class NetworkDriver>
bool StatefulWriterT<NetworkDriver>::checkDeadlineMissed() {
  void (*callback)(void *) = nullptr;
  void *callbackArg = nullptr;
  {
    Lock lock{m_mutex};
    if (m_deadlineMs == 0 || !m_hasDeadlineBaseline) return false;
    const uint32_t missed = deadlineMissedPeriods(
        rtps::getCurrentTimeMs(), m_nextDeadlineTimeMs, m_deadlineMs);
    if (missed == 0) return false;

    m_deadlineMissedCount += missed;
    m_nextDeadlineTimeMs += missed * m_deadlineMs;
    callback = m_deadlineMissedCb;
    callbackArg = m_deadlineMissedArg;
  }
  if (callback != nullptr) {
    callback(callbackArg);
  }
  return true;
}

template <class NetworkDriver>
void StatefulWriterT<NetworkDriver>::purgeExpiredChangesLocked(uint32_t nowMs) {
  if (m_lifespanMs == 0) {
    return;
  }

  while (true) {
    const SequenceNumber_t firstSN = m_history.getSeqNumMin();
    if (firstSN == SEQUENCENUMBER_UNKNOWN) {
      return;
    }

    const CacheChange *change = m_history.getChangeBySN(firstSN);
    if (change == nullptr ||
        !lifespanExpired(change->timestampMs, m_lifespanMs, nowMs)) {
      return;
    }

    m_history.dropOldest();
    ++m_lifespanDropCount;
    if (m_nextSequenceNumberToSend <= firstSN) {
      advanceSendCursorAfterSnapshot(m_nextSequenceNumberToSend,
                                     m_sendCursorExhausted, firstSN);
    }
  }
}

template <class NetworkDriver>
void StatefulWriterT<NetworkDriver>::
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

template <class NetworkDriver>
void StatefulWriterT<NetworkDriver>::releaseAcknowledgedChanges() {
  if (m_attributes.durabilityKind != DurabilityKind_t::VOLATILE) {
    return;
  }

  Lock lock{m_mutex};
  if (m_proxies.isEmpty()) {
    return;
  }
  SequenceNumber_t acknowledged = SEQUENCENUMBER_UNKNOWN;
  if (!reliableReaderReleaseBoundary(
          m_proxies, m_lastSequenceNumberSent, acknowledged)) {
    return;
  }

  m_history.removeUntilIncl(acknowledged);
  // ACK processing can race the ordinary-send completion that normally moves
  // this cursor. Make release self-contained even when the removal empties
  // History, while preserving any cursor already advanced farther.
  advanceSendCursorAfterSnapshot(
      m_nextSequenceNumberToSend, m_sendCursorExhausted, acknowledged);
}

#undef SFW_VERBOSE
