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
  ddsReaderCallback_fp callback = nullptr;
  void *callee = nullptr;
  bool shouldDeliver = false;

  {
    Lock lock{m_mutex};
    if (m_callback == nullptr) {
      return;
    }

    callback = m_callback;
    callee = m_callee;

    // Update Deadline timer: record time of last received data
    m_lastReceiveTimeMs = rtps::getCurrentTimeMs();
    m_nextDeadlineTimeMs =
        m_deadlineMs > 0 ? m_lastReceiveTimeMs + m_deadlineMs : 0;
    m_lastHeartbeatTimeMs = m_lastReceiveTimeMs;
    ++m_receivedCount;

    for (auto &proxy : m_proxies) {
      if (proxy.remoteWriterGuid == cacheChange.writerGuid) {
        if (cacheChange.sn < proxy.expectedSN) {
          ++m_outOfOrderDropCount;
          return;
        }
        if (proxy.expectedSN != cacheChange.sn) {
          SFR_LOG("Resynchronizing expected SN from (%i,%u) to (%i,%u).\n",
                  proxy.expectedSN.high, proxy.expectedSN.low,
                  cacheChange.sn.high, cacheChange.sn.low);
        }

        proxy.expectedSN = cacheChange.sn;
        ++proxy.expectedSN;
        shouldDeliver = true;
        break;
      }
    }

    if (!shouldDeliver) {
      // Accept data that arrives before SEDP endpoint matching completes, or
      // after a host reset where stale proxies may still exist briefly. When
      // the matching writer is later added, addNewMatchedWriter() advances its
      // expected sequence number to avoid replay-drop churn.
      m_pendingWriterGuid = cacheChange.writerGuid;
      m_pendingNextSN = cacheChange.sn;
      ++m_pendingNextSN;
      ++m_acceptedBeforeMatchCount;
      shouldDeliver = true;
    }
  }

  if (shouldDeliver && callback != nullptr) {
    callback(callee, cacheChange);
  }
}

template <class NetworkDriver>
void StatefulReaderT<NetworkDriver>::registerCallback(ddsReaderCallback_fp cb,
                                                      void *callee) {
  if (cb != nullptr) {
    m_callback = cb;
    m_callee = callee; // It's okay if this is null
  } else {

    SFR_LOG("Passed callback is nullptr\n");
  }
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
  if (m_pendingWriterGuid == proxy.remoteWriterGuid &&
      m_pendingNextSN != SEQUENCENUMBER_UNKNOWN &&
      proxy.expectedSN < m_pendingNextSN) {
    proxy.expectedSN = m_pendingNextSN;
  }
  return m_proxies.add(proxy);
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
}

template <class NetworkDriver>
bool StatefulReaderT<NetworkDriver>::onNewHeartbeat(
    const SubmessageHeartbeat &msg, const GuidPrefix_t &sourceGuidPrefix) {
  Lock lock(m_mutex);
  PacketInfo info;
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

  if (msg.count.value <= writer->hbCount.value) {

    SFR_LOG("Ignore heartbeat. Count too low.\n");
    return false;
  }

  writer->hbCount.value = msg.count.value;

  // Update Liveliness: heartbeat proves writer is alive
  m_lastHeartbeatTimeMs = rtps::getCurrentTimeMs();

  info.destAddr = writer->remoteLocator.getIp4Address();
  info.destPort = writer->remoteLocator.port;
  rtps::MessageFactory::addHeader(info.buffer,
                                  m_attributes.endpointGuid.prefix);
  rtps::MessageFactory::addAckNack(info.buffer, msg.writerId, msg.readerId,
                                   writer->getMissing(msg.firstSN, msg.lastSN),
                                   writer->getNextAckNackCount(), false);

  SFR_LOG("Sending acknack.\n");
  m_transport->sendPacket(info);
  return true;
}

template <class NetworkDriver>
bool StatefulReaderT<NetworkDriver>::isWriterAlive() const {
  if (m_livelinessLeaseMs == 0) return true; // infinite lease = always alive
  if (m_lastHeartbeatTimeMs == 0) return false; // never received heartbeat
  return (rtps::getCurrentTimeMs() - m_lastHeartbeatTimeMs) < m_livelinessLeaseMs;
}

template <class NetworkDriver>
bool StatefulReaderT<NetworkDriver>::checkDeadlineMissed() {
  if (m_deadlineMs == 0) return false; // disabled
  if (m_nextDeadlineTimeMs == 0) return false; // no data received yet
  uint32_t now = rtps::getCurrentTimeMs();
  if (now > m_nextDeadlineTimeMs) {
    uint32_t missed = 1 + static_cast<uint32_t>(
        (now - m_nextDeadlineTimeMs) / m_deadlineMs);
    m_deadlineMissedCount += missed;
    m_nextDeadlineTimeMs += static_cast<uint64_t>(missed) * m_deadlineMs;
    if (m_deadlineMissedCb) {
      m_deadlineMissedCb(m_deadlineMissedArg);
    }
    return true;
  }
  return false;
}

template <class NetworkDriver>
void StatefulReaderT<NetworkDriver>::checkLiveliness() {
  if (m_livelinessLeaseMs == 0) return; // infinite lease, no transitions
  bool alive = isWriterAlive();
  if (m_lastAliveState && !alive) {
    // Transition: alive → lost
    ++m_livelinessLostCount;
  } else if (!m_lastAliveState && alive) {
    // Transition: lost → recovered
    ++m_livelinessRecoveredCount;
  }
  m_lastAliveState = alive;
}

#undef SFR_VERBOSE
