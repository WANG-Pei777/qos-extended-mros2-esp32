/*
 * Host-side unit tests for mros2 QoS profile and policy logic.
 *
 * Compiled and run on the development host (no ESP32 required).
 * Coverage targets: Duration, QoSProfile, QoSPolicy::validate,
 * QoSPolicy::is_compatible, and all predefined profiles.
 */

#include "mros2/qos.h"

#include <cassert>
#include <cstdio>
#include <cstring>

static int total = 0;
static int passed = 0;
static int failed = 0;

static void check(bool condition, const char *label) {
  total++;
  if (condition) {
    passed++;
    printf("[PASS] %s\n", label);
  } else {
    failed++;
    printf("[FAIL] %s\n", label);
  }
}

// ============================================================
// Duration tests
// ============================================================

static void test_duration_from_ms() {
  using namespace mros2;

  {
    Duration d = Duration::from_ms(0);
    check(d.sec == 0 && d.nanosec == 0, "Duration::from_ms(0) -> {0, 0}");
  }
  {
    Duration d = Duration::from_ms(100);
    check(d.sec == 0 && d.nanosec == 100000000U,
          "Duration::from_ms(100) -> {0, 100000000}");
  }
  {
    Duration d = Duration::from_ms(1500);
    check(d.sec == 1 && d.nanosec == 500000000U,
          "Duration::from_ms(1500) -> {1, 500000000}");
  }
  {
    Duration d = Duration::from_ms(2000);
    check(d.sec == 2 && d.nanosec == 0,
          "Duration::from_ms(2000) -> {2, 0}");
  }
  {
    Duration d = Duration::from_ms(3000);
    check(d.sec == 3 && d.nanosec == 0,
          "Duration::from_ms(3000) -> {3, 0}");
  }
}

static void test_duration_from_sec() {
  using namespace mros2;

  {
    Duration d = Duration::from_sec(0);
    check(d.sec == 0 && d.nanosec == 0, "Duration::from_sec(0) -> {0, 0}");
  }
  {
    Duration d = Duration::from_sec(5);
    check(d.sec == 5 && d.nanosec == 0, "Duration::from_sec(5) -> {5, 0}");
  }
}

static void test_duration_infinite() {
  using namespace mros2;

  Duration d = Duration::infinite();
  check(d.sec == Duration::INFINITE_SEC,
        "Duration::infinite().sec == INFINITE_SEC");
  check(d.nanosec == Duration::INFINITE_NSEC,
        "Duration::infinite().nanosec == INFINITE_NSEC");
  check(d.is_infinite(), "infinite duration is_infinite() == true");

  Duration finite = Duration::from_ms(100);
  check(!finite.is_infinite(), "finite duration is_infinite() == false");
}

static void test_duration_is_valid() {
  using namespace mros2;

  check(Duration::infinite().is_valid(), "infinite duration is_valid()");
  check(Duration::from_ms(100).is_valid(), "from_ms(100) is_valid()");
  check(Duration::from_sec(5).is_valid(), "from_sec(5) is_valid()");

  // nanosec == 1000000000 is invalid (must be < 1e9)
  Duration bad{0, 1000000000U};
  check(!bad.is_valid(), "duration with nanosec=1000000000 is invalid");

  // negative sec is invalid (except infinite)
  Duration neg_sec{-1, 0};
  check(!neg_sec.is_valid(), "duration with negative sec is invalid");
}

// ============================================================
// QoSProfile default constructor
// ============================================================

static void test_qos_profile_defaults() {
  using namespace mros2;

  QoSProfile qos;
  check(qos.reliability == rtps::ReliabilityKind_t::RELIABLE,
        "default QoSProfile: reliability == RELIABLE");
  check(qos.durability == rtps::DurabilityKind_t::VOLATILE,
        "default QoSProfile: durability == VOLATILE");
  check(qos.history == HistoryKind::KEEP_LAST,
        "default QoSProfile: history == KEEP_LAST");
  check(qos.depth == 10, "default QoSProfile: depth == 10");
  check(qos.deadline.is_infinite(),
        "default QoSProfile: deadline is infinite");
  check(qos.lifespan.is_infinite(),
        "default QoSProfile: lifespan is infinite");
  check(qos.liveliness_lease_duration.is_infinite(),
        "default QoSProfile: liveliness_lease_duration is infinite");
  check(qos.liveliness == LivelinessKind::AUTOMATIC,
        "default QoSProfile: liveliness == AUTOMATIC");
  check(qos.max_samples == 0, "default QoSProfile: max_samples == 0");
  check(qos.max_bytes == 0, "default QoSProfile: max_bytes == 0");
}

static void test_qos_profile_int_constructor() {
  using namespace mros2;

  QoSProfile qos(5);
  check(qos.reliability == rtps::ReliabilityKind_t::RELIABLE,
        "QoSProfile(int): preserves default RELIABLE");
  check(qos.durability == rtps::DurabilityKind_t::VOLATILE,
        "QoSProfile(int): preserves default VOLATILE");
  check(qos.history == HistoryKind::KEEP_LAST,
        "QoSProfile(int): history == KEEP_LAST");
  check(qos.depth == 5, "QoSProfile(int): depth == 5");
  const QoSProfile defaults;
  check(qos.deadline.sec == defaults.deadline.sec &&
            qos.deadline.nanosec == defaults.deadline.nanosec &&
            qos.lifespan.sec == defaults.lifespan.sec &&
            qos.lifespan.nanosec == defaults.lifespan.nanosec &&
            qos.liveliness_lease_duration.sec ==
                defaults.liveliness_lease_duration.sec &&
            qos.liveliness_lease_duration.nanosec ==
                defaults.liveliness_lease_duration.nanosec &&
            qos.liveliness == defaults.liveliness &&
            qos.max_samples == defaults.max_samples &&
            qos.max_bytes == defaults.max_bytes,
        "QoSProfile(int): only depth differs from the project default");
}

// ============================================================
// Duration conversion helpers on QoSProfile
// ============================================================

static void test_qos_profile_duration_helpers() {
  using namespace mros2;

  QoSProfile qos;
  qos.deadline = Duration::from_ms(100);
  qos.lifespan = Duration::from_ms(2000);
  qos.liveliness_lease_duration = Duration::from_ms(3000);

  check(qos.deadline_ms() == 100, "deadline_ms() == 100");
  check(qos.lifespan_ms() == 2000, "lifespan_ms() == 2000");
  check(qos.liveliness_lease_ms() == 3000,
        "liveliness_lease_ms() == 3000");

  // Infinite durations return 0
  QoSProfile qos2;
  check(qos2.deadline_ms() == 0,
        "infinite deadline_ms() == 0");
  check(qos2.lifespan_ms() == 0,
        "infinite lifespan_ms() == 0");
  check(qos2.liveliness_lease_ms() == 0,
        "infinite liveliness_lease_ms() == 0");
}

// ============================================================
// Predefined profiles
// ============================================================

static void test_sensor_data_profile() {
  using namespace mros2;

  QoSProfile qos = QoSProfile::sensor_data();
  check(qos.reliability == rtps::ReliabilityKind_t::BEST_EFFORT,
        "sensor_data: BEST_EFFORT");
  check(qos.durability == rtps::DurabilityKind_t::VOLATILE,
        "sensor_data: VOLATILE");
  check(qos.history == HistoryKind::KEEP_LAST,
        "sensor_data: KEEP_LAST");
  check(qos.depth == 5, "sensor_data: depth == 5");
}

static void test_reliable_profile() {
  using namespace mros2;

  QoSProfile qos = QoSProfile::reliable();
  check(qos.reliability == rtps::ReliabilityKind_t::RELIABLE,
        "reliable: RELIABLE");
  check(qos.durability == rtps::DurabilityKind_t::VOLATILE,
        "reliable: VOLATILE");
  check(qos.history == HistoryKind::KEEP_LAST,
        "reliable: KEEP_LAST");
  check(qos.depth == 10, "reliable: depth == 10");
}

static void test_best_effort_profile() {
  using namespace mros2;

  QoSProfile qos = QoSProfile::best_effort();
  check(qos.reliability == rtps::ReliabilityKind_t::BEST_EFFORT,
        "best_effort: BEST_EFFORT");
  check(qos.durability == rtps::DurabilityKind_t::VOLATILE,
        "best_effort: VOLATILE");
  check(qos.history == HistoryKind::KEEP_LAST,
        "best_effort: KEEP_LAST");
  check(qos.depth == 10, "best_effort: depth == 10");
}

static void test_parameters_profile() {
  using namespace mros2;

  QoSProfile qos = QoSProfile::parameters();
  check(qos.reliability == rtps::ReliabilityKind_t::RELIABLE,
        "parameters: RELIABLE");
  check(qos.durability == rtps::DurabilityKind_t::VOLATILE,
        "parameters: VOLATILE");
  check(qos.depth == 10, "parameters: bounded depth == 10");
  check(QoSPolicy::validate(qos, 10),
        "parameters: valid at the default physical History capacity");
}

static void test_project_default_profile() {
  using namespace mros2;

  QoSProfile qos = QoSProfile::project_default();
  check(qos.reliability == rtps::ReliabilityKind_t::RELIABLE,
        "project_default: RELIABLE");
  check(qos.durability == rtps::DurabilityKind_t::VOLATILE,
        "project_default: VOLATILE");
  check(qos.history == HistoryKind::KEEP_LAST,
        "project_default: KEEP_LAST");
  check(qos.depth == 10, "project_default: depth == 10");
}

static void test_predefined_profiles_fit_canonical_capacity() {
  using namespace mros2;
  check(QoSPolicy::validate(QoSProfile::sensor_data(), 10) &&
            QoSPolicy::validate(QoSProfile::reliable(), 10) &&
            QoSPolicy::validate(QoSProfile::best_effort(), 10) &&
            QoSPolicy::validate(QoSProfile::parameters(), 10) &&
            QoSPolicy::validate(QoSProfile::project_default(), 10),
        "all predefined profiles fit canonical physical History capacity 10");
}

// ============================================================
// QoSPolicy::validate
// ============================================================

static void test_validate_reliable() {
  using namespace mros2;
  QoSProfile qos = QoSProfile::reliable();
  check(QoSPolicy::validate(qos), "reliable profile is valid");
}

static void test_validate_zero_depth() {
  using namespace mros2;
  QoSProfile qos = QoSProfile::reliable();
  qos.depth = 0;
  check(!QoSPolicy::validate(qos), "KEEP_LAST depth=0 is rejected");
}

static void test_validate_oversized_depth() {
  using namespace mros2;
  QoSProfile qos = QoSProfile::reliable();
  qos.depth = 256;
  check(!QoSPolicy::validate(qos), "unrepresentable depth (256) is rejected");
}

static void test_validate_manual_liveliness() {
  using namespace mros2;
  QoSProfile qos = QoSProfile::reliable();
  qos.liveliness = LivelinessKind::MANUAL_BY_TOPIC;
  check(!QoSPolicy::validate(qos),
        "unsupported manual liveliness is rejected");
}

static void test_validate_invalid_duration() {
  using namespace mros2;
  QoSProfile qos = QoSProfile::reliable();
  qos.deadline = Duration{0, 1000000000U};
  check(!QoSPolicy::validate(qos),
        "invalid nanosecond duration is rejected");
}

static void test_validate_max_samples_lt_depth() {
  using namespace mros2;
  QoSProfile qos = QoSProfile::reliable();
  qos.depth = 5;
  qos.max_samples = 4;
  check(!QoSPolicy::validate(qos),
        "max_samples smaller than KEEP_LAST depth is rejected");
}

static void test_validate_keep_all_no_depth() {
  using namespace mros2;
  QoSProfile qos;
  qos.history = HistoryKind::KEEP_ALL;
  qos.depth = 0;
  qos.max_samples = 1;
  check(QoSPolicy::validate(qos), "KEEP_ALL does not require depth");
}

static void test_validate_invalid_lifespan() {
  using namespace mros2;
  QoSProfile qos = QoSProfile::reliable();
  qos.lifespan = Duration{0, 1000000000U};
  check(!QoSPolicy::validate(qos),
        "invalid lifespan nanosec is rejected");
}

static void test_validate_duration_representation_boundary() {
  using namespace mros2;
  QoSProfile qos = QoSProfile::reliable();
  qos.lifespan = Duration{0, 0};
  check(!QoSPolicy::validate(qos),
        "zero Lifespan is rejected instead of becoming infinite");

  qos = QoSProfile::reliable();
  qos.lifespan = Duration{0, 500000};
  check(!QoSPolicy::validate(qos),
        "sub-millisecond Lifespan is rejected instead of becoming infinite");

  qos = QoSProfile::reliable();
  qos.lifespan = Duration{0, 1500000};
  check(!QoSPolicy::validate(qos),
        "fractional-millisecond Lifespan is rejected instead of truncating");

  qos = QoSProfile::reliable();
  qos.lifespan = Duration{0, 1000000};
  check(QoSPolicy::validate(qos),
        "one-millisecond Lifespan is exactly representable");

  qos = QoSProfile::reliable();
  qos.lifespan = Duration{
      static_cast<int32_t>(UINT32_MAX / 1000U + 1U), 0};
  check(!QoSPolicy::validate(qos),
        "Lifespan beyond the uint32 millisecond range is rejected");

  qos = QoSProfile::reliable();
  qos.deadline = Duration{0, 0};
  check(!QoSPolicy::validate(qos),
        "zero Deadline is not confused with the infinite sentinel");

  qos = QoSProfile::reliable();
  qos.liveliness_lease_duration = Duration{0, 0};
  check(!QoSPolicy::validate(qos),
        "zero Liveliness lease is not confused with the infinite sentinel");
}

static void test_validate_invalid_liveliness_lease() {
  using namespace mros2;
  QoSProfile qos = QoSProfile::reliable();
  qos.liveliness_lease_duration = Duration{-1, 0};
  check(!QoSPolicy::validate(qos),
        "invalid liveliness lease duration is rejected");
}

static void test_validate_manual_by_node() {
  using namespace mros2;
  QoSProfile qos = QoSProfile::reliable();
  qos.liveliness = LivelinessKind::MANUAL_BY_NODE;
  check(!QoSPolicy::validate(qos),
        "MANUAL_BY_NODE liveliness is rejected");
}

static void test_validate_negative_depth_overflow() {
  // The generic representation supports uint8_t capacity; endpoint creation
  // applies the selected Writer's usually smaller physical capacity.
  using namespace mros2;
  QoSProfile qos = QoSProfile::reliable();
  qos.depth = 255;
  check(QoSPolicy::validate(qos), "depth=255 is representable");
  qos.depth = 256;
  check(!QoSPolicy::validate(qos), "depth=256 is rejected");
}

static void test_validate_max_samples_eq_depth() {
  using namespace mros2;
  QoSProfile qos = QoSProfile::reliable();
  qos.depth = 5;
  qos.max_samples = 5;
  check(QoSPolicy::validate(qos),
        "max_samples == depth is valid");
}

static void test_validate_physical_history_capacity() {
  using namespace mros2;
  QoSProfile qos = QoSProfile::reliable();
  qos.depth = 11;
  check(!QoSPolicy::validate(qos, 10),
        "KEEP_LAST depth above physical capacity is rejected");
  qos.depth = 10;
  check(QoSPolicy::validate(qos, 10),
        "KEEP_LAST depth at physical capacity is valid");

  qos.history = HistoryKind::KEEP_ALL;
  qos.depth = 0;
  qos.max_samples = 11;
  check(!QoSPolicy::validate(qos, 10),
        "explicit max_samples above physical capacity is rejected");
  qos.max_samples = 10;
  check(QoSPolicy::validate(qos, 10),
        "explicit max_samples at physical capacity is valid");
  qos.max_samples = 0;
  check(QoSPolicy::validate(qos, 10),
        "unbounded profile still uses the physical capacity");
}

static void test_validate_representable_sample_limit() {
  using namespace mros2;
  QoSProfile qos;
  qos.history = HistoryKind::KEEP_ALL;
  qos.depth = 0;
  qos.max_samples = 255;
  check(QoSPolicy::validate(qos),
        "max_samples=255 is representable");
  qos.max_samples = 256;
  check(!QoSPolicy::validate(qos),
        "max_samples=256 is rejected");
}

static void test_validate_supported_reliability_and_durability() {
  using namespace mros2;
  QoSProfile qos;
  qos.reliability = static_cast<rtps::ReliabilityKind_t>(99);
  check(!QoSPolicy::validate(qos),
        "unknown Reliability kind is rejected");

  qos = QoSProfile{};
  qos.durability = rtps::DurabilityKind_t::TRANSIENT;
  check(!QoSPolicy::validate(qos),
        "TRANSIENT durability is rejected");

  qos.durability = rtps::DurabilityKind_t::PERSISTENT;
  check(!QoSPolicy::validate(qos),
        "PERSISTENT durability is rejected");
}

static void test_validate_best_effort_physical_capacity() {
  using namespace mros2;
  check(QoSPolicy::validate(QoSProfile::sensor_data(), 10),
        "sensor_data fits default Stateless history capacity");
  check(QoSPolicy::validate(QoSProfile::best_effort(), 10),
        "best_effort profile fits default Stateless history capacity");
  check(!QoSPolicy::validate(QoSProfile::sensor_data(), 2),
        "sensor_data is rejected when Stateless capacity is only two");
}

static void test_validate_best_effort_time_policy_gates() {
  using namespace mros2;
  QoSProfile qos = QoSProfile::best_effort();
  qos.deadline = Duration::from_ms(100);
  check(!QoSPolicy::validate(qos),
        "BEST_EFFORT finite Deadline is rejected");

  qos = QoSProfile::best_effort();
  qos.lifespan = Duration::from_ms(100);
  check(!QoSPolicy::validate(qos),
        "BEST_EFFORT finite Lifespan is rejected");

  qos = QoSProfile::best_effort();
  qos.liveliness_lease_duration = Duration::from_ms(100);
  check(!QoSPolicy::validate(qos),
        "BEST_EFFORT finite Liveliness lease is rejected");

  qos = QoSProfile::best_effort();
  qos.durability = rtps::DurabilityKind_t::TRANSIENT_LOCAL;
  qos.history = HistoryKind::KEEP_ALL;
  qos.depth = 1;
  qos.max_samples = 10;
  check(QoSPolicy::validate(qos, 10),
        "BEST_EFFORT still supports Durability, History, and Resource Limits");

  qos = QoSProfile::reliable();
  qos.deadline = Duration::from_ms(100);
  qos.lifespan = Duration::from_ms(200);
  qos.liveliness_lease_duration = Duration::from_ms(300);
  check(QoSPolicy::validate(qos, 10),
        "RELIABLE finite time policies remain supported");
}

// ============================================================
// QoSPolicy::is_compatible
// ============================================================

static void test_compatible_reliable_reliable() {
  using namespace mros2;
  QoSProfile offered = QoSProfile::reliable();
  QoSProfile requested = QoSProfile::reliable();
  check(QoSPolicy::is_compatible(offered, requested),
        "RELIABLE offered + RELIABLE requested = compatible");
}

static void test_incompatible_best_effort_offered_reliable_requested() {
  using namespace mros2;
  QoSProfile offered = QoSProfile::best_effort();
  QoSProfile requested = QoSProfile::reliable();
  check(!QoSPolicy::is_compatible(offered, requested),
        "BEST_EFFORT offered + RELIABLE requested = incompatible");
}

static void test_compatible_best_effort_best_effort() {
  using namespace mros2;
  QoSProfile offered = QoSProfile::best_effort();
  QoSProfile requested = QoSProfile::best_effort();
  check(QoSPolicy::is_compatible(offered, requested),
        "BEST_EFFORT offered + BEST_EFFORT requested = compatible");
}

static void test_compatible_reliable_offered_best_effort_requested() {
  using namespace mros2;
  QoSProfile offered = QoSProfile::reliable();
  QoSProfile requested = QoSProfile::best_effort();
  check(QoSPolicy::is_compatible(offered, requested),
        "RELIABLE offered + BEST_EFFORT requested = compatible");
}

static void test_incompatible_volatile_offered_transient_requested() {
  using namespace mros2;
  QoSProfile offered;
  offered.durability = rtps::DurabilityKind_t::VOLATILE;
  QoSProfile requested;
  requested.durability = rtps::DurabilityKind_t::TRANSIENT_LOCAL;
  check(!QoSPolicy::is_compatible(offered, requested),
        "VOLATILE offered + TRANSIENT_LOCAL requested = incompatible");
}

static void test_compatible_transient_offered_volatile_requested() {
  using namespace mros2;
  QoSProfile offered;
  offered.durability = rtps::DurabilityKind_t::TRANSIENT_LOCAL;
  QoSProfile requested;
  requested.durability = rtps::DurabilityKind_t::VOLATILE;
  check(QoSPolicy::is_compatible(offered, requested),
        "TRANSIENT_LOCAL offered + VOLATILE requested = compatible");
}

// ============================================================
// Main
// ============================================================

int main() {
  printf("=== mros2 QoS Unit Tests ===\n\n");

  printf("--- Duration ---\n");
  test_duration_from_ms();
  test_duration_from_sec();
  test_duration_infinite();
  test_duration_is_valid();

  printf("\n--- QoSProfile Defaults ---\n");
  test_qos_profile_defaults();
  test_qos_profile_int_constructor();
  test_qos_profile_duration_helpers();

  printf("\n--- Predefined Profiles ---\n");
  test_sensor_data_profile();
  test_reliable_profile();
  test_best_effort_profile();
  test_parameters_profile();
  test_project_default_profile();
  test_predefined_profiles_fit_canonical_capacity();

  printf("\n--- QoSPolicy::validate ---\n");
  test_validate_reliable();
  test_validate_zero_depth();
  test_validate_oversized_depth();
  test_validate_manual_liveliness();
  test_validate_invalid_duration();
  test_validate_max_samples_lt_depth();
  test_validate_keep_all_no_depth();
  test_validate_invalid_lifespan();
  test_validate_duration_representation_boundary();
  test_validate_invalid_liveliness_lease();
  test_validate_manual_by_node();
  test_validate_negative_depth_overflow();
  test_validate_max_samples_eq_depth();
  test_validate_physical_history_capacity();
  test_validate_representable_sample_limit();
  test_validate_supported_reliability_and_durability();
  test_validate_best_effort_physical_capacity();
  test_validate_best_effort_time_policy_gates();

  printf("\n--- QoSPolicy::is_compatible ---\n");
  test_compatible_reliable_reliable();
  test_incompatible_best_effort_offered_reliable_requested();
  test_compatible_best_effort_best_effort();
  test_compatible_reliable_offered_best_effort_requested();
  test_incompatible_volatile_offered_transient_requested();
  test_compatible_transient_offered_volatile_requested();

  printf("\n=== Results: %d/%d passed, %d failed ===\n",
         passed, total, failed);
  return failed == 0 ? 0 : 1;
}
