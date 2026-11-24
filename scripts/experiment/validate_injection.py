#!/usr/bin/env python3
"""Validate aggregate application-layer loss injection evidence in a CSV."""

import argparse
import csv
import math
import sys


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path")
    parser.add_argument("expected_loss", type=float)
    parser.add_argument("--min-attempts", type=int, default=1)
    return parser.parse_args()


def main():
    args = parse_args()
    if not 0.0 <= args.expected_loss <= 1.0:
        raise SystemExit("expected_loss must be in [0, 1]")

    with open(args.csv_path, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    required = {
        "host_loss_rate",
        "host_injection_attempted",
        "host_injection_dropped",
        "injection_layer",
    }
    if not rows or not required.issubset(rows[0]):
        raise SystemExit("CSV lacks ROUND4 injection evidence columns")

    attempted = 0
    dropped = 0
    for row in rows:
        if row["injection_layer"] != "application_reply":
            raise SystemExit(f"unexpected injection layer: {row['injection_layer']}")
        if not row["host_injection_attempted"] or not row["host_injection_dropped"]:
            raise SystemExit("missing host injection summary in one or more rows")
        if not math.isclose(float(row["host_loss_rate"]), args.expected_loss, abs_tol=1e-12):
            raise SystemExit("configured host loss rate does not match the condition")
        attempted += int(row["host_injection_attempted"])
        dropped += int(row["host_injection_dropped"])

    if attempted < args.min_attempts:
        raise SystemExit(
            f"only {attempted} injection attempts; need at least {args.min_attempts}"
        )

    observed = dropped / attempted
    if args.expected_loss == 0.0:
        if dropped != 0:
            raise SystemExit(f"0% condition dropped {dropped}/{attempted} messages")
        print(f"PASS: 0% injection, {attempted} attempts, 0 drops")
        return

    if dropped == 0:
        raise SystemExit(
            f"no observed drops over {attempted} attempts; injection evidence is insufficient"
        )

    # A broad four-sigma band avoids rejecting normal Bernoulli variation while
    # still detecting a materially different configured loss process.
    sigma = math.sqrt(args.expected_loss * (1.0 - args.expected_loss) / attempted)
    lower = max(0.0, args.expected_loss - 4.0 * sigma)
    upper = min(1.0, args.expected_loss + 4.0 * sigma)
    if not lower <= observed <= upper:
        raise SystemExit(
            f"observed loss {observed:.4%} outside 4-sigma band "
            f"[{lower:.4%}, {upper:.4%}]"
        )

    print(
        f"PASS: configured={args.expected_loss:.2%}, observed={observed:.2%}, "
        f"dropped={dropped}/{attempted}, band=[{lower:.2%}, {upper:.2%}]"
    )


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, csv.Error) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(2)
