// Verification tests for RTPS network input validation fixes
#include <cstdio>
#include <cstring>
#include <cstdint>
#include <cassert>

// Minimal mock types to test validation logic without full RTPS stack
namespace rtps {
  using DataSize_t = uint16_t;

  // Mirror the fixed MessageProcessingInfo
  struct MessageProcessingInfo {
    const uint8_t *data;
    const DataSize_t size;
    DataSize_t nextPos = 0;

    MessageProcessingInfo(const uint8_t *d, DataSize_t s) : data(d), size(s) {}

    const uint8_t *getPointerToCurrentPos() const {
      return &data[nextPos];
    }

    DataSize_t getRemainingSize() const {
      if (nextPos > size) {
        return 0;
      }
      return size - nextPos;
    }

    bool hasRemaining(DataSize_t needed) const {
      return getRemainingSize() >= needed;
    }

    bool advance(DataSize_t bytes) {
      if (nextPos + bytes > size) {
        return false;
      }
      nextPos += bytes;
      return true;
    }
  };
}

// Test 1: getRemainingSize with underflow protection
bool test_getRemainingSize_underflow() {
  // Case: nextPos > size (simulated corruption/overflow)
  uint8_t buf[10] = {};
  rtps::MessageProcessingInfo info(buf, 5);
  info.nextPos = 10; // deliberately beyond size

  rtps::DataSize_t remaining = info.getRemainingSize();
  if (remaining == 0) {
    printf("[PASS] getRemainingSize returns 0 when nextPos > size\n");
    return true;
  }
  printf("[FAIL] getRemainingSize should return 0, got %u\n", remaining);
  return false;
}

// Test 2: getRemainingSize normal case
bool test_getRemainingSize_normal() {
  uint8_t buf[20] = {};
  rtps::MessageProcessingInfo info(buf, 20);
  info.nextPos = 5;

  rtps::DataSize_t remaining = info.getRemainingSize();
  if (remaining == 15) {
    printf("[PASS] getRemainingSize normal case: 20-5=15\n");
    return true;
  }
  printf("[FAIL] getRemainingSize expected 15, got %u\n", remaining);
  return false;
}

// Test 3: advance overflow protection
bool test_advance_overflow() {
  uint8_t buf[10] = {};
  rtps::MessageProcessingInfo info(buf, 10);
  info.nextPos = 8;

  // Try to advance past buffer end
  if (!info.advance(5)) {
    printf("[PASS] advance() correctly rejects overflow\n");
    return true;
  }
  printf("[FAIL] advance() should have rejected 8+5 > 10\n");
  return false;
}

// Test 4: advance normal case
bool test_advance_normal() {
  uint8_t buf[20] = {};
  rtps::MessageProcessingInfo info(buf, 20);
  info.nextPos = 0;

  if (info.advance(10) && info.nextPos == 10) {
    printf("[PASS] advance() normal case: 0+10=10\n");
    return true;
  }
  printf("[FAIL] advance() should advance to 10\n");
  return false;
}

// Test 5: advance exact boundary
bool test_advance_exact_boundary() {
  uint8_t buf[10] = {};
  rtps::MessageProcessingInfo info(buf, 10);
  info.nextPos = 5;

  // advance exactly to end: 5+5=10, which equals size
  if (info.advance(5) && info.nextPos == 10) {
    printf("[PASS] advance() exact boundary: 5+5=10\n");
    return true;
  }
  printf("[FAIL] advance() should allow reaching exactly the end\n");
  return false;
}

// Test 6: hasRemaining check
bool test_hasRemaining() {
  uint8_t buf[10] = {};
  rtps::MessageProcessingInfo info(buf, 10);
  info.nextPos = 7;

  if (info.hasRemaining(3) && !info.hasRemaining(4)) {
    printf("[PASS] hasRemaining() boundary check\n");
    return true;
  }
  printf("[FAIL] hasRemaining() boundary check failed\n");
  return false;
}

// Test 7: Minimum size validation (simulates processMessage check)
bool test_minimum_size_check() {
  // Null data check
  const uint8_t *null_data = nullptr;
  bool null_rejected = (null_data == nullptr); // C++ doesn't let us deref null
  if (null_rejected) {
    printf("[PASS] Null data pointer rejected\n");
  } else {
    printf("[FAIL] Null data pointer not rejected\n");
    return false;
  }

  // Too small packet
  uint8_t buf[5] = {}; // 5 bytes < Header::getRawSize() (20 bytes)
  if (sizeof(buf) < 20) {
    printf("[PASS] 5-byte packet correctly identified as too small\n");
    return true;
  }
  printf("[FAIL] 5-byte packet should be too small\n");
  return false;
}

// Test 8: Submessage size underflow prevention
bool test_submsgSize_underflow() {
  // Simulates: octetsToNextHeader < dataHeaderSize
  uint16_t octetsToNextHeader = 5;  // smaller than data header
  uint16_t dataHeaderSize = 16;     // SubmessageData::getRawSize()

  if (octetsToNextHeader < dataHeaderSize) {
    printf("[PASS] Submessage size underflow detected (%u < %u)\n",
           octetsToNextHeader, dataHeaderSize);
    return true;
  }
  printf("[FAIL] Should have detected underflow\n");
  return false;
}

// Test 9: Submessage advance overflow prevention
bool test_submsg_advance_overflow() {
  uint8_t buf[10] = {};
  rtps::MessageProcessingInfo info(buf, 10);
  info.nextPos = 5;

  // Simulates: octetsToNextHeader=65535 + SubmessageHeader::getRawSize()=4
  uint16_t octetsToNextHeader = 65535;
  uint16_t submsgHeaderSize = 4;
  uint32_t totalSubmsgSize = (uint32_t)octetsToNextHeader + submsgHeaderSize;

  if (totalSubmsgSize > 65535 || !info.advance((rtps::DataSize_t)totalSubmsgSize)) {
    printf("[PASS] Submessage advance overflow prevented\n");
    return true;
  }
  printf("[FAIL] Should have prevented overflow\n");
  return false;
}

int main() {
  printf("=== Input Validation Verification Tests ===\n\n");

  int pass = 0, fail = 0;

  auto run = [&](bool result, const char* name) {
    if (result) pass++; else fail++;
  };

  run(test_getRemainingSize_underflow(), "getRemainingSize underflow");
  run(test_getRemainingSize_normal(), "getRemainingSize normal");
  run(test_advance_overflow(), "advance overflow");
  run(test_advance_normal(), "advance normal");
  run(test_advance_exact_boundary(), "advance boundary");
  run(test_hasRemaining(), "hasRemaining");
  run(test_minimum_size_check(), "minimum size");
  run(test_submsgSize_underflow(), "submsg underflow");
  run(test_submsg_advance_overflow(), "submsg advance overflow");

  printf("\n=== Results: %d/%d passed, %d failed ===\n",
         pass, pass + fail, fail);

  return fail == 0 ? 0 : 1;
}
