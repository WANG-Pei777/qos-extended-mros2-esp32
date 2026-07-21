"""Build native Origin figures for the completed H2B formal campaign.

Pandas and NumPy prepare auditable worksheet columns only. Every graph page and
every PNG/PDF export is created by OriginPro 2024b through the originpro API.
"""

from __future__ import annotations

import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd
import originpro as op

from build_native_origin_project import (
    BLACK,
    BLUE,
    GRAY,
    ORANGE,
    PURPLE,
    add_panel_label,
    dataframe_sheet,
    horizontal_interval_segments,
    pad_columns,
    remove_legend,
    set_layer_box,
    set_legend,
    set_page_size,
    style_layer,
    style_line_plot,
    style_raw_plot,
    style_summary_plot,
    vertical_interval_segments,
)


REPO = Path(__file__).resolve().parents[2]
WORKTREE = Path(
    os.environ.get(
        "MROS2_P4_WORKTREE",
        r"\\wsl.localhost\Ubuntu-22.04\home\wsde-47\mROS2-QoS\mROS2-QoS-p4-run",
    )
)
PACKAGE = Path(
    os.environ.get(
        "MROS2_H2B_ORIGIN_OUTPUT",
        str(REPO / "outputs" / "origin_h2b_formal_20260716"),
    )
)
DATA = PACKAGE / "origin_data"
EXPORTS = PACKAGE / "figures"
PROJECT = PACKAGE / "mROS2_H2B_Formal_Origin.opju"
MANIFEST = PACKAGE / "origin_project_manifest.json"

H2B_ROOT = (
    WORKTREE
    / "results"
    / "experiments"
    / "20260716_h2b_per_message_formal_restart2"
)
H2B_ANALYSIS = H2B_ROOT / "analysis" / "formal_8ca77cd"
P4_ROOT = WORKTREE / "results" / "experiments" / "20260715_p4_independent"
P4_ANALYSIS = P4_ROOT / "analysis" / "confirmatory_92e5218"

QOS_STYLES = {
    "best_effort": (BLUE, 2, -0.16),
    "reliable": (ORANGE, 1, 0.16),
}
LOSS_LEVELS = (0, 1, 5, 10, 15)
COMMON_LOSS = (0, 5, 15)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_inputs() -> dict[str, Path]:
    paths = {
        "h2b_runs": H2B_ANALYSIS / "h2b_run_outcomes.csv",
        "h2b_cells": H2B_ANALYSIS / "h2b_cell_summary.csv",
        "h2b_contrasts": H2B_ANALYSIS / "h2b_contrasts.csv",
        "h2b_audit": H2B_ROOT / "formal_audit_report.json",
        "h2b_seal": H2B_ROOT / "release_seal.json",
        "p4_contrasts": P4_ANALYSIS / "p4_contrasts.csv",
        "p4_audit": P4_ROOT / "analysis" / "formal_audit_report.json",
        "p4_seal": P4_ROOT / "release_seal.json",
    }
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise SystemExit(f"Missing required inputs: {missing}")
    return paths


def validate_evidence(inputs: dict[str, Path]) -> dict[str, object]:
    h2b_audit = json.loads(inputs["h2b_audit"].read_text(encoding="utf-8"))
    p4_audit = json.loads(inputs["p4_audit"].read_text(encoding="utf-8"))
    if h2b_audit.get("status") != "PASS" or h2b_audit.get("accepted_runs") != 300:
        raise SystemExit("H2B source is not the audited 300-run PASS result")
    if h2b_audit.get("rejected_runs") != 0:
        raise SystemExit("H2B source unexpectedly contains rejected runs")
    if p4_audit.get("status") != "PASS" or p4_audit.get("accepted_runs") != 180:
        raise SystemExit("P4 source is not the audited 180-run PASS result")
    return {"h2b_audit": h2b_audit, "p4_audit": p4_audit}


def deterministic_jitter(ids: Sequence[int], width: float, salt: int = 0) -> np.ndarray:
    values = np.asarray(ids, dtype=int)
    code = (values * 17 + salt * 11 + 7) % 37
    return ((code - 18) / 18.0) * width


def prepare_directional_effects(
    h2b_contrasts: pd.DataFrame, p4_contrasts: pd.DataFrame
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for direction, source in (("H2B", h2b_contrasts), ("B2H (P4)", p4_contrasts)):
        frame = source.loc[
            source["outcome"].isin(("delivery_ratio", "rtt_p95_ms"))
            & source["target_loss_percent"].isin(COMMON_LOSS)
        ]
        for row in frame.itertuples(index=False):
            scale = 100.0 if row.outcome == "delivery_ratio" else 1.0
            rows.append(
                {
                    "outcome": row.outcome,
                    "direction": direction,
                    "loss_percent": int(row.target_loss_percent),
                    "estimate": float(row.estimate) * scale,
                    "ci_low": float(row.ci_low) * scale,
                    "ci_high": float(row.ci_high) * scale,
                    "holm_p": float(row.holm_p),
                }
            )
    frame = pd.DataFrame(rows)
    position = {
        (15, "B2H (P4)"): 1,
        (15, "H2B"): 2,
        (5, "B2H (P4)"): 3,
        (5, "H2B"): 4,
        (0, "B2H (P4)"): 5,
        (0, "H2B"): 6,
    }
    frame["position"] = [
        position[(loss, direction)]
        for loss, direction in zip(frame["loss_percent"], frame["direction"])
    ]
    frame["label"] = frame.apply(
        lambda row: f"{int(row['loss_percent'])}% | {row['direction']}", axis=1
    )
    return frame.sort_values(["outcome", "position"]).reset_index(drop=True)


def prepare_data(inputs: dict[str, Path]) -> dict[str, pd.DataFrame]:
    frames = {
        "h2b_runs": pd.read_csv(inputs["h2b_runs"]),
        "h2b_cells": pd.read_csv(inputs["h2b_cells"]),
        "h2b_contrasts": pd.read_csv(inputs["h2b_contrasts"]),
        "p4_contrasts": pd.read_csv(inputs["p4_contrasts"]),
    }
    if len(frames["h2b_runs"]) != 300:
        raise SystemExit("H2B figure input must contain 300 accepted runs")
    cell_counts = frames["h2b_runs"].groupby(["qos", "target_loss_percent"]).size()
    if len(cell_counts) != 10 or not (cell_counts == 30).all():
        raise SystemExit(f"H2B cells must all contain N=30 runs: {cell_counts.to_dict()}")
    primary = frames["h2b_contrasts"].loc[
        frames["h2b_contrasts"]["outcome"].isin(("delivery_ratio", "rtt_p95_ms"))
    ]
    if len(primary) != 10 or not (primary["holm_family"] == "confirmatory_10").all():
        raise SystemExit("H2B primary contrast family is incomplete")
    frames["directional_effects"] = prepare_directional_effects(
        frames["h2b_contrasts"], frames["p4_contrasts"]
    )
    return frames


def save_origin_data(frames: dict[str, pd.DataFrame]) -> dict[str, Path]:
    DATA.mkdir(parents=True, exist_ok=True)
    names = {
        "h2b_runs": "h2b_run_outcomes.csv",
        "h2b_cells": "h2b_cell_summary.csv",
        "h2b_contrasts": "h2b_contrasts.csv",
        "directional_effects": "h2b_b2h_directional_effects.csv",
    }
    paths: dict[str, Path] = {}
    for key, filename in names.items():
        path = DATA / filename
        frames[key].to_csv(path, index=False)
        paths[key] = path
    return paths


def export_graph(page, stem: str, width: int) -> list[Path]:
    page.activate()
    targets = [EXPORTS / f"{stem}.png", EXPORTS / f"{stem}.pdf"]
    for target in targets:
        target.unlink(missing_ok=True)
    path = EXPORTS.as_posix()
    page.lt_exec(
        f'expGraph type:=png export:=page filename:="{stem}" '
        f'path:="{path}" overwrite:=replace tr.Margin:=1 '
        f'tr1.Unit:=2 tr1.Rescaling:=0 tr1.Width:={width} '
        'tr2.PNG.dotsperinch:=300 tr2.PNG.bitsperpixel:="24-bit Color";'
    )
    page.lt_exec("@EMRD=0;")
    page.lt_exec(
        f'expGraph type:=pdf export:=page filename:="{stem}" '
        f'path:="{path}" overwrite:=replace tr.Margin:=1 '
        'tr2.PDF.Fonts.Embed:=1 tr2.PDF.Fonts.TrueType:=1;'
    )
    missing = [str(target) for target in targets if not target.is_file()]
    if missing:
        raise RuntimeError(f"Origin failed to export: {missing}")
    return targets


def set_h2b_loss_ticks(layer) -> None:
    layer.activate()
    layer.lt_exec('layer.x.ticksbydata$="0 1 5 10 15";')


def add_h2b_metric_panel(
    layer,
    run_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    *,
    raw_column: str,
    outcome: str,
    short_name: str,
    ylabel: str,
    panel_title: str,
    ylim: tuple[float, float, float | None],
    scale: float = 1.0,
    yscale: str = "linear",
    title_x: float = 0.0,
) -> None:
    columns: dict[str, Sequence[object]] = {}
    specs: list[tuple[str, str, int]] = []
    for qos, prefix in (("best_effort", "BE"), ("reliable", "REL")):
        color, symbol, offset = QOS_STYLES[qos]
        raw = run_df.loc[run_df["qos"].eq(qos)].sort_values(
            ["target_loss_percent", "block", "accepted_ordinal"]
        )
        cells = summary_df.loc[
            summary_df["qos"].eq(qos) & summary_df["outcome"].eq(outcome)
        ].sort_values("target_loss_percent")
        xx = cells["target_loss_percent"].to_numpy(dtype=float) + offset
        low = cells["ci_low"].to_numpy(dtype=float) * scale
        high = cells["ci_high"].to_numpy(dtype=float) * scale
        vx, vy, cx, cy = vertical_interval_segments(xx, low, high, 0.11)
        columns.update(
            {
                f"{prefix}_ci_x": vx,
                f"{prefix}_ci_y": vy,
                f"{prefix}_cap_x": cx,
                f"{prefix}_cap_y": cy,
                f"{prefix}_raw_x": (
                    raw["target_loss_percent"].to_numpy(dtype=float)
                    + offset
                    + deterministic_jitter(
                        raw["accepted_ordinal"].to_numpy(dtype=int),
                        0.11,
                        1 if qos == "reliable" else 0,
                    )
                ),
                f"{prefix}_raw_y": raw[raw_column].to_numpy(dtype=float) * scale,
                f"{prefix}_mean_x": xx,
                f"{prefix}_mean_y": cells["mean"].to_numpy(dtype=float) * scale,
            }
        )
        specs.append((prefix, color, symbol))

    wks = dataframe_sheet(pad_columns(columns), short_name, f"{panel_title} plot data")
    for prefix, color, symbol in specs:
        plot = layer.add_plot(wks, f"{prefix}_ci_y", f"{prefix}_ci_x", type="l")
        style_line_plot(plot, color, 1.5)
        plot = layer.add_plot(wks, f"{prefix}_cap_y", f"{prefix}_cap_x", type="l")
        style_line_plot(plot, color, 1.5)
        plot = layer.add_plot(wks, f"{prefix}_raw_y", f"{prefix}_raw_x", type="s")
        style_raw_plot(plot, color, symbol, 5.8)
        plot.transparency = 28
        plot = layer.add_plot(wks, f"{prefix}_mean_y", f"{prefix}_mean_x", type="y")
        style_summary_plot(plot, color, symbol)

    style_layer(
        layer,
        "Nominal host-to-board loss target (%)",
        ylabel,
        (-0.55, 15.55, 5),
        ylim,
        yscale=yscale,
        xticks=LOSS_LEVELS,
    )
    set_h2b_loss_ticks(layer)
    title_y = ylim[1] * 0.84 if yscale == "log10" else ylim[1] - 0.04 * (ylim[1] - ylim[0])
    add_panel_label(layer, panel_title, title_x, title_y, 14)


def h2b_primary_graph(runs: pd.DataFrame, cells: pd.DataFrame):
    graph = op.new_graph(
        lname="H2B formal outcomes with all 300 independent runs", template="line"
    )
    graph.name = "H2BPrimary"
    set_page_size(graph, 10500, 5200)
    left, right = graph[0], graph.add_layer()
    set_layer_box(left, 9, 14, 39, 70)
    set_layer_box(right, 58, 14, 39, 70)
    add_h2b_metric_panel(
        left,
        runs,
        cells,
        raw_column="rtt_p95_ms",
        outcome="rtt_p95_ms",
        short_name="H2BRTTPlot",
        ylabel="Run-level RTT p95 (ms, log scale)",
        panel_title="A  RTT tail",
        ylim=(18, 2500, None),
        yscale="log10",
        title_x=0.6,
    )
    add_h2b_metric_panel(
        right,
        runs,
        cells,
        raw_column="delivery_ratio",
        outcome="delivery_ratio",
        short_name="H2BDelPlot",
        ylabel="Application delivery (%)",
        panel_title="B  Delivery",
        ylim=(78, 103.5, 5),
        scale=100.0,
        title_x=0.6,
    )
    set_legend(left, r"\l(3) Best Effort     \l(7) Reliable", 12, x=1.0, y=1450)
    remove_legend(right)
    return graph


def add_h2b_effect_forest(
    layer,
    contrasts: pd.DataFrame,
    *,
    outcome: str,
    short_name: str,
    xlabel: str,
    xlim: tuple[float, float, float],
    panel_title: str,
    scale: float,
    color: str,
) -> None:
    frame = contrasts.loc[contrasts["outcome"].eq(outcome)].copy()
    frame["position"] = frame["target_loss_percent"].map({15: 1, 10: 2, 5: 3, 1: 4, 0: 5})
    frame["label"] = frame["target_loss_percent"].map(lambda value: f"{int(value)}% loss")
    frame["estimate_plot"] = frame["estimate"].astype(float) * scale
    frame["ci_low_plot"] = frame["ci_low"].astype(float) * scale
    frame["ci_high_plot"] = frame["ci_high"].astype(float) * scale
    frame = frame.sort_values("position")
    lx, ly, cx, cy = horizontal_interval_segments(
        frame["position"], frame["ci_low_plot"], frame["ci_high_plot"], 0.11
    )
    wks = dataframe_sheet(
        pad_columns(
            {
                "position": frame["position"].to_numpy(),
                "label": frame["label"].to_numpy(),
                "line_x": lx,
                "line_y": ly,
                "cap_x": cx,
                "cap_y": cy,
                "point_x": frame["estimate_plot"].to_numpy(),
                "point_y": frame["position"].to_numpy(),
                "holm_p": frame["holm_p"].to_numpy(),
            }
        ),
        short_name,
        f"{panel_title} forest data",
    )
    plot = layer.add_plot(wks, "line_y", "line_x", type="l")
    style_line_plot(plot, color, 1.8)
    plot = layer.add_plot(wks, "cap_y", "cap_x", type="l")
    style_line_plot(plot, color, 1.8)
    plot = layer.add_plot(wks, "point_y", "point_x", type="s")
    plot.color = color
    plot.symbol_kind = 3
    plot.symbol_size = 10
    plot.symbol_interior = 1

    style_layer(layer, xlabel, "", xlim, (0.5, 5.5, 1))
    layer.activate()
    layer.lt_exec('layer.y.ticksbydata$="1 2 3 4 5";')
    book = wks.get_book()
    layer.lt_exec(f"range __h2blabel=[{book.name}]{wks.name}!col(label); axis -ps Y T __h2blabel;")
    zero = layer.add_line(0, 0.5, 0, 5.5)
    zero.color = GRAY
    zero.width = 1.2
    zero.type = 1
    add_panel_label(layer, panel_title, xlim[0] + 0.03 * (xlim[1] - xlim[0]), 5.33, 14)


def h2b_effect_graph(contrasts: pd.DataFrame):
    graph = op.new_graph(
        lname="H2B Reliable minus Best Effort confirmatory effects", template="line"
    )
    graph.name = "H2BEffects"
    set_page_size(graph, 11000, 5000)
    left, right = graph[0], graph.add_layer()
    set_layer_box(left, 19, 14, 33, 70)
    set_layer_box(right, 66, 14, 31, 70)
    add_h2b_effect_forest(
        left,
        contrasts,
        outcome="delivery_ratio",
        short_name="H2BDelEffect",
        xlabel="Reliable - Best Effort delivery (percentage points)",
        xlim=(-5, 5, 2),
        panel_title="A  Delivery effect",
        scale=100.0,
        color=BLUE,
    )
    add_h2b_effect_forest(
        right,
        contrasts,
        outcome="rtt_p95_ms",
        short_name="H2BRTTEffect",
        xlabel="Reliable - Best Effort RTT p95 (ms)",
        xlim=(-50, 180, 50),
        panel_title="B  Tail-latency effect",
        scale=1.0,
        color=PURPLE,
    )
    remove_legend(left)
    remove_legend(right)
    return graph


def add_direction_forest(
    layer,
    effects: pd.DataFrame,
    *,
    outcome: str,
    short_name: str,
    xlabel: str,
    xlim: tuple[float, float, float],
    panel_title: str,
) -> None:
    frame = effects.loc[effects["outcome"].eq(outcome)].sort_values("position").copy()
    columns: dict[str, Sequence[object]] = {
        "position": frame["position"].to_numpy(),
        "label": frame["label"].to_numpy(),
    }
    specs = (("H2B", "H2B", BLUE, 2), ("B2H (P4)", "B2H", ORANGE, 1))
    for direction, prefix, _color, _symbol in specs:
        subset = frame.loc[frame["direction"].eq(direction)].sort_values("position")
        lx, ly, cx, cy = horizontal_interval_segments(
            subset["position"], subset["ci_low"], subset["ci_high"], 0.10
        )
        columns.update(
            {
                f"{prefix}_line_x": lx,
                f"{prefix}_line_y": ly,
                f"{prefix}_cap_x": cx,
                f"{prefix}_cap_y": cy,
                f"{prefix}_point_x": subset["estimate"].to_numpy(),
                f"{prefix}_point_y": subset["position"].to_numpy(),
            }
        )
    wks = dataframe_sheet(pad_columns(columns), short_name, f"{panel_title} forest data")
    for _direction, prefix, color, symbol in specs:
        plot = layer.add_plot(wks, f"{prefix}_line_y", f"{prefix}_line_x", type="l")
        style_line_plot(plot, color, 1.8)
        plot = layer.add_plot(wks, f"{prefix}_cap_y", f"{prefix}_cap_x", type="l")
        style_line_plot(plot, color, 1.8)
        plot = layer.add_plot(wks, f"{prefix}_point_y", f"{prefix}_point_x", type="s")
        plot.color = color
        plot.symbol_kind = symbol
        plot.symbol_size = 10
        plot.symbol_interior = 1

    style_layer(layer, xlabel, "", xlim, (0.5, 6.5, 1))
    layer.activate()
    layer.lt_exec('layer.y.ticksbydata$="1 2 3 4 5 6";')
    book = wks.get_book()
    layer.lt_exec(f"range __dirlabels=[{book.name}]{wks.name}!col(label); axis -ps Y T __dirlabels;")
    zero = layer.add_line(0, 0.5, 0, 6.5)
    zero.color = GRAY
    zero.width = 1.2
    zero.type = 1
    add_panel_label(layer, panel_title, xlim[0] + 0.03 * (xlim[1] - xlim[0]), 6.30, 14)


def directional_effect_graph(effects: pd.DataFrame):
    graph = op.new_graph(
        lname="Direction-specific Reliability effects across independent campaigns",
        template="line",
    )
    graph.name = "DirectionalEffects"
    set_page_size(graph, 11600, 5400)
    left, right = graph[0], graph.add_layer()
    set_layer_box(left, 20, 14, 32, 70)
    set_layer_box(right, 67, 14, 30, 70)
    add_direction_forest(
        left,
        effects,
        outcome="delivery_ratio",
        short_name="DirDelEffect",
        xlabel="Reliable - Best Effort delivery (percentage points)",
        xlim=(-14, 6, 5),
        panel_title="A  Delivery effect",
    )
    add_direction_forest(
        right,
        effects,
        outcome="rtt_p95_ms",
        short_name="DirRTTEffect",
        xlabel="Reliable - Best Effort RTT p95 (ms)",
        xlim=(-700, 3900, 1000),
        panel_title="B  Tail-latency effect",
    )
    set_legend(left, r"\l(3) H2B formal     \l(6) B2H P4", 12, x=-12.5, y=0.72)
    remove_legend(right)
    return graph


def import_source_tables(frames: dict[str, pd.DataFrame]) -> None:
    specs = (
        ("H2BRuns", "H2B accepted run outcomes", "h2b_runs"),
        ("H2BCells", "H2B run-bootstrap cell summaries", "h2b_cells"),
        ("H2BContr", "H2B confirmatory and secondary contrasts", "h2b_contrasts"),
        ("DirEffects", "H2B and B2H direction-specific effects", "directional_effects"),
    )
    for short_name, long_name, key in specs:
        dataframe_sheet(frames[key], short_name, long_name)


def main() -> None:
    inputs = require_inputs()
    audits = validate_evidence(inputs)
    frames = prepare_data(inputs)
    output_data = save_origin_data(frames)
    EXPORTS.mkdir(parents=True, exist_ok=True)

    figure_notes = """Figure 1: Completed host-to-board formal campaign, 300 accepted independent runs (N=30 per QoS x nominal-loss cell). Faint symbols are independent runs; large symbols are cell means; intervals are 10,000-draw run-level bootstrap 95% CIs. RTT uses a log10 axis.

Figure 2: Ten prespecified Reliable-minus-Best-Effort H2B contrasts. Intervals are run-level bootstrap 95% CIs. None of the five delivery or five run-level RTT-p95 contrasts survives Holm correction; all Holm-adjusted p values equal 1.0.

Figure 3: Descriptive comparison of direction-specific effects at common 0%, 5%, and 15% conditions. H2B uses the completed 300-run campaign; B2H uses the independent 180-run P4 campaign. This is not a randomized between-direction contrast and must not be described as one.

Application RTT comes from application logs, not Wireshark. Nominal injected loss is a configured target, not measured packet loss.
"""

    exported: list[Path] = []
    origin_version = None
    reopen_verification = None
    try:
        op.set_show(True)
        op.new(asksave=False)
        op.lt_exec("@GEFD=0;")
        import_source_tables(frames)
        figures = (
            (h2b_primary_graph(frames["h2b_runs"], frames["h2b_cells"]), "H2B_formal_outcomes", 2500),
            (h2b_effect_graph(frames["h2b_contrasts"]), "H2B_confirmatory_effects", 2600),
            (directional_effect_graph(frames["directional_effects"]), "Direction_specific_reliability_effects", 2700),
        )
        for page, stem, width in figures:
            exported.extend(export_graph(page, stem, width))

        notes = op.new_notes("Figure Notes")
        notes.text = figure_notes
        provenance = op.new_notes("Analysis Provenance")
        provenance.text = json.dumps(
            {
                "classification": "h2b_formal_origin_project",
                "h2b_audit_status": audits["h2b_audit"]["status"],
                "h2b_accepted_runs": audits["h2b_audit"]["accepted_runs"],
                "h2b_rejected_runs": audits["h2b_audit"]["rejected_runs"],
                "p4_audit_status": audits["p4_audit"]["status"],
                "p4_accepted_runs": audits["p4_audit"]["accepted_runs"],
                "input_sha256": {name: sha256_file(path) for name, path in inputs.items()},
                "origin_data_sha256": {name: sha256_file(path) for name, path in output_data.items()},
            },
            indent=2,
            sort_keys=True,
        )
        blank = op.find_book("w", "Book1")
        if blank is not None:
            blank.destroy()
        origin_version = op.org_ver()
        if not op.save(str(PROJECT)):
            raise RuntimeError(f"Origin failed to save {PROJECT}")

        op.new(asksave=False)
        opened = bool(op.open(str(PROJECT)))
        graphs = [(page.name, page.lname) for page in op.pages("g")]
        expected = {"H2BPrimary", "H2BEffects", "DirectionalEffects"}
        found = {name for name, _lname in graphs}
        note_counts = {}
        for name in ("Figure Notes", "Analysis Provenance"):
            note = op.find_notes(name)
            note_counts[name] = len(note.text) if note else 0
        reopen_verification = {
            "opened": opened,
            "graph_pages": graphs,
            "notes_character_counts": note_counts,
            "status": "PASS" if opened and expected.issubset(found) and all(note_counts.values()) else "FAIL",
        }
        if reopen_verification["status"] != "PASS":
            raise RuntimeError(f"Origin reopen verification failed: {reopen_verification}")
    finally:
        op.exit()

    manifest = {
        "schema_version": 1,
        "classification": "h2b_formal_origin_project_manifest",
        "status": "COMPLETE",
        "origin_application_version": origin_version,
        "originpro_python_version": version("originpro"),
        "project": str(PROJECT),
        "project_sha256": sha256_file(PROJECT),
        "exports": {path.name: sha256_file(path) for path in exported},
        "source_files": {name: str(path) for name, path in inputs.items()},
        "source_sha256": {name: sha256_file(path) for name, path in inputs.items()},
        "origin_data": {name: str(path) for name, path in output_data.items()},
        "origin_data_sha256": {name: sha256_file(path) for name, path in output_data.items()},
        "evidence_boundary": {
            "h2b": "formal 300-run campaign; N=30 per QoS x nominal-loss cell",
            "b2h": "formal P4 180-run campaign used only for descriptive direction comparison",
            "direction_comparison": "not a randomized between-direction contrast",
            "rtt_source": "application logs, not Wireshark",
        },
        "reopen_verification": reopen_verification,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
