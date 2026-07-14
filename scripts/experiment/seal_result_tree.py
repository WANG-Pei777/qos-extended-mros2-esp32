#!/usr/bin/env python3
"""Create a deterministic SHA-256 manifest for an experiment result tree."""

import argparse
import csv
import hashlib
import json
from pathlib import Path


EXCLUDED = {"release_file_manifest.csv", "release_seal.json"}


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inventory(root):
    root = Path(root).resolve()
    rows = []
    for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
        relative = path.relative_to(root).as_posix()
        if relative in EXCLUDED:
            continue
        rows.append({
            "path": relative,
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        })
    return rows


def tree_digest(rows):
    digest = hashlib.sha256()
    for row in rows:
        digest.update(
            f"{row['path']}\0{row['bytes']}\0{row['sha256']}\n".encode("utf-8")
        )
    return digest.hexdigest()


def write_manifest(path, rows):
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("path", "bytes", "sha256"))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result_root", type=Path)
    args = parser.parse_args()
    root = args.result_root.resolve()
    rows = inventory(root)
    manifest_path = root / "release_file_manifest.csv"
    seal_path = root / "release_seal.json"
    write_manifest(manifest_path, rows)
    seal = {
        "schema_version": 1,
        "classification": "experiment_result_tree_release_seal",
        "root": str(root),
        "file_count": len(rows),
        "total_bytes": sum(row["bytes"] for row in rows),
        "tree_sha256": tree_digest(rows),
        "file_manifest_sha256": sha256_file(manifest_path),
        "excluded_self_referential_files": sorted(EXCLUDED),
    }
    seal_path.write_text(
        json.dumps(seal, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(seal, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
