"""Build editable Origin figures for Round 6 RTPS wire-cost analysis.

Pandas is used only to prepare Origin worksheets. All graph pages and exports
are produced by a licensed Origin instance through OriginLab's originpro API.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd
import originpro as op

from build_native_origin_project import (
    BLACK,
    BLUE,
    GREEN,
    ORANGE,
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
PACKAGE = REPO / "outputs" / "group_meeting_20260717"
DATA = PACKAGE / "wire_cost_analysis"
EXPORTS = PACKAGE / "origin_exports_wire_cost"
PROJECT = PACKAGE / "mROS2_QoS_Wire_Cost_Origin.opju"
EXPORTS = Path(os.environ.get("MROS2_ORIGIN_EXPORTS", str(EXPORTS)))
PROJECT = Path(os.environ.get("MROS2_ORIGIN_PROJECT", str(PROJECT)))

HB_SPECS = (
    (250, "H0250", GREEN, 2, -0.075),
    (1000, "H1000", BLUE, 1, 0.0),
    (4000, "H4000", ORANGE, 3, 0.075),
)


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


def _raw_x(raw: pd.DataFrame, log_offset: float) -> np.ndarray:
    run_id = raw["run_id"].to_numpy(dtype=int)
    jitter = ((((run_id * 17) % 31) - 15) / 15.0) * 0.032
    return raw["depth"].to_numpy(dtype=float) * np.exp(log_offset + jitter)


def _vertical_ci_columns(
    x: Sequence[float], low: Sequence[float], high: Sequence[float]
) -> tuple[list[float], list[float], list[float], list[float]]:
    vx: list[float] = []
    vy: list[float] = []
    cx: list[float] = []
    cy: list[float] = []
    for xx, lo, hi in zip(x, low, high):
        one = vertical_interval_segments([xx], [lo], [hi], float(xx) * 0.018)
        vx.extend(one[0])
        vy.extend(one[1])
        cx.extend(one[2])
        cy.extend(one[3])
    return vx, vy, cx, cy


def run_level_metric_graph(
    run_df: pd.DataFrame,
    cell_df: pd.DataFrame,
    *,
    long_name: str,
    graph_name: str,
    panel_specs: Sequence[tuple[object, ...]],
    legend_y: float,
):
    graph = op.new_graph(
        lname=long_name,
        template="line",
    )
    graph.name = graph_name
    set_page_size(graph, 9200, 4900)
    first_layer = graph[0]
    second_layer = graph.add_layer()
    set_layer_box(first_layer, 10, 14, 36, 70)
    set_layer_box(second_layer, 59, 14, 36, 70)

    for layer, spec in zip((first_layer, second_layer), panel_specs):
        metric, ylabel, ylim, title, sheet_name = spec
        columns: dict[str, Sequence[object]] = {}
        for hb, prefix, _, _, log_offset in HB_SPECS:
            raw = run_df.loc[run_df["heartbeat_ms"] == hb].sort_values(
                ["depth", "run_id"]
            )
            cells = cell_df.loc[cell_df["heartbeat_ms"] == hb].sort_values("depth")
            xx = cells["depth"].to_numpy(dtype=float) * np.exp(log_offset)
            low = cells[f"{metric}_ci_low"].to_numpy(dtype=float)
            high = cells[f"{metric}_ci_high"].to_numpy(dtype=float)
            vx, vy, cx, cy = _vertical_ci_columns(xx, low, high)
            columns.update(
                {
                    f"{prefix}_ci_x": vx,
                    f"{prefix}_ci_y": vy,
                    f"{prefix}_cap_x": cx,
                    f"{prefix}_cap_y": cy,
                    f"{prefix}_raw_x": _raw_x(raw, log_offset),
                    f"{prefix}_raw_y": raw[metric].to_numpy(dtype=float),
                    f"{prefix}_mean_x": xx,
                    f"{prefix}_mean_y": cells[f"{metric}_mean"].to_numpy(
                        dtype=float
                    ),
                }
            )
        wks = dataframe_sheet(
            pad_columns(columns), sheet_name, f"{ylabel} native Origin plot data"
        )
        for _, prefix, color, symbol, _ in HB_SPECS:
            plot = layer.add_plot(wks, f"{prefix}_ci_y", f"{prefix}_ci_x", type="l")
            style_line_plot(plot, color, 1.4)
            plot = layer.add_plot(
                wks, f"{prefix}_cap_y", f"{prefix}_cap_x", type="l"
            )
            style_line_plot(plot, color, 1.4)
            plot = layer.add_plot(
                wks, f"{prefix}_raw_y", f"{prefix}_raw_x", type="s"
            )
            style_raw_plot(plot, color, symbol, 5.8)
            plot.transparency = 30
            plot = layer.add_plot(
                wks, f"{prefix}_mean_y", f"{prefix}_mean_x", type="y"
            )
            style_summary_plot(plot, color, symbol)

        style_layer(
            layer,
            "History depth (log2 scale)",
            ylabel,
            (4.2, 44.5, None),
            ylim,
            xscale="log2",
            xticks=(5, 10, 20, 40),
        )
        add_panel_label(layer, title, 5.0, ylim[1] * 0.965, 14)

    set_legend(
        first_layer,
        r"\l(4) HB 250 ms    \l(8) HB 1000 ms    \l(12) HB 4000 ms",
        13,
        x=7.3,
        y=legend_y,
    )
    remove_legend(second_layer)
    return graph


def wire_cost_graph(run_df: pd.DataFrame, cell_df: pd.DataFrame):
    return run_level_metric_graph(
        run_df,
        cell_df,
        long_name="Round 6 captured RTPS cost across all 360 accepted runs",
        graph_name="FigW2WireCost",
        panel_specs=(
            (
                "pair_rtps_wire_bytes_per_tx",
                "Captured RTPS bytes / application TX",
                (450, 4300, 500),
                "A  Wire bytes per application TX",
                "W2BytesPlot",
            ),
            (
                "target_control_only_share_pct",
                "Target-endpoint control-only bytes (%)",
                (5, 75, 10),
                "B  Control-only share of target traffic",
                "W2ControlPlot",
            ),
        ),
        legend_y=4210,
    )


def wire_load_graph(run_df: pd.DataFrame, cell_df: pd.DataFrame):
    return run_level_metric_graph(
        run_df,
        cell_df,
        long_name="Round 6 captured RTPS frame and rate load",
        graph_name="FigW2SWireLoad",
        panel_specs=(
            (
                "pair_rtps_frames_per_tx",
                "Captured RTPS frames / application TX",
                (0, 43, 10),
                "A  RTPS frames per application TX",
                "W2SFramesPlot",
            ),
            (
                "pair_rtps_kbit_s",
                "Captured RTPS rate (kbit/s)",
                (0, 36, 10),
                "B  Captured RTPS wire rate",
                "W2SRatePlot",
            ),
        ),
        legend_y=34.8,
    )


def _add_cost_outcome_series(
    layer,
    wks,
    prefix: str,
    color: str,
    symbol: int,
) -> None:
    for suffix, width in (
        ("xci", 1.4),
        ("xcap", 1.4),
        ("yci", 1.4),
        ("ycap", 1.4),
    ):
        plot = layer.add_plot(wks, f"{prefix}_{suffix}_y", f"{prefix}_{suffix}_x", type="l")
        style_line_plot(plot, color, width)
    plot = layer.add_plot(wks, f"{prefix}_mean_y", f"{prefix}_mean_x", type="y")
    style_summary_plot(plot, color, symbol)


def cost_performance_graph(cell_df: pd.DataFrame):
    graph = op.new_graph(
        lname="Round 6 application outcomes versus captured RTPS cost",
        template="line",
    )
    graph.name = "FigW3CostPerformance"
    set_page_size(graph, 9200, 4900)
    first_layer = graph[0]
    second_layer = graph.add_layer()
    set_layer_box(first_layer, 10, 14, 36, 70)
    set_layer_box(second_layer, 59, 14, 36, 70)

    panel_specs = (
        (
            first_layer,
            "delivery_pct",
            "Application delivery (%)",
            (45, 103, 10),
            "A  Delivery versus wire cost",
            "W3DeliveryPlot",
            1.0,
        ),
        (
            second_layer,
            "rtt_p95_ms",
            "Run-level RTT p95 (ms)",
            (0, 4500, 1000),
            "B  RTT tail versus wire cost",
            "W3RTTPlot",
            80.0,
        ),
    )
    xmetric = "pair_rtps_wire_bytes_per_tx"

    for layer, ymetric, ylabel, ylim, title, sheet_name, ycap in panel_specs:
        columns: dict[str, Sequence[object]] = {}
        for hb, prefix, _, _, _ in HB_SPECS:
            cells = cell_df.loc[cell_df["heartbeat_ms"] == hb].sort_values("depth")
            xx = cells[f"{xmetric}_mean"].to_numpy(dtype=float)
            yy = cells[f"{ymetric}_mean"].to_numpy(dtype=float)
            xline, yline, xcap, ycap_values = horizontal_interval_segments(
                yy,
                cells[f"{xmetric}_ci_low"],
                cells[f"{xmetric}_ci_high"],
                ycap,
            )
            yline_x, yline_y, ycap_x, ycap_y = vertical_interval_segments(
                xx,
                cells[f"{ymetric}_ci_low"],
                cells[f"{ymetric}_ci_high"],
                28.0,
            )
            columns.update(
                {
                    f"{prefix}_xci_x": xline,
                    f"{prefix}_xci_y": yline,
                    f"{prefix}_xcap_x": xcap,
                    f"{prefix}_xcap_y": ycap_values,
                    f"{prefix}_yci_x": yline_x,
                    f"{prefix}_yci_y": yline_y,
                    f"{prefix}_ycap_x": ycap_x,
                    f"{prefix}_ycap_y": ycap_y,
                    f"{prefix}_mean_x": xx,
                    f"{prefix}_mean_y": yy,
                    f"{prefix}_depth": cells["depth"].to_numpy(dtype=int),
                }
            )
        wks = dataframe_sheet(
            pad_columns(columns),
            sheet_name,
            f"{ylabel} versus captured RTPS cost native Origin plot data",
        )
        for _, prefix, color, symbol, _ in HB_SPECS:
            _add_cost_outcome_series(layer, wks, prefix, color, symbol)

        style_layer(
            layer,
            "Captured RTPS bytes / application TX",
            ylabel,
            (450, 4300, 500),
            ylim,
        )
        add_panel_label(layer, title, 560, ylim[1] * 0.965, 14)

    set_legend(
        first_layer,
        r"\l(5) HB 250 ms    \l(10) HB 1000 ms    \l(15) HB 4000 ms",
        13,
        x=1020,
        y=101.5,
    )
    remove_legend(second_layer)
    return graph


def main() -> None:
    EXPORTS.mkdir(parents=True, exist_ok=True)
    run_df = pd.read_csv(DATA / "round6_wire_cost_run_level.csv")
    cell_df = pd.read_csv(DATA / "round6_wire_cost_cell_summary.csv")

    if len(run_df) != 360 or len(cell_df) != 12:
        raise RuntimeError(
            f"Unexpected input dimensions: runs={len(run_df)}, cells={len(cell_df)}"
        )
    counts = run_df.groupby(["depth", "heartbeat_ms"]).size()
    if not (counts == 30).all():
        raise RuntimeError(f"Expected 30 runs per cell, got {counts.to_dict()}")

    print("ORIGIN_STAGE=start", flush=True)
    op.set_show(True)
    op.new(asksave=False)
    print("ORIGIN_STAGE=new_project", flush=True)
    dataframe_sheet(run_df, "WireRuns", "Round 6 wire-cost run-level source data")
    dataframe_sheet(cell_df, "WireCells", "Round 6 wire-cost cell summary source data")
    print("ORIGIN_STAGE=source_tables", flush=True)

    figures = [
        (wire_cost_graph(run_df, cell_df), "FigW2_Wireshark_wire_cost"),
        (wire_load_graph(run_df, cell_df), "FigW2S_Wireshark_wire_load"),
        (
            cost_performance_graph(cell_df),
            "FigW3_Wireshark_cost_performance",
        ),
    ]
    print("ORIGIN_STAGE=graph_pages", flush=True)
    exported: list[str] = []
    for page, stem in figures:
        exported.extend(export_graph(page, stem))
        print(f"ORIGIN_STAGE=exported:{stem}", flush=True)

    blank_book = op.find_book("w", "Book1")
    if blank_book is not None:
        blank_book.destroy()
    if not op.save(str(PROJECT)):
        raise RuntimeError(f"Origin failed to save {PROJECT}")
    print("ORIGIN_STAGE=saved", flush=True)
    op.exit()

    print(f"ORIGIN_PROJECT={PROJECT}")
    for path in exported:
        print(f"ORIGIN_EXPORT={path}")


if __name__ == "__main__":
    main()
