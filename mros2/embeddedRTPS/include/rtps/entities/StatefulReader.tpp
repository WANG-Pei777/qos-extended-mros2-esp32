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
#include "lwip/tcpip.h"
#include "rtps/entities/StatefulReader.h"
#include "rtps/messages/MessageFactory.h"
#include "rtps/utils/Lock.h"
#include "rtps/utils/sysFunctions.h"

#if SFR_VERBOSE && RTPS_GLOBAL_VERBOSE
#include "rtps/utils/printutils.h"
#define SFR_LOG(...)                                                           \
  if (true) {                                                                  \
    printf("[StatefulReader %s] ", &m_attributes.topicName[0]);                \
    printf(__VA_ARGS__);                                                       \
    printf("\n");                                                              \
  }
#else
#define SFR_LOG(...) //
#endif

using rtps::StatefulReaderT;

template <class NetworkDriver>
StatefulReaderT<NetworkDriver>::~StatefulReaderT() {
  //  if(sys_mutex_valid(&m_mutex)){ // Getting invalid pointer error, there
  //  seems sth strange
  //    sys_mutex_free(&m_mutex);
  //  }
}

template <class NetworkDriver>
void StatefulReaderT<NetworkDriver>::init(const TopicData &attributes,
                                          NetworkDriver &driver) {
  if (sys_mutex_new(&m_mutex) != ERR_OK) {

    SFR_LOG("StatefulReader: Failed to create mutex.\n");

    return;
  }
  m_attributes = attributes;
  m_transport = &driver;
  m_packetInfo.srcPort = attributes.unicastLocator.port;
  m_is_initialized_ = true;
}

template <class NetworkDriver>
void StatefulReaderT<NetworkDriver>::newChange(
    const ReaderCacheChange &cacheChange) {
  if (!readerPayloadSupported(
          cacheChange.getData(), cacheChange.getDataSize()) ||
      (isUserReader() &&
       !mros2UserCdrPayloadSupported(
           cacheChange.getData(), cacheChange.getDataSize()))) {
    Lock lock{m_mutex};
    ++m_unsupportedPayloadDropCount;
      return;
  }
  ddsReaderPayloadValidator_fp payloadValidator = nullptr;
  void *payloadValidatorCallee = nullptr;
  {
    Lock lock{m_mutex};
    payloadValidator = m_payloadValidator;
    payloadValidatorCallee = m_payloadValidatorCallee;
  }
  if (payloadValidator != nullptr &&
      !payloadValidator(payloadValidatorCallee, cacheChange)) {
    Lock lock{m_mutex};
    ++m_unsupportedPayloadDropCount;
    return;
  }
  ddsReaderCallback_fp callback = nullptr;
  void *callee = nullptr;
  bool shouldDeliver = false;
  bool matchedButNotDelivered = false;
  bool sendRepair = false;
  PacketInfo repairInfo;

  {
    Lock lock{m_mutex};
    if (m_callback == nullptr) {
      return;
    }

    callback = m_callback;
    callee = m_callee;

    auto prepareRepair = [&](WriterProxy &proxy) {
      SequenceNumberSet missing;
      missing.base = proxy.expectedSN;
      missing.numBits = 1;
      missing.bitMap[0] = uint32_t{1} << 31;

      repairInfo.srcPort = m_packetInfo.srcPort;
      repairInfo.destAddr = proxy.remoteLocator.getIp4Address();
      repairInfo.destPort = proxy.remoteLocator.port;
      sendRepair =
          rtps::MessageFactory::addHeader(
              repairInfo.buffer, m_attributes.endpointGuid.prefix) &&
          rtps::MessageFactory::addAckNack(
              repairInfo.buffer, cacheChange.writerGuid.entityId,
              m_attributes.endpointGuid.entityId, missing,
              proxy.getNextAckNackCount(), false);
      if (!sendRepair) {
        ++m_controlSendFailureCount;
      }
    };

    for (auto &proxy : m_proxies) {
      if (proxy.remoteWriterGuid == cacheChange.writerGuid) {
        if (proxy.expectedSequenceExhausted) {
          ++m_outOfOrderDropCount;
          return;
        }
        const ReaderSequenceAdmission admission =
            classifyReaderSequence(proxy.expectedSN, cacheChange.sn);
        if (admission == ReaderSequenceAdmission::STALE) {
          ++m_outOfOrderDropCount;
          return;
        }
        if (admission == ReaderSequenceAdmission::AHEAD) {
          proxy.heartbeatSolicitationOutstanding = false;
          proxy.heartbeatSolicitationConfirmed = false;
          ++m_outOfOrderDropCount;
          recordHighestObserved(proxy.highestObservedSN, cacheChange.sn);
          prepareRepair(proxy);
          matchedButNotDelivered = true;
          break;
        }

        proxy.heartbeatSolicitationOutstanding = false;
        proxy.heartbeatSolicitationConfirmed = false;
        advanceReaderExpected(cacheChange.sn, proxy.expectedSN,
                              proxy.expectedSequenceExhausted);
        if (!proxy.expectedSequenceExhausted &&
            readerNeedsRepair(proxy.expectedSN, proxy.highestObservedSN)) {
          prepareRepair(proxy);
        } else {
          proxy.highestObservedSN = SEQUENCENUMBER_UNKNOWN;
        }
        shouldDeliver = true;
        break;
      }
    }

    if (!shouldDeliver && !matchedButNotDelivered) {
      // Volatile Readers may accept live DATA that races SEDP completion or a
      // stale-proxy cleanup. Transient Local Readers wait for matched replay
      // so an arbitrary early sequence cannot hide older retained History.
      if (!readerMayDeliverBeforeMatch(m_attributes.durabilityKind,
                                       m_attributes.reliabilityKind)) {
        ++m_unmatchedWriterDropCount;
        return;
      }
      PendingWriterState *pending =
          findOrAddPendingWriter(cacheChange.writerGuid);
      if (pending == nullptr) {
        ++m_unmatchedWriterDropCount;
        return;
      }
      if (!admitReliableSequence(cacheChange.sn, pending->nextSN,
                                 pending->sequenceExhausted)) {
        ++m_outOfOrderDropCount;
        return;
      }
      ++m_acceptedBeforeMatchCount;
      shouldDeliver = true;
    }

    // A duplicate or stale Reliable retransmission is not a new DDS sample and
    // must not refresh Deadline/Liveliness or inflate the accepted count.
    if (shouldDeliver) {
      m_lastReceiveTimeMs = rtps::getCurrentTimeMs();
      m_hasReceiveActivity = true;
      m_hasRepairProbeTime = false;
      m_nextDeadlineTimeMs =
          m_deadlineMs > 0 ? m_lastReceiveTimeMs + m_deadlineMs : 0;
      m_hasDeadlineBaseline = m_deadlineMs > 0;
      m_lastHeartbeatTimeMs = m_lastReceiveTimeMs;
      m_hasLivelinessActivity = true;
      if (!m_livelinessStateInitialized) {
        m_livelinessStateInitialized = true;
        m_lastAliveState = true;
      }
      ++m_receivedCount;
    }
  }

  if (sendRepair) {
    if (m_transport == nullptr || !m_transport->sendPacket(repairInfo)) {
      Lock lock(m_mutex);
      ++m_controlSendFailureCount;
    }
  }
  if (shouldDeliver && callback != nullptr) {
    callback(callee, cacheChange);
  }
}

template <class NetworkDriver>
void StatefulReaderT<NetworkDriver>::registerCallback(ddsReaderCallback_fp cb,
                                                      void *callee) {
  Lock lock{m_mutex};
  if (cb != nullptr) {
    m_callback = cb;
    m_callee = callee; // It's okay if this is null
  } else {

    SFR_LOG("Passed callback is nullptr\n");
  }
}

template <class NetworkDriver>
void StatefulReaderT<NetworkDriver>::registerPayloadValidator(
    ddsReaderPayloadValidator_fp validator, void *callee) {
  Lock lock{m_mutex};
  m_payloadValidator = validator;
  m_payloadValidatorCallee = callee;
}

template <class NetworkDriver>
void StatefulReaderT<NetworkDriver>::setDeadlineMissedCallback(
    void (*cb)(void *), void *arg) {
  Lock lock{m_mutex};
  m_deadlineMissedCb = cb;
  m_deadlineMissedArg = arg;
}

template <class NetworkDriver>
void StatefulReaderT<NetworkDriver>::setLivelinessLostCallback(
    void (*cb)(void *), void *arg) {
  Lock lock{m_mutex};
  m_livelinessLostCb = cb;
  m_livelinessLostArg = arg;
}

template <class NetworkDriver>
void StatefulReaderT<NetworkDriver>::setLivelinessRecoveredCallback(
    void (*cb)(void *), void *arg) {
  Lock lock{m_mutex};
  m_livelinessRecoveredCb = cb;
  m_livelinessRecoveredArg = arg;
}

template <class NetworkDriver>
bool StatefulReaderT<NetworkDriver>::addNewMatchedWriter(
    const WriterProxy &newProxy) {
#if SFR_VERBOSE && RTPS_GLOBAL_VERBOSE
  SFR_LOG("New writer added with id: ");
  printGuid(newProxy.remoteWriterGuid);
  SFR_LOG("\n");
#endif
  Lock lock{m_mutex};
  WriterProxy proxy = newProxy;
  for (const auto &matched : m_proxies) {
    if (matched.remoteWriterGuid == proxy.remoteWriterGuid) {
      return false;
    }
  }
  applyPendingWriterState(proxy);
  const bool added = m_proxies.add(proxy);
  if (added) {
    removePendingWriter(proxy.remoteWriterGuid);
  }
  return added;
}

template <class NetworkDriver>
void StatefulReaderT<NetworkDriver>::removeWriter(const Guid_t &guid) {
  Lock lock(m_mutex);
  auto isElementToRemove = [&](const WriterProxy &proxy) {
    return proxy.remoteWriterGuid == guid;
  };
  auto thunk = [](void *arg, const WriterProxy &value) {
    return (*static_cast<decltype(isElementToRemove) *>(arg))(value);
  };

  m_proxies.remove(thunk, &isElementToRemove);
  removePendingWriter(guid);
}

template <class NetworkDriver>
void StatefulReaderT<NetworkDriver>::removeWriterOfParticipant(
    const GuidPrefix_t &guidPrefix) {
  Lock lock(m_mutex);
  auto isElementToRemove = [&](const WriterProxy &proxy) {
    return proxy.remoteWriterGuid.prefix == guidPrefix;
  };
  auto thunk = [](void *arg, const WriterProxy &value) {
    return (*static_cast<decltype(isElementToRemove) *>(arg))(value);
  };

  m_proxies.remove(thunk, &isElementToRemove);
  removePendingWritersOfParticipant(guidPrefix);
}

template <class NetworkDriver>
bool StatefulReaderT<NetworkDriver>::onNewHeartbeat(
    const SubmessageHeartbeat &msg, const GuidPrefix_t &sourceGuidPrefix) {
  PacketInfo info;
  Guid_t writerGuid = GUID_UNKNOWN;
  Count_t previousHeartbeatCount{};
  bool previouslyHadHeartbeatCount = false;
  {
    Lock lock(m_mutex);
    info.srcPort = m_packetInfo.srcPort;
    WriterProxy *writer = nullptr;
    // Search for writer
    for (WriterProxy &proxy : m_proxies) {
      if (proxy.remoteWriterGuid.prefix == sourceGuidPrefix &&
          proxy.remoteWriterGuid.entityId == msg.writerId) {
        writer = &proxy;
        break;
      }
    }

    if (writer == nullptr) {

#if SFR_VERBOSE && RTPS_GLOBAL_VERBOSE
      SFR_LOG("Ignore heartbeat. Couldn't find a matching "
              "writer with id:");
      printEntityId(msg.writerId);
      SFR_LOG("\n");
#endif
      return false;
    }

    if (!countIsAdmissible(writer->hasHeartbeatCount, msg.count,
                           writer->hbCount)) {

      SFR_LOG("Ignore heartbeat. Count too low.\n");
      return false;
    }

    writerGuid = writer->remoteWriterGuid;
    previousHeartbeatCount = writer->hbCount;
    previouslyHadHeartbeatCount = writer->hasHeartbeatCount;
    writer->hbCount = msg.count;
    writer->hasHeartbeatCount = true;
    recordHeartbeatHigh(writer->highestObservedSN, msg.firstSN, msg.lastSN);

    // Update Liveliness: heartbeat proves writer is alive
    m_lastHeartbeatTimeMs = rtps::getCurrentTimeMs();
    m_hasLivelinessActivity = true;
    if (!m_livelinessStateInitialized) {
      m_livelinessStateInitialized = true;
      m_lastAliveState = true;
    }

    info.destAddr = writer->remoteLocator.getIp4Address();
    info.destPort = writer->remoteLocator.port;
    const SequenceNumberSet missing =
        writer->getMissing(msg.firstSN, msg.lastSN);
    const bool requestsRepair =
        sequenceNumberSetRequestsRepair(missing);
    if (writer->heartbeatSolicitationOutstanding) {
      writer->heartbeatSolicitationOutstanding = false;
      writer->heartbeatSolicitationConfirmed = !requestsRepair;
    }
    if (!rtps::MessageFactory::addHeader(
            info.buffer, m_attributes.endpointGuid.prefix) ||
        !rtps::MessageFactory::addAckNack(
            info.buffer, msg.writerId, m_attributes.endpointGuid.entityId,
            missing, writer->getNextAckNackCount(),
            !requestsRepair)) {
      rollbackCountIfCurrent(
          msg.count, previouslyHadHeartbeatCount, previousHeartbeatCount,
          writer->hasHeartbeatCount, writer->hbCount);
      ++m_controlSendFailureCount;
      return true;
    }
  }

  SFR_LOG("Sending acknack.\n");
  if (m_transport == nullptr || !m_transport->sendPacket(info)) {
    Lock lock(m_mutex);
    for (WriterProxy &proxy : m_proxies) {
      if (proxy.remoteWriterGuid == writerGuid) {
        rollbackCountIfCurrent(
            msg.count, previouslyHadHeartbeatCount, previousHeartbeatCount,
            proxy.hasHeartbeatCount, proxy.hbCount);
        break;
      }
    }
    ++m_controlSendFailureCount;
  }
  return true;
}

template <class NetworkDriver>
bool StatefulReaderT<NetworkDriver>::onNewGap(
    const SubmessageGap &msg, const GuidPrefix_t &sourceGuidPrefix) {
  PacketInfo repairInfo;
  bool found = false;
  bool sendRepair = false;
  {
    Lock lock(m_mutex);
    for (WriterProxy &proxy : m_proxies) {
      if (proxy.remoteWriterGuid.prefix == sourceGuidPrefix &&
          proxy.remoteWriterGuid.entityId == msg.writerId) {
        if (!proxy.expectedSequenceExhausted) {
          proxy.expectedSN = readerExpectedAfterGap(
              proxy.expectedSN, msg.gapStart, msg.gapList,
              &proxy.expectedSequenceExhausted);
        }
        ++m_gapReceivedCount;
        found = true;

        if (!proxy.expectedSequenceExhausted &&
            readerNeedsRepair(proxy.expectedSN, proxy.highestObservedSN)) {
          SequenceNumberSet missing;
          missing.base = proxy.expectedSN;
          missing.numBits = 1;
          missing.bitMap[0] = uint32_t{1} << 31;
          repairInfo.srcPort = m_packetInfo.srcPort;
          repairInfo.destAddr = proxy.remoteLocator.getIp4Address();
          repairInfo.destPort = proxy.remoteLocator.port;
          sendRepair =
              rtps::MessageFactory::addHeader(
                  repairInfo.buffer, m_attributes.endpointGuid.prefix) &&
              rtps::MessageFactory::addAckNack(
                  repairInfo.buffer, msg.writerId,
                  m_attributes.endpointGuid.entityId, missing,
                  proxy.getNextAckNackCount(), false);
          if (!sendRepair) {
            ++m_controlSendFailureCount;
          }
        } else {
          proxy.highestObservedSN = SEQUENCENUMBER_UNKNOWN;
        }
        break;
      }
    }
  }
  if (sendRepair) {
    if (m_transport == nullptr || !m_transport->sendPacket(repairInfo)) {
      Lock lock(m_mutex);
      ++m_controlSendFailureCount;
    }
  }
  return found;
}

template <class NetworkDriver>
void StatefulReaderT<NetworkDriver>::checkReliabilityRepair() {
  PacketInfo info;
  bool sendProbe = false;
  {
    Lock lock{m_mutex};
    const uint32_t nowMs = rtps::getCurrentTimeMs();
    for (WriterProxy &proxy : m_proxies) {
      const bool reliable =
          readerUsesReliabilityProtocol(m_attributes.reliabilityKind);
      const bool hasKnownMissing =
          readerNeedsRepair(proxy.expectedSN, proxy.highestObservedSN);
      const bool requestKnownMissing = readerRepairProbeDue(
          reliable, m_hasReceiveActivity, proxy.expectedSequenceExhausted,
          hasKnownMissing, nowMs, m_lastReceiveTimeMs, m_hasRepairProbeTime,
          m_lastRepairProbeTimeMs);
      const bool solicitHeartbeat =
          isUserReader() &&
          readerHeartbeatSolicitationDue(
              reliable, m_hasReceiveActivity, proxy.expectedSequenceExhausted,
              hasKnownMissing, proxy.heartbeatSolicitationConfirmed, nowMs,
              m_lastReceiveTimeMs, m_hasRepairProbeTime,
              m_lastRepairProbeTimeMs);
      if (!requestKnownMissing && !solicitHeartbeat) {
        continue;
      }

      SequenceNumberSet requested;
      requested.base = proxy.expectedSN;
      if (requestKnownMissing) {
        requested.numBits = 1;
        requested.bitMap[0] = uint32_t{1} << 31;
      } else {
        // The RTPS preemptive form (base 0, empty bitmap, Final=false) asks
        // for the Writer's HEARTBEAT without acknowledging or asserting that
        // expectedSN already exists.
        requested.base = {0, 0};
        requested.numBits = 0;
        proxy.heartbeatSolicitationOutstanding = true;
      }
      info.srcPort = m_packetInfo.srcPort;
      info.destAddr = proxy.remoteLocator.getIp4Address();
      info.destPort = proxy.remoteLocator.port;
      sendProbe =
          rtps::MessageFactory::addHeader(
              info.buffer, m_attributes.endpointGuid.prefix) &&
          rtps::MessageFactory::addAckNack(
              info.buffer, proxy.remoteWriterGuid.entityId,
              m_attributes.endpointGuid.entityId, requested,
              proxy.getNextAckNackCount(), false);
      m_lastRepairProbeTimeMs = nowMs;
      m_hasRepairProbeTime = true;
      if (!sendProbe) {
        ++m_controlSendFailureCount;
      }
      break;
    }
  }

  if (sendProbe &&
      (m_transport == nullptr || !m_transport->sendPacket(info))) {
    Lock lock{m_mutex};
    ++m_controlSendFailureCount;
  }
}

template <class NetworkDriver>
bool StatefulReaderT<NetworkDriver>::isWriterAlive() const {
  Lock lock{m_mutex};
  if (m_livelinessLeaseMs == 0) return true;
  if (!m_hasLivelinessActivity) return false;
  return qosLeaseAlive(m_lastHeartbeatTimeMs, m_livelinessLeaseMs,
                       rtps::getCurrentTimeMs());
}

template <class NetworkDriver>
bool StatefulReaderT<NetworkDriver>::checkDeadlineMissed() {
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
void StatefulReaderT<NetworkDriver>::checkLiveliness() {
  void (*callback)(void *) = nullptr;
  void *callbackArg = nullptr;
  {
    Lock lock{m_mutex};
    const bool alive = qosLeaseAlive(m_lastHeartbeatTimeMs,
                                     m_livelinessLeaseMs,
                                     rtps::getCurrentTimeMs());
    const auto transition = evaluateLivelinessTransition(
        m_livelinessLeaseMs > 0, m_livelinessStateInitialized,
        m_hasLivelinessActivity, m_lastAliveState, alive);
    if (transition == LivelinessTransition::NONE) {
      return;
    }
    if (transition == LivelinessTransition::LOST) {
      ++m_livelinessLostCount;
      callback = m_livelinessLostCb;
      callbackArg = m_livelinessLostArg;
    } else {
      ++m_livelinessRecoveredCount;
      callback = m_livelinessRecoveredCb;
      callbackArg = m_livelinessRecoveredArg;
    }
    m_lastAliveState = alive;
  }
  if (callback != nullptr) {
    callback(callbackArg);
  }
}

#undef SFR_VERBOSE
