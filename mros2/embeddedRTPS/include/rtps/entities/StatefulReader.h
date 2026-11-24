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

#ifndef RTPS_STATEFULREADER_H
#define RTPS_STATEFULREADER_H

#include "lwip/sys.h"
#include "rtps/communication/UdpDriver.h"
#include "rtps/config.h"
#include "rtps/entities/QosTime.h"
#include "rtps/entities/Reader.h"
#include "rtps/entities/ReaderSequence.h"
#include "rtps/entities/LivelinessState.h"
#include "rtps/entities/WriterProxy.h"
#include "rtps/storages/MemoryPool.h"
#include "rtps/utils/Lock.h"

namespace rtps {
struct SubmessageHeartbeat;

template <class NetworkDriver> class StatefulReaderT final : public Reader {
public:
  ~StatefulReaderT() override;
  void init(const TopicData &attributes, NetworkDriver &driver);
  void newChange(const ReaderCacheChange &cacheChange) override;
  void registerCallback(ddsReaderCallback_fp cb, void *callee) override;
  void registerPayloadValidator(
      ddsReaderPayloadValidator_fp validator, void *callee) override;
  bool addNewMatchedWriter(const WriterProxy &newProxy) override;
  bool knowWriterId(const Guid_t &guid) override {
    Lock lock{m_mutex};
    for (const auto &proxy : m_proxies) {
      if (proxy.remoteWriterGuid == guid) {
        return true;
      }
    }
    return false;
  }
  uint32_t getNumMatchedWriters() override {
    Lock lock{m_mutex};
    return m_proxies.getNumElements();
  }
  void removeWriter(const Guid_t &guid) override;
  void removeWriterOfParticipant(const GuidPrefix_t &guidPrefix) override;
  bool onNewHeartbeat(const SubmessageHeartbeat &msg,
                      const GuidPrefix_t &remotePrefix) override;
  bool onNewGap(const SubmessageGap &msg,
                const GuidPrefix_t &remotePrefix) override;

  // QoS configuration
  void setDeadlineMs(uint32_t ms) override {
    Lock lock{m_mutex};
    m_deadlineMs = ms;
  }
  void setLivelinessLeaseMs(uint32_t ms) override {
    Lock lock{m_mutex};
    m_livelinessLeaseMs = ms;
  }
  void setDeadlineMissedCallback(void (*cb)(void *), void *arg) override;
  void setLivelinessLostCallback(void (*cb)(void *), void *arg) override;
  void setLivelinessRecoveredCallback(void (*cb)(void *), void *arg) override;

  // QoS stats
  uint32_t getDeadlineMissedCount() const override {
    Lock lock{m_mutex};
    return m_deadlineMissedCount;
  }
  bool isWriterAlive() const override;
  uint32_t getReceivedCount() const override {
    Lock lock{m_mutex};
    return m_receivedCount;
  }
  uint32_t getAcceptedBeforeMatchCount() const override {
    Lock lock{m_mutex};
    return m_acceptedBeforeMatchCount;
  }
  uint32_t getOutOfOrderDropCount() const override {
    Lock lock{m_mutex};
    return m_outOfOrderDropCount;
  }
  uint32_t getUnmatchedWriterDropCount() const override {
    Lock lock{m_mutex};
    return m_unmatchedWriterDropCount;
  }
  uint32_t getUnsupportedPayloadDropCount() const override {
    Lock lock{m_mutex};
    return m_unsupportedPayloadDropCount;
  }
  uint32_t getGapReceivedCount() const override {
    Lock lock{m_mutex};
    return m_gapReceivedCount;
  }
  uint32_t getControlSendFailureCount() const override {
    Lock lock{m_mutex};
    return m_controlSendFailureCount;
  }
  void checkReliabilityRepair() override;
  // Periodic check: call from app thread to detect deadline misses
  bool checkDeadlineMissed();

  // Liveliness state machine: detect lost/recovered transitions
  void checkLiveliness() override;
  uint32_t getLivelinessLostCount() const override {
    Lock lock{m_mutex};
    return m_livelinessLostCount;
  }
  uint32_t getLivelinessRecoveredCount() const override {
    Lock lock{m_mutex};
    return m_livelinessRecoveredCount;
  }

private:
  PacketInfo
      m_packetInfo; // TODO intended for reuse but buffer not used as such
  NetworkDriver *m_transport;

  ddsReaderCallback_fp m_callback = nullptr;
  void *m_callee = nullptr;
  ddsReaderPayloadValidator_fp m_payloadValidator = nullptr;
  void *m_payloadValidatorCallee = nullptr;
  mutable sys_mutex_t m_mutex;

  // QoS state
  uint32_t m_deadlineMs = 0;
  uint32_t m_lastReceiveTimeMs = 0;
  uint32_t m_nextDeadlineTimeMs = 0;
  bool m_hasDeadlineBaseline = false;
  uint32_t m_deadlineMissedCount = 0;
  uint32_t m_livelinessLeaseMs = 0;
  uint32_t m_lastHeartbeatTimeMs = 0;
  bool m_hasLivelinessActivity = false;
  void (*m_deadlineMissedCb)(void *) = nullptr;
  void *m_deadlineMissedArg = nullptr;
  void (*m_livelinessLostCb)(void *) = nullptr;
  void *m_livelinessLostArg = nullptr;
  void (*m_livelinessRecoveredCb)(void *) = nullptr;
  void *m_livelinessRecoveredArg = nullptr;

  // Receive path observability. These counters are intentionally lightweight
  // so ESP32 validation runs can report what happened without enabling verbose RTPS logs.
  uint32_t m_receivedCount = 0;
  uint32_t m_acceptedBeforeMatchCount = 0;
  uint32_t m_outOfOrderDropCount = 0;
  uint32_t m_unmatchedWriterDropCount = 0;
  uint32_t m_unsupportedPayloadDropCount = 0;
  uint32_t m_gapReceivedCount = 0;
  uint32_t m_controlSendFailureCount = 0;
  bool m_hasReceiveActivity = false;
  bool m_hasRepairProbeTime = false;
  uint32_t m_lastRepairProbeTimeMs = 0;

  // Liveliness state machine
  bool m_livelinessStateInitialized = false;
  bool m_lastAliveState = false;
  uint32_t m_livelinessLostCount = 0;
  uint32_t m_livelinessRecoveredCount = 0;
};

using StatefulReader = StatefulReaderT<UdpDriver>;

} // namespace rtps

#include "StatefulReader.tpp"

#endif // RTPS_STATEFULREADER_H
