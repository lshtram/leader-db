#!/usr/bin/env bash
# Initialize the local data lake folders and the SQLite catalog.
#
# This is the shell wrapper around `leaders-db init-data-lake && leaders-db init-db`.
# Use it from CI / cron / a fresh checkout to bring the data lake and
# database to a clean, reproducible baseline.

set -euo pipefail

# Resolve the project root (directory containing this script's parent).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

# Prefer the in-tree venv if it exists; otherwise fall back to whatever
# `leaders-db` is on PATH.
if [[ -x "${PROJECT_ROOT}/.venv/bin/leaders-db" ]]; then
    LB="${PROJECT_ROOT}/.venv/bin/leaders-db"
else
    LB="$(command -v leaders-db || true)"
    if [[ -z "${LB}" ]]; then
        echo "leaders-db not found on PATH and no .venv present." >&2
        echo "Run: python3.11 -m venv .venv && source .venv/bin/activate && pip install -e '.[dev,duckdb]'" >&2
        exit 1
    fi
fi

echo "Using: ${LB}"
echo
echo "[1/2] init-data-lake"
"${LB}" init-data-lake
echo
echo "[2/2] init-db"
"${LB}" init-db
echo
echo "Done. Inspect the data lake with:"
echo "  ls -la data/raw data/processed data/catalog"
