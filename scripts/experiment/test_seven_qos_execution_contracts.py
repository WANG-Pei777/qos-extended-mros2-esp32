#!/usr/bin/env python3

from __future__ import annotations

from copy import deepcopy
import unittest

from generate_seven_qos_performance_protocol import load_json
from validate_seven_qos_execution_contracts import (
    DEFAULT_CONTRACTS,
    DEFAULT_SOURCE,
    validate_contracts,
)


class SevenQosExecutionContractsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.contracts = load_json(DEFAULT_CONTRACTS)
        self.source = load_json(DEFAULT_SOURCE)

    def test_frozen_contract_covers_all_cells_and_stays_blocked(self) -> None:
        summary = validate_contracts(self.contracts, self.source)
        self.assertEqual(summary["families"], 6)
        self.assertEqual(summary["cells"], 51)
        self.assertEqual(summary["smoke_ready_families"], 6)

    def test_root_formal_gate_cannot_be_enabled(self) -> None:
        changed = deepcopy(self.contracts)
        changed["formal_launch_allowed"] = True
        with self.assertRaisesRegex(ValueError, "root formal launch gate"):
            validate_contracts(changed, self.source)

    def test_missing_cell_is_rejected(self) -> None:
        changed = deepcopy(self.contracts)
        changed["family_contracts"]["deadline"]["cell_ids"].pop()
        with self.assertRaisesRegex(ValueError, "Deadline|deadline"):
            validate_contracts(changed, self.source)

    def test_liveliness_smoke_pair_cannot_be_reduced(self) -> None:
        changed = deepcopy(self.contracts)
        changed["family_contracts"]["liveliness"]["smoke_gates"].pop()
        with self.assertRaisesRegex(ValueError, "Liveliness"):
            validate_contracts(changed, self.source)

    def test_resource_smoke_set_cannot_be_reduced(self) -> None:
        changed = deepcopy(self.contracts)
        changed["family_contracts"]["resource_limits"]["smoke_gates"].pop()
        with self.assertRaisesRegex(ValueError, "Resource Limits"):
            validate_contracts(changed, self.source)

    def test_history_smoke_set_cannot_be_reduced(self) -> None:
        changed = deepcopy(self.contracts)
        changed["family_contracts"]["history_depth"]["smoke_gates"].pop()
        with self.assertRaisesRegex(ValueError, "History/Depth"):
            validate_contracts(changed, self.source)

    def test_durability_smoke_pair_cannot_be_reduced(self) -> None:
        changed = deepcopy(self.contracts)
        changed["family_contracts"]["durability"]["smoke_gates"].pop()
        with self.assertRaisesRegex(ValueError, "Durability"):
            validate_contracts(changed, self.source)


if __name__ == "__main__":
    unittest.main()
