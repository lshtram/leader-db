"""Data-lake path helpers.

All on-disk layout decisions live here so the rest of the package does not
hard-code ``"data/raw"`` or similar strings. The layout itself is normative
and documented in ``docs/local-data-store.md``.

Convention: every helper returns a :class:`pathlib.Path`; functions that
"create if missing" are explicit (``ensure_*``) so read paths never silently
materialize state.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from .env import _project_root

# Folder names are stable; if you change them here, update
# docs/local-data-store.md and the .gitignore at the project root.
RAW_DIR = "raw"
PROCESSED_DIR = "processed"
INTERIM_DIR = "interim"
OUTPUTS_DIR = "outputs"
LOGS_DIR = "logs"
METADATA_DIR = "metadata"

# The priority source folders must exist for the data lake to be considered
# initialized (see ``init_data_lake`` in ``cli.py``).
#
# This list is a superset that matches the keys consumed by
# :data:`leaders_db.ingest.STAGE2_ADAPTERS` plus the legacy ``client_existing``
# folder. SIPRI is split into ``sipri_milex`` and ``sipri_yearbook_ch7`` in
# the Stage 2 dispatch table; PTS is registered under ``pts`` in the
# dispatch table but the on-disk folder is ``political_terror_scale`` (the
# source name). ``init_data_lake`` creates all of these on a clean checkout.
PRIORITY_SOURCES: tuple[str, ...] = (
    # Client 2023 validation/reference bundle (always present).
    "client_existing",
    # Implemented Stage 2 adapters (raw + metadata on disk; see
    # ``docs/source-vetting-report.md`` and ``docs/source-attributions.md``).
    "archigos",
    "bti",
    "cirights",
    "fas",
    "political_terror_scale",  # Stage 2 dispatch key is ``pts``; raw folder uses the source name.
    "reign",
    "rsf_press_freedom",
    "sipri_milex",
    "sipri_yearbook_ch7",
    "transparency_cpi",
    "ucdp",
    "undp_hdi",
    "vdem",
    "who_gho_api",
    "wikidata_heads_of_state_government",
    "wikipedia_search_extract",
    "world_bank_wdi",
    "world_bank_wgi",
    # Blocked on raw bundle (raw file not staged locally).
    "leader_survival",
    "polity_v",
    "pwt",
    # User-managed / blocked (no code until files are placed locally).
    "cow_mid",
    "freedom_house",
    "imf_weo",
    "nti",
)


def project_root() -> Path:
    """Return the project root directory."""
    return _project_root()


def data_dir() -> Path:
    """Return the absolute path to the project's ``data/`` folder."""
    return project_root() / "data"


def raw_dir(source: str | None = None) -> Path:
    """Return the path to a ``data/raw/<source>/`` folder, or ``data/raw/``."""
    base = data_dir() / RAW_DIR
    return base / source if source else base


def processed_dir(source: str | None = None) -> Path:
    """Return the path to a ``data/processed/<source>/`` folder, or the parent."""
    base = data_dir() / PROCESSED_DIR
    return base / source if source else base


def interim_dir(source: str | None = None) -> Path:
    """Return the path to a ``data/interim/<source>/`` folder, or the parent."""
    base = data_dir() / INTERIM_DIR
    return base / source if source else base


def outputs_dir() -> Path:
    """Return the path to the ``data/outputs/`` folder."""
    return data_dir() / OUTPUTS_DIR


def logs_dir(run_id: str | None = None) -> Path:
    """Return the path to ``data/logs/`` or ``data/logs/<run_id>/``."""
    base = data_dir() / LOGS_DIR
    return base / run_id if run_id else base


def metadata_dir() -> Path:
    """Return the path to the ``data/metadata/`` folder."""
    return data_dir() / METADATA_DIR


def catalog_dir() -> Path:
    """Return the path to the ``data/catalog/`` folder (SQLite files live here)."""
    return data_dir() / "catalog"


def configs_dir() -> Path:
    """Return the path to the ``configs/`` folder at the project root."""
    return project_root() / "configs"


def research_dir() -> Path:
    """Return the path to the ``research/`` folder at the project root."""
    return project_root() / "research"


def tmp_dir() -> Path:
    """Return the path to the project-scoped ``tmp/`` folder for transient files."""
    return project_root() / "tmp"


def ensure_priority_folders(sources: Iterable[str] = PRIORITY_SOURCES) -> list[Path]:
    """Create the priority ``data/raw/<source>/`` folders if missing.

    Returns the list of folders that were created (already-existing folders
    are not returned).
    """
    created: list[Path] = []
    for src in sources:
        target = raw_dir(src)
        if not target.exists():
            target.mkdir(parents=True, exist_ok=True)
            created.append(target)
    # Ensure the lake's sibling folders exist too.
    for path in (
        processed_dir(),
        interim_dir(),
        outputs_dir(),
        logs_dir(),
        metadata_dir(),
    ):
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            created.append(path)
    return created


def ensure_data_lake_readme() -> Path:
    """Write a one-page README into ``data/`` explaining the layout, if missing.

    The README is what makes the data-lake skeleton self-describing when the
    folder is shared with collaborators who do not have access to the docs/.
    """
    readme = data_dir() / "README.md"
    if readme.exists():
        return readme

    body = (
        "# Local data lake\n\n"
        "This folder is governed by [`docs/local-data-store.md`](../docs/local-data-store.md).\n"
        "Layout:\n\n"
        "- `raw/<source>/` — immutable downloaded files + per-source `metadata.json`.\n"
        "- `processed/` — deterministic normalized parquet/csv.\n"
        "- `interim/` — mid-pipeline scratch.\n"
        "- `outputs/` — reports, validation CSVs, manual-review queue, summary markdown.\n"
        "- `logs/` — per-run log files.\n"
        "- `metadata/` — cross-source catalog metadata (aliases, authority, indicators).\n"
        "- `catalog/` — SQLite database file (`leaders_db.sqlite`).\n\n"
        "Files inside this folder are gitignored (see root `.gitignore`).\n"
        "Only the folder structure and this README are committed.\n"
    )
    readme.write_text(body, encoding="utf-8")
    return readme
