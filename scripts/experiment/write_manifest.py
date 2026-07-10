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
    return parser.parse_args()


def main():
    args = parse_args()
    path = Path(args.path)
    path.parent.mkdir(parents=True, exist_ok=True)

    immutable = {
        "schema_version": 1,
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
        "host_binary": {
            "path": args.host_binary,
            "sha256": sha256_file(args.host_binary),
        },
        "firmware_binary": {
            "path": args.firmware_binary,
            "sha256": sha256_file(args.firmware_binary),
        },
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
