#include "mros2.h"
#include "mros2/error_handler.h"

#include <rtps/rtps.h>
#include <array>
#include <atomic>
#include <cstring>
#include <memory>
#include <type_traits>
#include <utility>

#ifdef __MBED__
#include "mbed.h"
#else /* __MBED__ */
#include "mros2_config.h"
#include "cmsis_os.h"
#endif /* __MBED__ */

namespace mros2
{

#ifndef MROS2_FRAGMENT_BUFFER_SIZE
#define MROS2_FRAGMENT_BUFFER_SIZE 1024
#endif
  static_assert(MROS2_FRAGMENT_BUFFER_SIZE >= 8 &&
                    MROS2_FRAGMENT_BUFFER_SIZE <= 1400,
                "fragment buffer must fit the RTPS UDP MTU budget");

  rtps::Domain *domain_ptr = NULL;
  rtps::Participant *part_ptr = NULL;
  rtps::Writer *pub_ptr = NULL;
  rtps::Reader *sub_ptr = NULL;

  struct SubscribeDataType
  {
    std::array<uint8_t, sizeof(void (*)())> callbackBytes{};
    bool hasCallback = false;
  };
  constexpr size_t MAX_SUBSCRIBER_CALLBACK_SLOTS =
      rtps::Config::NUM_STATEFUL_READERS +
      rtps::Config::NUM_STATELESS_READERS;
  std::array<SubscribeDataType, MAX_SUBSCRIBER_CALLBACK_SLOTS>
      subscriber_callback_slots{};
  std::atomic<size_t> subscriber_callback_slot_count{0};

  template <class T, class = void>
  struct HasBoundedCopyFromBuf : std::false_type {};

  template <class T>
  struct HasBoundedCopyFromBuf<
      T, std::void_t<decltype(std::declval<T &>().copyFromBuf(
             std::declval<const uint8_t *>(), std::declval<uint32_t>()))>>
      : std::true_type {};

  template <class T, class = void>
  struct HasBoundedValidateFromBuf : std::false_type {};

  template <class T>
  struct HasBoundedValidateFromBuf<
      T, std::void_t<decltype(std::declval<const T &>().validateFromBuf(
             std::declval<const uint8_t *>(), std::declval<uint32_t>()))>>
      : std::true_type {};

  template <class T>
  bool copyMessageFromBoundedBuffer(
      T &message, const uint8_t *data, uint32_t size)
  {
    if constexpr (HasBoundedCopyFromBuf<T>::value) {
      return message.copyFromBuf(data, size);
    }
    message.copyFromBuf(data);
    return true;
  }

#define SUB_MSG_SIZE 4 // addr size
  osMessageQueueId_t subscriber_msg_queue_id;

  std::atomic<bool> completeNodeInit{false};
  uint8_t endpointId = 0;
  uint32_t subCbArray[10];

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
 *  Initialization of the mros2 environment
 */
#ifdef __MBED__
  Thread *mros2_init_thread;
#endif /* __MBED__ */
  void init(int argc, char *argv[])
  {
#ifdef __MBED__
    mros2_init_thread = new Thread(osPriorityAboveNormal, 5000, nullptr, "mros2Thread");
    mros2_init_thread->start(callback(mros2_init, (void *)NULL));
#else  /* __MBED__ */
    osThreadAttr_t attributes{};

    attributes.name = "mros2Thread";
    attributes.stack_size = 5000;
    attributes.priority = (osPriority_t)24;

    if (osThreadNew(mros2_init, NULL, &attributes) == nullptr) {
      MROS2_ERROR("[MROS2LIB] ERROR: mros2 init thread creation failed");
      handle_fatal_error(ErrorCode::RESOURCE_EXHAUSTED,
                         "mros2_init_thread");
    }
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
      MROS2_ERROR("[MROS2LIB] ERROR: mros2 init failed");
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
    const uint32_t physical_history_capacity =
        qos.reliability == rtps::ReliabilityKind_t::RELIABLE
            ? rtps::Config::HISTORY_SIZE_STATEFUL
            : rtps::Config::HISTORY_SIZE_STATELESS;
    if (!QoSPolicy::validate(qos, physical_history_capacity))
    {
      MROS2_ERROR("[MROS2LIB] invalid publisher QoS for %s: %s",
                  topic_name.c_str(),
                  QoSPolicy::validation_error(qos,
                                              physical_history_capacity));
      handle_fatal_error(ErrorCode::INVALID_QOS_PROFILE,
                        ("create_publisher:" + topic_name).c_str());
    }

    // Select Stateful (RELIABLE) or Stateless (BEST_EFFORT) from the QoS profile.
    bool reliable = (qos.reliability == rtps::ReliabilityKind_t::RELIABLE);

    // RELIABLE user-data writers should use the matched reader locator directly.
  // In WSL2/Wi-Fi validation runs, relying on multicast after discovery can produce a
    // confusing "matched but no data received" state with some ROS 2 endpoints.
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
        qos.liveliness_lease_ms(),
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
    pub.writer_ = writer;
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
  bool Publisher::publish(T &msg)
  {
    rtps::Writer *const writer = writer_;
    if (writer == nullptr || !completeNodeInit.load()) {
      return false;
    }

    constexpr size_t kInlineBufferSize = 100;
    const uint32_t serializedSize = msg.calcTotalSize();
    if (kInlineBufferSize < serializedSize)
    {
      if (!rtps::fragmentedPublicationValid(true, serializedSize)) {
        return writer->newChangeCallback(
                   rtps::ChangeKind_t::ALIVE,
                   rtps::CacheChange::SerializerCallback{},
                   serializedSize) != nullptr;
      }
      struct FragmentSerializationState {
        explicit FragmentSerializationState(const T &source) : message(source) {}
        T message;
        std::array<uint8_t, MROS2_FRAGMENT_BUFFER_SIZE> buffer{};
      };
      auto state = std::make_shared<FragmentSerializationState>(msg);
      auto func = [state](rtps::CacheChange::SerializerOperation operation)
      {
        if (operation == rtps::CacheChange::SerializerOperation::RESET)
        {
          state->message.resetCount();
          return std::make_pair(
              static_cast<uint8_t *>(nullptr),
              static_cast<rtps::DataSize_t>(0));
        }
        rtps::DataSize_t len = 0;
        rtps::DataSize_t mod_len = 0;
        size_t cdr_enc_offset = 0;

        if (0 == state->message.getPubCnt())
        {
          cdr_enc_offset = 4;
          state->buffer[0] = 0;
          state->buffer[1] = 1;
          state->buffer[2] = 0;
          state->buffer[3] = 0;
        }

        auto ret = state->message.copyToFragBuf(
            state->buffer.data() + cdr_enc_offset,
            state->buffer.size() - cdr_enc_offset);
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
                state->buffer[len++] = 0;
              }
            }
          }
          else
          {
            state->message.resetCount();
          }
        }

        return std::make_pair(state->buffer.data(),
                              static_cast<rtps::DataSize_t>(len));
      };
      return writer->newChangeCallback(rtps::ChangeKind_t::ALIVE, func,
                                       serializedSize) != nullptr;
    }

    std::array<uint8_t, kInlineBufferSize> inlineBuffer{};
    inlineBuffer[1] = 1; // CDR little-endian encapsulation header
    msg.copyToBuf(inlineBuffer.data() + 4);
    msg.memAlign(inlineBuffer.data() + 4);
    return writer->newChange(rtps::ChangeKind_t::ALIVE, inlineBuffer.data(),
                             msg.getTotalSize() + 4) != nullptr;
  }

  bool Publisher::matched() const
  {
    return writer_ != nullptr && writer_->getNumMatchedReader() > 0;
  }

  uint32_t Publisher::matched_reader_count() const
  {
    return writer_ == nullptr ? 0 : writer_->getNumMatchedReader();
  }

  uint32_t Publisher::publish_attempt_count() const
  {
    return writer_ == nullptr ? 0 : writer_->getPublishAttemptCount();
  }

  uint32_t Publisher::publish_accept_count() const
  {
    return writer_ == nullptr ? 0 : writer_->getPublishAcceptCount();
  }

  uint32_t Publisher::resource_reject_count() const
  {
    return writer_ == nullptr ? 0 : writer_->getResourceRejectCount();
  }

  uint32_t Publisher::allocation_failure_count() const
  {
    return writer_ == nullptr ? 0 : writer_->getAllocationFailureCount();
  }

  uint32_t Publisher::local_send_failure_count() const
  {
    return writer_ == nullptr ? 0 : writer_->getLocalSendFailureCount();
  }

  uint32_t Publisher::control_send_failure_count() const
  {
    return writer_ == nullptr ? 0 : writer_->getControlSendFailureCount();
  }

  uint32_t Publisher::history_depth() const
  {
    return writer_ == nullptr ? 0 : writer_->getHistoryDepth();
  }

  uint32_t Publisher::history_count() const
  {
    return writer_ == nullptr ? 0 : writer_->getHistoryCount();
  }

  uint32_t Publisher::history_bytes() const
  {
    return writer_ == nullptr ? 0 : writer_->getHistoryBytes();
  }

  uint32_t Publisher::acknack_receive_count() const
  { return writer_ == nullptr ? 0 : writer_->getAckNackReceiveCount(); }
  uint32_t Publisher::acknack_accept_count() const
  { return writer_ == nullptr ? 0 : writer_->getAckNackAcceptCount(); }
  uint32_t Publisher::acknack_stale_drop_count() const
  { return writer_ == nullptr ? 0 : writer_->getAckNackStaleDropCount(); }
  uint32_t Publisher::acknack_unknown_reader_drop_count() const
  { return writer_ == nullptr ? 0 : writer_->getAckNackUnknownReaderDropCount(); }
  uint32_t Publisher::acknack_best_effort_drop_count() const
  { return writer_ == nullptr ? 0 : writer_->getAckNackBestEffortDropCount(); }
  uint32_t Publisher::acknack_gap_response_count() const
  { return writer_ == nullptr ? 0 : writer_->getAckNackGapResponseCount(); }
  uint32_t Publisher::acknack_data_response_count() const
  { return writer_ == nullptr ? 0 : writer_->getAckNackDataResponseCount(); }
  uint32_t Publisher::acknack_deferred_response_count() const
  { return writer_ == nullptr ? 0 : writer_->getAckNackDeferredResponseCount(); }

  bool Publisher::set_transmission_held(bool held)
  {
    if (writer_ == nullptr) {
      return false;
    }
    writer_->setTransmissionHeld(held);
    return true;
  }

  /*
   *  Subscriber functions
   */
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

    Subscriber sub;
    sub.topic_name = topic_name;
    if (fp == nullptr) {
      MROS2_ERROR("[MROS2LIB] subscriber callback is null");
      handle_fatal_error(ErrorCode::READER_CREATION_FAILED,
                         ("create_subscription:" + topic_name).c_str());
      return sub;
    }

    const size_t callback_slot = subscriber_callback_slot_count.fetch_add(
        1, std::memory_order_relaxed);
    if (callback_slot >= subscriber_callback_slots.size()) {
      MROS2_ERROR("[MROS2LIB] subscriber callback slots exhausted");
      handle_fatal_error(ErrorCode::READER_CREATION_FAILED,
                         ("create_subscription:" + topic_name).c_str());
      return sub;
    }

    // Install the callback before Participant admission. A retained remote
    // endpoint can match immediately, and Best Effort Transient Local replay
    // has no ACKNACK retry after a callback-registration race.
    SubscribeDataType *callback_data =
        &subscriber_callback_slots[callback_slot];
    static_assert(
        sizeof(fp) <= sizeof(callback_data->callbackBytes),
        "subscriber callback slot cannot represent this function pointer");
    std::memcpy(
        callback_data->callbackBytes.data(), &fp, sizeof(fp));
    callback_data->hasCallback = true;

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
        qos.liveliness_lease_ms(),
        static_cast<uint32_t>(qos.history),
        qos.depth,
        Subscriber::callback_handler<T>,
        callback_data,
        Subscriber::payload_validator<T>,
        callback_data);

    if (reader == nullptr)
    {
      MROS2_ERROR("[MROS2LIB] ERROR: failed to create reader in create_subscription()");
      handle_fatal_error(ErrorCode::READER_CREATION_FAILED,
                        ("create_subscription:" + topic_name).c_str());
      return sub;
    }

    sub.reader_ = reader;
    sub_ptr = reader;

    /* Register callback to ensure that a subscriber is matched to the reader before receiving messages */
    part_ptr->registerOnNewPublisherMatchedCallback(subMatch, &pubMatched);
    if (reader->getNumMatchedWriters() > 0) {
      subMatch(&pubMatched);
    }

    MROS2_DEBUG("[MROS2LIB] create_subscription complete.");
    return sub;
  }

  bool Subscriber::matched() const
  {
    return reader_ != nullptr && reader_->getNumMatchedWriters() > 0;
  }

  uint32_t Subscriber::matched_writer_count() const
  {
    return reader_ == nullptr ? 0 : reader_->getNumMatchedWriters();
  }

  bool Subscriber::writer_alive() const
  {
    return reader_ != nullptr && reader_->isWriterAlive();
  }

  uint32_t Subscriber::deadline_missed_count() const
  {
    return reader_ == nullptr ? 0 : reader_->getDeadlineMissedCount();
  }

  uint32_t Subscriber::received_count() const
  {
    return reader_ == nullptr ? 0 : reader_->getReceivedCount();
  }

  uint32_t Subscriber::accepted_before_match_count() const
  {
    return reader_ == nullptr ? 0 : reader_->getAcceptedBeforeMatchCount();
  }

  uint32_t Subscriber::out_of_order_drop_count() const
  {
    return reader_ == nullptr ? 0 : reader_->getOutOfOrderDropCount();
  }

  uint32_t Subscriber::unmatched_writer_drop_count() const
  {
    return reader_ == nullptr ? 0 : reader_->getUnmatchedWriterDropCount();
  }

  uint32_t Subscriber::unsupported_payload_drop_count() const
  {
    return reader_ == nullptr
               ? 0
               : reader_->getUnsupportedPayloadDropCount();
  }

  uint32_t Subscriber::gap_received_count() const
  {
    return reader_ == nullptr ? 0 : reader_->getGapReceivedCount();
  }

  uint32_t Subscriber::control_send_failure_count() const
  {
    return reader_ == nullptr ? 0 : reader_->getControlSendFailureCount();
  }

  uint32_t Subscriber::liveliness_lost_count() const
  {
    return reader_ == nullptr ? 0 : reader_->getLivelinessLostCount();
  }

  uint32_t Subscriber::liveliness_recovered_count() const
  {
    return reader_ == nullptr ? 0 : reader_->getLivelinessRecoveredCount();
  }

  void Subscriber::check_liveliness()
  {
    if (reader_ != nullptr) {
      reader_->checkLiveliness();
    }
  }

  template <class T>
  bool Subscriber::payload_validator(
      void *callee, const rtps::ReaderCacheChange &cacheChange)
  {
    if (callee == nullptr || cacheChange.getData() == nullptr ||
        cacheChange.getDataSize() < 4 ||
        cacheChange.getData()[0] != 0 ||
        cacheChange.getData()[1] != 1) {
      return false;
    }
    if constexpr (HasBoundedValidateFromBuf<T>::value) {
      T message;
      return message.validateFromBuf(
          cacheChange.getData() + 4, cacheChange.getDataSize() - 4U);
    }
    return true;
  }

  template <class T>
  void Subscriber::callback_handler(void *callee, const rtps::ReaderCacheChange &cacheChange)
  {
    if (callee == nullptr || cacheChange.getData() == nullptr ||
        cacheChange.getDataSize() < 4 ||
        cacheChange.getData()[0] != 0 ||
        cacheChange.getData()[1] != 1) {
      return;
    }
    SubscribeDataType *sub = static_cast<SubscribeDataType *>(callee);
    if (!sub->hasCallback) {
      return;
    }

    T msg;
    const uint8_t *cacheData = cacheChange.getData();
    if (!copyMessageFromBoundedBuffer(
            msg, &cacheData[4], cacheChange.getDataSize() - 4U)) {
      return;
    }

    void (*fp)(T *) = nullptr;
    std::memcpy(&fp, sub->callbackBytes.data(), sizeof(fp));
    if (fp != nullptr) {
      fp(&msg);
    }
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
        MROS2_ERROR("[MROS2LIB] ERROR: mros2 spin() wait error %d", ret);
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
    return subMatched ||
           (pub_ptr != nullptr && pub_ptr->getNumMatchedReader() > 0);
  }

  bool publisher_has_matched_reader()
  {
    return pub_ptr != nullptr && pub_ptr->getNumMatchedReader() > 0;
  }

  uint32_t publisher_matched_reader_count()
  {
    return pub_ptr != nullptr ? pub_ptr->getNumMatchedReader() : 0;
  }

  bool subscriber_matched()
  {
    return pubMatched ||
           (sub_ptr != nullptr && sub_ptr->getNumMatchedWriters() > 0);
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

  uint32_t publisher_publish_attempt_count()
  {
    return pub_ptr == nullptr ? 0 : pub_ptr->getPublishAttemptCount();
  }

  uint32_t publisher_publish_accept_count()
  {
    return pub_ptr == nullptr ? 0 : pub_ptr->getPublishAcceptCount();
  }

  uint32_t publisher_resource_reject_count()
  {
    return pub_ptr == nullptr ? 0 : pub_ptr->getResourceRejectCount();
  }

  uint32_t publisher_allocation_failure_count()
  {
    return pub_ptr == nullptr ? 0 : pub_ptr->getAllocationFailureCount();
  }

  uint32_t publisher_local_send_failure_count()
  {
    return pub_ptr == nullptr ? 0 : pub_ptr->getLocalSendFailureCount();
  }

  uint32_t publisher_control_send_failure_count()
  {
    return pub_ptr == nullptr ? 0 : pub_ptr->getControlSendFailureCount();
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

  uint32_t publisher_acknack_receive_count()
  { return pub_ptr == nullptr ? 0 : pub_ptr->getAckNackReceiveCount(); }
  uint32_t publisher_acknack_accept_count()
  { return pub_ptr == nullptr ? 0 : pub_ptr->getAckNackAcceptCount(); }
  uint32_t publisher_acknack_stale_drop_count()
  { return pub_ptr == nullptr ? 0 : pub_ptr->getAckNackStaleDropCount(); }
  uint32_t publisher_acknack_unknown_reader_drop_count()
  { return pub_ptr == nullptr ? 0 : pub_ptr->getAckNackUnknownReaderDropCount(); }
  uint32_t publisher_acknack_best_effort_drop_count()
  { return pub_ptr == nullptr ? 0 : pub_ptr->getAckNackBestEffortDropCount(); }
  uint32_t publisher_acknack_gap_response_count()
  { return pub_ptr == nullptr ? 0 : pub_ptr->getAckNackGapResponseCount(); }
  uint32_t publisher_acknack_data_response_count()
  { return pub_ptr == nullptr ? 0 : pub_ptr->getAckNackDataResponseCount(); }
  uint32_t publisher_acknack_deferred_response_count()
  { return pub_ptr == nullptr ? 0 : pub_ptr->getAckNackDeferredResponseCount(); }

  bool publisher_set_transmission_held(bool held)
  {
    if (pub_ptr == nullptr) return false;
    pub_ptr->setTransmissionHeld(held);
    return true;
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

  uint32_t subscriber_unsupported_payload_drop_count()
  {
    return sub_ptr == nullptr
               ? 0
               : sub_ptr->getUnsupportedPayloadDropCount();
  }

  uint32_t subscriber_gap_received_count()
  {
    return sub_ptr == nullptr ? 0 : sub_ptr->getGapReceivedCount();
  }

  uint32_t subscriber_control_send_failure_count()
  {
    return sub_ptr == nullptr ? 0 : sub_ptr->getControlSendFailureCount();
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

  bool register_publisher_deadline_missed_callback(void (*cb)(void *),
                                                    void *arg)
  {
    if (pub_ptr == nullptr) return false;
    pub_ptr->setDeadlineMissedCallback(cb, arg);
    return true;
  }

  bool register_subscriber_deadline_missed_callback(void (*cb)(void *),
                                                     void *arg)
  {
    if (sub_ptr == nullptr) return false;
    sub_ptr->setDeadlineMissedCallback(cb, arg);
    return true;
  }

  bool register_subscriber_liveliness_lost_callback(void (*cb)(void *),
                                                     void *arg)
  {
    if (sub_ptr == nullptr) return false;
    sub_ptr->setLivelinessLostCallback(cb, arg);
    return true;
  }

  bool register_subscriber_liveliness_recovered_callback(void (*cb)(void *),
                                                          void *arg)
  {
    if (sub_ptr == nullptr) return false;
    sub_ptr->setLivelinessRecoveredCallback(cb, arg);
    return true;
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
