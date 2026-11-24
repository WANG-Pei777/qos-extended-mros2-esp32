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

#ifndef RTPS_READERPROXY_H
#define RTPS_READERPROXY_H

#include "rtps/common/types.h"
#include "rtps/discovery/ParticipantProxyData.h"

namespace rtps {
struct ReaderProxy {
  Guid_t remoteReaderGuid;
  LocatorIPv4 remoteLocator;
  LocatorIPv4 remoteMulticastLocator;
  bool useMulticast = false;
  bool suppressUnicast = false;
  bool unknown_eid = false;
  ReliabilityKind_t reliabilityKind = ReliabilityKind_t::RELIABLE;
  DurabilityKind_t durabilityKind = DurabilityKind_t::TRANSIENT_LOCAL;
  SequenceNumber_t firstRelevantSequence = SEQUENCENUMBER_UNKNOWN;
  bool noRelevantSequence = false;
  SequenceNumberSet ackNackSet;
  Count_t ackNackCount{0};
  bool hasAckNackCount = false;
  SequenceNumber_t acknowledgedThrough = SEQUENCENUMBER_UNKNOWN;
  bool hasAcknowledgedThrough = false;

  ReaderProxy() : remoteReaderGuid({GUIDPREFIX_UNKNOWN, ENTITYID_UNKNOWN}) {};
  ReaderProxy(const Guid_t &guid, const LocatorIPv4 &loc,
              ReliabilityKind_t reliability = ReliabilityKind_t::RELIABLE,
              DurabilityKind_t durability =
                  DurabilityKind_t::TRANSIENT_LOCAL)
      : remoteReaderGuid(guid), remoteLocator(loc),
        reliabilityKind(reliability), durabilityKind(durability),
        ackNackSet() {};
  ReaderProxy(const Guid_t &guid, const LocatorIPv4 &loc,
              const LocatorIPv4 &mcastloc,
              ReliabilityKind_t reliability = ReliabilityKind_t::RELIABLE,
              DurabilityKind_t durability =
                  DurabilityKind_t::TRANSIENT_LOCAL)
      : remoteReaderGuid(guid), remoteLocator(loc),
        remoteMulticastLocator(mcastloc), reliabilityKind(reliability),
        durabilityKind(durability), ackNackSet() {};
};

} // namespace rtps

#endif // RTPS_READERPROXY_H
