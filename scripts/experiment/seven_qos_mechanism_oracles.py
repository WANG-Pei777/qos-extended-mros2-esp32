#!/usr/bin/env python3
"""Frozen unit-oracle registry for Seven-QoS deterministic mechanisms."""

from __future__ import annotations

from typing import Any


def _binary(name: str, *labels: str, sources: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "binary": name,
        "required_pass_labels": list(labels),
        "source_assertions": sources or [],
    }


UNIT_ORACLES: dict[str, dict[str, Any]] = {
    "HIST-KL-ORDER": _binary(
        "test_simple_history_cache",
        "KEEP_LAST retains exactly the configured depth",
        "KEEP_LAST retains the newest sequence window",
        "retained history is retrievable in ascending sequence order",
    ),
    "HIST-KA-BOUND": _binary(
        "test_resource_limits",
        "non-full history accepts independently of policy",
        "KEEP_ALL rejects when capacity is full",
    ),
    "HIST-DUP-ONCE": _binary(
        "test_reader_sequence",
        "a duplicate sequence below expected is rejected",
    ),
    "HIST-GAP-SAFE": _binary(
        "test_reader_sequence",
        "a forward gap resynchronizes without an invalid history read",
    ),
    "HIST-PBUF-RELEASE": _binary(
        "test_simple_history_cache",
        "partial remove releases the removed payload",
        "capacity overflow releases the evicted payload",
        "remove-all releases every payload immediately",
    ),
    "DUR-TL-ORDER": _binary(
        "test_simple_history_cache",
        "retained history is retrievable in ascending sequence order",
        sources=[{
            "path": "mros2/embeddedRTPS/include/rtps/entities/StatefulWriter.tpp",
            "pattern": "while (sn <= lastSN)",
            "minimum_count": 1,
        }],
    ),
    "DUR-FRAG-CAPABILITY": _binary(
        "test_fragmentation_capability",
        "fragmented transient-local replay is declared supported",
        sources=[
            {
                "path": "mros2/embeddedRTPS/include/rtps/entities/StatefulWriter.tpp",
                "pattern": "MessageFactory::addSubMessageDataFrag",
                "minimum_count": 2,
            },
            {
                "path": "mros2/embeddedRTPS/include/rtps/entities/StatefulWriter.tpp",
                "pattern": "sendData(newProxy, sn)",
                "minimum_count": 1,
            },
        ],
    ),
    "DL-DISABLED": _binary(
        "test_qos_time", "disabled deadline never reports a miss"
    ),
    "DL-BEFORE": _binary(
        "test_qos_time", "deadline remains pending before boundary"
    ),
    "DL-BOUNDARY": _binary(
        "test_qos_time", "deadline misses at exact boundary"
    ),
    "DL-REPEATED": _binary(
        "test_qos_time", "deadline catch-up counts every complete period"
    ),
    "LS-DISABLED": _binary(
        "test_lifespan", "disabled lifespan never expires"
    ),
    "LS-FRESH": _binary(
        "test_lifespan", "sample remains valid before boundary"
    ),
    "LS-EXPIRED": _binary(
        "test_lifespan", "sample remains expired after boundary"
    ),
    "LS-BOUNDARY": _binary(
        "test_lifespan", "sample expires at boundary"
    ),
    "LV-STARTUP": _binary(
        "test_liveliness_state", "startup before first activity emits no transition"
    ),
    "LV-BEFORE": _binary(
        "test_liveliness_state",
        "an alive writer before the lease boundary emits no transition",
    ),
    "LV-LOSS-ONCE": _binary(
        "test_liveliness_state", "alive-to-dead crossing emits one lost transition"
    ),
    "LV-NO-DUP": _binary(
        "test_liveliness_state",
        "repeated outage checks emit no duplicate lost transition",
    ),
    "LV-RECOVERY-ONCE": _binary(
        "test_liveliness_state",
        "first post-outage activity emits one recovered transition",
    ),
    "LV-INFINITE": _binary(
        "test_liveliness_state", "an infinite lease disables liveliness transitions"
    ),
    "RES-SAMPLE-BOUND": _binary(
        "test_resource_limits", "sample count below max_samples is accepted"
    ),
    "RES-SAMPLE-REJECT": _binary(
        "test_resource_limits",
        "sample count at max_samples rejects the next sample",
    ),
    "RES-BYTE-BOUND": _binary(
        "test_resource_limits",
        "max_bytes accepts the exact boundary",
        "max_bytes rejects the first excess byte",
    ),
    "RES-HISTORY-ORDER": _binary(
        "test_resource_limits",
        "KEEP_ALL rejects when capacity is full",
        "KEEP_LAST evicts the oldest sample when capacity is full",
    ),
    "RES-ALLOC-FAIL": _binary(
        "test_simple_history_cache",
        "reserve failure rejects the change",
        "append failure rejects the change",
        "failed changes do not consume sequence numbers",
    ),
    "RES-NO-CORRUPTION": _binary(
        "test_simple_history_cache",
        "reserve failure retains no payload",
        "append failure releases temporary allocation",
        "wrapped history destruction releases all payloads",
    ),
}
