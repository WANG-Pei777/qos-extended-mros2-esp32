#!/usr/bin/env python3
"""Build and freeze the deterministic Seven-QoS mechanism protocol."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any

from run_seven_qos_mechanism_hardware_case import (
    HOST_PROBE,
    HOST_PROFILE,
    WORKSPACE,
    canonical_sha256,
    idf_shell,
    load_frozen_bundle,
    run_logged,
    sha256,
    write_json,
)
from seven_qos_mechanism_hardware_cases import HARDWARE_CASES, get_case
from seven_qos_mechanism_oracles import UNIT_ORACLES


REPO = Path(__file__).resolve().parents[2]
SOURCE_PROTOCOL = (
    REPO / "results/protocols/20260717_seven_qos_deterministic_expanded_draft"
)
SOURCE_CASES = REPO / "docs/benchmark/seven_qos_deterministic_cases_draft.json"
STATIC_GATE = REPO / "scripts/test/qos_static_checks.sh"
STATIC_BINARY_DIR = REPO / "build/qos_static_checks"
PREFREEZE_VERIFICATIONS = (
    (
        "frozen_flash_mode_smoke",
        "results/audits/20260720_seven_qos_frozen_flash_mode_prefreeze_smoke/release_verification.json",
    ),
    (
        "v1_protocol",
        "results/audits/20260720_seven_qos_mechanism_formal_protocol/release_verification.json",
    ),
    (
        "v1_failed_campaign",
        "results/audits/20260720_seven_qos_mechanism_formal_campaign_failed_release/release_verification.json",
    ),
    (
        "v1_failed_audit",
        "results/audits/20260720_seven_qos_mechanism_formal_campaign_failed_audit_release/release_verification.json",
    ),
    (
        "volatile_late_fix_smoke",
        "results/audits/20260720_seven_qos_volatile_late_fix_smoke/release_verification.json",
    ),
    (
        "transient_local_regression_smoke",
        "results/audits/20260720_seven_qos_transient_local_regression_smoke/release_verification.json",
    ),
    (
        "history_pbuf_ack_fix_smoke",
        "results/audits/20260720_seven_qos_history_pbuf_ack_fix_smoke/release_verification.json",
    ),
    (
        "resource_ack_recovery_fix_smoke",
        "results/audits/20260720_seven_qos_resource_ack_recovery_fix_smoke/release_verification.json",
    ),
)
SOURCE_PATHS = (
    "scripts/experiment/freeze_seven_qos_mechanism_protocol.py",
    "scripts/experiment/validate_seven_qos_mechanism_frozen.py",
    "scripts/experiment/run_seven_qos_mechanism_campaign.py",
    "scripts/experiment/audit_seven_qos_mechanism_campaign.py",
    "scripts/experiment/analyze_seven_qos_mechanism_campaign.py",
    "scripts/experiment/run_seven_qos_mechanism_hardware_case.py",
    "scripts/experiment/run_seven_qos_mechanism_unit_case.py",
    "scripts/experiment/seven_qos_mechanism_hardware_cases.py",
    "scripts/experiment/seven_qos_mechanism_oracles.py",
    "scripts/experiment/validate_seven_qos_mechanism_board_log.py",
    "scripts/experiment/capture_benchmark_telemetry_smoke.py",
    "scripts/test/qos_static_checks.sh",
    "docs/benchmark/SEVEN_QOS_MECHANISM_PROTOCOL_AMENDMENT_01.md",
    "tools/echo_cpp/src/qos_compatibility_probe.cpp",
    "tools/echo_cpp/config/seven_qos_esp32_initial_peer.xml",
    "workspace/seven_qos_mechanisms/CMakeLists.txt",
    "workspace/seven_qos_mechanisms/main/CMakeLists.txt",
    "workspace/seven_qos_mechanisms/main/app.cpp",
    "workspace/seven_qos_mechanisms/sdkconfig.defaults",
    "components/mros2-esp32/CMakeLists.txt",
    "mros2/include/mros2.h",
    "mros2/src/mros2.cpp",
    "mros2/embeddedRTPS/include/rtps/entities/FragmentationCapability.h",
    "mros2/embeddedRTPS/include/rtps/entities/DurabilityState.h",
    "mros2/embeddedRTPS/include/rtps/entities/Lifespan.h",
    "mros2/embeddedRTPS/include/rtps/entities/LivelinessState.h",
    "mros2/embeddedRTPS/include/rtps/entities/QosTime.h",
    "mros2/embeddedRTPS/include/rtps/entities/ReaderProxy.h",
    "mros2/embeddedRTPS/include/rtps/entities/ReaderSequence.h",
    "mros2/embeddedRTPS/include/rtps/entities/ReliabilityState.h",
    "mros2/embeddedRTPS/include/rtps/entities/ResourceLimits.h",
    "mros2/embeddedRTPS/include/rtps/storages/SimpleHistoryCache.h",
    "mros2/embeddedRTPS/include/rtps/entities/StatefulReader.h",
    "mros2/embeddedRTPS/include/rtps/entities/StatefulReader.tpp",
    "mros2/embeddedRTPS/include/rtps/entities/StatefulWriter.h",
    "mros2/embeddedRTPS/include/rtps/entities/StatefulWriter.tpp",
    "mros2/embeddedRTPS/include/rtps/entities/Writer.h",
    "platform/rtps/config.h",
    "platform/templates.hpp",
    "tests/test_fragmentation_capability.cpp",
    "tests/test_lifespan.cpp",
    "tests/test_liveliness_state.cpp",
    "tests/test_qos_time.cpp",
    "tests/test_reader_sequence.cpp",
    "tests/test_reliability_state.cpp",
    "tests/test_resource_limits.cpp",
    "tests/test_simple_history_cache.cpp",
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def load_claims(source_protocol: Path) -> list[dict[str, str]]:
    design = json.loads(
        (source_protocol / "design_manifest.json").read_text(encoding="utf-8")
    )
    schedule = source_protocol / "schedule.csv"
    if design.get("status") != "DRAFT_EXPANDED_NO_DATA":
        raise ValueError("source protocol is not the expanded no-data draft")
    if sha256(schedule) != design.get("schedule_sha256"):
        raise ValueError("expanded schedule hash mismatch")
    claims = [row for row in read_csv(schedule) if row["case_type"] == "mechanism"]
    if len(claims) != 36 or len({row["case_id"] for row in claims}) != 36:
        raise ValueError("expected 36 unique mechanism claims")
    if [int(row["ordinal"]) for row in claims] != list(range(49, 85)):
        raise ValueError("mechanism claim ordinals must be 49..84")
    return claims


def build_arguments(config: dict[str, Any], build_dir: str) -> list[str]:
    return [
        "-B", build_dir,
        f"-DMROS2_MECHANISM_CASE_ID={config['case_id']}",
        f"-DMROS2_MECHANISM_KIND={config['kind']}",
        f"-DMROS2_MECHANISM_PAYLOAD_BYTES={config['payload']}",
        f"-DMROS2_MECHANISM_TIMEOUT_MS={config['timeout_ms']}",
        f"-DMROS2_RTPS_HISTORY_CAPACITY={config['capacity']}",
        "-DMROS2_RTPS_HEARTBEAT_PERIOD_MS=100",
        "-DMROS2_QOS_MONITOR_PERIOD_MS=5",
        "-DCCACHE_ENABLE=0",
        "build",
    ]


def parse_flash_spec(build_dir: Path) -> dict[str, Any]:
    source = json.loads(
        (build_dir / "flasher_args.json").read_text(encoding="utf-8")
    )
    extra = source["extra_esptool_args"]
    files = [
        {"offset": offset, "relative_path": relative}
        for offset, relative in sorted(
            source["flash_files"].items(), key=lambda item: int(item[0], 16)
        )
    ]
    return {
        "chip": extra["chip"],
        "before": extra["before"],
        "after": extra["after"],
        "baud": 460800,
        "write_flash_args": source["write_flash_args"],
        "flash_files": files,
    }


def freeze_bundle(
    config: dict[str, Any], build_dir: Path, bundle_dir: Path
) -> dict[str, Any]:
    flash = parse_flash_spec(build_dir)
    bundle_dir.mkdir(parents=True)
    inventory: dict[str, dict[str, Any]] = {}
    for item in flash["flash_files"]:
        relative = item["relative_path"]
        source = build_dir / relative
        target = bundle_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        inventory[relative] = {
            "bytes": target.stat().st_size,
            "sha256": sha256(target),
        }
    extras = {
        "firmware.elf": build_dir / "seven_qos_mechanisms.elf",
        "firmware.map": build_dir / "seven_qos_mechanisms.map",
        "sdkconfig": WORKSPACE / "sdkconfig",
        "app.cpp": WORKSPACE / "main/app.cpp",
    }
    for relative, source in extras.items():
        target = bundle_dir / relative
        shutil.copy2(source, target)
        inventory[relative] = {
            "bytes": target.stat().st_size,
            "sha256": sha256(target),
        }
    shutil.copy2(
        build_dir / "flasher_args.json", bundle_dir / "flasher_args.json"
    )
    inventory["flasher_args.json"] = {
        "bytes": (bundle_dir / "flasher_args.json").stat().st_size,
        "sha256": sha256(bundle_dir / "flasher_args.json"),
    }
    app_relative = next(
        item["relative_path"] for item in flash["flash_files"]
        if item["offset"].lower() == "0x10000"
    )
    manifest = {
        "schema_version": 1,
        "classification": "seven_qos_mechanism_frozen_flash_bundle",
        "case_id": config["case_id"],
        "case_config_sha256": canonical_sha256(config),
        "app_relative_path": app_relative,
        "app_sha256": inventory[app_relative]["sha256"],
        "elf_relative_path": "firmware.elf",
        "map_relative_path": "firmware.map",
        "flash": flash,
        "files": inventory,
    }
    write_json(bundle_dir / "artifact_manifest.json", manifest)
    return manifest


def command_text(command: list[str]) -> str:
    completed = subprocess.run(
        command, check=False, capture_output=True, text=True
    )
    return (completed.stdout + completed.stderr).strip()


def capture_environment(
    root: Path, interface: str, board_ip: str, serial_by_id: str
) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    commands = {
        "wsl_interface.json": ["ip", "-j", "address", "show", "dev", interface],
        "wsl_board_route.json": ["ip", "-j", "route", "get", board_ip],
        "board_neighbor.txt": ["ip", "neigh", "show", board_ip],
        "qdisc.txt": ["tc", "qdisc", "show", "dev", interface],
        "uname.txt": ["uname", "-a"],
        "usb_uart_identity.txt": ["ls", "-l", "/dev/serial/by-id"],
        "windows_wlan_interfaces.txt": [
            "powershell.exe", "-NoProfile", "-Command", "netsh wlan show interfaces"
        ],
    }
    for name, command in commands.items():
        text = command_text(command)
        if not text:
            raise RuntimeError(f"empty environment command output: {name}")
        (root / name).write_text(text + "\n", encoding="utf-8")
    serial = Path(serial_by_id)
    if not serial.exists():
        raise RuntimeError(f"frozen serial identity is absent: {serial}")
    resolved = str(serial.resolve())
    (root / "serial_resolved.txt").write_text(resolved + "\n", encoding="ascii")
    qdisc = (root / "qdisc.txt").read_text(encoding="utf-8").strip()
    if any(token in qdisc for token in ("netem", "ingress", "clsact")):
        raise RuntimeError("environment snapshot contains an impairment qdisc")
    return {
        "serial_by_id": serial_by_id,
        "serial_resolved": resolved,
        "interface": interface,
        "board_ip": board_ip,
        "qdisc_sha256": canonical_sha256(qdisc),
        "files": {
            str(path.relative_to(root)): sha256(path)
            for path in sorted(root.iterdir()) if path.is_file()
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-protocol", type=Path, default=SOURCE_PROTOCOL)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume-staging", action="store_true")
    parser.add_argument("--max-new-bundles", type=int)
    parser.add_argument("--build-dir", default="build_mechanism_protocol_freeze")
    parser.add_argument("--host-probe", type=Path, default=HOST_PROBE)
    parser.add_argument("--profile", type=Path, default=HOST_PROFILE)
    parser.add_argument(
        "--serial-by-id",
        default=(
            "/dev/serial/by-id/usb-Silicon_Labs_CP2102N_USB_to_UART_"
            "Bridge_Controller_6a7f12ba5718ec11be2a4a103803ea95-if00-port0"
        ),
    )
    parser.add_argument("--interface", default="eth1")
    parser.add_argument("--host-ip", default="192.0.2.2")
    parser.add_argument("--host-mac", default="e0:d4:e8:37:50:a0")
    parser.add_argument("--board-ip", default="192.0.2.1")
    parser.add_argument("--board-mac", default="7c:df:a1:e2:19:74")
    parser.add_argument("--ap-ssid", default="abc")
    parser.add_argument("--ap-bssid", default="42:6d:be:8c:dd:1d")
    args = parser.parse_args()
    if args.max_new_bundles is not None and args.max_new_bundles < 1:
        parser.error("--max-new-bundles must be positive")

    output = args.output if args.output.is_absolute() else REPO / args.output
    output = output.resolve()
    staging = output.with_name(output.name + ".staging")
    if output.exists():
        parser.error(f"output already exists: {output}")
    if staging.exists() != args.resume_staging:
        if staging.exists():
            parser.error("staging exists; use --resume-staging")
        parser.error("--resume-staging requires an existing staging tree")

    source_protocol = args.source_protocol.resolve()
    claims = load_claims(source_protocol)
    claim_by_id = {row["case_id"]: row for row in claims}
    if set(HARDWARE_CASES) != {
        row["case_id"] for row in claims if row["level"] in {"hardware", "unit_and_hardware"}
    }:
        raise SystemExit("hardware registry does not exactly cover claim schedule")
    if set(UNIT_ORACLES) != {
        row["case_id"] for row in claims if row["level"] in {"unit", "unit_and_hardware"}
    }:
        raise SystemExit("unit registry does not exactly cover claim schedule")
    for relative in SOURCE_PATHS:
        if not (REPO / relative).is_file():
            raise SystemExit(f"missing bound source: {relative}")
    prefreeze_evidence = []
    for label, relative in PREFREEZE_VERIFICATIONS:
        path = REPO / relative
        verification = json.loads(path.read_text(encoding="utf-8"))
        if verification.get("status") != "PASS":
            raise SystemExit(f"prefreeze release is not verified: {label}")
        prefreeze_evidence.append({
            "label": label,
            "verification_path": relative,
            "verification_sha256": sha256(path),
            "tree_sha256": verification["tree_sha256"],
            "file_manifest_sha256": verification["file_manifest_sha256"],
        })

    if not args.resume_staging:
        staging.mkdir(parents=True)
        for relative in (
            "artifacts/cases", "artifacts/host", "artifacts/unit/bin",
            "artifacts/source", "artifacts/environment", "build_logs", "source",
        ):
            (staging / relative).mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_protocol / "schedule.csv", staging / "source/expanded_schedule.csv")
        shutil.copy2(source_protocol / "design_manifest.json", staging / "source/expanded_design_manifest.json")
        shutil.copy2(SOURCE_CASES, staging / "source/deterministic_cases.json")
        write_json(
            staging / "source/bound_source_hashes.json",
            {relative: sha256(REPO / relative) for relative in SOURCE_PATHS},
        )

        run_logged(["bash", str(STATIC_GATE)], staging / "build_logs/unit_static_gate.log")
        for binary in sorted({oracle["binary"] for oracle in UNIT_ORACLES.values()}):
            shutil.copy2(STATIC_BINARY_DIR / binary, staging / "artifacts/unit/bin" / binary)
        assertion_sources = {
            assertion["path"] for oracle in UNIT_ORACLES.values()
            for assertion in oracle["source_assertions"]
        }
        for relative in sorted(assertion_sources):
            target = staging / "artifacts/source" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / relative, target)
        shutil.copy2(args.host_probe.resolve(), staging / "artifacts/host/qos_compatibility_probe")
        shutil.copy2(args.profile.resolve(), staging / "artifacts/host/initial_peer.xml")
        ldd = command_text(["ldd", str(args.host_probe.resolve())])
        (staging / "artifacts/host/ldd.txt").write_text(ldd + "\n", encoding="utf-8")
        capture_environment(
            staging / "artifacts/environment", args.interface,
            args.board_ip, args.serial_by_id,
        )
    else:
        frozen_hashes = json.loads(
            (staging / "source/bound_source_hashes.json").read_text(encoding="utf-8")
        )
        current_hashes = {relative: sha256(REPO / relative) for relative in SOURCE_PATHS}
        if frozen_hashes != current_hashes:
            raise SystemExit("bound source drift while resuming protocol staging")
        if sha256(args.host_probe.resolve()) != sha256(
            staging / "artifacts/host/qos_compatibility_probe"
        ):
            raise SystemExit("host probe drift while resuming protocol staging")
        if sha256(args.profile.resolve()) != sha256(
            staging / "artifacts/host/initial_peer.xml"
        ):
            raise SystemExit("host profile drift while resuming protocol staging")

    build_dir = WORKSPACE / args.build_dir
    hardware_rows: list[dict[str, Any]] = []
    new_bundles = 0
    for index, case_id in enumerate(HARDWARE_CASES, start=1):
        config = get_case(case_id)
        bundle_relative = f"artifacts/cases/{index:03d}_{case_id}"
        bundle_dir = staging / bundle_relative
        if bundle_dir.exists():
            manifest = load_frozen_bundle(bundle_dir, config)
            print(f"REUSE {index}/32 {case_id}", flush=True)
        else:
            if (
                args.max_new_bundles is not None
                and new_bundles >= args.max_new_bundles
            ):
                print(
                    f"PAUSED: built_new={new_bundles} next={index}/32 {case_id} "
                    f"staging={staging}",
                    flush=True,
                )
                return 0
            print(f"BUILD {index}/32 {case_id}", flush=True)
            run_logged(
                idf_shell(build_arguments(config, args.build_dir)),
                staging / "build_logs" / f"{index:03d}_{case_id}.log",
            )
            manifest = freeze_bundle(config, build_dir, bundle_dir)
            new_bundles += 1
        claim = claim_by_id[case_id]
        hardware_rows.append({
            "ordinal": index,
            "claim_ordinal": int(claim["ordinal"]) - 48,
            "case_id": case_id,
            "policy": claim["policy"],
            "level": claim["level"],
            "kind": config["kind"],
            "case_config_json": json.dumps(config, sort_keys=True, separators=(",", ":")),
            "case_config_sha256": canonical_sha256(config),
            "bundle_relative_path": bundle_relative,
            "artifact_manifest_sha256": sha256(bundle_dir / "artifact_manifest.json"),
            "firmware_sha256": manifest["app_sha256"],
        })

    claim_rows = [
        {"claim_ordinal": index, **row}
        for index, row in enumerate(claims, start=1)
    ]
    unit_rows: list[dict[str, Any]] = []
    for index, case_id in enumerate(UNIT_ORACLES, start=1):
        oracle = UNIT_ORACLES[case_id]
        binary = staging / "artifacts/unit/bin" / oracle["binary"]
        claim = claim_by_id[case_id]
        unit_rows.append({
            "ordinal": index,
            "claim_ordinal": int(claim["ordinal"]) - 48,
            "case_id": case_id,
            "policy": claim["policy"],
            "level": claim["level"],
            "binary": oracle["binary"],
            "binary_sha256": sha256(binary),
            "oracle_sha256": canonical_sha256(oracle),
        })
    write_csv(staging / "claims.csv", claim_rows)
    write_csv(staging / "unit_schedule.csv", unit_rows)
    write_csv(staging / "hardware_schedule.csv", hardware_rows)

    environment = capture_environment(
        staging / "artifacts/environment", args.interface,
        args.board_ip, args.serial_by_id,
    )
    wlan = (staging / "artifacts/environment/windows_wlan_interfaces.txt").read_text(
        encoding="utf-8"
    ).lower()
    if args.ap_ssid.lower() not in wlan or args.ap_bssid.lower() not in wlan:
        raise SystemExit("current AP identity differs from the requested freeze gate")
    interface_data = json.loads(
        (staging / "artifacts/environment/wsl_interface.json").read_text(encoding="utf-8")
    )[0]
    ipv4 = {item["local"] for item in interface_data["addr_info"] if item["family"] == "inet"}
    if interface_data["address"].lower() != args.host_mac.lower() or args.host_ip not in ipv4:
        raise SystemExit("host interface identity differs from the freeze gate")
    neighbor = (staging / "artifacts/environment/board_neighbor.txt").read_text(encoding="utf-8").lower()
    if args.board_mac.lower() not in neighbor:
        raise SystemExit("board neighbor identity differs from the freeze gate")

    frozen_host = staging / "artifacts/host/qos_compatibility_probe"
    frozen_profile = staging / "artifacts/host/initial_peer.xml"
    design = {
        "schema_version": 1,
        "classification": "seven_qos_mechanism_formal_preregistration",
        "status": "FROZEN_NO_DATA",
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "claim_count": 36,
        "unit_execution_count": 27,
        "hardware_execution_count": 32,
        "policy_counts": dict(sorted(Counter(row["policy"] for row in claims).items())),
        "claims_sha256": sha256(staging / "claims.csv"),
        "unit_schedule_sha256": sha256(staging / "unit_schedule.csv"),
        "hardware_schedule_sha256": sha256(staging / "hardware_schedule.csv"),
        "source_expanded_schedule_sha256": sha256(source_protocol / "schedule.csv"),
        "source_deterministic_cases_sha256": sha256(SOURCE_CASES),
        "execution": {
            "order": "unit schedule followed by hardware schedule, each in canonical claim order",
            "randomization": "none; deterministic assertions are not pooled performance observations",
            "maximum_attempts_per_case": 3,
            "formal_runner_requires_frozen_binaries": True,
            "retry_policy": "retain every attempt; retry only nonfatal execution failures",
            "amendment_policy": "any bound-file change requires a new protocol directory and new campaign",
        },
        "hardware_and_network_gate": {
            **environment,
            "host_ip": args.host_ip,
            "host_mac": args.host_mac,
            "board_mac": args.board_mac,
            "ap_ssid": args.ap_ssid,
            "ap_bssid": args.ap_bssid,
        },
        "host_artifacts": {
            "probe_relative_path": "artifacts/host/qos_compatibility_probe",
            "probe_sha256": sha256(frozen_host),
            "profile_relative_path": "artifacts/host/initial_peer.xml",
            "profile_sha256": sha256(frozen_profile),
            "ldd_sha256": sha256(staging / "artifacts/host/ldd.txt"),
        },
        "unit_artifacts": {
            "binary_root": "artifacts/unit/bin",
            "source_root": "artifacts/source",
            "binary_hashes": {
                path.name: sha256(path)
                for path in sorted((staging / "artifacts/unit/bin").iterdir())
                if path.is_file()
            },
            "source_hashes": {
                str(path.relative_to(staging / "artifacts/source")): sha256(path)
                for path in sorted((staging / "artifacts/source").rglob("*"))
                if path.is_file()
            },
        },
        "bound_source_files": {relative: sha256(REPO / relative) for relative in SOURCE_PATHS},
        "excluded_prefreeze_evidence": {
            "statement": "no prefreeze smoke observation is accepted as formal evidence",
            "releases": prefreeze_evidence,
        },
        "amendment": {
            "identifier": "SEVEN_QOS_MECHANISM_PROTOCOL_AMENDMENT_01",
            "relative_path": "docs/benchmark/SEVEN_QOS_MECHANISM_PROTOCOL_AMENDMENT_01.md",
            "sha256": sha256(REPO / "docs/benchmark/SEVEN_QOS_MECHANISM_PROTOCOL_AMENDMENT_01.md"),
            "reason": "v1 exposed deterministic Volatile late-reader history replay",
            "claim_schedule_changed": False,
            "oracle_changed": False,
        },
        "evidence_boundary": "deterministic Seven-QoS mechanism evidence only; no latency, loss, energy, or resource observations are pooled as performance samples",
    }
    write_json(staging / "design_manifest.json", design)
    staging.replace(output)
    print(
        f"PASS: claims=36 unit=27 hardware=32 "
        f"hardware_schedule_sha256={design['hardware_schedule_sha256']} output={output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
