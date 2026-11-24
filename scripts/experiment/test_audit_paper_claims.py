#!/usr/bin/env python3
"""Unit tests for manuscript claim auditing helpers."""

import csv
from pathlib import Path
import tempfile
import unittest

from audit_paper_claims import (
    check_csv_assertion,
    parse_root_overrides,
    values_equal,
)


class PaperClaimAuditTests(unittest.TestCase):
    def test_numeric_comparison_uses_absolute_tolerance(self):
        self.assertTrue(values_equal("1.0000000005", 1.0, 1e-9))
        self.assertFalse(values_equal("1.000000002", 1.0, 1e-9))

    def test_root_override_parsing(self):
        overrides = parse_root_overrides(["round6=/tmp/round6", "p4=~/p4"])
        self.assertEqual(overrides["round6"], Path("/tmp/round6"))
        self.assertEqual(overrides["p4"], Path("~/p4").expanduser())
        with self.assertRaises(ValueError):
            parse_root_overrides(["round6"])

    def test_csv_assertion_requires_one_matching_row(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "claims.csv"
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=("name", "effect"))
                writer.writeheader()
                writer.writerow({"name": "supported", "effect": "2.5"})
                writer.writerow({"name": "null", "effect": "0.1"})
            errors = []
            check_csv_assertion(
                root,
                {
                    "path": "claims.csv",
                    "selector": {"name": "supported"},
                    "expected": {"effect": 2.5},
                },
                1e-9,
                errors,
            )
            self.assertEqual(errors, [])

    def test_csv_assertion_rejects_missing_selector(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "claims.csv"
            path.write_text("name,effect\nsupported,2.5\n", encoding="utf-8")
            errors = []
            check_csv_assertion(
                root,
                {
                    "path": "claims.csv",
                    "selector": {"name": "missing"},
                    "expected": {"effect": 2.5},
                },
                1e-9,
                errors,
            )
            self.assertEqual(len(errors), 1)


if __name__ == "__main__":
    unittest.main()
