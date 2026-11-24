// Host-test override, force-included with `-include`.
// Keeps the lwIP-dependent transport headers (UdpDriver, UdpConnection,
// TcpipCoreLock) out of host builds by pre-defining their include guards and
// providing the two static helpers that Locator.h calls.
#ifndef RTPS_TEST_UDP_DRIVER_OVERRIDE_H
#define RTPS_TEST_UDP_DRIVER_OVERRIDE_H

#define RTPS_TCPIPCORELOCK_H
#define RTPS_UDPCONNECTION_H
#define RTPS_UDPDRIVER_H

#include "lwip/ip4_addr.h"

namespace rtps {
class TcpipCoreLock {};
class UdpDriver {
public:
  static bool isSameSubnet(ip4_addr_t) { return true; }
  static bool isMulticastAddress(ip4_addr_t) { return false; }
};
}  // namespace rtps

#endif  // RTPS_TEST_UDP_DRIVER_OVERRIDE_H
