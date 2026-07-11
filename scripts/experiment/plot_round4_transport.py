#!/usr/bin/env python3
"""Generate ROUND4 transport figures from summary CSV outputs."""

import argparse
import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


QOS_ORDER = ("best_effort", "reliable")
LABELS = {"best_effort": "Best Effort", "reliable": "Reliable"}
COLORS = {"best_effort": "#4c78a8", "reliable": "#f58518"}


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def by_qos(rows):
    grouped = {qos: [] for qos in QOS_ORDER}
    for row in rows:
        grouped[row["qos"]].append(row)
    for qos_rows in grouped.values():
        qos_rows.sort(key=lambda row: float(row["loss_pct"]))
    return grouped


def values(rows, key):
    return [float(row[key]) for row in rows]


def save_all(fig, output_dir, stem):
    for suffix in ("png", "svg"):
        fig.savefig(output_dir / f"{stem}.{suffix}", bbox_inches="tight", dpi=200)
    plt.close(fig)


def plot_delivery(summary_rows, output_dir):
    fig, ax = plt.subplots(figsize=(7.0, 4.2))
    for qos, rows in by_qos(summary_rows).items():
        xs = values(rows, "loss_pct")
        ys = values(rows, "delivery_mean_pct")
        low = values(rows, "delivery_mean_ci_low_pct")
        high = values(rows, "delivery_mean_ci_high_pct")
        yerr = [[y - lo for y, lo in zip(ys, low)], [hi - y for y, hi in zip(ys, high)]]
        ax.errorbar(xs, ys, yerr=yerr, marker="o", linewidth=2, capsize=3,
                    color=COLORS[qos], label=LABELS[qos])
    ax.set_xlabel("Host-to-board netem loss (%)")
    ax.set_ylabel("Delivery (%)")
    ax.set_ylim(80, 101)
    ax.grid(True, axis="y", alpha=0.25)
    ax.legend(frameon=False)
    save_all(fig, output_dir, "round4_delivery")


def plot_rtt(summary_rows, output_dir):
    fig, ax = plt.subplots(figsize=(7.0, 4.2))
    for qos, rows in by_qos(summary_rows).items():
        xs = values(rows, "loss_pct")
        ys = values(rows, "rtt_mean_ms")
        low = values(rows, "rtt_mean_ci_low_ms")
        high = values(rows, "rtt_mean_ci_high_ms")
        p95 = values(rows, "rtt_run_mean_p95_ms")
        yerr = [[y - lo for y, lo in zip(ys, low)], [hi - y for y, hi in zip(ys, high)]]
        ax.errorbar(xs, ys, yerr=yerr, marker="o", linewidth=2, capsize=3,
                    color=COLORS[qos], label=f"{LABELS[qos]} mean")
        ax.plot(xs, p95, linestyle="--", linewidth=1.5, color=COLORS[qos],
                alpha=0.7, label=f"{LABELS[qos]} run-mean p95")
    ax.set_xlabel("Host-to-board netem loss (%)")
    ax.set_ylabel("RTT (ms)")
    ax.grid(True, axis="y", alpha=0.25)
    ax.legend(frameon=False, ncol=2)
    save_all(fig, output_dir, "round4_rtt")


def plot_effects(effect_rows, output_dir):
    fig, (ax_delivery, ax_rtt) = plt.subplots(2, 1, figsize=(7.0, 6.0), sharex=True)
    xs = values(effect_rows, "loss_pct")

    delivery = values(effect_rows, "delivery_mean_difference_pp")
    delivery_low = values(effect_rows, "delivery_difference_ci_low_pp")
    delivery_high = values(effect_rows, "delivery_difference_ci_high_pp")
    delivery_err = [
        [y - lo for y, lo in zip(delivery, delivery_low)],
        [hi - y for y, hi in zip(delivery, delivery_high)],
    ]
    ax_delivery.axhline(0, color="#333333", linewidth=1)
    ax_delivery.errorbar(xs, delivery, yerr=delivery_err, marker="o", linewidth=2,
                         capsize=3, color="#54a24b")
    ax_delivery.set_ylabel("Delivery diff. (pp)")
    ax_delivery.grid(True, axis="y", alpha=0.25)

    rtt = values(effect_rows, "rtt_mean_difference_ms")
    rtt_low = values(effect_rows, "rtt_difference_ci_low_ms")
    rtt_high = values(effect_rows, "rtt_difference_ci_high_ms")
    rtt_err = [[y - lo for y, lo in zip(rtt, rtt_low)], [hi - y for y, hi in zip(rtt, rtt_high)]]
    ax_rtt.axhline(0, color="#333333", linewidth=1)
    ax_rtt.errorbar(xs, rtt, yerr=rtt_err, marker="o", linewidth=2,
                    capsize=3, color="#b279a2")
    ax_rtt.set_xlabel("Host-to-board netem loss (%)")
    ax_rtt.set_ylabel("RTT diff. (ms)")
    ax_rtt.grid(True, axis="y", alpha=0.25)

    save_all(fig, output_dir, "round4_qos_effects")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary-csv", required=True, type=Path)
    parser.add_argument("--effects-csv", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary_rows = read_csv(args.summary_csv)
    effect_rows = read_csv(args.effects_csv)
    plot_delivery(summary_rows, args.output_dir)
    plot_rtt(summary_rows, args.output_dir)
    plot_effects(effect_rows, args.output_dir)
    print(f"Wrote figures to {args.output_dir}")


if __name__ == "__main__":
    main()
