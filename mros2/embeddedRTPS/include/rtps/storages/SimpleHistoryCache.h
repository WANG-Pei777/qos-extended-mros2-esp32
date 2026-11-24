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

#ifndef PROJECT_SIMPLEHISTORYCACHE_H
#define PROJECT_SIMPLEHISTORYCACHE_H

#include "rtps/config.h"
#include "rtps/storages/CacheChange.h"

#include <array>
#include <type_traits>
#include <utility>

namespace rtps {

/**
 * Simple version of a history cache. It sets consecutive sequence numbers
 * automatically which allows an easy and fast approach of dropping acknowledged
 * changes. Furthermore, disposing of arbitrary changes is not possible.
 * However, this is in principle easy to add by changing the ChangeKind and
 * dropping it when passing it during deleting of other sequence numbers
 */
template <uint16_t SIZE> class SimpleHistoryCache {
public:
  SimpleHistoryCache() = default;

  bool isFull() const {
    uint16_t it = m_head;
    incrementIterator(it);
    return it == m_tail;
  }

  bool canAddChange() const {
    return m_lastUsedSequenceNumber.high < INT32_MAX ||
           m_lastUsedSequenceNumber.low < UINT32_MAX;
  }

  const CacheChange *addChange(CacheChange::SerializerCallback func,
                              FragDataSize_t size) {
    if (!func || size == 0) {
      return nullptr;
    }
    CacheChange change;
    change.kind = ChangeKind_t::ALIVE;
    change.sizeToBeSerialized = size;
    change.serializerCallback = std::move(func);
    return commitPreparedChange(std::move(change));
  }

  const CacheChange *addChange(const uint8_t *data, DataSize_t size) {
    if (data == nullptr || size == 0) {
      return nullptr;
    }
    CacheChange change;
    change.kind = ChangeKind_t::ALIVE;
    if (!change.data.reserve(size) || !change.data.append(data, size)) {
      return nullptr;
    }
    return commitPreparedChange(std::move(change));
  }

  const CacheChange *commitPreparedChange(CacheChange &&change) {
    if (!change.isAdmissibleToHistory() || !canAddChange()) {
      return nullptr;
    }
    change.sequenceNumber = ++m_lastUsedSequenceNumber;
    CacheChange *place = &m_buffer[m_head];
    incrementHead();
    *place = std::move(change);
    return place;
  }

  void removeUntilIncl(SequenceNumber_t sn) {
    if (m_head == m_tail) {
      return;
    }

    while (m_head != m_tail && m_buffer[m_tail].sequenceNumber <= sn) {
      m_buffer[m_tail] = CacheChange{};
      incrementTail();
    }
  }

  void dropOldest() { removeUntilIncl(getSeqNumMin()); }

  const CacheChange *getChangeBySN(SequenceNumber_t sn) const {
    SequenceNumber_t minSN = getSeqNumMin();
    if (sn < minSN || getSeqNumMax() < sn) {
      return nullptr;
    }
    static_assert(std::is_unsigned<decltype(sn.low)>::value,
                  "Underflow well defined");
    static_assert(sizeof(m_tail) <= sizeof(uint16_t), "Cast ist well defined");
    // We don't overtake head, therefore difference of sn is within same range
    // as iterators
    uint16_t pos = m_tail + static_cast<uint16_t>(sn.low - minSN.low);

    // Diff is smaller than the size of the array -> max one overflow
    if (pos >= m_buffer.size()) {
      pos -= static_cast<uint16_t>(m_buffer.size());
    }
    return &m_buffer[pos];
  }

  const SequenceNumber_t &getSeqNumMin() const {
    if (m_head == m_tail) {
      return SEQUENCENUMBER_UNKNOWN;
    } else {
      return m_buffer[m_tail].sequenceNumber;
    }
  }

  const SequenceNumber_t &getSeqNumMax() const {
    if (m_head == m_tail) {
      return SEQUENCENUMBER_UNKNOWN;
    } else {
      return m_lastUsedSequenceNumber;
    }
  }

  const SequenceNumber_t &getLastUsedSequenceNumber() const {
    return m_lastUsedSequenceNumber;
  }

  uint16_t getChangeCount() const {
    if (m_head >= m_tail) {
      return m_head - m_tail;
    } else {
      return static_cast<uint16_t>(m_buffer.size() - m_tail + m_head);
    }
  }

  uint64_t getTotalDataBytes() const {
    uint64_t total = 0;
    uint16_t it = m_tail;
    while (it != m_head) {
      const CacheChange &change = m_buffer[it];
      if (change.serializerCallback) {
        total += change.sizeToBeSerialized;
      } else {
        total += change.data.spaceUsed();
      }
      incrementIterator(it);
    }
    return total;
  }

  uint64_t getOldestDataBytes(uint16_t count) const {
    uint64_t total = 0;
    uint16_t it = m_tail;
    while (it != m_head && count-- != 0) {
      const CacheChange &change = m_buffer[it];
      total += change.serializerCallback ? change.sizeToBeSerialized
                                         : change.data.spaceUsed();
      incrementIterator(it);
    }
    return total;
  }

private:
  std::array<CacheChange, SIZE + 1> m_buffer{};
  uint16_t m_head = 0;
  uint16_t m_tail = 0;
  static_assert(SIZE < UINT16_MAX,
                "History ring including its sentinel must fit uint16_t");

  SequenceNumber_t m_lastUsedSequenceNumber{0, 0};

  inline void incrementHead() {
    incrementIterator(m_head);
    if (m_head == m_tail) {
      m_buffer[m_tail] = CacheChange{};
      incrementIterator(m_tail);
    }
  }

  inline void incrementIterator(uint16_t &iterator) const {
    ++iterator;
    if (iterator >= m_buffer.size()) {
      iterator = 0;
    }
  }

  inline void incrementTail() {
    if (m_head != m_tail) {
      incrementIterator(m_tail);
    }
  }

protected:
  // This constructor was created for unit testing
  explicit SimpleHistoryCache(SequenceNumber_t lastUsed)
      : SimpleHistoryCache() {
    m_lastUsedSequenceNumber = lastUsed;
  }
};
} // namespace rtps

#endif // PROJECT_SIMPLEHISTORYCACHE_H
