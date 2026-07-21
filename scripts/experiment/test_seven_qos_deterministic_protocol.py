#!/usr/bin/env python3

from __future__ import annotations

import unittest
from collections import Counter

from generate_seven_qos_deterministic_protocol import DEFAULT_SOURCE, expand_cases
from validate_seven_qos_protocol import load_json


class DeterministicProtocolExpansionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = expand_cases(load_json(DEFAULT_SOURCE))

    def test_total_and_unique_ids(self) -> None:
        self.assertEqual(len(self.rows), 84)
        self.assertEqual(len({row["case_id"] for row in self.rows}), 84)

    def test_case_type_counts(self) -> None:
        self.assertEqual(
            Counter(row["case_type"] for row in self.rows),
            {"compatibility": 48, "mechanism": 36},
        )

    def test_ordinals_are_gapless(self) -> None:
        self.assertEqual(
            [int(row["ordinal"]) for row in self.rows], list(range(1, 85))
        )

    def test_compatibility_axes_are_explicit(self) -> None:
        compatibility = [
            row for row in self.rows if row["case_type"] == "compatibility"
        ]
        self.assertTrue(all(row["direction"] for row in compatibility))
        self.assertTrue(
            all(row["endpoint_creation_order"] for row in compatibility)
        )
        self.assertTrue(
            all("expected_match" in row["expected_json"] for row in compatibility)
        )


if __name__ == "__main__":
    unittest.main()
