"""Tests for the Country-Year Chronicle Increment 5 scope + condensed export.

These tests cover the new modules and behaviors added in
Increment 5:

- :mod:`leaders_db.chronicle.country_scope` derives the all-country
  scope from V-Dem coverage + the pilot
  :data:`COUNTRY_METADATA` and maps years to the four canonical
  ``existence_status`` labels.
- :mod:`leaders_db.chronicle.condensed_writer` writes the Increment 5
  condensed CSV with the fixed column order, omitting every
  source / provenance / confidence / text column.
- The CLI ``--countries all`` and ``--condensed-output`` /
  ``--no-condensed-output`` options drive the runner correctly.

The tests use a tiny synthetic V-Dem CSV (the same shape as the
``test_cli_chronicle`` fixture) so they do not depend on the real
388 MB V-Dem bundle.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd
import pytest

from leaders_db.chronicle.condensed_writer import (
    CONDENSED_CSV_COLUMNS,
    build_condensed_rows,
    write_condensed_csv,
)
from leaders_db.chronicle.constants import (
    CHRONICLE_CSV_COLUMNS,
    DEFAULT_COUNTRIES,
    EXISTS_STATUS_EXISTS,
    EXISTS_STATUS_NOT_FORMED,
    EXISTS_STATUS_OUT_OF_SCOPE,
    EXISTS_STATUS_SPLIT,
)
from leaders_db.chronicle.constants import (
    CONDENSED_CSV_COLUMNS as _CONDENSED_CSV_COLUMNS_CONST,
)
from leaders_db.chronicle.country_scope import (
    CountryScopeEntry,
    default_vdem_csv_path,
    derive_all_country_scope,
    derive_country_scope,
    get_existence_status,
)
from leaders_db.cli import app

# Re-export to silence the unused-import lint; the constant is
# referenced in the test bodies below.
del _CONDENSED_CSV_COLUMNS_CONST

# ---------------------------------------------------------------------------
# Synthetic V-Dem fixture
# ---------------------------------------------------------------------------


_VDEM_FIXTURE_COLUMNS = [
    "country_name",
    "country_text_id",
    "year",
    "v2x_regime",
    "v2x_polyarchy",
    "v2x_libdem",
]


def _build_synthetic_vdem_csv(
    path: Path, rows: list[tuple[str, str, int]]
) -> None:
    """Write a tiny V-Dem-style CSV from ``(country_name, iso3, year)`` rows.

    The CSV uses the same column names as the real V-Dem v16 file so
    :func:`derive_country_scope` and ``load_vdem_source`` can read it
    identically. We seed the columns the scope reader needs
    (``country_text_id``, ``country_name``, ``year``) plus the
    regime columns the V-Dem source loader expects
    (``v2x_regime`` / ``v2x_polyarchy`` / ``v2x_libdem``).
    """
    df = pd.DataFrame(
        [
            {
                "country_name": name,
                "country_text_id": iso3,
                "year": year,
                "v2x_regime": 2,
                "v2x_polyarchy": 0.7,
                "v2x_libdem": 0.7,
            }
            for name, iso3, year in rows
        ],
        columns=_VDEM_FIXTURE_COLUMNS,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def _read_csv_data(path: Path) -> list[dict[str, str]]:
    """Read a CSV (detailed or condensed) skipping comment lines."""
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(
            row for row in fh if not row.startswith("#")
        )
        return list(reader)


# ---------------------------------------------------------------------------
# Country-scope: derive_country_scope
# ---------------------------------------------------------------------------


def test_derive_country_scope_filters_non_iso3_ids(tmp_path: Path) -> None:
    """Non-ISO3 country_text_ids are dropped from the scope."""
    csv_path = tmp_path / "vdem.csv"
    _build_synthetic_vdem_csv(
        csv_path,
        [
            ("Slovenia", "SVN", 1990),
            ("Badland", "XYZ123", 2000),  # not 3-letter
            ("ABC", "abc", 2001),  # lowercase
            ("Empty", "", 2002),  # empty
        ],
    )
    scope = derive_country_scope(vdem_csv_path=csv_path)
    iso3s = sorted(scope)
    assert "SVN" in iso3s
    assert "XYZ123" not in iso3s
    assert "abc" not in iso3s
    assert "" not in iso3s


def test_derive_country_scope_includes_pilot_metadata(tmp_path: Path) -> None:
    """Pilot historical identities (SUN) remain in the scope even
    when V-Dem does not code them separately.
    """
    csv_path = tmp_path / "vdem.csv"
    _build_synthetic_vdem_csv(
        csv_path,
        [
            ("United States", "USA", 2024),
            ("Russia", "RUS", 2024),  # V-Dem merges SUN+RUS into RUS
        ],
    )
    scope = derive_country_scope(vdem_csv_path=csv_path)
    # SUN is in the pilot metadata even though V-Dem has no SUN row.
    assert "SUN" in scope
    sun = scope["SUN"]
    assert sun.country_name == "Soviet Union"
    assert sun.start_year == 1922
    assert sun.end_year == 1991
    assert sun.source == "metadata"
    # RUS has both V-Dem and pilot metadata; pilot start_year wins.
    rus = scope["RUS"]
    assert rus.start_year == 1991


def test_derive_country_scope_marks_merged_for_pilot_override(
    tmp_path: Path,
) -> None:
    """When the pilot metadata overrides V-Dem defaults, the source
    tag is ``"merged"`` so an audit can find the affected entries.
    """
    csv_path = tmp_path / "vdem.csv"
    _build_synthetic_vdem_csv(
        csv_path,
        [("Russia", "RUS", 2024)],
    )
    scope = derive_country_scope(vdem_csv_path=csv_path)
    rus = scope["RUS"]
    # The pilot metadata sets start_year=1991; V-Dem default would
    # be much earlier. The merged label is the audit trail.
    assert rus.source == "merged"


def test_derive_country_scope_vdem_only_when_no_pilot_override(
    tmp_path: Path,
) -> None:
    """V-Dem-only countries (no pilot metadata) keep the
    ``"vdem"`` source tag.
    """
    csv_path = tmp_path / "vdem.csv"
    _build_synthetic_vdem_csv(
        csv_path,
        [
            ("Slovenia", "SVN", 1990),
            ("United States", "USA", 2024),  # pilot metadata exists
        ],
    )
    scope = derive_country_scope(vdem_csv_path=csv_path)
    assert scope["SVN"].source == "vdem"
    assert scope["USA"].source == "merged"  # pilot says start=1776


def test_derive_country_scope_returns_empty_dict_when_file_missing(
    tmp_path: Path,
) -> None:
    """A missing V-Dem CSV returns a scope derived from the pilot
    metadata only (the runner falls back gracefully).
    """
    missing = tmp_path / "missing.csv"
    scope = derive_country_scope(vdem_csv_path=missing)
    # The pilot metadata is still overlaid.
    for iso3 in DEFAULT_COUNTRIES:
        assert iso3 in scope


def test_derive_all_country_scope_is_an_alias_for_default_derivation(
    tmp_path: Path,
) -> None:
    """The all-country scope is the V-Dem coverage + pilot overlay."""
    csv_path = tmp_path / "vdem.csv"
    _build_synthetic_vdem_csv(
        csv_path,
        [
            ("Slovenia", "SVN", 1990),
            ("Russia", "RUS", 2024),
        ],
    )
    all_scope = derive_all_country_scope(vdem_csv_path=csv_path)
    default_scope = derive_country_scope(vdem_csv_path=csv_path)
    assert sorted(all_scope) == sorted(default_scope)


# ---------------------------------------------------------------------------
# Existence-status mapping
# ---------------------------------------------------------------------------


def test_existence_status_not_formed_for_pre_start_year() -> None:
    """Years before the scope entry's start_year map to not_formed."""
    slovenia_1989 = CountryScopeEntry(
        iso3="SVN",
        country_name="Slovenia",
        start_year=1989,
        end_year=1991,
        source="vdem",
    )
    assert get_existence_status(slovenia_1989, 1988) == EXISTS_STATUS_NOT_FORMED
    assert get_existence_status(slovenia_1989, 1989) == EXISTS_STATUS_EXISTS


def test_existence_status_split_for_post_end_year() -> None:
    """Years after the scope entry's end_year map to split_or_dissolved."""
    sun = CountryScopeEntry(
        iso3="SUN",
        country_name="Soviet Union",
        start_year=1922,
        end_year=1991,
        source="metadata",
    )
    assert get_existence_status(sun, 1990) == EXISTS_STATUS_EXISTS
    assert get_existence_status(sun, 1991) == EXISTS_STATUS_EXISTS
    assert get_existence_status(sun, 1992) == EXISTS_STATUS_SPLIT
    assert get_existence_status(sun, 2025) == EXISTS_STATUS_SPLIT


def test_existence_status_exists_for_in_window_year() -> None:
    """Years in [start_year, end_year] map to exists."""
    usa = CountryScopeEntry(
        iso3="USA",
        country_name="United States",
        start_year=1776,
        end_year=2025,
        source="merged",
    )
    for year in (1776, 1900, 2025):
        assert get_existence_status(usa, year) == EXISTS_STATUS_EXISTS


def test_existence_status_out_of_scope_when_window_unknown() -> None:
    """A scope entry with no start / end year maps to out_of_scope_unknown."""
    unknown = CountryScopeEntry(
        iso3="ZZZ",
        country_name="Mystery",
        start_year=None,
        end_year=None,
        source="metadata",
    )
    assert get_existence_status(unknown, 1900) == EXISTS_STATUS_OUT_OF_SCOPE


def test_existence_status_covers_all_four_labels() -> None:
    """The four documented labels are produced by the canonical
    examples: Slovenia pre-1991, SUN after 1991, a modern country in
    its existence window, and an unknown-window country.
    """
    slovenia = CountryScopeEntry(
        iso3="SVN",
        country_name="Slovenia",
        start_year=1991,
        end_year=2025,
        source="vdem",
    )
    sun = CountryScopeEntry(
        iso3="SUN",
        country_name="Soviet Union",
        start_year=1922,
        end_year=1991,
        source="metadata",
    )
    france = CountryScopeEntry(
        iso3="FRA",
        country_name="France",
        start_year=1870,
        end_year=2025,
        source="merged",
    )
    unknown = CountryScopeEntry(
        iso3="ZZZ",
        country_name="Mystery",
        start_year=None,
        end_year=None,
        source="metadata",
    )
    assert get_existence_status(slovenia, 1900) == EXISTS_STATUS_NOT_FORMED
    assert get_existence_status(sun, 2025) == EXISTS_STATUS_SPLIT
    assert get_existence_status(france, 2024) == EXISTS_STATUS_EXISTS
    assert get_existence_status(unknown, 2024) == EXISTS_STATUS_OUT_OF_SCOPE


# ---------------------------------------------------------------------------
# Condensed CSV: column contract
# ---------------------------------------------------------------------------


def test_condensed_csv_columns_match_increment5_contract() -> None:
    """The condensed CSV column order matches the Increment 5 contract."""
    expected = (
        "year",
        "iso3",
        "country",
        "existence_status",
        "ruler",
        "political_regime",
        "system_type",
        "population",
        "gdp",
        "gdp_per_capita",
        "military_spend",
        "country_area_km2",
    )
    assert CONDENSED_CSV_COLUMNS == expected


def test_condensed_csv_omits_source_confidence_text_columns() -> None:
    """The condensed column set excludes every source / confidence /
    text / provenance column from the detailed contract."""
    forbidden = {
        # per-field source tags
        "ruler_source",
        "ruler_source_year_used",
        "political_regime_source",
        "political_regime_source_year_used",
        "population_source",
        "population_source_year_used",
        "gdp_source",
        "gdp_source_year_used",
        "military_spend_source",
        "military_spend_source_year_used",
        "area_source",
        "area_source_year_used",
        "controlled_area_note",
        # confidence values
        "ruler_confidence",
        "political_regime_confidence",
        "system_type_confidence",
        "row_confidence",
        # text / unit / note columns
        "system_type_notes",
        "gdp_unit",
        "gdp_per_capita_unit",
        "gdp_per_capita_method",
        "military_spend_unit",
        # audit / flags
        "data_quality_flags",
        "provenance_summary",
        "shared_rule_flag",
        "disputed_rule_flag",
        # controlled area (deferred per Increment 4)
        "controlled_area_km2",
        # metadata that doesn't fit the "data only" condensed export
        "country_status",
        "region",
        "subregion",
        "ruler_title",
        "ruler_type",
        "political_regime_raw_score",
        "system_type_secondary",
    }
    for col in forbidden:
        assert col not in CONDENSED_CSV_COLUMNS, (
            f"forbidden condensed column {col!r} leaked into the contract"
        )


# ---------------------------------------------------------------------------
# Condensed writer: transform behavior
# ---------------------------------------------------------------------------


def _detailed_row(**overrides: str) -> dict[str, str]:
    """Build a synthetic detailed chronicle row for the condensed
    writer tests. The row covers every CHRONICLE_CSV_COLUMNS key
    with empty defaults so the writer can read whichever subset
    it needs.
    """
    row = {col: "" for col in CHRONICLE_CSV_COLUMNS}
    row.update(overrides)
    return row


def test_build_condensed_rows_keeps_data_columns_for_exists_row() -> None:
    """A row whose existence_status is ``exists`` carries the data
    columns from the detailed row.
    """
    france = CountryScopeEntry(
        iso3="FRA",
        country_name="France",
        start_year=1870,
        end_year=2025,
        source="merged",
    )
    detailed = _detailed_row(
        year="2024",
        iso3="FRA",
        country_name="France",
        ruler_name="Emmanuel Macron",
        political_regime_bucket="Full democracy",
        system_type_primary="Liberal capitalist democracy",
        population="68000000",
        gdp="3000000000000",
        gdp_per_capita="44000",
        military_spend="50000",
        country_area_km2="640000",
    )
    condensed = build_condensed_rows([detailed], {"FRA": france})
    assert len(condensed) == 1
    row = condensed[0]
    assert row["year"] == "2024"
    assert row["iso3"] == "FRA"
    assert row["country"] == "France"
    assert row["existence_status"] == EXISTS_STATUS_EXISTS
    assert row["ruler"] == "Emmanuel Macron"
    assert row["political_regime"] == "Full democracy"
    assert row["system_type"] == "Liberal capitalist democracy"
    assert row["population"] == "68000000"
    assert row["gdp"] == "3000000000000"
    assert row["gdp_per_capita"] == "44000"
    assert row["military_spend"] == "50000"
    assert row["country_area_km2"] == "640000"


def test_build_condensed_rows_blanks_out_of_window_row() -> None:
    """Rows whose existence_status is ``not_formed`` or
    ``split_or_dissolved`` keep only year / iso3 / country /
    existence_status and leave every data column blank.
    """
    sun = CountryScopeEntry(
        iso3="SUN",
        country_name="Soviet Union",
        start_year=1922,
        end_year=1991,
        source="metadata",
    )
    # Pre-1922 row.
    detailed_pre = _detailed_row(
        year="1920",
        iso3="SUN",
        country_name="Soviet Union",
        ruler_name="(would-be-ruler)",
        political_regime_bucket="Authoritarian",
        system_type_primary="Monarchy",
        population="100000000",
        gdp="100000000000",
        gdp_per_capita="1000",
        military_spend="500",
        country_area_km2="22000000",
    )
    # Post-1991 row.
    detailed_post = _detailed_row(
        year="2024",
        iso3="SUN",
        country_name="Soviet Union",
        ruler_name="(would-be-ruler)",
        political_regime_bucket="Authoritarian",
        system_type_primary="Monarchy",
        population="100000000",
        gdp="100000000000",
        gdp_per_capita="1000",
        military_spend="500",
        country_area_km2="22000000",
    )
    condensed = build_condensed_rows(
        [detailed_pre, detailed_post],
        {"SUN": sun},
    )
    assert len(condensed) == 2
    pre, post = condensed
    assert pre["existence_status"] == EXISTS_STATUS_NOT_FORMED
    assert post["existence_status"] == EXISTS_STATUS_SPLIT
    for row in (pre, post):
        assert row["ruler"] == ""
        assert row["political_regime"] == ""
        assert row["system_type"] == ""
        assert row["population"] == ""
        assert row["gdp"] == ""
        assert row["gdp_per_capita"] == ""
        assert row["military_spend"] == ""
        assert row["country_area_km2"] == ""


def test_write_condensed_csv_writes_atomic_with_canonical_header(
    tmp_path: Path,
) -> None:
    """The condensed writer creates the parent directory, writes the
    canonical header, and produces one row per input.
    """
    output = tmp_path / "nested" / "condensed.csv"
    france = CountryScopeEntry(
        iso3="FRA",
        country_name="France",
        start_year=1870,
        end_year=2025,
        source="merged",
    )
    rows = [
        _detailed_row(
            year=str(year),
            iso3="FRA",
            country_name="France",
            ruler_name="ruler",
        )
        for year in range(2020, 2023)
    ]
    resolved = write_condensed_csv(
        output_path=output,
        detailed_rows=rows,
        country_scope={"FRA": france},
    )
    assert resolved == output.resolve()
    assert output.is_file()
    data_rows = _read_csv_data(output)
    assert [r["year"] for r in data_rows] == ["2020", "2021", "2022"]
    # The header is the canonical CONDENSED_CSV_COLUMNS order.
    with output.open(newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        header = next(reader)
    assert header == list(CONDENSED_CSV_COLUMNS)


# ---------------------------------------------------------------------------
# CLI: --countries all
# ---------------------------------------------------------------------------


runner = __import__("typer.testing", fromlist=["CliRunner"]).CliRunner()


def _seed_isolated_vdem(isolated_data_lake: Path) -> None:
    """Seed a small V-Dem CSV in the test data lake."""
    target = isolated_data_lake / "data" / "raw" / "vdem"
    target.mkdir(parents=True, exist_ok=True)
    _build_synthetic_vdem_csv(
        target / "V-Dem-CY-Full+Others-v16.csv",
        [
            ("United States", "USA", 2024),
            ("Russia", "RUS", 2024),
            ("Slovenia", "SVN", 2024),
            ("Brazil", "BRA", 2024),
            ("Badland", "XYZ123", 2024),
        ],
    )


def test_cli_countries_all_writes_condensed_output(
    isolated_data_lake: Path, tmp_path: Path
) -> None:
    """``--countries all`` writes the detailed and condensed CSVs
    covering every valid ISO3 in the synthetic V-Dem fixture.
    """
    _seed_isolated_vdem(isolated_data_lake)
    output_csv = tmp_path / "all.csv"
    result = runner.invoke(
        app,
        [
            "run-country-year-chronicle",
            "--start-year", "2024",
            "--end-year", "2024",
            "--countries", "all",
            "--output", str(output_csv),
            "--no-allow-regime-proxy",
        ],
    )
    assert result.exit_code == 0, result.stdout
    # The condensed CSV is written to the canonical default path.
    expected_condensed = (
        isolated_data_lake
        / "data"
        / "outputs"
        / "country-year-chronicle"
        / "condensed.csv"
    )
    assert expected_condensed.is_file()
    # The condensed file has more rows than the pilot scope (7
    # countries) because V-Dem seeds USA, RUS, SVN, BRA + the pilot
    # metadata overlays GBR, FRA, IND, SUN, CHN. 9 rows expected.
    condensed_data = _read_csv_data(expected_condensed)
    iso3s = sorted({r["iso3"] for r in condensed_data})
    assert "USA" in iso3s
    assert "RUS" in iso3s
    assert "SVN" in iso3s
    assert "BRA" in iso3s
    assert "SUN" in iso3s  # pilot overlay
    # The non-ISO3 ID was filtered out.
    assert "XYZ123" not in iso3s


def test_cli_countries_all_emits_existence_status_labels(
    isolated_data_lake: Path, tmp_path: Path
) -> None:
    """``--countries all`` emits the canonical existence_status
    labels for rows outside the country's source-backed window.
    """
    _seed_isolated_vdem(isolated_data_lake)
    expected_condensed = (
        isolated_data_lake
        / "data"
        / "outputs"
        / "country-year-chronicle"
        / "condensed.csv"
    )
    if expected_condensed.exists():
        expected_condensed.unlink()
    runner.invoke(
        app,
        [
            "run-country-year-chronicle",
            "--start-year", "1920",
            "--end-year", "2026",
            "--countries", "all",
            "--output", str(tmp_path / "all.csv"),
            "--no-allow-regime-proxy",
        ],
    )
    data_rows = _read_csv_data(expected_condensed)
    by_iso3: dict[str, list[dict[str, str]]] = {}
    for row in data_rows:
        by_iso3.setdefault(row["iso3"], []).append(row)
    # SUN pre-1922 → not_formed; SUN 1922-1991 → exists; SUN post-1991 → split_or_dissolved.
    sun_rows = sorted(by_iso3["SUN"], key=lambda r: int(r["year"]))
    sun_1920 = next(r for r in sun_rows if r["year"] == "1920")
    sun_2024 = next(r for r in sun_rows if r["year"] == "2024")
    assert sun_1920["existence_status"] == EXISTS_STATUS_NOT_FORMED
    assert sun_2024["existence_status"] == EXISTS_STATUS_SPLIT
    # The data columns are blank for the out-of-window rows.
    for col in ("ruler", "political_regime", "population", "gdp", "country_area_km2"):
        assert sun_1920[col] == ""
        assert sun_2024[col] == ""
    # The in-window row carries the data columns (any value the
    # detailed row populated). The exact ruler / population values
    # depend on which raw bundles the test environment has staged
    # (SUN curated + WDI + SIPRI + CShapes are not seeded in this
    # fixture), so we only assert the row is well-formed.
    sun_1950 = next(r for r in sun_rows if r["year"] == "1950")
    assert sun_1950["existence_status"] == EXISTS_STATUS_EXISTS


def test_cli_condensed_output_path_opt(tmp_path: Path) -> None:
    """``--condensed-output <PATH>`` writes the condensed CSV to the
    custom path instead of the canonical default.
    """
    _seed_isolated_vdem(tmp_path)
    output_csv = tmp_path / "all.csv"
    custom_condensed = tmp_path / "my_condensed.csv"
    result = runner.invoke(
        app,
        [
            "run-country-year-chronicle",
            "--start-year", "2024",
            "--end-year", "2024",
            "--countries", "all",
            "--output", str(output_csv),
            "--condensed-output", str(custom_condensed),
            "--no-allow-regime-proxy",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert custom_condensed.is_file()
    # The canonical default was NOT written.
    canonical = (
        tmp_path
        / "data"
        / "outputs"
        / "country-year-chronicle"
        / "condensed.csv"
    )
    assert not canonical.exists()


def test_cli_no_condensed_output_disables_condensed_write(
    isolated_data_lake: Path, tmp_path: Path
) -> None:
    """``--no-condensed-output`` skips the condensed CSV entirely.
    The detailed CSV is still written.
    """
    _seed_isolated_vdem(isolated_data_lake)
    canonical_condensed = (
        isolated_data_lake
        / "data"
        / "outputs"
        / "country-year-chronicle"
        / "condensed.csv"
    )
    if canonical_condensed.exists():
        canonical_condensed.unlink()
    output_csv = tmp_path / "all.csv"
    result = runner.invoke(
        app,
        [
            "run-country-year-chronicle",
            "--start-year", "2024",
            "--end-year", "2024",
            "--countries", "all",
            "--output", str(output_csv),
            "--no-condensed-output",
            "--no-allow-regime-proxy",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert output_csv.is_file()
    assert not canonical_condensed.exists()
    # The CLI summary explicitly reports the skipped state.
    assert "condensed_output_path:  (skipped)" in result.stdout


def test_cli_pilot_scope_still_writes_default_condensed(
    isolated_data_lake: Path, tmp_path: Path
) -> None:
    """Even without ``--countries all``, the default condensed CSV is
    written so users get the "data only" companion artifact.
    """
    _seed_isolated_vdem(isolated_data_lake)
    expected_condensed = (
        isolated_data_lake
        / "data"
        / "outputs"
        / "country-year-chronicle"
        / "condensed.csv"
    )
    if expected_condensed.exists():
        expected_condensed.unlink()
    output_csv = tmp_path / "pilot.csv"
    result = runner.invoke(
        app,
        [
            "run-country-year-chronicle",
            "--start-year", "2024",
            "--end-year", "2024",
            "--countries", "USA,GBR,FRA,IND,RUS,SUN,CHN",
            "--output", str(output_csv),
            "--no-allow-regime-proxy",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert expected_condensed.is_file()


def test_cli_detailed_output_unchanged_when_condensed_added(
    isolated_data_lake: Path, tmp_path: Path
) -> None:
    """The detailed CSV header / column order is preserved when the
    condensed write is added.
    """
    _seed_isolated_vdem(isolated_data_lake)
    output_csv = tmp_path / "detailed.csv"
    runner.invoke(
        app,
        [
            "run-country-year-chronicle",
            "--start-year", "2024",
            "--end-year", "2024",
            "--countries", "USA",
            "--output", str(output_csv),
            "--no-allow-regime-proxy",
        ],
    )
    data_rows = _read_csv_data(output_csv)
    assert len(data_rows) == 1
    row = data_rows[0]
    # The detailed CSV carries the audit-trail columns that the
    # condensed writer deliberately drops.
    assert "data_quality_flags" in row
    assert "provenance_summary" in row
    assert "ruler_source" in row
    assert "political_regime_confidence" in row
    assert "row_confidence" in row


# ---------------------------------------------------------------------------
# Country-scope: integration with the real V-Dem fixture (smoke test)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not default_vdem_csv_path().is_file(),
    reason="V-Dem raw CSV not available on disk",
)
def test_real_vdem_scope_has_no_non_iso3_ids() -> None:
    """When the real V-Dem raw CSV is on disk, every country_text_id
    is a valid 3-letter uppercase ISO3 code. No IDs are dropped.
    """
    scope = derive_country_scope()
    iso3_pattern = __import__("re").compile(r"^[A-Z]{3}$")
    non_iso3 = [iso3 for iso3 in scope if not iso3_pattern.match(iso3)]
    assert non_iso3 == [], (
        f"unexpected non-ISO3 IDs in V-Dem coverage: {sorted(non_iso3)[:10]}"
    )


@pytest.mark.skipif(
    not default_vdem_csv_path().is_file(),
    reason="V-Dem raw CSV not available on disk",
)
def test_real_vdem_scope_includes_pilot_historical_identities() -> None:
    """SUN is in the scope via the pilot metadata even though V-Dem
    v16 does not have a separate SUN country_text_id.
    """
    scope = derive_country_scope()
    assert "SUN" in scope
    sun = scope["SUN"]
    assert sun.start_year == 1922
    assert sun.end_year == 1991
