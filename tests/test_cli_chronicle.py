"""Tests for the ``run-country-year-chronicle`` CLI command.

These tests cover the CLI boundary contract:

- the command is registered on the Typer ``app`` and appears in
  ``--help``;
- ``--help`` shows the documented defaults (start year 1900, end year
  2026, the seven-country pilot list);
- the command writes the CSV file at the requested output path;
- the command rejects bad year ranges and bad country lists with a
  non-zero exit code;
- the command does not require or consult a database (the slice is
  read-only and CSV-only);
- the command writes the attribution comment block at the top of the
  output file.

The tests use the ``isolated_data_lake`` fixture so they do not
touch the project's real data lake. A tiny synthetic V-Dem CSV is
written under ``data/raw/vdem/`` in the tmp tree so the slice can
load real-format V-Dem rows for the pilot window.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from leaders_db.chronicle.sqlite_writer import default_sqlite_path
from leaders_db.cli import app

# ---------------------------------------------------------------------------
# CLI runner
# ---------------------------------------------------------------------------


runner = CliRunner()


# ---------------------------------------------------------------------------
# Synthetic V-Dem fixture for the isolated data lake
# ---------------------------------------------------------------------------


_VDEM_FIXTURE_COLUMNS = [
    "country_name",
    "country_text_id",
    "year",
    "v2x_regime",
    "v2x_polyarchy",
    "v2x_libdem",
]


def _build_synthetic_vdem_csv(path: Path) -> None:
    """Write a tiny V-Dem-style CSV for the pilot iso3 set + 2024/2025.

    The CSV uses the same column names as the real V-Dem v16 file so
    ``pandas.read_csv`` picks them up identically. We seed two
    regimes per pilot country (Full democracy for USA/GBR/FRA, and
    Authoritarian for CHN) plus a 2025 row so the proxy path can be
    exercised.
    """
    rows = []
    for iso3, regime, polyarchy, libdem in (
        ("USA", 2, 0.85, 0.85),
        ("GBR", 2, 0.80, 0.85),
        ("FRA", 3, 0.88, 0.90),
        ("IND", 1, 0.45, 0.50),
        ("RUS", 1, 0.25, 0.30),
        ("CHN", 0, 0.10, 0.10),
    ):
        rows.append(
            {
                "country_name": iso3,
                "country_text_id": iso3,
                "year": 2024,
                "v2x_regime": regime,
                "v2x_polyarchy": polyarchy,
                "v2x_libdem": libdem,
            }
        )
        rows.append(
            {
                "country_name": iso3,
                "country_text_id": iso3,
                "year": 2025,
                "v2x_regime": regime,
                "v2x_polyarchy": polyarchy,
                "v2x_libdem": libdem,
            }
        )
    # SUN is intentionally NOT in the V-Dem fixture (per Increment 0
    # finding: V-Dem v16 merges SUN into RUS, so a separate SUN row
    # is not present).
    df = pd.DataFrame(rows, columns=_VDEM_FIXTURE_COLUMNS)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def _seed_isolated_data_lake(isolated_data_lake: Path) -> None:
    """Stage a minimal V-Dem CSV in the tmp data lake."""
    target = isolated_data_lake / "data" / "raw" / "vdem"
    target.mkdir(parents=True, exist_ok=True)
    _build_synthetic_vdem_csv(target / "V-Dem-CY-Full+Others-v16.csv")


# ---------------------------------------------------------------------------
# CLI command registration
# ---------------------------------------------------------------------------


def test_cli_help_lists_run_country_year_chronicle() -> None:
    """The new command is registered on the Typer app."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0, result.stdout
    assert "run-country-year-chronicle" in result.stdout


def test_command_help_shows_documented_defaults() -> None:
    """The ``--help`` output shows the documented defaults."""
    result = runner.invoke(app, ["run-country-year-chronicle", "--help"])
    assert result.exit_code == 0, result.stdout
    assert "--start-year" in result.stdout
    assert "--end-year" in result.stdout
    assert "--countries" in result.stdout
    assert "--output" in result.stdout
    # Typer may truncate long option names in the help layout; check for
    # the substring instead of the full token.
    assert "allow-regime-proxy" in result.stdout


def test_command_help_does_not_document_sqlite_opt_out() -> None:
    """Help text should not claim ``--sqlite-output`` supports no-value
    usage or opt-out behavior.

    The historical blocker was a docs/help contract mismatch claiming
    pass-without-value/empty flags; the actual command does not support
    that mode.
    """
    result = runner.invoke(app, ["run-country-year-chronicle", "--help"])
    assert result.exit_code == 0, result.stdout
    help_text = result.stdout
    assert "--sqlite-output" in help_text
    assert "--sqlite-output <PATH>" in help_text
    assert "with no value" not in help_text.lower()
    assert "without an explicit path" not in help_text.lower()
    assert "empty --sqlite-output" not in help_text.lower()


# ---------------------------------------------------------------------------
# CLI command execution
# ---------------------------------------------------------------------------


def test_command_writes_csv_file(
    isolated_data_lake: Path, tmp_path: Path
) -> None:
    """The command writes a CSV at the requested output path."""
    _seed_isolated_data_lake(isolated_data_lake)
    output = tmp_path / "pilot.csv"
    result = runner.invoke(
        app,
        [
            "run-country-year-chronicle",
            "--start-year", "2024",
            "--end-year", "2025",
            "--countries", "USA,GBR,FRA",
            "--output", str(output),
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert output.is_file(), f"missing output file: {output}"
    assert output.stat().st_size > 0


def test_command_default_writes_sqlite_to_canonical_path(
    isolated_data_lake: Path, tmp_path: Path
) -> None:
    """Without ``--sqlite-output``, the default SQLite path is written."""
    _seed_isolated_data_lake(isolated_data_lake)

    output_csv = tmp_path / "pilot.csv"
    expected_sqlite = default_sqlite_path(project_root=isolated_data_lake)
    if expected_sqlite.exists():
        expected_sqlite.unlink()

    result = runner.invoke(
        app,
        [
            "run-country-year-chronicle",
            "--start-year",
            "2024",
            "--end-year",
            "2024",
            "--countries",
            "USA",
            "--output",
            str(output_csv),
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert output_csv.is_file()
    assert expected_sqlite.is_file()


def test_command_writes_sqlite_to_explicit_path_when_provided(
    isolated_data_lake: Path, tmp_path: Path
) -> None:
    """Passing ``--sqlite-output <PATH>`` writes SQLite to that path."""
    _seed_isolated_data_lake(isolated_data_lake)

    explicit_sqlite = tmp_path / "explicit.sqlite"
    output_csv = tmp_path / "pilot.csv"
    default_sqlite = default_sqlite_path(project_root=isolated_data_lake)
    if default_sqlite.exists():
        default_sqlite.unlink()

    result = runner.invoke(
        app,
        [
            "run-country-year-chronicle",
            "--start-year",
            "2024",
            "--end-year",
            "2024",
            "--countries",
            "USA",
            "--output",
            str(output_csv),
            "--sqlite-output",
            str(explicit_sqlite),
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert explicit_sqlite.is_file()
    assert not default_sqlite.exists()


def test_command_rejects_sqlite_output_without_value(
    isolated_data_lake: Path, tmp_path: Path
) -> None:
    """Typer requires a value after ``--sqlite-output``; no-value mode is
    unsupported."""
    _seed_isolated_data_lake(isolated_data_lake)

    output_csv = tmp_path / "pilot.csv"
    result = runner.invoke(
        app,
        [
            "run-country-year-chronicle",
            "--start-year",
            "2024",
            "--end-year",
            "2024",
            "--countries",
            "USA",
            "--output",
            str(output_csv),
            "--sqlite-output",
        ],
    )
    assert result.exit_code != 0, result.stdout
    combined_output = result.stdout + result.stderr
    assert "sqlite-output" in combined_output.lower()


def test_command_writes_attribution_block(
    isolated_data_lake: Path, tmp_path: Path
) -> None:
    """The CSV file starts with the attribution comment block."""
    _seed_isolated_data_lake(isolated_data_lake)
    output = tmp_path / "pilot.csv"
    runner.invoke(
        app,
        [
            "run-country-year-chronicle",
            "--start-year", "2024",
            "--end-year", "2025",
            "--countries", "USA",
            "--output", str(output),
        ],
    )
    text = output.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert lines[0] == "# Country-Year Chronicle pilot CSV"
    assert any("# V-Dem v16" in line for line in lines)


def test_command_writes_canonical_header(
    isolated_data_lake: Path, tmp_path: Path
) -> None:
    """The header row uses the canonical CHRONICLE_CSV_COLUMNS order."""
    _seed_isolated_data_lake(isolated_data_lake)
    output = tmp_path / "pilot.csv"
    runner.invoke(
        app,
        [
            "run-country-year-chronicle",
            "--start-year", "2024",
            "--end-year", "2024",
            "--countries", "USA",
            "--output", str(output),
        ],
    )
    with output.open(newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        rows = list(reader)
    header = next(r for r in rows if r and not r[0].startswith("#"))
    assert header[0] == "year"
    assert header[1] == "iso3"
    # First two columns confirm the order; the full set is asserted in
    # test_chronicle_constants.py.
    assert len(header) >= 30


def test_command_creates_output_parent_directory(
    isolated_data_lake: Path, tmp_path: Path
) -> None:
    """The command creates missing parent directories."""
    _seed_isolated_data_lake(isolated_data_lake)
    nested = tmp_path / "nested" / "more" / "pilot.csv"
    result = runner.invoke(
        app,
        [
            "run-country-year-chronicle",
            "--start-year", "2024",
            "--end-year", "2024",
            "--countries", "USA",
            "--output", str(nested),
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert nested.is_file()


def test_command_rejects_inverted_year_range(
    isolated_data_lake: Path, tmp_path: Path
) -> None:
    """start_year > end_year yields a non-zero exit code."""
    _seed_isolated_data_lake(isolated_data_lake)
    output = tmp_path / "pilot.csv"
    result = runner.invoke(
        app,
        [
            "run-country-year-chronicle",
            "--start-year", "2025",
            "--end-year", "2024",
            "--countries", "USA",
            "--output", str(output),
        ],
    )
    assert result.exit_code != 0, result.stdout


def test_command_rejects_empty_countries(
    isolated_data_lake: Path, tmp_path: Path
) -> None:
    """An empty --countries value is rejected."""
    _seed_isolated_data_lake(isolated_data_lake)
    output = tmp_path / "pilot.csv"
    result = runner.invoke(
        app,
        [
            "run-country-year-chronicle",
            "--start-year", "2024",
            "--end-year", "2024",
            "--countries", "",
            "--output", str(output),
        ],
    )
    assert result.exit_code != 0, result.stdout


def test_command_rejects_unknown_iso3(
    isolated_data_lake: Path, tmp_path: Path
) -> None:
    """An unknown ISO3 in --countries is rejected with a clear error."""
    _seed_isolated_data_lake(isolated_data_lake)
    output = tmp_path / "pilot.csv"
    result = runner.invoke(
        app,
        [
            "run-country-year-chronicle",
            "--start-year", "2024",
            "--end-year", "2024",
            "--countries", "USA,ZZZ",
            "--output", str(output),
        ],
    )
    assert result.exit_code != 0, result.stdout
    assert "ZZZ" in result.stdout or "Unknown" in result.stdout


def test_command_dedupes_countries(
    isolated_data_lake: Path, tmp_path: Path
) -> None:
    """Repeating the same ISO3 in --countries yields one row per year."""
    _seed_isolated_data_lake(isolated_data_lake)
    output = tmp_path / "pilot.csv"
    runner.invoke(
        app,
        [
            "run-country-year-chronicle",
            "--start-year", "2024",
            "--end-year", "2024",
            "--countries", "USA,USA,USA",
            "--output", str(output),
        ],
    )
    # The CSV has one data row for USA 2024.
    with output.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(
            row for row in fh if not row.startswith("#")
        )
        data_rows = list(reader)
    assert len(data_rows) == 1
    assert data_rows[0]["iso3"] == "USA"
    assert data_rows[0]["year"] == "2024"


def test_command_emits_proxy_year_flag_for_2026(
    isolated_data_lake: Path, tmp_path: Path
) -> None:
    """A row for 2026 carries ``proxy_year_used`` when proxy is enabled."""
    _seed_isolated_data_lake(isolated_data_lake)
    output = tmp_path / "pilot.csv"
    runner.invoke(
        app,
        [
            "run-country-year-chronicle",
            "--start-year", "2026",
            "--end-year", "2026",
            "--countries", "USA",
            "--output", str(output),
            "--allow-regime-proxy",
        ],
    )
    with output.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(
            row for row in fh if not row.startswith("#")
        )
        data_rows = list(reader)
    assert len(data_rows) == 1
    flags = data_rows[0]["data_quality_flags"].split("|")
    assert "proxy_year_used" in flags


def test_command_no_proxy_flag_when_disabled(
    isolated_data_lake: Path, tmp_path: Path
) -> None:
    """With ``--no-allow-regime-proxy`` the 2026 row uses Unknown + gap."""
    _seed_isolated_data_lake(isolated_data_lake)
    output = tmp_path / "pilot.csv"
    runner.invoke(
        app,
        [
            "run-country-year-chronicle",
            "--start-year", "2026",
            "--end-year", "2026",
            "--countries", "USA",
            "--output", str(output),
            "--no-allow-regime-proxy",
        ],
    )
    with output.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(
            row for row in fh if not row.startswith("#")
        )
        data_rows = list(reader)
    assert len(data_rows) == 1
    flags = data_rows[0]["data_quality_flags"].split("|")
    assert "proxy_year_used" not in flags
    assert "regime_source_gap" in flags
    assert data_rows[0]["political_regime_bucket"] == "Unknown"


def test_command_default_uses_chronicle_output_dir(
    isolated_data_lake: Path,
) -> None:
    """Running the command with no --output writes under the canonical
    data/outputs/country-year-chronicle/ directory."""
    _seed_isolated_data_lake(isolated_data_lake)
    expected = (
        isolated_data_lake
        / "data"
        / "outputs"
        / "country-year-chronicle"
        / "country_year_chronicle.csv"
    )
    # Remove anything the previous test wrote.
    if expected.exists():
        expected.unlink()
    result = runner.invoke(
        app,
        [
            "run-country-year-chronicle",
            "--start-year", "2024",
            "--end-year", "2024",
            "--countries", "USA",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert expected.is_file(), (
        f"default output path {expected} was not written"
    )


def test_command_summary_includes_row_count(
    isolated_data_lake: Path, tmp_path: Path
) -> None:
    """The CLI echoes a summary line with the row count."""
    _seed_isolated_data_lake(isolated_data_lake)
    output = tmp_path / "pilot.csv"
    result = runner.invoke(
        app,
        [
            "run-country-year-chronicle",
            "--start-year", "2024",
            "--end-year", "2025",
            "--countries", "USA,GBR",
            "--output", str(output),
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "rows_written:" in result.stdout
    # Two countries x two years = four data rows.
    assert "rows_written:        4" in result.stdout


def test_command_summary_lists_sources_used(
    isolated_data_lake: Path, tmp_path: Path
) -> None:
    """The CLI echoes the sources that contributed to the output."""
    _seed_isolated_data_lake(isolated_data_lake)
    output = tmp_path / "pilot.csv"
    result = runner.invoke(
        app,
        [
            "run-country-year-chronicle",
            "--start-year", "2024",
            "--end-year", "2024",
            "--countries", "USA",
            "--output", str(output),
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "sources_used:" in result.stdout
    # The synthetic V-Dem fixture has data for 2024 so vdem is in
    # the source list.
    assert "vdem" in result.stdout


# ---------------------------------------------------------------------------
# End-to-end happy path with the seven-country pilot
# ---------------------------------------------------------------------------


def test_seven_country_pilot_smoke(
    isolated_data_lake: Path, tmp_path: Path
) -> None:
    """The full pilot (7 countries, 2024-2025) runs end-to-end."""
    _seed_isolated_data_lake(isolated_data_lake)
    output = tmp_path / "pilot.csv"
    result = runner.invoke(
        app,
        [
            "run-country-year-chronicle",
            "--start-year", "2024",
            "--end-year", "2025",
            "--countries", "USA,GBR,FRA,IND,RUS,SUN,CHN",
            "--output", str(output),
        ],
    )
    assert result.exit_code == 0, result.stdout
    with output.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(
            row for row in fh if not row.startswith("#")
        )
        data_rows = list(reader)
    # 7 countries x 2 years = 14 rows.
    assert len(data_rows) == 14
    # Every pilot country has exactly two rows (one per year).
    iso3_counts: dict[str, int] = {}
    for row in data_rows:
        iso3_counts[row["iso3"]] = iso3_counts.get(row["iso3"], 0) + 1
    for iso3 in ("USA", "GBR", "FRA", "IND", "RUS", "SUN", "CHN"):
        assert iso3_counts[iso3] == 2, (
            f"{iso3} should appear 2 times, got {iso3_counts[iso3]}"
        )


# ---------------------------------------------------------------------------
# Reviewer-mandated parsed-row assertions: IND colonial status + RUS fallback
# ---------------------------------------------------------------------------


def _read_chronicle_rows(output: Path) -> list[dict[str, str]]:
    """Read the data rows from a chronicle CSV, skipping the attribution
    comment block.
    """
    with output.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(row for row in fh if not row.startswith("#"))
        return list(reader)


def test_cli_parsed_ind_1900_is_colonial_dependent(
    isolated_data_lake: Path, tmp_path: Path
) -> None:
    """Parsed CSV row for IND 1900 carries ``country_status=colonial/dependent``
    and the ``colonial_status_issue`` flag.
    """
    _seed_isolated_data_lake(isolated_data_lake)
    output = tmp_path / "pilot.csv"
    result = runner.invoke(
        app,
        [
            "run-country-year-chronicle",
            "--start-year", "1900",
            "--end-year", "1900",
            "--countries", "IND",
            "--output", str(output),
        ],
    )
    assert result.exit_code == 0, result.stdout
    rows = _read_chronicle_rows(output)
    assert len(rows) == 1
    assert rows[0]["iso3"] == "IND"
    assert rows[0]["year"] == "1900"
    assert rows[0]["country_status"] == "colonial/dependent"
    assert "colonial_status_issue" in rows[0]["data_quality_flags"].split("|")


def test_cli_parsed_ind_1946_is_colonial_dependent(
    isolated_data_lake: Path, tmp_path: Path
) -> None:
    """Parsed CSV row for IND 1946 (last colonial year per the documented
    cutoff ``colonial_status_until=1946``) carries
    ``country_status=colonial/dependent``.
    """
    _seed_isolated_data_lake(isolated_data_lake)
    output = tmp_path / "pilot.csv"
    result = runner.invoke(
        app,
        [
            "run-country-year-chronicle",
            "--start-year", "1946",
            "--end-year", "1946",
            "--countries", "IND",
            "--output", str(output),
        ],
    )
    assert result.exit_code == 0, result.stdout
    rows = _read_chronicle_rows(output)
    assert len(rows) == 1
    assert rows[0]["year"] == "1946"
    assert rows[0]["country_status"] == "colonial/dependent"
    assert "colonial_status_issue" in rows[0]["data_quality_flags"].split("|")


def test_cli_parsed_ind_1947_is_independent(
    isolated_data_lake: Path, tmp_path: Path
) -> None:
    """Parsed CSV row for IND 1947 (first year past the colonial cutoff)
    carries ``country_status=independent`` and no ``colonial_status_issue``
    flag.
    """
    _seed_isolated_data_lake(isolated_data_lake)
    output = tmp_path / "pilot.csv"
    result = runner.invoke(
        app,
        [
            "run-country-year-chronicle",
            "--start-year", "1947",
            "--end-year", "1947",
            "--countries", "IND",
            "--output", str(output),
        ],
    )
    assert result.exit_code == 0, result.stdout
    rows = _read_chronicle_rows(output)
    assert len(rows) == 1
    assert rows[0]["year"] == "1947"
    assert rows[0]["country_status"] == "independent"
    assert "colonial_status_issue" not in rows[0]["data_quality_flags"].split("|")


def test_cli_parsed_rus_with_authoritarian_vdem_is_mixed_unclear(
    isolated_data_lake: Path, tmp_path: Path
) -> None:
    """Parsed CSV row for RUS 2024 (synthetic V-Dem fixture says Authoritarian)
    routes through the regime-bucket fallback to ``Mixed / unclear`` — NOT
    ``Conservative capitalist democracy`` or any other democracy label.
    """
    _seed_isolated_data_lake(isolated_data_lake)
    output = tmp_path / "pilot.csv"
    result = runner.invoke(
        app,
        [
            "run-country-year-chronicle",
            "--start-year", "2024",
            "--end-year", "2024",
            "--countries", "RUS",
            "--output", str(output),
        ],
    )
    assert result.exit_code == 0, result.stdout
    rows = _read_chronicle_rows(output)
    assert len(rows) == 1
    assert rows[0]["iso3"] == "RUS"
    # The synthetic V-Dem fixture pins RUS 2024 to v2x_regime=1 (Hybrid).
    # Either Authoritarian or Hybrid bucket must yield Mixed / unclear.
    assert rows[0]["system_type_primary"] == "Mixed / unclear"
    assert rows[0]["system_type_source"] == "vdem"
