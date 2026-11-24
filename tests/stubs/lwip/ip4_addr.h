#ifndef QOS_TEST_LWIP_IP4_ADDR_H
#define QOS_TEST_LWIP_IP4_ADDR_H

#include <stdint.h>

typedef struct ip4_addr {
  uint32_t addr;
} ip4_addr_t;

static inline int ip4_addr_cmp(const ip4_addr_t *left,
                               const ip4_addr_t *right) {
  return left->addr == right->addr;
}

#endif // QOS_TEST_LWIP_IP4_ADDR_H
