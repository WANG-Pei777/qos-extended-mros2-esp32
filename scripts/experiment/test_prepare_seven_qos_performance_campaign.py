#!/usr/bin/env python3

from collections import Counter
import json
from pathlib import Path
import unittest

from generate_seven_qos_performance_protocol import (
    DEFAULT_SOURCE,
    expand_schedule,
    load_json,
)
from prepare_seven_qos_performance_campaign import build_tables


class PrepareSevenQosPerformanceCampaignTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        source = load_json(DEFAULT_SOURCE)
        cls.schedule, cls.cells = expand_schedule(source, 2026072301)
        cls.requirements, cls.plan = build_tables(cls.schedule, cls.cells)

    def test_table_sizes_and_unique_paths(self) -> None:
        self.assertEqual(len(self.requirements), 51)
        self.assertEqual(len(self.plan), 1530)
        self.assertEqual(
            len({row["candidate_relative_path"] for row in self.plan}), 1530
        )

    def test_every_cell_remains_n30(self) -> None:
        counts = Counter((row["family"], row["cell_id"]) for row in self.plan)
        self.assertEqual(set(counts.values()), {30})

    def test_one_stable_firmware_token_is_bound_per_cell(self) -> None:
        tokens = {row["firmware_run_token"] for row in self.requirements}
        self.assertEqual(len(tokens), 51)
        self.assertTrue(all(token.startswith("sqc-") for token in tokens))
        for row in self.requirements:
            self.assertTrue(
                row["firmware_run_token"].endswith(
                    row["configuration_sha256"][:12]
                )
            )

    def test_runner_routing_is_directionally_explicit(self) -> None:
        kinds = {
            row["family"]: row["runner_kind"] for row in self.requirements
        }
        self.assertEqual(kinds["history_depth"], "workload_ingress")
        self.assertEqual(kinds["deadline"], "workload_egress")
        self.assertEqual(kinds["resource_limits"], "workload_egress")
        self.assertEqual(kinds["durability"], "workload_egress")
        self.assertEqual(kinds["lifespan"], "workload_egress")

    def test_profiles_cover_frozen_levels(self) -> None:
        profiles = {
            (row["family"], row["network_profile"])
            for row in self.requirements
        }
        self.assertIn(("history_depth", "loss5_independent_b2h"), profiles)
        self.assertIn(("history_depth", "loss15_independent_b2h"), profiles)
        self.assertIn(("deadline", "delay50ms_h2b"), profiles)
        self.assertIn(("liveliness", "liveliness_outage_h2b"), profiles)
        self.assertIn(
            ("resource_limits", "resource_ack_suppression_h2b"), profiles
        )

    def test_every_binding_is_fail_closed(self) -> None:
        self.assertEqual(
            {row["artifact_bundle_status"] for row in self.requirements},
            {"UNBOUND"},
        )
        self.assertEqual(
            {row["launch_status"] for row in self.plan},
            {"BLOCKED_UNFROZEN_CELL_BINDING"},
        )
        for row in self.requirements:
            reasons = json.loads(row["blocking_reasons_json"])
            self.assertIn("exact_cell_firmware_bundle_unfrozen", reasons)

    def test_plan_preserves_frozen_identity(self) -> None:
        for scheduled, planned in zip(self.schedule, self.plan):
            self.assertEqual(planned["ordinal"], scheduled["ordinal"])
            self.assertEqual(planned["run_token"], scheduled["run_token"])
            self.assertEqual(planned["cell_id"], scheduled["cell_id"])


if __name__ == "__main__":
    unittest.main()
