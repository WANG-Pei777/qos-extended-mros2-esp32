from pathlib import Path
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/experiment"))

import run_seven_qos_mechanism_hardware_case as runner  # noqa: E402


CANONICAL = """qdisc mq 0: root
qdisc fq_codel 0: parent :2 limit 10240p
qdisc fq_codel 0: parent :1 limit 10240p"""

LEGACY = """qdisc mq 0: root
qdisc pfifo_fast 0: parent :2 bands 3
qdisc pfifo_fast 0: parent :1 bands 3"""


class MechanismQdiscTests(unittest.TestCase):
    def test_canonical_state_is_accepted_without_mutation(self):
        with mock.patch.object(runner, "qdisc_state", return_value=CANONICAL), \
             mock.patch.object(runner.subprocess, "run") as command:
            self.assertEqual(runner.normalize_clean_qdisc("eth1"), CANONICAL)
            command.assert_not_called()

    def test_legacy_state_is_normalized_once(self):
        with mock.patch.object(
            runner, "qdisc_state", side_effect=(LEGACY, CANONICAL)
        ), mock.patch.object(runner.subprocess, "run") as command:
            self.assertEqual(runner.normalize_clean_qdisc("eth1"), CANONICAL)
            command.assert_called_once()
            self.assertEqual(
                command.call_args.args[0],
                ["sudo", "-n", "tc", "qdisc", "del", "dev", "eth1", "root"],
            )

    def test_impairment_is_rejected(self):
        with mock.patch.object(
            runner, "qdisc_state", return_value="qdisc netem 8001: root"
        ):
            with self.assertRaisesRegex(RuntimeError, "pre-existing impairment"):
                runner.normalize_clean_qdisc("eth1")

    def test_unknown_clean_layout_is_rejected(self):
        with mock.patch.object(
            runner, "qdisc_state", return_value="qdisc noqueue 0: root"
        ):
            with self.assertRaisesRegex(RuntimeError, "unsupported clean"):
                runner.normalize_clean_qdisc("eth1")

    def test_neighbor_refresh_uses_one_bounded_probe(self):
        with mock.patch.object(runner.subprocess, "run") as command:
            runner.refresh_board_neighbor("192.0.2.7")
            command.assert_called_once_with(
                ["ping", "-c", "1", "-W", "3", "192.0.2.7"],
                check=True,
                stdout=runner.subprocess.DEVNULL,
                stderr=runner.subprocess.DEVNULL,
            )


if __name__ == "__main__":
    unittest.main()
