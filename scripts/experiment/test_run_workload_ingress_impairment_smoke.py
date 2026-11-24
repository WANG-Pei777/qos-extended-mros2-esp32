#!/usr/bin/env python3

from pathlib import Path
import sys
import unittest


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from run_workload_ingress_impairment_smoke import (
    cleanup_commands,
    ingress_commands,
)


class IngressImpairmentCommandTests(unittest.TestCase):
    def test_setup_is_source_scoped_and_uses_ifb_netem(self):
        commands = ingress_commands(
            "eth1", "ifb0", "172.24.195.36", ("loss", "random", "5%")
        )
        self.assertEqual(commands[0], ["modprobe", "ifb", "numifbs=1"])
        self.assertIn("172.24.195.36/32", commands[3])
        self.assertEqual(commands[3][-2:], ["dev", "ifb0"])
        self.assertEqual(
            commands[4],
            ["tc", "qdisc", "replace", "dev", "ifb0", "root", "netem",
             "loss", "random", "5%"],
        )

    def test_cleanup_removes_ingress_before_disabling_ifb(self):
        self.assertEqual(
            cleanup_commands("eth1", "ifb0"),
            [
                ["tc", "qdisc", "del", "dev", "eth1", "ingress"],
                ["tc", "qdisc", "del", "dev", "ifb0", "root"],
                ["ip", "link", "set", "dev", "ifb0", "down"],
            ],
        )


if __name__ == "__main__":
    unittest.main()
