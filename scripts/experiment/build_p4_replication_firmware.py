#!/usr/bin/env python3
"""Build and archive the frozen P4 RELIABLE/BEST_EFFORT firmware pair."""

import argparse
import csv
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
from datetime import datetime, timezone

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from build_round6_variants import (
    archive_file,
    build_artifact_sources,
    git_output,
    parse_cmake_cache,
    sha256_file,
)


QOS_MODES = ("reliable", "best_effort")
LOSS_TARGETS = (0, 5, 15)
DEPTH = 5
HISTORY_CAPACITY = 10
HEARTBEAT_MS = 4000
RESOURCE_MAX_SAMPLES = 30
RESOURCE_MAX_BYTES = 65536
WIFI_INITIAL_CONNECT_TIMEOUT_MS = 180000
SEED = 20260715
BLOCKS = 10
RUNS_PER_VISIT = 3


def cells():
    return [
        {
            "id": f"{qos}_target{loss:02d}",
            "qos": qos,
            "target_loss_percent": loss,
            "gact_denominator": 0 if loss == 0 else round(100 / loss),
            "effective_loss_percent": (
                0.0 if loss == 0 else 100.0 / round(100 / loss)
            ),
        }
        for qos in QOS_MODES
        for loss in LOSS_TARGETS
    ]


def randomized_schedule(seed=SEED):
    rng = random.Random(seed)
    output = []
    for block in range(1, BLOCKS + 1):
        order = cells()
        rng.shuffle(order)
        first = (block - 1) * RUNS_PER_VISIT + 1
        for visit, cell in enumerate(order, start=1):
            output.append({
                "block": block,
                "visit": visit,
                **cell,
                "run_start": first,
                "run_end": first + RUNS_PER_VISIT - 1,
            })
    return output


def ensure_clean(project_root):
    if git_output(project_root, "status", "--porcelain"):
        raise SystemExit("P4 firmware builds require a clean worktree")
    sdkconfig = project_root / "workspace/qos_eval/sdkconfig"
    if "CONFIG_APP_REPRODUCIBLE_BUILD=y" not in sdkconfig.read_text(encoding="utf-8"):
        raise SystemExit("CONFIG_APP_REPRODUCIBLE_BUILD=y is required")


def build_command(build_dir):
    return [
        "idf.py",
        "-B",
        str(build_dir),
        "-D",
        f"MROS2_QOS_HISTORY_DEPTH={DEPTH}",
        "-D",
        f"MROS2_RTPS_HISTORY_CAPACITY={HISTORY_CAPACITY}",
        "-D",
        f"MROS2_RTPS_HEARTBEAT_PERIOD_MS={HEARTBEAT_MS}",
        "-D",
        f"MROS2_QOS_RESOURCE_MAX_SAMPLES={RESOURCE_MAX_SAMPLES}",
        "-D",
        f"MROS2_QOS_RESOURCE_MAX_BYTES={RESOURCE_MAX_BYTES}",
        "-D",
        f"MROS2_WIFI_INITIAL_CONNECT_TIMEOUT_MS={WIFI_INITIAL_CONNECT_TIMEOUT_MS}",
        "build",
    ]


def verify_compile_evidence(build_dir, qos):
    entries = json.loads(
        (build_dir / "compile_commands.json").read_text(encoding="utf-8")
    )
    main_command = next(
        entry["command"] for entry in entries
        if entry["file"].endswith("/main/app.cpp")
    )
    wifi_command = next(
        entry["command"] for entry in entries
        if entry["file"].endswith("/platform/wifi/wifi.c")
    )
    expected = [
        f"-DMROS2_QOS_HISTORY_DEPTH={DEPTH}",
        f"-DMROS2_RTPS_HISTORY_CAPACITY={HISTORY_CAPACITY}",
        f"-DMROS2_RTPS_HEARTBEAT_PERIOD_MS={HEARTBEAT_MS}",
        f"-DMROS2_QOS_RESOURCE_MAX_SAMPLES={RESOURCE_MAX_SAMPLES}",
        f"-DMROS2_QOS_RESOURCE_MAX_BYTES={RESOURCE_MAX_BYTES}",
    ]
    missing = [flag for flag in expected if flag not in main_command]
    best_effort_flag = "-DMROS2_QOS_BEST_EFFORT=1"
    if qos == "best_effort" and best_effort_flag not in main_command:
        missing.append(best_effort_flag)
    if qos == "reliable" and best_effort_flag in main_command:
        missing.append(f"unexpected {best_effort_flag}")
    if missing:
        raise ValueError(f"{qos} compile evidence mismatch: {missing}")
    wifi_flag = (
        "-DMROS2_WIFI_INITIAL_CONNECT_TIMEOUT_MS="
        f"{WIFI_INITIAL_CONNECT_TIMEOUT_MS}"
    )
    if wifi_flag not in wifi_command:
        raise ValueError(f"{qos} Wi-Fi compile evidence mismatch: {wifi_flag}")
    return expected + [wifi_flag] + (
        [best_effort_flag] if qos == "best_effort" else []
    )


def expected_cache():
    return {
        "MROS2_QOS_HISTORY_DEPTH": str(DEPTH),
        "MROS2_RTPS_HISTORY_CAPACITY": str(HISTORY_CAPACITY),
        "MROS2_RTPS_HEARTBEAT_PERIOD_MS": str(HEARTBEAT_MS),
        "MROS2_QOS_RESOURCE_MAX_SAMPLES": str(RESOURCE_MAX_SAMPLES),
        "MROS2_QOS_RESOURCE_MAX_BYTES": str(RESOURCE_MAX_BYTES),
        "MROS2_WIFI_INITIAL_CONNECT_TIMEOUT_MS": str(
            WIFI_INITIAL_CONNECT_TIMEOUT_MS
        ),
    }


def build_variant(workspace, build_root, output_dir, qos, source_commit, epoch):
    variant_dir = output_dir / "variants" / qos
    build_dir = build_root / f"build_p4_{qos}"
    variant_dir.mkdir(parents=True, exist_ok=True)
    log_path = variant_dir / "build.log"
    command = build_command(build_dir)
    environment = os.environ.copy()
    environment["SOURCE_DATE_EPOCH"] = str(epoch)
    environment["MROS2_QOS_MODE"] = qos
    print(f"[build] {qos}")
    with log_path.open("w", encoding="utf-8") as log:
        subprocess.run(
            command,
            cwd=workspace,
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            check=True,
        )
    cache = parse_cmake_cache(build_dir / "CMakeCache.txt")
    observed = {key: cache.get(key) for key in expected_cache()}
    if observed != expected_cache():
        raise SystemExit(f"{qos} CMake cache mismatch: {observed}")
    definitions = verify_compile_evidence(build_dir, qos)
    artifact_dir = output_dir / "artifacts"
    artifacts = {
        role: archive_file(
            source,
            artifact_dir,
            f"p4_{qos}_{role}",
            manifest_root=output_dir,
        )
        for role, source in build_artifact_sources(workspace, build_dir).items()
    }
    artifacts["build_log"] = archive_file(
        log_path,
        artifact_dir,
        f"p4_{qos}_build_log",
        manifest_root=output_dir,
    )
    project = json.loads(
        (build_dir / "project_description.json").read_text(encoding="utf-8")
    )
    manifest = {
        "schema_version": 1,
        "classification": "p4_replication_firmware_build",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "qos": qos,
        "source_commit": source_commit,
        "source_date_epoch": epoch,
        "app_version": project.get("project_version"),
        "reproducible_build": True,
        "parameters": {
            "MROS2_QOS_HISTORY_DEPTH": DEPTH,
            "MROS2_RTPS_HISTORY_CAPACITY": HISTORY_CAPACITY,
            "MROS2_RTPS_HEARTBEAT_PERIOD_MS": HEARTBEAT_MS,
            "MROS2_QOS_RESOURCE_MAX_SAMPLES": RESOURCE_MAX_SAMPLES,
            "MROS2_QOS_RESOURCE_MAX_BYTES": RESOURCE_MAX_BYTES,
            "MROS2_WIFI_INITIAL_CONNECT_TIMEOUT_MS": (
                WIFI_INITIAL_CONNECT_TIMEOUT_MS
            ),
        },
        "cmake_cache": observed,
        "compile_definitions": definitions,
        "build_command": command,
        "artifacts": artifacts,
        "smoke_gate": {"required_runs": 3, "status": "PENDING"},
    }
    (variant_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"[archive] {qos} {artifacts['firmware']['sha256']}")
    return manifest


def reproducibility_check(workspace, build_root, output_dir, manifests, epoch):
    results = {}
    for qos, manifest in manifests.items():
        build_dir = build_root / f"build_p4_reprocheck_{qos}"
        log_path = output_dir / f"reprocheck_{qos}.log"
        environment = os.environ.copy()
        environment["SOURCE_DATE_EPOCH"] = str(epoch)
        environment["MROS2_QOS_MODE"] = qos
        with log_path.open("w", encoding="utf-8") as log:
            subprocess.run(
                build_command(build_dir),
                cwd=workspace,
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                check=True,
            )
        observed = {
            "firmware": sha256_file(build_dir / "qos_eval.bin"),
            "bootloader": sha256_file(build_dir / "bootloader/bootloader.bin"),
            "partition_table": sha256_file(
                build_dir / "partition_table/partition-table.bin"
            ),
        }
        expected = {
            role: manifest["artifacts"][role]["sha256"] for role in observed
        }
        if observed != expected:
            raise SystemExit(f"{qos} reproducibility SHA mismatch")
        results[qos] = {
            "result": "PASS",
            "observed_sha256": observed,
            "build_log_sha256": sha256_file(log_path),
        }
        print(f"[reproducibility] {qos} PASS")
    return results


def write_schedule(output_dir, seed):
    rows = randomized_schedule(seed)
    csv_path = output_dir / "randomized_schedule.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return csv_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    project_root = Path(__file__).resolve().parents[2]
    parser.add_argument("--project-root", type=Path, default=project_root)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--build-root", type=Path)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()
    project_root = args.project_root.resolve()
    workspace = project_root / "workspace/qos_eval"
    build_root = (args.build_root or workspace).resolve()
    output_dir = args.output_dir.resolve()
    if not shutil.which("idf.py"):
        raise SystemExit("idf.py unavailable; source the ESP-IDF environment")
    ensure_clean(project_root)
    source_commit = git_output(project_root, "rev-parse", "HEAD")
    epoch = int(git_output(project_root, "show", "-s", "--format=%ct", source_commit))
    output_dir.mkdir(parents=True, exist_ok=True)
    schedule_path = write_schedule(output_dir, args.seed)
    manifests = {
        qos: build_variant(
            workspace, build_root, output_dir, qos, source_commit, epoch
        )
        for qos in QOS_MODES
    }
    reproducibility = reproducibility_check(
        workspace, build_root, output_dir, manifests, epoch
    )
    master = {
        "schema_version": 1,
        "classification": "p4_replication_firmware_set",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": source_commit,
        "source_date_epoch": epoch,
        "randomization_seed": args.seed,
        "schedule_sha256": sha256_file(schedule_path),
        "reproducibility_check": reproducibility,
        "variants": {
            qos: {
                "manifest": f"variants/{qos}/manifest.json",
                "firmware": manifest["artifacts"]["firmware"],
            }
            for qos, manifest in manifests.items()
        },
    }
    master_path = output_dir / "manifest.json"
    master_path.write_text(
        json.dumps(master, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"[complete] {master_path}")


if __name__ == "__main__":
    main()
