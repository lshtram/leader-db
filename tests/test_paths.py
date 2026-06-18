"""Data-lake path helpers tests.

The path layer is the entry point for every on-disk layout decision, so
its tests verify that:

- The canonical folder names match the documented layout.
- ``PRIORITY_SOURCES`` covers every source in §6 plus ``client_existing``.
- ``ensure_priority_folders`` is idempotent.
- ``ensure_data_lake_readme`` writes a one-page README into ``data/``.
- An isolated data lake (via ``LEADERSDB_PROJECT_ROOT``) redirects all
  helpers into a temp directory.
"""

from __future__ import annotations

from pathlib import Path

from leaders_db import paths
from leaders_db.paths import PRIORITY_SOURCES, ensure_data_lake_readme


def test_priority_sources_present() -> None:
    expected = {
        "client_existing",
        "archigos",
        "leader_survival",
        "reign",
        "vdem",
        "freedom_house",
        "world_bank_wdi",
        "world_bank_wgi",
        "transparency_cpi",
        "ucdp",
        "cow_mid",
        "pts",
        "cirights",
        "sipri",
        "fas",
        "nti",
    }
    # ``pts`` is registered under ``political_terror_scale`` in the data
    # lake but the ingest module is ``pts`` — keep the alias documented.
    expected_in_dirs = expected - {"pts"} | {"political_terror_scale"}
    assert set(PRIORITY_SOURCES) == expected_in_dirs


def test_canonical_folder_names() -> None:
    assert paths.RAW_DIR == "raw"
    assert paths.PROCESSED_DIR == "processed"
    assert paths.INTERIM_DIR == "interim"
    assert paths.OUTPUTS_DIR == "outputs"
    assert paths.LOGS_DIR == "logs"
    assert paths.METADATA_DIR == "metadata"


def test_ensure_priority_folders_is_idempotent(isolated_data_lake: Path) -> None:
    created_once = paths.ensure_priority_folders()
    assert created_once, "first call should create the lake"

    created_again = paths.ensure_priority_folders()
    assert created_again == [], "second call must not recreate anything"


def test_data_lake_readme_is_written(isolated_data_lake: Path) -> None:
    readme = ensure_data_lake_readme()
    assert readme.exists()
    body = readme.read_text(encoding="utf-8")
    assert "Local data lake" in body
    assert "raw/" in body


def test_isolated_root_is_respected(isolated_data_lake: Path) -> None:
    # All path helpers must resolve under the isolated root.
    assert paths.data_dir() == isolated_data_lake / "data"
    assert paths.raw_dir("vdem") == isolated_data_lake / "data" / "raw" / "vdem"
    assert paths.outputs_dir() == isolated_data_lake / "data" / "outputs"
    assert paths.catalog_dir() == isolated_data_lake / "data" / "catalog"
