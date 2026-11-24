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

#ifndef RTPS_READER_H
#define RTPS_READER_H

#include "rtps/common/types.h"
#include "rtps/config.h"
#include "rtps/discovery/TopicData.h"
#include "rtps/entities/WriterProxy.h"
#include "rtps/storages/MemoryPool.h"
#include "rtps/storages/PBufWrapper.h"
#include <cstring>

namespace rtps {

struct SubmessageHeartbeat;
struct SubmessageGap;

class ReaderCacheChange {
private:
  const uint8_t *data;

public:
  const ChangeKind_t kind;
  const DataSize_t size;
  const Guid_t writerGuid;
  const SequenceNumber_t sn;

  ReaderCacheChange(ChangeKind_t kind, Guid_t &writerGuid, SequenceNumber_t sn,
                    const uint8_t *data, DataSize_t size)
      : data(data), kind(kind), size(size), writerGuid(writerGuid), sn(sn){};

  ~ReaderCacheChange() =
      default; // No need to free data. It's not owned by this object
  // Not allowed because this class doesn't own the ptr and the user isn't
  // allowed to use it outside the Scope of the callback
  ReaderCacheChange(const ReaderCacheChange &other) = delete;
  ReaderCacheChange(ReaderCacheChange &&other) = delete;
  ReaderCacheChange &operator=(const ReaderCacheChange &other) = delete;
  ReaderCacheChange &operator=(ReaderCacheChange &&other) = delete;

  bool copyInto(uint8_t *buffer, DataSize_t destSize) const {
    if (destSize < size) {
      return false;
    } else {
      memcpy(buffer, data, size);
      return true;
    }
  }

  const uint8_t *getData() const { return data; }

  DataSize_t getDataSize() const { return size; }
};

typedef void (*ddsReaderCallback_fp)(void *callee,
                                     const ReaderCacheChange &cacheChange);
typedef bool (*ddsReaderPayloadValidator_fp)(
    void *callee, const ReaderCacheChange &cacheChange);

struct PendingWriterState {
  Guid_t writerGuid = GUID_UNKNOWN;
  SequenceNumber_t nextSN = SEQUENCENUMBER_UNKNOWN;
  bool sequenceExhausted = false;
};

class Reader {
public:
  TopicData m_attributes;
  virtual void newChange(const ReaderCacheChange &cacheChange) = 0;
  virtual void registerCallback(ddsReaderCallback_fp cb, void *callee) = 0;
  virtual void registerPayloadValidator(
      ddsReaderPayloadValidator_fp validator, void *callee) = 0;
  virtual bool onNewHeartbeat(const SubmessageHeartbeat &msg,
                              const GuidPrefix_t &remotePrefix) = 0;
  virtual bool onNewGap(const SubmessageGap &,
                        const GuidPrefix_t &) {
    return false;
  }
  virtual bool addNewMatchedWriter(const WriterProxy &newProxy) = 0;
  virtual void removeWriter(const Guid_t &guid) = 0;
  virtual void removeWriterOfParticipant(const GuidPrefix_t &guidPrefix) = 0;
  bool isInitialized() { return m_is_initialized_; }

  virtual bool knowWriterId(const Guid_t &guid) = 0;
  virtual uint32_t getNumMatchedWriters() = 0;

  // QoS setters (overridden by StatefulReader)
  virtual void setDeadlineMs(uint32_t) {}
  virtual void setLivelinessLeaseMs(uint32_t) {}
  virtual void setDeadlineMissedCallback(void (*)(void *), void *) {}
  virtual void setLivelinessLostCallback(void (*)(void *), void *) {}
  virtual void setLivelinessRecoveredCallback(void (*)(void *), void *) {}
  virtual uint32_t getDeadlineMissedCount() const { return 0; }
  virtual bool checkDeadlineMissed() { return false; }
  virtual bool isWriterAlive() const { return true; }
  virtual uint32_t getReceivedCount() const { return 0; }
  virtual uint32_t getAcceptedBeforeMatchCount() const { return 0; }
  virtual uint32_t getOutOfOrderDropCount() const { return 0; }
  virtual uint32_t getUnmatchedWriterDropCount() const { return 0; }
  virtual uint32_t getUnsupportedPayloadDropCount() const { return 0; }
  virtual uint32_t getGapReceivedCount() const { return 0; }
  virtual uint32_t getControlSendFailureCount() const { return 0; }
  virtual void checkReliabilityRepair() {}
  virtual void checkLiveliness() {}
  virtual uint32_t getLivelinessLostCount() const { return 0; }
  virtual uint32_t getLivelinessRecoveredCount() const { return 0; }

protected:
  bool isUserReader() const {
    const EntityKind_t kind = m_attributes.endpointGuid.entityId.entityKind;
    return kind == EntityKind_t::USER_DEFINED_READER_WITH_KEY ||
           kind == EntityKind_t::USER_DEFINED_READER_WITHOUT_KEY;
  }

  bool m_is_initialized_ = false;
  virtual ~Reader() = default;
  MemoryPool<WriterProxy, Config::NUM_WRITER_PROXIES_PER_READER> m_proxies;
  MemoryPool<PendingWriterState, Config::NUM_WRITER_PROXIES_PER_READER>
      m_pendingWriters;

  PendingWriterState *findPendingWriter(const Guid_t &guid) {
    for (auto &pending : m_pendingWriters) {
      if (pending.writerGuid == guid) {
        return &pending;
      }
    }
    return nullptr;
  }

  PendingWriterState *findOrAddPendingWriter(const Guid_t &guid) {
    PendingWriterState *pending = findPendingWriter(guid);
    if (pending != nullptr) {
      return pending;
    }
    PendingWriterState state;
    state.writerGuid = guid;
    if (!m_pendingWriters.add(state)) {
      return nullptr;
    }
    return findPendingWriter(guid);
  }

  void applyPendingWriterState(WriterProxy &proxy) {
    const PendingWriterState *pending =
        findPendingWriter(proxy.remoteWriterGuid);
    if (pending == nullptr) {
      return;
    }
    if (pending->sequenceExhausted) {
      proxy.expectedSN = pending->nextSN;
      proxy.expectedSequenceExhausted = true;
      return;
    }
    if (pending->nextSN != SEQUENCENUMBER_UNKNOWN &&
        proxy.expectedSN < pending->nextSN) {
      proxy.expectedSN = pending->nextSN;
    }
  }

  void removePendingWriter(const Guid_t &guid) {
    auto matches = [&](const PendingWriterState &pending) {
      return pending.writerGuid == guid;
    };
    auto thunk = [](void *arg, const PendingWriterState &pending) {
      return (*static_cast<decltype(matches) *>(arg))(pending);
    };
    m_pendingWriters.remove(thunk, &matches);
  }

  void removePendingWritersOfParticipant(const GuidPrefix_t &guidPrefix) {
    auto matches = [&](const PendingWriterState &pending) {
      return pending.writerGuid.prefix == guidPrefix;
    };
    auto thunk = [](void *arg, const PendingWriterState &pending) {
      return (*static_cast<decltype(matches) *>(arg))(pending);
    };
    m_pendingWriters.remove(thunk, &matches);
  }
};
} // namespace rtps

#endif // RTPS_READER_H
