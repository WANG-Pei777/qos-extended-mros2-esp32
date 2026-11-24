#!/usr/bin/env python3
"""Create an immutable per-condition provenance manifest."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import socket
import subprocess
import sys
from datetime import datetime, timezone


def command_output(*command):
    try:
        return subprocess.check_output(command, text=True, stderr=subprocess.STDOUT).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        return f"unavailable: {exc}"


def sha256_file(path):
    if not path:
        return ""
    candidate = Path(path)
    if not candidate.is_file():
        return "missing"
    digest = hashlib.sha256()
    with candidate.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_binary_path(path, project_root):
    if not path:
        return None
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = Path(project_root) / candidate
    return candidate.resolve()


def display_path(path, project_root):
    try:
        return str(path.relative_to(Path(project_root).resolve()))
    except ValueError:
        return str(path)


def archive_binary(source_path, artifact_dir, role, project_root):
    source = resolve_binary_path(source_path, project_root)
    if source is None:
        return {"path": "", "source_path": "", "sha256": ""}
    if not source.is_file():
        raise ValueError(f"{role} binary does not exist: {source}")

    digest = sha256_file(source)
    suffix = source.suffix or ".bin"
    destination_dir = Path(artifact_dir).resolve()
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"{role}_{digest}{suffix}"

    if destination.exists():
        archived_digest = sha256_file(destination)
        if archived_digest != digest:
            raise ValueError(
                f"{role} archive hash mismatch: {destination} "
                f"contains {archived_digest}, expected {digest}"
            )
    else:
        shutil.copyfile(source, destination)
        destination.chmod(0o444)
        archived_digest = sha256_file(destination)
        if archived_digest != digest:
            destination.unlink(missing_ok=True)
            raise ValueError(f"{role} archive copy failed SHA-256 verification")

    return {
        "path": display_path(destination, project_root),
        "source_path": str(source_path),
        "sha256": digest,
    }


def manifest_hash(path):
    return sha256_file(path)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", required=True)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--system", required=True)
    parser.add_argument("--condition", required=True)
    parser.add_argument("--formal-run", required=True)
    parser.add_argument("--qos-mode", required=True)
    parser.add_argument("--firmware-mode", required=True)
    parser.add_argument("--host-mode", required=True)
    parser.add_argument("--injection-layer", required=True)
    parser.add_argument("--board-ip", required=True)
    parser.add_argument("--link-gate-ms", required=True)
    parser.add_argument("--commit-hash", required=True)
    parser.add_argument("--worktree-state", required=True)
    parser.add_argument("--worktree-fingerprint", required=True)
    parser.add_argument("--host-binary", default="")
    parser.add_argument("--firmware-binary", default="")
    parser.add_argument("--artifact-dir", required=True)
    return parser.parse_args()


def main():
    args = parse_args()
    path = Path(args.path)
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        host_binary = archive_binary(
            args.host_binary,
            args.artifact_dir,
            "host",
            args.project_root,
        )
        firmware_binary = archive_binary(
            args.firmware_binary,
            args.artifact_dir,
            "firmware",
            args.project_root,
        )
    except (OSError, ValueError) as exc:
        raise SystemExit(f"binary archival failed: {exc}") from exc

    immutable = {
        "schema_version": 2,
        "experiment": {
            "system": args.system,
            "condition": args.condition,
            "formal_run": int(args.formal_run),
            "qos_mode": args.qos_mode,
            "firmware_mode": args.firmware_mode,
            "host_mode": args.host_mode,
            "injection_layer": args.injection_layer,
            "board_ip": args.board_ip,
            "link_gate_ms": int(args.link_gate_ms),
        },
        "source": {
            "commit_hash": args.commit_hash,
            "worktree_state": args.worktree_state,
            "worktree_fingerprint": args.worktree_fingerprint,
        },
        "host_binary": host_binary,
        "firmware_binary": firmware_binary,
    }

    if path.exists():
        with path.open(encoding="utf-8") as handle:
            existing = json.load(handle)
        existing_immutable = {
            key: existing[key]
            for key in ("schema_version", "experiment", "source", "host_binary", "firmware_binary")
        }
        if existing_immutable != immutable:
            raise SystemExit(
                "manifest conflict: refusing to append rows with different provenance"
            )
    else:
        payload = {
            **immutable,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "operator": os.environ.get("EXPERIMENT_OPERATOR", os.environ.get("USER", "unknown")),
            "host_environment": {
                "hostname": socket.gethostname(),
                "platform": platform.platform(),
                "python": sys.version.split()[0],
                "ros_distro": os.environ.get("ROS_DISTRO", "unavailable"),
                "idf_version": command_output("idf.py", "--version") if shutil.which("idf.py") else "unavailable",
                "network_interfaces": command_output("ip", "-brief", "address"),
            },
        }
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")

    print(manifest_hash(path))


if __name__ == "__main__":
    main()
