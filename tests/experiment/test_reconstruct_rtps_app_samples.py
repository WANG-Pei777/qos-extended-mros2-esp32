import importlib.util
from pathlib import Path
import unittest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "experiment"
    / "reconstruct_rtps_app_samples.py"
)
SPEC = importlib.util.spec_from_file_location("rtps_reconstruct", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class SequenceSetTests(unittest.TestCase):
    def test_decodes_single_requested_sequence(self):
        self.assertEqual(
            MODULE.decode_sequence_set(43, 1, "00:00:00:80"),
            [43],
        )

    def test_decodes_five_requested_sequences(self):
        self.assertEqual(
            MODULE.decode_sequence_set(39, 5, "00:00:00:f8"),
            [39, 40, 41, 42, 43],
        )

    def test_decodes_sparse_requested_sequences(self):
        self.assertEqual(
            MODULE.decode_sequence_set(10, 3, "00:00:00:a0"),
            [10, 12],
        )


class NackLinkTests(unittest.TestCase):
    def test_acknack_uses_target_writer_guid_for_run(self):
        events = [
            {
                "flow": "board_to_host_app",
                "source_ip": "board",
                "event_type": "data",
                "source_guid": "board-one",
                "destination_guid": "",
                "time_s": 1.0,
            },
            {
                "flow": "host_to_board_reply",
                "source_ip": "host",
                "event_type": "data",
                "source_guid": "host-one",
                "destination_guid": "",
                "time_s": 1.1,
            },
            {
                "flow": "host_to_board_reply",
                "source_ip": "host",
                "event_type": "data",
                "source_guid": "host-two",
                "destination_guid": "",
                "time_s": 2.0,
            },
            {
                "flow": "board_to_host_app",
                "source_ip": "host",
                "event_type": "acknack",
                "source_guid": "host-two",
                "destination_guid": "board-one",
                "time_s": 2.1,
            },
        ]
        MODULE.assign_runs(events, "board", "host")
        self.assertEqual(events[-1]["run_id"], 1)

    def test_links_nack_to_later_same_sequence_data(self):
        events = [
            {
                "run_id": 1,
                "flow": "board_to_host_app",
                "event_type": "data",
                "sequence": 7,
                "time_s": 1.0,
            },
            {
                "run_id": 1,
                "flow": "board_to_host_app",
                "event_type": "acknack",
                "frame_number": 10,
                "time_s": 2.0,
                "acknack_count": 3,
                "requested_sequences": [7],
            },
            {
                "run_id": 1,
                "flow": "board_to_host_app",
                "event_type": "data",
                "sequence": 7,
                "time_s": 2.25,
            },
        ]
        links = MODULE.reconstruct_nack_links(
            events,
            1,
            "board_to_host_app",
        )
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]["prior_data_observed"], 1)
        self.assertEqual(links[0]["post_nack_data_observed"], 1)
        self.assertAlmostEqual(links[0]["nack_to_next_data_ms"], 250.0)


if __name__ == "__main__":
    unittest.main()
