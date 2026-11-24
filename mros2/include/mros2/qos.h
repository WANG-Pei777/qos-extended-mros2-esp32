#ifndef MROS2_QOS_H
#define MROS2_QOS_H

#include "rtps/common/types.h"
#include <cstdint>

namespace mros2 {

// ROS 2-compatible duration representation.
struct Duration {
    static constexpr int32_t INFINITE_SEC = 0x7FFFFFFF;
    static constexpr uint32_t INFINITE_NSEC = 0xFFFFFFFF;

    int32_t sec;
    uint32_t nanosec;

    static Duration from_ms(uint32_t ms) {
        return Duration{static_cast<int32_t>(ms / 1000), (ms % 1000) * 1000000};
    }

    static Duration from_sec(uint32_t s) {
        return Duration{static_cast<int32_t>(s), 0};
    }

    static Duration infinite() {
        return Duration{INFINITE_SEC, INFINITE_NSEC};
    }

    bool is_infinite() const {
        return sec == INFINITE_SEC && nanosec == INFINITE_NSEC;
    }

    bool is_valid() const {
        if (is_infinite()) return true;
        return sec >= 0 && nanosec < 1000000000U;
    }

    bool is_millisecond_representable() const {
        if (is_infinite()) return true;
        if (!is_valid() || (sec == 0 && nanosec == 0) ||
            nanosec % 1000000U != 0) {
            return false;
        }
        const uint64_t milliseconds =
            static_cast<uint64_t>(sec) * 1000U + nanosec / 1000000U;
        return milliseconds <= UINT32_MAX;
    }
};

// History policy.
enum class HistoryKind : uint8_t {
    KEEP_LAST = 0,
    KEEP_ALL = 1
};

// Liveliness policy.
enum class LivelinessKind : uint8_t {
    AUTOMATIC = 0,
    MANUAL_BY_TOPIC = 1,
    MANUAL_BY_NODE = 2
};

// QoS profile compatible with embeddedRTPS.
struct QoSProfile {
    rtps::ReliabilityKind_t reliability;
    rtps::DurabilityKind_t durability;
    HistoryKind history;
    uint32_t depth;
    Duration deadline;
    Duration lifespan;
    Duration liveliness_lease_duration;
    LivelinessKind liveliness;
    uint32_t max_samples;   // Resource Limits: 0 = unlimited
    // Local retained RTPS serializedPayload bound, including the CDR
    // encapsulation header and serializer padding. Excludes CacheChange,
    // pbuf/allocator metadata, RTPS/UDP/IP framing, and serializer workspace.
    // Zero removes this profile bound but not physical History capacity.
    uint32_t max_bytes;

    // Helper methods: convert durations to milliseconds.
    // Clamps to UINT32_MAX on overflow to prevent undefined behavior.
    uint32_t deadline_ms() const {
        if (deadline.is_infinite()) return 0;
        if (!deadline.is_valid()) return 0;
        // Check for overflow: if sec > UINT32_MAX/1000, clamp to max
        if (static_cast<uint32_t>(deadline.sec) > UINT32_MAX / 1000U)
            return UINT32_MAX;
        uint32_t ms_from_sec = static_cast<uint32_t>(deadline.sec) * 1000;
        uint32_t ms_from_nsec = deadline.nanosec / 1000000;
        if (ms_from_sec > UINT32_MAX - ms_from_nsec) return UINT32_MAX;
        return ms_from_sec + ms_from_nsec;
    }
    uint32_t lifespan_ms() const {
        if (lifespan.is_infinite()) return 0;
        if (!lifespan.is_valid()) return 0;
        if (static_cast<uint32_t>(lifespan.sec) > UINT32_MAX / 1000U)
            return UINT32_MAX;
        uint32_t ms_from_sec = static_cast<uint32_t>(lifespan.sec) * 1000;
        uint32_t ms_from_nsec = lifespan.nanosec / 1000000;
        if (ms_from_sec > UINT32_MAX - ms_from_nsec) return UINT32_MAX;
        return ms_from_sec + ms_from_nsec;
    }
    uint32_t liveliness_lease_ms() const {
        if (liveliness_lease_duration.is_infinite()) return 0;
        if (!liveliness_lease_duration.is_valid()) return 0;
        if (static_cast<uint32_t>(liveliness_lease_duration.sec) >
            UINT32_MAX / 1000U)
            return UINT32_MAX;
        uint32_t ms_from_sec = static_cast<uint32_t>(liveliness_lease_duration.sec) * 1000;
        uint32_t ms_from_nsec = liveliness_lease_duration.nanosec / 1000000;
        if (ms_from_sec > UINT32_MAX - ms_from_nsec) return UINT32_MAX;
        return ms_from_sec + ms_from_nsec;
    }

    // Concrete mros2 project default.
    QoSProfile()
        : reliability(rtps::ReliabilityKind_t::RELIABLE),
          durability(rtps::DurabilityKind_t::VOLATILE),
          history(HistoryKind::KEEP_LAST),
          depth(10),
          deadline(Duration::infinite()),
          lifespan(Duration::infinite()),
          liveliness_lease_duration(Duration::infinite()),
          liveliness(LivelinessKind::AUTOMATIC),
          max_samples(0),
          max_bytes(0) {}

    // Construct from a history depth while preserving every other project
    // default. A depth-only spelling must not silently change Reliability or
    // Durability.
    explicit QoSProfile(int history_depth)
        : reliability(rtps::ReliabilityKind_t::RELIABLE),
          durability(rtps::DurabilityKind_t::VOLATILE),
          history(HistoryKind::KEEP_LAST),
          depth(history_depth),
          deadline(Duration::infinite()),
          lifespan(Duration::infinite()),
          liveliness_lease_duration(Duration::infinite()),
          liveliness(LivelinessKind::AUTOMATIC),
          max_samples(0),
          max_bytes(0) {}

    // Predefined profile for sensor data.
    static QoSProfile sensor_data() {
        QoSProfile qos;
        qos.reliability = rtps::ReliabilityKind_t::BEST_EFFORT;
        qos.durability = rtps::DurabilityKind_t::VOLATILE;
        qos.history = HistoryKind::KEEP_LAST;
        qos.depth = 5;
        // Keep sensor-data timing policies infinite. Deadline and Lifespan
        // event mechanisms are implemented on the reliable stateful path.
        qos.deadline = Duration::infinite();
        qos.lifespan = Duration::infinite();
        return qos;
    }

    // Predefined profile for reliable transport.
    static QoSProfile reliable() {
        QoSProfile qos;
        qos.reliability = rtps::ReliabilityKind_t::RELIABLE;
        qos.durability = rtps::DurabilityKind_t::VOLATILE;
        qos.history = HistoryKind::KEEP_LAST;
        qos.depth = 10;
        return qos;
    }

    // Predefined profile for best-effort transport.
    static QoSProfile best_effort() {
        QoSProfile qos;
        qos.reliability = rtps::ReliabilityKind_t::BEST_EFFORT;
        qos.durability = rtps::DurabilityKind_t::VOLATILE;
        qos.history = HistoryKind::KEEP_LAST;
        qos.depth = 10;
        return qos;
    }

    // Bounded parameter-service style profile. Keep the canonical project
    // depth within the default embedded Writer capacity.
    static QoSProfile parameters() {
        QoSProfile qos;
        qos.reliability = rtps::ReliabilityKind_t::RELIABLE;
        qos.durability = rtps::DurabilityKind_t::VOLATILE;
        qos.history = HistoryKind::KEEP_LAST;
        qos.depth = 10;
        return qos;
    }

    // Concrete mros2 project default. This does not query or defer to a host
    // ROS 2 RMW/DDS system-default profile.
    static QoSProfile project_default() {
        return QoSProfile();
    }
};

// QoS validation and compatibility checks.
class QoSPolicy {
public:
    // Compile-time Writer capacities are represented by uint8_t in embeddedRTPS.
    static constexpr uint32_t MAX_REPRESENTABLE_HISTORY_DEPTH = UINT8_MAX;

    static const char* validation_error(
        const QoSProfile& qos, uint32_t physical_history_capacity = 0) {
        if (qos.reliability != rtps::ReliabilityKind_t::BEST_EFFORT &&
            qos.reliability != rtps::ReliabilityKind_t::RELIABLE) {
            return "unsupported reliability kind";
        }
        if (qos.durability != rtps::DurabilityKind_t::VOLATILE &&
            qos.durability != rtps::DurabilityKind_t::TRANSIENT_LOCAL) {
            return "only VOLATILE and TRANSIENT_LOCAL durability are implemented";
        }
        if (qos.history == HistoryKind::KEEP_LAST && qos.depth == 0) {
            return "KEEP_LAST requires depth > 0";
        }
        if (qos.history != HistoryKind::KEEP_LAST &&
            qos.history != HistoryKind::KEEP_ALL) {
            return "unsupported history kind";
        }
        if (qos.depth > MAX_REPRESENTABLE_HISTORY_DEPTH) {
            return "history depth exceeds embeddedRTPS representable capacity";
        }
        if (qos.max_samples > MAX_REPRESENTABLE_HISTORY_DEPTH) {
            return "max_samples exceeds embeddedRTPS representable capacity";
        }
        if (physical_history_capacity > 0 &&
            qos.history == HistoryKind::KEEP_LAST &&
            qos.depth > physical_history_capacity) {
            return "KEEP_LAST depth exceeds physical history capacity";
        }
        if (physical_history_capacity > 0 && qos.max_samples > 0 &&
            qos.max_samples > physical_history_capacity) {
            return "max_samples exceeds physical history capacity";
        }
        if (!qos.deadline.is_valid()) {
            return "invalid deadline duration";
        }
        if (!qos.lifespan.is_valid()) {
            return "invalid lifespan duration";
        }
        if (!qos.liveliness_lease_duration.is_valid()) {
            return "invalid liveliness lease duration";
        }
        if (!qos.deadline.is_millisecond_representable()) {
            return "deadline must be infinite or an exactly representable positive millisecond duration";
        }
        if (!qos.lifespan.is_millisecond_representable()) {
            return "lifespan must be infinite or an exactly representable positive millisecond duration";
        }
        if (!qos.liveliness_lease_duration.is_millisecond_representable()) {
            return "liveliness lease must be infinite or an exactly representable positive millisecond duration";
        }
        if (qos.reliability == rtps::ReliabilityKind_t::BEST_EFFORT &&
            !qos.deadline.is_infinite()) {
            return "finite deadline is not implemented for BEST_EFFORT endpoints";
        }
        if (qos.reliability == rtps::ReliabilityKind_t::BEST_EFFORT &&
            !qos.lifespan.is_infinite()) {
            return "finite lifespan is not implemented for BEST_EFFORT endpoints";
        }
        if (qos.reliability == rtps::ReliabilityKind_t::BEST_EFFORT &&
            !qos.liveliness_lease_duration.is_infinite()) {
            return "finite liveliness lease is not implemented for BEST_EFFORT endpoints";
        }
        if (qos.liveliness != LivelinessKind::AUTOMATIC) {
            return "only AUTOMATIC liveliness is currently implemented";
        }
        if (qos.max_samples > 0 && qos.history == HistoryKind::KEEP_LAST &&
            qos.max_samples < qos.depth) {
            return "max_samples must be >= KEEP_LAST depth";
        }
        return nullptr;
    }

    // Validate whether the QoS profile is supported by this implementation.
    static bool validate(
        const QoSProfile& qos, uint32_t physical_history_capacity = 0) {
        return validation_error(qos, physical_history_capacity) == nullptr;
    }

    // Check whether two QoS profiles are compatible under DDS rules.
    static bool is_compatible(const QoSProfile& offered, const QoSProfile& requested) {
        if (!validate(offered) || !validate(requested)) {
            return false;
        }
        // Reliability compatibility rule:
        // A RELIABLE subscriber cannot accept a BEST_EFFORT publisher.
        if (requested.reliability == rtps::ReliabilityKind_t::RELIABLE &&
            offered.reliability == rtps::ReliabilityKind_t::BEST_EFFORT) {
            return false;
        }

        // Durability compatibility rule:
        // A TRANSIENT_LOCAL subscriber cannot accept a VOLATILE publisher.
        if (requested.durability == rtps::DurabilityKind_t::TRANSIENT_LOCAL &&
            offered.durability == rtps::DurabilityKind_t::VOLATILE) {
            return false;
        }

        return true;
    }
};

} // namespace mros2

#endif // MROS2_QOS_H
