/* Host-side fragmentation capability declaration test. */

#include "rtps/entities/FragmentationCapability.h"

#include <cstdio>

int main() {
  if (!rtps::fragmentedTransientLocalReplaySupported()) {
    std::printf("[FAIL] fragmented transient-local replay is declared supported\n");
    return 1;
  }
  std::printf("[PASS] fragmented transient-local replay is declared supported\n");
  return 0;
}
