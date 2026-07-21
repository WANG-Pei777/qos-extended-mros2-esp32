#!/usr/bin/env python3
"""Build an auditable Origin project from the three-system analysis exports."""

from __future__ import annotations

import argparse
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import subprocess

import pandas as pd


SYSTEM_ORDER = ("mros2qos", "upstream", "microros")
SYSTEM_LABELS = {
    "mros2qos": "mROS2-QoS",
    "upstream": "upstream mros2-esp32",
    "microros": "micro-ROS",
}
COLORS = ("#176B87", "#C04B3A", "#4B7F52")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_commit():
    completed = subprocess.run(
        ["git", "-C", str(Path(__file__).resolve().parents[2]), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def require_inputs(root):
    names = (
        "run_metrics.csv",
        "publication_system_table.csv",
        "publication_confirmatory_table.csv",
        "resource_wire_table.csv",
        "three_system_primary_outcomes.png",
        "figure_caption.md",
        "analysis_report.json",
    )
    paths = {name: root / name for name in names}
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise SystemExit(f"missing analysis inputs: {missing}")
    return paths


def add_frame(book, name, frame):
    sheet = book.add_sheet(name)
    sheet.lname = name
    sheet.from_df(frame, addindex=False)
    return sheet


def make_primary_frame(metrics):
    columns = {}
    for system in SYSTEM_ORDER:
        subset = metrics.loc[metrics["system"] == system].sort_values(
            "accepted_ordinal"
        )
        if len(subset) != 100:
            raise SystemExit(f"Origin export requires 100 runs for {system}")
        columns[f"{SYSTEM_LABELS[system]} RTT p95 (ms)"] = (
            subset["rtt_p95_us"].to_numpy() / 1_000.0
        )
    for system in SYSTEM_ORDER:
        subset = metrics.loc[metrics["system"] == system].sort_values(
            "accepted_ordinal"
        )
        columns[f"{SYSTEM_LABELS[system]} reset-to-ready (s)"] = (
            subset["runner_ready_ms"].to_numpy() / 1_000.0
        )
    return pd.DataFrame(columns)


def add_editable_box_graph(op, sheet, name, column_indices, y_title):
    graph = op.new_graph(lname=name, template="BOX", hidden=False)
    if graph is None:
        raise RuntimeError("Origin BOX template did not create a graph")
    layer = graph[0]
    for column in column_indices:
        if layer.add_plot(sheet, coly=column, type=206) is None:
            raise RuntimeError(f"Origin failed to add box plot for column {column}")
    layer.group(False)
    for plot, color in zip(layer.plot_list(), COLORS):
        plot.color = color
        plot.transparency = 18
    layer.axis("y").title = y_title
    layer.axis("x").title = ""
    layer.rescale()
    layer.lt_exec(
        'layer.color=color(white); layer.y.showgrids=1; '
        'layer.x.from=0.5; layer.x.to=3.5; layer.x.inc=1; '
        'layer.x.showLabels=1; layer.x.label.type=10; '
        'layer.x.label.string$="mROS2-QoS upstream micro-ROS";'
    )
    legend = layer.label("Legend")
    if legend:
        legend.remove()
    graph.set_int("aa", 1)
    return graph


def main():
    args = parse_args()
    root = args.analysis_root.resolve()
    inputs = require_inputs(root)
    output = (
        args.output.resolve()
        if args.output
        else root / "three_system_formal_origin.opju"
    )
    output.parent.mkdir(parents=True, exist_ok=True)

    metrics = pd.read_csv(inputs["run_metrics.csv"])
    if len(metrics) != 300:
        raise SystemExit("Origin export requires exactly 300 accepted runs")
    primary = make_primary_frame(metrics)
    system_table = pd.read_csv(inputs["publication_system_table.csv"])
    contrast_table = pd.read_csv(inputs["publication_confirmatory_table.csv"])
    resource_table = pd.read_csv(inputs["resource_wire_table.csv"])
    caption = inputs["figure_caption.md"].read_text(encoding="utf-8").strip()
    analysis_report = json.loads(
        inputs["analysis_report.json"].read_text(encoding="utf-8")
    )

    try:
        import originpro as op
    except ImportError as exc:
        raise SystemExit("originpro is required to build the .opju project") from exc

    origin_version = None
    reopen_verification = None
    try:
        if op.oext:
            op.set_show(False)
        op.new(asksave=False)
        op.lt_exec("@GEFD=0;")
        data_book = next(op.pages("w"))
        data_book.lname = "Three-System Formal Data"
        primary_sheet = data_book[0]
        primary_sheet.lname = "Primary Outcomes"
        primary_sheet.from_df(primary, addindex=False)
        primary_sheet.cols_axis("yyyyyy")

        tables = op.new_book("w", lname="Publication Tables")
        tables[0].lname = "System Summary"
        tables[0].from_df(system_table, addindex=False)
        add_frame(tables, "Confirmatory", contrast_table)
        add_frame(tables, "Resource Wire", resource_table)

        provenance = pd.DataFrame(
            [
                {"item": name, "sha256": sha256_file(path), "path": str(path)}
                for name, path in inputs.items()
            ]
        )
        add_frame(tables, "Provenance", provenance)

        add_editable_box_graph(
            op, primary_sheet, "Editable RTT p95", range(0, 3), "RTT p95 (ms)"
        )
        add_editable_box_graph(
            op,
            primary_sheet,
            "Editable Reset-to-ready",
            range(3, 6),
            "Reset-to-ready (s)",
        )
        image = op.new_image(lname="Final Publication Figure")
        if not image.from_file(str(inputs["three_system_primary_outcomes.png"])):
            raise RuntimeError("Origin failed to import the final publication figure")
        image.lname = "Final Publication Figure"

        caption_note = op.new_notes("Figure Caption")
        caption_note.text = caption
        provenance_note = op.new_notes("Analysis Provenance")
        provenance_note.text = json.dumps(
            {
                "classification": "three_system_origin_project",
                "analysis_report": analysis_report,
                "note": (
                    "Final Publication Figure is the exact sealed raster. "
                    "The two Editable graph pages are native Origin views linked "
                    "to the 300-run worksheet."
                ),
            },
            indent=2,
            sort_keys=True,
        )
        origin_version = op.org_ver()
        op.save(str(output))
        op.new(asksave=False)
        opened = bool(op.open(str(output)))
        pages = [(type(page).__name__, page.lname) for page in op.pages()]
        notes = {}
        for name in ("Figure Caption", "Analysis Provenance"):
            note = op.find_notes(name)
            notes[name] = len(note.text) if note else 0
        expected_pages = [
            ("WBook", "Three-System Formal Data"),
            ("WBook", "Publication Tables"),
            ("GPage", "Editable RTT p95"),
            ("GPage", "Editable Reset-to-ready"),
            ("IPage", "Final Publication Figure"),
        ]
        reopen_verification = {
            "opened": opened,
            "pages": pages,
            "notes_character_counts": notes,
            "status": (
                "PASS"
                if opened
                and pages == expected_pages
                and all(count > 0 for count in notes.values())
                else "FAIL"
            ),
        }
        if reopen_verification["status"] != "PASS":
            raise RuntimeError(
                f"Origin project reopen verification failed: {reopen_verification}"
            )
    finally:
        op.exit()

    if not output.is_file():
        raise SystemExit(f"Origin did not create project: {output}")
    manifest = {
        "schema_version": 1,
        "classification": "three_system_origin_project_manifest",
        "status": "COMPLETE",
        "project": {
            "path": str(output),
            "bytes": output.stat().st_size,
            "sha256": sha256_file(output),
        },
        "origin_application_version": origin_version,
        "originpro_python_version": version("originpro"),
        "reopen_verification": reopen_verification,
        "builder": {
            "source_commit": source_commit(),
            "script_path": str(Path(__file__).resolve()),
            "script_sha256": sha256_file(Path(__file__).resolve()),
        },
        "runs": len(metrics),
        "inputs": {
            name: {"path": str(path), "sha256": sha256_file(path)}
            for name, path in inputs.items()
        },
    }
    manifest_path = output.with_name("origin_project_manifest.json")
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
