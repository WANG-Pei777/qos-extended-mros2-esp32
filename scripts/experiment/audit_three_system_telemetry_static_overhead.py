#!/usr/bin/env python3
"""Audit the sealed inputs for the three-system telemetry overhead gate."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shlex
import subprocess
import sys
from pathlib import Path


SYSTEMS = ("mros2qos", "upstream", "microros")
MODES = ("off", "on")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_nm(compile_commands: Path) -> Path:
    commands = json.loads(compile_commands.read_text(encoding="utf-8"))
    if not commands:
        raise ValueError(f"{compile_commands}: no compile commands")
    compiler = Path(shlex.split(commands[0]["command"])[0])
    for suffix in ("-gcc", "-g++"):
        if compiler.name.endswith(suffix):
            candidate = compiler.with_name(compiler.name[: -len(suffix)] + "-nm")
            if candidate.is_file():
                return candidate
    raise ValueError(f"cannot derive nm from {compiler}")


def telemetry_symbol_count(nm: Path, elf: Path) -> int:
    output = subprocess.run(
        [str(nm), "-C", "--defined-only", str(elf)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return len(
        {
            line.split(maxsplit=2)[-1]
            for line in output.splitlines()
            if "benchmark_telemetry_" in line
        }
    )


def run_validator(command: list[str]) -> None:
    subprocess.run(command, check=True, capture_output=True, text=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("result_root", type=Path)
    args = parser.parse_args()
    root = args.result_root.resolve()
    repo = Path(__file__).resolve().parents[2]

    errors: list[str] = []
    accepted = read_csv(root / "accepted_smoke_manifest.csv")
    accepted_keys = [(row["system"], row["mode"]) for row in accepted]
    expected_keys = [(system, mode) for system in SYSTEMS for mode in MODES]
    if sorted(accepted_keys) != sorted(expected_keys):
        errors.append(f"accepted grain mismatch: {accepted_keys}")
    if len(set(accepted_keys)) != len(accepted_keys):
        errors.append("accepted manifest contains duplicate system/mode keys")

    summary_rows = {
        row["system"]: row for row in read_csv(root / "static_overhead_summary.csv")
    }
    smoke_rows = {
        (row["system"], row["mode"]): row
        for row in read_csv(root / "exact_binary_smoke_summary.csv")
    }

    for row in accepted:
        system = row["system"]
        mode = row["mode"]
        artifact = root / system / mode
        smoke = root / row["relative_path"]
        firmware = artifact / "firmware.bin"
        actual_hash = sha256(firmware)
        if actual_hash != row["firmware_sha256"]:
            errors.append(f"{system}/{mode}: manifest firmware hash mismatch")
        recorded_hash = (smoke / "firmware.bin.sha256").read_text(
            encoding="utf-8"
        ).split()[0]
        if recorded_hash != actual_hash:
            errors.append(f"{system}/{mode}: smoke firmware hash mismatch")

        smoke_row = smoke_rows.get((system, mode))
        if smoke_row is None or smoke_row["accepted"] != "true":
            errors.append(f"{system}/{mode}: missing accepted smoke summary row")
        elif smoke_row["firmware_sha256"] != actual_hash:
            errors.append(f"{system}/{mode}: smoke summary hash mismatch")

        try:
            nm = find_nm(artifact / "compile_commands.json")
            symbols = telemetry_symbol_count(nm, artifact / "firmware.elf")
        except (OSError, ValueError, subprocess.CalledProcessError) as exc:
            errors.append(f"{system}/{mode}: symbol audit failed: {exc}")
            symbols = -1
        expected_symbols = int(
            summary_rows[system][f"{mode}_telemetry_defined_symbols"]
        )
        if symbols != expected_symbols:
            errors.append(
                f"{system}/{mode}: telemetry symbols {symbols} != {expected_symbols}"
            )
        if mode == "off" and symbols != 0:
            errors.append(f"{system}/off: telemetry symbols are linked")
        if mode == "on" and symbols <= 0:
            errors.append(f"{system}/on: telemetry symbols are absent")

        try:
            if mode == "off":
                run_validator(
                    [
                        sys.executable,
                        str(repo / "scripts/experiment/validate_telemetry_off_smoke.py"),
                        str(smoke / "serial.raw"),
                        "--system",
                        system,
                    ]
                )
            else:
                run_validator(
                    [
                        sys.executable,
                        str(
                            repo
                            / "scripts/experiment/validate_benchmark_telemetry_smoke.py"
                        ),
                        str(smoke / "serial.raw"),
                    ]
                )
        except subprocess.CalledProcessError as exc:
            errors.append(f"{system}/{mode}: UART validator failed: {exc.stderr.strip()}")

    for system in SYSTEMS:
        row = summary_rows.get(system)
        if row is None:
            errors.append(f"{system}: missing static summary row")
            continue
        off_size = (root / system / "off/firmware.bin").stat().st_size
        on_size = (root / system / "on/firmware.bin").stat().st_size
        expected = {
            "firmware_bin_off_bytes": off_size,
            "firmware_bin_on_bytes": on_size,
            "firmware_bin_delta_bytes": on_size - off_size,
        }
        for key, value in expected.items():
            if int(row[key]) != value:
                errors.append(f"{system}: {key}={row[key]} != {value}")

        deltas = {
            item["metric"]: int(item["delta_bytes"])
            for item in read_csv(root / system / "size_delta.csv")
        }
        crosswalk = {
            "diram_data_delta_bytes": "diram_data",
            "diram_bss_delta_bytes": "diram_bss",
            "diram_text_delta_bytes": "diram_text",
            "used_diram_delta_bytes": "used_diram",
            "used_flash_non_ram_delta_bytes": "used_flash_non_ram",
            "total_size_delta_bytes": "total_size",
        }
        for summary_key, delta_key in crosswalk.items():
            if int(row[summary_key]) != deltas[delta_key]:
                errors.append(
                    f"{system}: {summary_key} disagrees with size_delta.csv"
                )

    rejected = read_csv(root / "rejected_attempt_ledger.csv")
    for row in rejected:
        attempt = root / row["relative_path"]
        records = list(attempt.glob("failure.txt")) + list(
            attempt.glob("disposition.txt")
        )
        if not attempt.is_dir() or len(records) != 1:
            errors.append(f"{row['relative_path']}: missing unique classification record")
    if {row["relative_path"] for row in rejected} & {
        row["relative_path"] for row in accepted
    }:
        errors.append("accepted and rejected paths overlap")

    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(
        "PASS: systems=3 accepted_smokes=6 rejected_attempts="
        f"{len(rejected)} hashes=6 UART_validators=6 static_summaries=3"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
