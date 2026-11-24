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

#ifndef PROJECT_CACHECHANGE_H
#define PROJECT_CACHECHANGE_H

#include <functional>
#include "rtps/common/types.h"
#include "rtps/storages/PBufWrapper.h"

namespace rtps {
struct CacheChange {
  enum class SerializerOperation {
    RESET,
    NEXT_FRAGMENT,
  };

  ChangeKind_t kind = ChangeKind_t::INVALID;
  SequenceNumber_t sequenceNumber = SEQUENCENUMBER_UNKNOWN;
  PBufWrapper data{};
  typedef std::pair<uint8_t *, DataSize_t> SerializedBuf;
  typedef std::function<SerializedBuf(SerializerOperation)> SerializerCallback;
  SerializerCallback serializerCallback = nullptr;
  FragDataSize_t sizeToBeSerialized = 0;
  uint32_t timestampMs = 0; // For Lifespan QoS: time of creation in ms

  CacheChange() = default;
  CacheChange(ChangeKind_t kind, SequenceNumber_t sequenceNumber)
      : kind(kind), sequenceNumber(sequenceNumber){};

  void resetSerializer() const {
    if (serializerCallback) {
      serializerCallback(SerializerOperation::RESET);
    }
  }

  bool hasValidSerializationContract() const {
    return serializerCallback ? sizeToBeSerialized != 0
                              : sizeToBeSerialized == 0;
  }

  bool isAdmissibleToHistory() const {
    const bool hasPayload =
        serializerCallback ? sizeToBeSerialized != 0 : data.spaceUsed() != 0;
    return kind != ChangeKind_t::INVALID && hasValidSerializationContract() &&
           hasPayload;
  }
};
} // namespace rtps

#endif // PROJECT_CACHECHANGE_H
