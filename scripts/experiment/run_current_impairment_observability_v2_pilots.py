#!/usr/bin/env python3
"""Collect impaired cells and matched controls with board-side observability."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from run_current_impairment_matrix_pilots import (
    ACK_TEXT,
    PROJECT,
    REPO,
    build_firmware,
    chown_tree,
    existing_result,
    run_smoke,
    verify_build,
)


PROFILES = (
    "clean",
    "delay20ms_jitter10ms_normal_h2b",
    "delay20ms_reorder25_corr50_gap5_h2b",
    "loss5_independent_h2b",
    "burst_ge_p1_r25_h95_k999_h2b",
)


def write_ledger(path: Path, entries: list[dict[str, object]]) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "classification": "impairment_observability_v2_engineering_pilot",
                "evidence_boundary": "excluded N=1 efficacy pilots; never formal comparison data",
                "updated_at_utc": datetime.now(timezone.utc).isoformat(),
                "expected_cells": 10,
                "collected_cells": sum(
                    entry["collection_status"] == "COLLECTED" for entry in entries
                ),
                "energy_gate": "BLOCKED_EXTERNAL_CALIBRATED_MONITOR_AND_GPIO_ALIGNMENT",
                "entries": entries,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-user", default="wsde-47")
    parser.add_argument("--interface", default="eth1")
    parser.add_argument("--board-ip", default="192.0.2.1")
    parser.add_argument("--network-change-ack", required=True)
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("this runner must execute as root")
    if args.network_change_ack != ACK_TEXT:
        parser.error(f"--network-change-ack must be {ACK_TEXT}")
    if shutil.disk_usage("/mnt/c").free < 5 * 1024**3:
        parser.error("host storage gate failed: less than 5 GiB free on /mnt/c")

    audit_root = (
        REPO / "results/audits/20260720_impairment_observability_v2_pilots"
    )
    audit_root.mkdir(parents=True, exist_ok=True)
    ledger_path = audit_root / "collection_ledger.json"
    entries = []
    if ledger_path.is_file():
        entries = json.loads(ledger_path.read_text(encoding="utf-8")).get(
            "entries", []
        )
    by_key = {(entry["qos"], entry["profile"]): entry for entry in entries}
    fatal_error = False

    for qos in ("BEST_EFFORT", "RELIABLE"):
        qos_label = "be" if qos == "BEST_EFFORT" else "rel"
        build_dir = PROJECT / f"build_impair_{qos_label}_p512_r50_matrix"
        for profile in PROFILES:
            output = (
                REPO
                / "results/diagnostics"
                / (
                    f"20260720_impair_{qos_label}_p512_r50_{profile}"
                    "_observability_v2_smoke"
                )
            )
            key = (qos, profile)
            entry = by_key.get(
                key,
                {
                    "qos": qos,
                    "profile": profile,
                    "relative_path": output.relative_to(REPO).as_posix(),
                },
            )
            by_key[key] = entry
            smoke_status, collected = existing_result(output)
            if collected:
                entry.update(
                    collection_status="COLLECTED",
                    smoke_status=smoke_status,
                    disposition="existing v2 evidence retained",
                )
                write_ledger(ledger_path, list(by_key.values()))
                print(f"SKIP: {qos}/{profile}", flush=True)
                continue

            build_log = audit_root / f"build_{qos_label}_{profile}.log"
            run_log = audit_root / f"run_{qos_label}_{profile}.log"
            try:
                print(f"BUILD: {qos}/{profile}", flush=True)
                build = build_firmware(
                    args.run_user, qos, profile, build_dir, build_log
                )
                if build.returncode != 0:
                    raise RuntimeError(f"build returned {build.returncode}")
                verify_build(build_dir, qos, profile)
                print(f"RUN: {qos}/{profile}", flush=True)
                run = run_smoke(
                    args, qos, profile, build_dir, output, run_log
                )
                smoke_status, collected = existing_result(output)
                entry.update(
                    build_returncode=build.returncode,
                    wrapper_returncode=run.returncode,
                    collection_status="COLLECTED" if collected else "INCOMPLETE",
                    smoke_status=smoke_status,
                    disposition="observability v2 efficacy smoke",
                )
                if not collected:
                    fatal_error = True
            except Exception as exc:
                entry.update(
                    collection_status="INCOMPLETE",
                    smoke_status="ERROR",
                    disposition=str(exc),
                )
                fatal_error = True
                print(f"ERROR: {qos}/{profile}: {exc}", file=sys.stderr, flush=True)

            current_entries = list(by_key.values())
            write_ledger(ledger_path, current_entries)
            chown_tree(audit_root, args.run_user)
            if fatal_error:
                break
        if fatal_error:
            break

    entries = list(by_key.values())
    write_ledger(ledger_path, entries)
    chown_tree(audit_root, args.run_user)
    collected_count = sum(
        entry.get("collection_status") == "COLLECTED" for entry in entries
    )
    print(
        f"DONE: ledger_cells={len(entries)} collected={collected_count} "
        f"fatal_error={fatal_error}",
        flush=True,
    )
    return 1 if fatal_error else 0


if __name__ == "__main__":
    raise SystemExit(main())
