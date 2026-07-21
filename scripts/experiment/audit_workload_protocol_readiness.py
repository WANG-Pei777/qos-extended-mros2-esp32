#!/usr/bin/env python3
"""Audit excluded workload/protocol readiness smokes and emit inventories."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ANCHORS = (
    {
        "anchor_id": "mros2qos-be-2048-100",
        "path": "results/diagnostics/20260720_workload_p2048_r100_mros2qos_fastdds_fragment_smoke",
        "system": "mros2qos",
        "qos": "BEST_EFFORT",
        "payload_bytes": 2048,
        "rate_hz": 100,
        "target_tx": 2000,
        "expected_rx": 2000,
        "firmware_sha256": "4c2f45e19e7f48e107b2d38ae73d70223335789b38af3d9a8275d275a0edf85a",
        "expected_manifest_status": "FAIL",
        "expected_manifest_validator_rc": 1,
        "offline_revalidation_required": True,
    },
    {
        "anchor_id": "mros2qos-rel-2048-10",
        "path": "results/diagnostics/20260720_workload_rel_p2048_r10_mros2qos_smoke_retry2",
        "system": "mros2qos",
        "qos": "RELIABLE",
        "payload_bytes": 2048,
        "rate_hz": 10,
        "target_tx": 200,
        "expected_rx": 200,
        "firmware_sha256": "4b23fd90a52b4ca0f39c75dde901608ccdae0d70148ab157aa0216a022527c2b",
        "pcap_sha256": "a85337bb6ca2e3ff5498375f3c4ed5f351458595f2fa147db83d84f5e9cb7b4c",
        "pcap_packets": 1354,
    },
    {
        "anchor_id": "microros-be-512-100",
        "path": "results/diagnostics/20260720_workload_p512_r100_microros_mtu1200_smoke_retry2",
        "system": "microros",
        "qos": "BEST_EFFORT",
        "payload_bytes": 512,
        "rate_hz": 100,
        "target_tx": 2000,
        "expected_rx": 2000,
        "firmware_sha256": "4dd8a2c8460df42034ab74818816a916a4e3522cf3935800b9a54adcabf6ac7d",
    },
    {
        "anchor_id": "microros-rel-512-10",
        "path": "results/diagnostics/20260720_workload_rel_p512_r10_microros_agent242_smoke",
        "system": "microros",
        "qos": "RELIABLE",
        "payload_bytes": 512,
        "rate_hz": 10,
        "target_tx": 200,
        "expected_rx": 198,
        "firmware_sha256": "3f92d4b0c74b0be545c0bbecd9d97e1d6e9c695cc435a4513b5c2a9e1a45531a",
    },
    {
        "anchor_id": "microros-rel-2048-10",
        "path": "results/diagnostics/20260720_workload_rel_p2048_r10_microros_agent242_size4096_ddsmtu1200_smoke_retry2",
        "system": "microros",
        "qos": "RELIABLE",
        "payload_bytes": 2048,
        "rate_hz": 10,
        "target_tx": 200,
        "expected_rx": 195,
        "firmware_sha256": "03aa7f4fcbb6f8382877b6b17a97147030977b9d27ef767d1e6f6262b04d0fe0",
        "pcap_sha256": "ba93f88d021c669cd35f65cafee9faafb293824f47642a909bb5b8e1de8c11c8",
        "pcap_packets": 7458,
    },
)

RESOURCES = (
    {
        "system": "mros2qos",
        "anchor_id": "mros2qos-rel-2048-10",
        "map": "artifacts/mros2qos_telemetry_compare.map",
        "expected": {
            "diram_data": 17916,
            "diram_bss": 80912,
            "used_diram": 168567,
            "used_flash_non_ram": 682715,
            "total_size": 786753,
        },
    },
    {
        "system": "microros",
        "anchor_id": "microros-rel-2048-10",
        "map": "artifacts/microros_telemetry_compare.map",
        "expected": {
            "diram_data": 18048,
            "diram_bss": 69792,
            "used_diram": 157555,
            "used_flash_non_ram": 725147,
            "total_size": 829293,
        },
    },
)

AGENT_EXECUTABLE_SHA256 = (
    "869c538feeb216bb63b037ce1d5e4f89a72ca7671fc4321e516a587dedc5e749"
)
AGENT_LIBRARY_SHA256 = (
    "af7b801c8b4c82e6bf03f86bc7baeccb139da850748e8fb702630d752f0129f3"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_key_values(line: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for token in line.strip().split():
        if "=" in token:
            key, value = token.split("=", 1)
            values[key] = value
    return values


def last_record(path: Path, prefix: str) -> dict[str, str]:
    match = None
    for raw in path.read_bytes().splitlines():
        line = raw.decode("utf-8", errors="ignore")
        if line.startswith(prefix):
            match = parse_key_values(line)
    if match is None:
        raise ValueError(f"{path}: missing {prefix}")
    return match


def capinfos(path: Path) -> tuple[int, float]:
    result = subprocess.run(
        ["capinfos", "-Tm", "-c", "-u", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    rows = list(csv.DictReader(result.stdout.splitlines()))
    if len(rows) != 1:
        raise ValueError(f"{path}: capinfos returned {len(rows)} rows")
    return int(rows[0]["Number of packets"]), float(
        rows[0]["Capture duration (seconds)"]
    )


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        raise ValueError(f"refusing to write empty CSV: {path}")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def audit_anchor(
    repo: Path, anchor: dict[str, object], errors: list[str]
) -> tuple[dict[str, object], dict[str, object]]:
    root = repo / str(anchor["path"])
    manifest = json.loads((root / "attempt_manifest.json").read_text(encoding="utf-8"))
    validation = (root / "validation.txt").read_text(encoding="utf-8").strip()
    validation_values = parse_key_values(validation)
    compare = last_record(root / "serial.raw", "COMPARE_FINAL")
    final = last_record(root / "serial.raw", "BENCH_FINAL")

    workload = manifest["workload"]
    expected_pairs = {
        "status": (
            manifest["status"],
            anchor.get("expected_manifest_status", "PASS"),
        ),
        "system": (manifest["system"], anchor["system"]),
        "qos": (workload["qos"], anchor["qos"]),
        "payload_bytes": (workload["payload_bytes"], anchor["payload_bytes"]),
        "rate_hz": (workload["rate_hz"], anchor["rate_hz"]),
        "target_tx": (workload["target_tx"], anchor["target_tx"]),
        "validation_tx": (int(validation_values.get("tx", -1)), anchor["target_tx"]),
        "validation_rx": (int(validation_values.get("rx", -1)), anchor["expected_rx"]),
        "compare_tx": (int(compare["tx"]), anchor["target_tx"]),
        "compare_rx": (int(compare["rx"]), anchor["expected_rx"]),
        "final_tx": (int(final["attempted_tx"]), anchor["target_tx"]),
        "final_rx": (int(final["rx"]), anchor["expected_rx"]),
        "validator_rc": (
            manifest["return_codes"]["validator"],
            anchor.get("expected_manifest_validator_rc", 0),
        ),
    }
    if not validation.startswith("PASS:"):
        errors.append(f"{anchor['anchor_id']}: validator did not pass")
    for name, (actual, expected) in expected_pairs.items():
        if actual != expected:
            errors.append(
                f"{anchor['anchor_id']}: {name}={actual!r} != {expected!r}"
            )

    validator_command = list(manifest["commands"]["validator"])
    revalidation = subprocess.run(
        validator_command,
        capture_output=True,
        text=True,
    )
    if revalidation.returncode != 0 or not revalidation.stdout.startswith("PASS:"):
        errors.append(f"{anchor['anchor_id']}: current offline validator failed")
    if anchor.get("offline_revalidation_required") and manifest["status"] != "FAIL":
        errors.append(
            f"{anchor['anchor_id']}: historical validator failure was not retained"
        )

    firmware = root / manifest["artifacts"]["firmware"]["path"]
    firmware_hash = sha256(firmware)
    recorded_firmware_hash = manifest["artifacts"]["firmware"]["sha256"]
    if firmware_hash != recorded_firmware_hash:
        errors.append(f"{anchor['anchor_id']}: artifact/manifest firmware mismatch")
    if firmware_hash != anchor["firmware_sha256"]:
        errors.append(f"{anchor['anchor_id']}: firmware differs from frozen expectation")

    for artifact_name, artifact in manifest["artifacts"].items():
        artifact_path = root / artifact["path"]
        if sha256(artifact_path) != artifact["sha256"]:
            errors.append(
                f"{anchor['anchor_id']}: {artifact_name} hash does not match manifest"
            )

    pcap = root / "traffic.pcapng"
    packets, duration = capinfos(pcap)
    pcap_hash = sha256(pcap)
    if anchor.get("pcap_sha256") and pcap_hash != anchor["pcap_sha256"]:
        errors.append(f"{anchor['anchor_id']}: PCAP differs from frozen expectation")
    if anchor.get("pcap_packets") and packets != anchor["pcap_packets"]:
        errors.append(f"{anchor['anchor_id']}: PCAP packet count changed")

    summary = {
        "anchor_id": anchor["anchor_id"],
        "classification": manifest["classification"],
        "manifest_status": manifest["status"],
        "current_offline_validator_status": (
            "PASS" if revalidation.returncode == 0 else "FAIL"
        ),
        "system": anchor["system"],
        "qos": anchor["qos"],
        "payload_bytes": anchor["payload_bytes"],
        "rate_hz": anchor["rate_hz"],
        "tx": anchor["target_tx"],
        "rx": anchor["expected_rx"],
        "delivery_ratio": int(anchor["expected_rx"]) / int(anchor["target_tx"]),
        "rtt_samples": compare["samples"],
        "rtt_mean_us": compare["avg_us"],
        "cpu_mean_ppm": validation_values["cpu_mean_ppm"],
        "cpu_p95_ppm": validation_values["cpu_p95_ppm"],
        "min_internal_heap_bytes": validation_values["min_internal_heap"],
        "min_stack_hwm_bytes": validation_values["min_stack_hwm"],
        "window_us": validation_values["window_us"],
        "firmware_sha256": firmware_hash,
        "relative_path": anchor["path"],
    }
    pcap_row = {
        "anchor_id": anchor["anchor_id"],
        "packets": packets,
        "capture_duration_seconds": f"{duration:.9f}",
        "sha256": pcap_hash,
        "relative_path": f"{anchor['path']}/traffic.pcapng",
    }
    return summary, pcap_row


def audit_resources(
    repo: Path,
    anchors_by_id: dict[str, dict[str, object]],
    idf_python: Path,
    idf_size_tool: Path,
    errors: list[str],
) -> list[dict[str, object]]:
    rows = []
    for item in RESOURCES:
        anchor = anchors_by_id[str(item["anchor_id"])]
        map_path = repo / str(anchor["path"]) / str(item["map"])
        result = subprocess.run(
            [
                str(idf_python),
                str(idf_size_tool),
                "--format",
                "json",
                "--target",
                "esp32s3",
                str(map_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        measured = json.loads(result.stdout)
        expected = item["expected"]
        for metric, expected_value in expected.items():
            if measured.get(metric) != expected_value:
                errors.append(
                    f"{item['system']}: {metric}={measured.get(metric)} "
                    f"!= {expected_value}"
                )
        rows.append(
            {
                "system": item["system"],
                "anchor_id": item["anchor_id"],
                **{metric: measured[metric] for metric in expected},
                "map_sha256": sha256(map_path),
                "relative_map_path": map_path.relative_to(repo).as_posix(),
            }
        )
    return rows


def audit_boundaries(repo: Path, errors: list[str]) -> list[dict[str, object]]:
    micro_path = Path(
        "results/diagnostics/"
        "20260720_workload_rel_p512_r100_microros_agent242_executor_drain_smoke"
    )
    micro_root = repo / micro_path
    micro_manifest = json.loads(
        (micro_root / "attempt_manifest.json").read_text(encoding="utf-8")
    )
    micro_compare = last_record(micro_root / "serial.raw", "COMPARE_FINAL")
    micro_validation = (micro_root / "validation.txt").read_text(encoding="utf-8")
    if micro_manifest["status"] != "FAIL":
        errors.append("microros-rel-512-100 boundary attempt is not retained as FAIL")
    if not micro_validation.startswith("FAIL: core 0 control window is 51680797 us"):
        errors.append("microros-rel-512-100 failure reason changed")
    if (int(micro_compare["tx"]), int(micro_compare["rx"])) != (2000, 1559):
        errors.append("microros-rel-512-100 boundary counts changed")

    upstream_path = Path(
        "results/diagnostics/20260720_workload_p2048_r100_upstream_native_smoke"
    )
    upstream_manifest = json.loads(
        (repo / upstream_path / "attempt_manifest.json").read_text(encoding="utf-8")
    )
    if upstream_manifest["status"] != "FAIL":
        errors.append("upstream-be-2048-100 attempt is not retained as FAIL")

    upstream_root = repo.parent / "upstream_bench/mros2-esp32/workspace/telemetry_compare"
    source = upstream_root / "main/telemetry_compare.cpp"
    compile_logs = upstream_root / "build_workload_rel_compile_gate/log"
    compile_gate_text = "upstream mros2-esp32 does not expose Reliable user-endpoint creation"
    source_has_gate = compile_gate_text in source.read_text(encoding="utf-8")
    log_has_gate = any(
        compile_gate_text in path.read_text(encoding="utf-8", errors="ignore")
        for path in compile_logs.glob("idf_py_*_output_*")
    )
    if not source_has_gate or not log_has_gate:
        errors.append("upstream Reliable compile-gate evidence is incomplete")

    return [
        {
            "boundary_id": "microros-rel-512-100-capacity",
            "classification": "retained_fail",
            "observed_tx": 2000,
            "observed_rx": 1559,
            "reason": "51.680797 s control window exceeds the 20 s contract",
            "relative_path": micro_path.as_posix(),
        },
        {
            "boundary_id": "upstream-be-2048-100-reader",
            "classification": "retained_fail",
            "observed_tx": "",
            "observed_rx": "",
            "reason": "native reader cannot reassemble the large return DATA_FRAG sample",
            "relative_path": upstream_path.as_posix(),
        },
        {
            "boundary_id": "upstream-reliable-api",
            "classification": "compile_gate",
            "observed_tx": "",
            "observed_rx": "",
            "reason": "no native Reliable user-endpoint creation API",
            "relative_path": source.relative_to(repo.parent).as_posix(),
        },
    ]


def audit_agent(repo: Path, errors: list[str]) -> dict[str, object]:
    anchor = next(item for item in ANCHORS if item["anchor_id"] == "microros-rel-2048-10")
    artifacts = repo / str(anchor["path"]) / "artifacts"
    executable_hash = sha256(artifacts / "MicroXRCEAgent")
    library_hash = sha256(artifacts / "libmicroxrcedds_agent.so.2.4")
    cache = (artifacts / "CMakeCache.txt").read_text(encoding="utf-8")
    if executable_hash != AGENT_EXECUTABLE_SHA256:
        errors.append("MicroXRCEAgent executable hash changed")
    if library_hash != AGENT_LIBRARY_SHA256:
        errors.append("MicroXRCEAgent shared-library hash changed")
    if "UAGENT_TOPIC_MAX_SERIALIZED_SIZE:STRING=4096" not in cache:
        errors.append("MicroXRCEAgent 4096-byte DDS topic capacity is not bound")
    return {
        "version": "2.4.2",
        "source_commit": "57d086216d01ec43121845d385894a25987f8a2c",
        "fastdds_version": "2.12.2",
        "topic_max_serialized_size": 4096,
        "executable_sha256": executable_hash,
        "shared_library_sha256": library_hash,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    default_repo = Path(__file__).resolve().parents[2]
    parser.add_argument("--repo-root", type=Path, default=default_repo)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=default_repo
        / "results/audits/20260720_workload_protocol_readiness",
    )
    parser.add_argument(
        "--idf-python",
        type=Path,
        default=Path(os.environ.get("IDF_PYTHON", sys.executable)),
    )
    parser.add_argument(
        "--idf-size-tool",
        type=Path,
        default=Path(os.environ.get("IDF_SIZE_TOOL", "idf_size.py")),
    )
    args = parser.parse_args()

    repo = args.repo_root.resolve()
    output = args.output_dir.resolve()
    errors: list[str] = []
    anchor_rows = []
    pcap_rows = []
    anchors_by_id = {str(item["anchor_id"]): item for item in ANCHORS}

    try:
        for anchor in ANCHORS:
            summary, pcap = audit_anchor(repo, anchor, errors)
            anchor_rows.append(summary)
            pcap_rows.append(pcap)
        resource_rows = audit_resources(
            repo, anchors_by_id, args.idf_python, args.idf_size_tool, errors
        )
        boundary_rows = audit_boundaries(repo, errors)
        agent = audit_agent(repo, errors)
    except (OSError, KeyError, ValueError, subprocess.CalledProcessError) as exc:
        errors.append(f"audit execution failed: {exc}")
        resource_rows = []
        boundary_rows = []
        agent = {}

    output.mkdir(parents=True, exist_ok=True)
    if anchor_rows:
        write_csv(output / "accepted_anchor_summary.csv", anchor_rows)
    if pcap_rows:
        write_csv(output / "pcap_inventory.csv", pcap_rows)
    if resource_rows:
        write_csv(output / "resource_table.csv", resource_rows)
    if boundary_rows:
        write_csv(output / "boundary_inventory.csv", boundary_rows)

    report = {
        "schema_version": 1,
        "classification": "engineering_readiness_audit",
        "evidence_boundary": "excluded N=1 smokes; never formal comparison data",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if not errors else "FAIL",
        "accepted_anchors": len(anchor_rows),
        "pcaps": len(pcap_rows),
        "resource_rows": len(resource_rows),
        "boundary_rows": len(boundary_rows),
        "energy_gate": "BLOCKED_EXTERNAL_CALIBRATED_MONITOR_AND_GPIO_ALIGNMENT",
        "agent": agent,
        "errors": errors,
    }
    (output / "audit.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(
        "PASS: accepted_anchors=5 pcaps=5 resource_rows=2 boundaries=3 "
        "agent_capacity=4096 energy_gate=BLOCKED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
