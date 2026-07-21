#!/usr/bin/env python3
"""Single source of truth for the 32 deterministic mechanism hardware cases."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def host(
    role: str,
    *,
    durability: str = "volatile",
    deadline_ms: str = "infinite",
    liveliness_lease_ms: str = "infinite",
    expected_rx: int | None = None,
    message_count: int = 1,
    period_ms: int = 100,
    pre_publish_ms: int = 0,
    post_match_ms: int = 20000,
    start_delay_ms: int = 500,
    expected_first_bytes: list[int] | None = None,
    expected_message_bytes: int | None = None,
) -> dict[str, Any]:
    return {
        "role": role,
        "reliability": "reliable",
        "durability": durability,
        "deadline_ms": deadline_ms,
        "liveliness_lease_ms": liveliness_lease_ms,
        "expected_rx": expected_rx,
        "message_count": message_count,
        "period_ms": period_ms,
        "pre_publish_ms": pre_publish_ms,
        "post_match_ms": post_match_ms,
        "start_delay_ms": start_delay_ms,
        "expected_first_bytes": expected_first_bytes,
        "expected_message_bytes": expected_message_bytes,
    }


def case(
    kind: str,
    *,
    capacity: int = 40,
    payload: int = 64,
    host_config: dict[str, Any] | None = None,
    orchestration: str = "single",
    timeout_ms: int = 20000,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "capacity": capacity,
        "payload": payload,
        "host": host_config,
        "orchestration": orchestration,
        "timeout_ms": timeout_ms,
    }


HARDWARE_CASES: dict[str, dict[str, Any]] = {
    "HIST-KL-ORDER": case(
        "history_keep_last_order",
        host_config=host(
            "subscriber", durability="transient_local", expected_rx=3,
            start_delay_ms=4000, expected_first_bytes=[67, 68, 69]
        ),
    ),
    "HIST-KA-BOUND": case("history_keep_all_bound"),
    "HIST-DUP-ONCE": case(
        "history_duplicate_once",
        host_config=host(
            "publisher", pre_publish_ms=15000, post_match_ms=16000
        ),
        orchestration="duplicate_user_data",
        timeout_ms=50000,
    ),
    "HIST-GAP-SAFE": case(
        "history_gap_safe",
        host_config=host(
            "publisher", message_count=3, period_ms=100,
            pre_publish_ms=15000, post_match_ms=17000
        ),
        orchestration="delay_first_user_data",
        timeout_ms=50000,
    ),
    "HIST-EPOCH-RESET": case(
        "history_epoch_reset",
        host_config=host(
            "publisher", pre_publish_ms=15000, post_match_ms=16000
        ),
        orchestration="restart_host_writer",
        timeout_ms=50000,
    ),
    "HIST-PBUF-RELEASE": case(
        "history_pbuf_release",
        host_config=host("subscriber", expected_rx=5),
    ),
    "DUR-VOL-LATE": case(
        "durability_volatile_late",
        host_config=host(
            "subscriber", expected_rx=1, start_delay_ms=4000,
            expected_first_bytes=[90]
        ),
    ),
    "DUR-TL-ORDER": case(
        "durability_tl_order",
        host_config=host(
            "subscriber", durability="transient_local", expected_rx=3,
            start_delay_ms=4000, expected_first_bytes=[67, 68, 69]
        ),
    ),
    "DUR-TL-DEPTH": case(
        "durability_tl_depth",
        host_config=host(
            "subscriber", durability="transient_local", expected_rx=2,
            start_delay_ms=4000, expected_first_bytes=[68, 69]
        ),
    ),
    "DUR-TL-EPOCH": case(
        "durability_tl_epoch",
        host_config=host(
            "subscriber", durability="transient_local", expected_rx=3,
            start_delay_ms=4000
        ),
        orchestration="reset_board_then_late_join",
        timeout_ms=50000,
    ),
    "DUR-FRAG-CAPABILITY": case(
        "durability_frag_capability", payload=512,
        host_config=host(
            "subscriber", durability="transient_local", expected_rx=1,
            start_delay_ms=4000, expected_first_bytes=[65],
            expected_message_bytes=512
        ),
    ),
    "DL-DISABLED": case(
        "deadline_disabled",
        host_config=host(
            "publisher", pre_publish_ms=15000, post_match_ms=16000
        ),
    ),
    "DL-BOUNDARY": case(
        "deadline_boundary",
        host_config=host(
            "publisher", deadline_ms="50", pre_publish_ms=15000,
            post_match_ms=16000
        ),
    ),
    "DL-REPEATED": case(
        "deadline_repeated",
        host_config=host(
            "publisher", deadline_ms="50", pre_publish_ms=15000,
            post_match_ms=16000
        ),
    ),
    "DL-RECOVERY": case(
        "deadline_recovery",
        host_config=host(
            "publisher", deadline_ms="50", message_count=2, period_ms=30,
            pre_publish_ms=15000, post_match_ms=16200
        ),
    ),
    "DL-POLLING": case(
        "deadline_polling",
        host_config=host(
            "publisher", deadline_ms="50", pre_publish_ms=15000,
            post_match_ms=16000
        ),
    ),
    "LS-DISABLED": case(
        "lifespan_disabled",
        host_config=host("subscriber", expected_rx=1),
    ),
    "LS-FRESH": case(
        "lifespan_fresh",
        host_config=host("subscriber", expected_rx=1),
    ),
    "LS-EXPIRED": case(
        "lifespan_expired",
        host_config=host("subscriber", expected_rx=0),
    ),
    "LS-RECONNECT": case(
        "lifespan_reconnect",
        host_config=host(
            "subscriber", durability="transient_local", expected_rx=0,
            start_delay_ms=4000
        ),
    ),
    "LS-HOLD-MARKERS": case(
        "lifespan_hold_markers",
        host_config=host("subscriber", expected_rx=1),
    ),
    "LV-STARTUP": case("liveliness_startup"),
    "LV-LOSS-ONCE": case(
        "liveliness_loss_once",
        host_config=host(
            "publisher", liveliness_lease_ms="500",
            pre_publish_ms=15000, post_match_ms=15100
        ),
    ),
    "LV-NO-DUP": case(
        "liveliness_no_duplicate",
        host_config=host(
            "publisher", liveliness_lease_ms="500",
            pre_publish_ms=15000, post_match_ms=15100
        ),
    ),
    "LV-RECOVERY-ONCE": case(
        "liveliness_recovery_once",
        host_config=host(
            "publisher", liveliness_lease_ms="500",
            pre_publish_ms=15000, post_match_ms=15100
        ),
        orchestration="restart_host_after_loss",
        timeout_ms=50000,
    ),
    "LV-INFINITE": case(
        "liveliness_infinite",
        host_config=host(
            "publisher", pre_publish_ms=15000, post_match_ms=15100
        ),
    ),
    "RES-SAMPLE-BOUND": case("resource_sample_bound", capacity=100),
    "RES-SAMPLE-REJECT": case("resource_sample_reject", capacity=100),
    "RES-BYTE-BOUND": case("resource_byte_bound", capacity=100),
    "RES-ALLOC-FAIL": case("resource_alloc_fail", capacity=100),
    "RES-RECOVERY": case(
        "resource_recovery", capacity=100,
        host_config=host(
            "subscriber", expected_rx=6,
            expected_first_bytes=[65, 66, 67, 68, 69, 86]
        ),
    ),
    "RES-NO-CORRUPTION": case("resource_no_corruption", capacity=100),
}


def get_case(case_id: str) -> dict[str, Any]:
    if case_id not in HARDWARE_CASES:
        raise KeyError(f"unknown hardware mechanism case: {case_id}")
    value = deepcopy(HARDWARE_CASES[case_id])
    value["case_id"] = case_id
    return value
