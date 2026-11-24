#!/usr/bin/env python3

import unittest

from run_native_ros2_baseline_pilot import (
    FINAL_PREFIX,
    SAMPLE_PREFIX,
    parse_record,
    validate_probe_output,
)


class NativeRos2BaselinePilotTest(unittest.TestCase):
    def valid_output(self) -> str:
        return "\n".join(
            [
                (
                    f"{SAMPLE_PREFIX}schema=1 run_token=native-r01"
                    " seq=0 rtt_us=100"
                ),
                (
                    f"{SAMPLE_PREFIX}schema=1 run_token=native-r01"
                    " seq=1 rtt_us=200"
                ),
                (
                    f"{FINAL_PREFIX}schema=1 run_token=native-r01 qos=RELIABLE"
                    " payload_bytes=512 rate_hz=50 target_tx=2 tx=2 rx=2"
                    " missing=0 duplicates=0 malformed=0 arrival_inversions=0"
                    " min_us=100 avg_us=150 p95_us=200 max_us=200"
                    " rtt_sum_us=300 ready_ms=20 durability=TRANSIENT_LOCAL"
                    " history=KEEP_LAST depth=10"
                ),
            ]
        )

    def validate(self, text: str) -> dict:
        return validate_probe_output(
            text,
            run_token="native-r01",
            qos="RELIABLE",
            durability="transient_local",
            history_depth=10,
            payload_bytes=512,
            rate_hz=50,
            target_tx=2,
        )

    def test_valid_output_reconciles(self) -> None:
        self.assertEqual(self.validate(self.valid_output())["sample_count"], 2)

    def test_duplicate_field_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate"):
            parse_record(f"{FINAL_PREFIX}schema=1 schema=1", FINAL_PREFIX)

    def test_missing_count_must_reconcile(self) -> None:
        text = self.valid_output().replace("missing=0", "missing=1")
        with self.assertRaisesRegex(ValueError, "missing count"):
            self.validate(text)

    def test_rtt_sidecar_sum_must_reconcile(self) -> None:
        text = self.valid_output().replace("rtt_sum_us=300", "rtt_sum_us=301")
        with self.assertRaisesRegex(ValueError, "sidecar sum"):
            self.validate(text)

    def test_wrong_identity_is_rejected(self) -> None:
        text = self.valid_output().replace("run_token=native-r01", "run_token=other")
        with self.assertRaisesRegex(ValueError, "run_token"):
            self.validate(text)

    def test_wrong_durability_is_rejected(self) -> None:
        text = self.valid_output().replace(
            "durability=TRANSIENT_LOCAL", "durability=VOLATILE"
        )
        with self.assertRaisesRegex(ValueError, "durability"):
            self.validate(text)

    def test_wrong_history_depth_is_rejected(self) -> None:
        text = self.valid_output().replace("depth=10", "depth=9")
        with self.assertRaisesRegex(ValueError, "depth"):
            self.validate(text)


if __name__ == "__main__":
    unittest.main()
