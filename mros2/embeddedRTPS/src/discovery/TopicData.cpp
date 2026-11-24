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
#include "rtps/discovery/TopicData.h"
#include "rtps/messages/MessageTypes.h"
#include <cstring>

using rtps::TopicData;
using rtps::TopicDataCompressed;
using rtps::SMElement::ParameterId;

bool TopicData::matchesTopicOf(const TopicData &other) {
  return strcmp(this->topicName, other.topicName) == 0 &&
         strcmp(this->typeName, other.typeName) == 0;
}

bool TopicData::readFromUcdrBuffer(ucdrBuffer &buffer) {

  while (ucdr_buffer_remaining(&buffer) >= 4) {
    ParameterId pid;
    uint16_t length;
    FullLengthLocator uLoc;
    ucdr_deserialize_uint16_t(&buffer, reinterpret_cast<uint16_t *>(&pid));
    ucdr_deserialize_uint16_t(&buffer, &length);

    if (ucdr_buffer_remaining(&buffer) < length) {
      return false;
    }

    switch (pid) {
    case ParameterId::PID_ENDPOINT_GUID:
      if (length != sizeof(GuidPrefix_t::id) + 4) {
        return false;
      }
      ucdr_deserialize_array_uint8_t(&buffer, endpointGuid.prefix.id.data(),
                                     endpointGuid.prefix.id.size());
      ucdr_deserialize_array_uint8_t(&buffer,
                                     endpointGuid.entityId.entityKey.data(),
                                     endpointGuid.entityId.entityKey.size());
      ucdr_deserialize_uint8_t(&buffer, reinterpret_cast<uint8_t *>(
                                            &endpointGuid.entityId.entityKind));
      break;
    case ParameterId::PID_RELIABILITY:
      if (length != 12 ||
          !ucdr_deserialize_uint32_t(
              &buffer, reinterpret_cast<uint32_t *>(&reliabilityKind))) {
        return false;
      }
      buffer.iterator += 8;
      buffer.last_data_size = 1;
      break;
    case ParameterId::PID_DURABILITY:
      if (length != 4 ||
          !ucdr_deserialize_uint32_t(
              &buffer, reinterpret_cast<uint32_t *>(&durabilityKind))) {
        return false;
      }
      break;
    case ParameterId::PID_HISTORY:
      if (length != 8 ||
          !ucdr_deserialize_uint32_t(&buffer, &historyKind) ||
          !ucdr_deserialize_uint32_t(&buffer, &historyDepth)) {
        return false;
      }
      break;
    case ParameterId::PID_RESOURCE_LIMITS: {
      int32_t wireMaxSamples;
      int32_t ignored;
      if (length != 12 ||
          !ucdr_deserialize_int32_t(&buffer, &wireMaxSamples) ||
          !ucdr_deserialize_int32_t(&buffer, &ignored) ||
          !ucdr_deserialize_int32_t(&buffer, &ignored)) {
        return false;
      }
      if (wireMaxSamples == -1) {
        maxSamples = 0; // mros2 local convention: no additional limit
      } else if (wireMaxSamples > 0) {
        maxSamples = static_cast<uint32_t>(wireMaxSamples);
      } else {
        return false;
      }
      break;
    }
    case ParameterId::PID_DEADLINE:
      if (length != 8 ||
          !ucdr_deserialize_uint32_t(&buffer, &deadlineSec) ||
          !ucdr_deserialize_uint32_t(&buffer, &deadlineFraction)) {
        return false;
      }
      break;
    case ParameterId::PID_LIFESPAN:
      if (length != 8 ||
          !ucdr_deserialize_uint32_t(&buffer, &lifespanSec) ||
          !ucdr_deserialize_uint32_t(&buffer, &lifespanFraction)) {
        return false;
      }
      break;
    case ParameterId::PID_LIVELINESS:
      if (length != 12) {
        return false;
      }
      buffer.iterator += 4;
      buffer.last_data_size = 1;
      if (!ucdr_deserialize_uint32_t(&buffer, &livelinessSec) ||
          !ucdr_deserialize_uint32_t(&buffer, &livelinessFraction)) {
        return false;
      }
      break;
    case ParameterId::PID_SENTINEL:
      return length == 0;
    case ParameterId::PID_TOPIC_NAME: {
      uint32_t topicNameLength;
      if (length < 4 ||
          !ucdr_deserialize_uint32_t(&buffer, &topicNameLength) ||
          topicNameLength == 0 ||
          topicNameLength > Config::MAX_TOPICNAME_LENGTH ||
          topicNameLength > static_cast<uint32_t>(length - 4) ||
          !ucdr_deserialize_array_char(&buffer, topicName, topicNameLength) ||
          topicName[topicNameLength - 1] != '\0') {
        return false;
      }
      const uint32_t padding = length - 4 - topicNameLength;
      buffer.iterator += padding;
      buffer.last_data_size = 1;
      break;
    }
    case ParameterId::PID_TYPE_NAME: {
      uint32_t typeNameLength;
      if (length < 4 ||
          !ucdr_deserialize_uint32_t(&buffer, &typeNameLength) ||
          typeNameLength == 0 ||
          typeNameLength > Config::MAX_TYPENAME_LENGTH ||
          typeNameLength > static_cast<uint32_t>(length - 4) ||
          !ucdr_deserialize_array_char(&buffer, typeName, typeNameLength) ||
          typeName[typeNameLength - 1] != '\0') {
        return false;
      }
      const uint32_t padding = length - 4 - typeNameLength;
      buffer.iterator += padding;
      buffer.last_data_size = 1;
      break;
    }
    case ParameterId::PID_UNICAST_LOCATOR:
      if (length != sizeof(FullLengthLocator) ||
          !uLoc.readFromUcdrBuffer(buffer)) {
        return false;
      }
      if (uLoc.kind == LocatorKind_t::LOCATOR_KIND_UDPv4 &&
          uLoc.isSameSubnet()) {
        unicastLocator = uLoc;
      }
      break;
    case ParameterId::PID_MULTICAST_LOCATOR:
      if (length != sizeof(FullLengthLocator) ||
          !multicastLocator.readFromUcdrBuffer(buffer)) {
        return false;
      }
      break;
    default:
      buffer.iterator += length;
      buffer.last_data_size = 1;
    }

    uint32_t alignment = ucdr_buffer_alignment(&buffer, 4);
    buffer.iterator += alignment;
    buffer.last_data_size = 4; // 4 Byte alignment per element
  }
  return ucdr_buffer_remaining(&buffer) == 0;
}

bool TopicData::serializeIntoUcdrBuffer(ucdrBuffer &buffer) const {
  const uint16_t guidSize = sizeof(GuidPrefix_t::id) + 4;

#if SUPPRESS_UNICAST
  if (multicastLocator.kind != LocatorKind_t::LOCATOR_KIND_UDPv4) {
#endif
    ucdr_serialize_uint16_t(&buffer, ParameterId::PID_UNICAST_LOCATOR);
    ucdr_serialize_uint16_t(&buffer, sizeof(FullLengthLocator));
    ucdr_serialize_array_uint8_t(
        &buffer, reinterpret_cast<const uint8_t *>(&unicastLocator),
        sizeof(FullLengthLocator));
#if SUPPRESS_UNICAST
  }
#endif

  if (multicastLocator.kind == LocatorKind_t::LOCATOR_KIND_UDPv4) {
    ucdr_serialize_uint16_t(&buffer, ParameterId::PID_MULTICAST_LOCATOR);
    ucdr_serialize_uint16_t(&buffer, sizeof(FullLengthLocator));
    ucdr_serialize_array_uint8_t(
        &buffer, reinterpret_cast<const uint8_t *>(&multicastLocator),
        sizeof(FullLengthLocator));
  }

  // It's a 32 bit instead of 16 because it seems like the field is padded.
  const auto lenTopicName =
      static_cast<uint32_t>(strlen(topicName) + 1); // + \0
  uint16_t topicAlignment = 0;
  if (lenTopicName % 4 != 0) {
    topicAlignment = static_cast<uint8_t>(4 - (lenTopicName % 4));
  }
  const auto totalLengthTopicNameField = static_cast<uint16_t>(
      sizeof(lenTopicName) + lenTopicName + topicAlignment);
  ucdr_serialize_uint16_t(&buffer, ParameterId::PID_TOPIC_NAME);
  ucdr_serialize_uint16_t(&buffer, totalLengthTopicNameField);
  ucdr_serialize_uint32_t(&buffer, lenTopicName);
  ucdr_serialize_array_char(&buffer, topicName, lenTopicName);
  ucdr_align_to(&buffer, 4);

  // It's a 32 bit instead of 16 because it seems like the field is padded.
  const auto lenTypeName = static_cast<uint32_t>(strlen(typeName) + 1); // + \0
  uint16_t typeAlignment = 0;
  if (lenTypeName % 4 != 0) {
    typeAlignment = static_cast<uint8_t>(4 - (lenTypeName % 4));
  }
  const auto totalLengthTypeNameField =
      static_cast<uint16_t>(sizeof(lenTypeName) + lenTypeName + typeAlignment);

  ucdr_serialize_uint16_t(&buffer, ParameterId::PID_TYPE_NAME);
  ucdr_serialize_uint16_t(&buffer, totalLengthTypeNameField);
  ucdr_serialize_uint32_t(&buffer, lenTypeName);
  ucdr_serialize_array_char(&buffer, typeName, lenTypeName);
  ucdr_align_to(&buffer, 4);

  ucdr_serialize_uint16_t(&buffer, ParameterId::PID_KEY_HASH);
  ucdr_serialize_uint16_t(&buffer, guidSize);
  ucdr_serialize_array_uint8_t(&buffer, endpointGuid.prefix.id.data(),
                               endpointGuid.prefix.id.size());
  ucdr_serialize_array_uint8_t(&buffer, endpointGuid.entityId.entityKey.data(),
                               endpointGuid.entityId.entityKey.size());
  ucdr_serialize_uint8_t(
      &buffer, static_cast<uint8_t>(endpointGuid.entityId.entityKind));

  ucdr_serialize_uint16_t(&buffer, ParameterId::PID_ENDPOINT_GUID);
  ucdr_serialize_uint16_t(&buffer, guidSize);
  ucdr_serialize_array_uint8_t(&buffer, endpointGuid.prefix.id.data(),
                               endpointGuid.prefix.id.size());
  ucdr_serialize_array_uint8_t(&buffer, endpointGuid.entityId.entityKey.data(),
                               endpointGuid.entityId.entityKey.size());
  ucdr_serialize_uint8_t(
      &buffer, static_cast<uint8_t>(endpointGuid.entityId.entityKind));

  const uint8_t unidentifiedOffset = 8;
  ucdr_serialize_uint16_t(&buffer, ParameterId::PID_RELIABILITY);
  ucdr_serialize_uint16_t(&buffer,
                          sizeof(ReliabilityKind_t) + unidentifiedOffset);
  ucdr_serialize_uint32_t(&buffer, static_cast<uint32_t>(reliabilityKind));
  ucdr_serialize_uint32_t(&buffer, 0); // unidentified additional value
  ucdr_serialize_uint32_t(&buffer, 0); // unidentified additional value

  ucdr_serialize_uint16_t(&buffer, ParameterId::PID_DURABILITY);
  ucdr_serialize_uint16_t(&buffer, sizeof(DurabilityKind_t));
  ucdr_serialize_uint32_t(&buffer, static_cast<uint32_t>(durabilityKind));

  // PID_DEADLINE - use the actual QoS value.
  ucdr_serialize_uint16_t(&buffer, ParameterId::PID_DEADLINE);
  ucdr_serialize_uint16_t(&buffer, 8);
  ucdr_serialize_uint32_t(&buffer, deadlineSec);
  ucdr_serialize_uint32_t(&buffer, deadlineFraction);

  // PID_LIFESPAN
  ucdr_serialize_uint16_t(&buffer, ParameterId::PID_LIFESPAN);
  ucdr_serialize_uint16_t(&buffer, 8);
  ucdr_serialize_uint32_t(&buffer, lifespanSec);
  ucdr_serialize_uint32_t(&buffer, lifespanFraction);

  // PID_LIVELINESS - lease duration
  ucdr_serialize_uint16_t(&buffer, ParameterId::PID_LIVELINESS);
  ucdr_serialize_uint16_t(&buffer, 12);      // kind(4) + duration(8)
  ucdr_serialize_uint32_t(&buffer, 0);       // AUTOMATIC
  ucdr_serialize_uint32_t(&buffer, livelinessSec);
  ucdr_serialize_uint32_t(&buffer, livelinessFraction);

  // PID_HISTORY - kind + depth
  ucdr_serialize_uint16_t(&buffer, ParameterId::PID_HISTORY);
  ucdr_serialize_uint16_t(&buffer, 8);
  ucdr_serialize_uint32_t(&buffer, historyKind);
  ucdr_serialize_uint32_t(&buffer, historyDepth);

  // PID_RESOURCE_LIMITS - DDS standard fields are sample/instance counts.
  // This project also tracks maxBytes locally; maxBytes is not represented by
  // this standard PID and remains an ESP32-local limit.
  ucdr_serialize_uint16_t(&buffer, ParameterId::PID_RESOURCE_LIMITS);
  ucdr_serialize_uint16_t(&buffer, 12);
  ucdr_serialize_int32_t(
      &buffer, maxSamples == 0 ? -1 : static_cast<int32_t>(maxSamples));
  ucdr_serialize_int32_t(&buffer, -1);
  ucdr_serialize_int32_t(&buffer, -1);

  ucdr_serialize_uint16_t(&buffer, ParameterId::PID_SENTINEL);
  ucdr_serialize_uint16_t(&buffer, 0);

  return !ucdr_buffer_has_error(&buffer);
}

bool TopicDataCompressed::matchesTopicOf(const TopicData &other) const {
  return (hashCharArray(other.topicName, sizeof(other.topicName)) ==
              topicHash &&
          hashCharArray(other.typeName, sizeof(other.typeName)) == typeHash);
}
