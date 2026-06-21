"""Tests for the Country-Year Chronicle SQLite artifact.

The Chronicle slice ships an optional SQLite artifact alongside
its CSV output. This test module pins:

- the canonical schema (one ``country_year_chronicle`` table
  with the documented column order and types);
- the row contents (same rows as the CSV companion file);
- the ``source_attributions`` sidecar table;
- the writer's atomic-rename guarantee;
- the CLI integration (the ``--sqlite-output`` flag wires the
  artifact through the production runner).
"""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from leaders_db.chronicle.constants import CHRONICLE_CSV_COLUMNS
from leaders_db.chronicle.sqlite_writer import (
    CHRONICLE_COLUMN_TYPES,
    SOURCE_ATTRIBUTIONS,
    default_sqlite_path,
    write_chronicle_sqlite,
)
from leaders_db.cli import app

runner = CliRunner()


def _sample_row() -> dict[str, str]:
    """A minimally populated row with the full column set."""
    row: dict[str, str] = {col: "" for col in CHRONICLE_CSV_COLUMNS}
    row["year"] = "2023"
    row["iso3"] = "USA"
    row["country_name"] = "United States"
    row["country_status"] = "independent"
    row["region"] = "Americas"
    row["subregion"] = "Northern America"
    row["political_regime_bucket"] = "Full democracy"
    row["political_regime_raw_score"] = "3"
    row["political_regime_source"] = "vdem"
    row["political_regime_source_year_used"] = "2023"
    row["political_regime_confidence"] = "80"
    row["system_type_primary"] = "Liberal capitalist democracy"
    row["system_type_confidence"] = "40"
    row["population"] = "334000000"
    row["population_source"] = "wdi"
    row["population_source_year_used"] = "2023"
    row["gdp"] = "21000000000000"
    row["gdp_unit"] = "constant_2015_usd"
    row["gdp_source"] = "wdi"
    row["gdp_source_year_used"] = "2023"
    row["data_quality_flags"] = "missing_ruler|missing_area|controlled_area_not_modeled"
    row["row_confidence"] = "65"
    row["provenance_summary"] = (
        "regime=vdem|wdi=yes|sipri=no|maddison=no|ruler=none"
        "|flags=missing_ruler,missing_area"
    )
    return row


# ---------------------------------------------------------------------------
# Default path resolution
# ---------------------------------------------------------------------------


def test_default_sqlite_path_lands_under_chronicle_output_dir() -> None:
    """``default_sqlite_path()`` resolves to
    ``<project_root>/data/outputs/country-year-chronicle/pilot.sqlite``.
    """
    path = default_sqlite_path()
    assert path.name == "pilot.sqlite"
    assert path.parent.name == "country-year-chronicle"
    assert path.parent.parent.name == "outputs"


def test_default_sqlite_path_honors_project_root_override(
    tmp_path: Path,
) -> None:
    """``default_sqlite_path(project_root=...)`` honors the override."""
    path = default_sqlite_path(project_root=tmp_path)
    # Path layout: <root>/data/outputs/country-year-chronicle/pilot.sqlite
    # so the 4th parent is <root>.
    assert path.parent.parent.parent.parent == tmp_path


# ---------------------------------------------------------------------------
# Writer direct tests
# ---------------------------------------------------------------------------


def test_write_sqlite_creates_canonical_schema(tmp_path: Path) -> None:
    """The writer creates the ``country_year_chronicle`` table
    with all expected columns and the documented storage types.
    """
    output = tmp_path / "pilot.sqlite"
    rows = [_sample_row()]
    write_chronicle_sqlite(
        output_path=output,
        rows=rows,
        sources_used=["vdem", "wdi"],
    )
    assert output.is_file()
    conn = sqlite3.connect(str(output))
    try:
        cur = conn.cursor()
        # Verify the chronicle table exists.
        cur.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='country_year_chronicle'"
        )
        assert cur.fetchone() is not None
        # Verify the source_attributions sidecar exists.
        cur.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='source_attributions'"
        )
        assert cur.fetchone() is not None
        # Verify the column names and types match the canonical contract.
        cur.execute("PRAGMA table_info(country_year_chronicle)")
        cols = cur.fetchall()
        column_names = [c[1] for c in cols]
        assert column_names == list(CHRONICLE_CSV_COLUMNS)
        # Verify a few type assertions.
        type_by_col = {c[1]: c[2] for c in cols}
        assert type_by_col["year"] == "INTEGER"
        assert type_by_col["population"] == "REAL"
        assert type_by_col["population_source_year_used"] == "INTEGER"
        assert type_by_col["iso3"] == "TEXT"
        assert type_by_col["provenance_summary"] == "TEXT"
    finally:
        conn.close()


def test_write_sqlite_inserts_rows_with_correct_types(tmp_path: Path) -> None:
    """Numeric columns are stored as INTEGER / REAL; empty cells
    are NULL; string columns are TEXT.
    """
    output = tmp_path / "pilot.sqlite"
    row = _sample_row()
    row["population"] = "334000000"
    row["row_confidence"] = "65"
    row["political_regime_source_year_used"] = "2023"
    # Add a row with empty cells.
    row2 = _sample_row()
    row2["iso3"] = "GBR"
    row2["population"] = ""  # empty -> NULL
    row2["gdp"] = ""  # empty -> NULL
    row2["row_confidence"] = ""  # empty -> NULL

    write_chronicle_sqlite(
        output_path=output,
        rows=[row, row2],
        sources_used=["vdem"],
    )

    conn = sqlite3.connect(str(output))
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT iso3, population, row_confidence, gdp FROM "
            "country_year_chronicle ORDER BY iso3"
        )
        rows = cur.fetchall()
        assert len(rows) == 2
        # USA row: numeric values typed correctly.
        assert rows[0][0] == "GBR"
        assert rows[0][1] is None
        assert rows[0][2] is None
        assert rows[0][3] is None
        assert rows[1][0] == "USA"
        assert rows[1][1] == 334000000.0  # REAL
        assert rows[1][2] == 65  # INTEGER
        assert rows[1][3] == 21_000_000_000_000.0
    finally:
        conn.close()


def test_write_sqlite_records_source_attributions(tmp_path: Path) -> None:
    """The ``source_attributions`` sidecar table is populated for
    every source in ``sources_used`` that has a canonical
    attribution constant.
    """
    output = tmp_path / "pilot.sqlite"
    write_chronicle_sqlite(
        output_path=output,
        rows=[_sample_row()],
        sources_used=["vdem", "wdi", "maddison_project", "archigos", "reign"],
    )

    conn = sqlite3.connect(str(output))
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT source_key, attribution_text FROM source_attributions "
            "ORDER BY source_key"
        )
        rows = cur.fetchall()
        # 5 source keys -> 5 rows in the sidecar.
        assert len(rows) == 5
        key_to_text = dict(rows)
        assert key_to_text["vdem"] == SOURCE_ATTRIBUTIONS["vdem"]
        assert key_to_text["wdi"] == SOURCE_ATTRIBUTIONS["wdi"]
        assert (
            key_to_text["maddison_project"]
            == SOURCE_ATTRIBUTIONS["maddison_project"]
        )
        assert key_to_text["archigos"] == SOURCE_ATTRIBUTIONS["archigos"]
        assert key_to_text["reign"] == SOURCE_ATTRIBUTIONS["reign"]
    finally:
        conn.close()


def test_write_sqlite_skips_unknown_sources(tmp_path: Path) -> None:
    """``sources_used`` entries without a canonical attribution
    constant (e.g. ``client_existing``) are silently skipped --
    they are not evidence for the chronicle, just metadata.
    """
    output = tmp_path / "pilot.sqlite"
    write_chronicle_sqlite(
        output_path=output,
        rows=[_sample_row()],
        sources_used=["vdem", "client_existing"],
    )
    conn = sqlite3.connect(str(output))
    try:
        cur = conn.cursor()
        cur.execute("SELECT source_key FROM source_attributions")
        keys = {r[0] for r in cur.fetchall()}
        assert keys == {"vdem"}
    finally:
        conn.close()


def test_write_sqlite_writes_atomically(tmp_path: Path) -> None:
    """The writer builds the SQLite file in a temp file under the
    same directory and renames atomically. A crash mid-write
    leaves the destination untouched.
    """
    output = tmp_path / "pilot.sqlite"
    write_chronicle_sqlite(
        output_path=output,
        rows=[_sample_row()],
        sources_used=["vdem"],
    )
    assert output.is_file()
    # No leftover tmp files in the directory.
    leftover = list(tmp_path.glob("*.tmp"))
    assert leftover == []


def test_write_sqlite_creates_parent_directory(tmp_path: Path) -> None:
    """The writer creates the parent directory if missing."""
    output = tmp_path / "nested" / "dir" / "pilot.sqlite"
    write_chronicle_sqlite(
        output_path=output,
        rows=[_sample_row()],
        sources_used=["vdem"],
    )
    assert output.is_file()


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


def test_cli_with_explicit_sqlite_path_writes_at_that_path(
    isolated_data_lake: Path,
    tmp_path: Path,
) -> None:
    """When ``--sqlite-output <PATH>`` is passed with an explicit
    path, the runner writes the SQLite artifact to that path and
    the canonical default path is NOT touched.
    """
    from tests.test_cli_chronicle import _seed_isolated_data_lake

    _seed_isolated_data_lake(isolated_data_lake)

    runner_environ = {"LEADERSDB_PROJECT_ROOT": str(isolated_data_lake)}
    csv_path = tmp_path / "pilot.csv"
    sqlite_path = tmp_path / "explicit.sqlite"
    default_sqlite_path = (
        isolated_data_lake
        / "data"
        / "outputs"
        / "country-year-chronicle"
        / "pilot.sqlite"
    )
    if default_sqlite_path.exists():
        default_sqlite_path.unlink()

    result = runner.invoke(
        app,
        [
            "run-country-year-chronicle",
            "--start-year", "2024",
            "--end-year", "2024",
            "--countries", "USA",
            "--output", str(csv_path),
            "--sqlite-output", str(sqlite_path),
        ],
        env=runner_environ,
    )
    assert result.exit_code == 0, result.stdout
    assert csv_path.is_file()
    assert sqlite_path.is_file()
    # Default canonical path is NOT touched when --output and
    # --sqlite-output are explicit.
    assert not default_sqlite_path.exists()


def test_cli_default_command_writes_sqlite_alongside_csv(
    isolated_data_lake: Path,
) -> None:
    """The default CLI command writes BOTH the CSV and the SQLite
    artifact at the canonical paths (no ``--sqlite-output`` flag
    needed; the runner's default behavior is to write both per
    the Increment 2 contract).

    This documents the "create SQLite alongside the CSV by
    default" behavior so a future reviewer-gate refactor that
    turns it off (making SQLite opt-in) fails loud.
    """
    from tests.test_cli_chronicle import _seed_isolated_data_lake

    _seed_isolated_data_lake(isolated_data_lake)

    runner_environ = {"LEADERSDB_PROJECT_ROOT": str(isolated_data_lake)}
    csv_path = (
        isolated_data_lake
        / "data"
        / "outputs"
        / "country-year-chronicle"
        / "country_year_chronicle.csv"
    )
    sqlite_path = (
        isolated_data_lake
        / "data"
        / "outputs"
        / "country-year-chronicle"
        / "pilot.sqlite"
    )
    if csv_path.exists():
        csv_path.unlink()
    if sqlite_path.exists():
        sqlite_path.unlink()

    result = runner.invoke(
        app,
        [
            "run-country-year-chronicle",
            "--start-year", "2024",
            "--end-year", "2024",
            "--countries", "USA",
        ],
        env=runner_environ,
    )
    assert result.exit_code == 0, result.stdout
    assert csv_path.is_file()
    # SQLite is created alongside the CSV by default.
    assert sqlite_path.is_file()


def test_cli_sqlite_artifact_row_count_matches_csv(
    isolated_data_lake: Path,
    tmp_path: Path,
) -> None:
    """The SQLite row count exactly matches the CSV data-row
    count for the same run.
    """
    from tests.test_cli_chronicle import _seed_isolated_data_lake

    _seed_isolated_data_lake(isolated_data_lake)

    runner_environ = {"LEADERSDB_PROJECT_ROOT": str(isolated_data_lake)}
    csv_path = tmp_path / "pilot.csv"
    sqlite_path = tmp_path / "pilot.sqlite"

    result = runner.invoke(
        app,
        [
            "run-country-year-chronicle",
            "--start-year", "2024",
            "--end-year", "2025",
            "--countries", "USA,GBR",
            "--output", str(csv_path),
            "--sqlite-output", str(sqlite_path),
        ],
        env=runner_environ,
    )
    assert result.exit_code == 0, result.stdout

    # CSV row count.
    with csv_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(row for row in fh if not row.startswith("#"))
        csv_rows = list(reader)
    assert len(csv_rows) == 4  # 2 countries x 2 years

    # SQLite row count.
    conn = sqlite3.connect(str(sqlite_path))
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM country_year_chronicle")
        sqlite_count = cur.fetchone()[0]
        assert sqlite_count == 4
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Caveat: schema discipline
# ---------------------------------------------------------------------------


def test_column_types_mapping_matches_documented_set() -> None:
    """The :data:`CHRONICLE_COLUMN_TYPES` mapping is a subset of
    the chronicle CSV columns and uses the documented storage
    classes only (no exotic types).
    """
    for column, sql_type in CHRONICLE_COLUMN_TYPES.items():
        assert column in CHRONICLE_CSV_COLUMNS, (
            f"{column!r} is in CHRONICLE_COLUMN_TYPES but not in "
            "CHRONICLE_CSV_COLUMNS"
        )
        assert sql_type in {"INTEGER", "REAL"}, (
            f"{column!r} has unsupported SQL type {sql_type!r}; "
            "use INTEGER or REAL only (TEXT is the default for "
            "non-listed columns)."
        )


def test_source_attributions_covers_all_chronicle_sources() -> None:
    """Every source the Chronicle runner can report must have a
    canonical attribution constant. This guards against the
    silent-skip-of-unknown-source bug in :func:`write_chronicle_sqlite`.
    """
    required_sources = {
        "archigos", "maddison_project", "reign", "sipri_milex",
        "vdem", "wdi",
    }
    assert required_sources.issubset(set(SOURCE_ATTRIBUTIONS.keys())), (
        "Missing attribution constants for: "
        f"{required_sources - set(SOURCE_ATTRIBUTIONS.keys())}"
    )
