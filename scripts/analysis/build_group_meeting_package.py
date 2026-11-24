#!/usr/bin/env python3
"""Build the 2026-07-17 group-meeting evidence package.

The script reads only audited analysis outputs. It does not modify raw results.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import shutil
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


COLORS = {
    "best_effort": "#0072B2",
    "reliable": "#D55E00",
    "supported": "#009E73",
    "focused": "#E69F00",
    "none": "#B7BEC8",
    "text": "#20252B",
    "grid": "#D9DEE5",
}
QOS_LABELS = {"best_effort": "Best Effort", "reliable": "Reliable"}
MARKERS = {"best_effort": "o", "reliable": "s"}
LOSS_LEVELS = (0, 1, 5, 10, 15)

R4_H2B = Path("results/experiments/20260711_net37/analysis")
R4_B2H = Path(
    "results/experiments/20260712_rtt_samples_b2h_net219_v2/analysis"
)
R6 = Path(
    "results/experiments/20260713_round6_formal_5dabf7e/analysis/complete_1c99afa"
)
R6_ROOT = Path("results/experiments/20260713_round6_formal_5dabf7e")
REPRESENTATIVE_PCAP = R6_ROOT / Path(
    "pcaps/20260714_121043_round6_d05_h4000_"
    "b2h_target15_gact1of7_eff14p285714.pcapng"
)
REPRESENTATIVE_PCAP_SHA256 = (
    "4f4beea2e2600005af569b8603b39ebd37c5fbda1403d48d024eadb8377fd65c"
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def setup_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10.5,
            "axes.titlesize": 11.5,
            "axes.labelsize": 10.5,
            "axes.titleweight": "bold",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.edgecolor": COLORS["text"],
            "axes.labelcolor": COLORS["text"],
            "xtick.color": COLORS["text"],
            "ytick.color": COLORS["text"],
            "legend.fontsize": 9.5,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
        }
    )


def save_figure(fig: plt.Figure, output_dir: Path, stem: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for suffix in ("png", "pdf", "svg"):
        fig.savefig(
            output_dir / f"{stem}.{suffix}",
            dpi=320,
            bbox_inches="tight",
            pad_inches=0.06,
        )
    plt.close(fig)


def grouped(rows: list[dict[str, str]], key: str) -> dict[str, list[dict[str, str]]]:
    output: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        output[row[key]].append(row)
    for values in output.values():
        values.sort(key=lambda row: float(row["loss_pct"]))
    return output


def asym_error(rows, mean_key, low_key, high_key):
    means = np.asarray([float(row[mean_key]) for row in rows])
    lows = np.asarray([float(row[low_key]) for row in rows])
    highs = np.asarray([float(row[high_key]) for row in rows])
    return means, np.vstack([means - lows, highs - means])


def plot_delivery(ax, rows, title, x_label):
    for qos in ("best_effort", "reliable"):
        selected = grouped(rows, "qos")[qos]
        xs = np.asarray([float(row["loss_pct"]) for row in selected])
        means, errors = asym_error(
            selected,
            "delivery_mean_pct",
            "delivery_mean_ci_low_pct",
            "delivery_mean_ci_high_pct",
        )
        ax.errorbar(
            xs,
            means,
            yerr=errors,
            color=COLORS[qos],
            marker=MARKERS[qos],
            markersize=5.3,
            linewidth=1.9,
            capsize=2.8,
            label=QOS_LABELS[qos],
        )
    ax.set_title(title, loc="left")
    ax.set_xlabel(x_label)
    ax.set_ylabel("Delivery (%)")
    ax.set_xticks(LOSS_LEVELS)
    ax.set_ylim(72, 101)
    ax.grid(axis="y", color=COLORS["grid"], linewidth=0.7)


def build_round4_figure(repo_root: Path, figure_dir: Path) -> None:
    h2b = read_csv(repo_root / R4_H2B / "round4_transport_summary.csv")
    b2h = read_csv(repo_root / R4_B2H / "round4_transport_summary.csv")
    message = read_csv(repo_root / R4_B2H / "round4_rtt_message_summary.csv")
    message_effects = read_csv(
        repo_root / R4_B2H / "round4_rtt_message_qos_effects.csv"
    )

    fig, axes = plt.subplots(2, 2, figsize=(10.0, 7.0), constrained_layout=True)
    plot_delivery(
        axes[0, 0], h2b, "A  Host-to-board impairment", "Injected loss (%)"
    )
    plot_delivery(
        axes[0, 1], b2h, "B  Board-to-host impairment", "Injected loss (%)"
    )
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="upper center",
        ncol=2,
        frameon=False,
        bbox_to_anchor=(0.5, 1.025),
    )

    message_groups = grouped(message, "qos")
    for qos in ("best_effort", "reliable"):
        selected = message_groups[qos]
        xs = np.asarray([float(row["loss_pct"]) for row in selected])
        means, errors = asym_error(
            selected,
            "rtt_message_p95_ms",
            "rtt_message_p95_ci_low_ms",
            "rtt_message_p95_ci_high_ms",
        )
        axes[1, 0].errorbar(
            xs,
            means,
            yerr=errors,
            color=COLORS[qos],
            marker=MARKERS[qos],
            markersize=5.3,
            linewidth=1.9,
            capsize=2.8,
        )
    axes[1, 0].set_title("C  Board-to-host application RTT tail", loc="left")
    axes[1, 0].set_xlabel("Injected loss (%)")
    axes[1, 0].set_ylabel("Per-message RTT p95 (ms, log scale)")
    axes[1, 0].set_xticks(LOSS_LEVELS)
    axes[1, 0].set_yscale("log")
    axes[1, 0].set_ylim(10, 10000)
    axes[1, 0].grid(axis="y", which="both", color=COLORS["grid"], linewidth=0.7)

    effects = sorted(message_effects, key=lambda row: float(row["loss_pct"]))
    xs = np.asarray([float(row["loss_pct"]) for row in effects])
    estimates, errors = asym_error(
        effects,
        "rtt_message_p95_difference_ms",
        "rtt_message_p95_difference_ci_low_ms",
        "rtt_message_p95_difference_ci_high_ms",
    )
    axes[1, 1].axhline(0, color=COLORS["text"], linewidth=0.9)
    axes[1, 1].errorbar(
        xs,
        estimates,
        yerr=errors,
        color="#7A5195",
        marker="D",
        markersize=5.0,
        linewidth=1.8,
        capsize=2.8,
    )
    axes[1, 1].set_title("D  Reliable minus Best Effort", loc="left")
    axes[1, 1].set_xlabel("Board-to-host injected loss (%)")
    axes[1, 1].set_ylabel("RTT p95 difference (ms)")
    axes[1, 1].set_xticks(LOSS_LEVELS)
    axes[1, 1].grid(axis="y", color=COLORS["grid"], linewidth=0.7)

    fig.suptitle(
        "Round 4: QoS behavior depends on impairment direction",
        fontsize=14,
        fontweight="bold",
        y=1.07,
    )
    fig.text(
        0.5,
        -0.015,
        "N = 30 independent runs per QoS/loss cell. Error bars are 95% bootstrap CI; "
        "RTT p95 uses run-cluster bootstrap.",
        ha="center",
        fontsize=9,
        color="#505860",
    )
    save_figure(fig, figure_dir, "fig02_round4_directional_qos")


def build_qos_scope_figure(figure_dir: Path, origin_dir: Path) -> None:
    rows = [
        ("Reliability", "RELIABLE + BEST_EFFORT", "Bidirectional hardware", "R4 policy + R6 mechanism"),
        ("History", "KEEP_LAST(depth)", "Focused hardware", "R6 depth intervention"),
        ("Durability", "VOLATILE + TRANSIENT_LOCAL", "Late-join hardware", "Not performance-tested"),
        ("Deadline", "Finite period + counters", "Focused hardware", "Not performance-tested"),
        ("Lifespan", "Finite duration + aging", "Focused hardware", "Not performance-tested"),
        ("Liveliness", "AUTOMATIC", "Focused hardware", "Not performance-tested"),
        ("Resource limits", "Samples + local byte limit", "Focused hardware", "Not performance-tested"),
    ]
    columns = ["Implemented/configured", "Hardware evidence", "Formal experiment"]
    fig, ax = plt.subplots(figsize=(10.0, 4.6))
    ax.set_xlim(-0.7, 2.7)
    ax.set_ylim(-0.8, len(rows) - 0.2)
    ax.invert_yaxis()
    ax.set_xticks(range(3), columns)
    ax.xaxis.tick_top()
    ax.tick_params(axis="x", length=0, labelsize=10.5, pad=10)
    ax.set_yticks(range(len(rows)), [row[0] for row in rows])
    ax.tick_params(axis="y", length=0, pad=8)
    for y, row in enumerate(rows):
        ax.axhline(y + 0.5, color="#E7EAF0", linewidth=0.8)
        for x, text in enumerate(row[1:]):
            if x == 2 and "Not" in text:
                color = COLORS["none"]
            elif x == 2:
                color = COLORS["supported"]
            elif x == 1:
                color = COLORS["focused"]
            else:
                color = COLORS["supported"]
            ax.scatter(x, y, s=155, color=color, edgecolor="white", linewidth=1.2, zorder=2)
            ax.text(
                x + 0.11,
                y,
                text,
                va="center",
                ha="left",
                fontsize=8.8,
                color=COLORS["text"],
            )
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_title(
        "Fig. 1  QoS contribution and evidence scope",
        loc="left",
        fontsize=14,
        pad=26,
    )
    fig.text(
        0.5,
        -0.01,
        "The 22/22 hardware validation suite supports the focused implementation scope; "
        "it is not a claim of complete DDS QoS conformance.",
        ha="center",
        fontsize=9,
        color="#505860",
    )
    save_figure(fig, figure_dir, "fig01_qos_evidence_scope")

    write_csv(
        origin_dir / "qos_evidence_scope.csv",
        ["qos_policy", "implemented_configured", "hardware_evidence", "formal_experiment"],
        [
            {
                "qos_policy": row[0],
                "implemented_configured": row[1],
                "hardware_evidence": row[2],
                "formal_experiment": row[3],
            }
            for row in rows
        ],
    )


def build_round6_forest(repo_root: Path, figure_dir: Path) -> None:
    rows = read_csv(repo_root / R6 / "round6_complete_contrasts.csv")
    order = [
        "depth_10_minus_5",
        "depth_20_minus_5",
        "depth_40_minus_5",
        "heartbeat_250_minus_4000",
        "heartbeat_1000_minus_4000",
        "interaction_depth40_vs5_hb250_vs4000",
    ]
    labels = {
        "depth_10_minus_5": "Depth 10 - 5",
        "depth_20_minus_5": "Depth 20 - 5",
        "depth_40_minus_5": "Depth 40 - 5",
        "heartbeat_250_minus_4000": "Heartbeat 250 - 4000 ms",
        "heartbeat_1000_minus_4000": "Heartbeat 1000 - 4000 ms",
        "interaction_depth40_vs5_hb250_vs4000": "Depth x heartbeat interaction",
    }
    fig, axes = plt.subplots(1, 2, figsize=(10.0, 4.8), constrained_layout=True)
    outcomes = (
        ("delivery_ratio", "A  Delivery contrast", "Difference (percentage points)", 100.0),
        ("rtt_p95_ms", "B  RTT-tail contrast", "Difference in run RTT p95 (ms)", 1.0),
    )
    y = np.arange(len(order))
    for ax, (outcome, title, xlabel, scale) in zip(axes, outcomes):
        selected = {row["contrast"]: row for row in rows if row["outcome"] == outcome}
        for index, contrast in enumerate(order):
            row = selected[contrast]
            estimate = float(row["estimate"]) * scale
            low = float(row["ci_low"]) * scale
            high = float(row["ci_high"]) * scale
            significant = float(row["holm_p"] or 1.0) < 0.05
            color = COLORS["supported"] if significant else "#7D8792"
            ax.errorbar(
                estimate,
                index,
                xerr=[[estimate - low], [high - estimate]],
                fmt="o",
                color=color,
                markeredgecolor="white",
                markeredgewidth=0.8,
                markersize=7.0,
                capsize=3.0,
                linewidth=1.8,
            )
        ax.axvline(0, color=COLORS["text"], linewidth=0.9)
        ax.set_yticks(y, [labels[item] for item in order])
        ax.invert_yaxis()
        ax.set_title(title, loc="left")
        ax.set_xlabel(xlabel)
        ax.grid(axis="x", color=COLORS["grid"], linewidth=0.7)
    axes[1].tick_params(axis="y", labelleft=False)
    fig.suptitle(
        "Round 6: feedback timing changed outcomes; retained depth did not",
        fontsize=14,
        fontweight="bold",
    )
    fig.text(
        0.5,
        -0.02,
        "Green: Holm-adjusted p < 0.05 in the preregistered 24-test family. "
        "Points: estimate; bars: 95% run-bootstrap CI.",
        ha="center",
        fontsize=9,
        color="#505860",
    )
    save_figure(fig, figure_dir, "fig04_round6_confirmatory_contrasts")


def export_round4_origin_data(repo_root: Path, origin_dir: Path) -> None:
    all_rows = []
    for direction, analysis_dir in (("host_to_board", R4_H2B), ("board_to_host", R4_B2H)):
        rows = read_csv(repo_root / analysis_dir / "round4_transport_summary.csv")
        indexed = {(row["qos"], int(row["loss_pct"])): row for row in rows}
        for loss in LOSS_LEVELS:
            output = {"direction": direction, "loss_pct": loss}
            for qos, prefix in (("best_effort", "BE"), ("reliable", "REL")):
                row = indexed[(qos, loss)]
                mean = float(row["delivery_mean_pct"])
                low = float(row["delivery_mean_ci_low_pct"])
                high = float(row["delivery_mean_ci_high_pct"])
                output.update(
                    {
                        f"{prefix}_mean_pct": mean,
                        f"{prefix}_ci_low_pct": low,
                        f"{prefix}_ci_high_pct": high,
                        f"{prefix}_err_minus_pct": mean - low,
                        f"{prefix}_err_plus_pct": high - mean,
                    }
                )
            all_rows.append(output)
    fields = ["direction", "loss_pct"]
    for prefix in ("BE", "REL"):
        fields.extend(
            [
                f"{prefix}_mean_pct",
                f"{prefix}_ci_low_pct",
                f"{prefix}_ci_high_pct",
                f"{prefix}_err_minus_pct",
                f"{prefix}_err_plus_pct",
            ]
        )
    write_csv(origin_dir / "round4_delivery_origin.csv", fields, all_rows)

    rows = read_csv(repo_root / R4_B2H / "round4_rtt_message_summary.csv")
    indexed = {(row["qos"], int(row["loss_pct"])): row for row in rows}
    output_rows = []
    for loss in LOSS_LEVELS:
        output = {"loss_pct": loss}
        for qos, prefix in (("best_effort", "BE"), ("reliable", "REL")):
            row = indexed[(qos, loss)]
            mean = float(row["rtt_message_p95_ms"])
            low = float(row["rtt_message_p95_ci_low_ms"])
            high = float(row["rtt_message_p95_ci_high_ms"])
            output.update(
                {
                    f"{prefix}_p95_ms": mean,
                    f"{prefix}_ci_low_ms": low,
                    f"{prefix}_ci_high_ms": high,
                    f"{prefix}_err_minus_ms": mean - low,
                    f"{prefix}_err_plus_ms": high - mean,
                }
            )
        output_rows.append(output)
    fields = ["loss_pct"]
    for prefix in ("BE", "REL"):
        fields.extend(
            [
                f"{prefix}_p95_ms",
                f"{prefix}_ci_low_ms",
                f"{prefix}_ci_high_ms",
                f"{prefix}_err_minus_ms",
                f"{prefix}_err_plus_ms",
            ]
        )
    write_csv(origin_dir / "round4_b2h_message_p95_origin.csv", fields, output_rows)


def copy_authoritative_outputs(repo_root: Path, output_dir: Path) -> None:
    figure_dir = output_dir / "figures"
    shutil.copy2(
        repo_root / R6 / "round6_complete_outcomes.png",
        figure_dir / "fig03_round6_mechanism_outcomes.png",
    )
    shutil.copy2(
        repo_root / R6 / "round6_complete_outcomes.pdf",
        figure_dir / "fig03_round6_mechanism_outcomes.pdf",
    )
    origin_dir = output_dir / "origin_data"
    shutil.copy2(
        repo_root / R6 / "round6_complete_cell_summary.csv",
        origin_dir / "round6_complete_cell_summary.csv",
    )
    shutil.copy2(
        repo_root / R6 / "round6_complete_contrasts.csv",
        origin_dir / "round6_complete_contrasts.csv",
    )


def write_evidence_manifest(repo_root: Path, output_dir: Path) -> None:
    evidence = [
        {
            "id": "VALIDATION-22",
            "role": "Focused hardware QoS validation",
            "status": "22/22 PASS",
            "population": "22 assertions",
            "source": "docs/benchmark/REMEDIATION_ROUND3_EXECUTION.md",
            "artifact": "docs/qos/QOS_EVIDENCE_MATRIX.md",
            "claim_boundary": "Focused prototype behavior, not complete DDS conformance",
        },
        {
            "id": "ROUND4-H2B",
            "role": "QoS comparison under host-to-board loss",
            "status": "Formal",
            "population": "2 QoS x 5 loss x 30 = 300 runs",
            "source": str(R4_H2B.parent),
            "artifact": str(R4_H2B / "round4_transport_summary.csv"),
            "claim_boundary": "Run-level RTT; no broad Reliable delivery advantage",
        },
        {
            "id": "ROUND4-B2H",
            "role": "QoS comparison under board-to-host loss",
            "status": "Formal and audited",
            "population": "300 runs; 11,054 message RTT samples",
            "source": str(R4_B2H.parent),
            "artifact": str(R4_B2H / "round4_rtt_message_summary.csv"),
            "claim_boundary": "Single ESP32/AP/testbed; ingress capture is not delivery proof",
        },
        {
            "id": "ROUND6",
            "role": "History-depth x heartbeat mechanism intervention",
            "status": "Preregistered, complete, audited, sealed",
            "population": "4 depths x 3 heartbeats x 30 = 360 runs",
            "source": str(R6_ROOT),
            "artifact": str(R6 / "complete_analysis_manifest.json"),
            "claim_boundary": "Reliable only at nominal 15% B2H loss",
        },
        {
            "id": "P4",
            "role": "Independent time/network-window replication",
            "status": "Preregistered; collection not in this package",
            "population": "Planned: 2 QoS x 3 loss x 30 = 180 runs",
            "source": "docs/benchmark/P4_INDEPENDENT_WINDOW_PREREGISTRATION.md",
            "artifact": "docs/benchmark/P4_EXECUTION_RUNBOOK.md",
            "claim_boundary": "Do not present as completed until audit passes",
        },
        {
            "id": "EXTERNAL",
            "role": "micro-ROS and upstream mros2-esp32 baselines",
            "status": "Exploratory only",
            "population": "N=1 pilot per implementation",
            "source": "docs/benchmark/MICROROS_COMPARISON_PROTOCOL.md",
            "artifact": "docs/benchmark/MICROROS_COMPARISON_PROTOCOL.md",
            "claim_boundary": "No quantitative superiority claim",
        },
    ]
    for row in evidence:
        artifact = repo_root / row["artifact"]
        row["artifact_sha256"] = sha256_file(artifact) if artifact.is_file() else ""
    fields = [
        "id",
        "role",
        "status",
        "population",
        "source",
        "artifact",
        "artifact_sha256",
        "claim_boundary",
    ]
    write_csv(output_dir / "evidence_manifest.csv", fields, evidence)


def write_text_guides(output_dir: Path, pcap_name: str) -> None:
    readme = """mROS2-QoS 周五组会展示包（2026-07-17）

建议展示顺序（8-10 分钟）
1. fig01：先说明项目不是只做 Reliability。七类 QoS 都有实现/实机证据，但证据成熟度不同。
2. fig02：Round 4 的核心政策比较。强调方向不对称；Reliable 在当前 B2H 丢包下出现长尾，且没有测得交付率优势。
3. fig03：Round 6 的 4x3 机制干预。展示完整四结果图，不只挑显著结果。
4. fig04：展示预注册对比。心跳周期显著改变交付率与 RTT p95；History depth 和交互未获支持。
5. evidence_manifest.csv：说明 300 + 300 + 360 次正式运行、审计和证据边界。
6. 最后一页只讲下一步：P4 独立窗口重复，以及 micro-ROS/upstream 正式对比。

组会时可以说的核心结论
- 系统贡献：mROS2-ESP32 的结构化 QoS 配置和七类政策的分层实机证据。
- 经验发现：QoS 标签本身不足以预测应用结果，丢包方向会改变 Reliable/Best Effort 的表现。
- 机制发现：在本测试床名义 15% B2H 丢包下，反馈时序（heartbeat）比保留深度更能解释结果。
- 方法贡献：预注册、每格 N=30、随机化区组、bootstrap CI、Holm 校正、PCAP/日志/哈希审计。

不要说
- “所有 QoS 都完整支持”或“完全符合 DDS”。
- “Reliable 在丢包下总是更可靠”。
- “比 micro-ROS 快 25%”或任何外部实现优越性结论；当前外部基线只有 N=1 pilot。
- “358/360 证明应用收到修复包”；它是线级 same-sequence repair evidence。
- P4 已完成；只有审计 PASS 后才能加入结果页。

建议发给老师
- 00_README_GROUP_MEETING_CN.txt
- figures/ 中 fig01-fig04 的 PDF（看细节）和 PNG（放 PPT）
- evidence_manifest.csv
- origin_data/（老师若要复核或重画）
- wireshark/ 中的一份代表性 PCAP 和说明

不建议直接发送
- 641 MB 全量 results/ 目录
- smoke、failed、superseded、incomplete 目录
- 旧版 EXPERIMENT_DESIGN/QUICK_START 中的预期数字
- 360 份 PCAP 全集（老师明确索要时再给审计封存包）
"""
    (output_dir / "00_README_GROUP_MEETING_CN.txt").write_text(readme, encoding="utf-8")

    origin = """OriginPro 绘图步骤（组会版）

1. Data > Import From File > Single ASCII，导入 origin_data/*.csv。
2. Round 4 delivery：X=loss_pct；Y=BE_mean_pct/REL_mean_pct；使用对应 err_minus/err_plus 作为非对称 Y error。
3. Round 4 RTT p95：X=loss_pct；Y=BE_p95_ms/REL_p95_ms；Y 轴设为 Log10。
4. 颜色使用 #0072B2（Best Effort）与 #D55E00（Reliable）；同时使用圆/方标记，保证灰度可区分。
5. 图中文字建议 8-10 pt（论文双栏）或 18 pt 以上（组会 PPT）；不要用 3D、渐变、阴影或双 Y 轴。
6. 导出 PDF/EPS/SVG 矢量图；PNG 仅用于 PPT，至少 300 dpi。

注意：Origin 官网试用版导出会带 demo 水印。正式投稿图应使用学校许可证、合法学生版，或直接使用本包已生成的无水印 PDF/SVG。
"""
    (output_dir / "01_ORIGIN_RECIPE_CN.txt").write_text(origin, encoding="utf-8")

    display_filter = (
        "frame.time_relative >= 23 && "
        "rtps.sm.wrEntityId.entityKey == 1 && "
        "rtps.sm.wrEntityId.entityKind == 3 && "
        "rtps.sm.rdEntityId.entityKey == 18 && "
        "rtps.sm.rdEntityId.entityKind == 4 && "
        "(rtps.sm.id == 0x06 || rtps.sm.id == 0x07 || rtps.sm.id == 0x15)"
    )
    wireshark = f"""Wireshark 组会演示

文件：{pcap_name}
条件：Round 6, depth=5, heartbeat=4000 ms, nominal B2H loss=15%（configured 1/7 = 14.285714%）
代表性：run 29；delivery=0.8276；run RTT p95=3243.5 ms；6 个 requested unique sequences。
SHA-256：{REPRESENTATIVE_PCAP_SHA256}

显示过滤器（直接粘贴）：
{display_filter}

建议列：Time、Source、Destination、Protocol、Info，再增加 rtps.sm.seqNumber 和 rtps.bitmap。
只用于展示 DATA / HEARTBEAT / ACKNACK 的可观察顺序。不要把 ingress 抓到的 pre-NACK DATA 解释为 host application 已交付。
量化结论来自归档 PCAP 的 tshark 批处理和 360-run 分析，不依赖手工截图。
"""
    (output_dir / "wireshark" / "WIRESHARK_DEMO_CN.txt").write_text(
        wireshark, encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/group_meeting_20260717"),
    )
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    output_dir = args.output_dir
    if not output_dir.is_absolute():
        output_dir = repo_root / output_dir
    figure_dir = output_dir / "figures"
    origin_dir = output_dir / "origin_data"
    wireshark_dir = output_dir / "wireshark"
    figure_dir.mkdir(parents=True, exist_ok=True)
    origin_dir.mkdir(parents=True, exist_ok=True)
    wireshark_dir.mkdir(parents=True, exist_ok=True)

    setup_style()
    build_qos_scope_figure(figure_dir, origin_dir)
    build_round4_figure(repo_root, figure_dir)
    build_round6_forest(repo_root, figure_dir)
    export_round4_origin_data(repo_root, origin_dir)
    copy_authoritative_outputs(repo_root, output_dir)
    write_evidence_manifest(repo_root, output_dir)

    pcap_source = repo_root / REPRESENTATIVE_PCAP
    if sha256_file(pcap_source) != REPRESENTATIVE_PCAP_SHA256:
        raise ValueError("representative PCAP hash mismatch")
    pcap_dest = wireshark_dir / "round6_representative_d05_h4000_run29.pcapng"
    shutil.copy2(pcap_source, pcap_dest)
    write_text_guides(output_dir, pcap_dest.name)

    print(f"Built group-meeting package: {output_dir}")


if __name__ == "__main__":
    main()
