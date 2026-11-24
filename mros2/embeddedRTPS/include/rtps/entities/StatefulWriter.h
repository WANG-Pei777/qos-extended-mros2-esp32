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

#ifndef RTPS_STATEFULWRITER_H
#define RTPS_STATEFULWRITER_H

#include "rtps/entities/ReaderProxy.h"
#include "rtps/entities/DurabilityState.h"
#include "rtps/entities/FragmentationCapability.h"
#include "rtps/entities/Lifespan.h"
#include "rtps/entities/QosTime.h"
#include "rtps/entities/ReliabilityState.h"
#include "rtps/entities/ResourceLimits.h"
#include "rtps/entities/Writer.h"
#include "rtps/storages/MemoryPool.h"
#include "rtps/storages/SimpleHistoryCache.h"
#include "rtps/utils/Lock.h"
#include "rtps/utils/sysFunctions.h"

#include <array>
#include <atomic>

namespace rtps {

template <class NetworkDriver> class StatefulWriterT final : public Writer {
public:
  ~StatefulWriterT() override;
  bool init(TopicData attributes, TopicKind_t topicKind, ThreadPool *threadPool,
            NetworkDriver &driver, bool enfUnicast = false);

  // QoS configuration
  void setDeadlineMs(uint32_t ms) override {
    Lock lock{m_mutex};
    m_deadlineMs = ms;
  }
  void setLifespanMs(uint32_t ms) override {
    Lock lock{m_mutex};
    m_lifespanMs = ms;
  }
  void setLivelinessLeaseMs(uint32_t ms) override {
    Lock lock{m_mutex};
    m_livelinessLeaseMs = ms;
  }
  void setResourceLimits(uint32_t maxSamples, uint32_t maxBytes) {
    Lock lock{m_mutex};
    m_maxSamples = maxSamples;
    m_maxBytes = maxBytes;
  }
  void setKeepAll(bool keepAll) override {
    Lock lock{m_mutex};
    m_keepAll = keepAll;
  }
  void setHistoryDepth(uint32_t depth) override {
    Lock lock{m_mutex};
    m_historyDepth = depth;
  }
  void setTransmissionHeld(bool held) override;
  void setDeadlineMissedCallback(void (*cb)(void *), void *arg) override;
  bool checkDeadlineMissed() override;

  // QoS stats
  uint32_t getDeadlineMissedCount() const override {
    Lock lock{m_mutex};
    return m_deadlineMissedCount;
  }
  uint32_t getLifespanDropCount() const override {
    Lock lock{m_mutex};
    return m_lifespanDropCount;
  }
  uint32_t getPublishAttemptCount() const override {
    Lock lock{m_mutex};
    return m_publishAttemptCount;
  }
  uint32_t getPublishAcceptCount() const override {
    Lock lock{m_mutex};
    return m_publishAcceptCount;
  }
  uint32_t getResourceRejectCount() const override {
    Lock lock{m_mutex};
    return m_resourceRejectCount;
  }
  uint32_t getAllocationFailureCount() const override {
    Lock lock{m_mutex};
    return m_allocationFailureCount;
  }
  uint32_t getLocalSendFailureCount() const override {
    Lock lock{m_mutex};
    return m_localSendFailureCount;
  }
  uint32_t getControlSendFailureCount() const override {
    Lock lock{m_mutex};
    return m_controlSendFailureCount;
  }
  uint32_t getHistoryDepth() const override {
    Lock lock{m_mutex};
    return m_historyDepth;
  }
  uint32_t getHistoryCount() const override {
    Lock lock{m_mutex};
    return m_history.getChangeCount();
  }
  uint32_t getHistoryBytes() const override {
    Lock lock{m_mutex};
    const uint64_t bytes = m_history.getTotalDataBytes();
    return bytes > UINT32_MAX ? UINT32_MAX : static_cast<uint32_t>(bytes);
  }
  uint32_t getAckNackReceiveCount() const override {
    Lock lock{m_mutex};
    return m_ackNackReceiveCount;
  }
  uint32_t getAckNackAcceptCount() const override {
    Lock lock{m_mutex};
    return m_ackNackAcceptCount;
  }
  uint32_t getAckNackStaleDropCount() const override {
    Lock lock{m_mutex};
    return m_ackNackStaleDropCount;
  }
  uint32_t getAckNackUnknownReaderDropCount() const override {
    Lock lock{m_mutex};
    return m_ackNackUnknownReaderDropCount;
  }
  uint32_t getAckNackBestEffortDropCount() const override {
    Lock lock{m_mutex};
    return m_ackNackBestEffortDropCount;
  }
  uint32_t getAckNackGapResponseCount() const override {
    Lock lock{m_mutex};
    return m_ackNackGapResponseCount;
  }
  uint32_t getAckNackDataResponseCount() const override {
    Lock lock{m_mutex};
    return m_ackNackDataResponseCount;
  }
  uint32_t getAckNackDeferredResponseCount() const override {
    Lock lock{m_mutex};
    return m_ackNackDeferredResponseCount;
  }
  bool isAlive() const {
    Lock lock{m_mutex};
    return m_isAlive;
  }
  // Liveliness: manually assert that this writer is alive
  void assertLiveliness() override {
    Lock lock{m_mutex};
    m_isAlive = true;
    m_lastPublishTimeMs = rtps::getCurrentTimeMs();
  }

  bool addNewMatchedReader(const ReaderProxy &newProxy) override;
  bool knowReaderId(const Guid_t &guid) override {
    Lock lock{m_mutex};
    for (const auto &proxy : m_proxies) {
      if (proxy.remoteReaderGuid == guid) {
        return true;
      }
    }
    return false;
  }
  uint32_t getNumMatchedReader() override {
    Lock lock{m_mutex};
    return m_proxies.getNumElements();
  }
  void removeReader(const Guid_t &guid) override;
  void removeReaderOfParticipant(const GuidPrefix_t &guidPrefix) override;
  void progress() override;
  const CacheChange *newChange(ChangeKind_t kind, const uint8_t *data,
                               DataSize_t size) override;
  const CacheChange *newChangeCallback(ChangeKind_t kind,
      CacheChange::SerializerCallback func,
      FragDataSize_t size) override;
  void setAllChangesToUnsent() override;
  void onNewAckNack(const SubmessageAckNack &msg,
                    const GuidPrefix_t &sourceGuidPrefix) override;

private:
  mutable sys_mutex_t m_mutex;
  ThreadPool *mp_threadPool = nullptr;

  PacketInfo m_packetInfo;
  NetworkDriver *m_transport;
  bool m_enforceUnicast;

  TopicKind_t m_topicKind = TopicKind_t::NO_KEY;
  SequenceNumber_t m_nextSequenceNumberToSend = {0, 1};
  bool m_sendCursorExhausted = false;
  SequenceNumber_t m_retrySequence = SEQUENCENUMBER_UNKNOWN;
  uint8_t m_sendRetryCount = 0;
  SequenceNumber_t m_lastSequenceNumberSent = SEQUENCENUMBER_UNKNOWN;
  SimpleHistoryCache<Config::HISTORY_SIZE_STATEFUL> m_history;
  sys_thread_t m_heartbeatThread;
  Count_t m_hbCount{1};

  std::atomic<bool> m_running{true};
  std::atomic<bool> m_thread_running{false};

  // QoS state
  bool m_keepAll = false;
  uint32_t m_historyDepth = 0;
  uint32_t m_deadlineMs = 0;
  uint32_t m_lastPublishTimeMs = 0;
  uint32_t m_nextDeadlineTimeMs = 0;
  bool m_hasDeadlineBaseline = false;
  uint32_t m_deadlineMissedCount = 0;
  void (*m_deadlineMissedCb)(void *) = nullptr;
  void *m_deadlineMissedArg = nullptr;
  uint32_t m_lifespanMs = 0;
  uint32_t m_lifespanDropCount = 0;
  uint32_t m_livelinessLeaseMs = 0;
  bool m_isAlive = true;
  uint32_t m_maxSamples = 0;
  uint32_t m_maxBytes = 0;
  uint32_t m_publishAttemptCount = 0;
  uint32_t m_publishAcceptCount = 0;
  uint32_t m_resourceRejectCount = 0;
  uint32_t m_allocationFailureCount = 0;
  uint32_t m_localSendFailureCount = 0;
  uint32_t m_controlSendFailureCount = 0;
  uint32_t m_ackNackReceiveCount = 0;
  uint32_t m_ackNackAcceptCount = 0;
  uint32_t m_ackNackStaleDropCount = 0;
  uint32_t m_ackNackUnknownReaderDropCount = 0;
  uint32_t m_ackNackBestEffortDropCount = 0;
  uint32_t m_ackNackGapResponseCount = 0;
  uint32_t m_ackNackDataResponseCount = 0;
  uint32_t m_ackNackDeferredResponseCount = 0;
  bool m_transmissionHeld = false;

  bool sendData(const ReaderProxy &reader, const SequenceNumber_t &sn);
  bool sendDataLocked(const ReaderProxy &reader, const SequenceNumber_t &sn);
  bool sendGap(const ReaderProxy &reader, const SequenceNumber_t &sn);
  bool sendDataWRMulticast(const ReaderProxy &reader,
                           const SequenceNumber_t &sn);
  static void hbFunctionJumppad(void *thisPointer);
  void sendHeartBeatLoop();
  void sendHeartBeat();
  void purgeExpiredChangesLocked(uint32_t nowMs);
  void releaseUnmatchedVolatileHistoryLocked();
  void releaseAcknowledgedChanges();
  bool isIrrelevant(ChangeKind_t kind) const;
  void manageSendOptions();
  void resetSendOptions();
};

using StatefulWriter = StatefulWriterT<UdpDriver>;
} // namespace rtps

#include "StatefulWriter.tpp"

#endif // RTPS_STATEFULWRITER_H
