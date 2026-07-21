#!/usr/bin/env python3
"""Analyze the frozen paired telemetry runtime-overhead engineering pilot."""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import re
import statistics
from pathlib import Path


ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
SYSTEMS = ("mros2qos", "upstream", "microros")
BOOTSTRAP_SEED = 2026071702
BOOTSTRAP_RESAMPLES = 20_000
CPU_LIMIT_PP = 2.0
AGREEMENT_LIMIT_PP = 0.5


def parse_fields(line: str) -> dict[str, str]:
    return dict(token.split("=", 1) for token in line.split()[1:] if "=" in token)


def one(lines: list[str], prefix: str) -> dict[str, str]:
    matches = [parse_fields(line) for line in lines if line.startswith(prefix)]
    if len(matches) != 1:
        raise ValueError(f"expected one {prefix.strip()}, found {len(matches)}")
    return matches[0]


def percentile(sorted_values: list[float], probability: float) -> float:
    position = (len(sorted_values) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[lower]
    weight = position - lower
    return sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight


def paired_bootstrap(values: list[float], seed: int) -> tuple[float, float]:
    rng = random.Random(seed)
    size = len(values)
    means = sorted(
        statistics.fmean(values[rng.randrange(size)] for _ in range(size))
        for _ in range(BOOTSTRAP_RESAMPLES)
    )
    return percentile(means, 0.025), percentile(means, 0.975)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("campaign", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    campaign = args.campaign.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    with (campaign / "accepted_runs.csv").open(newline="", encoding="utf-8") as stream:
        accepted = list(csv.DictReader(stream))
    metrics = []
    for row in accepted:
        run_dir = campaign / row["relative_path"]
        text = (run_dir / "serial.raw").read_bytes().decode("utf-8", errors="replace")
        lines = [ANSI_RE.sub("", line).strip() for line in text.splitlines()]
        control = one(lines, "COMPARE_CPU_CONTROL ")
        final = one(lines, "COMPARE_FINAL ")
        mode = row["telemetry"]
        sample_cpu_mean_pp = ""
        agreement_pp = ""
        if mode == "on":
            samples = [
                parse_fields(line) for line in lines if line.startswith("BENCH_SAMPLE ")
            ]
            if len(samples) != 200:
                raise ValueError(f"{row['run_id']} has {len(samples)} BENCH_SAMPLE rows")
            sample_cpu_mean_pp = statistics.fmean(
                (int(sample["busy0_ppm"]) + int(sample["busy1_ppm"])) / 20_000
                for sample in samples
            )
            agreement_pp = abs(
                sample_cpu_mean_pp - int(control["busy_mean_ppm"]) / 10_000
            )
        metrics.append(
            {
                **row,
                "control_cpu_mean_pp": int(control["busy_mean_ppm"]) / 10_000,
                "sample_cpu_mean_pp": sample_cpu_mean_pp,
                "sample_control_agreement_pp": agreement_pp,
                "rtt_mean_us": int(final["avg_us"]),
                "rtt_max_us": int(final["max_us"]),
                "ready_ms": int(final["ready_ms"]),
                "rx": int(final["rx"]),
            }
        )

    metric_fields = list(metrics[0]) if metrics else [
        "ordinal", "run_id", "system", "telemetry"
    ]
    with (output / "run_metrics.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=metric_fields)
        writer.writeheader()
        writer.writerows(metrics)

    report = {
        "schema_version": 1,
        "classification": "telemetry_runtime_overhead_pilot_analysis",
        "accepted_runs": len(metrics),
        "scheduled_runs": 60,
        "status": "COMPLETE" if len(metrics) == 60 else "INCOMPLETE",
        "bootstrap": {
            "method": "paired_percentile",
            "seed": BOOTSTRAP_SEED,
            "resamples": BOOTSTRAP_RESAMPLES,
            "confidence": 0.95,
        },
        "systems": {},
    }
    pair_rows = []
    for system_index, system in enumerate(SYSTEMS):
        system_metrics = [row for row in metrics if row["system"] == system]
        by_pair: dict[str, dict[str, dict]] = {}
        for row in system_metrics:
            by_pair.setdefault(row["pair_id"], {})[row["telemetry"]] = row
        complete_pairs = {
            pair_id: modes for pair_id, modes in by_pair.items() if set(modes) == {"on", "off"}
        }
        cpu_differences = []
        rtt_differences = []
        rtt_ratios = []
        for pair_id in sorted(complete_pairs):
            modes = complete_pairs[pair_id]
            cpu_difference = (
                modes["on"]["control_cpu_mean_pp"]
                - modes["off"]["control_cpu_mean_pp"]
            )
            rtt_difference = modes["on"]["rtt_mean_us"] - modes["off"]["rtt_mean_us"]
            rtt_ratio = modes["on"]["rtt_mean_us"] / modes["off"]["rtt_mean_us"]
            cpu_differences.append(cpu_difference)
            rtt_differences.append(rtt_difference)
            rtt_ratios.append(rtt_ratio)
            pair_rows.append(
                {
                    "system": system,
                    "pair_id": pair_id,
                    "cpu_difference_pp": cpu_difference,
                    "rtt_mean_difference_us": rtt_difference,
                    "rtt_mean_ratio": rtt_ratio,
                }
            )

        result = {
            "accepted_on": sum(row["telemetry"] == "on" for row in system_metrics),
            "accepted_off": sum(row["telemetry"] == "off" for row in system_metrics),
            "complete_pairs": len(complete_pairs),
            "all_delivery_200_of_200": all(row["rx"] == 200 for row in system_metrics),
        }
        if cpu_differences:
            cpu_low, cpu_high = paired_bootstrap(
                cpu_differences, BOOTSTRAP_SEED + system_index
            )
            rtt_low, rtt_high = paired_bootstrap(
                rtt_differences, BOOTSTRAP_SEED + 10 + system_index
            )
            ratio_low, ratio_high = paired_bootstrap(
                rtt_ratios, BOOTSTRAP_SEED + 20 + system_index
            )
            agreements = [
                row["sample_control_agreement_pp"]
                for row in system_metrics
                if row["telemetry"] == "on"
            ]
            result.update(
                {
                    "cpu_overhead_mean_pp": statistics.fmean(cpu_differences),
                    "cpu_overhead_ci95_pp": [cpu_low, cpu_high],
                    "rtt_mean_difference_us": statistics.fmean(rtt_differences),
                    "rtt_difference_ci95_us": [rtt_low, rtt_high],
                    "rtt_mean_ratio": statistics.fmean(rtt_ratios),
                    "rtt_ratio_ci95": [ratio_low, ratio_high],
                    "maximum_sample_control_agreement_pp": max(agreements),
                    "rtt_review_trigger": statistics.fmean(rtt_ratios) > 1.10,
                }
            )
            if len(complete_pairs) == 10:
                result["cpu_gate_pass"] = (
                    result["cpu_overhead_mean_pp"] <= CPU_LIMIT_PP
                    and cpu_high <= CPU_LIMIT_PP
                    and result["maximum_sample_control_agreement_pp"]
                    <= AGREEMENT_LIMIT_PP
                    and result["all_delivery_200_of_200"]
                )
        report["systems"][system] = result

    pair_fields = [
        "system",
        "pair_id",
        "cpu_difference_pp",
        "rtt_mean_difference_us",
        "rtt_mean_ratio",
    ]
    with (output / "paired_differences.csv").open(
        "w", newline="", encoding="utf-8"
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=pair_fields)
        writer.writeheader()
        writer.writerows(pair_rows)

    if report["status"] == "COMPLETE":
        report["overall_cpu_gate_pass"] = all(
            report["systems"][system].get("cpu_gate_pass") is True for system in SYSTEMS
        )
    (output / "analysis_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"PASS: status={report['status']} accepted={len(metrics)}/60 "
        + " ".join(
            f"{system}_pairs={report['systems'][system]['complete_pairs']}"
            for system in SYSTEMS
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
