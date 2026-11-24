#!/usr/bin/env python3
"""Capture and verify the hardware/network gate for Seven-QoS collection."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shlex
import subprocess


REPO = Path(__file__).resolve().parents[2]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_revision() -> dict[str, object]:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    tracked_status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return {
        "commit": commit,
        "tracked_worktree_dirty": bool(tracked_status),
    }


def run_text(command: list[str]) -> str:
    completed = subprocess.run(command, check=True, capture_output=True)
    return completed.stdout.decode("utf-8", errors="replace")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--serial-by-id", required=True)
    parser.add_argument("--board-chip", required=True)
    parser.add_argument("--board-mac", required=True)
    parser.add_argument("--board-ip", required=True)
    parser.add_argument("--interface", required=True)
    parser.add_argument("--host-ip", required=True)
    parser.add_argument("--host-mac", required=True)
    parser.add_argument("--ap-ssid", required=True)
    parser.add_argument("--ap-bssid", required=True)
    parser.add_argument(
        "--idf-export", type=Path, default=Path.home() / "esp-idf/export.sh"
    )
    args = parser.parse_args()

    output = args.output if args.output.is_absolute() else REPO / args.output
    output = output.resolve()
    if output.exists():
        parser.error(f"output already exists: {output}")
    if not output.is_relative_to(REPO):
        parser.error("output must be inside the repository")

    source_git = git_revision()
    if source_git["tracked_worktree_dirty"]:
        raise SystemExit("tracked worktree must be clean before environment capture")

    serial = Path(args.serial_by_id)
    if not serial.exists():
        raise SystemExit(f"serial identity is not present: {serial}")
    resolved_serial = serial.resolve()

    interface_text = run_text(
        ["ip", "-j", "address", "show", "dev", args.interface]
    )
    interface_data = json.loads(interface_text)
    if len(interface_data) != 1:
        raise SystemExit("expected exactly one interface record")
    record = interface_data[0]
    ipv4 = {
        item["local"]
        for item in record.get("addr_info", [])
        if item.get("family") == "inet"
    }
    if record.get("address", "").lower() != args.host_mac.lower():
        raise SystemExit("host interface MAC differs from the requested gate")
    if args.host_ip not in ipv4:
        raise SystemExit("host IPv4 address differs from the requested gate")

    netsh = Path("/mnt/c/Windows/System32/netsh.exe")
    wlan_text = run_text([str(netsh), "wlan", "show", "interfaces"])
    wlan_lower = wlan_text.lower()
    if args.ap_ssid.lower() not in wlan_lower:
        raise SystemExit("AP SSID is absent from the Windows WLAN snapshot")
    if args.ap_bssid.lower() not in wlan_lower:
        raise SystemExit("AP BSSID is absent from the Windows WLAN snapshot")

    subprocess.run(
        ["ping", "-c", "2", "-W", "2", args.board_ip],
        check=True,
        capture_output=True,
    )
    neighbor_text = run_text(
        ["ip", "neigh", "show", "to", args.board_ip, "dev", args.interface]
    )
    if args.board_mac.lower() not in neighbor_text.lower():
        raise SystemExit("board MAC is absent from the neighbor table")

    chip_command = (
        f"source {shlex.quote(str(args.idf_export))} >/dev/null 2>&1 && "
        f"python -m esptool --chip esp32s3 --port "
        f"{shlex.quote(str(serial))} chip_id"
    )
    board_probe = run_text(["bash", "-lc", chip_command])
    if args.board_mac.lower() not in board_probe.lower():
        raise SystemExit("board MAC differs from the serial probe")

    output.mkdir(parents=True)
    files = {
        "windows_wlan_interfaces.txt": wlan_text,
        "wsl_interface.json": json.dumps(interface_data, indent=2) + "\n",
        "usb_uart_identity.txt": (
            f"serial_by_id={serial}\nresolved={resolved_serial}\n"
        ),
        "board_identity.txt": board_probe + "\nneighbor=" + neighbor_text,
    }
    for name, content in files.items():
        (output / name).write_text(content, encoding="utf-8")

    identity = {
        "serial_by_id": args.serial_by_id,
        "board_chip": args.board_chip,
        "board_mac": args.board_mac,
        "board_ip": args.board_ip,
        "interface": args.interface,
        "host_ip": args.host_ip,
        "host_mac": args.host_mac,
        "ap_ssid": args.ap_ssid,
        "ap_bssid": args.ap_bssid,
    }
    manifest = {
        "schema_version": 1,
        "classification": "seven_qos_environment_snapshot",
        "status": "PASS",
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_git": source_git,
        "identity": identity,
        "files": {name: sha256(output / name) for name in files},
    }
    (output / "snapshot_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"PASS: interface={args.interface} host={args.host_ip} "
        f"board={args.board_ip} ap={args.ap_ssid} output={output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
