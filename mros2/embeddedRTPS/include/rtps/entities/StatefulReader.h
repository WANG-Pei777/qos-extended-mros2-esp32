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
#include "rtps/entities/Reader.h"
#include "rtps/entities/WriterProxy.h"
#include "rtps/storages/MemoryPool.h"

namespace rtps {
struct SubmessageHeartbeat;

template <class NetworkDriver> class StatefulReaderT final : public Reader {
public:
  ~StatefulReaderT() override;
  void init(const TopicData &attributes, NetworkDriver &driver);
  void newChange(const ReaderCacheChange &cacheChange) override;
  void registerCallback(ddsReaderCallback_fp cb, void *callee) override;
  bool addNewMatchedWriter(const WriterProxy &newProxy) override;
  void removeWriter(const Guid_t &guid) override;
  void removeWriterOfParticipant(const GuidPrefix_t &guidPrefix) override;
  bool onNewHeartbeat(const SubmessageHeartbeat &msg,
                      const GuidPrefix_t &remotePrefix) override;

  // QoS configuration
  void setDeadlineMs(uint32_t ms) override { m_deadlineMs = ms; }
  void setLivelinessLeaseMs(uint32_t ms) override { m_livelinessLeaseMs = ms; }
  void setDeadlineMissedCallback(void (*cb)(void *), void *arg) {
    m_deadlineMissedCb = cb;
    m_deadlineMissedArg = arg;
  }

  // QoS stats
  uint32_t getDeadlineMissedCount() const { return m_deadlineMissedCount; }
  bool isWriterAlive() const override;
  uint32_t getReceivedCount() const override { return m_receivedCount; }
  uint32_t getAcceptedBeforeMatchCount() const override {
    return m_acceptedBeforeMatchCount;
  }
  uint32_t getOutOfOrderDropCount() const override {
    return m_outOfOrderDropCount;
  }
  uint32_t getUnmatchedWriterDropCount() const override {
    return m_unmatchedWriterDropCount;
  }
  // Periodic check: call from app thread to detect deadline misses
  bool checkDeadlineMissed();

  // Liveliness state machine: detect lost/recovered transitions
  void checkLiveliness() override;
  uint32_t getLivelinessLostCount() const override { return m_livelinessLostCount; }
  uint32_t getLivelinessRecoveredCount() const override { return m_livelinessRecoveredCount; }

private:
  PacketInfo
      m_packetInfo; // TODO intended for reuse but buffer not used as such
  NetworkDriver *m_transport;

  ddsReaderCallback_fp m_callback = nullptr;
  void *m_callee = nullptr;
  sys_mutex_t m_mutex;

  // QoS state
  uint32_t m_deadlineMs = 0;
  uint64_t m_lastReceiveTimeMs = 0;
  uint64_t m_nextDeadlineTimeMs = 0;
  uint32_t m_deadlineMissedCount = 0;
  uint32_t m_livelinessLeaseMs = 0;
  uint64_t m_lastHeartbeatTimeMs = 0;
  void (*m_deadlineMissedCb)(void *) = nullptr;
  void *m_deadlineMissedArg = nullptr;

  // Receive path observability. These counters are intentionally lightweight
  // so ESP32 validation runs can report what happened without enabling verbose RTPS logs.
  uint32_t m_receivedCount = 0;
  uint32_t m_acceptedBeforeMatchCount = 0;
  uint32_t m_outOfOrderDropCount = 0;
  uint32_t m_unmatchedWriterDropCount = 0;
  Guid_t m_pendingWriterGuid = GUID_UNKNOWN;
  SequenceNumber_t m_pendingNextSN = SEQUENCENUMBER_UNKNOWN;

  // Liveliness state machine
  bool m_lastAliveState = true; // assume alive initially
  uint32_t m_livelinessLostCount = 0;
  uint32_t m_livelinessRecoveredCount = 0;
};

using StatefulReader = StatefulReaderT<UdpDriver>;

} // namespace rtps

#include "StatefulReader.tpp"

#endif // RTPS_STATEFULREADER_H
