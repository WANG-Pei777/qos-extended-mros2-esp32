#!/usr/bin/env python3
"""Build and immutably archive the preregistered Round 6 firmware variants."""

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
from datetime import datetime, timezone


DEPTHS = (5, 10, 20, 40)
HEARTBEATS_MS = (250, 1000, 4000)
HISTORY_CAPACITY = 48
RESOURCE_MAX_SAMPLES = 48
RESOURCE_MAX_BYTES = 65536
RANDOMIZATION_SEED = 20260714
SUPERBLOCKS = 10
RUNS_PER_VISIT = 3


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def variants():
    return [
        {
            "id": f"d{depth:02d}_h{heartbeat:04d}",
            "depth": depth,
            "heartbeat_ms": heartbeat,
        }
        for depth in DEPTHS
        for heartbeat in HEARTBEATS_MS
    ]


def randomized_schedule(seed=RANDOMIZATION_SEED):
    rng = random.Random(seed)
    cells = variants()
    schedule = []
    for block in range(1, SUPERBLOCKS + 1):
        order = list(cells)
        rng.shuffle(order)
        for visit, cell in enumerate(order, start=1):
            first_run = (block - 1) * RUNS_PER_VISIT + 1
            schedule.append(
                {
                    "block": block,
                    "visit": visit,
                    **cell,
                    "run_start": first_run,
                    "run_end": first_run + RUNS_PER_VISIT - 1,
                }
            )
    return schedule


def archive_file(source, artifact_dir, role, manifest_root=None):
    source = Path(source).resolve()
    if not source.is_file():
        raise ValueError(f"missing artifact: {source}")
    digest = sha256_file(source)
    suffix = "".join(source.suffixes) or ".bin"
    artifact_dir = Path(artifact_dir).resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    destination = artifact_dir / f"{role}_{digest}{suffix}"
    if destination.exists():
        if sha256_file(destination) != digest:
            raise ValueError(f"corrupt existing archive: {destination}")
    else:
        shutil.copy2(source, destination)
        destination.chmod(0o444)
    display_path = destination
    if manifest_root is not None:
        display_path = destination.relative_to(Path(manifest_root).resolve())
    return {
        "path": str(display_path),
        "source_path": str(source),
        "sha256": digest,
        "bytes": destination.stat().st_size,
    }


def parse_cmake_cache(path):
    values = {}
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        if not line or line.startswith(("#", "//")) or "=" not in line:
            continue
        key_and_type, value = line.split("=", 1)
        key = key_and_type.split(":", 1)[0]
        values[key] = value
    return values


def compile_definition_evidence(path, variant):
    entries = json.loads(Path(path).read_text(encoding="utf-8"))
    main_command = next(
        entry["command"]
        for entry in entries
        if entry["file"].endswith("/main/app.cpp")
    )
    rtps_command = next(
        entry["command"]
        for entry in entries
        if entry["file"].endswith("/entities/Participant.cpp")
    )
    expected_main = [
        f"-DMROS2_QOS_HISTORY_DEPTH={variant['depth']}",
        f"-DMROS2_RTPS_HISTORY_CAPACITY={HISTORY_CAPACITY}",
        f"-DMROS2_RTPS_HEARTBEAT_PERIOD_MS={variant['heartbeat_ms']}",
        f"-DMROS2_QOS_RESOURCE_MAX_SAMPLES={RESOURCE_MAX_SAMPLES}",
        f"-DMROS2_QOS_RESOURCE_MAX_BYTES={RESOURCE_MAX_BYTES}",
    ]
    expected_rtps = [
        f"-DMROS2_RTPS_HISTORY_CAPACITY={HISTORY_CAPACITY}",
        f"-DMROS2_RTPS_HEARTBEAT_PERIOD_MS={variant['heartbeat_ms']}",
    ]
    missing = [
        flag
        for flag in expected_main
        if flag not in main_command
    ] + [
        flag
        for flag in expected_rtps
        if flag not in rtps_command
    ]
    if missing:
        raise ValueError(f"compile definitions missing for {variant['id']}: {missing}")
    return {"main": expected_main, "rtps": expected_rtps}


def write_schedule(output_dir, seed):
    rows = randomized_schedule(seed)
    csv_path = output_dir / "randomized_schedule.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    json_path = output_dir / "randomized_schedule.json"
    json_path.write_text(
        json.dumps(
            {
                "seed": seed,
                "superblocks": SUPERBLOCKS,
                "runs_per_visit": RUNS_PER_VISIT,
                "schedule": rows,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return csv_path, json_path


def git_output(project_root, *args):
    return subprocess.check_output(
        ["git", "-C", str(project_root), *args],
        text=True,
    ).strip()


def ensure_clean_source(project_root):
    status = git_output(project_root, "status", "--porcelain")
    if status:
        raise SystemExit("formal variant builds require a clean worktree")
    sdkconfig = project_root / "workspace/qos_eval/sdkconfig"
    if "CONFIG_APP_REPRODUCIBLE_BUILD=y" not in sdkconfig.read_text(encoding="utf-8"):
        raise SystemExit("CONFIG_APP_REPRODUCIBLE_BUILD=y is required")


def verify_archived_record(record, manifest_root=None):
    path = Path(record["path"])
    if not path.is_absolute() and manifest_root is not None:
        path = Path(manifest_root) / path
    return (
        path.is_file()
        and path.stat().st_size == record["bytes"]
        and sha256_file(path) == record["sha256"]
    )


def build_variant(
    project_root,
    workspace,
    build_root,
    output_dir,
    source_commit,
    source_date_epoch,
    variant,
):
    variant_dir = output_dir / "variants" / variant["id"]
    manifest_path = variant_dir / "manifest.json"
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (
            existing.get("source_commit") == source_commit
            and existing.get("parameters", {}).get("MROS2_QOS_HISTORY_DEPTH")
            == variant["depth"]
            and existing.get("parameters", {}).get(
                "MROS2_RTPS_HEARTBEAT_PERIOD_MS"
            )
            == variant["heartbeat_ms"]
            and all(
                verify_archived_record(record, output_dir)
                for record in existing.get("artifacts", {}).values()
            )
        ):
            print(f"[resume] {variant['id']} archive verified")
            return existing
        raise SystemExit(f"conflicting or corrupt existing manifest: {manifest_path}")

    variant_dir.mkdir(parents=True, exist_ok=True)
    build_dir = build_root / f"build_round6_{variant['id']}"
    log_path = variant_dir / "build.log"
    if log_path.exists():
        log_path.chmod(0o644)
    command = [
        "idf.py",
        "-B",
        str(build_dir),
        "-D",
        f"MROS2_QOS_HISTORY_DEPTH={variant['depth']}",
        "-D",
        f"MROS2_RTPS_HISTORY_CAPACITY={HISTORY_CAPACITY}",
        "-D",
        f"MROS2_RTPS_HEARTBEAT_PERIOD_MS={variant['heartbeat_ms']}",
        "-D",
        f"MROS2_QOS_RESOURCE_MAX_SAMPLES={RESOURCE_MAX_SAMPLES}",
        "-D",
        f"MROS2_QOS_RESOURCE_MAX_BYTES={RESOURCE_MAX_BYTES}",
        "build",
    ]
    environment = os.environ.copy()
    environment["SOURCE_DATE_EPOCH"] = str(source_date_epoch)
    print(f"[build] {variant['id']}")
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
    expected_cache = {
        "MROS2_QOS_HISTORY_DEPTH": str(variant["depth"]),
        "MROS2_RTPS_HISTORY_CAPACITY": str(HISTORY_CAPACITY),
        "MROS2_RTPS_HEARTBEAT_PERIOD_MS": str(variant["heartbeat_ms"]),
        "MROS2_QOS_RESOURCE_MAX_SAMPLES": str(RESOURCE_MAX_SAMPLES),
        "MROS2_QOS_RESOURCE_MAX_BYTES": str(RESOURCE_MAX_BYTES),
    }
    observed_cache = {key: cache.get(key) for key in expected_cache}
    if observed_cache != expected_cache:
        raise SystemExit(
            f"CMake cache mismatch for {variant['id']}: {observed_cache}"
        )
    definitions = compile_definition_evidence(
        build_dir / "compile_commands.json",
        variant,
    )

    artifact_dir = output_dir / "artifacts"
    sources = {
        "firmware": build_dir / "qos_eval.bin",
        "bootloader": build_dir / "bootloader/bootloader.bin",
        "partition_table": build_dir / "partition_table/partition-table.bin",
        "elf": build_dir / "qos_eval.elf",
        "linker_map": build_dir / "qos_eval.map",
        "sdkconfig": build_dir / "sdkconfig",
    }
    artifacts = {
        role: archive_file(
            source,
            artifact_dir,
            f"{variant['id']}_{role}",
            manifest_root=output_dir,
        )
        for role, source in sources.items()
    }
    log_path.chmod(0o444)
    artifacts["build_log"] = {
        "path": str(log_path.relative_to(output_dir)),
        "source_path": str(log_path.resolve()),
        "sha256": sha256_file(log_path),
        "bytes": log_path.stat().st_size,
    }
    project_description = json.loads(
        (build_dir / "project_description.json").read_text(encoding="utf-8")
    )
    manifest = {
        "schema_version": 1,
        "classification": "round6_preregistered_firmware_build",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "variant": variant,
        "source_commit": source_commit,
        "source_date_epoch": source_date_epoch,
        "app_version": project_description.get("project_version"),
        "reproducible_build": True,
        "parameters": {
            "MROS2_QOS_HISTORY_DEPTH": variant["depth"],
            "MROS2_RTPS_HISTORY_CAPACITY": HISTORY_CAPACITY,
            "MROS2_RTPS_HEARTBEAT_PERIOD_MS": variant["heartbeat_ms"],
            "MROS2_QOS_RESOURCE_MAX_SAMPLES": RESOURCE_MAX_SAMPLES,
            "MROS2_QOS_RESOURCE_MAX_BYTES": RESOURCE_MAX_BYTES,
        },
        "cmake_cache": observed_cache,
        "compile_definitions": definitions,
        "build_command": command,
        "artifacts": artifacts,
        "smoke_gate": {"required_runs": 3, "accepted_runs": 0, "status": "PENDING"},
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"[archive] {variant['id']} {artifacts['firmware']['sha256']}")
    return manifest


def verify_reproducible_sentinel(
    workspace,
    build_root,
    output_dir,
    source_date_epoch,
    reference_manifest,
):
    variant = reference_manifest["variant"]
    check_dir = build_root / f"build_round6_reprocheck_{variant['id']}"
    check_output = output_dir / "reproducibility_check"
    check_output.mkdir(parents=True, exist_ok=True)
    log_path = check_output / "build.log"
    if log_path.exists():
        log_path.chmod(0o644)
    command = [
        "idf.py",
        "-B",
        str(check_dir),
        "-D",
        f"MROS2_QOS_HISTORY_DEPTH={variant['depth']}",
        "-D",
        f"MROS2_RTPS_HISTORY_CAPACITY={HISTORY_CAPACITY}",
        "-D",
        f"MROS2_RTPS_HEARTBEAT_PERIOD_MS={variant['heartbeat_ms']}",
        "-D",
        f"MROS2_QOS_RESOURCE_MAX_SAMPLES={RESOURCE_MAX_SAMPLES}",
        "-D",
        f"MROS2_QOS_RESOURCE_MAX_BYTES={RESOURCE_MAX_BYTES}",
        "build",
    ]
    environment = os.environ.copy()
    environment["SOURCE_DATE_EPOCH"] = str(source_date_epoch)
    print(f"[reproducibility] rebuilding {variant['id']} independently")
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
    candidates = {
        "firmware": check_dir / "qos_eval.bin",
        "bootloader": check_dir / "bootloader/bootloader.bin",
        "partition_table": check_dir / "partition_table/partition-table.bin",
    }
    observed = {role: sha256_file(path) for role, path in candidates.items()}
    expected = {
        role: reference_manifest["artifacts"][role]["sha256"]
        for role in candidates
    }
    result = "PASS" if observed == expected else "FAIL"
    payload = {
        "schema_version": 1,
        "variant": variant,
        "source_date_epoch": source_date_epoch,
        "result": result,
        "expected_sha256": expected,
        "observed_sha256": observed,
        "build_command": command,
        "build_log_sha256": sha256_file(log_path),
    }
    (check_output / "manifest.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    log_path.chmod(0o444)
    if result != "PASS":
        raise SystemExit(
            f"reproducibility check failed for {variant['id']}: "
            f"expected {expected}, observed {observed}"
        )
    print(f"[reproducibility] {variant['id']} SHA match PASS")
    return payload


def parse_args():
    project_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=project_root)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--build-root", type=Path)
    parser.add_argument("--seed", type=int, default=RANDOMIZATION_SEED)
    return parser.parse_args()


def main():
    args = parse_args()
    project_root = args.project_root.resolve()
    workspace = project_root / "workspace/qos_eval"
    build_root = (args.build_root or workspace).resolve()
    output_dir = args.output_dir.resolve()
    if not shutil.which("idf.py"):
        raise SystemExit("idf.py is unavailable; source the ESP-IDF environment")
    ensure_clean_source(project_root)
    source_commit = git_output(project_root, "rev-parse", "HEAD")
    source_date_epoch = int(
        git_output(project_root, "show", "-s", "--format=%ct", source_commit)
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    schedule_paths = write_schedule(output_dir, args.seed)

    built = [
        build_variant(
            project_root,
            workspace,
            build_root,
            output_dir,
            source_commit,
            source_date_epoch,
            variant,
        )
        for variant in variants()
    ]
    reproducibility = verify_reproducible_sentinel(
        workspace,
        build_root,
        output_dir,
        source_date_epoch,
        built[0],
    )
    master = {
        "schema_version": 1,
        "classification": "round6_preregistered_firmware_set",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": source_commit,
        "source_date_epoch": source_date_epoch,
        "randomization_seed": args.seed,
        "reproducibility_check": reproducibility,
        "schedule": {
            path.name: sha256_file(path)
            for path in schedule_paths
        },
        "variants": [
            {
                "id": item["variant"]["id"],
                "depth": item["variant"]["depth"],
                "heartbeat_ms": item["variant"]["heartbeat_ms"],
                "firmware": item["artifacts"]["firmware"],
            }
            for item in built
        ],
    }
    master_path = output_dir / "manifest.json"
    master_path.write_text(
        json.dumps(master, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"[complete] {len(built)} variants: {master_path}")


if __name__ == "__main__":
    main()
