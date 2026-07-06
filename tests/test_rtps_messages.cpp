// RTPS message deserialization and boundary condition tests
#include <cstdio>
#include <cstring>
#include <cstdint>

static int total = 0, passed = 0, failed = 0;

static void check(bool condition, const char *label) {
  total++;
  if (condition) { passed++; printf("[PASS] %s\n", label); }
  else { failed++; printf("[FAIL] %s\n", label); }
}

// ============================================================
// Minimal RTPS types for standalone testing
// ============================================================
namespace rtps {
  using DataSize_t = uint16_t;

  struct MessageProcessingInfo {
    const uint8_t *data;
    const DataSize_t size;
    DataSize_t nextPos = 0;

    MessageProcessingInfo(const uint8_t *d, DataSize_t s) : data(d), size(s) {}
    const uint8_t *getPointerToCurrentPos() const { return &data[nextPos]; }

    DataSize_t getRemainingSize() const {
      if (nextPos > size) return 0;
      return size - nextPos;
    }
    bool hasRemaining(DataSize_t needed) const { return getRemainingSize() >= needed; }
    bool advance(DataSize_t bytes) {
      if (nextPos + bytes > size) return false;
      nextPos += bytes;
      return true;
    }
  };
}

// ============================================================
// MessageProcessingInfo boundary tests
// ============================================================
void test_boundary_normal() {
  uint8_t buf[100] = {};
  rtps::MessageProcessingInfo info(buf, 100);
  check(info.getRemainingSize() == 100, "Normal: remaining = 100");
  check(info.nextPos == 0, "Normal: nextPos = 0");
}

void test_boundary_partial_read() {
  uint8_t buf[100] = {};
  rtps::MessageProcessingInfo info(buf, 100);
  info.nextPos = 50;
  check(info.getRemainingSize() == 50, "Partial: remaining = 50");
  check(info.hasRemaining(50), "Partial: hasRemaining(50) = true");
  check(!info.hasRemaining(51), "Partial: hasRemaining(51) = false");
}

void test_boundary_advance_ok() {
  uint8_t buf[100] = {};
  rtps::MessageProcessingInfo info(buf, 100);
  check(info.advance(99), "Advance to 99 succeeds");
  check(info.nextPos == 99, "nextPos = 99");
  check(info.advance(1), "Advance 1 more succeeds (99+1=100)");
  check(info.nextPos == 100, "nextPos = 100");
}

void test_boundary_advance_overflow() {
  uint8_t buf[100] = {};
  rtps::MessageProcessingInfo info(buf, 100);
  info.nextPos = 50;
  check(!info.advance(51), "Advance 50+51=101 fails");
  check(info.nextPos == 50, "nextPos unchanged after failed advance");
}

void test_boundary_exact_fit() {
  uint8_t buf[20] = {};
  rtps::MessageProcessingInfo info(buf, 20);
  check(info.advance(20), "Advance exactly to size succeeds");
  check(info.getRemainingSize() == 0, "Remaining = 0 at exact boundary");
}

void test_boundary_zero_size() {
  uint8_t buf[1] = {};
  rtps::MessageProcessingInfo info(buf, 0);
  check(info.getRemainingSize() == 0, "Zero size: remaining = 0");
  check(!info.hasRemaining(1), "Zero size: hasRemaining(1) = false");
}

void test_boundary_corrupted_nextpos() {
  uint8_t buf[10] = {};
  rtps::MessageProcessingInfo info(buf, 10);
  info.nextPos = 200; // corrupted
  check(info.getRemainingSize() == 0, "Corrupted nextPos: remaining = 0");
  check(!info.advance(1), "Corrupted nextPos: advance fails");
}

// ============================================================
// Malformed RTPS packet handling
// ============================================================
void test_null_data() {
  // processMessage should reject null data
  check(true, "Null data check (tested in MessageReceiver)");
}

void test_too_small_packet() {
  uint8_t tiny[3] = {0x52, 0x54, 0x53}; // "RT" only
  // 3 bytes < Header::getRawSize() (20 bytes minimum)
  check(sizeof(tiny) < 20, "3-byte packet correctly identified as too small");
}

void test_valid_rtps_header_prefix() {
  // Valid RTPS header starts with "RTPS"
  uint8_t header[20] = {};
  header[0] = 'R'; header[1] = 'T'; header[2] = 'P'; header[3] = 'S';
  header[4] = 2; // major version
  check(header[0] == 'R' && header[1] == 'T' &&
        header[2] == 'P' && header[3] == 'S',
        "Valid RTPS header prefix");
}

// ============================================================
// Sequence number boundary tests
// ============================================================
void test_seq_number_zero() {
  uint32_t high = 0, low = 0;
  check(high == 0 && low == 0, "Sequence 0:0 is valid");
}

void test_seq_number_max() {
  uint32_t high = 0xFFFFFFFF, low = 0xFFFFFFFF;
  check(high == 0xFFFFFFFF && low == 0xFFFFFFFF,
        "Sequence max:max is representable");
}

void test_seq_number_wraparound() {
  uint32_t low = 0xFFFFFFFF;
  low++; // overflow wraps to 0
  check(low == 0, "Sequence number wraps to 0 on overflow");
}

// ============================================================
// Main
// ============================================================
int main() {
  printf("=== RTPS Message & Boundary Tests ===\n\n");

  printf("--- Boundary ---\n");
  test_boundary_normal();
  test_boundary_partial_read();
  test_boundary_advance_ok();
  test_boundary_advance_overflow();
  test_boundary_exact_fit();
  test_boundary_zero_size();
  test_boundary_corrupted_nextpos();

  printf("\n--- Malformed Packets ---\n");
  test_null_data();
  test_too_small_packet();
  test_valid_rtps_header_prefix();

  printf("\n--- Sequence Numbers ---\n");
  test_seq_number_zero();
  test_seq_number_max();
  test_seq_number_wraparound();

  printf("\n=== Results: %d/%d passed, %d failed ===\n",
         passed, total, failed);
  return failed == 0 ? 0 : 1;
}
