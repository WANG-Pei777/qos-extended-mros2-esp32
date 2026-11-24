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

#ifndef RTPS_THREADPOOL_H
#define RTPS_THREADPOOL_H

#include "lwip/sys.h"
#include "rtps/communication/PacketInfo.h"
#include "rtps/communication/UdpDriver.h"
#include "rtps/config.h"
#include "rtps/storages/PBufWrapper.h"
#include "rtps/storages/ThreadSafeCircularBuffer.h"

#include <array>

namespace rtps {

class Writer;

class ThreadPool {
  // MessageReceiver owns one bounded DATA_FRAG reassembler and exposes a
  // completed slot only for the duration of synchronous Reader callbacks.
  // Parallel receive workers would require an explicit receiver/reassembly
  // lock or an owning completed-sample copy.
  static_assert(Config::THREAD_POOL_NUM_READERS == 1,
                "MessageReceiver requires exactly one receive worker");

public:
  using receiveJumppad_fp = void (*)(void *callee, const PacketInfo &packet);

  // Performance monitoring statistics
  struct RxStats {
    uint32_t packetsReceived = 0;
    uint32_t packetsDropped = 0;
    uint32_t queueDepthMax = 0;
    uint32_t chainedPbufs = 0;
  };

  ThreadPool(receiveJumppad_fp receiveCallback, void *callee);

  ~ThreadPool();

  bool startThreads();
  void stopThreads();

  void clearQueues();
  bool addWorkload(Writer *workload);
  bool addRetryWorkload(Writer *workload);
  bool addNewPacket(PacketInfo &&packet);

  static void readCallback(void *arg, udp_pcb *pcb, pbuf *p,
                           const ip_addr_t *addr, Ip4Port_t port);

  // Get performance statistics
  const RxStats& getRxStats() const { return m_rxStats; }
  void resetRxStats() { m_rxStats = {}; }
  void printRxStats() const;

private:
  receiveJumppad_fp m_receiveJumppad;
  void *m_callee;
  bool m_running = false;
  std::array<sys_thread_t, Config::THREAD_POOL_NUM_WRITERS> m_writers;
  std::array<sys_thread_t, Config::THREAD_POOL_NUM_READERS> m_readers;

  sys_sem_t m_readerNotificationSem;
  sys_sem_t m_writerNotificationSem;

  ThreadSafeCircularBuffer<Writer *, Config::THREAD_POOL_WORKLOAD_QUEUE_LENGTH>
      m_queueOutgoing;
  ThreadSafeCircularBuffer<Writer *, Config::THREAD_POOL_RETRY_QUEUE_LENGTH>
      m_queueRetry;
  ThreadSafeCircularBuffer<PacketInfo,
                           Config::THREAD_POOL_WORKLOAD_QUEUE_LENGTH>
      m_queueIncoming;

  RxStats m_rxStats;  // Performance monitoring statistics

  static void writerThreadFunction(void *arg);
  static void readerThreadFunction(void *arg);
  void doWriterWork();
  void doReaderWork();
};
} // namespace rtps

#endif // RTPS_THREADPOOL_H
