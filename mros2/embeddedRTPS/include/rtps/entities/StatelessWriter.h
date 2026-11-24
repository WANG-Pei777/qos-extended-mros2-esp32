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

#ifndef RTPS_RTPSWRITER_H
#define RTPS_RTPSWRITER_H

#include "lwip/sys.h"
#include "rtps/common/types.h"
#include "rtps/config.h"
#include "rtps/entities/DurabilityState.h"
#include "rtps/entities/ReliabilityState.h"
#include "rtps/entities/ResourceLimits.h"
#include "rtps/entities/Writer.h"
#include "rtps/storages/MemoryPool.h"
#include "rtps/storages/SimpleHistoryCache.h"
#include "rtps/utils/Lock.h"

#include <array>

namespace rtps {

struct PBufWrapper;

template <typename NetworkDriver> class StatelessWriterT : public Writer {
public:
  ~StatelessWriterT() override;
  bool init(TopicData attributes, TopicKind_t topicKind, ThreadPool *threadPool,
            NetworkDriver &driver, bool enfUnicast = false);

  void setResourceLimits(uint32_t maxSamples, uint32_t maxBytes) override {
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
  void sendRawPacket(PacketInfo &info);

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
  SimpleHistoryCache<Config::HISTORY_SIZE_STATELESS> m_history;
  bool m_keepAll = false;
  uint32_t m_historyDepth = 0;
  uint32_t m_maxSamples = 0;
  uint32_t m_maxBytes = 0;
  uint32_t m_publishAttemptCount = 0;
  uint32_t m_publishAcceptCount = 0;
  uint32_t m_resourceRejectCount = 0;
  uint32_t m_allocationFailureCount = 0;
  uint32_t m_localSendFailureCount = 0;
  bool m_transmissionHeld = false;

  bool isIrrelevant(ChangeKind_t kind) const;
  bool sendData(const ReaderProxy &reader, const SequenceNumber_t &sn);
  bool sendDataLocked(const ReaderProxy &reader, const SequenceNumber_t &sn);
  void releaseUnmatchedVolatileHistoryLocked();

  void manageSendOptions();
  void resetSendOptions();
};

using StatelessWriter = StatelessWriterT<UdpDriver>;

} // namespace rtps

#include "StatelessWriter.tpp"

#endif // RTPS_RTPSWRITER_H
