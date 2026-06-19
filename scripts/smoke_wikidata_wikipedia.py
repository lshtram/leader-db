"""Live-smoke script for the Wikidata heads-of-state-and-government Stage 2 adapter.

**Smoke-only -- not part of the test suite.** This script issues one
real Wikidata SPARQL query and one real Wikipedia Action API call
(``extracts``) and prints the resulting ``source_observations`` row
counts. It is gated behind a user prompt unless the
``LEADERSDB_SMOKE_YES=1`` env var is set so accidental runs do not
hit the public APIs.

Usage:

    python scripts/smoke_wikidata_wikipedia.py

or to bypass the prompt:

    LEADERSDB_SMOKE_YES=1 python scripts/smoke_wikidata_wikipedia.py

The script does NOT write to the production database or parquet. It
uses an isolated temp directory and a temp SQLite DB via the standard
``LEADERSDB_PROJECT_ROOT`` env var. The script is therefore safe to
run on any machine with network access (rate-limited per the
Wikimedia User-Agent policy).
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from leaders_db import env as _env
from leaders_db import paths as _paths
from leaders_db.db.engine import init_database
from leaders_db.db.session import default_sqlite_url
from leaders_db.ingest import (
    wikidata_heads_of_state_government,
    wikipedia_search_extract,
)

# Repository root is the parent of this script.
_REPO_ROOT = Path(__file__).resolve().parents[1]


def _confirm_or_skip() -> bool:
    """Prompt for confirmation unless ``LEADERSDB_SMOKE_YES=1`` is set."""
    if os.environ.get("LEADERSDB_SMOKE_YES") == "1":
        return True
    print(
        "This script will issue live HTTP requests to the Wikidata "
        "SPARQL endpoint\nand the Wikipedia Action API. They are "
        "rate-limited per the Wikimedia User-Agent policy.\n"
        "Re-run with LEADERSDB_SMOKE_YES=1 to skip this prompt."
    )
    response = input("Continue? [y/N]: ")
    return response.strip().lower() in {"y", "yes"}


def main() -> int:
    if not _confirm_or_skip():
        print("Aborted.")
        return 0

    with tempfile.TemporaryDirectory(prefix="leaders-db-smoke-") as tmp:
        os.environ["LEADERSDB_PROJECT_ROOT"] = tmp

        # Force a re-resolve of the cached paths so the override
        # takes effect (mirrors ``conftest.py``).
        _env._LOADED = False  # type: ignore[attr-defined]
        if hasattr(_paths, "_project_root_cached"):
            delattr(_paths, "_project_root_cached")

        # Mirror the data-lake skeleton (the orchestrator's
        # ``default_cache_dir`` would create it on demand, but we
        # stage it eagerly so the smoke run is deterministic).
        for sub in (
            "data/raw",
            "data/processed",
            "data/interim",
            "data/outputs",
            "data/logs",
            "data/metadata",
            "data/catalog",
        ):
            (Path(tmp) / sub).mkdir(parents=True, exist_ok=True)

        init_database(default_sqlite_url())  # resolves through
                                              # ``LEADERSDB_PROJECT_ROOT``.

        print("=== Wikidata SPARQL ===")
        wd_result = (
            wikidata_heads_of_state_government
            .ingest_wikidata_heads_of_state_government(
                year=2023,
                country_qids=["Q30", "Q96"],
                force_refresh=True,
            )
        )
        print(
            f"  observation_rows: {wd_result.observation_rows}\n"
            f"  countries: {wd_result.countries}\n"
            f"  persons: {wd_result.persons}\n"
            f"  parquet: {wd_result.parquet_path}\n"
            f"  attribution: {wd_result.attribution}"
        )

        print("=== Wikipedia Action API ===")
        wiki_result = (
            wikipedia_search_extract
            .ingest_wikipedia_search_extract(
                queries=["Joe Biden"],
                actions=["extracts"],
                force_refresh=True,
            )
        )
        print(
            f"  observation_rows: {wiki_result.observation_rows}\n"
            f"  queries: {wiki_result.queries}\n"
            f"  parquet: {wiki_result.parquet_path}\n"
            f"  attribution: {wiki_result.attribution}"
        )

        return 0


if __name__ == "__main__":
    sys.exit(main())
