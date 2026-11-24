#!/usr/bin/env python3
"""Fail-closed identity checks for Seven-QoS evidence attempts."""

from __future__ import annotations

import re
from dataclasses import dataclass


EVIDENCE_MODES = ("engineering_smoke", "formal_candidate")
TOKEN_RE = re.compile(r"^sqp-[A-Za-z0-9][A-Za-z0-9_.-]*$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
CELL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


@dataclass(frozen=True)
class EvidenceIdentity:
    mode: str
    campaign_run_token: str | None
    protocol_schedule_sha256: str | None
    schedule_ordinal: int | None
    cell_id: str | None

    def as_dict(self) -> dict[str, str | int | None]:
        return {
            "mode": self.mode,
            "campaign_run_token": self.campaign_run_token,
            "protocol_schedule_sha256": self.protocol_schedule_sha256,
            "schedule_ordinal": self.schedule_ordinal,
            "cell_id": self.cell_id,
        }


def validate_evidence_identity(
    *,
    mode: str,
    campaign_run_token: str | None,
    protocol_schedule_sha256: str | None,
    schedule_ordinal: int | None,
    cell_id: str | None,
) -> EvidenceIdentity:
    """Validate and return a normalized evidence identity."""
    if mode not in EVIDENCE_MODES:
        raise ValueError(f"unsupported evidence mode: {mode}")

    formal_values = (
        campaign_run_token,
        protocol_schedule_sha256,
        schedule_ordinal,
        cell_id,
    )
    if mode == "engineering_smoke":
        if any(value is not None for value in formal_values):
            raise ValueError("formal identity fields are forbidden in engineering_smoke mode")
        return EvidenceIdentity(mode, None, None, None, None)

    if any(value is None for value in formal_values):
        raise ValueError("formal_candidate requires every formal identity field")
    assert campaign_run_token is not None
    assert protocol_schedule_sha256 is not None
    assert schedule_ordinal is not None
    assert cell_id is not None
    if not TOKEN_RE.fullmatch(campaign_run_token):
        raise ValueError("campaign run token must match sqp-[A-Za-z0-9_.-]+")
    if not SHA256_RE.fullmatch(protocol_schedule_sha256):
        raise ValueError("protocol schedule SHA-256 must be 64 lowercase hex characters")
    if schedule_ordinal <= 0:
        raise ValueError("schedule ordinal must be positive")
    if not CELL_ID_RE.fullmatch(cell_id):
        raise ValueError("cell ID is not machine-safe")
    return EvidenceIdentity(
        mode,
        campaign_run_token,
        protocol_schedule_sha256,
        schedule_ordinal,
        cell_id,
    )
