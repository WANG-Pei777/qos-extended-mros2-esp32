#ifndef MROS2_MROS2_H
#define MROS2_MROS2_H

#include <string>
#include "rtps/rtps.h"
#ifndef __MBED__
#include "lwip.h"
#endif /* __MBED__ */
#include "mros2/logging.h"
#include "mros2/qos.h"  // QoS support

/* Statement to avoid link error */
#ifdef __cplusplus
extern void *__dso_handle;
#endif

namespace rtps
{
  namespace Config
  {
    extern std::array<uint8_t, 4> IP_ADDRESS;
  }
}

namespace mros2
{

  void init(int argc, char *argv[]);
  void shutdown();

#ifdef __cplusplus
  extern "C"
  {
#endif
    void mros2_init(void *arg);
#ifdef __cplusplus
  }
#endif

  class Node;
  class Publisher;
  class Subscriber;

  /* TODO: move to node.h/cpp? */
  class Node
  {
  public:
    static Node create_node(
        std::string node_name);

    // New API: accept the full QoSProfile structure.
    template <class T>
    Publisher create_publisher(
        const std::string& topic_name,
        const QoSProfile& qos);

    template <class T>
    Subscriber create_subscription(
        const std::string& topic_name,
        const QoSProfile& qos,
        void (*fp)(T *));

    // Backward-compatible API: accept an integer history depth.
    template <class T>
    Publisher create_publisher(
        std::string topic_name,
        int qos);

    template <class T>
    Subscriber create_subscription(
        std::string topic_name,
        int qos,
        void (*fp)(T *));

    std::string node_name;
    rtps::Participant *part;

  private:
  };

  class Publisher
  {
  public:
    std::string topic_name;
    template <class T>
    void publish(T &msg);
  };

  class Subscriber
  {
  public:
    std::string topic_name;
    template <class T>
    static void callback_handler(
        void *callee,
        const rtps::ReaderCacheChange &cacheChange);
    void (*cb_fp)(intptr_t);

  private:
  };

  void spin();

  // Performance monitoring for receive path
  void printRxStats();
  void resetRxStats();
  bool publisher_matched();
  bool subscriber_matched();
  bool subscriber_writer_alive();
  uint32_t publisher_deadline_missed_count();
  uint32_t publisher_lifespan_drop_count();
  uint32_t publisher_resource_reject_count();
  uint32_t publisher_history_depth();
  uint32_t publisher_history_count();
  uint32_t publisher_history_bytes();
  uint32_t subscriber_deadline_missed_count();
  uint32_t subscriber_received_count();
  uint32_t subscriber_accepted_before_match_count();
  uint32_t subscriber_out_of_order_drop_count();
  uint32_t subscriber_unmatched_writer_drop_count();
  uint32_t subscriber_liveliness_lost_count();
  uint32_t subscriber_liveliness_recovered_count();
  void subscriber_check_liveliness();

#ifdef __MBED__
  int setIPAddrRTPS(std::array<uint8_t, 4> ipaddr);
#endif /* __MBED__ */

} /* namespace mros2 */

#ifndef __MBED__
extern "C" int mros2_setIPAddrRTPS(uint32_t ipaddr);
#endif /* __MBED__ */

namespace message_traits
{
  template <class T>
  struct TypeName
  {
    static const char *value();
  };
} /* namespace message_traits */

#endif /* MROS2_MROS2_H */
