#!/usr/bin/env python3

import unittest

from seven_qos_evidence_identity import validate_evidence_identity


SCHEDULE_SHA = "3e76421e2c07869df73e76663c80084f875ab8cbbcabaf7d52fc7a46e4309abe"


class EvidenceIdentityTest(unittest.TestCase):
    def test_smoke_accepts_no_formal_fields(self) -> None:
        identity = validate_evidence_identity(
            mode="engineering_smoke",
            campaign_run_token=None,
            protocol_schedule_sha256=None,
            schedule_ordinal=None,
            cell_id=None,
        )
        self.assertEqual(identity.mode, "engineering_smoke")

    def test_smoke_rejects_formal_field(self) -> None:
        with self.assertRaisesRegex(ValueError, "forbidden"):
            validate_evidence_identity(
                mode="engineering_smoke",
                campaign_run_token="sqp-0001",
                protocol_schedule_sha256=None,
                schedule_ordinal=None,
                cell_id=None,
            )

    def test_formal_accepts_complete_identity(self) -> None:
        identity = validate_evidence_identity(
            mode="formal_candidate",
            campaign_run_token="sqp-0001",
            protocol_schedule_sha256=SCHEDULE_SHA,
            schedule_ordinal=1,
            cell_id="REL-L05-H2B",
        )
        self.assertEqual(identity.schedule_ordinal, 1)

    def test_formal_rejects_missing_field(self) -> None:
        with self.assertRaisesRegex(ValueError, "every formal identity"):
            validate_evidence_identity(
                mode="formal_candidate",
                campaign_run_token="sqp-0001",
                protocol_schedule_sha256=SCHEDULE_SHA,
                schedule_ordinal=1,
                cell_id=None,
            )

    def test_formal_rejects_bad_schedule_sha(self) -> None:
        with self.assertRaisesRegex(ValueError, "64 lowercase"):
            validate_evidence_identity(
                mode="formal_candidate",
                campaign_run_token="sqp-0001",
                protocol_schedule_sha256="ABC",
                schedule_ordinal=1,
                cell_id="REL-L05-H2B",
            )


if __name__ == "__main__":
    unittest.main()
