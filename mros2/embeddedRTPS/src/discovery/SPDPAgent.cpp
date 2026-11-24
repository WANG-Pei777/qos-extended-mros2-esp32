/*
The MIT License
Copyright (c) 2019 Lehrstuhl Informatik 11 - RWTH Aachen University
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE

This file is part of embeddedRTPS.

Author: i11 - Embedded Software, RWTH Aachen University
*/

#include "rtps/discovery/SPDPAgent.h"
#include "lwip/sys.h"
#include "rtps/discovery/ParticipantProxyData.h"
#include "rtps/entities/Participant.h"
#include "rtps/entities/Reader.h"
#include "rtps/entities/Writer.h"
#include "rtps/entities/StatelessWriter.h"
#include "rtps/messages/MessageFactory.h"
#include "rtps/messages/MessageTypes.h"
#include "rtps/storages/PBufWrapper.h"
#include "rtps/utils/Log.h"
#include "rtps/utils/udpUtils.h"

using rtps::SPDPAgent;
using rtps::SMElement::BuildInEndpointSet;
using rtps::SMElement::ParameterId;

SPDPAgent::~SPDPAgent() {
  if (initialized) {
    sys_mutex_free(&m_mutex);
  }
}

void SPDPAgent::init(Participant &participant, BuiltInEndpoints &endpoints) {
  if (sys_mutex_new(&m_mutex) != ERR_OK) {
    SPDP_LOG("Could not alloc mutex");
    return;
  }
  mp_participant = &participant;
  m_buildInEndpoints = endpoints;
  m_buildInEndpoints.spdpReader->registerCallback(receiveCallback, this);

  ucdr_init_buffer(&m_microbuffer, m_outputBuffer.data(),
                   m_outputBuffer.size());
  // addInlineQos();
  addParticipantParameters();

  // WSL2 fix: Send SPDP announcement via unicast to ROS 2 and register SEDP
  // builtin endpoints. WSL2 drops external UDP multicast, so ESP32's standard
  // SPDP never reaches ROS 2. We bypass this by sending SPDP directly and
  // manually registering SEDP proxies (bypassing isSameSubnet() restriction).
  sendSpdpUnicast();
  registerSedpBuiltinEndpoints();

  initialized = true;
}

void SPDPAgent::start() {
  if (m_running) {
    return;
  }
  m_running = true;
  sys_thread_new("SPDPThread", runBroadcast, this,
                 Config::SPDP_WRITER_STACKSIZE, Config::SPDP_WRITER_PRIO);
}

void SPDPAgent::stop() { m_running = false; }

void SPDPAgent::runBroadcast(void *args) {
  SPDPAgent &agent = *static_cast<SPDPAgent *>(args);
  const DataSize_t size = ucdr_buffer_length(&agent.m_microbuffer);
  agent.m_buildInEndpoints.spdpWriter->newChange(
      ChangeKind_t::ALIVE, agent.m_microbuffer.init, size);
  while (agent.m_running) {
#ifdef OS_IS_FREERTOS
    vTaskDelay(pdMS_TO_TICKS(Config::SPDP_RESEND_PERIOD_MS));
#else
    sys_msleep(Config::SPDP_RESEND_PERIOD_MS);
#endif
    agent.m_buildInEndpoints.spdpWriter->setAllChangesToUnsent();
    if (agent.m_cycleHB == Config::SPDP_CYCLECOUNT_HEARTBEAT) {
      agent.m_cycleHB = 0;
      agent.mp_participant->checkAndResetHeartbeats();
    } else {
      agent.m_cycleHB++;
    }
  }
}

void SPDPAgent::receiveCallback(void *callee,
                                const ReaderCacheChange &cacheChange) {
  auto agent = static_cast<SPDPAgent *>(callee);
  agent->handleSPDPPackage(cacheChange);
}

void SPDPAgent::handleSPDPPackage(const ReaderCacheChange &cacheChange) {
  if (!initialized) {
    SPDP_LOG("Callback called without initialization\n");
    return;
  }

  Lock lock{m_mutex};
  if (cacheChange.size > m_inputBuffer.size()) {
    SPDP_LOG("Input buffer to small\n");
    return;
  }

  // Something went wrong deserializing remote participant
  if (!cacheChange.copyInto(m_inputBuffer.data(), m_inputBuffer.size())) {
    return;
  }

  ucdrBuffer buffer;
  ucdr_init_buffer(&buffer, m_inputBuffer.data(), m_inputBuffer.size());

  if (cacheChange.kind == ChangeKind_t::ALIVE) {
    configureEndianessAndOptions(buffer);
    volatile bool success =
        m_proxyDataBuffer.readFromUcdrBuffer(buffer, mp_participant);
    if (success) {
      // TODO In case we store the history we can free the history mutex here
      processProxyData();
    } else {
      SPDP_LOG("ParticipantProxyData deserializtaion failed\n");
    }
  } else {
    // TODO RemoveParticipant
  }
}

void SPDPAgent::configureEndianessAndOptions(ucdrBuffer &buffer) {
  std::array<uint8_t, 2> encapsulation{};
  // Endianess doesn't matter for this since those are single bytes
  ucdr_deserialize_array_uint8_t(&buffer, encapsulation.data(),
                                 encapsulation.size());
  if (encapsulation == SMElement::SCHEME_PL_CDR_LE) {
    buffer.endianness = UCDR_LITTLE_ENDIANNESS;
  } else {
    buffer.endianness = UCDR_BIG_ENDIANNESS;
  }
  // Reuse encapsulation buffer to skip options
  ucdr_deserialize_array_uint8_t(&buffer, encapsulation.data(),
                                 encapsulation.size());
}

void SPDPAgent::processProxyData() {
  if (m_proxyDataBuffer.m_guid.prefix.id == mp_participant->m_guidPrefix.id) {
    return; // Our own packet
  }

  const rtps::ParticipantProxyData *remote_part;
  remote_part =
      mp_participant->findRemoteParticipant(m_proxyDataBuffer.m_guid.prefix);
  if (remote_part != nullptr) {
    SPDP_LOG("Not adding remote participant guid.prefix = %u \n",
             (unsigned int)Guid_t::sum(remote_part->m_guid));
    mp_participant->refreshRemoteParticipantLiveliness(
        m_proxyDataBuffer.m_guid.prefix);
    return; // Already in our list
  }

  if (mp_participant->addNewRemoteParticipant(m_proxyDataBuffer)) {
    addProxiesForBuiltInEndpoints();
    updateSedpEndpointProxies();
    mp_participant->tryMatchDiscoveredEndpoints();
    m_buildInEndpoints.spdpWriter->setAllChangesToUnsent();
#if SPDP_VERBOSE && RTPS_GLOBAL_VERBOSE
    SPDP_LOG("Added new participant with guid: ");
    printGuidPrefix(m_proxyDataBuffer.m_guid.prefix);
  } else {
    SPDP_LOG("Failed to add new participant");
  }
#else
  } else {
    while (1) {
      SPDP_LOG("failed to add remote participant");
    }
  }
#endif
}

bool SPDPAgent::addProxiesForBuiltInEndpoints() {

  LocatorIPv4 *locator = nullptr;

  // Check if the remote participants has a locator in our subnet
  for (unsigned int i = 0;
       i < m_proxyDataBuffer.m_metatrafficUnicastLocatorList.size(); i++) {
    LocatorIPv4 *l = &(m_proxyDataBuffer.m_metatrafficUnicastLocatorList[i]);
    if (l->isValid() && l->isSameSubnet()) {
      locator = l;
      break;
    }
  }

  if (!locator) {
    return false;
  }

  ip4_addr_t ip4addr = locator->getIp4Address();
  const char *addr = ip4addr_ntoa(&ip4addr);
  SPDP_LOG("Adding IPv4 Locator %s\n", addr);

  if (m_proxyDataBuffer.hasPublicationWriter()) {
    const WriterProxy proxy{{m_proxyDataBuffer.m_guid.prefix,
                             ENTITYID_SEDP_BUILTIN_PUBLICATIONS_WRITER},
                            *locator};
    m_buildInEndpoints.sedpPubReader->addNewMatchedWriter(proxy);
  }

  if (m_proxyDataBuffer.hasSubscriptionWriter()) {
    const WriterProxy proxy{{m_proxyDataBuffer.m_guid.prefix,
                             ENTITYID_SEDP_BUILTIN_SUBSCRIPTIONS_WRITER},
                            *locator};
    m_buildInEndpoints.sedpSubReader->addNewMatchedWriter(proxy);
  }

  if (m_proxyDataBuffer.hasPublicationReader()) {
    const ReaderProxy proxy{{m_proxyDataBuffer.m_guid.prefix,
                             ENTITYID_SEDP_BUILTIN_PUBLICATIONS_READER},
                            *locator};
    m_buildInEndpoints.sedpPubWriter->addNewMatchedReader(proxy);
  }

  if (m_proxyDataBuffer.hasSubscriptionReader()) {
    const ReaderProxy proxy{{m_proxyDataBuffer.m_guid.prefix,
                             ENTITYID_SEDP_BUILTIN_SUBSCRIPTIONS_READER},
                            *locator};
    m_buildInEndpoints.sedpSubWriter->addNewMatchedReader(proxy);
  }

  return true;
}

void SPDPAgent::sendSpdpUnicast() {
  if (!m_buildInEndpoints.spdpWriter) {
    return;
  }

  // Build RTPS DATA submessage with the pre-serialized SPDP participant data.
  // This sends the ESP32's SPDP announcement directly to ROS 2's unicast SPDP
  // port, bypassing WSL2's broken multicast.
  PacketInfo info;
  info.srcPort = getBuiltInMulticastPort();

  ip4_addr_t destIp = transformIP4ToU32(
      Config::REMOTE_PARTICIPANT_IP[0], Config::REMOTE_PARTICIPANT_IP[1],
      Config::REMOTE_PARTICIPANT_IP[2], Config::REMOTE_PARTICIPANT_IP[3]);
  info.destAddr = destIp;
  info.destPort = Config::REMOTE_SPDP_PORT;

  MessageFactory::addHeader(info.buffer, mp_participant->m_guidPrefix);
  MessageFactory::addSubMessageTimeStamp(info.buffer);

  PBufWrapper payload;
  payload.reserve(ucdr_buffer_length(&m_microbuffer));
  payload.append(m_outputBuffer.data(), ucdr_buffer_length(&m_microbuffer));

  MessageFactory::addSubMessageData(
      info.buffer, payload, false, SequenceNumber_t{0, 1},
      ENTITYID_SPDP_BUILTIN_PARTICIPANT_WRITER, ENTITYID_UNKNOWN);

  m_buildInEndpoints.spdpWriter->sendRawPacket(info);
  printf("[SPDP] Unicast SPDP announcement sent to %d.%d.%d.%d:%d (%u bytes payload)\n",
         Config::REMOTE_PARTICIPANT_IP[0], Config::REMOTE_PARTICIPANT_IP[1],
         Config::REMOTE_PARTICIPANT_IP[2], Config::REMOTE_PARTICIPANT_IP[3],
         Config::REMOTE_SPDP_PORT,
         (unsigned int)ucdr_buffer_length(&m_microbuffer));
}

void SPDPAgent::registerSedpBuiltinEndpoints() {
  // Manually register SEDP builtin endpoint proxies for the pre-configured
  // remote participant. This bypasses addProxiesForBuiltInEndpoints()'s
  // isSameSubnet() check which fails when ESP32 and ROS 2 are on different
  // subnets (e.g. 10.150.x.x vs 10.116.x.x in WSL2).

  LocatorIPv4 remoteLocator;
  remoteLocator.kind = LocatorKind_t::LOCATOR_KIND_UDPv4;
  remoteLocator.address = {Config::REMOTE_PARTICIPANT_IP[0],
                           Config::REMOTE_PARTICIPANT_IP[1],
                           Config::REMOTE_PARTICIPANT_IP[2],
                           Config::REMOTE_PARTICIPANT_IP[3]};

  // We don't know the remote participant's GUID prefix yet (SPDP hasn't
  // arrived). Use a zero prefix; ROS 2 routes SEDP by writer entity ID
  // regardless of GUID prefix for initial matching.
  GuidPrefix_t zeroPrefix{0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0};

  // ESP32's SEDP pub writer → ROS 2's SEDP pub reader
  remoteLocator.port = Config::REMOTE_SEDP_PORT;
  {
    ReaderProxy proxy;
    proxy.remoteReaderGuid = {zeroPrefix,
                              ENTITYID_SEDP_BUILTIN_PUBLICATIONS_READER};
    proxy.remoteLocator = remoteLocator;
    proxy.remoteMulticastLocator = LocatorIPv4{};
    proxy.useMulticast = false;
    proxy.suppressUnicast = false;
    m_buildInEndpoints.sedpPubWriter->addNewMatchedReader(proxy);
  }

  // ESP32's SEDP sub writer → ROS 2's SEDP sub reader
  {
    ReaderProxy proxy;
    proxy.remoteReaderGuid = {zeroPrefix,
                              ENTITYID_SEDP_BUILTIN_SUBSCRIPTIONS_READER};
    proxy.remoteLocator = remoteLocator;
    proxy.remoteMulticastLocator = LocatorIPv4{};
    proxy.useMulticast = false;
    proxy.suppressUnicast = false;
    m_buildInEndpoints.sedpSubWriter->addNewMatchedReader(proxy);
  }

  printf("[SPDP] SEDP builtin endpoints registered for %d.%d.%d.%d:%d\n",
         Config::REMOTE_PARTICIPANT_IP[0], Config::REMOTE_PARTICIPANT_IP[1],
         Config::REMOTE_PARTICIPANT_IP[2], Config::REMOTE_PARTICIPANT_IP[3],
         Config::REMOTE_SEDP_PORT);
}

void SPDPAgent::updateSedpEndpointProxies() {
  // The zero-prefix bootstrap proxies only let our SEDP writers announce to a
  // preconfigured host. Once SPDP reveals the host GUID, bind all four reliable
  // SEDP directions so late-joining readers can ACKNACK and recover discovery
  // DATA that the host published before this participant existed.
  const GuidPrefix_t remotePrefix = m_proxyDataBuffer.m_guid.prefix;
  const GuidPrefix_t bootstrapPrefix{
      0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
  LocatorIPv4 remoteLocator;
  remoteLocator.kind = LocatorKind_t::LOCATOR_KIND_UDPv4;
  remoteLocator.address = {Config::REMOTE_PARTICIPANT_IP[0],
                           Config::REMOTE_PARTICIPANT_IP[1],
                           Config::REMOTE_PARTICIPANT_IP[2],
                           Config::REMOTE_PARTICIPANT_IP[3]};
  remoteLocator.port = Config::REMOTE_SEDP_PORT;

  const Guid_t remotePubWriter = {
      remotePrefix, ENTITYID_SEDP_BUILTIN_PUBLICATIONS_WRITER};
  if (m_buildInEndpoints.sedpPubReader != nullptr &&
      !m_buildInEndpoints.sedpPubReader->knowWriterId(remotePubWriter)) {
    m_buildInEndpoints.sedpPubReader->addNewMatchedWriter(
        WriterProxy{remotePubWriter, remoteLocator});
  }

  const Guid_t remoteSubWriter = {
      remotePrefix, ENTITYID_SEDP_BUILTIN_SUBSCRIPTIONS_WRITER};
  if (m_buildInEndpoints.sedpSubReader != nullptr &&
      !m_buildInEndpoints.sedpSubReader->knowWriterId(remoteSubWriter)) {
    m_buildInEndpoints.sedpSubReader->addNewMatchedWriter(
        WriterProxy{remoteSubWriter, remoteLocator});
  }

  const Guid_t remotePubReader = {
      remotePrefix, ENTITYID_SEDP_BUILTIN_PUBLICATIONS_READER};
  const Guid_t bootstrapPubReader = {
      bootstrapPrefix, ENTITYID_SEDP_BUILTIN_PUBLICATIONS_READER};
  if (m_buildInEndpoints.sedpPubWriter != nullptr) {
    m_buildInEndpoints.sedpPubWriter->removeReader(bootstrapPubReader);
    if (!m_buildInEndpoints.sedpPubWriter->knowReaderId(remotePubReader)) {
      m_buildInEndpoints.sedpPubWriter->addNewMatchedReader(
          ReaderProxy{remotePubReader, remoteLocator});
    }
  }

  const Guid_t remoteSubReader = {
      remotePrefix, ENTITYID_SEDP_BUILTIN_SUBSCRIPTIONS_READER};
  const Guid_t bootstrapSubReader = {
      bootstrapPrefix, ENTITYID_SEDP_BUILTIN_SUBSCRIPTIONS_READER};
  if (m_buildInEndpoints.sedpSubWriter != nullptr) {
    m_buildInEndpoints.sedpSubWriter->removeReader(bootstrapSubReader);
    if (!m_buildInEndpoints.sedpSubWriter->knowReaderId(remoteSubReader)) {
      m_buildInEndpoints.sedpSubWriter->addNewMatchedReader(
          ReaderProxy{remoteSubReader, remoteLocator});
    }
  }

  printf("[SPDP] SEDP proxies updated with remote GUID prefix\n");
}

void SPDPAgent::addInlineQos() {
  ucdr_serialize_uint16_t(&m_microbuffer, ParameterId::PID_KEY_HASH);
  ucdr_serialize_uint16_t(&m_microbuffer, 16);
  ucdr_serialize_array_uint8_t(&m_microbuffer,
                               mp_participant->m_guidPrefix.id.data(),
                               sizeof(GuidPrefix_t::id));
  ucdr_serialize_array_uint8_t(&m_microbuffer,
                               ENTITYID_BUILD_IN_PARTICIPANT.entityKey.data(),
                               sizeof(EntityId_t::entityKey));
  ucdr_serialize_uint8_t(
      &m_microbuffer,
      static_cast<uint8_t>(ENTITYID_BUILD_IN_PARTICIPANT.entityKind));

  endCurrentList();
}

void SPDPAgent::endCurrentList() {
  ucdr_serialize_uint16_t(&m_microbuffer, ParameterId::PID_SENTINEL);
  ucdr_serialize_uint16_t(&m_microbuffer, 0);
}

void SPDPAgent::addParticipantParameters() {
  const uint16_t zero_options = 0;
  const uint16_t protocolVersionSize =
      sizeof(PROTOCOLVERSION.major) + sizeof(PROTOCOLVERSION.minor);
  const uint16_t vendorIdSize = Config::VENDOR_ID.vendorId.size();
  const uint16_t locatorSize = sizeof(FullLengthLocator);
  const uint16_t durationSize =
      sizeof(Duration_t::seconds) + sizeof(Duration_t::fraction);
  const uint16_t entityKeySize = 3;
  const uint16_t entityKindSize = 1;
  const uint16_t entityIdSize = entityKeySize + entityKindSize;
  const uint16_t guidSize = sizeof(GuidPrefix_t::id) + entityIdSize;

  const FullLengthLocator userUniCastLocator =
      getUserUnicastLocator(mp_participant->m_participantId);
  const FullLengthLocator builtInUniCastLocator =
      getBuiltInUnicastLocator(mp_participant->m_participantId);
  const FullLengthLocator builtInMultiCastLocator =
      getBuiltInMulticastLocator();

  ucdr_serialize_array_uint8_t(&m_microbuffer,
                               rtps::SMElement::SCHEME_PL_CDR_LE.data(),
                               rtps::SMElement::SCHEME_PL_CDR_LE.size());
  ucdr_serialize_uint16_t(&m_microbuffer, zero_options);

  ucdr_serialize_uint16_t(&m_microbuffer, ParameterId::PID_PROTOCOL_VERSION);
  ucdr_serialize_uint16_t(&m_microbuffer, protocolVersionSize + 2);
  ucdr_serialize_uint8_t(&m_microbuffer, PROTOCOLVERSION.major);
  ucdr_serialize_uint8_t(&m_microbuffer, PROTOCOLVERSION.minor);
  m_microbuffer.iterator += 2;      // padding
  m_microbuffer.last_data_size = 4; // to 4 byte

  ucdr_serialize_uint16_t(&m_microbuffer, ParameterId::PID_VENDORID);
  ucdr_serialize_uint16_t(&m_microbuffer, vendorIdSize + 2);
  ucdr_serialize_array_uint8_t(&m_microbuffer,
                               Config::VENDOR_ID.vendorId.data(), vendorIdSize);
  m_microbuffer.iterator += 2;      // padding
  m_microbuffer.last_data_size = 4; // to 4 byte

  ucdr_serialize_uint16_t(&m_microbuffer,
                          ParameterId::PID_DEFAULT_UNICAST_LOCATOR);
  ucdr_serialize_uint16_t(&m_microbuffer, locatorSize);
  ucdr_serialize_array_uint8_t(
      &m_microbuffer, reinterpret_cast<const uint8_t *>(&userUniCastLocator),
      locatorSize);

  ucdr_serialize_uint16_t(&m_microbuffer,
                          ParameterId::PID_METATRAFFIC_UNICAST_LOCATOR);
  ucdr_serialize_uint16_t(&m_microbuffer, locatorSize);
  ucdr_serialize_array_uint8_t(
      &m_microbuffer, reinterpret_cast<const uint8_t *>(&builtInUniCastLocator),
      locatorSize);

  ucdr_serialize_uint16_t(&m_microbuffer,
                          ParameterId::PID_METATRAFFIC_MULTICAST_LOCATOR);
  ucdr_serialize_uint16_t(&m_microbuffer, locatorSize);
  ucdr_serialize_array_uint8_t(
      &m_microbuffer,
      reinterpret_cast<const uint8_t *>(&builtInMultiCastLocator), locatorSize);

  ucdr_serialize_uint16_t(&m_microbuffer,
                          ParameterId::PID_PARTICIPANT_LEASE_DURATION);
  ucdr_serialize_uint16_t(&m_microbuffer, durationSize);
  ucdr_serialize_int32_t(&m_microbuffer,
                         Config::SPDP_DEFAULT_REMOTE_LEASE_DURATION.seconds);
  ucdr_serialize_uint32_t(&m_microbuffer,
                          Config::SPDP_DEFAULT_REMOTE_LEASE_DURATION.fraction);

  ucdr_serialize_uint16_t(&m_microbuffer, ParameterId::PID_PARTICIPANT_GUID);
  ucdr_serialize_uint16_t(&m_microbuffer, guidSize);
  ucdr_serialize_array_uint8_t(&m_microbuffer,
                               mp_participant->m_guidPrefix.id.data(),
                               sizeof(GuidPrefix_t::id));
  ucdr_serialize_array_uint8_t(&m_microbuffer,
                               ENTITYID_BUILD_IN_PARTICIPANT.entityKey.data(),
                               entityKeySize);
  ucdr_serialize_uint8_t(
      &m_microbuffer,
      static_cast<uint8_t>(ENTITYID_BUILD_IN_PARTICIPANT.entityKind));

  ucdr_serialize_uint16_t(&m_microbuffer,
                          ParameterId::PID_BUILTIN_ENDPOINT_SET);
  ucdr_serialize_uint16_t(&m_microbuffer, sizeof(BuildInEndpointSet));
  ucdr_serialize_uint32_t(
      &m_microbuffer, BuildInEndpointSet::DISC_BIE_PARTICIPANT_ANNOUNCER |
                          BuildInEndpointSet::DISC_BIE_PARTICIPANT_DETECTOR |
                          BuildInEndpointSet::DISC_BIE_PUBLICATION_ANNOUNCER |
                          BuildInEndpointSet::DISC_BIE_PUBLICATION_DETECTOR |
                          BuildInEndpointSet::DISC_BIE_SUBSCRIPTION_ANNOUNCER |
                          BuildInEndpointSet::DISC_BIE_SUBSCRIPTION_DETECTOR);

  endCurrentList();
}

#undef SPDP_VERBOSE
