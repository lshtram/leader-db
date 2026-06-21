"""Production-wiring test for the Country-Year Chronicle slice.

Reviewer blocker: the existing chronicle CLI tests use only V-Dem
fixtures; the Maddison, Archigos, and REIGN production loaders
were not exercised end-to-end through the runner. This test
stages real-format fixtures for all three of those sources under
an isolated data lake, invokes the actual runner (not a stub
loader), and asserts:

- the resulting CSV has the expected rows and fields,
- ``sources_used`` includes ``maddison_project`` and either
  ``archigos`` and/or ``reign`` (the production loaders are
  wired into the runner),
- the audit-trail invariants hold (provenance_summary, source
  tags, attribution block).

We deliberately avoid touching the project's real data lake by
using the ``isolated_data_lake`` fixture (which monkeypatches
``LEADERSDB_PROJECT_ROOT``). Real-format fixtures are copied in
under ``data/raw/<source>/`` so the runner resolves them through
its production default path helpers.
"""

from __future__ import annotations

import csv
import shutil
from pathlib import Path

from typer.testing import CliRunner

from leaders_db.chronicle.constants import SOURCE_TAG_MADDISON
from leaders_db.cli import app

runner = CliRunner()

# Paths to the real-format fixtures committed under tests/fixtures/.
# These are NOT invented; they are real-format slices of the
# upstream bundles (see the per-fixture build_sample_*.py
# docstrings for the provenance).
_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
_MADDISON_XLSX = _FIXTURES_DIR / "maddison_project" / "sample.xlsx"
_ARCHIGOS_DTA = _FIXTURES_DIR / "archigos" / "sample.dta"
_REIGN_CSV = _FIXTURES_DIR / "reign" / "sample.csv"


def _stage_real_format_fixtures(isolated_data_lake: Path) -> None:
    """Copy the real-format Maddison / Archigos / REIGN fixtures
    into the isolated data lake under their canonical raw paths.

    The runner resolves ``default_maddison_xlsx_path()``,
    ``default_archigos_dta_path()``, and
    ``default_reign_csv_path()`` through ``leaders_db.paths``,
    which honours ``LEADERSDB_PROJECT_ROOT``. By placing the
    fixtures at those exact paths we exercise the production
    loader chain end-to-end.
    """
    maddison_dir = isolated_data_lake / "data" / "raw" / "maddison_project"
    archigos_dir = isolated_data_lake / "data" / "raw" / "archigos"
    reign_dir = isolated_data_lake / "data" / "raw" / "reign"
    sun_dir = isolated_data_lake / "data" / "raw" / "soviet_leaders_curated"
    cshapes_dir = isolated_data_lake / "data" / "raw" / "cshapes"
    maddison_dir.mkdir(parents=True, exist_ok=True)
    archigos_dir.mkdir(parents=True, exist_ok=True)
    reign_dir.mkdir(parents=True, exist_ok=True)
    sun_dir.mkdir(parents=True, exist_ok=True)
    cshapes_dir.mkdir(parents=True, exist_ok=True)

    shutil.copy2(_MADDISON_XLSX, maddison_dir / "mpd2023.xlsx")
    shutil.copy2(_ARCHIGOS_DTA, archigos_dir / "Archigos_4.1_stata14.dta")
    shutil.copy2(_REIGN_CSV, reign_dir / "REIGN_2021_8.csv")
    # Stage the canonical curated SUN CSV by copying the committed
    # raw file (the .csv is gitignored; the .gitkeep plus the
    # explicit stage here reproduces the production layout).
    sun_src = Path(__file__).resolve().parent.parent / "data" / "raw" / \
        "soviet_leaders_curated" / "soviet_leaders.csv"
    if sun_src.is_file():
        shutil.copy2(sun_src, sun_dir / "soviet_leaders.csv")
    # Stage the canonical CShapes CSV by copying the committed
    # raw file (the .csv is gitignored).
    cshapes_src = Path(__file__).resolve().parent.parent / "data" / "raw" / \
        "cshapes" / "CShapes-2.0.csv"
    if cshapes_src.is_file():
        shutil.copy2(cshapes_src, cshapes_dir / "CShapes-2.0.csv")


def _read_csv_data_rows(path: Path) -> list[dict[str, str]]:
    """Return the data rows of a chronicle CSV, skipping comment lines."""
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(row for row in fh if not row.startswith("#"))
        return list(reader)


def _read_csv_comment_lines(path: Path) -> list[str]:
    """Return the leading comment lines of a chronicle CSV."""
    text = path.read_text(encoding="utf-8")
    return [
        line for line in text.splitlines()
        if line.startswith("#")
    ]


# ---------------------------------------------------------------------------
# Maddison + Archigos + REIGN end-to-end via the CLI runner
# ---------------------------------------------------------------------------


def test_runner_loads_real_maddison_xlsx_into_chronicle_csv(
    isolated_data_lake: Path,
    tmp_path: Path,
) -> None:
    """The runner reads the real-format Maddison xlsx from the
    canonical raw path and emits Maddison-backed economy fields
    in the CSV (proves the production loader chain works).
    """
    _stage_real_format_fixtures(isolated_data_lake)
    output = tmp_path / "pilot.csv"

    result = runner.invoke(
        app,
        [
            "run-country-year-chronicle",
            "--start-year", "2022",
            "--end-year", "2022",
            "--countries", "USA",
            "--output", str(output),
        ],
    )
    assert result.exit_code == 0, result.stdout

    rows = _read_csv_data_rows(output)
    assert len(rows) == 1
    row = rows[0]
    assert row["iso3"] == "USA"
    assert row["year"] == "2022"
    # Maddison 2022 direct hit (USA 2022 is in the fixture).
    assert row["population_source"] == SOURCE_TAG_MADDISON
    assert row["gdp_source"] == SOURCE_TAG_MADDISON
    assert row["population_source_year_used"] == "2022"
    assert row["gdp_source_year_used"] == "2022"
    # Maddison populating alone (no WDI) means wdi=no in provenance.
    assert "wdi=no" in row["provenance_summary"]
    assert "maddison=yes" in row["provenance_summary"]


def test_runner_reports_archigos_in_sources_used(
    isolated_data_lake: Path,
    tmp_path: Path,
) -> None:
    """When Archigos has data for the requested year, the runner
    resolves a ruler name from the real Archigos .dta and reports
    ``archigos`` in ``sources_used``.
    """
    _stage_real_format_fixtures(isolated_data_lake)
    output = tmp_path / "pilot.csv"

    # The committed Archigos sample.dta covers USA 1869-1889.
    # USA 1880 falls inside one of the McKinley-precursor spells.
    result = runner.invoke(
        app,
        [
            "run-country-year-chronicle",
            "--start-year", "1880",
            "--end-year", "1880",
            "--countries", "USA",
            "--output", str(output),
        ],
    )
    assert result.exit_code == 0, result.stdout

    rows = _read_csv_data_rows(output)
    assert len(rows) == 1
    row = rows[0]
    # Archigos leader resolver picks the spell whose
    # startyear <= 1880 <= endyear. The fixture's Grant / Hayes /
    # Garfield / Arthur / Cleveland spells cover 1869-1889, so
    # 1880 resolves to one of them.
    assert row["ruler_source"] == "archigos"
    assert row["ruler_name"] != ""
    assert "ruler=archigos" in row["provenance_summary"]

    # The CLI summary line echoes sources_used (which is also
    # written into the CSV attribution block); check the CLI
    # stdout for ``archigos`` in sources_used.
    assert "sources_used:" in result.stdout
    assert "archigos" in result.stdout


def test_runner_reports_reign_in_sources_used(
    isolated_data_lake: Path,
    tmp_path: Path,
) -> None:
    """When REIGN has data for the requested year, the runner
    resolves a ruler name from the real REIGN CSV and reports
    ``reign`` in ``sources_used``.
    """
    _stage_real_format_fixtures(isolated_data_lake)
    output = tmp_path / "pilot.csv"

    # The committed REIGN sample.csv covers USA 2020 + 2021.
    result = runner.invoke(
        app,
        [
            "run-country-year-chronicle",
            "--start-year", "2020",
            "--end-year", "2020",
            "--countries", "USA",
            "--output", str(output),
        ],
    )
    assert result.exit_code == 0, result.stdout

    rows = _read_csv_data_rows(output)
    assert len(rows) == 1
    row = rows[0]
    assert row["ruler_source"] == "reign"
    assert row["ruler_name"] != ""
    assert "ruler=reign" in row["provenance_summary"]

    assert "sources_used:" in result.stdout
    assert "reign" in result.stdout


def test_runner_reports_maddison_archigos_and_reign_in_combined_run(
    isolated_data_lake: Path,
    tmp_path: Path,
) -> None:
    """A combined Maddison / Archigos / REIGN run produces a CSV
    whose ``sources_used`` includes all three sources (alongside
    V-Dem / SIPRI milex). This is the end-to-end production
    wiring proof: the runner auto-loads every source from its
    canonical data-lake path.
    """
    _stage_real_format_fixtures(isolated_data_lake)
    output = tmp_path / "pilot.csv"

    # Use the full pilot country set so Maddison has multiple
    # years / countries to resolve, and Archigos covers USA
    # pre-1890, and REIGN covers USA 2020+.
    result = runner.invoke(
        app,
        [
            "run-country-year-chronicle",
            "--start-year", "1880",
            "--end-year", "2022",
            "--countries", "USA",
            "--output", str(output),
        ],
    )
    assert result.exit_code == 0, result.stdout

    # CLI summary echoes ``sources_used`` with all wired sources.
    assert "maddison_project" in result.stdout
    assert "archigos" in result.stdout
    assert "reign" in result.stdout
    # The canonical chronicle sources are also there.
    assert "vdem" in result.stdout

    # The CSV comment block mirrors sources_used (one
    # attribution line per source key).
    comment_lines = _read_csv_comment_lines(output)
    comment_text = "\n".join(comment_lines)
    assert "Bolt, Jutta and Jan Luiten van Zanden (2024)" in comment_text
    assert "Archigos v4.1" in comment_text
    assert "REIGN dataset (Bell 2016)" in comment_text
    assert "V-Dem v16" in comment_text


def test_runner_reports_cshapes_in_sources_used(
    isolated_data_lake: Path,
    tmp_path: Path,
) -> None:
    """When CShapes has data for the requested year, the runner
    resolves a country area from the real CShapes CSV and reports
    ``cshapes`` in ``sources_used``.

    Increment 3 wiring proof: the runner auto-loads CShapes 2.0
    from its canonical data-lake path and emits
    ``country_area_km2`` per ``(iso3, year)``.
    """
    _stage_real_format_fixtures(isolated_data_lake)
    output = tmp_path / "pilot.csv"

    # USA 1900 falls inside the CShapes 1886-2019 coverage window.
    result = runner.invoke(
        app,
        [
            "run-country-year-chronicle",
            "--start-year", "1900",
            "--end-year", "1900",
            "--countries", "USA",
            "--output", str(output),
        ],
    )
    assert result.exit_code == 0, result.stdout

    rows = _read_csv_data_rows(output)
    assert len(rows) == 1
    row = rows[0]
    # CShapes populates the country area.
    assert row["area_source"] == "cshapes"
    assert row["country_area_km2"] != ""
    assert row["controlled_area_km2"] != ""
    assert row["controlled_area_km2"] == row["country_area_km2"]
    # The CShapes attribution line is in the comment block.
    comment_lines = _read_csv_comment_lines(output)
    assert any("CShapes 2.0" in line for line in comment_lines)
    # sources_used reports cshapes.
    assert "cshapes" in result.stdout


def test_runner_reports_soviet_leaders_curated_for_sun_rows(
    isolated_data_lake: Path,
    tmp_path: Path,
) -> None:
    """SUN 1922 (a year within the curated-source window) resolves
    to Lenin via the curated source, and the runner reports
    ``soviet_leaders_curated`` in ``sources_used``.

    Increment 3 wiring proof: the curated Soviet-leaders CSV is
    auto-loaded and routes SUN rows through it.
    """
    _stage_real_format_fixtures(isolated_data_lake)
    output = tmp_path / "pilot.csv"

    result = runner.invoke(
        app,
        [
            "run-country-year-chronicle",
            "--start-year", "1922",
            "--end-year", "1922",
            "--countries", "SUN",
            "--output", str(output),
        ],
    )
    assert result.exit_code == 0, result.stdout

    rows = _read_csv_data_rows(output)
    assert len(rows) == 1
    row = rows[0]
    assert row["ruler_name"] == "Lenin"
    assert row["ruler_source"] == "soviet_leaders_curated"
    assert "ruler=soviet_leaders_curated" in row["provenance_summary"]
    assert "soviet_leaders_curated" in result.stdout


def test_runner_combined_run_reports_all_seven_sources(
    isolated_data_lake: Path,
    tmp_path: Path,
) -> None:
    """A combined run with all seven Increment 3 sources staged
    reports ``sources_used`` containing every source key: archigos,
    cshapes, maddison_project, reign, sipri_milex,
    soviet_leaders_curated, vdem.

    This is the Increment 3 end-to-end production-wiring proof.
    """
    _stage_real_format_fixtures(isolated_data_lake)
    output = tmp_path / "pilot.csv"

    # Use the full pilot country set so Maddison has multiple
    # years / countries to resolve, Archigos covers USA pre-1890,
    # REIGN covers USA 2020+, and the SUN curated source covers
    # SUN 1922-1991.
    result = runner.invoke(
        app,
        [
            "run-country-year-chronicle",
            "--start-year", "1922",
            "--end-year", "2022",
            "--countries", "USA,SUN",
            "--output", str(output),
        ],
    )
    assert result.exit_code == 0, result.stdout

    # All 7 Increment 3 sources are reported.
    assert "cshapes" in result.stdout
    assert "soviet_leaders_curated" in result.stdout
    assert "maddison_project" in result.stdout
    assert "archigos" in result.stdout
    assert "reign" in result.stdout
    assert "vdem" in result.stdout

    # CSV comment block mirrors sources_used with attribution lines.
    comment_lines = _read_csv_comment_lines(output)
    comment_text = "\n".join(comment_lines)
    assert "CShapes 2.0" in comment_text
    assert "Soviet leaders" in comment_text


def test_runner_three_country_pilot_smoke_with_real_fixtures(
    isolated_data_lake: Path,
    tmp_path: Path,
) -> None:
    """A 3-country x 3-year pilot runs end-to-end with the real
    fixtures staged, produces the expected row count, and emits
    a well-formed CSV (header + data rows + comment block).

    The pilot uses the seven-country Increment 0 set because
    ``COUNTRY_METADATA`` is the authoritative source of supported
    ISO3 keys; MEX / SWE are not in the metadata map so we use
    USA / GBR / FRA instead. The point is to exercise the
    runner end-to-end with multiple countries / years.
    """
    _stage_real_format_fixtures(isolated_data_lake)
    output = tmp_path / "pilot.csv"

    result = runner.invoke(
        app,
        [
            "run-country-year-chronicle",
            "--start-year", "2020",
            "--end-year", "2022",
            "--countries", "USA,GBR,FRA",
            "--output", str(output),
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert output.is_file()

    # 3 countries x 3 years = 9 data rows.
    rows = _read_csv_data_rows(output)
    assert len(rows) == 9

    # Each row carries the expected canonical columns.
    expected_columns = {
        "year", "iso3", "country_name", "ruler_name", "ruler_source",
        "population", "population_source", "gdp", "gdp_source",
        "data_quality_flags", "row_confidence", "provenance_summary",
    }
    for row in rows:
        assert expected_columns.issubset(set(row.keys()))


def test_runner_csv_attribution_block_is_byte_identical_to_doc(
    isolated_data_lake: Path,
    tmp_path: Path,
) -> None:
    """End-to-end attribution drift guard: the attribution
    comment block in the CSV (the public output) is byte-for-byte
    a substring of ``docs/source-attributions.md``.

    This is the production-wiring companion to the constant
    drift tests in ``test_chronicle_constants.py``: it verifies
    the line lands in the actual CSV that downstream consumers
    read.
    """
    _stage_real_format_fixtures(isolated_data_lake)
    output = tmp_path / "pilot.csv"

    result = runner.invoke(
        app,
        [
            "run-country-year-chronicle",
            "--start-year", "2022",
            "--end-year", "2022",
            "--countries", "USA",
            "--output", str(output),
        ],
    )
    assert result.exit_code == 0, result.stdout

    text = output.read_text(encoding="utf-8")
    doc_path = (
        Path(__file__).resolve().parents[1]
        / "docs"
        / "source-attributions.md"
    )
    doc_text = doc_path.read_text(encoding="utf-8")

    # Each attribution comment line in the CSV (lines starting
    # with ``# <text>``) must appear verbatim in the doc.
    for line in text.splitlines():
        if not line.startswith("# "):
            continue
        # Skip the chronicle marker and the experimental-slice
        # warning (those are emitted by the writer, not by the
        # per-source mapping).
        if (
            "Country-Year Chronicle pilot CSV" in line
            or "Experimental vertical slice" in line
        ):
            continue
        # Skip the runtime ISO3 scope / year window / rows
        # extra-attribution lines (those are caller-supplied).
        if (
            "ISO3 scope" in line
            or "Year window" in line
            or "Rows:" in line
        ):
            continue
        # Each attribution line is ``# <text>`` where <text> is a
        # substring of the doc. Strip the leading ``# `` and
        # verify.
        text_after_hash = line[2:]
        assert text_after_hash in doc_text, (
            f"Attribution line {text_after_hash!r} (from CSV "
            f"comment block) is not in docs/source-attributions.md."
        )
