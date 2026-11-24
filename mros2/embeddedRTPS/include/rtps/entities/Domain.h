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

#ifndef RTPS_DOMAIN_H
#define RTPS_DOMAIN_H

#include "rtps/ThreadPool.h"
#include "rtps/config.h"
#include "rtps/entities/Participant.h"
#include "rtps/entities/StatefulReader.h"
#include "rtps/entities/StatefulWriter.h"
#include "rtps/entities/StatelessReader.h"
#include "rtps/entities/StatelessWriter.h"
#include "rtps/storages/PBufWrapper.h"
#include <rtps/common/Locator.h>
#include <atomic>

namespace rtps {
class Domain {
public:
  Domain();
  ~Domain();

  bool completeInit();
  void stop();

  Participant *createParticipant();

  // New API: accept the full QoS parameter set.
  Writer *createWriter(Participant &part, const char *topicName,
                       const char *typeName, bool reliable,
                       ReliabilityKind_t reliabilityKind,
                       DurabilityKind_t durabilityKind,
                       bool enforceUnicast = false,
                       uint32_t deadlineMs = 0, uint32_t lifespanMs = 0,
                       uint32_t livelinessLeaseMs = 0,
                       uint32_t historyKind = 0, uint32_t historyDepth = 0,
                       uint32_t maxSamples = 0, uint32_t maxBytes = 0);

  Reader *createReader(Participant &part, const char *topicName,
                       const char *typeName, bool reliable,
                       ReliabilityKind_t reliabilityKind,
                       DurabilityKind_t durabilityKind,
                       ip4_addr_t mcastaddress = {0},
                       uint32_t deadlineMs = 0, uint32_t lifespanMs = 0,
                       uint32_t livelinessLeaseMs = 0,
                       uint32_t historyKind = 0, uint32_t historyDepth = 0,
                       ddsReaderCallback_fp callback = nullptr,
                       void *callbackCallee = nullptr,
                       ddsReaderPayloadValidator_fp payloadValidator = nullptr,
                       void *payloadValidatorCallee = nullptr);

  // Backward-compatible overloads for the previous API.
  Writer *createWriter(Participant &part, const char *topicName,
                       const char *typeName, bool reliable,
                       bool enforceUnicast = false) {
    return createWriter(part, topicName, typeName, reliable,
                       reliable ? ReliabilityKind_t::RELIABLE : ReliabilityKind_t::BEST_EFFORT,
                       DurabilityKind_t::TRANSIENT_LOCAL,
                       enforceUnicast);
  }

  Reader *createReader(Participant &part, const char *topicName,
                       const char *typeName, bool reliable,
                       ip4_addr_t mcastaddress = {0}) {
    return createReader(part, topicName, typeName, reliable,
                       reliable ? ReliabilityKind_t::RELIABLE : ReliabilityKind_t::BEST_EFFORT,
                       DurabilityKind_t::VOLATILE,
                       mcastaddress);
  }

  Writer *writerExists(Participant &part, const char *topicName,
                       const char *typeName, bool reliable);
  Reader *readerExists(Participant &part, const char *topicName,
                       const char *typeName, bool reliable);

private:
  friend class SizeInspector;
  ThreadPool m_threadPool;
  UdpDriver m_transport;
  std::array<Participant, Config::MAX_NUM_PARTICIPANTS> m_participants;
  const uint8_t PARTICIPANT_START_ID = 0;
  ParticipantId_t m_nextParticipantId = PARTICIPANT_START_ID;

  std::array<StatelessWriter, Config::NUM_STATELESS_WRITERS> m_statelessWriters;
  std::array<StatelessReader, Config::NUM_STATELESS_READERS> m_statelessReaders;
  uint8_t m_numStatelessWriters = 0;
  uint8_t m_numStatelessReaders = 0;
  std::array<StatefulReader, Config::NUM_STATEFUL_READERS> m_statefulReaders;
  uint8_t m_numStatefulReaders = 0;
  std::array<StatefulWriter, Config::NUM_STATEFUL_WRITERS> m_statefulWriters;
  uint8_t m_numStatefulWriters = 0;

  bool m_initComplete = false;
  std::atomic<bool> m_qosMonitorRunning{false};
  sys_thread_t m_qosMonitorThread{};

  void receiveCallback(const PacketInfo &packet);
  GuidPrefix_t generateGuidPrefix(ParticipantId_t id) const;
  void createBuiltinWritersAndReaders(Participant &part);
  void registerPort(const Participant &part);
  void registerMulticastPort(FullLengthLocator mcastLocator);
  static void receiveJumppad(void *callee, const PacketInfo &packet);
  static void qosMonitorJumppad(void *callee);
  void qosMonitorLoop();

public:
  // Performance monitoring
  const ThreadPool::RxStats& getRxStats() const { return m_threadPool.getRxStats(); }
  void resetRxStats() { m_threadPool.resetRxStats(); }
  void printRxStats() const { m_threadPool.printRxStats(); }
};
} // namespace rtps

#endif // RTPS_DOMAIN_H
