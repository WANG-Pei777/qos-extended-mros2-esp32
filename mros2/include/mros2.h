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
    // Returns true only when the local RTPS Writer accepts the sample.
    // This is not a remote-delivery acknowledgment. A false result means the
    // sample was not admitted (for example because of history/resource or
    // allocation limits); inspect the publisher counters for diagnosis.
    template <class T>
    bool publish(T &msg);
    bool matched() const;
    uint32_t matched_reader_count() const;
    uint32_t publish_attempt_count() const;
    uint32_t publish_accept_count() const;
    uint32_t resource_reject_count() const;
    uint32_t allocation_failure_count() const;
    uint32_t local_send_failure_count() const;
    uint32_t control_send_failure_count() const;
    uint32_t history_depth() const;
    uint32_t history_count() const;
    // Saturating retained RTPS serializedPayload bytes, including CDR
    // encapsulation/padding but excluding RTPS/network and allocation overhead.
    uint32_t history_bytes() const;
    uint32_t acknack_receive_count() const;
    uint32_t acknack_accept_count() const;
    uint32_t acknack_stale_drop_count() const;
    uint32_t acknack_unknown_reader_drop_count() const;
    uint32_t acknack_best_effort_drop_count() const;
    uint32_t acknack_gap_response_count() const;
    uint32_t acknack_data_response_count() const;
    uint32_t acknack_deferred_response_count() const;
    bool set_transmission_held(bool held);

  private:
    friend class Node;
    rtps::Writer *writer_ = nullptr;
  };

  class Subscriber
  {
  public:
    std::string topic_name;
    bool matched() const;
    uint32_t matched_writer_count() const;
    bool writer_alive() const;
    uint32_t deadline_missed_count() const;
    uint32_t received_count() const;
    uint32_t accepted_before_match_count() const;
    uint32_t out_of_order_drop_count() const;
    uint32_t unmatched_writer_drop_count() const;
    uint32_t unsupported_payload_drop_count() const;
    uint32_t gap_received_count() const;
    uint32_t control_send_failure_count() const;
    uint32_t liveliness_lost_count() const;
    uint32_t liveliness_recovered_count() const;
    void check_liveliness();
    template <class T>
    static void callback_handler(
        void *callee,
        const rtps::ReaderCacheChange &cacheChange);
    template <class T>
    static bool payload_validator(
        void *callee,
        const rtps::ReaderCacheChange &cacheChange);

  private:
    friend class Node;
    rtps::Reader *reader_ = nullptr;
  };

  void spin();

  // Performance monitoring for receive path
  void printRxStats();
  void resetRxStats();
  bool publisher_matched();
  bool publisher_has_matched_reader();
  uint32_t publisher_matched_reader_count();
  bool subscriber_matched();
  bool subscriber_writer_alive();
  uint32_t publisher_deadline_missed_count();
  uint32_t publisher_lifespan_drop_count();
  uint32_t publisher_publish_attempt_count();
  uint32_t publisher_publish_accept_count();
  uint32_t publisher_resource_reject_count();
  uint32_t publisher_allocation_failure_count();
  uint32_t publisher_local_send_failure_count();
  uint32_t publisher_control_send_failure_count();
  uint32_t publisher_history_depth();
  uint32_t publisher_history_count();
  uint32_t publisher_history_bytes();
  uint32_t publisher_acknack_receive_count();
  uint32_t publisher_acknack_accept_count();
  uint32_t publisher_acknack_stale_drop_count();
  uint32_t publisher_acknack_unknown_reader_drop_count();
  uint32_t publisher_acknack_best_effort_drop_count();
  uint32_t publisher_acknack_gap_response_count();
  uint32_t publisher_acknack_data_response_count();
  uint32_t publisher_acknack_deferred_response_count();
  bool publisher_set_transmission_held(bool held);
  uint32_t subscriber_deadline_missed_count();
  uint32_t subscriber_received_count();
  uint32_t subscriber_accepted_before_match_count();
  uint32_t subscriber_out_of_order_drop_count();
  uint32_t subscriber_unmatched_writer_drop_count();
  uint32_t subscriber_unsupported_payload_drop_count();
  uint32_t subscriber_gap_received_count();
  uint32_t subscriber_control_send_failure_count();
  uint32_t subscriber_liveliness_lost_count();
  uint32_t subscriber_liveliness_recovered_count();
  void subscriber_check_liveliness();
  bool register_publisher_deadline_missed_callback(void (*cb)(void *),
                                                    void *arg);
  bool register_subscriber_deadline_missed_callback(void (*cb)(void *),
                                                     void *arg);
  bool register_subscriber_liveliness_lost_callback(void (*cb)(void *),
                                                     void *arg);
  bool register_subscriber_liveliness_recovered_callback(void (*cb)(void *),
                                                          void *arg);

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
