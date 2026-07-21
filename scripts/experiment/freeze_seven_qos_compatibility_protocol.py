#!/usr/bin/env python3
# flake8: noqa: E501
"""Build and freeze the 48-case Seven-QoS compatibility protocol."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from run_seven_qos_compatibility_case import (
    DEFAULT_HOST_PROBE,
    DEFAULT_PROFILE,
    WORKSPACE,
    cmake_duration,
    idf_command,
    load_frozen_bundle,
    resolve_case,
    run_logged,
    sha256,
)


REPO = Path(__file__).resolve().parents[2]
SOURCE_PROTOCOL = (
    REPO
    / "results/protocols/20260717_seven_qos_deterministic_expanded_draft"
)
SOURCE_PATHS = (
    "scripts/experiment/freeze_seven_qos_compatibility_protocol.py",
    "scripts/experiment/run_seven_qos_compatibility_case.py",
    "scripts/experiment/run_seven_qos_compatibility_campaign.py",
    "scripts/experiment/audit_seven_qos_compatibility_campaign.py",
    "scripts/experiment/validate_seven_qos_compatibility_frozen.py",
    "scripts/experiment/capture_benchmark_telemetry_smoke.py",
    "scripts/experiment/validate_qos_compatibility_host_probe.py",
    "scripts/experiment/validate_qos_compatibility_board_probe.py",
    "tools/echo_cpp/src/qos_compatibility_probe.cpp",
    "mros2/embeddedRTPS/src/discovery/SPDPAgent.cpp",
    "mros2/embeddedRTPS/src/discovery/SEDPAgent.cpp",
    "mros2/embeddedRTPS/src/discovery/TopicData.cpp",
    "mros2/embeddedRTPS/src/entities/Domain.cpp",
    "mros2/embeddedRTPS/include/rtps/discovery/TopicData.h",
    "mros2/embeddedRTPS/include/rtps/discovery/QoSCompatibility.h",
    "mros2/embeddedRTPS/include/rtps/entities/QosTime.h",
    "mros2/include/mros2.h",
    "mros2/src/mros2.cpp",
    "workspace/seven_qos_compatibility/CMakeLists.txt",
    "workspace/seven_qos_compatibility/main/CMakeLists.txt",
    "workspace/seven_qos_compatibility/main/app.cpp",
    "workspace/seven_qos_compatibility/sdkconfig",
)
SMOKE_VERIFICATIONS = (
    "results/audits/20260717_seven_qos_compatibility_smoke_release/"
    "release_verification.json",
    "results/audits/20260717_seven_qos_compatibility_family_smoke_release/"
    "release_verification.json",
    "results/audits/20260717_seven_qos_frozen_flash_mode_prefreeze_smoke/"
    "release_verification.json",
)
ENVIRONMENT_ROOT = (
    REPO
    / "results/diagnostics/"
    "20260717_seven_qos_compatibility_environment_gate"
)
ENVIRONMENT_VERIFICATION = (
    "results/audits/20260717_seven_qos_compatibility_environment_gate/"
    "release_verification.json"
)


def canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_source_rows(protocol: Path) -> tuple[dict, list[dict[str, str]]]:
    design_path = protocol / "design_manifest.json"
    schedule_path = protocol / "schedule.csv"
    design = json.loads(design_path.read_text(encoding="utf-8"))
    if design.get("status") != "DRAFT_EXPANDED_NO_DATA":
        raise ValueError("source protocol is not the expanded no-data draft")
    if sha256(schedule_path) != design.get("schedule_sha256"):
        raise ValueError("source schedule SHA-256 mismatch")
    with schedule_path.open(newline="", encoding="utf-8") as stream:
        rows = [
            row
            for row in csv.DictReader(stream)
            if row["case_type"] == "compatibility"
        ]
    if len(rows) != 48 or [int(row["ordinal"]) for row in rows] != list(
        range(1, 49)
    ):
        raise ValueError("expected canonical compatibility ordinals 1..48")
    if len({row["case_id"] for row in rows}) != 48:
        raise ValueError("compatibility case IDs are not unique")
    for row in rows:
        resolve_case(row)
    return design, rows


def build_arguments(row: dict[str, str]) -> list[str]:
    case = resolve_case(row)
    return [
        "-DMROS2_QOS_CASE_ID=" + case.case_id,
        "-DMROS2_QOS_BOARD_ROLE=" + case.board_role,
        "-DMROS2_QOS_RELIABILITY=" + case.board_qos.reliability,
        "-DMROS2_QOS_DURABILITY=" + case.board_qos.durability,
        "-DMROS2_QOS_DEADLINE_MS="
        + cmake_duration(case.board_qos.deadline_ms),
        "-DMROS2_QOS_LIVELINESS_LEASE_MS="
        + cmake_duration(case.board_qos.liveliness_lease_ms),
        "-DMROS2_QOS_EXPECTED_MATCH=" + str(int(case.expected_match)),
        "-DMROS2_QOS_WAIT_MS=20000",
        "-DMROS2_QOS_POST_MATCH_MS=5000",
        "-DMROS2_QOS_MESSAGE_COUNT=10",
        "-DMROS2_QOS_PERIOD_MS=100",
        "build",
    ]


def parse_flash_spec(build_dir: Path) -> dict:
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
    row: dict[str, str],
    build_dir: Path,
    bundle_dir: Path,
) -> dict:
    flash = parse_flash_spec(build_dir)
    bundle_dir.mkdir(parents=True)
    inventory = {}
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
    shutil.copy2(
        build_dir / "flasher_args.json", bundle_dir / "flasher_args.json"
    )
    inventory["flasher_args.json"] = {
        "bytes": (bundle_dir / "flasher_args.json").stat().st_size,
        "sha256": sha256(bundle_dir / "flasher_args.json"),
    }
    app_relative = next(
        item["relative_path"]
        for item in flash["flash_files"]
        if item["offset"].lower() == "0x10000"
    )
    manifest = {
        "schema_version": 1,
        "classification": "seven_qos_compatibility_frozen_flash_bundle",
        "case_id": row["case_id"],
        "schedule_row_sha256": canonical_sha256(row),
        "app_relative_path": app_relative,
        "app_sha256": inventory[app_relative]["sha256"],
        "flash": flash,
        "files": inventory,
    }
    write_json(bundle_dir / "artifact_manifest.json", manifest)
    return manifest


def command_output(command: list[str]) -> str:
    result = subprocess.run(
        command, check=False, capture_output=True, text=True
    )
    return (result.stdout + result.stderr).strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-protocol", type=Path, default=SOURCE_PROTOCOL)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--resume-staging",
        action="store_true",
        help="verify and reuse contiguous completed bundles in the staging tree",
    )
    parser.add_argument("--idf-export", type=Path, default=Path.home() / "esp-idf/export.sh")
    parser.add_argument("--build-dir", default="build_compatibility_protocol_freeze")
    parser.add_argument("--host-probe", type=Path, default=DEFAULT_HOST_PROBE)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--serial-by-id", default="/dev/serial/by-id/usb-Silicon_Labs_CP2102N_USB_to_UART_Bridge_Controller_6a7f12ba5718ec11be2a4a103803ea95-if00-port0")
    parser.add_argument("--board-chip", default="ESP32-S3 (QFN56) revision v0.1")
    parser.add_argument("--board-mac", default="7c:df:a1:e2:19:74")
    parser.add_argument("--board-ip", default="192.0.2.1")
    parser.add_argument("--interface", default="eth1")
    parser.add_argument("--host-ip", default="192.0.2.2")
    parser.add_argument("--host-mac", default="e0:d4:e8:37:50:a0")
    parser.add_argument("--ap-ssid", default="abc")
    parser.add_argument("--ap-bssid", default="42:6d:be:8c:dd:1d")
    args = parser.parse_args()

    source_protocol = args.source_protocol.resolve()
    output = args.output if args.output.is_absolute() else REPO / args.output
    output = output.resolve()
    staging = output.with_name(output.name + ".staging")
    if output.exists():
        parser.error(f"output already exists: {output}")
    if staging.exists() != args.resume_staging:
        if staging.exists():
            parser.error("staging exists; use --resume-staging")
        parser.error("--resume-staging requires an existing staging tree")
    source_design, source_rows = load_source_rows(source_protocol)
    for relative in (
        *SOURCE_PATHS,
        *SMOKE_VERIFICATIONS,
        ENVIRONMENT_VERIFICATION,
    ):
        if not (REPO / relative).is_file():
            raise SystemExit(f"missing freeze input: {relative}")
    wlan_text = (
        ENVIRONMENT_ROOT / "windows_wlan_interfaces.txt"
    ).read_text(encoding="utf-8-sig").lower()
    if args.ap_bssid.lower() not in wlan_text or args.ap_ssid.lower() not in wlan_text:
        raise SystemExit("AP identity does not match the environment snapshot")
    interface_data = json.loads(
        (ENVIRONMENT_ROOT / "wsl_interface.json").read_text(encoding="utf-8")
    )[0]
    interface_ipv4 = {
        item["local"]
        for item in interface_data["addr_info"]
        if item["family"] == "inet"
    }
    if (
        interface_data["ifname"] != args.interface
        or interface_data["address"].lower() != args.host_mac.lower()
        or args.host_ip not in interface_ipv4
    ):
        raise SystemExit("host interface identity does not match the snapshot")
    usb_text = (ENVIRONMENT_ROOT / "usb_uart_identity.txt").read_text()
    if Path(args.serial_by_id).name not in usb_text:
        raise SystemExit("USB-UART identity does not match the snapshot")
    board_text = (ENVIRONMENT_ROOT / "board_identity.txt").read_text().lower()
    if args.board_mac.lower() not in board_text:
        raise SystemExit("board MAC does not match the snapshot")

    host_probe = args.host_probe.resolve()
    profile = args.profile.resolve()
    frozen_host = staging / "artifacts/host/qos_compatibility_probe"
    frozen_profile = staging / "artifacts/host/initial_peer.xml"
    if not args.resume_staging:
        staging.mkdir(parents=True)
        (staging / "artifacts/cases").mkdir(parents=True)
        (staging / "artifacts/host").mkdir(parents=True)
        (staging / "build_logs").mkdir()
        (staging / "source").mkdir()
        shutil.copy2(
            source_protocol / "schedule.csv",
            staging / "source/expanded_schedule.csv",
        )
        shutil.copy2(
            source_protocol / "design_manifest.json",
            staging / "source/expanded_design_manifest.json",
        )
        shutil.copy2(host_probe, frozen_host)
        shutil.copy2(profile, frozen_profile)
        shutil.copytree(
            ENVIRONMENT_ROOT, staging / "artifacts/environment"
        )
    else:
        expected_copies = (
            (
                source_protocol / "schedule.csv",
                staging / "source/expanded_schedule.csv",
            ),
            (
                source_protocol / "design_manifest.json",
                staging / "source/expanded_design_manifest.json",
            ),
            (host_probe, frozen_host),
            (profile, frozen_profile),
        )
        for source, frozen in expected_copies:
            if not frozen.is_file() or sha256(source) != sha256(frozen):
                raise SystemExit(f"staging input drift: {frozen}")
        source_environment = {
            str(path.relative_to(ENVIRONMENT_ROOT)): sha256(path)
            for path in ENVIRONMENT_ROOT.rglob("*")
            if path.is_file()
        }
        frozen_environment_root = staging / "artifacts/environment"
        frozen_environment = {
            str(path.relative_to(frozen_environment_root)): sha256(path)
            for path in frozen_environment_root.rglob("*")
            if path.is_file()
        }
        if frozen_environment != source_environment:
            raise SystemExit("staging environment snapshot drift")

    build_dir = WORKSPACE / args.build_dir
    frozen_rows = []
    for index, row in enumerate(source_rows, start=1):
        bundle_relative = f"artifacts/cases/{index:03d}_{row['case_id']}"
        bundle_dir = staging / bundle_relative
        if bundle_dir.exists():
            bundle = load_frozen_bundle(bundle_dir, row["case_id"])
            if bundle.get("schedule_row_sha256") != canonical_sha256(row):
                raise SystemExit(f"staging schedule-row drift: {row['case_id']}")
            print(f"REUSE {index}/48 {row['case_id']}", flush=True)
        else:
            print(f"BUILD {index}/48 {row['case_id']}", flush=True)
            log = staging / "build_logs" / f"{index:03d}_{row['case_id']}.log"
            result = run_logged(
                idf_command(
                    args.idf_export,
                    WORKSPACE,
                    ["-B", args.build_dir, *build_arguments(row)],
                ),
                log,
            )
            if result != 0:
                write_json(
                    staging / "freeze_failure.json",
                    {"case_id": row["case_id"], "return_code": result},
                )
                raise SystemExit(
                    f"build failed for {row['case_id']}; retained {staging}"
                )
            bundle = freeze_bundle(row, build_dir, bundle_dir)
        frozen_rows.append(
            {
                **row,
                "artifact_manifest_relative_path": bundle_relative
                + "/artifact_manifest.json",
                "artifact_manifest_sha256": sha256(
                    staging / bundle_relative / "artifact_manifest.json"
                ),
                "firmware_sha256": bundle["app_sha256"],
            }
        )

    schedule_path = staging / "schedule.csv"
    with schedule_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(frozen_rows[0]))
        writer.writeheader()
        writer.writerows(frozen_rows)

    ldd = command_output(
        [
            "bash",
            "-lc",
            "source /opt/ros/humble/setup.bash && ldd "
            + str(host_probe),
        ]
    )
    (staging / "artifacts/host/ldd.txt").write_text(ldd + "\n", encoding="utf-8")
    smoke_evidence = []
    for relative in SMOKE_VERIFICATIONS:
        verification = json.loads((REPO / relative).read_text(encoding="utf-8"))
        if verification.get("status") != "PASS":
            raise SystemExit(f"smoke release is not verified: {relative}")
        smoke_evidence.append(
            {
                "verification_path": relative,
                "verification_sha256": sha256(REPO / relative),
                "tree_sha256": verification["tree_sha256"],
                "file_manifest_sha256": verification["file_manifest_sha256"],
            }
        )

    policy_counts = Counter(row["policy"] for row in frozen_rows)
    environment_verification = json.loads(
        (REPO / ENVIRONMENT_VERIFICATION).read_text(encoding="utf-8")
    )
    if environment_verification.get("status") != "PASS":
        raise SystemExit("environment snapshot release is not verified")
    environment_files = {
        str(path.relative_to(staging / "artifacts/environment")): sha256(path)
        for path in sorted((staging / "artifacts/environment").rglob("*"))
        if path.is_file()
    }
    design = {
        "schema_version": 1,
        "classification": "seven_qos_compatibility_formal_preregistration",
        "status": "FROZEN_NO_DATA",
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "total_scheduled_cases": len(frozen_rows),
        "schedule_sha256": sha256(schedule_path),
        "source_expanded_design_sha256": sha256(
            source_protocol / "design_manifest.json"
        ),
        "source_expanded_schedule_sha256": source_design["schedule_sha256"],
        "policy_counts": dict(sorted(policy_counts.items())),
        "direction_counts": dict(sorted(Counter(row["direction"] for row in frozen_rows).items())),
        "order_counts": dict(sorted(Counter(row["endpoint_creation_order"] for row in frozen_rows).items())),
        "expected_match_counts": dict(sorted(Counter(str(json.loads(row["expected_json"])["expected_match"]).lower() for row in frozen_rows).items())),
        "execution": {
            "order": "canonical schedule order",
            "randomization": "none; cases are deterministic assertions, not pooled performance observations",
            "maximum_attempts_per_case": 3,
            "retry_policy": "retain every attempt; retry nonfatal execution failures only; stop on crash, panic, watchdog, corruption, or attempt exhaustion",
            "board_wait_ms": 20000,
            "host_compatible_wait_ms": 50000,
            "host_incompatible_wait_ms": 25000,
            "post_match_ms": 20000,
            "message_count": 10,
            "publish_period_ms": 100,
            "compatible_assertion": "both endpoints match and all publisher messages are accepted and received",
            "incompatible_assertion": "neither endpoint matches and both endpoints report zero application traffic",
            "formal_runner_requires_frozen_artifacts": True,
            "amendment_policy": "any protocol or bound-file change requires a new protocol directory and a new time-window campaign; in-place edits are forbidden",
        },
        "hardware_and_network_gate": {
            "serial_by_id": args.serial_by_id,
            "board_chip": args.board_chip,
            "board_mac": args.board_mac,
            "board_ip": args.board_ip,
            "interface": args.interface,
            "host_ip": args.host_ip,
            "host_mac": args.host_mac,
            "ap_ssid": args.ap_ssid,
            "ap_bssid": args.ap_bssid,
        },
        "environment_snapshot": {
            "relative_root": "artifacts/environment",
            "files": environment_files,
            "source_verification_path": ENVIRONMENT_VERIFICATION,
            "source_verification_sha256": sha256(
                REPO / ENVIRONMENT_VERIFICATION
            ),
            "source_tree_sha256": environment_verification["tree_sha256"],
            "source_file_manifest_sha256": environment_verification[
                "file_manifest_sha256"
            ],
        },
        "host_artifacts": {
            "probe_relative_path": "artifacts/host/qos_compatibility_probe",
            "probe_sha256": sha256(frozen_host),
            "profile_relative_path": "artifacts/host/initial_peer.xml",
            "profile_sha256": sha256(frozen_profile),
            "ldd_relative_path": "artifacts/host/ldd.txt",
            "ldd_sha256": sha256(staging / "artifacts/host/ldd.txt"),
        },
        "bound_source_files": {
            relative: sha256(REPO / relative) for relative in SOURCE_PATHS
        },
        "excluded_prefreeze_smoke_releases": smoke_evidence,
        "evidence_boundary": "formal deterministic ROS 2 endpoint compatibility evidence only; no observations are pooled as latency, loss, energy, or resource performance samples",
    }
    write_json(staging / "design_manifest.json", design)
    staging.replace(output)
    print(
        f"PASS: frozen_cases=48 schedule_sha256={design['schedule_sha256']} "
        f"output={output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
