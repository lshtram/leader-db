"""Shared fixtures and helpers for the PWT Stage 2 test split.

Layout: this conftest sits at ``tests/ingest/sources/pwt/conftest.py``
and is auto-loaded by pytest for every test in
``tests/ingest/sources/pwt/``. The fixtures mirror the ones the
old monolithic ``tests/test_ingest_pwt.py`` exposed so the split
tests can keep using them.

Fixtures:

- :func:`pwt_xlsx_dir` -- stage the PWT fixture bundle
  (``pwt1001.xlsx`` + well-formed ``metadata.json``) under
  ``data/raw/pwt/`` in the isolated data lake.
- :func:`pwt_xlsx_no_metadata` -- same as above but WITHOUT the
  ``metadata.json`` (used by the readiness tests that need the
  gate to short-circuit before the reader opens the xlsx).
- :func:`pwt_custom_raw_root` -- stage the same valid bundle under
  a custom raw root outside the default ``data/raw`` tree, proving
  request-scoped raw-root wiring through the registry path.
- :func:`pwt_init_test_db` -- initialise the isolated SQLite DB
  with the project schema (per the
  ``tests/ingest/sources/pwt/test_db_cli.py`` tests).

Constants:

- :data:`PWT_SOURCE_KEY` / :data:`PWT_XLSX_NAME` /
  :data:`PWT_METADATA_NAME` -- the canonical bundle file names.
- :data:`PWT_CATALOG_RAW_COLUMNS` -- the 11 catalog numeric
  columns the Stage 2 reader / transform drive (mirrors
  :data:`leaders_db.ingest.sources.pwt.PWT_CATALOG_RAW_COLUMNS`).
- :data:`PWT_TEST_IDENTITY_COLUMNS` -- the 4 identity columns
  the reader always validates.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from leaders_db.db.engine import init_database

# ---------------------------------------------------------------------------
# Constants mirrored from the per-source package
# ---------------------------------------------------------------------------

PWT_SOURCE_KEY = "pwt"
PWT_XLSX_NAME = "pwt1001.xlsx"
PWT_METADATA_NAME = "metadata.json"

# The 11 catalog raw columns the Stage 2 reader / transform
# use. Mirrors ``PWT_CATALOG_RAW_COLUMNS`` in the per-source
# package's ``__init__.py``.
PWT_CATALOG_RAW_COLUMNS: tuple[str, ...] = (
    "rgdpe",
    "rgdpo",
    "pop",
    "emp",
    "avh",
    "hc",
    "ccon",
    "cda",
    "ctfp",
    "rkna",
    "rtfpna",
)

# Identity columns the reader always validates (4-column key).
PWT_TEST_IDENTITY_COLUMNS: tuple[str, ...] = (
    "countrycode",
    "country",
    "currency_unit",
    "year",
)


# ---------------------------------------------------------------------------
# Helpers and fixtures
# ---------------------------------------------------------------------------


def _stage_fixture(target_dir: Path, *, with_metadata: bool = True) -> Path:
    """Stage the PWT fixture xlsx (+ optional metadata) under
    ``data/raw/pwt/`` inside the isolated data lake.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    fixtures_dir = Path(__file__).resolve().parents[3] / "fixtures" / "pwt"
    fixture_xlsx = fixtures_dir / "sample.xlsx"
    shutil.copy2(fixture_xlsx, target_dir / PWT_XLSX_NAME)
    if with_metadata:
        sha = hashlib.sha256(
            (target_dir / PWT_XLSX_NAME).read_bytes(),
        ).hexdigest()
        payload = {
            "source_name": "Penn World Table",
            "source_version": "10.01",
            "download_date": "2026-06-22",
            "coverage": "country-year economic accounts",
            "years_available": "1950-2019",
            "license_note": (
                "Creative Commons Attribution 4.0 International "
                "(CC BY 4.0); cite Feenstra, Inklaar, Timmer 2015."
            ),
            "local_files": [PWT_XLSX_NAME],
            "ingestion_status": "downloaded",
            "source_url": (
                "https://www.rug.nl/ggdc/productivity/pwt/"
                "pwt-releases/pwt1001"
            ),
            "checksum_sha256": sha,
        }
        (target_dir / PWT_METADATA_NAME).write_text(
            json.dumps(payload, indent=2), encoding="utf-8",
        )
    return target_dir


@pytest.fixture()
def pwt_xlsx_dir(isolated_data_lake: Path) -> Path:
    """Stage the PWT fixture bundle with both the xlsx and a
    valid ``metadata.json`` under ``data/raw/pwt/``.
    """
    target = isolated_data_lake / "data" / "raw" / PWT_SOURCE_KEY
    return _stage_fixture(target, with_metadata=True)


@pytest.fixture()
def pwt_xlsx_no_metadata(isolated_data_lake: Path) -> Path:
    """Stage the PWT fixture xlsx WITHOUT ``metadata.json`` so
    the readiness gate must block before the reader opens the
    xlsx.
    """
    target = isolated_data_lake / "data" / "raw" / PWT_SOURCE_KEY
    return _stage_fixture(target, with_metadata=False)


@pytest.fixture()
def pwt_custom_raw_root(isolated_data_lake: Path) -> Path:
    """Stage a valid PWT fixture bundle under a non-default raw root.

    The default ``data/raw/pwt`` path is deliberately left absent.
    Registry-path tests use this fixture to prove production code
    carries ``IngestRequest.raw_root`` through ``check_ready`` ->
    ``read`` -> ``transform`` -> ``write`` instead of falling back
    to the default data-lake raw directory after readiness.
    """
    default_bundle = isolated_data_lake / "data" / "raw" / PWT_SOURCE_KEY
    assert not default_bundle.exists(), (
        "custom raw-root fixture requires default data/raw/pwt to be absent"
    )
    custom_raw_root = isolated_data_lake / "custom-raw-root"
    _stage_fixture(custom_raw_root / PWT_SOURCE_KEY, with_metadata=True)
    return custom_raw_root


@pytest.fixture()
def pwt_init_test_db(database_url: str) -> str:
    """Initialise the isolated SQLite DB with the project schema
    and return the URL so the test can scope a session.
    """
    init_database(database_url)
    return database_url


__all__ = [
    "PWT_CATALOG_RAW_COLUMNS",
    "PWT_METADATA_NAME",
    "PWT_SOURCE_KEY",
    "PWT_TEST_IDENTITY_COLUMNS",
    "PWT_XLSX_NAME",
    "pwt_custom_raw_root",
    "pwt_init_test_db",
    "pwt_xlsx_dir",
    "pwt_xlsx_no_metadata",
]
