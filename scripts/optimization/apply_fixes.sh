#!/usr/bin/env bash
#
# Apply automated fixes for static analysis issues
#
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${PROJECT_ROOT}"

echo "=========================================="
echo "Applying Automated Code Fixes"
echo "=========================================="
echo ""

FIXED_COUNT=0

# Fix 1: Add override specifiers
echo "[1/4] Adding override specifiers..."

# StatefulReader.h
if grep -q "void setDeadlineMs(uint32_t ms) { m_deadlineMs = ms; }" mros2/embeddedRTPS/include/rtps/entities/StatefulReader.h; then
    sed -i 's/void setDeadlineMs(uint32_t ms) { m_deadlineMs = ms; }/void setDeadlineMs(uint32_t ms) override { m_deadlineMs = ms; }/' \
        mros2/embeddedRTPS/include/rtps/entities/StatefulReader.h
    echo "  ✓ Fixed setDeadlineMs()"
    FIXED_COUNT=$((FIXED_COUNT + 1))
fi

if grep -q "void setLivelinessLeaseMs(uint32_t ms) { m_livelinessLeaseMs = ms; }" mros2/embeddedRTPS/include/rtps/entities/StatefulReader.h; then
    sed -i 's/void setLivelinessLeaseMs(uint32_t ms) { m_livelinessLeaseMs = ms; }/void setLivelinessLeaseMs(uint32_t ms) override { m_livelinessLeaseMs = ms; }/' \
        mros2/embeddedRTPS/include/rtps/entities/StatefulReader.h
    echo "  ✓ Fixed setLivelinessLeaseMs()"
    FIXED_COUNT=$((FIXED_COUNT + 1))
fi

# Fix 2: Change pass-by-value to pass-by-reference for performance
echo ""
echo "[2/4] Optimizing function parameters (pass by reference)..."

# mros2.cpp - publisher
if grep -q "Publisher Node::create_publisher(std::string topic_name" mros2/src/mros2.cpp; then
    sed -i 's/Publisher Node::create_publisher(std::string topic_name/Publisher Node::create_publisher(const std::string\& topic_name/' \
        mros2/src/mros2.cpp
    echo "  ✓ Fixed create_publisher()"
    FIXED_COUNT=$((FIXED_COUNT + 1))
fi

# mros2.cpp - subscriber
if grep -q "Subscriber Node::create_subscription(std::string topic_name" mros2/src/mros2.cpp; then
    sed -i 's/Subscriber Node::create_subscription(std::string topic_name/Subscriber Node::create_subscription(const std::string\& topic_name/' \
        mros2/src/mros2.cpp
    echo "  ✓ Fixed create_subscription()"
    FIXED_COUNT=$((FIXED_COUNT + 1))
fi

# Fix 3: Initialize member variables
echo ""
echo "[3/4] Adding member variable initializations..."

# ParticipantProxyData.h
if grep -q "ParticipantProxyData() { onAliveSignal(); }" mros2/embeddedRTPS/include/rtps/discovery/ParticipantProxyData.h; then
    sed -i 's/ParticipantProxyData() { onAliveSignal(); }/ParticipantProxyData() : m_availableBuiltInEndpoints(0) { onAliveSignal(); }/' \
        mros2/embeddedRTPS/include/rtps/discovery/ParticipantProxyData.h
    echo "  ✓ Fixed ParticipantProxyData default constructor"
    FIXED_COUNT=$((FIXED_COUNT + 1))
fi

# ReaderProxy.h
if grep -q "ReaderProxy() : remoteReaderGuid({GUIDPREFIX_UNKNOWN, ENTITYID_UNKNOWN}){};" mros2/embeddedRTPS/include/rtps/entities/ReaderProxy.h; then
    sed -i 's/ReaderProxy() : remoteReaderGuid({GUIDPREFIX_UNKNOWN, ENTITYID_UNKNOWN}){};/ReaderProxy() : remoteReaderGuid({GUIDPREFIX_UNKNOWN, ENTITYID_UNKNOWN}), ackNackCount(0) {};/' \
        mros2/embeddedRTPS/include/rtps/entities/ReaderProxy.h
    echo "  ✓ Fixed ReaderProxy constructor"
    FIXED_COUNT=$((FIXED_COUNT + 1))
fi

# Fix 4: Add explicit to single-parameter constructors
echo ""
echo "[4/4] Adding explicit to constructors..."

# LocatorIPv4
if grep -q "LocatorIPv4(const FullLengthLocator &locator)" mros2/embeddedRTPS/include/rtps/common/Locator.h; then
    sed -i 's/LocatorIPv4(const FullLengthLocator &locator)/explicit LocatorIPv4(const FullLengthLocator \&locator)/' \
        mros2/embeddedRTPS/include/rtps/common/Locator.h
    echo "  ✓ Fixed LocatorIPv4 constructor"
    FIXED_COUNT=$((FIXED_COUNT + 1))
fi

# TopicDataCompressed
if grep -q "TopicDataCompressed(const TopicData &topic_data)" mros2/embeddedRTPS/include/rtps/discovery/TopicData.h; then
    sed -i 's/TopicDataCompressed(const TopicData &topic_data)/explicit TopicDataCompressed(const TopicData \&topic_data)/' \
        mros2/embeddedRTPS/include/rtps/discovery/TopicData.h
    echo "  ✓ Fixed TopicDataCompressed constructor"
    FIXED_COUNT=$((FIXED_COUNT + 1))
fi

echo ""
echo "=========================================="
echo "Summary"
echo "=========================================="
echo "Total fixes applied: ${FIXED_COUNT}"
echo ""

if [ "$FIXED_COUNT" -gt 0 ]; then
    echo "✓ Code improvements completed"
    echo ""
    echo "Next steps:"
    echo "  1. Review changes: git diff"
    echo "  2. Re-run analysis: ./scripts/analysis/run_static_analysis.sh"
    echo "  3. Test build: cd workspace/step7_full_qos && idf.py build"
else
    echo "⚠ No fixes were applied (already fixed or patterns not found)"
fi
