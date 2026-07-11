#!/usr/bin/env python3
"""Summarize validated ROUND4 transport CSVs with deterministic bootstrap CIs."""

import argparse
import csv
import math
from pathlib import Path
import random
import re
import statistics


CONDITION_RE = re.compile(r"^round4_transport_(reliable|best_effort)_(\d+)pct$")
REQUIRED_COLUMNS = {"condition", "formal_run", "tx_count", "rx_count", "rtt_avg_us"}


def percentile(values, fraction):
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    return values[lower] if lower == upper else (
        values[lower] + (values[upper] - values[lower]) * (position - lower)
    )


def bootstrap_ci(values, samples, rng):
    """Percentile-bootstrap 95% CI for the mean of independent observations."""
    size = len(values)
    estimates = sorted(
        statistics.mean(values[rng.randrange(size)] for _ in range(size))
        for _ in range(samples)
    )
    return percentile(estimates, 0.025), percentile(estimates, 0.975)


def read_condition(path):
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("contains no rows")
    if not REQUIRED_COLUMNS.issubset(rows[0]):
        missing = ", ".join(sorted(REQUIRED_COLUMNS.difference(rows[0])))
        raise ValueError(f"missing required columns: {missing}")
    condition = rows[0].get("condition", "")
    match = CONDITION_RE.fullmatch(condition)
    if match is None:
        raise ValueError(f"unexpected condition {condition!r}")
    if any(row.get("condition") != condition for row in rows):
        raise ValueError("contains multiple conditions")
    if any(row.get("formal_run") != "1" for row in rows):
        raise ValueError("contains non-formal rows")
    return match.group(1), int(match.group(2)), rows


def delivery_values(rows):
    return [100.0 * int(row["rx_count"]) / int(row["tx_count"]) for row in rows]


def rtt_values(rows):
    return [float(row["rtt_avg_us"]) / 1000.0 for row in rows]


def summarize(qos, loss_pct, rows, samples, rng):
    delivery = delivery_values(rows)
    rtt = rtt_values(rows)
    delivery_ci = bootstrap_ci(delivery, samples, rng)
    rtt_ci = bootstrap_ci(rtt, samples, rng)
    return {
        "qos": qos,
        "loss_pct": loss_pct,
        "n": len(rows),
        "delivery_mean_pct": statistics.mean(delivery),
        "delivery_median_pct": statistics.median(delivery),
        "delivery_sd_pct": statistics.stdev(delivery) if len(delivery) > 1 else 0.0,
        "delivery_mean_ci_low_pct": delivery_ci[0],
        "delivery_mean_ci_high_pct": delivery_ci[1],
        "rtt_mean_ms": statistics.mean(rtt),
        "rtt_median_ms": statistics.median(rtt),
        "rtt_sd_ms": statistics.stdev(rtt) if len(rtt) > 1 else 0.0,
        "rtt_mean_ci_low_ms": rtt_ci[0],
        "rtt_mean_ci_high_ms": rtt_ci[1],
    }


def difference_ci(left, right, samples, rng):
    estimates = []
    for _ in range(samples):
        left_mean = statistics.mean(left[rng.randrange(len(left))] for _ in range(len(left)))
        right_mean = statistics.mean(right[rng.randrange(len(right))] for _ in range(len(right)))
        estimates.append(left_mean - right_mean)
    estimates.sort()
    return percentile(estimates, 0.025), percentile(estimates, 0.975)


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def fmt(value):
    return f"{value:.3f}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_paths", nargs="+", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--bootstrap-samples", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20260711)
    args = parser.parse_args()
    if args.bootstrap_samples < 1000:
        parser.error("--bootstrap-samples must be at least 1000")

    groups = {}
    for path in args.csv_paths:
        try:
            qos, loss_pct, rows = read_condition(path)
        except (OSError, ValueError, csv.Error) as exc:
            raise SystemExit(f"FAIL: {path}: {exc}") from exc
        key = (qos, loss_pct)
        if key in groups:
            raise SystemExit(f"FAIL: duplicate condition input {key}")
        groups[key] = rows

    rng = random.Random(args.seed)
    condition_rows = [
        summarize(qos, loss_pct, rows, args.bootstrap_samples, rng)
        for (qos, loss_pct), rows in sorted(groups.items(), key=lambda item: (item[0][1], item[0][0]))
    ]

    effects = []
    for loss_pct in sorted({loss for _, loss in groups}):
        reliable = groups.get(("reliable", loss_pct))
        best_effort = groups.get(("best_effort", loss_pct))
        if reliable is None or best_effort is None:
            continue
        reliable_delivery, best_delivery = delivery_values(reliable), delivery_values(best_effort)
        reliable_rtt, best_rtt = rtt_values(reliable), rtt_values(best_effort)
        delivery_ci = difference_ci(reliable_delivery, best_delivery, args.bootstrap_samples, rng)
        rtt_ci = difference_ci(reliable_rtt, best_rtt, args.bootstrap_samples, rng)
        effects.append({
            "loss_pct": loss_pct,
            "reliable_n": len(reliable),
            "best_effort_n": len(best_effort),
            "delivery_mean_difference_pp": statistics.mean(reliable_delivery) - statistics.mean(best_delivery),
            "delivery_difference_ci_low_pp": delivery_ci[0],
            "delivery_difference_ci_high_pp": delivery_ci[1],
            "rtt_mean_difference_ms": statistics.mean(reliable_rtt) - statistics.mean(best_rtt),
            "rtt_difference_ci_low_ms": rtt_ci[0],
            "rtt_difference_ci_high_ms": rtt_ci[1],
        })

    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = args.output_dir / "round4_transport_summary.csv"
    effect_path = args.output_dir / "round4_transport_qos_effects.csv"
    markdown_path = args.output_dir / "round4_transport_summary.md"
    write_csv(summary_path, condition_rows)
    if effects:
        write_csv(effect_path, effects)
    else:
        effect_path.write_text("loss_pct\n", encoding="utf-8")

    lines = [
        "# ROUND4 Transport Summary", "",
        f"Bootstrap: percentile 95% CI; {args.bootstrap_samples} resamples; seed {args.seed}.",
        "Source CSVs must pass `validate_round4.py` before interpretation.", "",
        "## Conditions", "",
        "| QoS | Loss (%) | N | Delivery mean % [95% CI] | Delivery median % | Delivery SD % | RTT mean ms [95% CI] | RTT median ms | RTT SD ms |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in condition_rows:
        lines.append(
            "| {qos} | {loss_pct} | {n} | {delivery_mean_pct:.3f} [{delivery_mean_ci_low_pct:.3f}, {delivery_mean_ci_high_pct:.3f}] | {delivery_median_pct:.3f} | {delivery_sd_pct:.3f} | {rtt_mean_ms:.3f} [{rtt_mean_ci_low_ms:.3f}, {rtt_mean_ci_high_ms:.3f}] | {rtt_median_ms:.3f} | {rtt_sd_ms:.3f} |".format(**row)
        )
    lines.extend(["", "## QoS Effects (RELIABLE minus BEST_EFFORT)", ""])
    if effects:
        lines.extend([
            "| Loss (%) | Reliable N | Best Effort N | Delivery difference pp [95% CI] | RTT mean difference ms [95% CI] |",
            "| ---: | ---: | ---: | ---: | ---: |",
        ])
        for row in effects:
            lines.append(
                f"| {row['loss_pct']} | {row['reliable_n']} | {row['best_effort_n']} | "
                f"{fmt(row['delivery_mean_difference_pp'])} [{fmt(row['delivery_difference_ci_low_pp'])}, {fmt(row['delivery_difference_ci_high_pp'])}] | "
                f"{fmt(row['rtt_mean_difference_ms'])} [{fmt(row['rtt_difference_ci_low_ms'])}, {fmt(row['rtt_difference_ci_high_ms'])}] |"
            )
    else:
        lines.append("No matched QoS pairs were supplied.")
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Wrote {summary_path}")
    print(f"Wrote {effect_path}")
    print(f"Wrote {markdown_path}")


if __name__ == "__main__":
    main()
