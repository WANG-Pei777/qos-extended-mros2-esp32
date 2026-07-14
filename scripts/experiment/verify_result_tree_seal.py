#!/usr/bin/env python3
"""Verify every file and digest in an experiment result-tree release seal."""

import argparse
import csv
import json
from pathlib import Path, PurePosixPath
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from seal_result_tree import EXCLUDED, sha256_file, tree_digest


def read_manifest(path):
    with Path(path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != ["path", "bytes", "sha256"]:
            raise ValueError("release manifest schema mismatch")
        rows = []
        for row in reader:
            relative = PurePosixPath(row["path"])
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError(f"unsafe release-manifest path: {row['path']}")
            try:
                size = int(row["bytes"])
            except ValueError as exc:
                raise ValueError(
                    f"invalid byte count for {row['path']}: {row['bytes']}"
                ) from exc
            rows.append({
                "path": row["path"],
                "bytes": size,
                "sha256": row["sha256"],
            })
    paths = [row["path"] for row in rows]
    if paths != sorted(paths):
        raise ValueError("release manifest paths are not sorted")
    if len(paths) != len(set(paths)):
        raise ValueError("release manifest contains duplicate paths")
    return rows


def verify(root):
    root = Path(root).resolve()
    manifest_path = root / "release_file_manifest.csv"
    seal_path = root / "release_seal.json"
    errors = []
    if not manifest_path.is_file() or not seal_path.is_file():
        missing = [
            str(path)
            for path in (manifest_path, seal_path)
            if not path.is_file()
        ]
        return {
            "schema_version": 1,
            "classification": "experiment_result_tree_release_verification",
            "status": "FAIL",
            "root": str(root),
            "errors": [f"missing seal files: {missing}"],
        }
    try:
        rows = read_manifest(manifest_path)
        seal = json.loads(seal_path.read_text(encoding="utf-8"))
    except (csv.Error, json.JSONDecodeError, OSError, ValueError) as exc:
        return {
            "schema_version": 1,
            "classification": "experiment_result_tree_release_verification",
            "status": "FAIL",
            "root": str(root),
            "errors": [str(exc)],
        }
    if seal.get("classification") != "experiment_result_tree_release_seal":
        errors.append("release seal classification mismatch")
    if set(seal.get("excluded_self_referential_files", [])) != EXCLUDED:
        errors.append("release seal exclusion set mismatch")
    if seal.get("file_manifest_sha256") != sha256_file(manifest_path):
        errors.append("release file-manifest hash mismatch")
    if seal.get("file_count") != len(rows):
        errors.append("release file count mismatch")
    if seal.get("total_bytes") != sum(row["bytes"] for row in rows):
        errors.append("release total byte count mismatch")
    if seal.get("tree_sha256") != tree_digest(rows):
        errors.append("release tree digest mismatch")

    manifest_paths = {row["path"] for row in rows}
    actual_paths = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.relative_to(root).as_posix() not in EXCLUDED
    }
    for missing in sorted(manifest_paths - actual_paths):
        errors.append(f"manifest file missing: {missing}")
    for extra in sorted(actual_paths - manifest_paths):
        errors.append(f"unsealed extra file: {extra}")
    verified_files = 0
    for row in rows:
        path = root / row["path"]
        if not path.is_file():
            continue
        if path.stat().st_size != row["bytes"]:
            errors.append(f"file size mismatch: {row['path']}")
            continue
        if sha256_file(path) != row["sha256"]:
            errors.append(f"file hash mismatch: {row['path']}")
            continue
        verified_files += 1
    return {
        "schema_version": 1,
        "classification": "experiment_result_tree_release_verification",
        "status": "PASS" if not errors else "FAIL",
        "root": str(root),
        "verified_files": verified_files,
        "file_count": len(rows),
        "total_bytes": sum(row["bytes"] for row in rows),
        "tree_sha256": seal.get("tree_sha256"),
        "file_manifest_sha256": seal.get("file_manifest_sha256"),
        "errors": errors,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result_root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = verify(args.result_root)
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
