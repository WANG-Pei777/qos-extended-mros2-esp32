#!/usr/bin/env python3

from __future__ import annotations

import unittest

from validate_benchmark_telemetry_smoke import validate_delivery_contract


def compare_lines(**final_overrides: str) -> list[bytes]:
    final = {
        "system": "mros2qos",
        "tx": "200",
        "rx": "200",
        "samples": "200",
        "payload_bytes": "64",
        "period_ms": "100",
        "telemetry": "on",
    }
    final.update(final_overrides)
    config_line = (
        "COMPARE_CONFIG system=mros2qos qos=BEST_EFFORT payload_bytes=64 "
        "messages=200 period_ms=100 telemetry=on"
    )
    final_line = "COMPARE_FINAL " + " ".join(
        f"{key}={value}" for key, value in final.items()
    )
    return [config_line.encode("ascii"), final_line.encode("ascii")]


def bench_config() -> dict[str, str]:
    return {
        "system": "mros2qos",
        "qos": "BEST_EFFORT",
        "payload_bytes": "64",
        "rate_hz": "10",
        "target_tx": "200",
        "impairment": "clean",
        "window_ms": "20000",
        "period_ms": "100",
        "interval_count": "200",
    }


def bench_final(**overrides: str) -> dict[str, str]:
    fields = {
        "attempted_tx": "200",
        "publish_failures": "0",
        "rx": "200",
        "duplicates": "0",
        "malformed": "0",
        "rtt_samples": "200",
    }
    fields.update(overrides)
    return fields


class DeliveryContractValidationTest(unittest.TestCase):
    def test_valid_delivery(self) -> None:
        result = validate_delivery_contract(
            compare_lines(), bench_config(), bench_final()
        )
        self.assertEqual(result["rx"], "200")

    def test_compare_rx_loss_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "COMPARE_FINAL rx"):
            validate_delivery_contract(
                compare_lines(rx="199", samples="199"),
                bench_config(),
                bench_final(rx="199", rtt_samples="199"),
            )

    def test_publish_failure_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "publish_failures"):
            validate_delivery_contract(
                compare_lines(), bench_config(), bench_final(publish_failures="1")
            )

    def test_delivery_loss_is_an_outcome_when_enabled(self) -> None:
        result = validate_delivery_contract(
            compare_lines(rx="199", samples="199"),
            bench_config(),
            bench_final(rx="199", rtt_samples="199"),
            require_full_delivery=False,
        )
        self.assertEqual(result["rx"], "199")

    def test_delivery_outcome_counts_must_reconcile(self) -> None:
        with self.assertRaisesRegex(ValueError, "delivered count"):
            validate_delivery_contract(
                compare_lines(rx="199", samples="198"),
                bench_config(),
                bench_final(rx="199", rtt_samples="199"),
                require_full_delivery=False,
            )

    def test_duplicate_compare_final_is_rejected(self) -> None:
        lines = compare_lines()
        with self.assertRaisesRegex(ValueError, "exactly one"):
            validate_delivery_contract(
                lines + [lines[-1]], bench_config(), bench_final()
            )

    def test_configurable_large_high_rate_contract(self) -> None:
        lines = compare_lines(
            tx="2000",
            rx="2000",
            samples="2000",
            payload_bytes="2048",
            period_ms="10",
        )
        lines[0] = (
            b"COMPARE_CONFIG system=mros2qos qos=BEST_EFFORT "
            b"payload_bytes=2048 messages=2000 period_ms=10 telemetry=on"
        )
        config = bench_config()
        config.update(
            payload_bytes="2048", rate_hz="100", target_tx="2000",
            period_ms="100"
        )
        final = bench_final()
        final.update(attempted_tx="2000", rx="2000", rtt_samples="2000")
        result = validate_delivery_contract(
            lines,
            config,
            final,
            expected_payload_bytes=2048,
            expected_rate_hz=100,
            expected_target_tx=2000,
        )
        self.assertEqual(result["rx"], "2000")

    def test_delivery_observability_reconciles(self) -> None:
        fields = {
            "missing": "2",
            "missing_runs": "1",
            "max_missing_run": "2",
            "arrival_inversions": "3",
            "rtt_sum_us": "198000",
            "rtt_sum_sq_us2": "198000000",
        }
        lines = compare_lines(
            rx="198",
            samples="198",
            min_us="1000",
            avg_us="1000",
            max_us="1000",
            **fields,
        )
        result = validate_delivery_contract(
            lines,
            bench_config(),
            bench_final(rx="198", rtt_samples="198", **fields),
            require_full_delivery=False,
        )
        self.assertEqual(result["max_missing_run"], "2")

    def test_delivery_observability_rejects_wrong_missing_count(self) -> None:
        fields = {
            "missing": "1",
            "missing_runs": "1",
            "max_missing_run": "1",
            "arrival_inversions": "0",
            "rtt_sum_us": "198000",
            "rtt_sum_sq_us2": "198000000",
        }
        with self.assertRaisesRegex(ValueError, "missing count"):
            validate_delivery_contract(
                compare_lines(
                    rx="198", samples="198", avg_us="1000", **fields
                ),
                bench_config(),
                bench_final(rx="198", rtt_samples="198", **fields),
                require_full_delivery=False,
            )

    def test_delivery_observability_rejects_partial_fields(self) -> None:
        with self.assertRaisesRegex(ValueError, "incomplete"):
            validate_delivery_contract(
                compare_lines(missing="0"),
                bench_config(),
                bench_final(missing="0"),
            )


if __name__ == "__main__":
    unittest.main()
