"""Build the editable group-meeting figures with the Origin graph engine.

This module does not use a Python plotting library. Pandas is used only to
prepare worksheet columns; every graph page and every exported file is created
by a running, licensed Origin instance through OriginLab's originpro API.
"""

from __future__ import annotations

import os
from pathlib import Path
import time
from typing import Iterable, Sequence

import numpy as np
import pandas as pd
import originpro as op


REPO = Path(__file__).resolve().parents[2]
PACKAGE = REPO / "outputs" / "group_meeting_20260717"
DATA = PACKAGE / "origin_data"
EXPORTS = PACKAGE / "origin_exports"
PROJECT = PACKAGE / "mROS2_QoS_Group_Meeting_Origin.opju"
EXPORTS = Path(os.environ.get("MROS2_ORIGIN_EXPORTS", str(EXPORTS)))
PROJECT = Path(os.environ.get("MROS2_ORIGIN_PROJECT", str(PROJECT)))

BLUE = "#0072B2"
ORANGE = "#D55E00"
GREEN = "#009E73"
PURPLE = "#7B3294"
GRAY = "#6B7280"
LIGHT_GRAY = "#B8BEC7"
BLACK = "#111111"
FONT = "Arial"


def dataframe_sheet(df: pd.DataFrame, short_name: str, long_name: str):
    """Create one Origin workbook containing a dataframe."""
    wks = None
    for _attempt in range(4):
        wks = op.new_sheet("w", lname=long_name)
        if wks is not None:
            break
        time.sleep(2)
    if wks is None:
        raise RuntimeError(f"Origin failed to create workbook {short_name}")
    book = wks.get_book()
    book.name = short_name
    book.lname = long_name
    wks.from_df(df)
    wks.header_rows("l")
    return wks


def import_source_tables() -> dict[str, object]:
    specs = {
        "QoSScope": ("qos_evidence_scope.csv", "QoS evidence scope"),
        "R4DeliverySummary": (
            "round4_delivery_origin.csv",
            "Round 4 delivery summary and confidence intervals",
        ),
        "R4DeliveryRuns": (
            "round4_run_level_delivery_origin.csv",
            "Round 4 all 600 run-level delivery observations",
        ),
        "R4RTTRuns": (
            "round4_b2h_run_level_rtt_origin.csv",
            "Round 4 B2H all 300 run-level RTT summaries",
        ),
        "R4MessageP95": (
            "round4_b2h_message_p95_origin.csv",
            "Round 4 B2H per-message RTT p95 summaries",
        ),
        "R4P95Effect": (
            "round4_b2h_p95_effect_origin.csv",
            "Round 4 B2H Reliable minus Best Effort p95 effects",
        ),
        "R6Runs": (
            "round6_run_level_origin.csv",
            "Round 6 all 360 accepted run-level outcomes",
        ),
        "R6Cells": (
            "round6_complete_cell_summary.csv",
            "Round 6 complete cell summaries",
        ),
        "R6Contrasts": (
            "round6_complete_contrasts.csv",
            "Round 6 complete prespecified contrasts",
        ),
    }
    sheets = {}
    for short_name, (filename, long_name) in specs.items():
        sheets[short_name] = dataframe_sheet(
            pd.read_csv(DATA / filename), short_name, long_name
        )
    return sheets


def pad_columns(columns: dict[str, Sequence[object]]) -> pd.DataFrame:
    return pd.concat(
        {name: pd.Series(values) for name, values in columns.items()}, axis=1
    )


def vertical_interval_segments(
    x: Iterable[float], low: Iterable[float], high: Iterable[float], cap: float
) -> tuple[list[float], list[float], list[float], list[float]]:
    line_x: list[float] = []
    line_y: list[float] = []
    cap_x: list[float] = []
    cap_y: list[float] = []
    for xx, lo, hi in zip(x, low, high):
        line_x.extend([xx, xx, np.nan])
        line_y.extend([lo, hi, np.nan])
        cap_x.extend([xx - cap, xx + cap, np.nan, xx - cap, xx + cap, np.nan])
        cap_y.extend([lo, lo, np.nan, hi, hi, np.nan])
    return line_x, line_y, cap_x, cap_y


def horizontal_interval_segments(
    y: Iterable[float], low: Iterable[float], high: Iterable[float], cap: float
) -> tuple[list[float], list[float], list[float], list[float]]:
    line_x: list[float] = []
    line_y: list[float] = []
    cap_x: list[float] = []
    cap_y: list[float] = []
    for yy, lo, hi in zip(y, low, high):
        line_x.extend([lo, hi, np.nan])
        line_y.extend([yy, yy, np.nan])
        cap_x.extend([lo, lo, np.nan, hi, hi, np.nan])
        cap_y.extend([yy - cap, yy + cap, np.nan, yy - cap, yy + cap, np.nan])
    return line_x, line_y, cap_x, cap_y


def set_page_size(page, width: int = 9000, height: int = 4800) -> None:
    page.activate()
    page.lt_exec(
        "page.autoSize=0; "
        f"page.width={width}; page.height={height}; "
        "page.baseColor=color(white); page.revcolor=0; page.cntrl=16;"
    )


def set_layer_box(layer, left: float, top: float, width: float, height: float) -> None:
    layer.set_float("left", left)
    layer.set_float("top", top)
    layer.set_float("width", width)
    layer.set_float("height", height)


def style_axis_label(layer, name: str, size: float = 20) -> None:
    label = layer.label(name)
    if label:
        label.set_float("fsize", size)
        label.lt_exec(f"font=font({FONT});")
        label.color = BLACK


def style_layer(
    layer,
    xlabel: str,
    ylabel: str,
    xlim: tuple[float, float, float | None],
    ylim: tuple[float, float, float | None],
    xscale: str = "linear",
    yscale: str = "linear",
    xticks: Sequence[float] | None = None,
) -> None:
    layer.axis("x").title = xlabel
    layer.axis("y").title = ylabel
    layer.axis("x").scale = xscale
    layer.axis("y").scale = yscale
    layer.set_xlim(*xlim)
    layer.set_ylim(*ylim)
    layer.set_float("x.label.fsize", 14)
    layer.set_float("y.label.fsize", 14)
    layer.set_float("x.tickthickness", 1.4)
    layer.set_float("y.tickthickness", 1.4)
    style_axis_label(layer, "xb", 16)
    style_axis_label(layer, "yl", 16)
    layer.activate()
    layer.lt_exec(
        "layer.color=color(white); "
        "layer.x.color=color(black); layer.y.color=color(black); "
        "layer.x.label.color=color(black); layer.y.label.color=color(black); "
        f"layer.x.label.font=font({FONT}); layer.y.label.font=font({FONT}); "
        "axis -ps X M 1; axis -ps Y M 1;"
    )
    if xticks:
        tick_string = " ".join(f"{value:g}" for value in xticks)
        layer.lt_exec(f'layer.x.ticksbydata$="{tick_string}";')


def style_line_plot(plot, color: str, width: float = 1.5) -> None:
    plot.color = color
    plot.set_float("line.width", width)


def style_raw_plot(plot, color: str, symbol: int, size: float = 5.4) -> None:
    plot.color = color
    plot.symbol_kind = symbol
    plot.symbol_size = size
    plot.symbol_interior = 1
    plot.transparency = 35


def style_summary_plot(plot, color: str, symbol: int) -> None:
    plot.color = color
    plot.symbol_kind = symbol
    plot.symbol_size = 10
    plot.symbol_interior = 1
    plot.set_float("line.width", 2.2)


def add_panel_label(layer, text: str, x: float, y: float, size: float = 19) -> None:
    label = layer.add_label(text, x, y)
    label.set_int("attach", 2)
    label.set_float("x1", x)
    label.set_float("y1", y)
    label.set_float("fsize", size)
    label.set_int("fontbold", 1)
    label.lt_exec(f"font=font({FONT});")
    label.color = BLACK


def set_legend(
    layer, text: str, size: float = 14, x: float | None = None, y: float | None = None
) -> None:
    layer.activate()
    layer.lt_exec("legend -s 1;")
    legend = layer.label("legend")
    if legend:
        legend.text = text
        legend.set_float("fsize", size)
        legend.lt_exec(f"font=font({FONT});")
        legend.set_int("showframe", 0)
        legend.set_int("attach", 0)
        if x is not None:
            legend.set_int("attach", 2)
            legend.set_float("x1", x)
        if y is not None:
            legend.set_float("y1", y)
        legend.color = BLACK
        layer.lt_exec("legend -ah; legend.showframe=0;")


def remove_legend(layer) -> None:
    legend = layer.label("legend")
    if legend:
        legend.remove()


def export_graph(page, stem: str, width: int = 2000) -> list[str]:
    page.activate()
    export_path = EXPORTS.as_posix()
    targets = [EXPORTS / f"{stem}.png", EXPORTS / f"{stem}.pdf"]
    for target in targets:
        target.unlink(missing_ok=True)

    page.lt_exec(
        f'expGraph type:=png export:=page filename:="{stem}" '
        f'path:="{export_path}" overwrite:=replace tr.Margin:=1 '
        f'tr1.Unit:=2 tr1.Rescaling:=0 tr1.Width:={width} '
        'tr2.PNG.dotsperinch:=300 tr2.PNG.bitsperpixel:="24-bit Color";'
    )
    # Origin defaults to descriptor-only fonts. Embed the TrueType font so the
    # submission PDF renders identically on systems without local Arial.
    page.lt_exec('@EMRD=0;')
    page.lt_exec(
        f'expGraph type:=pdf export:=page filename:="{stem}" '
        f'path:="{export_path}" overwrite:=replace tr.Margin:=1 '
        'tr2.PDF.Fonts.Embed:=1 tr2.PDF.Fonts.TrueType:=1;'
    )
    missing = [str(target) for target in targets if not target.exists()]
    if missing:
        raise RuntimeError(f"Origin failed to export: {missing}")
    return [str(target) for target in targets]


def round4_delivery_graph(run_df: pd.DataFrame, summary_df: pd.DataFrame):
    graph = op.new_graph(
        lname="Round 4 delivery: all 600 runs and run-cluster 95% CIs",
        template="line",
    )
    graph.name = "Fig1R4Delivery"
    set_page_size(graph, 9000, 4800)
    first_layer = graph[0]
    second_layer = graph.add_layer()
    set_layer_box(first_layer, 10, 14, 36, 70)
    set_layer_box(second_layer, 59, 14, 36, 70)

    for panel, direction, title in (
        (first_layer, "host_to_board", "A  Host-to-board"),
        (second_layer, "board_to_host", "B  Board-to-host"),
    ):
        raw = run_df.loc[run_df["direction"] == direction]
        summary = summary_df.loc[summary_df["direction"] == direction].copy()
        columns: dict[str, Sequence[object]] = {}
        plot_specs = []
        for prefix, qos, color, symbol in (
            ("BE", "best_effort", BLUE, 2),
            ("REL", "reliable", ORANGE, 1),
        ):
            raw_q = raw.loc[raw["qos_mode"] == qos]
            mean = summary[f"{prefix}_mean_pct"].to_numpy()
            low = summary[f"{prefix}_ci_low_pct"].to_numpy()
            high = summary[f"{prefix}_ci_high_pct"].to_numpy()
            xx = summary["loss_pct"].to_numpy(dtype=float)
            vx, vy, cx, cy = vertical_interval_segments(xx, low, high, 0.11)
            columns.update(
                {
                    f"{prefix}_ci_x": vx,
                    f"{prefix}_ci_y": vy,
                    f"{prefix}_cap_x": cx,
                    f"{prefix}_cap_y": cy,
                    f"{prefix}_raw_x": (
                        raw_q["loss_pct"].to_numpy(dtype=float)
                        + (-0.20 if qos == "best_effort" else 0.20)
                        + ((((raw_q["run_id"].to_numpy(dtype=int) * 17) % 31) - 15) / 15)
                        * 0.16
                    ),
                    f"{prefix}_raw_y": raw_q["delivery_pct"].to_numpy(),
                    f"{prefix}_mean_x": xx,
                    f"{prefix}_mean_y": mean,
                }
            )
            plot_specs.append((prefix, color, symbol))
        wks = dataframe_sheet(
            pad_columns(columns),
            f"R4Del{'H2B' if direction == 'host_to_board' else 'B2H'}",
            f"Round 4 {direction} native Origin plot data",
        )
        for prefix, color, _ in plot_specs:
            p = panel.add_plot(wks, f"{prefix}_ci_y", f"{prefix}_ci_x", type="l")
            style_line_plot(p, color, 1.3)
            p = panel.add_plot(
                wks, f"{prefix}_cap_y", f"{prefix}_cap_x", type="l"
            )
            style_line_plot(p, color, 1.3)
        for prefix, color, symbol in plot_specs:
            p = panel.add_plot(
                wks, f"{prefix}_raw_y", f"{prefix}_raw_x", type="s"
            )
            style_raw_plot(p, color, symbol)
        for prefix, color, symbol in plot_specs:
            p = panel.add_plot(
                wks, f"{prefix}_mean_y", f"{prefix}_mean_x", type="y"
            )
            style_summary_plot(p, color, symbol)
        style_layer(
            panel,
            "Nominal injected loss (%)",
            "Delivery (%)",
            (-0.45, 15.45, 5),
            (40, 105, 10),
            xticks=(0, 1, 5, 10, 15),
        )
        add_panel_label(panel, title, 0.0, 103.1, 14)
    set_legend(
        first_layer,
        r"\l(7) Best Effort     \l(8) Reliable",
        x=5.3,
        y=103.0,
    )
    remove_legend(second_layer)
    return graph


def round4_rtt_distribution_graph(run_df: pd.DataFrame):
    graph = op.new_graph(
        lname="Round 4 B2H run-level RTT p95 distributions", template="line"
    )
    graph.name = "Fig2R4RTTRuns"
    set_page_size(graph, 7600, 5200)
    layer = graph[0]
    set_layer_box(layer, 15, 11, 77, 76)
    columns: dict[str, Sequence[object]] = {}
    specs = []
    for prefix, qos, color, symbol, offset in (
        ("BE", "best_effort", BLUE, 2, -0.13),
        ("REL", "reliable", ORANGE, 1, 0.13),
    ):
        raw = run_df.loc[run_df["qos_mode"] == qos]
        grouped = (
            raw.groupby("loss_pct")["run_rtt_p95_ms"]
            .agg(
                median="median",
                q25=lambda x: x.quantile(0.25),
                q75=lambda x: x.quantile(0.75),
            )
            .reset_index()
        )
        xx = grouped["loss_pct"].to_numpy(dtype=float) + offset
        vx, vy, cx, cy = vertical_interval_segments(
            xx, grouped["q25"], grouped["q75"], 0.11
        )
        columns.update(
            {
                f"{prefix}_iqr_x": vx,
                f"{prefix}_iqr_y": vy,
                f"{prefix}_cap_x": cx,
                f"{prefix}_cap_y": cy,
                f"{prefix}_raw_x": (
                    raw["loss_pct"].to_numpy(dtype=float)
                    + offset * (0.20 / 0.13)
                    + ((((raw["run_id"].to_numpy(dtype=int) * 17) % 31) - 15) / 15)
                    * 0.16
                ),
                f"{prefix}_raw_y": raw["run_rtt_p95_ms"].to_numpy(),
                f"{prefix}_median_x": xx,
                f"{prefix}_median_y": grouped["median"].to_numpy(),
            }
        )
        specs.append((prefix, color, symbol))
    wks = dataframe_sheet(
        pad_columns(columns), "R4RTTPlot", "Round 4 RTT distribution plot data"
    )
    for prefix, color, _ in specs:
        p = layer.add_plot(wks, f"{prefix}_iqr_y", f"{prefix}_iqr_x", type="l")
        style_line_plot(p, color, 3.0)
        p = layer.add_plot(wks, f"{prefix}_cap_y", f"{prefix}_cap_x", type="l")
        style_line_plot(p, color, 1.5)
    for prefix, color, symbol in specs:
        p = layer.add_plot(wks, f"{prefix}_raw_y", f"{prefix}_raw_x", type="s")
        style_raw_plot(p, color, symbol)
        p.transparency = 35
    for prefix, color, symbol in specs:
        p = layer.add_plot(
            wks, f"{prefix}_median_y", f"{prefix}_median_x", type="y"
        )
        style_summary_plot(p, color, symbol)
    style_layer(
        layer,
        "Nominal B2H loss (%)",
        "Run-level RTT p95 (ms, log scale)",
        (-0.45, 15.45, 5),
        (10, 10000, None),
        yscale="log10",
        xticks=(0, 1, 5, 10, 15),
    )
    set_legend(
        layer,
        r"\l(7) Best Effort     \l(8) Reliable",
        x=0.6,
        y=8200,
    )
    return graph


def round4_effect_graph(effect_df: pd.DataFrame):
    graph = op.new_graph(
        lname="Round 4 B2H RTT p95 effect sizes", template="line"
    )
    graph.name = "Fig3R4P95Effect"
    set_page_size(graph, 7000, 4800)
    layer = graph[0]
    set_layer_box(layer, 15, 11, 77, 76)
    x = effect_df["loss_pct"].to_numpy(dtype=float)
    vx, vy, cx, cy = vertical_interval_segments(
        x, effect_df["ci_low_ms"], effect_df["ci_high_ms"], 0.13
    )
    columns = {
        "ci_x": vx,
        "ci_y": vy,
        "cap_x": cx,
        "cap_y": cy,
        "point_x": x,
        "point_y": effect_df["estimate_ms"].to_numpy(),
    }
    wks = dataframe_sheet(
        pad_columns(columns), "R4EffectPlot", "Round 4 p95 effect plot data"
    )
    p = layer.add_plot(wks, "ci_y", "ci_x", type="l")
    style_line_plot(p, BLUE, 1.7)
    p = layer.add_plot(wks, "cap_y", "cap_x", type="l")
    style_line_plot(p, BLUE, 1.7)
    p = layer.add_plot(wks, "point_y", "point_x", type="s")
    p.color = BLUE
    p.symbol_kind = 3
    p.symbol_size = 11
    p.symbol_interior = 1
    style_layer(
        layer,
        "Nominal B2H loss (%)",
        "RTT p95 effect: Reliable - Best Effort (ms)",
        (-0.45, 15.45, 5),
        (-500, 5500, 1000),
        xticks=(0, 1, 5, 10, 15),
    )
    zero = layer.add_line(-0.45, 0, 15.45, 0)
    zero.color = GRAY
    zero.width = 1.2
    zero.type = 1
    remove_legend(layer)
    return graph


def round6_all_cells_graph(run_df: pd.DataFrame, cell_df: pd.DataFrame):
    graph = op.new_graph(
        lname="Round 6 all 360 accepted runs across 12 cells", template="line"
    )
    graph.name = "Fig4R6AllCells"
    set_page_size(graph, 9000, 4800)
    first_layer = graph[0]
    second_layer = graph.add_layer()
    set_layer_box(first_layer, 10, 14, 36, 70)
    set_layer_box(second_layer, 59, 14, 36, 70)

    panel_specs = (
        (
            first_layer,
            "delivery_pct",
            "delivery_ratio",
            100.0,
            "Delivery (%)",
            (15, 110, 20),
            "A  Application delivery",
            "linear",
        ),
        (
            second_layer,
            "rtt_p95_ms",
            "rtt_p95_ms",
            1.0,
            "Run-level RTT p95 (ms, log scale)",
            (20, 10000, None),
            "B  Application RTT tail",
            "log10",
        ),
    )
    hb_specs = (
        (250, "H0250", GREEN, 2, -0.075),
        (1000, "H1000", BLUE, 1, 0.0),
        (4000, "H4000", ORANGE, 3, 0.075),
    )
    for layer, run_col, outcome, scale, ylabel, ylim, title, yscale in panel_specs:
        summary = cell_df.loc[cell_df["outcome"] == outcome].copy()
        columns: dict[str, Sequence[object]] = {}
        for hb, prefix, color, symbol, log_offset in hb_specs:
            raw = run_df.loc[run_df["heartbeat_ms"] == hb]
            cells = summary.loc[summary["heartbeat_ms"] == hb].sort_values("depth")
            xx = cells["depth"].to_numpy(dtype=float) * np.exp(log_offset)
            mean = cells["mean"].to_numpy(dtype=float) * scale
            low = cells["ci_low"].to_numpy(dtype=float) * scale
            high = cells["ci_high"].to_numpy(dtype=float) * scale
            cap = xx * 0.018
            vx: list[float] = []
            vy: list[float] = []
            cx: list[float] = []
            cy: list[float] = []
            for xxx, lo, hi, cc in zip(xx, low, high, cap):
                one = vertical_interval_segments([xxx], [lo], [hi], float(cc))
                vx.extend(one[0]); vy.extend(one[1]); cx.extend(one[2]); cy.extend(one[3])
            columns.update(
                {
                    f"{prefix}_ci_x": vx,
                    f"{prefix}_ci_y": vy,
                    f"{prefix}_cap_x": cx,
                    f"{prefix}_cap_y": cy,
                    f"{prefix}_raw_x": raw["x_plot"].to_numpy(),
                    f"{prefix}_raw_y": raw[run_col].to_numpy(dtype=float)
                    * (100.0 if run_col == "delivery_ratio" else 1.0),
                    f"{prefix}_mean_x": xx,
                    f"{prefix}_mean_y": mean,
                }
            )
        wks = dataframe_sheet(
            pad_columns(columns),
            "R6DelPlot" if outcome == "delivery_ratio" else "R6RTTPlot",
            f"Round 6 {outcome} native Origin plot data",
        )
        for _, prefix, color, _, _ in hb_specs:
            p = layer.add_plot(wks, f"{prefix}_ci_y", f"{prefix}_ci_x", type="l")
            style_line_plot(p, color, 1.3)
            p = layer.add_plot(wks, f"{prefix}_cap_y", f"{prefix}_cap_x", type="l")
            style_line_plot(p, color, 1.3)
            p = layer.add_plot(wks, f"{prefix}_raw_y", f"{prefix}_raw_x", type="s")
            style_raw_plot(
                p,
                color,
                hb_specs[[v[1] for v in hb_specs].index(prefix)][3],
                5.0,
            )
            p.transparency = 40
            p = layer.add_plot(wks, f"{prefix}_mean_y", f"{prefix}_mean_x", type="y")
            style_summary_plot(
                p, color, hb_specs[[v[1] for v in hb_specs].index(prefix)][3]
            )
        style_layer(
            layer,
            "History depth (log2 scale)",
            ylabel,
            (4.2, 44.5, None),
            ylim,
            xscale="log2",
            yscale=yscale,
            xticks=(5, 10, 20, 40),
        )
        title_y = 7600 if yscale == "log10" else ylim[1] * 0.975
        add_panel_label(layer, title[0], 5.0, title_y, 16)
    set_legend(
        first_layer,
        r"\l(4) HB 250 ms    \l(8) HB 1000 ms    \l(12) HB 4000 ms",
        13,
        x=8,
        y=108,
    )
    remove_legend(second_layer)
    return graph


def effect_plot_data(df: pd.DataFrame, outcome: str, scale: float) -> pd.DataFrame:
    labels = {
        "depth_10_minus_5": "Depth 10 - 5",
        "depth_20_minus_5": "Depth 20 - 5",
        "depth_40_minus_5": "Depth 40 - 5",
        "heartbeat_250_minus_4000": "HB 250 - 4000",
        "heartbeat_1000_minus_4000": "HB 1000 - 4000",
        "interaction_depth40_vs5_hb250_vs4000": "Depth-HB int.",
    }
    order = list(labels)
    out = df.loc[df["outcome"] == outcome].set_index("contrast").loc[order].reset_index()
    out["label"] = out["contrast"].map(labels)
    out["position"] = np.arange(1, len(out) + 1)
    for col in ("estimate", "ci_low", "ci_high"):
        out[col] = out[col].astype(float) * scale
    out["supported"] = out["holm_p"].astype(float) < 0.05
    return out


def add_horizontal_forest(layer, data: pd.DataFrame, short_name: str, color: str):
    lx, ly, cx, cy = horizontal_interval_segments(
        data["position"], data["ci_low"], data["ci_high"], 0.11
    )
    columns = {
        "position": data["position"].to_numpy(),
        "label": data["label"].to_numpy(),
        "line_x": lx,
        "line_y": ly,
        "cap_x": cx,
        "cap_y": cy,
        "all_x": data["estimate"].to_numpy(),
        "all_y": data["position"].to_numpy(),
        "sig_x": data.loc[data["supported"], "estimate"].to_numpy(),
        "sig_y": data.loc[data["supported"], "position"].to_numpy(),
    }
    wks = dataframe_sheet(
        pad_columns(columns), short_name, f"{short_name} forest plot data"
    )
    p = layer.add_plot(wks, "line_y", "line_x", type="l")
    style_line_plot(p, color, 1.7)
    p = layer.add_plot(wks, "cap_y", "cap_x", type="l")
    style_line_plot(p, color, 1.7)
    p = layer.add_plot(wks, "all_y", "all_x", type="s")
    p.color = GRAY
    p.symbol_kind = 2
    p.symbol_size = 10
    p.symbol_interior = 2
    p = layer.add_plot(wks, "sig_y", "sig_x", type="s")
    p.color = color
    p.symbol_kind = 5
    p.symbol_size = 11
    p.symbol_interior = 1
    layer.activate()
    layer.lt_exec('layer.y.ticksbydata$="1 2 3 4 5 6";')
    book = wks.get_book()
    layer.lt_exec(
        f"range __ticklabels=[{book.name}]{wks.name}!col(label); "
        "axis -ps Y T __ticklabels;"
    )
    return wks


def round6_effect_graph(contrast_df: pd.DataFrame):
    graph = op.new_graph(
        lname="Round 6 complete application-outcome contrasts", template="line"
    )
    graph.name = "Fig5R6Effects"
    set_page_size(graph, 10000, 5200)
    first_layer = graph[0]
    second_layer = graph.add_layer()
    set_layer_box(first_layer, 18, 13, 30, 72)
    set_layer_box(second_layer, 65, 13, 31, 72)

    delivery = effect_plot_data(contrast_df, "delivery_ratio", 100.0)
    rtt = effect_plot_data(contrast_df, "rtt_p95_ms", 1.0)
    add_horizontal_forest(first_layer, delivery, "R6EffDelivery", GREEN)
    add_horizontal_forest(second_layer, rtt, "R6EffRTT", PURPLE)
    style_layer(
        first_layer,
        "Effect on delivery (percentage points)",
        "",
        (-10, 45, 10),
        (0.5, 6.5, 1),
    )
    style_layer(
        second_layer,
        "Effect on run RTT p95 (ms)",
        "",
        (-3600, 1400, 1000),
        (0.5, 6.5, 1),
    )
    # style_layer resets axis settings, so re-apply text labels.
    for layer, book_name in ((first_layer, "R6EffDelivery"), (second_layer, "R6EffRTT")):
        layer.activate()
        layer.lt_exec('layer.y.ticksbydata$="1 2 3 4 5 6";')
        layer.lt_exec(
            f"range __ticklabels=[{book_name}]Sheet1!col(label); "
            "axis -ps Y T __ticklabels;"
        )
    for layer, xlim in ((first_layer, (-10, 45)), (second_layer, (-3600, 1400))):
        zero = layer.add_line(xlim[0], 0.5, xlim[0], 0.5)
        zero.set_float("x1", 0)
        zero.set_float("y1", 0.5)
        zero.set_float("x2", 0)
        zero.set_float("y2", 6.5)
        zero.color = GRAY
        zero.width = 1.2
        zero.type = 1
    add_panel_label(first_layer, "A", -9.0, 6.32, 16)
    add_panel_label(second_layer, "B", -3500, 6.32, 16)
    remove_legend(first_layer)
    remove_legend(second_layer)
    return graph


def main() -> None:
    EXPORTS.mkdir(parents=True, exist_ok=True)
    # Start a dedicated Origin automation instance. ApplicationSI attachment
    # is not registered by every desktop installation (notably this 2024b
    # setup), while OriginExt.Application is supported by both 2024b and 2026b.
    op.set_show(True)
    op.new(asksave=False)

    import_source_tables()
    r4_delivery_runs = pd.read_csv(DATA / "round4_run_level_delivery_origin.csv")
    r4_delivery_summary = pd.read_csv(DATA / "round4_delivery_origin.csv")
    r4_rtt_runs = pd.read_csv(DATA / "round4_b2h_run_level_rtt_origin.csv")
    r4_effect = pd.read_csv(DATA / "round4_b2h_p95_effect_origin.csv")
    r6_runs = pd.read_csv(DATA / "round6_run_level_origin.csv")
    r6_cells = pd.read_csv(DATA / "round6_complete_cell_summary.csv")
    r6_contrasts = pd.read_csv(DATA / "round6_complete_contrasts.csv")

    figures = [
        (round4_delivery_graph(r4_delivery_runs, r4_delivery_summary), "Fig1_R4_all_runs_delivery"),
        (round4_rtt_distribution_graph(r4_rtt_runs), "Fig2_R4_B2H_run_level_RTT_p95"),
        (round4_effect_graph(r4_effect), "Fig3_R4_B2H_RTT_p95_effect"),
        (round6_all_cells_graph(r6_runs, r6_cells), "Fig4_R6_all_360_runs"),
        (round6_effect_graph(r6_contrasts), "Fig5_R6_complete_contrasts"),
    ]

    exported: list[str] = []
    for page, stem in figures:
        exported.extend(export_graph(page, stem))
    blank_book = op.find_book("w", "Book1")
    if blank_book is not None:
        blank_book.destroy()
    if not op.save(str(PROJECT)):
        raise RuntimeError(f"Origin failed to save {PROJECT}")
    op.exit()

    print(f"ORIGIN_PROJECT={PROJECT}")
    for path in exported:
        print(f"ORIGIN_EXPORT={path}")


if __name__ == "__main__":
    main()
