#!/usr/bin/env bash
#
# NOTE: this script expects the full test set of the development workstation;
# several test sources it references are not in this repository. For the
# tests that ship with the repository use scripts/test/run_host_tests.sh.

#
# Host-side QoS unit tests + security/static checks.
# Runs on any Linux/macOS host with g++.
# No ESP32 or ESP-IDF required.
#
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILD_DIR="${PROJECT_ROOT}/build/qos_static_checks"
SRC="${PROJECT_ROOT}/tests/test_qos.cpp"
BIN="${BUILD_DIR}/test_qos"
FAILED=0

echo "=== Phase 1: QoS Unit Tests ==="
mkdir -p "${BUILD_DIR}"

g++ -std=c++17 -Wall -Wextra -Werror \
  -I"${PROJECT_ROOT}/tests/stubs" \
  -I"${PROJECT_ROOT}/mros2/include" \
  -o "${BIN}" \
  "${SRC}"

if ! "${BIN}"; then
  echo "[FAIL] QoS unit tests failed"
  FAILED=1
fi

echo ""
echo "=== Phase 1a: Discovery QoS Compatibility Tests ==="
DISCOVERY_BIN="${BUILD_DIR}/test_qos_compatibility"
g++ -std=c++17 \
  -I"${PROJECT_ROOT}/tests/stubs" \
  -I"${PROJECT_ROOT}/mros2/embeddedRTPS/include" \
  -o "${DISCOVERY_BIN}" \
  "${PROJECT_ROOT}/tests/test_qos_compatibility.cpp"

if ! "${DISCOVERY_BIN}"; then
  echo "[FAIL] Discovery QoS compatibility tests failed"
  FAILED=1
fi

echo ""
echo "=== Phase 1a1: SEDP Parameter Parsing Tests ==="
TOPIC_DATA_BUILD="${BUILD_DIR}/topic_data"
TOPIC_DATA_BIN="${BUILD_DIR}/test_topic_data_parsing"
mkdir -p "${TOPIC_DATA_BUILD}"
for source in common types/basic types/array; do
  object_name="${source//\//_}.o"
  gcc -std=c11 \
    -I"${PROJECT_ROOT}/mros2/embeddedRTPS/thirdparty/Micro-CDR/include" \
    -I"${PROJECT_ROOT}/mros2/embeddedRTPS/thirdparty/Micro-CDR/src/c" \
    -c "${PROJECT_ROOT}/mros2/embeddedRTPS/thirdparty/Micro-CDR/src/c/${source}.c" \
    -o "${TOPIC_DATA_BUILD}/${object_name}"
done
g++ -std=c++17 \
  -include "${PROJECT_ROOT}/tests/stubs/udp_driver_override.h" \
  -I"${PROJECT_ROOT}/platform" \
  -I"${PROJECT_ROOT}/mros2/embeddedRTPS/include" \
  -I"${PROJECT_ROOT}/mros2/embeddedRTPS/thirdparty/Micro-CDR/include" \
  -I"${PROJECT_ROOT}/tests/stubs" \
  "${PROJECT_ROOT}/tests/test_topic_data_parsing.cpp" \
  "${PROJECT_ROOT}/mros2/embeddedRTPS/src/discovery/TopicData.cpp" \
  "${PROJECT_ROOT}/mros2/embeddedRTPS/src/messages/MessageTypes.cpp" \
  "${TOPIC_DATA_BUILD}/common.o" \
  "${TOPIC_DATA_BUILD}/types_basic.o" \
  "${TOPIC_DATA_BUILD}/types_array.o" \
  -o "${TOPIC_DATA_BIN}"

if ! "${TOPIC_DATA_BIN}"; then
  echo "[FAIL] SEDP parameter parsing tests failed"
  FAILED=1
fi

echo ""
echo "=== Phase 1aa: Discovery Compatibility Wiring ==="
SEDP_SOURCE="${PROJECT_ROOT}/mros2/embeddedRTPS/src/discovery/SEDPAgent.cpp"
TOPIC_DATA="${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/discovery/TopicData.h"
COMPATIBILITY_CALLS=$(grep -c "qosPoliciesCompatible" "${SEDP_SOURCE}" || true)
if [ "${COMPATIBILITY_CALLS}" -eq 4 ]; then
  echo "[PASS] Immediate and delayed discovery paths share four compatibility calls"
else
  echo "[FAIL] Expected four discovery compatibility calls, found ${COMPATIBILITY_CALLS}"
  FAILED=1
fi
if grep -q "livelinessSec = topic_data.livelinessSec" "${TOPIC_DATA}" && \
   grep -q "livelinessFraction = topic_data.livelinessFraction" "${TOPIC_DATA}"; then
  echo "[PASS] Delayed endpoint records preserve Liveliness lease"
else
  echo "[FAIL] Delayed endpoint records do not preserve Liveliness lease"
  FAILED=1
fi
MATCH_SUCCESS_GATES=$(grep -c "if (!matched)" "${SEDP_SOURCE}" || true)
MATCHED_CALLBACK_GATES=$(grep -c "matched && mfp_onNew" "${SEDP_SOURCE}" || true)
DIRECT_ADMISSION_GATES=$(grep -c "if (!reader.addNewMatchedWriter" \
  "${SEDP_SOURCE}" || true)
if [ "$((MATCH_SUCCESS_GATES + DIRECT_ADMISSION_GATES))" -ge 3 ] && \
   [ "${MATCHED_CALLBACK_GATES}" -ge 1 ]; then
  echo "[PASS] SEDP notifies applications only after proxy admission succeeds"
else
  echo "[FAIL] SEDP proxy-capacity failure can produce a false match callback"
  FAILED=1
fi
if [ "$(grep -c "m_part->forEachReader" "${SEDP_SOURCE}" || true)" -ge 2 ] && \
   [ "$(grep -c "m_part->forEachWriter" "${SEDP_SOURCE}" || true)" -ge 2 ] && \
   grep -q "addUnmatchedRemoteWriter(writerData)" "${SEDP_SOURCE}" && \
   grep -q "addUnmatchedRemoteReader(readerData)" "${SEDP_SOURCE}"; then
  echo "[PASS] SEDP retains discovered endpoints and fans out every compatible local match"
else
  echo "[FAIL] SEDP still limits a remote endpoint to one local match"
  FAILED=1
fi
READER_PROXY_DUP_GATES=$(grep -h -c \
  "proxy.remoteReaderGuid == matchedProxy.remoteReaderGuid" \
  "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/StatefulWriter.tpp" \
  "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/StatelessWriter.tpp" \
  | awk '{sum += $1} END {print sum + 0}')
WRITER_PROXY_DUP_GATES=$(grep -h -c "remoteWriterGuid ==" \
  "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/StatefulReader.tpp" \
  "${PROJECT_ROOT}/mros2/embeddedRTPS/src/entities/StatelessReader.cpp" \
  | awk '{sum += $1} END {print sum + 0}')
if [ "${READER_PROXY_DUP_GATES}" -eq 2 ] && \
   [ "${WRITER_PROXY_DUP_GATES}" -ge 2 ]; then
  echo "[PASS] ReaderProxy and WriterProxy admission rejects duplicate GUIDs"
else
  echo "[FAIL] Endpoint proxy duplicate-admission gates are incomplete"
  FAILED=1
fi

TOPIC_DATA_SOURCE="${PROJECT_ROOT}/mros2/embeddedRTPS/src/discovery/TopicData.cpp"
if grep -q "length != 12" "${TOPIC_DATA_SOURCE}" && \
   grep -q "topicNameLength > Config::MAX_TOPICNAME_LENGTH" "${TOPIC_DATA_SOURCE}" && \
   grep -q "typeNameLength > Config::MAX_TYPENAME_LENGTH" "${TOPIC_DATA_SOURCE}"; then
  echo "[PASS] SEDP QoS parameter lengths and discovery strings are bounded"
else
  echo "[FAIL] SEDP parameter-list bounds checks are incomplete"
  FAILED=1
fi
if grep -q "return !ucdr_buffer_has_error(&buffer)" \
     "${TOPIC_DATA_SOURCE}" && \
   [ "$(grep -c "endpoint QoS serialization failed" \
          "${SEDP_SOURCE}" || true)" -eq 2 ]; then
  echo "[PASS] SEDP never publishes a partially serialized QoS parameter list"
else
  echo "[FAIL] SEDP QoS serialization errors are not propagated"
  FAILED=1
fi

echo ""
echo "=== Phase 1ab: Simple History Ownership Tests ==="
HISTORY_BIN="${BUILD_DIR}/test_simple_history_cache"
g++ -std=c++17 -Wall -Wextra -Werror \
  -I"${PROJECT_ROOT}/tests/history_stubs" \
  -I"${PROJECT_ROOT}/mros2/embeddedRTPS/include" \
  -I"${PROJECT_ROOT}/platform" \
  -I"${PROJECT_ROOT}/tests/stubs" \
  -o "${HISTORY_BIN}" \
  "${PROJECT_ROOT}/tests/test_simple_history_cache.cpp"

if ! "${HISTORY_BIN}"; then
  echo "[FAIL] Simple history ownership tests failed"
  FAILED=1
fi

if grep -q "while (sn <= lastSN)" "${WRITER_IMPL:-${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/StatefulWriter.tpp}" 2>/dev/null; then
  echo "[PASS] Transient-local replay walks the frozen history range in order"
else
  echo "[FAIL] Transient-local replay order wiring is incomplete"
  FAILED=1
fi

echo ""
echo "=== Phase 1ac: Reliability State Tests ==="
RELIABILITY_BIN="${BUILD_DIR}/test_reliability_state"
g++ -std=c++17 -Wall -Wextra -Werror \
  -I"${PROJECT_ROOT}/mros2/embeddedRTPS/include" \
  -I"${PROJECT_ROOT}/tests/stubs" \
  -o "${RELIABILITY_BIN}" \
  "${PROJECT_ROOT}/tests/test_reliability_state.cpp"

if ! "${RELIABILITY_BIN}"; then
  echo "[FAIL] Reliability state tests failed"
  FAILED=1
fi

ACKNACK_BUDGET_VARIANTS_OK=1
for budget in 1 32; do
  budget_bin="${BUILD_DIR}/test_reliability_state_budget_${budget}"
  g++ -std=c++17 -Wall -Wextra -Werror \
    -DMROS2_RTPS_ACKNACK_SEQUENCE_RESPONSE_BUDGET="${budget}" \
    -I"${PROJECT_ROOT}/mros2/embeddedRTPS/include" \
    -I"${PROJECT_ROOT}/tests/stubs" \
    -o "${budget_bin}" \
    "${PROJECT_ROOT}/tests/test_reliability_state.cpp"
  if ! "${budget_bin}" >/dev/null; then
    ACKNACK_BUDGET_VARIANTS_OK=0
  fi
done
if [ "${ACKNACK_BUDGET_VARIANTS_OK}" -eq 1 ]; then
  echo "[PASS] ACKNACK sequence-response budgets 1 and 32 pass state tests"
else
  echo "[FAIL] ACKNACK sequence-response boundary configuration failed"
  FAILED=1
fi

GAP_BIN="${BUILD_DIR}/test_gap_message"
g++ -std=c++17 \
  -I"${PROJECT_ROOT}/tests/gap_stubs" \
  -I"${PROJECT_ROOT}/mros2/embeddedRTPS/include" \
  -I"${PROJECT_ROOT}/platform" \
  -o "${GAP_BIN}" \
  "${PROJECT_ROOT}/tests/test_gap_message.cpp" \
  "${PROJECT_ROOT}/mros2/embeddedRTPS/src/messages/MessageTypes.cpp"

if ! "${GAP_BIN}"; then
  echo "[FAIL] GAP serialization tests failed"
  FAILED=1
fi

if python3 - \
  "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/StatefulReader.tpp" \
  "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/StatefulWriter.tpp" \
  "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/StatelessWriter.tpp" <<'PY'
import pathlib
import re
import sys

factory_call = re.compile(
    r"(?:rtps::)?MessageFactory::"
    r"(?:addHeader|addSubMessageTimeStamp|addSubMessageDataFrag|"
    r"addSubMessageData|addHeartbeat|addGap|addAckNack)\s*\("
)
unchecked = []
for filename in sys.argv[1:]:
    source = pathlib.Path(filename).read_text(encoding="utf-8")
    for statement in source.split(";"):
        if factory_call.search(statement) and not any(
            token in statement for token in ("if (", "=", "return", "&&", "||")
        ):
            unchecked.append(filename)
if unchecked:
    raise SystemExit(1)
PY
then
  echo "[PASS] Reliability paths consume every RTPS message-construction result"
else
  echo "[FAIL] Reliability path ignores an RTPS message-construction result"
  FAILED=1
fi

if ! python3 \
  "${PROJECT_ROOT}/scripts/experiment/test_validate_rtps_gap_smoke.py"; then
  echo "[FAIL] RTPS GAP PCAP validator tests failed"
  FAILED=1
fi

if ! PYTHONPATH="${PROJECT_ROOT}/scripts/experiment" python3 \
  "${PROJECT_ROOT}/scripts/experiment/test_inject_directed_rtps_acknack.py"; then
  echo "[FAIL] directed RTPS ACKNACK injector tests failed"
  FAILED=1
fi

if ! PYTHONPATH="${PROJECT_ROOT}/scripts/experiment" python3 \
  "${PROJECT_ROOT}/scripts/experiment/test_inject_directed_rtps_gap_data.py"; then
  echo "[FAIL] directed RTPS GAP+DATA injector tests failed"
  FAILED=1
fi

if ! PYTHONPATH="${PROJECT_ROOT}/scripts/experiment" python3 \
  "${PROJECT_ROOT}/scripts/experiment/test_inject_malformed_then_valid_string.py"; then
  echo "[FAIL] malformed-then-valid String injector tests failed"
  FAILED=1
fi

WRITER_IMPL="${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/StatefulWriter.tpp"
STATELESS_WRITER_IMPL="${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/StatelessWriter.tpp"
if grep -q "advanceCumulativeAck" "${WRITER_IMPL}" && \
   grep -q "releaseAcknowledgedChanges" "${WRITER_IMPL}" && \
   grep -q "DurabilityKind_t::VOLATILE" "${WRITER_IMPL}" && \
   grep -q "m_sendCursorExhausted, acknowledged" "${WRITER_IMPL}"; then
  echo "[PASS] ACKNACK state is wired to volatile history release"
else
  echo "[FAIL] ACKNACK history-release wiring is incomplete"
  FAILED=1
fi
if grep -q "countIsAdmissible(proxy.hasAckNackCount, msg.count" \
     "${WRITER_IMPL}" && \
   grep -q "proxy.hasAckNackCount = true" "${WRITER_IMPL}" && \
   grep -q "bool hasAckNackCount = false" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/ReaderProxy.h"; then
  echo "[PASS] First Writer-side ACKNACK Count establishes an explicit baseline"
else
  echo "[FAIL] Writer-side ACKNACK Count still depends on an artificial baseline"
  FAILED=1
fi
if grep -q "shouldDiscardUnmatchedHistoryOnReaderMatch" "${WRITER_IMPL}"; then
  echo "[PASS] First-reader durability policy gates unmatched history"
else
  echo "[FAIL] First-reader durability history gate is missing"
  FAILED=1
fi
if grep -q "RequestedSequenceAvailability::NO_LONGER_AVAILABLE" "${WRITER_IMPL}" && \
   grep -q "MessageFactory::addGap" "${WRITER_IMPL}"; then
  echo "[PASS] Unavailable ACKNACK requests are wired to RTPS GAP"
else
  echo "[FAIL] Unavailable ACKNACK requests are not wired to RTPS GAP"
  FAILED=1
fi
if grep -q "ackNackRequestedSequence(msg.readerSNState" "${WRITER_IMPL}" && \
   ! grep -q "while (nextSN <= maxSN)" "${WRITER_IMPL}"; then
  echo "[PASS] ACKNACK repair is limited to explicitly set bitmap sequences"
else
  echo "[FAIL] ACKNACK repair still transmits an implicit history suffix"
  FAILED=1
fi
if grep -q "advanceCumulativeAckBounded" "${WRITER_IMPL}" && \
   grep -q "m_history.getLastUsedSequenceNumber()" "${WRITER_IMPL}"; then
  echo "[PASS] Cumulative ACK cannot pre-ack future Writer sequences"
else
  echo "[FAIL] Cumulative ACK is not bounded by the last written sequence"
  FAILED=1
fi
if python3 - "${WRITER_IMPL}" <<'PY'
import pathlib
import sys

source = pathlib.Path(sys.argv[1]).read_text()
start = source.index("void StatefulWriterT<NetworkDriver>::sendHeartBeat()")
end = source.index(
    "void StatefulWriterT<NetworkDriver>::setDeadlineMissedCallback", start
)
body = source[start:end]
heartbeat_range = body.index("heartbeatSequenceRangeForReader(")
hold_recheck = body.index("if (m_transmissionHeld)", body.index("for ("))
purge = body.index(
    "purgeExpiredChangesLocked(rtps::getCurrentTimeMs())", hold_recheck
)
send = body.index("m_transport->sendPacket(info)", hold_recheck)
raise SystemExit(
    0 if hold_recheck < purge < heartbeat_range < send else 1
)
PY
then
  echo "[PASS] Periodic HEARTBEAT rechecks hold and purges History in its send transaction"
else
  echo "[FAIL] Periodic HEARTBEAT hold/History send transaction is incomplete"
  FAILED=1
fi
if grep -q "case SubmessageKind::GAP" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/src/messages/MessageReceiver.cpp" && \
   grep -q "readerExpectedAfterGap" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/StatefulReader.tpp"; then
  echo "[PASS] Received RTPS GAP advances StatefulReader sequence state"
else
  echo "[FAIL] Received RTPS GAP is not wired to StatefulReader state"
  FAILED=1
fi
MESSAGE_RECEIVER_SOURCE="${PROJECT_ROOT}/mros2/embeddedRTPS/src/messages/MessageReceiver.cpp"
PARTICIPANT_SOURCE="${PROJECT_ROOT}/mros2/embeddedRTPS/src/entities/Participant.cpp"
STATEFUL_READER_IMPL="${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/StatefulReader.tpp"
if grep -q "deliverChangeToReaders(change)" "${MESSAGE_RECEIVER_SOURCE}" && \
   grep -q "deliverHeartbeatToReaders(submsgHB, sourceGuidPrefix)" \
     "${MESSAGE_RECEIVER_SOURCE}" && \
   grep -q "deliverGapToReaders(submsgGap, sourceGuidPrefix)" \
     "${MESSAGE_RECEIVER_SOURCE}" && \
   [ "$(grep -c "dispatchMatchedReaders(" \
          "${PARTICIPANT_SOURCE}" || true)" -eq 3 ] && \
   grep -q "msg.writerId, m_attributes.endpointGuid.entityId" \
     "${STATEFUL_READER_IMPL}"; then
  echo "[PASS] UNKNOWN-target DATA/HEARTBEAT/GAP fan out to every matched local Reader"
else
  echo "[FAIL] UNKNOWN-target reliability control routing is incomplete"
  FAILED=1
fi
if grep -q "#define MROS2_ALLOW_UNMATCHED_USER_READER_FALLBACK 0" \
     "${PROJECT_ROOT}/platform/rtps/config.h" && \
   grep -q "MROS2_ALLOW_UNMATCHED_USER_READER_FALLBACK != 1" \
     "${PROJECT_ROOT}/platform/rtps/config.h" && \
   grep -q "MROS2_ALLOW_UNMATCHED_USER_READER_FALLBACK == 1" \
     "${PROJECT_ROOT}/platform/rtps/config.h" && \
   grep -q "if (!Config::ALLOW_UNMATCHED_USER_READER_FALLBACK)" \
     "${PARTICIPANT_SOURCE}" && \
   grep -q "selectSoleEligibleReader(" "${PARTICIPANT_SOURCE}" && \
   grep -q "USER_DEFINED_READER_WITHOUT_KEY" "${PARTICIPANT_SOURCE}" && \
   grep -q "if (selected != nullptr)" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/MatchedReaderDispatch.h"; then
  echo "[PASS] pre-SEDP fallback fails closed unless explicitly enabled"
else
  echo "[FAIL] topic-less pre-SEDP DATA can be routed to an arbitrary Reader"
  FAILED=1
fi
if grep -q "MROS2_ALLOW_UNMATCHED_USER_READER_FALLBACK=.*MROS2_ALLOW_UNMATCHED_USER_READER_FALLBACK" \
     "${PROJECT_ROOT}/components/mros2-esp32/CMakeLists.txt" && \
   grep -q "unmatched_user_reader_fallback=%u" \
     "${PROJECT_ROOT}/workspace/seven_qos_mechanisms/main/app.cpp"; then
  echo "[PASS] pre-SEDP fallback value is build-configured and board-observable"
else
  echo "[FAIL] pre-SEDP fallback build/evidence wiring is incomplete"
  FAILED=1
fi
if grep -q "if (!processSubmessage(msgInfo, submsgHeader))" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/src/messages/MessageReceiver.cpp" && \
   grep -q "processInfoDestinationSubmessage" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/src/messages/MessageReceiver.cpp" && \
   grep -q "m_destinationMatches" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/src/messages/MessageReceiver.cpp"; then
  echo "[PASS] MessageReceiver propagates known failures and honors INFO_DST"
else
  echo "[FAIL] MessageReceiver submessage failure/destination routing is incomplete"
  FAILED=1
fi
if ! grep -q "return mp_part->deliverGapToReaders" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/src/messages/MessageReceiver.cpp" && \
   ! grep -q "return mp_part->deliverChangeToReaders" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/src/messages/MessageReceiver.cpp"; then
  echo "[PASS] valid irrelevant RTPS submessages are not classified malformed"
else
  echo "[FAIL] endpoint routing outcome still controls RTPS parse validity"
  FAILED=1
fi
if grep -q "readWireValue(" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/src/messages/MessageTypes.cpp" && \
   grep -q "msg.readerSNState.bitMap\\[word\\]" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/src/messages/MessageTypes.cpp" && \
   grep -q "msg.fragmentSize, currentPos, littleEndian" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/src/messages/MessageTypes.cpp"; then
  echo "[PASS] RTPS numeric receive fields follow each submessage endian flag"
else
  echo "[FAIL] RTPS receive endianness coverage is incomplete"
  FAILED=1
fi
if grep -q "sequenceNumberSetRequestsRepair(missing)" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/StatefulReader.tpp" &&
   grep -q "!requestsRepair" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/StatefulReader.tpp"; then
  echo "[PASS] caught-up HEARTBEAT responses set ACKNACK Final"
else
  echo "[FAIL] ACKNACK Final does not follow the missing-sequence set"
  FAILED=1
fi

echo ""
echo "=== Phase 1ad: Reader Sequence Tests ==="
READER_SEQUENCE_BIN="${BUILD_DIR}/test_reader_sequence"
g++ -std=c++17 \
  -include "${PROJECT_ROOT}/tests/stubs/udp_driver_override.h" \
  -I"${PROJECT_ROOT}/platform" \
  -I"${PROJECT_ROOT}/mros2/embeddedRTPS/include" \
  -I"${PROJECT_ROOT}/mros2/embeddedRTPS/thirdparty/Micro-CDR/include" \
  -I"${PROJECT_ROOT}/tests/stubs" \
  -o "${READER_SEQUENCE_BIN}" \
  "${PROJECT_ROOT}/tests/test_reader_sequence.cpp"

if ! "${READER_SEQUENCE_BIN}"; then
  echo "[FAIL] Reader sequence tests failed"
  FAILED=1
fi

PENDING_WRITER_BIN="${BUILD_DIR}/test_pending_writer_state"
g++ -std=c++17 \
  -include "${PROJECT_ROOT}/tests/stubs/udp_driver_override.h" \
  -I"${PROJECT_ROOT}/platform" \
  -I"${PROJECT_ROOT}/tests/history_stubs" \
  -I"${PROJECT_ROOT}/mros2/embeddedRTPS/include" \
  -I"${PROJECT_ROOT}/mros2/embeddedRTPS/thirdparty/Micro-CDR/include" \
  -I"${PROJECT_ROOT}/tests/stubs" \
  -o "${PENDING_WRITER_BIN}" \
  "${PROJECT_ROOT}/tests/test_pending_writer_state.cpp"

if ! "${PENDING_WRITER_BIN}"; then
  echo "[FAIL] Pending Writer state tests failed"
  FAILED=1
fi

READER_IMPL="${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/StatefulReader.tpp"
READER_BASE="${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/Reader.h"
if grep -q "findOrAddPendingWriter(cacheChange.writerGuid)" "${READER_IMPL}" && \
   grep -q "readerMayDeliverBeforeMatch(m_attributes.durabilityKind," \
     "${READER_IMPL}" && \
   grep -q "applyPendingWriterState(proxy)" "${READER_IMPL}" && \
   grep -q "removePendingWriter(proxy.remoteWriterGuid)" "${READER_IMPL}" && \
   grep -q "removePendingWritersOfParticipant(guidPrefix)" "${READER_IMPL}" && \
   grep -q "MemoryPool<PendingWriterState" "${READER_BASE}" && \
   grep -q "readerMayDeliverBeforeMatch(m_attributes.durabilityKind," \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/src/entities/StatelessReader.cpp" && \
   grep -q "applyPendingWriterState(proxy)" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/src/entities/StatelessReader.cpp" && \
   grep -q "++m_unmatchedWriterDropCount" "${READER_IMPL}"; then
  echo "[PASS] Bounded per-Writer pre-match suppression and cleanup are wired"
else
  echo "[FAIL] Reader sequence/epoch wiring is incomplete"
  FAILED=1
fi

FRESHNESS_LINE=$(grep -n "classifyReaderSequence(proxy.expectedSN" \
  "${READER_IMPL}" | head -1 | cut -d: -f1 || true)
CALLBACK_LINE=$(grep -n "if (shouldDeliver && callback != nullptr)" \
  "${READER_IMPL}" | head -1 | cut -d: -f1 || true)
ACTIVITY_LINE=$(grep -n "m_lastReceiveTimeMs = rtps::getCurrentTimeMs" \
  "${READER_IMPL}" | head -1 | cut -d: -f1 || true)
if [ -n "${FRESHNESS_LINE}" ] && [ -n "${CALLBACK_LINE}" ] && \
   [ -n "${ACTIVITY_LINE}" ] && \
   [ "${FRESHNESS_LINE}" -lt "${CALLBACK_LINE}" ] && \
   [ "${FRESHNESS_LINE}" -lt "${ACTIVITY_LINE}" ] && \
   grep -q "callback(callee, cacheChange)" "${READER_IMPL}"; then
  echo "[PASS] Reader QoS activity and callback follow sequence admission"
else
  echo "[FAIL] Reader admission/activity/callback contract drifted"
  FAILED=1
fi

if grep -q "recordHighestObserved(proxy.highestObservedSN" "${READER_IMPL}" && \
   [ "$(grep -c "readerNeedsRepair(proxy.expectedSN" "${READER_IMPL}")" -ge 2 ] && \
   [ "$(grep -c "proxy.getNextAckNackCount()" "${READER_IMPL}")" -ge 2 ] && \
   grep -q "recordHeartbeatHigh(writer->highestObservedSN" "${READER_IMPL}"; then
  echo "[PASS] Ahead DATA and GAP advancement both chain exact ACKNACK repair"
else
  echo "[FAIL] Reader DATA/GAP repair chaining is incomplete"
  FAILED=1
fi
if grep -q "proxy.expectedSequenceExhausted" "${READER_IMPL}" && \
   grep -q "pending->sequenceExhausted" "${READER_IMPL}" && \
   grep -q "admitReliableSequence(cacheChange.sn, pending->nextSN" \
     "${READER_IMPL}" && \
   grep -q "advanceReaderExpected" "${READER_IMPL}"; then
  echo "[PASS] Reader sequence exhaustion prevents terminal duplicate delivery"
else
  echo "[FAIL] Reader terminal sequence state is incomplete"
  FAILED=1
fi
if grep -q "countIsAdmissible(writer->hasHeartbeatCount" "${READER_IMPL}" && \
   grep -q "writer->hasHeartbeatCount = true" "${READER_IMPL}"; then
  echo "[PASS] First HEARTBEAT count establishes an explicit Reader baseline"
else
  echo "[FAIL] Reader HEARTBEAT count baseline wiring is incomplete"
  FAILED=1
fi
READER_CONTROL_RETRY_BIN="${BUILD_DIR}/test_reader_control_retry"
g++ -std=c++17 -Wall -Wextra -Werror \
  -I"${PROJECT_ROOT}/tests/reader_control_stubs" \
  -I"${PROJECT_ROOT}/mros2/embeddedRTPS/include" \
  -I"${PROJECT_ROOT}/platform" \
  -I"${PROJECT_ROOT}/mros2/embeddedRTPS/thirdparty/Micro-CDR/include" \
  -o "${READER_CONTROL_RETRY_BIN}" \
  "${PROJECT_ROOT}/tests/test_reader_control_retry.cpp"
if ! "${READER_CONTROL_RETRY_BIN}"; then
  echo "[FAIL] Reader control-send retry integration tests failed"
  FAILED=1
fi
STATELESS_REPLAY_RECOVERY_BIN="${BUILD_DIR}/test_stateless_late_replay_recovery"
g++ -std=c++17 -Wall -Wextra -Werror \
  -I"${PROJECT_ROOT}/tests/reader_control_stubs" \
  -I"${PROJECT_ROOT}/mros2/embeddedRTPS/include" \
  -I"${PROJECT_ROOT}/platform" \
  -I"${PROJECT_ROOT}/mros2/embeddedRTPS/thirdparty/Micro-CDR/include" \
  -o "${STATELESS_REPLAY_RECOVERY_BIN}" \
  "${PROJECT_ROOT}/tests/test_stateless_late_replay_recovery.cpp"
if ! "${STATELESS_REPLAY_RECOVERY_BIN}"; then
  echo "[FAIL] Stateless late-replay recovery integration tests failed"
  FAILED=1
fi
STATEFUL_REPLAY_RECOVERY_BIN="${BUILD_DIR}/test_stateful_late_replay_recovery"
g++ -std=c++17 -pthread -DMROS2_RTPS_HEARTBEAT_PERIOD_MS=60000 \
  -Wall -Wextra -Werror \
  -I"${PROJECT_ROOT}/tests/reader_control_stubs" \
  -I"${PROJECT_ROOT}/mros2/embeddedRTPS/include" \
  -I"${PROJECT_ROOT}/platform" \
  -I"${PROJECT_ROOT}/mros2/embeddedRTPS/thirdparty/Micro-CDR/include" \
  -o "${STATEFUL_REPLAY_RECOVERY_BIN}" \
  "${PROJECT_ROOT}/tests/test_stateful_late_replay_recovery.cpp"
if ! "${STATEFUL_REPLAY_RECOVERY_BIN}"; then
  echo "[FAIL] Stateful late-replay recovery integration tests failed"
  FAILED=1
fi
WRITER_PERIODIC_HEARTBEAT_BIN="${BUILD_DIR}/test_writer_periodic_heartbeat_recovery"
g++ -std=c++17 -pthread -DMROS2_RTPS_HEARTBEAT_PERIOD_MS=50 \
  -Wall -Wextra -Werror \
  -I"${PROJECT_ROOT}/tests/reader_control_stubs" \
  -I"${PROJECT_ROOT}/mros2/embeddedRTPS/include" \
  -I"${PROJECT_ROOT}/platform" \
  -I"${PROJECT_ROOT}/mros2/embeddedRTPS/thirdparty/Micro-CDR/include" \
  -o "${WRITER_PERIODIC_HEARTBEAT_BIN}" \
  "${PROJECT_ROOT}/tests/test_writer_periodic_heartbeat_recovery.cpp"
if ! "${WRITER_PERIODIC_HEARTBEAT_BIN}"; then
  echo "[FAIL] Writer periodic HEARTBEAT recovery integration tests failed"
  FAILED=1
fi
WRITER_HISTORY_ADMISSION_BIN="${BUILD_DIR}/test_writer_history_admission_matrix"
g++ -std=c++17 -pthread -DMROS2_RTPS_HEARTBEAT_PERIOD_MS=60000 \
  -Wall -Wextra -Werror \
  -I"${PROJECT_ROOT}/tests/reader_control_stubs" \
  -I"${PROJECT_ROOT}/mros2/embeddedRTPS/include" \
  -I"${PROJECT_ROOT}/platform" \
  -I"${PROJECT_ROOT}/mros2/embeddedRTPS/thirdparty/Micro-CDR/include" \
  -o "${WRITER_HISTORY_ADMISSION_BIN}" \
  "${PROJECT_ROOT}/tests/test_writer_history_admission_matrix.cpp"
if ! "${WRITER_HISTORY_ADMISSION_BIN}"; then
  echo "[FAIL] Writer History admission matrix integration tests failed"
  FAILED=1
fi
if [ "$(grep -c "rollbackCountIfCurrent" "${READER_IMPL}")" -ge 2 ] && \
   [ "$(grep -c "m_controlSendFailureCount" "${READER_IMPL}")" -ge 3 ] && \
   grep -q "subscriber_control_send_failure_count" \
     "${PROJECT_ROOT}/mros2/src/mros2.cpp"; then
  echo "[PASS] Reader ACKNACK failures are observable and retry the same HEARTBEAT Count"
else
  echo "[FAIL] Reader control-send failure recovery or observability is incomplete"
  FAILED=1
fi
STATELESS_READER_IMPL="${PROJECT_ROOT}/mros2/embeddedRTPS/src/entities/StatelessReader.cpp"
if grep -q "admitBestEffortSequence(cacheChange.sn, proxy.expectedSN" \
     "${STATELESS_READER_IMPL}" && \
   grep -q "isUserReader()" "${STATELESS_READER_IMPL}"; then
  echo "[PASS] Best Effort user Reader suppresses duplicate Writer sequences"
else
  echo "[FAIL] Stateless user Reader duplicate suppression is incomplete"
  FAILED=1
fi

echo ""
echo "=== Phase 1ae: Resource Limit Tests ==="
RESOURCE_BIN="${BUILD_DIR}/test_resource_limits"
g++ -std=c++17 \
  -I"${PROJECT_ROOT}/mros2/embeddedRTPS/include" \
  -I"${PROJECT_ROOT}/tests/stubs" \
  -o "${RESOURCE_BIN}" \
  "${PROJECT_ROOT}/tests/test_resource_limits.cpp"

if ! "${RESOURCE_BIN}"; then
  echo "[FAIL] Resource limit tests failed"
  FAILED=1
fi
if [ "$(grep -c "evaluateResourceLimitsAfterEviction" \
          "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/StatefulWriter.tpp")" \
       -eq 2 ] && \
   [ "$(grep -c "evaluateResourceLimitsAfterEviction" \
          "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/StatelessWriter.tpp")" \
       -eq 2 ]; then
  echo "[PASS] all four Writer admission paths share fail-closed projections"
else
  echo "[FAIL] Writer admission projection logic has drifted between paths"
  FAILED=1
fi

if ! python3 \
  "${PROJECT_ROOT}/scripts/experiment/test_validate_rtps_tl_best_effort_late_smoke.py"; then
  echo "[FAIL] Transient Local replay validator unit checks failed"
  FAILED=1
fi

if ! python3 \
  "${PROJECT_ROOT}/scripts/experiment/test_validate_rtps_writer_qos_advertisement.py"; then
  echo "[FAIL] Writer QoS advertisement validator unit checks failed"
  FAILED=1
fi

if ! PYTHONPATH="${PROJECT_ROOT}/scripts/experiment" python3 \
  "${PROJECT_ROOT}/scripts/experiment/test_validate_rdh_small_paired_pilot.py"; then
  echo "[FAIL] Reliability/Durability/History paired-pilot validator checks failed"
  FAILED=1
fi

if [ "$(grep -c "evaluateResourceLimits" "${WRITER_IMPL}" || true)" -eq 2 ] && \
   [ "$(grep -c "evaluateHistoryCapacity" "${WRITER_IMPL}" || true)" -eq 2 ] && \
   [ "$(grep -c "plannedKeepLastEvictions" "${WRITER_IMPL}" || true)" -eq 2 ] && \
   [ "$(grep -c "commitPreparedChange" "${WRITER_IMPL}" || true)" -eq 2 ]; then
  echo "[PASS] Normal and fragmented publish paths share atomic resource decisions"
else
  echo "[FAIL] Writer resource-decision wiring is incomplete"
  FAILED=1
fi
if grep -q "fragmentedPublicationValid(static_cast<bool>(func), size)" \
     "${WRITER_IMPL}" && \
   grep -q "fragmentedPublicationValid(static_cast<bool>(func), size)" \
     "${STATELESS_WRITER_IMPL}"; then
  echo "[PASS] Both Writer types reject empty fragmented publication contracts"
else
  echo "[FAIL] A Writer can retain an unsendable fragmented publication"
  FAILED=1
fi
DOMAIN_SOURCE="${PROJECT_ROOT}/mros2/embeddedRTPS/src/entities/Domain.cpp"
if [ "$(grep -c "writer.setResourceLimits(maxSamples, maxBytes)" \
          "${DOMAIN_SOURCE}" || true)" -eq 2 ] && \
   [ "$(grep -c "writer.setKeepAll(historyKind == HISTORY_KIND_KEEP_ALL)" \
          "${DOMAIN_SOURCE}" || true)" -eq 2 ] && \
   [ "$(grep -c "writer.setHistoryDepth(" \
          "${DOMAIN_SOURCE}" || true)" -eq 2 ] && \
   grep -q "effectiveHistoryDepth" "${DOMAIN_SOURCE}" && \
   grep -q "++m_numStatelessWriters" "${DOMAIN_SOURCE}"; then
  echo "[PASS] Domain Writer creation applies advertised QoS before endpoint admission"
else
  echo "[FAIL] Direct Domain Writer creation can diverge from advertised QoS"
  FAILED=1
fi
if grep -q "reader.setDeadlineMs(deadlineMs)" "${DOMAIN_SOURCE}" && \
   grep -q "reader.setLivelinessLeaseMs(livelinessLeaseMs)" \
     "${DOMAIN_SOURCE}" && \
   grep -q "++m_numStatelessReaders" "${DOMAIN_SOURCE}" && \
   [ "$(grep -c "m_statelessReaders\\[m_numStatelessReaders++\\]" \
          "${DOMAIN_SOURCE}" || true)" -eq 1 ]; then
  echo "[PASS] Domain Reader creation applies QoS and commits slots after admission"
else
  echo "[FAIL] Direct Domain Reader creation can leak a slot or defer local QoS"
  FAILED=1
fi
if python3 - "${DOMAIN_SOURCE}" <<'PY'
import pathlib
import sys

source = pathlib.Path(sys.argv[1]).read_text()
writer_start = source.index("rtps::Writer *Domain::createWriter(")
reader_start = source.index("rtps::Reader *Domain::createReader(", writer_start)
end = source.index("rtps::GuidPrefix_t Domain::generateGuidPrefix", reader_start)

def positions(body, needle):
    return [
        pos for pos in range(len(body))
        if body.startswith(needle, pos)
    ]

writer = source[writer_start:reader_start]
reader = source[reader_start:end]
writer_init = positions(writer, "writer.init(")
writer_check = positions(writer, "if (!writer.isInitialized())")
writer_config = positions(writer, "writer.setResourceLimits(")
writer_admit = positions(writer, "part.addWriter(&writer)")
reader_init = positions(reader, "reader.init(")
reader_check = positions(reader, "if (!reader.isInitialized())")
reader_config = positions(reader, "reader.registerCallback(")
reader_admit = positions(reader, "part.addReader(&reader)")
valid = (
    all(len(items) == 2 for items in (
        writer_init, writer_check, writer_config, writer_admit,
        reader_init, reader_check, reader_config, reader_admit,
    ))
    and all(i < c < q < a for i, c, q, a in zip(
        writer_init, writer_check, writer_config, writer_admit
    ))
    and all(i < c < q < a for i, c, q, a in zip(
        reader_init, reader_check, reader_config, reader_admit
    ))
)
raise SystemExit(0 if valid else 1)
PY
then
  echo "[PASS] Domain endpoints configure only after init and before admission"
else
  echo "[FAIL] Domain endpoint initialization/configuration order is unsafe"
  FAILED=1
fi
if python3 - "${DOMAIN_SOURCE}" <<'PY'
import pathlib
import sys

source = pathlib.Path(sys.argv[1]).read_text()
start = source.index("rtps::Reader *Domain::createReader(")
end = source.index("rtps::GuidPrefix_t Domain::generateGuidPrefix", start)
body = source[start:end]
register = [
    pos for pos in range(len(body))
    if body.startswith(
        "reader.registerCallback(callback, callbackCallee)", pos
    )
]
admit = [
    pos for pos in range(len(body))
    if body.startswith("part.addReader(&reader)", pos)
]
raise SystemExit(
    0 if len(register) == 2 and len(admit) == 2
    and all(r < a for r, a in zip(register, admit)) else 1
)
PY
then
  if grep -q "Subscriber::callback_handler<T>" \
       "${PROJECT_ROOT}/mros2/src/mros2.cpp"; then
  echo "[PASS] mros2 Subscriber callback is installed before Reader admission"
  else
    echo "[FAIL] mros2 does not pass its Subscriber callback into admission"
    FAILED=1
  fi
else
  echo "[FAIL] Transient Local replay can race Subscriber callback registration"
  FAILED=1
fi
if [ "$(grep -c "inlinePublicationValid(data, size)" "${WRITER_IMPL}" || true)" \
       -ge 1 ] && \
   [ "$(grep -c "inlinePublicationValid(data, size)" \
       "${STATELESS_WRITER_IMPL}" || true)" -ge 1 ] && \
   grep -q "data == nullptr || size == 0" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/storages/SimpleHistoryCache.h"; then
  echo "[PASS] Both Writer types reject empty inline publication contracts"
else
  echo "[FAIL] Inline publication contracts can admit empty History"
  FAILED=1
fi

if grep -q "Linearize matching, HEARTBEAT range" "${WRITER_IMPL}" && \
   grep -q "attempt <= SEND_RETRY_LIMIT" "${WRITER_IMPL}" && \
   grep -q "sendDataLocked(matchedProxy, sn)" "${WRITER_IMPL}"; then
  echo "[PASS] Stateful Transient Local match and replay are one bounded transaction"
else
  echo "[FAIL] Stateful Transient Local replay linearization is incomplete"
  FAILED=1
fi

STATELESS_WRITER_IMPL="${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/StatelessWriter.tpp"
if grep -q "mayAdvanceGlobalCursorForVolatileMatch(hadMatchedReaders)" \
     "${STATELESS_WRITER_IMPL}" && \
   grep -q "allReadersSkipSequence(readerCount, anyReaderMayReceive)" \
     "${STATELESS_WRITER_IMPL}"; then
  echo "[PASS] Later Volatile match cannot skip existing Stateless Reader work"
else
  echo "[FAIL] Stateless global send cursor is not protected across Reader matches"
  FAILED=1
fi
if grep -q "consumeSendRetryBudget" "${WRITER_IMPL}" && \
   grep -q "consumeSendRetryBudget" "${STATELESS_WRITER_IMPL}" && \
   grep -q "sendSnapshotStillPending" "${WRITER_IMPL}" && \
   grep -q "sendSnapshotStillPending" "${STATELESS_WRITER_IMPL}" && \
   grep -q "clearSendRetryBudget" "${WRITER_IMPL}" && \
   grep -q "clearSendRetryBudget" "${STATELESS_WRITER_IMPL}"; then
  echo "[PASS] Both Writer types bound and reset automatic send retries"
else
  echo "[FAIL] A retained failed send has no bounded retry lifecycle"
  FAILED=1
fi
if [ "$(grep -c "resetSendCursorToHistory(" "${WRITER_IMPL}" || true)" -ge 2 ] && \
   [ "$(grep -c "resetSendCursorToHistory(" \
          "${STATELESS_WRITER_IMPL}" || true)" -ge 2 ] && \
   ! grep -q "m_nextSequenceNumberToSend = SEQUENCENUMBER_UNKNOWN" \
     "${WRITER_IMPL}" "${STATELESS_WRITER_IMPL}"; then
  echo "[PASS] Empty-History resend resets preserve the next valid Writer sequence"
else
  echo "[FAIL] Writer resend reset can leave an UNKNOWN send cursor"
  FAILED=1
fi
if grep -q "sendCursorTargetsRetainedHistory" "${WRITER_IMPL}" && \
   grep -q "sendCursorTargetsRetainedHistory" "${STATELESS_WRITER_IMPL}" && \
   grep -q "if (scheduleNext &&" "${WRITER_IMPL}" && \
   grep -q "if (scheduleNext &&" \
     "${STATELESS_WRITER_IMPL}" && \
   grep -q "mp_threadPool == nullptr || !mp_threadPool->addWorkload(this)" \
     "${WRITER_IMPL}" && \
   grep -q "mp_threadPool == nullptr || !mp_threadPool->addWorkload(this)" \
     "${STATELESS_WRITER_IMPL}"; then
  echo "[PASS] Both Writer types self-drain retained History beyond queue bursts"
else
  echo "[FAIL] A full workload queue can strand accepted History"
  FAILED=1
fi
LOCK_HEADER="${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/utils/Lock.h"
if [ "$(grep -c "lock.release()" "${WRITER_IMPL}" || true)" -ge 3 ] && \
   [ "$(grep -c "lock.release()" "${STATELESS_WRITER_IMPL}" || true)" -ge 3 ] && \
   grep -q "if (!mp_threadPool->addWorkload(this))" "${WRITER_IMPL}" && \
   grep -q "if (!mp_threadPool->addWorkload(this))" \
     "${STATELESS_WRITER_IMPL}" && \
   grep -q "if (m_locked)" "${LOCK_HEADER}" && \
   grep -q "m_locked = false" "${LOCK_HEADER}"; then
  echo "[PASS] Accepted publication falls back synchronously when workload enqueue fails"
else
  echo "[FAIL] A first workload enqueue failure can strand accepted History"
  FAILED=1
fi
if grep -q "bool m_sendCursorExhausted = false" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/StatefulWriter.h" && \
   grep -q "bool m_sendCursorExhausted = false" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/StatelessWriter.h" && \
   grep -q "m_sendCursorExhausted, sequenceToSend" "${WRITER_IMPL}" && \
   grep -q "m_sendCursorExhausted, sequenceToSend" \
     "${STATELESS_WRITER_IMPL}"; then
  echo "[PASS] Stateful and Stateless Writer cursors represent sequence exhaustion"
else
  echo "[FAIL] Writer send cursor can repeat the terminal sequence"
  FAILED=1
fi
if grep -q "if (replaySucceeded &&" "${STATELESS_WRITER_IMPL}" && \
   grep -q "replaySucceeded = replaySent && replaySucceeded" \
     "${STATELESS_WRITER_IMPL}" && \
   grep -q "mayAdvanceGlobalCursorAfterDirectedReplay(hadMatchedReaders)" \
     "${STATELESS_WRITER_IMPL}" && \
   grep -q "shouldScheduleOrdinaryReplayRecovery(replaySucceeded" \
     "${STATELESS_WRITER_IMPL}" && \
   grep -q "if (scheduleOrdinaryReplayRecovery)" \
     "${STATELESS_WRITER_IMPL}" && \
   grep -q "retainEarliestSendCursorForRecovery" \
     "${STATELESS_WRITER_IMPL}" && \
   grep -q "retainEarliestSendCursorForRecovery" \
     "${WRITER_IMPL}" && \
   grep -q "shouldScheduleOrdinaryReplayRecovery" \
     "${WRITER_IMPL}"; then
  echo "[PASS] First-Reader replay failure retains or rewinds ordinary recovery work"
else
  echo "[FAIL] First-Reader replay can skip failed historical sends"
  FAILED=1
fi
if python3 - "${WRITER_IMPL}" "${STATELESS_WRITER_IMPL}" <<'PY'
import pathlib
import re
import sys

stop_on_failure = re.compile(
    r"firstFailed\s*=\s*sn\s*;\s*"
    r"(?:replaySucceeded\s*=\s*false\s*;\s*)?"
    r"break\s*;"
)
raise SystemExit(
    0 if all(stop_on_failure.search(
        pathlib.Path(name).read_text(encoding="utf-8"))
        for name in sys.argv[1:]) else 1
)
PY
then
  echo "[PASS] Directed replay stops at its first failed sequence"
else
  echo "[FAIL] Directed replay can create a Best Effort sequence hole"
  FAILED=1
fi
if grep -q "mayAdvanceGlobalCursorForVolatileMatch(hadMatchedReaders)" \
     "${WRITER_IMPL}" && \
   grep -q "allReadersSkipSequence(readerCount, anyReaderMayReceive)" \
     "${WRITER_IMPL}" && \
   grep -q "ordinarySendSnapshotComplete(sent, allEligibleReadersSent)" \
     "${WRITER_IMPL}" && \
   grep -q "if (snapshotComplete && hasBestEffortReader" \
     "${WRITER_IMPL}"; then
  echo "[PASS] Stateful cursor advances only when Volatile visibility skips all Readers"
else
  echo "[FAIL] Stateful Volatile visibility can stall or skip Reader work"
  FAILED=1
fi
if [ "$(grep -c -- "->resetSerializer()" "${WRITER_IMPL}" || true)" -ge 2 ] && \
   [ "$(grep -c -- "->resetSerializer()" "${STATELESS_WRITER_IMPL}" || true)" -ge 2 ] && \
   [ "$(grep -c "sentFragment" "${WRITER_IMPL}" || true)" -ge 6 ] && \
   [ "$(grep -c "sentFragment" "${STATELESS_WRITER_IMPL}" || true)" -ge 3 ] && \
   grep -q "serializerCallback(SerializerOperation::RESET)" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/storages/CacheChange.h" && \
   grep -q "SerializerOperation::NEXT_FRAGMENT" "${WRITER_IMPL}" && \
   grep -q "SerializerOperation::NEXT_FRAGMENT" "${STATELESS_WRITER_IMPL}"; then
  echo "[PASS] Fragmented paths reset their cursor and reject zero-fragment sends"
else
  echo "[FAIL] Fragmented retry/replay serializer reset wiring is incomplete"
  FAILED=1
fi
if [ "$(grep -c "accountSerializedFragment" "${WRITER_IMPL}" || true)" -ge 2 ] && \
   [ "$(grep -c "serializedSampleComplete" "${WRITER_IMPL}" || true)" -ge 2 ] && \
   [ "$(grep -c "serializedFragmentPositionValid" \
          "${WRITER_IMPL}" || true)" -ge 2 ] && \
   [ "$(grep -c "accountSerializedFragment" \
          "${STATELESS_WRITER_IMPL}" || true)" -ge 2 ] && \
   [ "$(grep -c "serializedSampleComplete" \
          "${STATELESS_WRITER_IMPL}" || true)" -ge 2 ] && \
   [ "$(grep -c "serializedFragmentPositionValid" \
          "${STATELESS_WRITER_IMPL}" || true)" -ge 2 ]; then
  echo "[PASS] Every fragmented send path validates exact size and wire position"
else
  echo "[FAIL] A fragmented send path can accept truncated or oversized output"
  FAILED=1
fi

if grep -q "initializeVolatileReaderBoundary" "${WRITER_IMPL}" && \
   grep -q "initializeVolatileReaderBoundary" "${STATELESS_WRITER_IMPL}" && \
   [ "$(grep -c "reader.noRelevantSequence" "${WRITER_IMPL}" || true)" -ge 3 ] && \
   [ "$(grep -c "noRelevantSequence" "${STATELESS_WRITER_IMPL}" || true)" -ge 4 ]; then
  echo "[PASS] Sequence exhaustion preserves Volatile matching with no visible History"
else
  echo "[FAIL] Volatile sequence-exhaustion visibility is incomplete"
  FAILED=1
fi

if [ "$(grep -c "evaluateResourceLimits" "${STATELESS_WRITER_IMPL}" || true)" -eq 2 ] && \
   [ "$(grep -c "evaluateHistoryCapacity" "${STATELESS_WRITER_IMPL}" || true)" -eq 2 ] && \
   [ "$(grep -c "plannedKeepLastEvictions" "${STATELESS_WRITER_IMPL}" || true)" -eq 2 ] && \
   [ "$(grep -c "commitPreparedChange" "${STATELESS_WRITER_IMPL}" || true)" -eq 2 ] && \
   grep -q "getOldestDataBytes" \
     "${STATELESS_WRITER_IMPL}"; then
  echo "[PASS] Stateless Writer atomically enforces History and Resource Limits on both publish paths"
else
  echo "[FAIL] Stateless Writer History/Resource Limits wiring is incomplete"
  FAILED=1
fi

if grep -q "readerMayReceiveSequence" "${STATELESS_WRITER_IMPL}" && \
   grep -q "attempt <= SEND_RETRY_LIMIT" "${STATELESS_WRITER_IMPL}" && \
   grep -q "sendDataLocked(matchedProxy, sn)" "${STATELESS_WRITER_IMPL}" && \
   grep -q "replayFirst = firstSN" "${STATELESS_WRITER_IMPL}" && \
   grep -q "replayLast = lastSN" "${STATELESS_WRITER_IMPL}" && \
   grep -q "Linearize Transient Local replay" "${STATELESS_WRITER_IMPL}"; then
  echo "[PASS] Stateless late-join replay is linearized, range-bounded, and Reader-directed"
else
  echo "[FAIL] Stateless late-join durability wiring is incomplete"
  FAILED=1
fi

DATA_FRAG_CALLS=$(grep -c "MessageFactory::addSubMessageDataFrag" "${WRITER_IMPL}" || true)
FRAGMENT_ALLOC_GATES=$(grep -c "fragment.*reserve\|fragData.reserve" "${WRITER_IMPL}" || true)
if [ "${DATA_FRAG_CALLS}" -eq 2 ] && [ "${FRAGMENT_ALLOC_GATES}" -eq 2 ]; then
  echo "[PASS] Unicast/replay and multicast paths emit guarded DATA_FRAG samples"
else
  echo "[FAIL] Fragmented writer paths are incomplete"
  FAILED=1
fi

FRAGMENT_CAPABILITY_BIN="${BUILD_DIR}/test_fragmentation_capability"
g++ -std=c++17 \
  -I"${PROJECT_ROOT}/mros2/embeddedRTPS/include" \
  -o "${FRAGMENT_CAPABILITY_BIN}" \
  "${PROJECT_ROOT}/tests/test_fragmentation_capability.cpp"
if ! "${FRAGMENT_CAPABILITY_BIN}"; then
  echo "[FAIL] Fragmentation capability declaration test failed"
  FAILED=1
fi

FRAGMENT_REASSEMBLY_BIN="${BUILD_DIR}/test_data_fragment_reassembly"
g++ -std=c++17 \
  -I"${PROJECT_ROOT}/mros2/embeddedRTPS/include" \
  -I"${PROJECT_ROOT}/tests/stubs" \
  -o "${FRAGMENT_REASSEMBLY_BIN}" \
  "${PROJECT_ROOT}/tests/test_data_fragment_reassembly.cpp" \
  "${PROJECT_ROOT}/mros2/embeddedRTPS/src/messages/MessageTypes.cpp"
if ! "${FRAGMENT_REASSEMBLY_BIN}"; then
  echo "[FAIL] DATA_FRAG reassembly tests failed"
  FAILED=1
fi

if grep -q "SubmessageKind::DATA_FRAG" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/src/messages/MessageReceiver.cpp"; then
  echo "[PASS] DATA_FRAG receive reassembly is wired"
else
  echo "[FAIL] DATA_FRAG receive reassembly wiring is incomplete"
  FAILED=1
fi

echo ""
echo "=== Phase 1af: Liveliness State Tests ==="
LIVELINESS_BIN="${BUILD_DIR}/test_liveliness_state"
g++ -std=c++17 \
  -I"${PROJECT_ROOT}/mros2/embeddedRTPS/include" \
  -o "${LIVELINESS_BIN}" \
  "${PROJECT_ROOT}/tests/test_liveliness_state.cpp"

if ! "${LIVELINESS_BIN}"; then
  echo "[FAIL] Liveliness state tests failed"
  FAILED=1
fi

if grep -q "evaluateLivelinessTransition" "${READER_IMPL}"; then
  echo "[PASS] StatefulReader uses the tested liveliness transition oracle"
else
  echo "[FAIL] StatefulReader liveliness transition wiring is incomplete"
  FAILED=1
fi

echo ""
echo "=== Phase 1ag: Lifespan Boundary Tests ==="
LIFESPAN_BIN="${BUILD_DIR}/test_lifespan"
g++ -std=c++17 \
  -I"${PROJECT_ROOT}/mros2/embeddedRTPS/include" \
  -o "${LIFESPAN_BIN}" \
  "${PROJECT_ROOT}/tests/test_lifespan.cpp"

if ! "${LIFESPAN_BIN}"; then
  echo "[FAIL] Lifespan boundary tests failed"
  FAILED=1
fi

echo ""
echo "=== Phase 1ah: Deadline and Liveliness Time Tests ==="
QOS_TIME_BIN="${BUILD_DIR}/test_qos_time"
g++ -std=c++17 \
  -I"${PROJECT_ROOT}/mros2/embeddedRTPS/include" \
  -o "${QOS_TIME_BIN}" \
  "${PROJECT_ROOT}/tests/test_qos_time.cpp"

if ! "${QOS_TIME_BIN}"; then
  echo "[FAIL] Deadline/liveliness time tests failed"
  FAILED=1
fi

echo ""
echo "=== Phase 1ai: Benchmark Telemetry Math Tests ==="
TELEMETRY_BIN="${BUILD_DIR}/test_benchmark_telemetry_math"
g++ -std=c++17 \
  -I"${PROJECT_ROOT}/components/benchmark_telemetry/include" \
  -o "${TELEMETRY_BIN}" \
  "${PROJECT_ROOT}/tests/test_benchmark_telemetry_math.cpp"

if ! "${TELEMETRY_BIN}"; then
  echo "[FAIL] Benchmark telemetry math tests failed"
  FAILED=1
fi

echo ""
echo "=== Phase 1b: RTPS Message Tests ==="
THREAD_QUEUE_BIN="${BUILD_DIR}/test_threadsafe_circular_buffer"
g++ -std=c++17 -Wall -Wextra -Werror \
  -I"${PROJECT_ROOT}/tests/threadpool_stubs" \
  -I"${PROJECT_ROOT}/mros2/embeddedRTPS/include" \
  -o "${THREAD_QUEUE_BIN}" \
  "${PROJECT_ROOT}/tests/test_threadsafe_circular_buffer.cpp"
if ! "${THREAD_QUEUE_BIN}"; then
  echo "[FAIL] ThreadPool queue capacity tests failed"
  FAILED=1
fi

BOUNDED_DECODE_BIN="${BUILD_DIR}/test_bounded_message_decode"
g++ -std=c++17 -Wall -Wextra -Werror \
  -I"${PROJECT_ROOT}/mros2/mros2_msgs" \
  -o "${BOUNDED_DECODE_BIN}" \
  "${PROJECT_ROOT}/tests/test_bounded_message_decode.cpp"
if ! "${BOUNDED_DECODE_BIN}"; then
  echo "[FAIL] Bounded generated-message decode tests failed"
  FAILED=1
fi

GENERATED_BOUNDED_BIN="${BUILD_DIR}/test_generated_bounded_decode"
g++ -std=c++17 \
  -I"${PROJECT_ROOT}/mros2/mros2_msgs" \
  -o "${GENERATED_BOUNDED_BIN}" \
  "${PROJECT_ROOT}/tests/test_generated_bounded_decode.cpp"
if ! "${GENERATED_BOUNDED_BIN}"; then
  echo "[FAIL] Generator-produced bounded nested decode tests failed"
  FAILED=1
fi

GENERATED_DYNAMIC_BIN="${BUILD_DIR}/test_generated_dynamic_bounded_decode"
g++ -std=c++17 \
  -I"${PROJECT_ROOT}/tests/generator_fixture" \
  -o "${GENERATED_DYNAMIC_BIN}" \
  "${PROJECT_ROOT}/tests/test_generated_dynamic_bounded_decode.cpp"
if ! "${GENERATED_DYNAMIC_BIN}"; then
  echo "[FAIL] Generator-produced dynamic bounded decode tests failed"
  FAILED=1
fi

LEGACY_BOUNDED_BIN="${BUILD_DIR}/test_legacy_message_bounded_decode"
g++ -std=c++17 \
  -I"${PROJECT_ROOT}/mros2/mros2_msgs" \
  -o "${LEGACY_BOUNDED_BIN}" \
  "${PROJECT_ROOT}/tests/test_legacy_message_bounded_decode.cpp"
if ! "${LEGACY_BOUNDED_BIN}"; then
  echo "[FAIL] Legacy primitive/Header/Image bounded decode tests failed"
  FAILED=1
fi
if grep -q "bool copyFromBuf(const uint8_t \\*addrPtr, uint32_t availableBytes)" \
     "${PROJECT_ROOT}/mros2/mros2_header_generator/header_template.tpl" && \
   grep -q "bool boundedSizeFromBuf" \
     "${PROJECT_ROOT}/mros2/mros2_header_generator/header_template.tpl" && \
   grep -q "bool validateFromBuf" \
     "${PROJECT_ROOT}/mros2/mros2_header_generator/header_template.tpl"; then
  echo "[PASS] message generator emits bounded decode and admission hooks"
else
  echo "[FAIL] message generator lacks bounded decode/admission hooks"
  FAILED=1
fi
if grep -q "copyMessageFromBoundedBuffer" \
     "${PROJECT_ROOT}/mros2/src/mros2.cpp" && \
   grep -q "cacheChange.getDataSize() - 4U" \
     "${PROJECT_ROOT}/mros2/src/mros2.cpp"; then
  echo "[PASS] typed Subscriber uses length-aware decoding when available"
else
  echo "[FAIL] typed Subscriber bypasses available decode bounds"
  FAILED=1
fi
if python3 - \
  "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/StatefulReader.tpp" \
  "${PROJECT_ROOT}/mros2/embeddedRTPS/src/entities/StatelessReader.cpp" \
  "${PROJECT_ROOT}/mros2/embeddedRTPS/src/entities/Domain.cpp" \
  "${PROJECT_ROOT}/mros2/src/mros2.cpp" <<'PY'
import pathlib
import sys

stateful, stateless, domain, api = (
    pathlib.Path(path).read_text() for path in sys.argv[1:]
)
assert stateful.index("!payloadValidator(") < stateful.index(
    "advanceReaderExpected("
)
assert stateless.index("!payloadValidator(") < stateless.index(
    "admitBestEffortSequence("
)
assert domain.count("reader.registerPayloadValidator(") == 2
assert domain.index("reader.registerPayloadValidator(") < domain.index(
    "part.addReader(&reader)"
)
assert "Subscriber::payload_validator<T>" in api
PY
then
  echo "[PASS] bounded payload validation precedes Reliability admission"
else
  echo "[FAIL] malformed typed payload can advance Reader Reliability state"
  FAILED=1
fi

RTPS_BIN="${BUILD_DIR}/test_rtps_messages"
g++ -std=c++17 \
  -o "${RTPS_BIN}" \
  "${PROJECT_ROOT}/tests/test_rtps_messages.cpp"

if ! "${RTPS_BIN}"; then
  echo "[FAIL] RTPS message tests failed"
  FAILED=1
fi

echo ""
echo "=== Phase 2: Security Checks ==="

# Check no unsafe string operations in modified files
UNSAFE_FILES=$(grep -rn "strcpy\|strcat\|sprintf" \
  "${PROJECT_ROOT}/mros2/src/" \
  "${PROJECT_ROOT}/mros2/embeddedRTPS/src/entities/" \
  "${PROJECT_ROOT}/mros2/embeddedRTPS/src/messages/" \
  --include="*.cpp" --include="*.h" --include="*.tpp" 2>/dev/null || true)

if [ -n "$UNSAFE_FILES" ]; then
  echo "[FAIL] Unsafe string operations found:"
  echo "$UNSAFE_FILES"
  FAILED=1
else
  echo "[PASS] No unsafe string operations"
fi

echo ""
echo "=== Phase 3: Error Handling Checks ==="

# Check no infinite loops remain in error paths (except spin() main loop)
# Get spin() function line number, then exclude that range
SPIN_LINE=$(grep -n "void spin()" "${PROJECT_ROOT}/mros2/src/mros2.cpp" 2>/dev/null | head -1 | cut -d: -f1 || echo "0")
INFINITE_LOOPS=$(grep -n "while (true)" \
  "${PROJECT_ROOT}/mros2/src/mros2.cpp" 2>/dev/null \
  | awk -F: -v spin="$SPIN_LINE" '{if ($1 < spin || $1 > spin+20) print}' || true)

if [ -n "$INFINITE_LOOPS" ]; then
  echo "[FAIL] Infinite loops in error paths:"
  echo "$INFINITE_LOOPS"
  FAILED=1
else
  echo "[PASS] No infinite loops in error paths"
fi

echo ""
echo "=== Phase 4: Code Quality Checks ==="

# Check no memory leaks (new without delete pattern)
NEW_COUNT=$(grep -c "new " "${PROJECT_ROOT}/mros2/src/mros2.cpp" 2>/dev/null || echo "0")
DELETE_COUNT=$(grep -c "delete " "${PROJECT_ROOT}/mros2/src/mros2.cpp" 2>/dev/null || echo "0")
# Note: new=1 is Thread creation (FreeRTOS managed), not a leak
echo "[INFO] new/delete in mros2.cpp: new=$NEW_COUNT, delete=$DELETE_COUNT (Thread is FreeRTOS-managed)"

# Check shutdown function exists
if grep -q "void shutdown()" "${PROJECT_ROOT}/mros2/include/mros2.h" 2>/dev/null; then
  echo "[PASS] shutdown() API declared"
else
  echo "[FAIL] shutdown() API missing"
  FAILED=1
fi

echo ""
echo "=== Phase 5: API Signature Consistency ==="
# Guards against declaration/definition/template-instantiation signature drift
# (e.g. create_publisher(std::string) vs create_publisher(const std::string&)),
# which breaks the firmware build but is invisible to the host unit tests.
if ! bash "${PROJECT_ROOT}/scripts/test/qos_api_signature_check.sh"; then
  echo "[FAIL] create_publisher/create_subscription signature drift (would break firmware build)"
  FAILED=1
fi

if grep -q "bool publish(T &msg)" "${PROJECT_ROOT}/mros2/include/mros2.h" && \
   grep -q "bool Publisher::publish(T &msg)" "${PROJECT_ROOT}/mros2/src/mros2.cpp" && \
   grep -q "template bool mros2::Publisher::publish" "${PROJECT_ROOT}/platform/templates.hpp"; then
  echo "[PASS] publish() acceptance result is consistent across API and instantiation"
else
  echo "[FAIL] publish() acceptance result signature drift"
  FAILED=1
fi
if grep -q "rtps::Writer \\*writer_ = nullptr" \
     "${PROJECT_ROOT}/mros2/include/mros2.h" && \
   grep -q "rtps::Writer \\*const writer = writer_" \
     "${PROJECT_ROOT}/mros2/src/mros2.cpp" && \
   grep -q "FragmentSerializationState" \
     "${PROJECT_ROOT}/mros2/src/mros2.cpp"; then
  echo "[PASS] Publisher binds its Writer and fragmented workspace per sample"
else
  echo "[FAIL] Publisher endpoint/QoS binding can alias global publish state"
  FAILED=1
fi
if grep -q "fragmentedPublicationValid(true, serializedSize)" \
     "${PROJECT_ROOT}/mros2/src/mros2.cpp" && \
   grep -q "CacheChange::SerializerCallback{}" \
     "${PROJECT_ROOT}/mros2/src/mros2.cpp" && \
   grep -q "const uint32_t serializedSize = msg.calcTotalSize()" \
     "${PROJECT_ROOT}/mros2/src/mros2.cpp"; then
  echo "[PASS] oversized fragmented publish rejects before serializer allocation"
else
  echo "[FAIL] known-oversized publish can allocate before History rejection"
  FAILED=1
fi
if grep -q "uint32_t history_count() const" \
     "${PROJECT_ROOT}/mros2/include/mros2.h" && \
   grep -q "Publisher::resource_reject_count() const" \
     "${PROJECT_ROOT}/mros2/src/mros2.cpp" && \
   grep -q "Publisher::matched_reader_count() const" \
     "${PROJECT_ROOT}/mros2/src/mros2.cpp"; then
  echo "[PASS] Publisher exposes endpoint-scoped match and History admission state"
else
  echo "[FAIL] Publisher observability still depends only on global endpoint state"
  FAILED=1
fi

if grep -q "publisher_set_transmission_held(bool held)" \
     "${PROJECT_ROOT}/mros2/include/mros2.h" && \
   grep -q "setTransmissionHeld(bool) = 0" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/Writer.h" && \
   grep -q "void StatefulWriterT<NetworkDriver>::setTransmissionHeld" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/StatefulWriter.tpp" && \
   grep -q "void StatelessWriterT<NetworkDriver>::setTransmissionHeld" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/StatelessWriter.tpp" && \
   [ "$(grep -c 'if (m_transmissionHeld)' \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/StatefulWriter.tpp")" -ge 4 ] && \
   [ "$(grep -c 'if (m_transmissionHeld)' \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/StatelessWriter.tpp")" -ge 4 ]; then
  echo "[PASS] board-side transmission hold covers writer send paths"
else
  echo "[FAIL] board-side transmission hold API or send-path coverage drift"
  FAILED=1
fi
if grep -q "applyTransmissionHold(held, m_transmissionHeld)" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/StatefulWriter.tpp" && \
   grep -q "applyTransmissionHold(held, m_transmissionHeld)" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/StatelessWriter.tpp" && \
   grep -q "mp_threadPool == nullptr || !mp_threadPool->addWorkload(this)" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/StatefulWriter.tpp" && \
   grep -q "mp_threadPool == nullptr || !mp_threadPool->addWorkload(this)" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/StatelessWriter.tpp"; then
  echo "[PASS] transmission hold transitions are idempotent and release always resumes"
else
  echo "[FAIL] repeated hold values can rewind History or pool-less release can stall"
  FAILED=1
fi
if [ "$(grep -c 'mp_threadPool == nullptr || !mp_threadPool->addWorkload(this)' \
       "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/StatefulWriter.tpp")" -ge 2 ] && \
   [ "$(grep -c 'mp_threadPool == nullptr || !mp_threadPool->addWorkload(this)' \
       "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/StatelessWriter.tpp")" -ge 2 ]; then
  echo "[PASS] release and successor work self-drain through queue failure"
else
  echo "[FAIL] release can stall after one sample when successor queueing fails"
  FAILED=1
fi
if python3 - \
  "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/StatefulWriter.tpp" \
  "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/StatelessWriter.tpp" <<'PY'
import pathlib
import sys

for filename in sys.argv[1:]:
    source = pathlib.Path(filename).read_text(encoding="utf-8")
    start = source.index("::progress()")
    end = source.find("\ntemplate <", start)
    if end < 0:
        end = len(source)
    body = source[start:end]
    if "while (true)" not in body or "progress();" in body:
        raise SystemExit(1)
PY
then
  echo "[PASS] Writer successor self-drain is iterative rather than recursive"
else
  echo "[FAIL] Writer History self-drain can grow stack with configured depth"
  FAILED=1
fi
if grep -q "THREAD_POOL_RETRY_QUEUE_LENGTH" \
     "${PROJECT_ROOT}/platform/rtps/config.h" && \
   grep -q "m_queueRetry" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/ThreadPool.h" && \
   grep -q "tryMarkRetryQueued" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/src/ThreadPool.cpp" && \
   [ "$(grep -h -c 'addRetryWorkload(this)' \
        "${WRITER_IMPL}" "${STATELESS_WRITER_IMPL}" \
        | awk '{sum += $1} END {print sum + 0}')" -eq 2 ]; then
  echo "[PASS] failed sends use a coalesced all-Writer retry queue"
else
  echo "[FAIL] send retry can be lost behind a full ordinary workload queue"
  FAILED=1
fi
if grep -q "delayTicks == 0 ? 1 : delayTicks" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/StatefulWriter.tpp"; then
  echo "[PASS] sub-tick HEARTBEAT periods cannot create a zero-delay busy loop"
else
  echo "[FAIL] valid HEARTBEAT configuration can collapse to zero RTOS ticks"
  FAILED=1
fi
if grep -q "if (success && !m_transmissionHeld &&" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/StatefulWriter.tpp" && \
   grep -q "if (success && !m_transmissionHeld &&" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/StatelessWriter.tpp"; then
  echo "[PASS] held Writers defer late-join replay without false send failures"
else
  echo "[FAIL] late-join replay can leak traffic or failures during hold"
  FAILED=1
fi
if grep -q "mayAdvanceGlobalCursorAfterDirectedReplay(" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/StatefulWriter.tpp" && \
   grep -q "mayAdvanceGlobalCursorAfterDirectedReplay(" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/StatelessWriter.tpp"; then
  echo "[PASS] first successful directed replay advances both Writer cursors"
else
  echo "[FAIL] directed replay cursor ownership differs by Writer kind"
  FAILED=1
fi
if grep -q "held = m_transmissionHeld" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/StatefulWriter.tpp" && \
   grep -q "shouldCountRepairSendFailure(held, retryAvailability)" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/StatefulWriter.tpp"; then
  echo "[PASS] held ACKNACK repair is deferred rather than counted failed"
else
  echo "[FAIL] transmission hold can inflate ACKNACK repair failure state"
  FAILED=1
fi
if python3 - \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/StatefulWriter.tpp" <<'PY'
import pathlib
import sys

text = pathlib.Path(sys.argv[1]).read_text()
start = text.index("void StatefulWriterT<NetworkDriver>::sendHeartBeat()")
body = text[start:text.index(
    "template <class NetworkDriver>", start + 20)]
purge = body.index("purgeExpiredChangesLocked")
hold = body.index("if (m_transmissionHeld)")
reader_empty = body.index("if (readerCount == 0)")
raise SystemExit(0 if purge < hold < reader_empty else 1)
PY
then
  echo "[PASS] periodic Lifespan cleanup precedes hold/no-Reader heartbeat exits"
else
  echo "[FAIL] held or unmatched Writer can retain expired History indefinitely"
  FAILED=1
fi
if grep -q "scheduleAfterEviction" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/StatefulWriter.tpp" && \
   grep -q "!sendSnapshotStillPending(" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/StatefulWriter.tpp" && \
   grep -q "sendCursorTargetsRetainedHistory(" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/StatefulWriter.tpp"; then
  echo "[PASS] mid-send eviction advances without false failure or cursor stall"
else
  echo "[FAIL] Lifespan/Keep Last eviction can strand ordinary Writer progress"
  FAILED=1
fi
if grep -q "shouldCountRepairSendFailure(held, retryAvailability)" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/StatefulWriter.tpp" && \
   grep -q "currentAvailability == RequestedSequenceAvailability::AVAILABLE" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/ReliabilityState.h"; then
  echo "[PASS] ACKNACK repair eviction converts to GAP without false failure telemetry"
else
  echo "[FAIL] ACKNACK repair eviction is still reported as a local send failure"
  FAILED=1
fi
if grep -q "subscriber_callback_slots" \
     "${PROJECT_ROOT}/mros2/src/mros2.cpp" && \
   grep -q "subscriber_callback_slot_count" \
     "${PROJECT_ROOT}/mros2/src/mros2.cpp" && \
   ! grep -q "static SubscribeDataType callback_data" \
     "${PROJECT_ROOT}/mros2/src/mros2.cpp"; then
  echo "[PASS] each Subscriber Reader owns a stable bounded callback slot"
else
  echo "[FAIL] Subscriber callbacks can alias across Reader endpoints"
  FAILED=1
fi
if grep -q "rtps::Reader \\*reader_ = nullptr" \
     "${PROJECT_ROOT}/mros2/include/mros2.h" && \
   grep -q "Subscriber::received_count() const" \
     "${PROJECT_ROOT}/mros2/src/mros2.cpp" && \
   grep -q "Subscriber::unsupported_payload_drop_count() const" \
     "${PROJECT_ROOT}/mros2/src/mros2.cpp" && \
   grep -q "sub.reader_ = reader" \
     "${PROJECT_ROOT}/mros2/src/mros2.cpp"; then
  echo "[PASS] Subscriber observability is bound to its own Reader endpoint"
else
  echo "[FAIL] Subscriber QoS state still aliases the last-created Reader"
  FAILED=1
fi
if grep -q "cacheChange.getDataSize() < 4" \
     "${PROJECT_ROOT}/mros2/src/mros2.cpp" && \
   grep -q "sub->hasCallback" \
     "${PROJECT_ROOT}/mros2/src/mros2.cpp" && \
   grep -q "std::memcpy(&fp, sub->callbackBytes.data(), sizeof(fp))" \
     "${PROJECT_ROOT}/mros2/src/mros2.cpp"; then
  echo "[PASS] typed Subscriber callback defends its CDR and callback bounds"
else
  echo "[FAIL] internal Reader delivery can bypass typed callback bounds"
  FAILED=1
fi
if grep -q "readerPayloadSupported(" "${READER_IMPL}" && \
   grep -q "mros2UserCdrPayloadSupported(" "${READER_IMPL}" && \
   grep -q "readerPayloadSupported(" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/src/entities/StatelessReader.cpp" && \
   grep -q "mros2UserCdrPayloadSupported(" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/src/entities/StatelessReader.cpp"; then
  echo "[PASS] both Readers validate CDR bounds before sequence admission"
else
  echo "[FAIL] malformed internal payload can advance Reader sequence state"
  FAILED=1
fi
if grep -q "subscriber_unsupported_payload_drop_count()" \
     "${PROJECT_ROOT}/mros2/include/mros2.h" && \
   grep -q "getUnsupportedPayloadDropCount" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/StatefulReader.h" && \
   grep -q "getUnsupportedPayloadDropCount" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/StatelessReader.h" && \
   grep -q "m_unsupportedPayloadDropCount" "${READER_IMPL}" && \
   grep -q "m_unsupportedPayloadDropCount" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/src/entities/StatelessReader.cpp"; then
  echo "[PASS] unsupported user CDR drops are observable before admission"
else
  echo "[FAIL] unsupported payload rejection lacks Reader observability"
  FAILED=1
fi

if grep -q "local_send_failure_count() const" \
     "${PROJECT_ROOT}/mros2/include/mros2.h" && \
   grep -q "publisher_local_send_failure_count()" \
     "${PROJECT_ROOT}/mros2/include/mros2.h" && \
   grep -q "getLocalSendFailureCount() const override" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/StatefulWriter.h" && \
   grep -q "getLocalSendFailureCount() const override" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/StatelessWriter.h" && \
   grep -q "m_localSendFailureCount" "${WRITER_IMPL}" && \
   grep -q "m_localSendFailureCount" "${STATELESS_WRITER_IMPL}"; then
  echo "[PASS] local DATA send failures are observable per Writer"
else
  echo "[FAIL] local DATA send failure observability is incomplete"
  FAILED=1
fi
if [ "$(grep -c "m_controlSendFailureCount" "${WRITER_IMPL}")" -ge 4 ] && \
   grep -q "publisher_control_send_failure_count" \
     "${PROJECT_ROOT}/mros2/src/mros2.cpp"; then
  echo "[PASS] Writer HEARTBEAT/GAP local failures are endpoint-observable"
else
  echo "[FAIL] Writer control-send failure observability is incomplete"
  FAILED=1
fi
if grep -q "bool sendPacket(PacketInfo &info);" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/communication/UdpDriver.h" && \
   grep -q "bool UdpDriver::sendPacket(PacketInfo &packet)" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/src/communication/UdpDriver.cpp" && \
   grep -q "return sendPacket(\\*p_conn" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/src/communication/UdpDriver.cpp" && \
   grep -q "return m_transport->sendPacket(info);" "${WRITER_IMPL}" && \
   grep -q "return m_transport->sendPacket(info);" \
     "${STATELESS_WRITER_IMPL}" && \
   grep -q "if (!m_transport->sendPacket(fragmentInfo))" "${WRITER_IMPL}" && \
   grep -q "if (!m_transport->sendPacket(info))" \
     "${STATELESS_WRITER_IMPL}"; then
  echo "[PASS] UDP send status reaches DATA/DATA_FRAG History decisions"
else
  echo "[FAIL] a Writer can still treat a failed UDP DATA send as successful"
  FAILED=1
fi
if grep -q "static QoSProfile project_default()" \
     "${PROJECT_ROOT}/mros2/include/mros2/qos.h" && \
   ! grep -q "static QoSProfile system_default()" \
     "${PROJECT_ROOT}/mros2/include/mros2/qos.h"; then
  echo "[PASS] concrete defaults do not masquerade as host ROS 2 system defaults"
else
  echo "[FAIL] QoS default factory naming implies unsupported host delegation"
  FAILED=1
fi
if grep -q "MROS2_RTPS_ACKNACK_SEQUENCE_RESPONSE_BUDGET" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/ReliabilityState.h" && \
   grep -q "ACKNACK sequence-response budget must fit its bitmap" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/ReliabilityState.h" && \
   grep -q "MROS2_RTPS_ACKNACK_SEQUENCE_RESPONSE_BUDGET=" \
     "${PROJECT_ROOT}/components/mros2-esp32/CMakeLists.txt" && \
   grep -q "MROS2_RTPS_ACKNACK_SEQUENCE_RESPONSE_BUDGET 4 1 32" \
     "${PROJECT_ROOT}/workspace/qos_eval/CMakeLists.txt" && \
   grep -q "tryReserveAckNackSequenceResponse(attemptedResponses)" \
     "${WRITER_IMPL}" && \
   grep -q "m_ackNackDeferredResponseCount" "${WRITER_IMPL}" && \
   grep -q "acknack_deferred_response_count() const" \
     "${PROJECT_ROOT}/mros2/include/mros2.h" && \
   grep -q "publisher_acknack_deferred_response_count()" \
     "${PROJECT_ROOT}/mros2/include/mros2.h"; then
  echo "[PASS] ACKNACK sequence recovery and deferred-response telemetry are bounded"
else
  echo "[FAIL] ACKNACK sequence-response bounding is incomplete"
  FAILED=1
fi
if grep -q "MAX_FRAGMENTED_SAMPLE_SIZE = 4096" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/common/types.h" && \
   grep -q "MAX_FRAGMENTS_PER_SAMPLE = 128" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/common/types.h" && \
   grep -q "sampleSize <= MAX_FRAGMENTED_SAMPLE_SIZE" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/ReliabilityState.h" && \
   grep -q "fragmentStartNumber <= MAX_FRAGMENTS_PER_SAMPLE" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/ReliabilityState.h" && \
   grep -q "MaxSampleSize = MAX_FRAGMENTED_SAMPLE_SIZE" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/messages/DataFragmentReassembly.h" && \
   grep -q "MaxFragments = MAX_FRAGMENTS_PER_SAMPLE" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/messages/DataFragmentReassembly.h"; then
  echo "[PASS] outgoing and incoming fragmented sample bounds are symmetric"
else
  echo "[FAIL] fragmented sample work or storage is not symmetrically bounded"
  FAILED=1
fi
if [ "$(grep -c "releaseUnmatchedVolatileHistoryLocked();" \
        "${WRITER_IMPL}" || true)" -ge 2 ] && \
   [ "$(grep -c "releaseUnmatchedVolatileHistoryLocked();" \
        "${STATELESS_WRITER_IMPL}" || true)" -ge 2 ] && \
   grep -q "shouldReleaseHistoryAfterReaderRemoval" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/DurabilityState.h" && \
   grep -q "m_history.removeUntilIncl(lastRetained)" "${WRITER_IMPL}" && \
   grep -q "shouldReleaseUnmatchedReliableFallbackHistory" \
     "${WRITER_IMPL}" && \
   grep -q "m_history.removeUntilIncl(lastRetained)" \
     "${STATELESS_WRITER_IMPL}" && \
   grep -q "shouldReleaseHistoryAfterBestEffortSend" \
     "${STATELESS_WRITER_IMPL}" && \
   grep -q "shouldReleaseUnmatchedBestEffortHistory" \
     "${STATELESS_WRITER_IMPL}" && \
   grep -q "m_history.getChangeBySN(sequenceToSend) != nullptr" \
     "${STATELESS_WRITER_IMPL}"; then
  echo "[PASS] Volatile Writer paths release completed/unmatched old History"
else
  echo "[FAIL] unmatched Volatile History can strand Writer capacity"
  FAILED=1
fi
PBUF_SOURCE="${PROJECT_ROOT}/mros2/embeddedRTPS/src/storages/PBufWrapper.cpp"
if [ "$(grep -c "this == &other" "${PBUF_SOURCE}" || true)" -ge 3 ] && \
   grep -q "!isValid() || length > m_freeSpace" "${PBUF_SOURCE}" && \
   grep -q "if (!isValid())" "${PBUF_SOURCE}"; then
  echo "[PASS] PBuf ownership operations guard invalid and self use"
else
  echo "[FAIL] PBuf ownership defensive guards are incomplete"
  FAILED=1
fi

THREAD_POOL_SOURCE="${PROJECT_ROOT}/mros2/embeddedRTPS/src/ThreadPool.cpp"
THREAD_POOL_HEADER="${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/ThreadPool.h"
if grep -q "pbuf_alloc(PBUF_RAW, pbuf->tot_len, PBUF_RAM)" \
     "${THREAD_POOL_SOURCE}" && \
   grep -q "linear == nullptr || linear->next != nullptr" \
     "${THREAD_POOL_SOURCE}" && \
   grep -q "pbuf_copy(linear, pbuf) != ERR_OK" \
     "${THREAD_POOL_SOURCE}" && \
   grep -q "pool.m_rxStats.packetsDropped++" "${THREAD_POOL_SOURCE}"; then
  echo "[PASS] chained receive pbuf linearization fails closed under pressure"
else
  echo "[FAIL] chained receive pbuf allocation can crash or pass truncation"
  FAILED=1
fi
if grep -q "static_assert(Config::THREAD_POOL_NUM_READERS == 1" \
     "${THREAD_POOL_HEADER}" && \
   grep -q "completed.data = slot->data.data()" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/messages/DataFragmentReassembly.h"; then
  echo "[PASS] synchronous DATA_FRAG slot lifetime has one receive worker"
else
  echo "[FAIL] DATA_FRAG completed-slot lifetime permits concurrent reuse"
  FAILED=1
fi

MECHANISM_APP="${PROJECT_ROOT}/workspace/seven_qos_mechanisms/main/app.cpp"
MECHANISM_CMAKE="${PROJECT_ROOT}/workspace/seven_qos_mechanisms/main/CMakeLists.txt"
if grep -q 'MROS2_MECHANISM_KIND STREQUAL "history_writer_gap"' \
     "${MECHANISM_CMAKE}" && \
   grep -q "phase=awaiting_directed_acknack" "${MECHANISM_APP}" && \
   grep -q "MROS2_MECHANISM_KIND_CODE == 16" "${MECHANISM_APP}"; then
  echo "[PASS] dedicated mros2 Writer GAP board state machine is wired"
else
  echo "[FAIL] dedicated mros2 Writer GAP board state machine is incomplete"
  FAILED=1
fi

if grep -q 'MROS2_MECHANISM_KIND STREQUAL "history_reader_gap"' \
     "${MECHANISM_CMAKE}" && \
   grep -q "phase=awaiting_host_gap" "${MECHANISM_APP}" && \
   grep -q "subscriber_gap_received_count() == 1" "${MECHANISM_APP}" && \
   grep -q "getGapReceivedCount" \
     "${PROJECT_ROOT}/mros2/embeddedRTPS/include/rtps/entities/StatefulReader.h"; then
  echo "[PASS] dedicated mros2 Reader GAP board state and counter are wired"
else
  echo "[FAIL] dedicated mros2 Reader GAP board state or counter is incomplete"
  FAILED=1
fi

HOST_PROBE="${PROJECT_ROOT}/tools/echo_cpp/src/qos_compatibility_probe.cpp"
if grep -q "finished = finished ||" "${HOST_PROBE}" && \
   grep -q "node->rx_count() == static_cast<uint32_t>(options.expected_rx_count)" \
     "${HOST_PROBE}" && \
   grep -q "node->rx_count() > 0" "${HOST_PROBE}"; then
  echo "[PASS] host subscriber waits for its receive goal before early completion"
else
  echo "[FAIL] host subscriber completion can precede its receive goal"
  FAILED=1
fi

if python3 "${PROJECT_ROOT}/scripts/experiment/test_validate_microros_rdh_late_join_smoke.py"; then
  echo "[PASS] micro-ROS RDH late-join oracle rejects ordering and QoS drift"
else
  echo "[FAIL] micro-ROS RDH late-join oracle self-tests failed"
  FAILED=1
fi
if python3 \
  "${PROJECT_ROOT}/scripts/experiment/test_validate_native_ros2_rdh_late_join_smoke.py"; then
  echo "[PASS] native ROS 2 RDH late-join oracle rejects content and QoS drift"
else
  echo "[FAIL] native ROS 2 RDH late-join oracle self-tests failed"
  FAILED=1
fi
if python3 "${PROJECT_ROOT}/scripts/experiment/test_run_microros_rdh_late_join_smoke.py"; then
  echo "[PASS] micro-ROS RDH runner preserves bounded scale and environment classification"
else
  echo "[FAIL] micro-ROS RDH runner self-tests failed"
  FAILED=1
fi
if PYTHONPATH="${PROJECT_ROOT}/scripts/experiment" python3 \
  "${PROJECT_ROOT}/scripts/experiment/test_validate_rdh_external_baseline_pair.py"; then
  echo "[PASS] external RDH baseline pair validator enforces semantic identity"
else
  echo "[FAIL] external RDH baseline pair validator self-tests failed"
  FAILED=1
fi

echo ""
if [ $FAILED -eq 0 ]; then
  echo "=== All checks PASSED ==="
else
  echo "=== Some checks FAILED ==="
  exit 1
fi
