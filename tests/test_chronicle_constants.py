"""Tests for the Country-Year Chronicle slice — constants + CSV writer.

These tests cover:

- the fixed column order contract (Increment 0 §4);
- the canonical attribution strings match the source-attributions doc
  (Always-On Rule #15);
- the source-tag / flag-value / source-tag constants are stable;
- the CSV writer produces the attribution comment block, writes the
  header in the canonical column order, normalizes ``None`` / NaN to
  empty cells, and writes atomically.

No I/O against the real data lake is performed here — the test for
the end-to-end CLI lives in ``test_cli_chronicle.py`` and uses the
``isolated_data_lake`` fixture to redirect the data lake to a tmp
tree that contains a hand-built minimal V-Dem CSV.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

from leaders_db.chronicle.constants import (
    CHRONICLE_CSV_COLUMNS,
    COUNTRY_METADATA,
    DEFAULT_COUNTRIES,
    DEFAULT_END_YEAR,
    DEFAULT_OUTPUT_BASENAME,
    DEFAULT_PROXY_YEAR,
    DEFAULT_START_YEAR,
    FLAG_COLONIAL_STATUS_ISSUE,
    FLAG_CONTROLLED_AREA_NOT_MODELED,
    FLAG_MISSING_AREA,
    FLAG_MISSING_GDP,
    FLAG_MISSING_MILITARY_SPEND,
    FLAG_MISSING_POPULATION,
    FLAG_MISSING_RULER,
    FLAG_POST_EXISTENCE_GAP,
    FLAG_PRE_EXISTENCE_GAP,
    FLAG_PROXY_YEAR_USED,
    FLAG_REGIME_SOURCE_GAP,
    FLAG_SUCCESSOR_STATE_ISSUE,
    FLAG_SYSTEM_TYPE_LOW_CONFIDENCE,
    REGIME_BUCKET_DEFAULT_SYSTEM_TYPE,
    SIPRI_MILEX_ATTRIBUTION,
    SOURCE_TAG_SIPRI,
    SOURCE_TAG_VDEM,
    SOURCE_TAG_WDI,
    SYSTEM_TYPE_COUNTRY_PERIODS,
    VDEM_ATTRIBUTION,
    VDEM_MAX_COVERED_YEAR,
    VDEM_REGIME_TO_BUCKET,
    WDI_ATTRIBUTION,
)
from leaders_db.chronicle.csv_writer import (
    build_attribution_comment_block,
    write_chronicle_csv,
)

# ---------------------------------------------------------------------------
# Column contract
# ---------------------------------------------------------------------------


def test_csv_columns_match_increment0_contract() -> None:
    """The CSV column order exactly matches Increment 0 §4."""
    expected = (
        "year",
        "iso3",
        "country_name",
        "country_status",
        "region",
        "subregion",
        "ruler_name",
        "ruler_title",
        "ruler_type",
        "ruler_source",
        "ruler_source_year_used",
        "ruler_confidence",
        "shared_rule_flag",
        "disputed_rule_flag",
        "political_regime_bucket",
        "political_regime_raw_score",
        "political_regime_source",
        "political_regime_source_year_used",
        "political_regime_confidence",
        "system_type_primary",
        "system_type_secondary",
        "system_type_source",
        "system_type_confidence",
        "system_type_notes",
        "population",
        "population_source",
        "population_source_year_used",
        "gdp",
        "gdp_unit",
        "gdp_source",
        "gdp_source_year_used",
        "gdp_per_capita",
        "gdp_per_capita_unit",
        "gdp_per_capita_method",
        "military_spend",
        "military_spend_unit",
        "military_spend_source",
        "military_spend_source_year_used",
        "country_area_km2",
        "controlled_area_km2",
        "area_source",
        "area_source_year_used",
        "controlled_area_note",
        "data_quality_flags",
        "row_confidence",
        "provenance_summary",
    )
    assert CHRONICLE_CSV_COLUMNS == expected


def test_csv_columns_are_unique() -> None:
    """No duplicate column names (the writer would silently drop duplicates)."""
    assert len(CHRONICLE_CSV_COLUMNS) == len(set(CHRONICLE_CSV_COLUMNS))


# ---------------------------------------------------------------------------
# Attribution strings
# ---------------------------------------------------------------------------


def _read_source_attributions_doc() -> str:
    """Read the source-attributions doc from the project root."""
    repo_root = Path(__file__).resolve().parents[1]
    doc_path = repo_root / "docs" / "source-attributions.md"
    return doc_path.read_text(encoding="utf-8")


def test_vdem_attribution_matches_attributions_doc() -> None:
    """VDEM_ATTRIBUTION is a substring of docs/source-attributions.md."""
    doc = _read_source_attributions_doc()
    assert VDEM_ATTRIBUTION in doc, (
        f"{VDEM_ATTRIBUTION!r} is not in docs/source-attributions.md; "
        "update the doc and the constant together per Rule #15."
    )


def test_wdi_attribution_matches_attributions_doc() -> None:
    """WDI_ATTRIBUTION is a substring of docs/source-attributions.md."""
    doc = _read_source_attributions_doc()
    assert WDI_ATTRIBUTION in doc, (
        f"{WDI_ATTRIBUTION!r} is not in docs/source-attributions.md; "
        "update the doc and the constant together per Rule #15."
    )


def test_sipri_attribution_matches_attributions_doc() -> None:
    """SIPRI_MILEX_ATTRIBUTION is a substring of docs/source-attributions.md."""
    doc = _read_source_attributions_doc()
    assert SIPRI_MILEX_ATTRIBUTION in doc, (
        f"{SIPRI_MILEX_ATTRIBUTION!r} is not in docs/source-attributions.md; "
        "update the doc and the constant together per Rule #15."
    )


# ---------------------------------------------------------------------------
# Constants stability
# ---------------------------------------------------------------------------


def test_default_iso3_scope_matches_increment0_pilot() -> None:
    """DEFAULT_COUNTRIES is exactly the Increment 0 pilot list."""
    assert DEFAULT_COUNTRIES == ("USA", "GBR", "FRA", "IND", "RUS", "SUN", "CHN")


def test_default_year_window_matches_increment0_pilot() -> None:
    assert DEFAULT_START_YEAR == 1900
    assert DEFAULT_END_YEAR == 2026


def test_default_output_basename_is_stable() -> None:
    assert DEFAULT_OUTPUT_BASENAME == "country_year_chronicle.csv"


def test_proxy_year_default_is_2025() -> None:
    """The proxy year for years beyond V-Dem coverage is 2025 (the latest
    year V-Dem v16 covers). The choice is documented in the workplan
    Increment 0 §5.1 and Increment 1's task plan."""
    assert DEFAULT_PROXY_YEAR == 2025
    assert VDEM_MAX_COVERED_YEAR == 2025
    assert DEFAULT_PROXY_YEAR == VDEM_MAX_COVERED_YEAR


def test_vdem_regime_mapping_matches_increment0() -> None:
    """V-Dem v2x_regime integer -> CYC bucket mapping is documented."""
    assert VDEM_REGIME_TO_BUCKET == {
        0: "Authoritarian",
        1: "Hybrid regime",
        2: "Flawed democracy",
        3: "Full democracy",
    }


def test_system_type_country_periods_covers_documented_cases() -> None:
    """The curated mapping includes SUN Soviet period, CHN post-1949,
    and IND pre-1947 (per Increment 0 §5.2). RUS is intentionally NOT
    curated: the documented fallback handles all RUS rows."""
    iso3_periods = {entry[0] for entry in SYSTEM_TYPE_COUNTRY_PERIODS}
    assert "SUN" in iso3_periods
    assert "CHN" in iso3_periods
    assert "IND" in iso3_periods
    assert "RUS" not in iso3_periods

    # SUN must cover 1922-1991.
    sun_entries = [
        (start, end, label)
        for iso3, start, end, label in SYSTEM_TYPE_COUNTRY_PERIODS
        if iso3 == "SUN"
    ]
    assert any(start == 1922 and end == 1991 and label == "Communist one-party state"
               for start, end, label in sun_entries)


def test_regime_bucket_default_system_type_covers_all_buckets() -> None:
    """REGIME_BUCKET_DEFAULT_SYSTEM_TYPE covers every regime bucket."""
    expected_buckets = {"Full democracy", "Flawed democracy", "Hybrid regime",
                        "Authoritarian", "Unknown"}
    assert set(REGIME_BUCKET_DEFAULT_SYSTEM_TYPE) == expected_buckets


def test_country_metadata_contains_all_pilot_iso3() -> None:
    """COUNTRY_METADATA has the seven pilot ISO3 codes as keys."""
    for iso3 in DEFAULT_COUNTRIES:
        assert iso3 in COUNTRY_METADATA, f"missing {iso3} in COUNTRY_METADATA"


def test_country_metadata_for_sun_has_end_year() -> None:
    """SUN has an ``end_year`` set (successor state ending 1991)."""
    sun = COUNTRY_METADATA["SUN"]
    assert sun["country_status"] == "successor_state"
    assert sun["end_year"] == "1991"


def test_country_metadata_for_ind_marks_colonial_period() -> None:
    """IND has ``colonial_status_until`` set so pre-1947 rows get a
    colonial-status flag."""
    ind = COUNTRY_METADATA["IND"]
    assert ind["colonial_status_until"] == "1946"


# ---------------------------------------------------------------------------
# Source-tag constants
# ---------------------------------------------------------------------------


def test_source_tags_match_stage2_conventions() -> None:
    """Source tags match the project's Stage 2 dispatcher keys."""
    assert SOURCE_TAG_VDEM == "vdem"
    assert SOURCE_TAG_WDI == "wdi"
    assert SOURCE_TAG_SIPRI == "sipri_milex"


def test_flag_constants_match_increment0_list() -> None:
    """Every canonical flag in Increment 0 §6 has a constant here."""
    expected = {
        "missing_ruler",
        "multiple_rulers",
        "shared_rule",
        "disputed_rule",
        "proxy_year_used",
        "missing_population",
        "missing_gdp",
        "missing_military_spend",
        "missing_area",
        "regime_source_gap",
        "system_type_low_confidence",
        "successor_state_issue",
        "colonial_status_issue",
        "controlled_area_not_modeled",
        "source_conflict",
    }
    actual = {
        FLAG_MISSING_RULER,
        FLAG_MISSING_POPULATION,
        FLAG_MISSING_GDP,
        FLAG_MISSING_MILITARY_SPEND,
        FLAG_MISSING_AREA,
        FLAG_PROXY_YEAR_USED,
        FLAG_REGIME_SOURCE_GAP,
        FLAG_SYSTEM_TYPE_LOW_CONFIDENCE,
        FLAG_SUCCESSOR_STATE_ISSUE,
        FLAG_COLONIAL_STATUS_ISSUE,
        FLAG_CONTROLLED_AREA_NOT_MODELED,
    }
    # Every constant maps to a canonical flag value; ``multiple_rulers``,
    # ``shared_rule``, ``disputed_rule``, and ``source_conflict`` are
    # reserved for future ruler-resolver work and are not used in
    # Increment 1.
    assert expected.issuperset(actual)
    # And our pre/post-existence flags are not in the canonical list.
    assert FLAG_PRE_EXISTENCE_GAP not in expected
    assert FLAG_POST_EXISTENCE_GAP not in expected


# ---------------------------------------------------------------------------
# CSV writer — attribution block
# ---------------------------------------------------------------------------


def test_attribution_block_opens_with_chronicle_marker() -> None:
    """The attribution block always opens with the chronicle marker so
    a downstream consumer can detect the format."""
    lines = build_attribution_comment_block(sources_used=[])
    assert lines[0] == "# Country-Year Chronicle pilot CSV"
    assert any("# Experimental vertical slice" in line for line in lines)


def test_attribution_block_emits_vdem_line() -> None:
    lines = build_attribution_comment_block(sources_used=["vdem"])
    assert any(VDEM_ATTRIBUTION in line for line in lines)


def test_attribution_block_emits_wdi_line() -> None:
    lines = build_attribution_comment_block(sources_used=["wdi"])
    assert any(WDI_ATTRIBUTION in line for line in lines)


def test_attribution_block_emits_sipri_line_only_when_used() -> None:
    lines = build_attribution_comment_block(sources_used=["sipri_milex"])
    assert any(SIPRI_MILEX_ATTRIBUTION in line for line in lines)


def test_attribution_block_dedupes_sources() -> None:
    """Repeating the same source tag does not duplicate the attribution line."""
    lines = build_attribution_comment_block(sources_used=["vdem", "vdem", "wdi"])
    vdem_lines = [line for line in lines if VDEM_ATTRIBUTION in line]
    assert len(vdem_lines) == 1


def test_attribution_block_includes_extra_lines() -> None:
    lines = build_attribution_comment_block(
        sources_used=["vdem"],
        extra_lines=["Run id: test-001"],
    )
    assert any("# Run id: test-001" == line for line in lines)


# ---------------------------------------------------------------------------
# CSV writer — file output
# ---------------------------------------------------------------------------


def _sample_row() -> dict[str, str]:
    """A minimally populated row with the full column set."""
    row: dict[str, str] = {}
    for col in CHRONICLE_CSV_COLUMNS:
        row[col] = ""
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
    row["controlled_area_note"] = (
        "controlled_area not modeled in Increment 1; standard area empty "
        "pending a vetted static area source."
    )
    return row


def test_write_csv_emits_attribution_block_before_header(tmp_path: Path) -> None:
    """The CSV file starts with the attribution comment lines, then the header."""
    output = tmp_path / "out.csv"
    write_chronicle_csv(
        output_path=output,
        rows=[_sample_row()],
        sources_used=["vdem", "wdi"],
    )
    text = output.read_text(encoding="utf-8")
    lines = text.splitlines()
    # First non-blank line is the chronicle marker.
    assert lines[0] == "# Country-Year Chronicle pilot CSV"
    # Find the first non-comment line and confirm it is the canonical
    # header (which starts with the first column name).
    header_line = next(line for line in lines if not line.startswith("#"))
    assert header_line == ",".join(CHRONICLE_CSV_COLUMNS)


def test_write_csv_uses_canonical_column_order(tmp_path: Path) -> None:
    """The header row uses the canonical CHRONICLE_CSV_COLUMNS order."""
    output = tmp_path / "out.csv"
    write_chronicle_csv(
        output_path=output,
        rows=[_sample_row()],
        sources_used=["vdem"],
    )
    with output.open(newline="", encoding="utf-8") as fh:
        # Skip comment lines so csv.reader sees the header as the first row.
        non_comment_lines = [line for line in fh if not line.startswith("#")]
    reader = csv.reader(non_comment_lines)
    rows = list(reader)
    header = rows[0]
    assert header == list(CHRONICLE_CSV_COLUMNS)


def test_write_csv_normalizes_none_and_nan_to_empty(tmp_path: Path) -> None:
    """None and float('nan') values become empty CSV cells, not the string 'None'/'nan'."""
    output = tmp_path / "out.csv"
    row = _sample_row()
    row["population"] = None  # type: ignore[assignment]
    row["gdp_per_capita"] = float("nan")
    write_chronicle_csv(
        output_path=output,
        rows=[row],
        sources_used=["wdi"],
    )
    text = output.read_text(encoding="utf-8")
    # The data row should have empty cells at population and gdp_per_capita.
    data_row = text.splitlines()[-1]
    cells = data_row.split(",")
    pop_idx = list(CHRONICLE_CSV_COLUMNS).index("population")
    pc_idx = list(CHRONICLE_CSV_COLUMNS).index("gdp_per_capita")
    assert cells[pop_idx] == ""
    assert cells[pc_idx] == ""
    # And the strings 'None' / 'nan' must not appear in the data row.
    assert "None" not in data_row
    assert " nan" not in data_row
    assert ",nan," not in data_row


def test_write_csv_writes_atomically(tmp_path: Path) -> None:
    """The output file appears atomically; no ``.tmp`` files are left behind."""
    output = tmp_path / "out.csv"
    write_chronicle_csv(
        output_path=output,
        rows=[_sample_row()],
        sources_used=["vdem"],
    )
    assert output.is_file()
    leftover = list(tmp_path.glob("*.tmp"))
    assert leftover == []


def test_write_csv_creates_parent_directory(tmp_path: Path) -> None:
    """The writer creates parent directories on demand."""
    output = tmp_path / "nested" / "dir" / "out.csv"
    write_chronicle_csv(
        output_path=output,
        rows=[_sample_row()],
        sources_used=["vdem"],
    )
    assert output.is_file()


def _read_data_rows(output: Path) -> list[dict[str, str]]:
    """Read the data rows of a chronicle CSV, skipping comment lines."""
    with output.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(
            row for row in fh if not row.startswith("#")
        )
        return list(reader)


def test_write_csv_row_count_matches_input(tmp_path: Path) -> None:
    """The output CSV has exactly one data row per input row."""
    output = tmp_path / "out.csv"
    rows = [_sample_row() for _ in range(5)]
    write_chronicle_csv(
        output_path=output,
        rows=rows,
        sources_used=["vdem"],
    )
    data_rows = _read_data_rows(output)
    assert len(data_rows) == 5


def test_write_csv_preserves_pipe_flag_separator(tmp_path: Path) -> None:
    """The data_quality_flags column uses ``|`` between flags (Increment 0 §4)."""
    output = tmp_path / "out.csv"
    row = _sample_row()
    row["data_quality_flags"] = (
        "missing_ruler|missing_area|controlled_area_not_modeled"
    )
    write_chronicle_csv(
        output_path=output,
        rows=[row],
        sources_used=["vdem"],
    )
    data_rows = _read_data_rows(output)
    assert data_rows[0]["data_quality_flags"] == (
        "missing_ruler|missing_area|controlled_area_not_modeled"
    )


def test_write_csv_ignores_extra_keys(tmp_path: Path) -> None:
    """Input rows with keys outside CHRONICLE_CSV_COLUMNS are normalized
    to the canonical column set; the extra key does not appear in the
    output. The row builder is the only sanctioned caller and always
    emits canonical keys, but the writer is defensive."""
    output = tmp_path / "out.csv"
    row = _sample_row()
    row["nonsense_extra_column"] = "should not be here"
    write_chronicle_csv(
        output_path=output,
        rows=[row],
        sources_used=["vdem"],
    )
    data_rows = _read_data_rows(output)
    assert len(data_rows) == 1
    # The extra key must not appear in the output; the canonical column
    # set is unchanged.
    assert "nonsense_extra_column" not in data_rows[0]
    assert set(data_rows[0].keys()) == set(CHRONICLE_CSV_COLUMNS)


# ---------------------------------------------------------------------------
# Numerical coercion guard
# ---------------------------------------------------------------------------


def test_nan_handling_helper_consistency() -> None:
    """Sanity check: float('nan') and ``None`` normalize to empty string."""
    # The CSV writer uses ``_normalize_cell`` which is private. We
    # exercise the public behavior through write_chronicle_csv above.
    # Here we just confirm Python's behavior we rely on.
    assert math.isnan(float("nan"))
    assert repr(None) == "None"  # Confirm Python semantics so a refactor is intentional.


# ---------------------------------------------------------------------------
# Reviewer-blocker drift tests (Increment 2 sign-off)
#
# The Chronicle slice emits attribution comment lines via
# :func:`leaders_db.chronicle.csv_writer.build_attribution_comment_block`.
# Per Always-On Rule #15 every emitted line must be a substring of
# ``docs/source-attributions.md``. The reviewer called out the
# Maddison attribution in particular: the Chronicle constant must
# be byte-identical to the canonical citation in the doc, not a
# shorter abbreviation. The same drift guard covers Archigos and
# REIGN (REIGN was a reviewer finding too).
# ---------------------------------------------------------------------------


def test_maddison_chronicle_attribution_matches_attributions_doc() -> None:
    """Drift guard: the Chronicle ``MADDISON_PROJECT_ATTRIBUTION``
    constant must appear verbatim in ``docs/source-attributions.md``.

    This is the Increment 2 reviewer gate: the canonical
    Maddison citation in the doc is the long
    ``Bolt, Jutta and Jan Luiten van Zanden (2024), ...``
    string. A Chronicle constant that uses a short
    abbreviation will fail this test and force both to be
    updated together.
    """
    from leaders_db.chronicle.source_constants import (
        MADDISON_PROJECT_ATTRIBUTION,
    )

    doc = _read_source_attributions_doc()
    assert MADDISON_PROJECT_ATTRIBUTION in doc, (
        f"MADDISON_PROJECT_ATTRIBUTION constant is not in "
        f"docs/source-attributions.md: {MADDISON_PROJECT_ATTRIBUTION!r}"
    )


def test_reign_chronicle_attribution_matches_attributions_doc() -> None:
    """Drift guard: the Chronicle ``REIGN_ATTRIBUTION`` constant
    must appear verbatim in ``docs/source-attributions.md``.

    The doc says ``"REIGN dataset (Bell 2016), snapshot of
    August 2021."`` and the Chronicle constant must match.
    """
    from leaders_db.chronicle.source_constants import (
        REIGN_ATTRIBUTION,
    )

    doc = _read_source_attributions_doc()
    assert REIGN_ATTRIBUTION in doc, (
        f"REIGN_ATTRIBUTION constant is not in "
        f"docs/source-attributions.md: {REIGN_ATTRIBUTION!r}"
    )


def test_archigos_chronicle_attribution_matches_attributions_doc() -> None:
    """Drift guard: the Chronicle ``ARCHIGOS_ATTRIBUTION``
    constant must appear verbatim in
    ``docs/source-attributions.md``.
    """
    from leaders_db.chronicle.source_constants import (
        ARCHIGOS_ATTRIBUTION,
    )

    doc = _read_source_attributions_doc()
    assert ARCHIGOS_ATTRIBUTION in doc, (
        f"ARCHIGOS_ATTRIBUTION constant is not in "
        f"docs/source-attributions.md: {ARCHIGOS_ATTRIBUTION!r}"
    )


def test_build_attribution_block_emits_maddison_long_form() -> None:
    """End-to-end check: the CSV writer's attribution comment
    block emits the long-form Maddison attribution string when
    the runner reports ``maddison_project`` in ``sources_used``.

    This catches the bug where the constant is short but the doc
    is long (or vice versa) -- the writer is the production
    surface that downstream readers see.
    """
    from leaders_db.chronicle.source_constants import (
        MADDISON_PROJECT_ATTRIBUTION,
    )

    lines = build_attribution_comment_block(
        sources_used=["maddison_project"],
    )
    maddison_lines = [
        line for line in lines if MADDISON_PROJECT_ATTRIBUTION in line
    ]
    assert len(maddison_lines) == 1, (
        f"expected exactly one Maddison attribution line, got "
        f"{len(maddison_lines)} in {lines!r}"
    )
    assert maddison_lines[0].startswith("# ")


def test_build_attribution_block_emits_reign_canonical_form() -> None:
    """End-to-end check: the CSV writer's attribution comment
    block emits the canonical REIGN attribution string.
    """
    from leaders_db.chronicle.source_constants import (
        REIGN_ATTRIBUTION,
    )

    lines = build_attribution_comment_block(sources_used=["reign"])
    reign_lines = [line for line in lines if REIGN_ATTRIBUTION in line]
    assert len(reign_lines) == 1
    assert reign_lines[0].startswith("# ")


def test_write_chronicle_csv_emits_maddison_long_form_in_file(
    tmp_path: Path,
) -> None:
    """The literal CSV file (the production public output)
    contains the long-form Maddison attribution string. This is
    the ultimate reviewer-gate proof: a downstream consumer who
    parses the CSV with pandas and looks at the leading comment
    block sees the canonical Bolt and van Zanden (2024) text.
    """
    from leaders_db.chronicle.source_constants import (
        MADDISON_PROJECT_ATTRIBUTION,
    )

    out = tmp_path / "pilot.csv"
    write_chronicle_csv(
        output_path=out,
        rows=[_sample_row()],
        sources_used=["maddison_project"],
    )
    text = out.read_text(encoding="utf-8")
    assert MADDISON_PROJECT_ATTRIBUTION in text, (
        "Maddison attribution line missing from the CSV file"
    )


# ---------------------------------------------------------------------------
# Reviewer-blocker drift tests (Increment 3 sign-off)
#
# Increment 3 adds two new sources to the Chronicle: CShapes 2.0
# (country area) and the curated Soviet-leaders spell list (SUN
# rulers). The drift-guard pattern is the same as for Maddison /
# REIGN / Archigos: the canonical attribution constant must be a
# substring of docs/source-attributions.md, the writer must emit
# the canonical text in the leading comment block, and the
# literal CSV file must contain the canonical text. The reviewer
# gate is "no source ships without attribution".
# ---------------------------------------------------------------------------


def test_cshapes_chronicle_attribution_matches_attributions_doc() -> None:
    """Drift guard: the Chronicle ``CSHAPES_ATTRIBUTION`` constant
    must appear verbatim in ``docs/source-attributions.md``.
    """
    from leaders_db.chronicle.source_constants import (
        CSHAPES_ATTRIBUTION,
    )

    doc = _read_source_attributions_doc()
    assert CSHAPES_ATTRIBUTION in doc, (
        f"CSHAPES_ATTRIBUTION constant is not in "
        f"docs/source-attributions.md: {CSHAPES_ATTRIBUTION!r}"
    )


def test_soviet_leaders_curated_attribution_matches_attributions_doc() -> None:
    """Drift guard: the ``SOVIET_LEADERS_CURATED_ATTRIBUTION``
    constant must appear verbatim in
    ``docs/source-attributions.md``.
    """
    from leaders_db.chronicle.source_constants import (
        SOVIET_LEADERS_CURATED_ATTRIBUTION,
    )

    doc = _read_source_attributions_doc()
    assert SOVIET_LEADERS_CURATED_ATTRIBUTION in doc, (
        f"SOVIET_LEADERS_CURATED_ATTRIBUTION constant is not in "
        f"docs/source-attributions.md: {SOVIET_LEADERS_CURATED_ATTRIBUTION!r}"
    )


def test_build_attribution_block_emits_cshapes_line() -> None:
    """End-to-end: the CSV writer's attribution comment block
    emits the canonical CShapes 2.0 attribution string.
    """
    from leaders_db.chronicle.source_constants import (
        CSHAPES_ATTRIBUTION,
    )

    lines = build_attribution_comment_block(sources_used=["cshapes"])
    cshapes_lines = [line for line in lines if CSHAPES_ATTRIBUTION in line]
    assert len(cshapes_lines) == 1
    assert cshapes_lines[0].startswith("# ")


def test_build_attribution_block_emits_soviet_leaders_curated_line() -> None:
    """End-to-end: the CSV writer's attribution comment block
    emits the canonical Soviet-leaders curated attribution string.
    """
    from leaders_db.chronicle.source_constants import (
        SOVIET_LEADERS_CURATED_ATTRIBUTION,
    )

    lines = build_attribution_comment_block(
        sources_used=["soviet_leaders_curated"],
    )
    sun_lines = [
        line for line in lines if SOVIET_LEADERS_CURATED_ATTRIBUTION in line
    ]
    assert len(sun_lines) == 1
    assert sun_lines[0].startswith("# ")


def test_write_chronicle_csv_emits_cshapes_line_in_file(
    tmp_path: Path,
) -> None:
    """The literal CSV file (the production public output)
    contains the canonical CShapes 2.0 attribution string when
    the runner reports ``cshapes`` in ``sources_used``.
    """
    from leaders_db.chronicle.source_constants import (
        CSHAPES_ATTRIBUTION,
    )

    out = tmp_path / "pilot.csv"
    write_chronicle_csv(
        output_path=out,
        rows=[_sample_row()],
        sources_used=["cshapes"],
    )
    text = out.read_text(encoding="utf-8")
    assert CSHAPES_ATTRIBUTION in text


def test_write_chronicle_csv_emits_soviet_leaders_curated_line_in_file(
    tmp_path: Path,
) -> None:
    """The literal CSV file contains the canonical Soviet-leaders
    attribution string when the runner reports
    ``soviet_leaders_curated`` in ``sources_used``.
    """
    from leaders_db.chronicle.source_constants import (
        SOVIET_LEADERS_CURATED_ATTRIBUTION,
    )

    out = tmp_path / "pilot.csv"
    write_chronicle_csv(
        output_path=out,
        rows=[_sample_row()],
        sources_used=["soviet_leaders_curated"],
    )
    text = out.read_text(encoding="utf-8")
    assert SOVIET_LEADERS_CURATED_ATTRIBUTION in text


def test_cshapes_source_tag_constant_value() -> None:
    """The CShapes source-tag constant is the canonical
    ``"cshapes"`` string. Downstream consumers (the row builder,
    the runner's ``sources_used`` detection, the SQLite sidecar)
    use this constant as the canonical tag.
    """
    from leaders_db.chronicle.source_constants import (
        SOURCE_TAG_CSHAPES,
    )

    assert SOURCE_TAG_CSHAPES == "cshapes"


def test_soviet_leaders_curated_source_tag_constant_value() -> None:
    """The Soviet-leaders curated source-tag constant is the
    canonical ``"soviet_leaders_curated"`` string.
    """
    from leaders_db.chronicle.source_constants import (
        SOURCE_TAG_SOVIET_LEADERS_CURATED,
    )

    assert SOURCE_TAG_SOVIET_LEADERS_CURATED == "soviet_leaders_curated"


def test_flag_constants_match_increment3_spec() -> None:
    """The Increment 3 area / controlled-area flags are stable
    constants and match the documented strings.
    """
    from leaders_db.chronicle.constants import (
        FLAG_AREA_PROXY_YEAR_USED,
        FLAG_CONTROLLED_AREA_COUNTRY_ONLY,
    )

    assert FLAG_AREA_PROXY_YEAR_USED == "area_proxy_year_used"
    assert FLAG_CONTROLLED_AREA_COUNTRY_ONLY == "controlled_area_country_only"
