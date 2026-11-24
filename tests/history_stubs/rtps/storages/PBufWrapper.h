#ifndef HISTORY_TEST_PBUFWRAPPER_H
#define HISTORY_TEST_PBUFWRAPPER_H

#include "rtps/common/types.h"

#include <cstddef>
#include <cstdint>
#include <utility>

namespace rtps {

class PBufWrapper {
public:
  PBufWrapper() = default;
  PBufWrapper(const PBufWrapper &) = delete;
  PBufWrapper &operator=(const PBufWrapper &) = delete;

  PBufWrapper(PBufWrapper &&other) noexcept { moveFrom(other); }

  PBufWrapper &operator=(PBufWrapper &&other) noexcept {
    if (this != &other) {
      release();
      moveFrom(other);
    }
    return *this;
  }

  ~PBufWrapper() { release(); }

  bool reserve(DataSize_t length) {
    if (failNextReserve_) {
      failNextReserve_ = false;
      return false;
    }
    if (length > capacity_) {
      liveBytes_ += length - capacity_;
      capacity_ = length;
    }
    return true;
  }

  bool append(const uint8_t *, DataSize_t length) {
    if (failNextAppend_) {
      failNextAppend_ = false;
      return false;
    }
    if (used_ + length > capacity_) {
      return false;
    }
    used_ += length;
    return true;
  }

  DataSize_t spaceUsed() const { return used_; }

  static void resetTestState() {
    liveBytes_ = 0;
    failNextReserve_ = false;
    failNextAppend_ = false;
  }

  static void failNextReserve() { failNextReserve_ = true; }
  static void failNextAppend() { failNextAppend_ = true; }
  static std::size_t liveBytes() { return liveBytes_; }

private:
  void release() {
    liveBytes_ -= capacity_;
    capacity_ = 0;
    used_ = 0;
  }

  void moveFrom(PBufWrapper &other) {
    capacity_ = other.capacity_;
    used_ = other.used_;
    other.capacity_ = 0;
    other.used_ = 0;
  }

  DataSize_t capacity_ = 0;
  DataSize_t used_ = 0;

  static inline std::size_t liveBytes_ = 0;
  static inline bool failNextReserve_ = false;
  static inline bool failNextAppend_ = false;
};

}  // namespace rtps

#endif
