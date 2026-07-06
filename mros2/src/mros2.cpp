#include "mros2.h"
#include "mros2/error_handler.h"

#include <rtps/rtps.h>
#include <atomic>

#ifdef __MBED__
#include "mbed.h"
#else /* __MBED__ */
#include "mros2_config.h"
#include "cmsis_os.h"
#endif /* __MBED__ */

namespace mros2
{

  rtps::Domain *domain_ptr = NULL;
  rtps::Participant *part_ptr = NULL;
  rtps::Writer *pub_ptr = NULL;
  rtps::Reader *sub_ptr = NULL;

#define SUB_MSG_SIZE 4 // addr size
  osMessageQueueId_t subscriber_msg_queue_id;

  std::atomic<bool> completeNodeInit{false};
  uint8_t endpointId = 0;
  uint32_t subCbArray[10];

  uint8_t buf[100], frag_buf[64];
  uint8_t buf_index = 4;

  /* Callback function to set the boolean to true upon a match */
  void setTrue(void *args)
  {
    *static_cast<std::atomic<bool> *>(args) = true;
  }

  std::atomic<bool> subMatched{false};
  std::atomic<bool> pubMatched{false};

  void pubMatch(void *args)
  {
    if (args != nullptr) {
      *static_cast<std::atomic<bool> *>(args) = true;
    }
    MROS2_DEBUG("[MROS2LIB] publisher matched with remote subscriber");
  }

  void subMatch(void *args)
  {
    if (args != nullptr) {
      *static_cast<std::atomic<bool> *>(args) = true;
    }
    MROS2_DEBUG("[MROS2LIB] subscriber matched with remote publisher");
  }

/*
 *  Initialization of mROS 2 environment
 */
#ifdef __MBED__
  Thread *mros2_init_thread;
#endif /* __MBED__ */
  void init(int argc, char *argv[])
  {
    buf[0] = 0;
    buf[1] = 1;
    buf[2] = 0;
    buf[3] = 0;

#ifdef __MBED__
    mros2_init_thread = new Thread(osPriorityAboveNormal, 5000, nullptr, "mROS2Thread");
    mros2_init_thread->start(callback(mros2_init, (void *)NULL));
#else  /* __MBED__ */
    osThreadAttr_t attributes;

    attributes.name = "mROS2Thread",
    attributes.stack_size = 5000,
    attributes.priority = (osPriority_t)24,

    osThreadNew(mros2_init, NULL, (const osThreadAttr_t *)&attributes);
#endif /* __MBED__ */
  }

  void mros2_init(void *args)
  {
    osStatus_t ret;

    MROS2_DEBUG("[MROS2LIB] mros2_init task start");

#ifndef __MBED__
    MX_LWIP_Init();
    MROS2_DEBUG("[MROS2LIB] Initializing lwIP complete");
#endif /* __MBED__ */

    static rtps::Domain domain;
    domain_ptr = &domain;

#ifndef __MBED__
    subscriber_msg_queue_id = osMessageQueueNew(SUB_MSG_COUNT, SUB_MSG_SIZE, NULL);
    if (subscriber_msg_queue_id == NULL)
    {
      MROS2_ERROR("[MROS2LIB] ERROR: mROS2 init failed");
      return;
    }
#endif /* __MBED__ */

    /* wait until participant(node) is created */
    while (!completeNodeInit)
    {
      osDelay(100);
    }
    domain.completeInit();
    MROS2_DEBUG("[MROS2LIB] Initializing Domain complete");

    while (!subMatched && !pubMatched)
    {
      osDelay(1000);
    }

    MROS2_DEBUG("[MROS2LIB] mros2_init task end");

    ret = osThreadTerminate(NULL);
    if (ret != osOK)
    {
      MROS2_ERROR("[MROS2LIB] ERROR: mros2_init() task terminate error %d", ret);
    }
  }

  void shutdown()
  {
    MROS2_DEBUG("[MROS2LIB] shutdown() called");

    // 1. Reset endpoint pointers so no new publishes/subscribes happen
    pub_ptr = NULL;
    sub_ptr = NULL;

    // 2. Reset match state
    subMatched = false;
    pubMatched = false;

    // Note: We do NOT call domain_ptr->stop() because it terminates
    // FreeRTOS background threads which causes an abort.
    // On ESP32, the system is typically rebooted rather than cleanly shut down.
    // Background threads will be cleaned up on reboot.

    part_ptr = NULL;
    completeNodeInit = false;

    MROS2_DEBUG("[MROS2LIB] shutdown() complete");
  }

  /*
   *  Node functions
   */
  Node Node::create_node(std::string node_name)
  {
    MROS2_DEBUG("[MROS2LIB] create_node");
    MROS2_DEBUG("[MROS2LIB] start creating participant");

    while (domain_ptr == NULL)
    {
      osDelay(100);
    }

    Node node;
    node.part = domain_ptr->createParticipant();
    /* TODO: utilize node name */
    node.node_name = node_name;
    part_ptr = node.part;
    if (node.part == nullptr)
    {
      MROS2_ERROR("[MROS2LIB] ERROR: create_node() failed");
      handle_fatal_error(ErrorCode::NODE_CREATION_FAILED, "create_node");
    }
    completeNodeInit = true;

    MROS2_DEBUG("[MROS2LIB] successfully created participant");
    return node;
  }

  /*
   *  Publisher functions
   */
  template <class T>
  Publisher Node::create_publisher(const std::string& topic_name, const QoSProfile& qos)
  {
    if (!QoSPolicy::validate(qos))
    {
      MROS2_ERROR("[MROS2LIB] invalid publisher QoS for %s: %s",
                  topic_name.c_str(), QoSPolicy::validation_error(qos));
      handle_fatal_error(ErrorCode::INVALID_QOS_PROFILE,
                        ("create_publisher:" + topic_name).c_str());
    }

    // Select Stateful (RELIABLE) or Stateless (BEST_EFFORT) from the QoS profile.
    bool reliable = (qos.reliability == rtps::ReliabilityKind_t::RELIABLE);

    // RELIABLE user-data writers should use the matched reader locator directly.
  // In WSL2/Wi-Fi validation runs, relying on multicast after discovery can produce a
    // confusing "matched but no data received" state with some ROS2 endpoints.
    bool enforce_unicast = reliable;

    // Create the writer with the full QoS profile.
    rtps::Writer *writer = domain_ptr->createWriter(
        *part_ptr,
        ("rt/" + topic_name).c_str(),
        message_traits::TypeName<T *>().value(),
        reliable,
        qos.reliability,
        qos.durability,
        enforce_unicast,
        qos.deadline_ms(),
        qos.lifespan_ms(),
        static_cast<uint32_t>(qos.history),
        qos.depth,
        qos.max_samples,
        qos.max_bytes);

    if (writer == nullptr)
    {
      MROS2_ERROR("[MROS2LIB] ERROR: failed to create writer in create_publisher()");
      handle_fatal_error(ErrorCode::WRITER_CREATION_FAILED,
                        ("create_publisher:" + topic_name).c_str());
    }

    Publisher pub;
    pub_ptr = writer;
    pub.topic_name = topic_name;

    // Apply full QoS settings to the writer
    writer->setDeadlineMs(qos.deadline_ms());
    writer->setLifespanMs(qos.lifespan_ms());
    writer->setLivelinessLeaseMs(qos.liveliness_lease_ms());
    writer->setResourceLimits(qos.max_samples, qos.max_bytes);
    writer->setKeepAll(qos.history == HistoryKind::KEEP_ALL);
    writer->setHistoryDepth(qos.history == HistoryKind::KEEP_LAST ? qos.depth : 0);

    /* Register callback to ensure that a publisher is matched to the writer before sending messages */
    part_ptr->registerOnNewSubscriberMatchedCallback(pubMatch, &subMatched);
    if (writer->getNumMatchedReader() > 0) {
      pubMatch(&subMatched);
    }

    MROS2_DEBUG("[MROS2LIB] create_publisher complete.");
    return pub;
  }

  template <class T>
  void Publisher::publish(T &msg)
  {
    auto func = [&msg]
    {
      rtps::DataSize_t len = 0;
      rtps::DataSize_t mod_len = 0;
      size_t cdr_enc_offset = 0;

      if (0 == msg.getPubCnt())
      {
        cdr_enc_offset = 4;
        frag_buf[0] = 0;
        frag_buf[1] = 1;
        frag_buf[2] = 0;
        frag_buf[3] = 0;
      }

      auto ret = msg.copyToFragBuf(&frag_buf[cdr_enc_offset],
                                   sizeof(frag_buf) - cdr_enc_offset);
      len = ret.second + cdr_enc_offset;
      if (ret.first)
      {
        if (0 < ret.second)
        {
          mod_len = len % 4;
          if (mod_len > 0)
          {
            for (int i = 0; i < (4 - mod_len); i++)
            {
              frag_buf[len++] = 0;
            }
          }
        }
        else
        {
          msg.resetCount();
        }
      }

      return std::make_pair(frag_buf, (rtps::DataSize_t)(len));
    };

    if (sizeof(buf) < msg.calcTotalSize())
    {
      pub_ptr->newChangeCallback(rtps::ChangeKind_t::ALIVE,
                                 func, msg.calcTotalSize());
    }
    else
    {
      msg.copyToBuf(&buf[4]);
      msg.memAlign(&buf[4]);
      pub_ptr->newChange(rtps::ChangeKind_t::ALIVE, buf,
                         msg.getTotalSize() + 4);
    }
  }

  /*
   *  Subscriber functions
   */
  typedef struct
  {
    void (*cb_fp)(intptr_t);
    intptr_t argp;
  } SubscribeDataType;

  template <class T>
  Subscriber Node::create_subscription(const std::string& topic_name, const QoSProfile& qos, void (*fp)(T *))
  {
    if (!QoSPolicy::validate(qos))
    {
      MROS2_ERROR("[MROS2LIB] invalid subscriber QoS for %s: %s",
                  topic_name.c_str(), QoSPolicy::validation_error(qos));
      handle_fatal_error(ErrorCode::INVALID_QOS_PROFILE,
                        ("create_subscription:" + topic_name).c_str());
    }

    // Select Stateful (RELIABLE) or Stateless (BEST_EFFORT) from the QoS profile.
    bool reliable = (qos.reliability == rtps::ReliabilityKind_t::RELIABLE);

    // Create the reader with the full QoS profile.
    rtps::Reader *reader = domain_ptr->createReader(
        *(this->part),
        ("rt/" + topic_name).c_str(),
        message_traits::TypeName<T *>().value(),
        reliable,
        qos.reliability,
        qos.durability,
        {0},
        qos.deadline_ms(),
        qos.lifespan_ms(),
        static_cast<uint32_t>(qos.history),
        qos.depth);

    if (reader == nullptr)
    {
      MROS2_ERROR("[MROS2LIB] ERROR: failed to create reader in create_subscription()");
      handle_fatal_error(ErrorCode::READER_CREATION_FAILED,
                        ("create_subscription:" + topic_name).c_str());
    }

    Subscriber sub;
    sub_ptr = reader;
    sub.topic_name = topic_name;
    sub.cb_fp = (void (*)(intptr_t))fp;

    // Apply full QoS settings to the reader
    reader->setDeadlineMs(qos.deadline_ms());
    reader->setLivelinessLeaseMs(qos.liveliness_lease_ms());

    // Use static allocation to avoid memory leak
    // Note: This limits to one subscriber per program, but matches current
    // single-instance design with global sub_ptr
    static SubscribeDataType callback_data;
    callback_data.cb_fp = (void (*)(intptr_t))fp;
    callback_data.argp = (intptr_t)NULL;
    reader->registerCallback(sub.callback_handler<T>, (void *)&callback_data);

    /* Register callback to ensure that a subscriber is matched to the reader before receiving messages */
    part_ptr->registerOnNewPublisherMatchedCallback(subMatch, &pubMatched);
    if (reader->getNumMatchedWriters() > 0) {
      subMatch(&pubMatched);
    }

    MROS2_DEBUG("[MROS2LIB] create_subscription complete.");
    return sub;
  }

  template <class T>
  void Subscriber::callback_handler(void *callee, const rtps::ReaderCacheChange &cacheChange)
  {
    T msg;
    const uint8_t *cacheData = cacheChange.getData();
    msg.copyFromBuf(&cacheData[4]);

    SubscribeDataType *sub = (SubscribeDataType *)callee;
    void (*fp)(intptr_t) = sub->cb_fp;
    fp((intptr_t)&msg);
  }

  /*
   *  Other utility functions
   */
  void spin()
  {
    while (true)
    {
#ifndef __MBED__
      osStatus_t ret;
      SubscribeDataType *msg;
      ret = osMessageQueueGet(subscriber_msg_queue_id, &msg, NULL, osWaitForever);
      if (ret != osOK)
      {
        MROS2_ERROR("[MROS2LIB] ERROR: mROS2 spin() wait error %d", ret);
      }
#else  /* __MBED__ */
      // The queue above seems not to be pushed anywhere. So just sleep.
      ThisThread::sleep_for(1s);
#endif /* __MBED__ */
    }
  }

  void printRxStats()
  {
    if (domain_ptr != NULL) {
      domain_ptr->printRxStats();
    } else {
      MROS2_ERROR("[MROS2LIB] Domain not initialized, cannot print RxStats");
    }
  }

  void resetRxStats()
  {
    if (domain_ptr != NULL) {
      domain_ptr->resetRxStats();
    } else {
      MROS2_ERROR("[MROS2LIB] Domain not initialized, cannot reset RxStats");
    }
  }

  bool publisher_matched()
  {
    return subMatched;
  }

  bool subscriber_matched()
  {
    return pubMatched;
  }

  bool subscriber_writer_alive()
  {
    return sub_ptr == nullptr ? false : sub_ptr->isWriterAlive();
  }

  uint32_t publisher_deadline_missed_count()
  {
    return pub_ptr == nullptr ? 0 : pub_ptr->getDeadlineMissedCount();
  }

  uint32_t publisher_lifespan_drop_count()
  {
    return pub_ptr == nullptr ? 0 : pub_ptr->getLifespanDropCount();
  }

  uint32_t publisher_resource_reject_count()
  {
    return pub_ptr == nullptr ? 0 : pub_ptr->getResourceRejectCount();
  }

  uint32_t publisher_history_depth()
  {
    return pub_ptr == nullptr ? 0 : pub_ptr->getHistoryDepth();
  }

  uint32_t publisher_history_count()
  {
    return pub_ptr == nullptr ? 0 : pub_ptr->getHistoryCount();
  }

  uint32_t publisher_history_bytes()
  {
    return pub_ptr == nullptr ? 0 : pub_ptr->getHistoryBytes();
  }

  uint32_t subscriber_deadline_missed_count()
  {
    return sub_ptr == nullptr ? 0 : sub_ptr->getDeadlineMissedCount();
  }

  uint32_t subscriber_received_count()
  {
    return sub_ptr == nullptr ? 0 : sub_ptr->getReceivedCount();
  }

  uint32_t subscriber_accepted_before_match_count()
  {
    return sub_ptr == nullptr ? 0 : sub_ptr->getAcceptedBeforeMatchCount();
  }

  uint32_t subscriber_out_of_order_drop_count()
  {
    return sub_ptr == nullptr ? 0 : sub_ptr->getOutOfOrderDropCount();
  }

  uint32_t subscriber_unmatched_writer_drop_count()
  {
    return sub_ptr == nullptr ? 0 : sub_ptr->getUnmatchedWriterDropCount();
  }

  uint32_t subscriber_liveliness_lost_count()
  {
    return sub_ptr == nullptr ? 0 : sub_ptr->getLivelinessLostCount();
  }

  uint32_t subscriber_liveliness_recovered_count()
  {
    return sub_ptr == nullptr ? 0 : sub_ptr->getLivelinessRecoveredCount();
  }

  void subscriber_check_liveliness()
  {
    if (sub_ptr != nullptr) {
      sub_ptr->checkLiveliness();
    }
  }

  /* implementation for mros2-mbed */
#ifdef __MBED__
  int setIPAddrRTPS(std::array<uint8_t, 4> ipaddr)
  {
    /* check whether IP address has been obtained */
    if (!(ipaddr[0] + ipaddr[1] + ipaddr[2] + ipaddr[3]))
    {
      MROS2_ERROR("IP address has not been obtained!");
      return 0;
    }

    rtps::Config::IP_ADDRESS = ipaddr;
    MROS2_DEBUG("[MROS2LIB] set \"%d.%d.%d.%d\" for RTPS communication",
                rtps::Config::IP_ADDRESS[0], rtps::Config::IP_ADDRESS[1], rtps::Config::IP_ADDRESS[2], rtps::Config::IP_ADDRESS[3]);

    return 1;
  }
#endif /* __MBED__ */

} /* namespace mros2 */

/* implementation for mros2-esp32 */
#ifndef __MBED__
extern "C" int mros2_setIPAddrRTPS(uint32_t ipaddr)
{
  /* check whether IP address has been obtained */
  if (!ipaddr)
  {
    MROS2_ERROR("IP address has not been obtained!");
    return 0;
  }

  std::array<uint8_t, 4> rtps_ipaddr;
  for (int i = 0; i < 4; i++)
    rtps_ipaddr[i] = ipaddr >> (i * 8);

  rtps::Config::IP_ADDRESS = rtps_ipaddr;
  MROS2_DEBUG("[MROS2LIB] set \"%d.%d.%d.%d\" for RTPS communication",
              rtps::Config::IP_ADDRESS[0], rtps::Config::IP_ADDRESS[1], rtps::Config::IP_ADDRESS[2], rtps::Config::IP_ADDRESS[3]);

  return 1;
}
#endif /* __MBED__ */

/*
 *  Declaration for embeddedRTPS participants
 */
void *networkSubDriverPtr;
void *networkPubDriverPtr;
void (*hbPubFuncPtr)(void *);
void (*hbSubFuncPtr)(void *);

extern "C" void callHbPubFunc(void *arg)
{
  if (hbPubFuncPtr != NULL && networkPubDriverPtr != NULL)
  {
    (*hbPubFuncPtr)(networkPubDriverPtr);
  }
}
extern "C" void callHbSubFunc(void *arg)
{
  if (hbSubFuncPtr != NULL && networkSubDriverPtr != NULL)
  {
    (*hbSubFuncPtr)(networkSubDriverPtr);
  }
}

void setTrue(void *args)
{
  *static_cast<std::atomic<bool> *>(args) = true;
}

namespace rtps
{
  namespace Config
  {
    std::array<uint8_t, 4> IP_ADDRESS;
  }
} /* namespace rtps */

/*
 * specialize template functions described in platform's workspace
 */
#include "templates.hpp"
