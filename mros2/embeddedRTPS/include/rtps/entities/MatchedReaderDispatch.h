#ifndef RTPS_MATCHED_READER_DISPATCH_H
#define RTPS_MATCHED_READER_DISPATCH_H

#include <array>
#include <cstddef>
#include <cstdint>

namespace rtps {

template <class ReaderType, std::size_t Capacity, class Matches,
          class Deliver>
uint32_t dispatchMatchedReaders(
    const std::array<ReaderType *, Capacity> &readers, uint32_t readerCount,
    Matches matches, Deliver deliver) {
  const uint32_t boundedCount =
      readerCount < Capacity ? readerCount : static_cast<uint32_t>(Capacity);
  uint32_t routed = 0;
  for (uint32_t index = 0; index < boundedCount; ++index) {
    ReaderType *reader = readers[index];
    if (reader != nullptr && matches(*reader)) {
      deliver(*reader);
      ++routed;
    }
  }
  return routed;
}

template <class ReaderType, std::size_t Capacity, class Eligible>
ReaderType *selectSoleEligibleReader(
    const std::array<ReaderType *, Capacity> &readers, uint32_t readerCount,
    Eligible eligible) {
  const uint32_t boundedCount =
      readerCount < Capacity ? readerCount : static_cast<uint32_t>(Capacity);
  ReaderType *selected = nullptr;
  for (uint32_t index = 0; index < boundedCount; ++index) {
    ReaderType *reader = readers[index];
    if (reader == nullptr || !eligible(*reader)) {
      continue;
    }
    if (selected != nullptr) {
      return nullptr;
    }
    selected = reader;
  }
  return selected;
}

}  // namespace rtps

#endif  // RTPS_MATCHED_READER_DISPATCH_H
