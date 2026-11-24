#!/usr/bin/env python3
"""Freeze the randomized telemetry runtime-overhead pilot schedule."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from datetime import datetime, timezone
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
PROJECT_ROOT = REPO.parent
SYSTEMS = ("mros2qos", "upstream", "microros")
MODES = ("on", "off")

BUILD_SPECS = {
    ("mros2qos", "on"): (
        REPO / "workspace/telemetry_compare/build_overhead_tickfix_on",
        "mros2qos_telemetry_compare",
    ),
    ("mros2qos", "off"): (
        REPO / "workspace/telemetry_compare/build_overhead_tickfix_off",
        "mros2qos_telemetry_compare",
    ),
    ("upstream", "on"): (
        PROJECT_ROOT
        / "upstream_bench/mros2-esp32/workspace/telemetry_compare/build_overhead_on",
        "upstream_telemetry_compare",
    ),
    ("upstream", "off"): (
        PROJECT_ROOT
        / "upstream_bench/mros2-esp32/workspace/telemetry_compare/build_overhead_off",
        "upstream_telemetry_compare",
    ),
    ("microros", "on"): (
        PROJECT_ROOT / "microros_bench/telemetry_compare/build_overhead_on",
        "microros_telemetry_compare",
    ),
    ("microros", "off"): (
        PROJECT_ROOT / "microros_bench/telemetry_compare/build_overhead_off",
        "microros_telemetry_compare",
    ),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=2026071701)
    parser.add_argument("--pairs-per-system", type=int, default=10)
    args = parser.parse_args()
    if args.pairs_per_system < 2:
        parser.error("--pairs-per-system must be at least 2")

    output = args.output if args.output.is_absolute() else REPO / args.output
    if output.exists():
        parser.error(f"output already exists: {output}")
    output.mkdir(parents=True)

    artifacts = {}
    for system in SYSTEMS:
        artifacts[system] = {}
        for mode in MODES:
            build_dir, app_name = BUILD_SPECS[(system, mode)]
            firmware = build_dir / f"{app_name}.bin"
            elf = build_dir / f"{app_name}.elf"
            map_file = build_dir / f"{app_name}.map"
            project_description = build_dir / "project_description.json"
            for path in (firmware, elf, map_file, project_description):
                if not path.is_file():
                    raise SystemExit(f"missing build artifact: {path}")
            description = json.loads(project_description.read_text())
            sdkconfig = Path(description["config_file"])
            artifacts[system][mode] = {
                "build_dir": str(build_dir),
                "firmware_sha256": sha256(firmware),
                "elf_sha256": sha256(elf),
                "map_sha256": sha256(map_file),
                "sdkconfig_sha256": sha256(sdkconfig),
            }

    rng = random.Random(args.seed)
    rows = []
    ordinal = 0
    for superblock in range(1, args.pairs_per_system + 1):
        system_order = list(SYSTEMS)
        rng.shuffle(system_order)
        for system_position, system in enumerate(system_order, start=1):
            mode_order = list(MODES)
            rng.shuffle(mode_order)
            pair_id = f"{system}-pair-{superblock:02d}"
            for pair_position, mode in enumerate(mode_order, start=1):
                ordinal += 1
                rows.append(
                    {
                        "ordinal": ordinal,
                        "run_id": f"trop-{ordinal:03d}",
                        "superblock": superblock,
                        "system_position": system_position,
                        "pair_id": pair_id,
                        "pair_position": pair_position,
                        "system": system,
                        "telemetry": mode,
                        "firmware_sha256": artifacts[system][mode]["firmware_sha256"],
                        "payload_bytes": 64,
                        "publish_rate_hz": 10,
                        "window_ms": 20_000,
                        "impairment": "clean",
                        "target_tx": 200,
                    }
                )

    schedule_path = output / "schedule.csv"
    with schedule_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    counts = {
        f"{system}_{mode}": sum(
            row["system"] == system and row["telemetry"] == mode for row in rows
        )
        for system in SYSTEMS
        for mode in MODES
    }
    manifest = {
        "schema_version": 1,
        "classification": "telemetry_runtime_overhead_pilot_preregistration",
        "status": "FROZEN_NO_DATA",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "seed": args.seed,
        "pairs_per_system": args.pairs_per_system,
        "total_scheduled_runs": len(rows),
        "counts": counts,
        "schedule_sha256": sha256(schedule_path),
        "artifacts": artifacts,
        "frozen_factors": {
            "payload_bytes": 64,
            "publish_rate_hz": 10,
            "window_ms": 20_000,
            "impairment": "clean",
            "target_tx": 200,
            "post_terminal_watchdog_seconds": 6,
            "maximum_attempts_per_scheduled_run": 3,
        },
        "evidence_boundary": (
            "engineering instrumentation-overhead pilot; excluded from all formal "
            "system and QoS performance tables"
        ),
        "pre_freeze_smokes_excluded": (
            "six N=1 control-probe hardware smokes collected before this schedule"
        ),
    }
    (output / "design_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"PASS: runs={len(rows)} pairs_per_system={args.pairs_per_system} "
        f"schedule_sha256={manifest['schedule_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
