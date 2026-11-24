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

#include "rtps/entities/StatelessReader.h"
#include "rtps/utils/Lock.h"
#include "rtps/utils/Log.h"

using rtps::StatelessReader;

#if SLR_VERBOSE && RTPS_GLOBAL_VERBOSE
#include "rtps/utils/printutils.h"
#define SLR_LOG(...)                                                           \
  if (true) {                                                                  \
    printf("[StatelessReader %s] ", &m_attributes.topicName[0]);               \
    printf(__VA_ARGS__);                                                       \
    printf("\n");                                                              \
  }
#else
#define SLR_LOG(...) //
#endif

void StatelessReader::init(const TopicData &attributes) {
  m_attributes = attributes;
  if (sys_mutex_new(&m_mutex) != ERR_OK) {
    SLR_LOG("Failed to create mutex.\n");
    return;
  }
  m_is_initialized_ = true;
}

void StatelessReader::newChange(const ReaderCacheChange &cacheChange) {
  if (!readerPayloadSupported(
          cacheChange.getData(), cacheChange.getDataSize()) ||
      (isUserReader() &&
       !mros2UserCdrPayloadSupported(
           cacheChange.getData(), cacheChange.getDataSize()))) {
    Lock lock(m_mutex);
    ++m_unsupportedPayloadDropCount;
      return;
  }
  ddsReaderPayloadValidator_fp payloadValidator = nullptr;
  void *payloadValidatorCallee = nullptr;
  {
    Lock lock(m_mutex);
    payloadValidator = m_payloadValidator;
    payloadValidatorCallee = m_payloadValidatorCallee;
  }
  if (payloadValidator != nullptr &&
      !payloadValidator(payloadValidatorCallee, cacheChange)) {
    Lock lock(m_mutex);
    ++m_unsupportedPayloadDropCount;
    return;
  }
  ddsReaderCallback_fp callback = nullptr;
  void *callee = nullptr;
  {
    Lock lock(m_mutex);
    if (m_callback == nullptr) {
      return;
    }
    callback = m_callback;
    callee = m_callee;

    bool matched = false;
    for (auto &proxy : m_proxies) {
      if (!(proxy.remoteWriterGuid == cacheChange.writerGuid)) {
        continue;
      }
      matched = true;
      if (!admitBestEffortSequence(cacheChange.sn, proxy.expectedSN,
                                   proxy.expectedSequenceExhausted)) {
        ++m_outOfOrderDropCount;
        return;
      }
      break;
    }

    if (!matched && isUserReader()) {
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
      if (!admitBestEffortSequence(cacheChange.sn, pending->nextSN,
                                   pending->sequenceExhausted)) {
        ++m_outOfOrderDropCount;
        return;
      }
      ++m_acceptedBeforeMatchCount;
    }
    ++m_receivedCount;
  }
  callback(callee, cacheChange);
}

void StatelessReader::registerCallback(ddsReaderCallback_fp cb, void *callee) {
  Lock lock(m_mutex);
  if (cb != nullptr) {
    m_callback = cb;
    m_callee = callee; // It's okay if this is null
  } else {
#if (SLR_VERBOSE && RTPS_GLOBAL_VERBOSE)
    SLR_LOG("Passed callback is nullptr\n");
#endif
  }
}

void StatelessReader::registerPayloadValidator(
    ddsReaderPayloadValidator_fp validator, void *callee) {
  Lock lock(m_mutex);
  m_payloadValidator = validator;
  m_payloadValidatorCallee = callee;
}

bool StatelessReader::addNewMatchedWriter(const WriterProxy &newProxy) {
#if (SLR_VERBOSE && RTPS_GLOBAL_VERBOSE)
  SLR_LOG("Adding WriterProxy");
  printGuid(newProxy.remoteWriterGuid);
  printf("\n");
#endif
  Lock lock(m_mutex);
  for (const auto &proxy : m_proxies) {
    if (proxy.remoteWriterGuid == newProxy.remoteWriterGuid) {
      return false;
    }
  }
  WriterProxy proxy = newProxy;
  if (isUserReader()) {
    applyPendingWriterState(proxy);
  }
  const bool added = m_proxies.add(proxy);
  if (added) {
    removePendingWriter(proxy.remoteWriterGuid);
  }
  return added;
}

bool StatelessReader::knowWriterId(const Guid_t &guid) {
  Lock lock(m_mutex);
  for (const auto &proxy : m_proxies) {
    if (proxy.remoteWriterGuid == guid) {
      return true;
    }
  }
  return false;
}

uint32_t StatelessReader::getNumMatchedWriters() {
  Lock lock(m_mutex);
  return m_proxies.getNumElements();
}

void StatelessReader::removeWriter(const Guid_t &guid) {
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

void StatelessReader::removeWriterOfParticipant(
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

bool StatelessReader::onNewHeartbeat(const SubmessageHeartbeat &,
                                     const GuidPrefix_t &) {
  // nothing to do
  return true;
}

#undef SLR_VERBOSE
