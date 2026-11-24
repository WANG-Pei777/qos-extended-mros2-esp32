#!/usr/bin/env bash
# Historical E6 wrapper retained only to prevent accidental use.
set -euo pipefail

echo "[ERROR] The legacy E6 heartbeat sweep is retired and must not collect data." >&2
echo "[ERROR] Its --loss and --condition arguments were interpreted as sweep values." >&2
echo "[ERROR] Use docs/benchmark/ROUND6_MECHANISM_PREREGISTRATION.md." >&2
exit 2
