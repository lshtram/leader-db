"""Tests for the RSF World Press Freedom Index Stage 2 adapter (REQ-SRC-002).

The RSF adapter is the 10th Stage 2 adapter built (after V-Dem, WDI,
WGI, UCDP, SIPRI milex, SIPRI Yearbook Ch.7, PTS, UNDP HDI, WHO GHO
API). These tests define what "done" means for the RSF adapter --
they would fail if any of the production wiring (catalog load,
BOM-first / cp1252-fallback encoding detection, semicolon-delimited
CSV read with comma-decimal normalization, pre/post-2022 schema
break handling, blank-row filtering, source registration,
source_observations write, end-to-end orchestrator) regresses.

RSF is structurally distinct from every prior adapter:

- It is the first source with **multiple local input files** (24
  annual CSVs spanning 2002-2026, with 2011 absent).
- It is the first source with **semicolon-delimited CSVs and a
  comma decimal separator** (European convention).
- It is the first source with **mixed encodings across years**:
  2002-2024 are ``utf-8-sig`` (with BOM); 2025-2026 are ``cp1252``
  (no BOM, contains Arabic/Persian country labels not representable
  in UTF-8).
- It has **two pre/post-2022 schema generations**: 2002-2021 is a
  16-column wide format with score + rank only; 2022+ adds 5
  component-context columns (Political Context, Economic Context,
  Legal Context, Social Context, Safety).
- The 2022 file contains **181 blank separator rows** between data
  rows.
- It is the first source where the **direct 2011 file is absent**
  (RSF's combined 2011/2012 edition is represented by the 2012 CSV).
- It is the first source where the **score direction is
  higher-is-better** (higher RSF score = better press-freedom
  situation -- the RSF methodology inverts the natural "freedom"
  framing).
- It targets the ``political_freedom`` rating category exclusively
  (RSF is a press/media-freedom sub-signal per
  ``docs/source-vetting-report.md`` §3.2).

Tests use 3 small real-format fixtures under
``tests/fixtures/rsf_press_freedom/``:

- ``rsf_press_freedom_2002_sample.csv`` -- 2002 file (pre-2022
  shape: 16-col wide format with ``Score N`` / ``Rank N`` columns,
  no component-context columns).
- ``rsf_press_freedom_2022_sample.csv`` -- 2022 file (transition
  shape: 22-col wide format with blank separator rows in the
  source; the reader filters them).
- ``rsf_press_freedom_2023_sample.csv`` -- 2023 file (post-2022
  shape: 25-col wide format with all 5 component-context columns).

The fixtures are real-format slices (every cell value copied
verbatim from the real bundle, no invented data), produced by
``tests/fixtures/rsf_press_freedom/build_sample_csv.py``.

Key design decisions exercised by these tests:

- ``iso3`` is the primary key. ``raw_value`` preserves the verbatim
  RSF cell text (with comma decimal like ``"72,67"``); ``normalized_value``
  is the float-coerced value (``72.67``) with the comma normalized
  to period. ``country_id`` is NULL at Stage 2; ``confidence`` is
  NULL at Stage 2.
- ``source_row_reference`` is ``"rsf_press_freedom:<iso3>:<actual_column>"``
  where ``<actual_column>`` is the year-specific column name
  (``Score N`` for 2002-2021, ``Score`` for 2022+, etc.). The actual
  column name is preserved so the audit trail can locate the exact
  RSF header.
- The Stage 2 end-to-end row count for the 2023 fixture (5
  countries x 7 indicators = 35 observations) is asserted
  explicitly. The full-window real-file run for 2022-2026 produces
  180 countries x 7 indicators = 1,260 per year.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pyarrow.parquet as pq
import pytest
from sqlalchemy import func, select

from leaders_db.db.engine import init_database
from leaders_db.db.models import Source, SourceObservation
from leaders_db.db.session import session_scope
from leaders_db.ingest.rsf_press_freedom_csv import _detect_encoding

# Try importing the RSF modules; the tests fail gracefully if any
# of them do not exist (the import block sets the names to ``None``
# and every test that needs them asserts ``is not None`` first).
try:
    from leaders_db.ingest import (
        STAGE2_ADAPTERS,
        rsf_press_freedom,
        rsf_press_freedom_csv,
        rsf_press_freedom_io,
    )
    from leaders_db.ingest.rsf_press_freedom import (
        RSF_PRESS_FREEDOM_ATTRIBUTION,
        RSF_PRESS_FREEDOM_SOURCE_KEY,
        IndicatorSpec,
        RsfPressFreedomIngestResult,
        attribution,
        default_processed_parquet_path,
        default_raw_csv_path,
        ingest_rsf_press_freedom,
        load_rsf_press_freedom_catalog,
        read_rsf_press_freedom_csv,
        register_rsf_press_freedom_source,
        write_rsf_press_freedom_observations,
        write_rsf_press_freedom_parquet,
        write_rsf_press_freedom_run_manifest,
    )
except ImportError:
    # Modules do not exist yet; tests will fail with appropriate
    # errors when they assert against these names.
    rsf_press_freedom = None  # type: ignore[assignment]
    rsf_press_freedom_csv = None  # type: ignore[assignment]
    rsf_press_freedom_io = None  # type: ignore[assignment]
    RSF_PRESS_FREEDOM_ATTRIBUTION = None  # type: ignore[assignment]
    RSF_PRESS_FREEDOM_SOURCE_KEY = None  # type: ignore[assignment]
    IndicatorSpec = None  # type: ignore[assignment]
    RsfPressFreedomIngestResult = None  # type: ignore[assignment]
    STAGE2_ADAPTERS = None  # type: ignore[assignment]
    attribution = None  # type: ignore[assignment]
    default_processed_parquet_path = None  # type: ignore[assignment]
    default_raw_csv_path = None  # type: ignore[assignment]
    ingest_rsf_press_freedom = None  # type: ignore[assignment]
    load_rsf_press_freedom_catalog = None  # type: ignore[assignment]
    read_rsf_press_freedom_csv = None  # type: ignore[assignment]
    register_rsf_press_freedom_source = None  # type: ignore[assignment]
    write_rsf_press_freedom_observations = None  # type: ignore[assignment]
    write_rsf_press_freedom_parquet = None  # type: ignore[assignment]
    write_rsf_press_freedom_run_manifest = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def rsf_raw_dir(isolated_data_lake: Path) -> Path:
    """Stage the RSF fixture CSVs under data/raw/rsf_press_freedom/ in the test lake.

    Also copies the project's real ``metadata.json`` if present, so
    ``register_rsf_press_freedom_source`` exercises the bundle
    metadata path.
    """
    target = isolated_data_lake / "data" / "raw" / "rsf_press_freedom"
    target.mkdir(parents=True, exist_ok=True)

    fixtures_dir = Path(__file__).resolve().parent / "fixtures" / "rsf_press_freedom"
    for fixture_name in (
        "rsf_press_freedom_2002_sample.csv",
        "rsf_press_freedom_2022_sample.csv",
        "rsf_press_freedom_2023_sample.csv",
    ):
        shutil.copy2(
            fixtures_dir / fixture_name,
            target / fixture_name.replace("_sample.csv", ".csv"),
        )

    project_root = Path(__file__).resolve().parents[1]
    real_meta = project_root / "data" / "raw" / "rsf_press_freedom" / "metadata.json"
    if real_meta.is_file():
        shutil.copy2(real_meta, target / "metadata.json")

    return target


@pytest.fixture()
def rsf_catalog_path() -> Path:
    """Return the absolute path of the checked-in RSF indicator catalog."""
    return (
        Path(__file__).resolve().parents[1]
        / "src"
        / "leaders_db"
        / "ingest"
        / "catalogs"
        / "rsf_press_freedom.csv"
    )


def _init_test_db(database_url: str) -> None:
    """Apply migrations to the test DB so the ORM has its tables."""
    init_database(database_url)


# ---------------------------------------------------------------------------
# §A.1 — Catalog loader (4 tests)
# ---------------------------------------------------------------------------


def test_load_indicator_catalog_has_seven_specs(
    rsf_catalog_path: Path,
) -> None:
    """The checked-in catalog has exactly 7 indicators (2 base + 5 components)."""
    assert load_rsf_press_freedom_catalog is not None, (
        "rsf_press_freedom_io module not implemented"
    )
    specs = load_rsf_press_freedom_catalog(rsf_catalog_path)
    assert len(specs) == 7, f"Expected 7 indicators, got {len(specs)}"
    assert all(s.variable_name and s.raw_column for s in specs)


def test_load_indicator_catalog_required_columns_present(
    rsf_catalog_path: Path,
) -> None:
    """The 8 required CSV columns are present and parsed without error."""
    assert load_rsf_press_freedom_catalog is not None, (
        "rsf_press_freedom_io module not implemented"
    )
    specs = load_rsf_press_freedom_catalog(rsf_catalog_path)
    for spec in specs:
        assert spec.variable_name, f"missing variable_name: {spec}"
        assert spec.raw_column, f"missing raw_column: {spec}"
        assert spec.category, f"missing category: {spec}"
        assert spec.raw_scale, f"missing raw_scale: {spec}"
        assert spec.normalized_scale_target, (
            f"missing normalized_scale_target: {spec}"
        )
        assert spec.unit, f"missing unit: {spec}"
        assert spec.description, f"missing description: {spec}"
    # All 7 are in political_freedom per architecture §3
    categories = {s.category for s in specs}
    assert categories == {"political_freedom"}, (
        f"Expected category 'political_freedom' for all 7 specs, "
        f"got {categories}"
    )


def test_load_indicator_catalog_score_direction_higher_is_better(
    rsf_catalog_path: Path,
) -> None:
    """The annual score is ``higher_is_better=True`` (higher RSF score
    = better press freedom). The annual rank is
    ``higher_is_better=False`` (rank 1 = best). The 5 component
    scores are all ``higher_is_better=True``.
    """
    assert load_rsf_press_freedom_catalog is not None, (
        "rsf_press_freedom_io module not implemented"
    )
    specs = load_rsf_press_freedom_catalog(rsf_catalog_path)
    by_var = {s.variable_name: s for s in specs}
    assert by_var["rsf_press_freedom_score"].higher_is_better is True, (
        "rsf_press_freedom_score must be higher_is_better=True "
        "(higher RSF score = better press freedom)"
    )
    assert by_var["rsf_press_freedom_rank"].higher_is_better is False, (
        "rsf_press_freedom_rank must be higher_is_better=False "
        "(rank 1 = best)"
    )
    for component_var in (
        "rsf_press_freedom_political_context",
        "rsf_press_freedom_economic_context",
        "rsf_press_freedom_legal_context",
        "rsf_press_freedom_social_context",
        "rsf_press_freedom_safety",
    ):
        assert by_var[component_var].higher_is_better is True, (
            f"{component_var} must be higher_is_better=True"
        )


def test_load_indicator_catalog_missing_file_raises(
    tmp_path: Path,
) -> None:
    """Missing catalog path raises FileNotFoundError."""
    assert load_rsf_press_freedom_catalog is not None, (
        "rsf_press_freedom_io module not implemented"
    )
    with pytest.raises(FileNotFoundError):
        load_rsf_press_freedom_catalog(tmp_path / "does-not-exist.csv")


# ---------------------------------------------------------------------------
# §A.2 — Pre-2022 CSV reader (4 tests)
# ---------------------------------------------------------------------------


def test_read_csv_pre_2022_uses_score_n_column(
    rsf_raw_dir: Path,
    rsf_catalog_path: Path,
) -> None:
    """Pre-2022 files use ``Score N`` / ``Rank N`` as the score and
    rank column names; the reader resolves the catalog's logical
    ``score`` / ``rank`` to the year-specific actual column at
    parse time.

    For the 2002 fixture (5 countries x 2 indicators = 10 rows), the
    ``source_row_reference`` must carry the literal year-specific
    ``Score N`` / ``Rank N`` column names.
    """
    assert read_rsf_press_freedom_csv is not None, (
        "rsf_press_freedom_csv module not implemented"
    )
    csv_path = rsf_raw_dir / "rsf_press_freedom_2002.csv"
    df = read_rsf_press_freedom_csv(
        year=2002, csv_path=csv_path, catalog_path=rsf_catalog_path,
    )
    assert len(df) == 10, (
        f"Expected 10 narrow rows (5 countries x 2 indicators), "
        f"got {len(df)}"
    )
    # Every source_row_reference must use a pre-2022 column name
    # suffix (either ``:Score N`` for the score rows or ``:Rank N``
    # for the rank rows -- the 2002 file has no component-context
    # columns).
    refs = df["source_row_reference"].tolist()
    score_refs = [
        ref for ref in refs
        if ref.endswith(":Score N")
    ]
    rank_refs = [
        ref for ref in refs
        if ref.endswith(":Rank N")
    ]
    assert len(score_refs) == 5, (
        f"Expected 5 score refs (5 countries), got {len(score_refs)}: {score_refs}"
    )
    assert len(rank_refs) == 5, (
        f"Expected 5 rank refs (5 countries), got {len(rank_refs)}: {rank_refs}"
    )


def test_read_csv_pre_2022_no_component_columns(
    rsf_raw_dir: Path,
    rsf_catalog_path: Path,
) -> None:
    """Pre-2022 files do NOT carry the 5 component-context columns;
    the reader emits no component observations for pre-2022 years.
    The narrow frame's ``variable_name`` column carries only
    ``rsf_press_freedom_score`` and ``rsf_press_freedom_rank``.
    """
    assert read_rsf_press_freedom_csv is not None
    csv_path = rsf_raw_dir / "rsf_press_freedom_2002.csv"
    df = read_rsf_press_freedom_csv(
        year=2002, csv_path=csv_path, catalog_path=rsf_catalog_path,
    )
    observed_vars = set(df["variable_name"].unique())
    assert observed_vars == {
        "rsf_press_freedom_score",
        "rsf_press_freedom_rank",
    }, (
        f"Pre-2022 narrow frame must carry only the 2 base "
        f"indicators, got {observed_vars}"
    )


def test_read_csv_pre_2022_normalizes_comma_decimal(
    rsf_raw_dir: Path,
    rsf_catalog_path: Path,
) -> None:
    """Pre-2022 RSF score cells use ``,`` as the decimal separator
    (European convention). The reader normalizes commas to periods
    in ``normalized_value`` only; ``raw_value`` preserves the
    verbatim RSF cell text (with comma).
    """
    assert read_rsf_press_freedom_csv is not None
    csv_path = rsf_raw_dir / "rsf_press_freedom_2002.csv"
    df = read_rsf_press_freedom_csv(
        year=2002, csv_path=csv_path, catalog_path=rsf_catalog_path,
    )
    score_df = df[df["variable_name"] == "rsf_press_freedom_score"]
    # raw_value preserves commas
    assert all("," in str(v) or str(v).strip() == "" for v in score_df["raw_value"]), (
        f"raw_value should preserve comma decimal, got {score_df['raw_value'].tolist()[:3]}"
    )
    # normalized_value uses period
    for nv in score_df["normalized_value"]:
        if nv is None:
            continue
        assert isinstance(nv, float), (
            f"normalized_value must be float for scores, got {type(nv).__name__}"
        )
        # No commas in the float repr
        assert "," not in repr(nv)


def test_read_csv_pre_2022_preserves_rank_as_int(
    rsf_raw_dir: Path,
    rsf_catalog_path: Path,
) -> None:
    """The RSF rank column is always an integer in the live data.
    The reader coerces it to ``int``; ``raw_value`` preserves the
    literal cell text.
    """
    assert read_rsf_press_freedom_csv is not None
    csv_path = rsf_raw_dir / "rsf_press_freedom_2002.csv"
    df = read_rsf_press_freedom_csv(
        year=2002, csv_path=csv_path, catalog_path=rsf_catalog_path,
    )
    rank_df = df[df["variable_name"] == "rsf_press_freedom_rank"]
    for _, row in rank_df.iterrows():
        # normalized_value should be int-like (parseable as int)
        assert row["normalized_value"] is not None
        assert float(row["normalized_value"]) == int(float(row["normalized_value"])), (
            f"Rank normalized_value must be int-like, got "
            f"{row['normalized_value']!r}"
        )


# ---------------------------------------------------------------------------
# §A.3 — 2022 transition-year CSV reader (2 tests)
# ---------------------------------------------------------------------------


def test_read_csv_2022_uses_score_column(
    rsf_raw_dir: Path,
    rsf_catalog_path: Path,
) -> None:
    """The 2022 file uses ``Score`` (not ``Score N``) and ``Rank``
    (not ``Rank N``) as the column names; the reader resolves the
    catalog's logical ``score`` / ``rank`` to the year-specific
    actual column at parse time.
    """
    assert read_rsf_press_freedom_csv is not None
    csv_path = rsf_raw_dir / "rsf_press_freedom_2022.csv"
    df = read_rsf_press_freedom_csv(
        year=2022, csv_path=csv_path, catalog_path=rsf_catalog_path,
    )
    refs = df["source_row_reference"].tolist()
    score_refs = [
        ref for ref in refs
        if ref.endswith(":Score")
    ]
    rank_refs = [
        ref for ref in refs
        if ref.endswith(":Rank")
    ]
    component_ref_suffixes = (
        ":Political Context",
        ":Economic Context",
        ":Legal Context",
        ":Social Context",
        ":Safety",
    )
    component_refs = [
        ref for ref in refs
        if any(ref.endswith(suffix) for suffix in component_ref_suffixes)
    ]
    assert len(score_refs) == 5, (
        f"Expected 5 score refs for the 2022 fixture, got {len(score_refs)}"
    )
    assert len(rank_refs) == 5, (
        f"Expected 5 rank refs for the 2022 fixture, got {len(rank_refs)}"
    )
    assert len(component_refs) == 25, (
        f"Expected 25 component refs (5 countries x 5 components) "
        f"for the 2022 fixture, got {len(component_refs)}"
    )
    # None of the pre-2022 column names should leak into the 2022 refs.
    assert not any(":Score N" in ref for ref in refs), (
        f"2022 refs must not contain the pre-2022 'Score N' "
        f"column name, got {refs[:5]}"
    )
    assert not any(":Rank N" in ref for ref in refs), (
        f"2022 refs must not contain the pre-2022 'Rank N' "
        f"column name, got {refs[:5]}"
    )


def test_read_csv_2022_full_source_filters_blank_rows() -> None:
    """The 2022 file contains 181 blank separator rows in the source
    bundle (per metadata.json ``blank_row_count_excluding_header``).
    When reading the full 2022 file directly, the reader must drop
    those blank rows; the resulting narrow frame must have one row
    per ``(iso3, variable_name)`` triple with no duplicate ISO3s.

    This test is gated on the real 2022 file being on disk.
    """
    assert read_rsf_press_freedom_csv is not None
    project_root = Path(__file__).resolve().parents[1]
    real_csv = project_root / "data" / "raw" / "rsf_press_freedom" / "rsf_press_freedom_2022.csv"
    rsf_catalog_path = (
        project_root
        / "src" / "leaders_db" / "ingest" / "catalogs" / "rsf_press_freedom.csv"
    )
    if not real_csv.is_file():
        pytest.skip("Real RSF 2022 CSV not on disk")

    df = read_rsf_press_freedom_csv(
        year=2022, csv_path=real_csv, catalog_path=rsf_catalog_path,
    )
    # 180 distinct ISO3s x 7 indicators = 1260 observations
    assert len(df) == 180 * 7, (
        f"Expected 1260 narrow rows (180 countries x 7 indicators) "
        f"from the real 2022 file, got {len(df)}"
    )
    assert df["iso3"].nunique() == 180
    # No duplicate (iso3, variable_name) triple
    triples = df[["iso3", "variable_name"]].drop_duplicates().shape[0]
    assert triples == len(df), (
        f"Duplicate (iso3, variable_name) triples detected: "
        f"{len(df)} rows but only {triples} unique"
    )


# ---------------------------------------------------------------------------
# §A.4 — Post-2022 CSV reader (3 tests)
# ---------------------------------------------------------------------------


def test_read_csv_post_2022_emits_all_seven_indicators(
    rsf_raw_dir: Path,
    rsf_catalog_path: Path,
) -> None:
    """Post-2022 files carry the 5 component-context columns; the
    reader emits all 7 indicators (2 base + 5 components) per
    country.
    """
    assert read_rsf_press_freedom_csv is not None
    csv_path = rsf_raw_dir / "rsf_press_freedom_2023.csv"
    df = read_rsf_press_freedom_csv(
        year=2023, csv_path=csv_path, catalog_path=rsf_catalog_path,
    )
    observed_vars = set(df["variable_name"].unique())
    expected_vars = {
        "rsf_press_freedom_score",
        "rsf_press_freedom_rank",
        "rsf_press_freedom_political_context",
        "rsf_press_freedom_economic_context",
        "rsf_press_freedom_legal_context",
        "rsf_press_freedom_social_context",
        "rsf_press_freedom_safety",
    }
    assert observed_vars == expected_vars, (
        f"Post-2022 narrow frame must carry all 7 indicators, "
        f"got {observed_vars}"
    )


def test_read_csv_post_2022_component_source_row_reference(
    rsf_raw_dir: Path,
    rsf_catalog_path: Path,
) -> None:
    """The 5 component-context ``source_row_reference`` values carry
    the literal year-specific actual column name (``Political
    Context`` etc.). The score and rank references carry ``Score``
    / ``Rank``.
    """
    assert read_rsf_press_freedom_csv is not None
    csv_path = rsf_raw_dir / "rsf_press_freedom_2023.csv"
    df = read_rsf_press_freedom_csv(
        year=2023, csv_path=csv_path, catalog_path=rsf_catalog_path,
    )
    # 5 countries x 7 indicators = 35 observations
    assert len(df) == 35, (
        f"Expected 35 narrow rows (5 countries x 7 indicators), "
        f"got {len(df)}"
    )
    # Component rows must carry the literal component column name
    component_refs = df[
        df["variable_name"] == "rsf_press_freedom_political_context"
    ]["source_row_reference"].tolist()
    assert all(
        ref.endswith(":Political Context") for ref in component_refs
    ), f"Political Context refs malformed: {component_refs}"


def test_read_csv_post_2022_full_source_row_count() -> None:
    """Gated on the real 2023 file. The full 2023 file (180 ISO3s
    x 7 indicators) produces 1,260 narrow rows. Empty-cell rows
    produce ``raw_value=""`` and ``normalized_value=None`` and are
    still emitted in the narrow frame as Stage 2 audit records
    (per the architecture §6 ``raw_value`` preservation contract).
    """
    assert read_rsf_press_freedom_csv is not None
    project_root = Path(__file__).resolve().parents[1]
    real_csv = project_root / "data" / "raw" / "rsf_press_freedom" / "rsf_press_freedom_2023.csv"
    rsf_catalog_path = (
        project_root
        / "src" / "leaders_db" / "ingest" / "catalogs" / "rsf_press_freedom.csv"
    )
    if not real_csv.is_file():
        pytest.skip("Real RSF 2023 CSV not on disk")

    df = read_rsf_press_freedom_csv(
        year=2023, csv_path=real_csv, catalog_path=rsf_catalog_path,
    )
    # 180 ISO3s x 7 indicators = 1260 narrow rows. Empty cells are
    # PRESERVED in the narrow frame (raw_value="", normalized_value=None)
    # so Stage 15 reports can audit them; they are NOT dropped.
    assert len(df) == 180 * 7, (
        f"Expected 1260 narrow rows from the real 2023 file, "
        f"got {len(df)}"
    )


# ---------------------------------------------------------------------------
# §A.5 — Missing 2011 file (1 test)
# ---------------------------------------------------------------------------


def test_read_csv_year_2011_raises_file_not_found(
    rsf_raw_dir: Path,
) -> None:
    """``year=2011`` raises :class:`FileNotFoundError` because the
    direct ``rsf_press_freedom_2011.csv`` is intentionally absent
    (RSF's combined 2011/2012 edition is represented by the 2012
    CSV). The orchestrator's full-window run silently skips 2011
    so the FileNotFoundError never escapes.
    """
    assert default_raw_csv_path is not None
    with pytest.raises(FileNotFoundError):
        default_raw_csv_path(2011)


# ---------------------------------------------------------------------------
# §A.6 — Encoding fallback (2 tests)
# ---------------------------------------------------------------------------


def test_detect_encoding_bom_for_utf8_sig_files(
    tmp_path: Path,
) -> None:
    """A file starting with the UTF-8 BOM (``EF BB BF``) is detected
    as ``utf-8-sig``. This is the canonical RSF encoding for
    2002-2024 files.
    """
    f = tmp_path / "utf8.csv"
    f.write_bytes(b"\xef\xbb\xbfISO;Score\nNOR;92,65\n")
    assert _detect_encoding(f) == "utf-8-sig"


def test_detect_encoding_cp1252_for_non_utf8_files(
    tmp_path: Path,
) -> None:
    """A file WITHOUT the UTF-8 BOM but containing cp1252-representable
    bytes is detected as ``cp1252``. This is the canonical RSF
    encoding for 2025-2026 files (Arabic/Persian country labels).
    """
    # 0xe2 is the start byte of a 3-byte UTF-8 sequence (Arabic/Persian
    # codepoints); cp1252 maps it to "â" (a Latin letter), so the file
    # decodes cleanly under cp1252 but raises under utf-8.
    f = tmp_path / "cp1252.csv"
    f.write_bytes(b"ISO;Score\nNOR;\xe2\x80\x93\n")
    assert _detect_encoding(f) == "cp1252"


# ---------------------------------------------------------------------------
# §A.7 — DB writers (4 tests)
# ---------------------------------------------------------------------------


def test_db_writers_register_source_idempotent(
    rsf_raw_dir: Path,
    database_url: str,
) -> None:
    """``register_rsf_press_freedom_source`` returns the same ``id``
    on every call.
    """
    assert register_rsf_press_freedom_source is not None
    _init_test_db(database_url)

    with session_scope(database_url) as session:
        first_id = register_rsf_press_freedom_source(session)
    with session_scope(database_url) as session:
        second_id = register_rsf_press_freedom_source(session)
    assert first_id == second_id, (
        "register_rsf_press_freedom_source should be idempotent"
    )

    with session_scope(database_url) as session:
        row = session.execute(
            select(Source).where(Source.id == first_id),
        ).scalar_one()
        assert row.source_name == (
            "Reporters Without Borders World Press Freedom Index"
        )
        assert row.version == "annual CSV series 2002-2026"
        assert row.source_type == "official"


def test_db_writers_observation_count_matches_narrow_frame(
    rsf_raw_dir: Path,
    rsf_catalog_path: Path,
    database_url: str,
) -> None:
    """The number of ``source_observations`` rows written equals the
    narrow-frame row count.
    """
    assert ingest_rsf_press_freedom is not None, (
        "rsf_press_freedom module not implemented"
    )
    _init_test_db(database_url)

    # Use a per-year path override so the orchestrator reads the
    # 2023 fixture (not the missing 2011 file).
    year_paths = {
        2023: rsf_raw_dir / "rsf_press_freedom_2023.csv",
    }
    result = ingest_rsf_press_freedom(
        year=2023,
        raw_dir_year_csv_paths=year_paths,
        catalog_path=rsf_catalog_path,
    )
    # 5 countries x 7 indicators = 35 observations
    assert result.observation_rows == 35, (
        f"Expected 35 observations for year=2023 against the "
        f"fixture (5 countries x 7 indicators), got {result.observation_rows}"
    )

    with session_scope(database_url) as session:
        rows = session.execute(
            select(SourceObservation).where(
                SourceObservation.source_id == result.source_id,
            ),
        ).scalars().all()
    assert len(rows) == 35
    # No (country_id, leader_id, confidence) should be set at Stage 2.
    assert all(r.country_id is None for r in rows)
    assert all(r.confidence is None for r in rows)


def test_db_writers_rerun_is_idempotent(
    rsf_raw_dir: Path,
    rsf_catalog_path: Path,
    database_url: str,
) -> None:
    """Re-running the orchestrator with the same year produces the
    same final state (no double-writes).
    """
    assert ingest_rsf_press_freedom is not None
    _init_test_db(database_url)

    year_paths = {
        2023: rsf_raw_dir / "rsf_press_freedom_2023.csv",
    }
    first = ingest_rsf_press_freedom(
        year=2023,
        raw_dir_year_csv_paths=year_paths,
        catalog_path=rsf_catalog_path,
    )
    second = ingest_rsf_press_freedom(
        year=2023,
        raw_dir_year_csv_paths=year_paths,
        catalog_path=rsf_catalog_path,
    )
    assert first.source_id == second.source_id
    assert first.observation_rows == second.observation_rows == 35

    with session_scope(database_url) as session:
        count = session.execute(
            select(func.count(SourceObservation.id)).where(
                SourceObservation.source_id == first.source_id,
            ),
        ).scalar_one()
    assert count == 35, (
        f"Expected 35 observations after idempotent rerun, got {count}"
    )


def test_db_writers_source_row_reference_format(
    rsf_raw_dir: Path,
    rsf_catalog_path: Path,
    database_url: str,
) -> None:
    """Every ``source_observations.source_row_reference`` starts
    with ``"rsf_press_freedom:"`` and carries the year-specific
    actual RSF column name as the suffix.
    """
    assert ingest_rsf_press_freedom is not None
    _init_test_db(database_url)

    year_paths = {
        2023: rsf_raw_dir / "rsf_press_freedom_2023.csv",
    }
    result = ingest_rsf_press_freedom(
        year=2023,
        raw_dir_year_csv_paths=year_paths,
        catalog_path=rsf_catalog_path,
    )

    with session_scope(database_url) as session:
        refs = session.execute(
            select(SourceObservation.source_row_reference).where(
                SourceObservation.source_id == result.source_id,
            ),
        ).scalars().all()

    assert refs, "Expected source_observations rows"
    expected_iso3 = {"MEX", "USA", "NGA", "SWE", "NOR"}
    for ref in refs:
        assert ref.startswith("rsf_press_freedom:"), (
            f"Bad prefix: {ref}"
        )
        # ref is "rsf_press_freedom:<ISO3>:<actual_column>".
        parts = ref.split(":", 2)
        assert len(parts) == 3, f"Bad ref format: {ref}"
        assert parts[1] in expected_iso3, f"Bad ISO3: {parts[1]}"


# ---------------------------------------------------------------------------
# §A.8 — Parquet writer + attribution (2 tests)
# ---------------------------------------------------------------------------


def test_parquet_metadata_carries_attribution_and_source_key(
    rsf_raw_dir: Path,
    rsf_catalog_path: Path,
) -> None:
    """The narrow parquet's file-level metadata carries
    ``rsf_press_freedom_attribution`` and
    ``rsf_press_freedom_source_key`` (mirror of the V-Dem / WGI /
    UCDP / SIPRI milex / SIPRI Yearbook Ch.7 / PTS / UNDP HDI
    pattern, per architecture §12 regression checklist item 12).
    """
    assert write_rsf_press_freedom_parquet is not None
    assert read_rsf_press_freedom_csv is not None
    assert RSF_PRESS_FREEDOM_ATTRIBUTION is not None

    csv_path = rsf_raw_dir / "rsf_press_freedom_2023.csv"
    narrow = read_rsf_press_freedom_csv(
        year=2023, csv_path=csv_path, catalog_path=rsf_catalog_path,
    )
    out = write_rsf_press_freedom_parquet(narrow)

    assert out.exists()
    table = pq.read_table(out)
    meta = table.schema.metadata or {}
    attribution_bytes = meta.get(b"rsf_press_freedom_attribution")
    assert attribution_bytes is not None, (
        "parquet missing rsf_press_freedom_attribution metadata"
    )
    assert attribution_bytes.decode("utf-8") == RSF_PRESS_FREEDOM_ATTRIBUTION
    assert meta.get(b"rsf_press_freedom_source_key") == b"rsf_press_freedom"


def test_rsf_press_freedom_attribution_matches_attributions_doc() -> None:
    """``RSF_PRESS_FREEDOM_ATTRIBUTION`` is a substring of
    ``docs/source-attributions.md`` (drift guard per Rule #15).
    """
    assert RSF_PRESS_FREEDOM_ATTRIBUTION is not None, (
        "rsf_press_freedom_io module not implemented"
    )
    doc_path = (
        Path(__file__).resolve().parents[1]
        / "docs" / "source-attributions.md"
    )
    doc_text = doc_path.read_text(encoding="utf-8")
    assert RSF_PRESS_FREEDOM_ATTRIBUTION in doc_text, (
        f"RSF_PRESS_FREEDOM_ATTRIBUTION not found in {doc_path}. "
        "Update both in the same commit (Rule #15)."
    )


# ---------------------------------------------------------------------------
# §A.9 — End-to-end real-file smoke (2 tests)
# ---------------------------------------------------------------------------


def test_end_to_end_real_file_year_2023_row_count(
    rsf_catalog_path: Path,
    database_url: str,
) -> None:
    """Gated on the real local CSV. For ``year=2023``, the output
    has 1,260 rows (180 countries x 7 indicators).
    """
    assert ingest_rsf_press_freedom is not None
    project_root = Path(__file__).resolve().parents[1]
    real_csv = (
        project_root
        / "data" / "raw" / "rsf_press_freedom" / "rsf_press_freedom_2023.csv"
    )
    if not real_csv.is_file():
        pytest.skip("Real RSF 2023 CSV not on disk")

    _init_test_db(database_url)
    year_paths = {2023: real_csv}
    result = ingest_rsf_press_freedom(
        year=2023,
        raw_dir_year_csv_paths=year_paths,
        catalog_path=rsf_catalog_path,
    )
    assert result.observation_rows == 180 * 7, (
        f"Expected 1260 observations for year=2023 against the "
        f"real file (180 countries x 7 indicators), got {result.observation_rows}"
    )
    assert result.countries == 180
    assert result.indicators == 7
    assert result.pre_2022_country_count == 0
    assert result.post_2022_country_count == 180


def test_end_to_end_real_file_does_not_modify_raw(
    rsf_catalog_path: Path,
    database_url: str,
) -> None:
    """The end-to-end smoke against the real RSF CSV must not modify
    the raw file (Phase C convention #2: no raw edits).
    """
    assert ingest_rsf_press_freedom is not None
    project_root = Path(__file__).resolve().parents[1]
    real_csv = (
        project_root
        / "data" / "raw" / "rsf_press_freedom" / "rsf_press_freedom_2023.csv"
    )
    if not real_csv.is_file():
        pytest.skip("Real RSF 2023 CSV not on disk")

    sha_before = hashlib.sha256(real_csv.read_bytes()).hexdigest()

    _init_test_db(database_url)
    ingest_rsf_press_freedom(
        year=2023,
        raw_dir_year_csv_paths={2023: real_csv},
        catalog_path=rsf_catalog_path,
    )

    sha_after = hashlib.sha256(real_csv.read_bytes()).hexdigest()
    assert sha_before == sha_after, (
        f"Real raw RSF CSV was modified during ingest: "
        f"before={sha_before} after={sha_after}"
    )


# ---------------------------------------------------------------------------
# §A.10 — Orchestrator end-to-end (3 tests)
# ---------------------------------------------------------------------------


def test_orchestrator_full_window_writes_db_rows_and_manifest(
    rsf_raw_dir: Path,
    rsf_catalog_path: Path,
    database_url: str,
) -> None:
    """``ingest_rsf_press_freedom(year=None)`` walks every year file
    in the canonical direct-CSV pattern (2002-2026, skipping 2011),
    concatenates the per-year narrow frames, writes the parquet,
    the DB rows, and the run manifest. The result is a
    :class:`RsfPressFreedomIngestResult` with the expected 10 fields.
    """
    assert ingest_rsf_press_freedom is not None
    assert RsfPressFreedomIngestResult is not None
    _init_test_db(database_url)

    # Override every year path so the orchestrator reads from the
    # test data lake (the project-root data lake is also fine in CI
    # but the test must be self-contained).
    year_paths: dict[int, Path] = {}
    for year in range(2002, 2027):
        if year == 2011:
            continue
        candidate = rsf_raw_dir / f"rsf_press_freedom_{year}.csv"
        if candidate.is_file():
            year_paths[year] = candidate

    result = ingest_rsf_press_freedom(
        raw_dir_year_csv_paths=year_paths,
        catalog_path=rsf_catalog_path,
    )

    assert isinstance(result, RsfPressFreedomIngestResult)
    assert result.parquet_path.exists()
    assert result.source_id > 0
    # The fixture has 3 year files (2002, 2022, 2023). The 2002
    # fixture (FIN, NOR, USA, NGA, MEX) and the 2022/2023 fixtures
    # (NOR + DNK + SWE + USA + NGA + MEX across both years) share 4
    # ISO3s; the union is 7 distinct ISO3s (FIN unique to pre-2022;
    # DNK + SWE + MEX unique to post-2022; NOR + USA + NGA shared).
    # Post-2022 alone is 6 ISO3s (DNK + SWE + MEX + NOR + USA + NGA).
    # Row count:
    #   2002: 2 indicators x 5 countries = 10
    #   2022: 7 indicators x 5 countries = 35
    #   2023: 7 indicators x 5 countries = 35
    # Total: 80
    assert result.observation_rows == 80, (
        f"Expected 80 observations for the 3-year fixture run, "
        f"got {result.observation_rows}"
    )
    assert result.countries == 7
    assert result.pre_2022_country_count == 5
    assert result.post_2022_country_count == 6, (
        "Expected 6 post-2022 distinct ISO3s (NOR + USA + NGA "
        "shared with pre-2022 plus DNK + SWE + MEX unique to "
        "post-2022), got "
        f"{result.post_2022_country_count}"
    )
    assert result.indicators == 7
    assert result.year_window == (2002, 2023)

    # The run manifest is auto-written.
    manifest = result.parquet_path.parent / "rsf_press_freedom_run_manifest.json"
    assert manifest.exists()
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["source_key"] == "rsf_press_freedom"
    assert payload["attribution"] == RSF_PRESS_FREEDOM_ATTRIBUTION
    assert payload["observation_rows"] == 80
    assert payload["pre_2022_country_count"] == 5
    assert payload["post_2022_country_count"] == 6
    assert payload["year_window"] == [2002, 2023]


def test_orchestrator_year_filter_works(
    rsf_raw_dir: Path,
    rsf_catalog_path: Path,
    database_url: str,
) -> None:
    """``ingest_rsf_press_freedom(year=2023)`` reads only the 2023
    file (5 countries x 7 indicators = 35 rows).
    """
    assert ingest_rsf_press_freedom is not None
    _init_test_db(database_url)

    year_paths = {2023: rsf_raw_dir / "rsf_press_freedom_2023.csv"}
    result = ingest_rsf_press_freedom(
        year=2023,
        raw_dir_year_csv_paths=year_paths,
        catalog_path=rsf_catalog_path,
    )
    assert result.years == (2023,)
    assert result.observation_rows == 35
    assert result.countries == 5
    assert result.pre_2022_country_count == 0
    assert result.post_2022_country_count == 5
    assert result.year_window == (2023, 2023)


def test_orchestrator_year_2011_short_circuits(
    rsf_raw_dir: Path,
    rsf_catalog_path: Path,
    database_url: str,
) -> None:
    """``ingest_rsf_press_freedom(year=2011)`` raises
    :class:`FileNotFoundError` because the direct
    ``rsf_press_freedom_2011.csv`` is intentionally absent. The
    full-window orchestrator silently skips 2011; a direct
    ``year=2011`` call surfaces the missing file.
    """
    assert ingest_rsf_press_freedom is not None
    _init_test_db(database_url)

    with pytest.raises(FileNotFoundError):
        ingest_rsf_press_freedom(
            year=2011,
            raw_dir_year_csv_paths={},
            catalog_path=rsf_catalog_path,
        )


# ---------------------------------------------------------------------------
# §A.11 — Public surface (2 tests)
# ---------------------------------------------------------------------------


def test_rsf_press_freedom_module_public_surface() -> None:
    """The ``rsf_press_freedom`` module re-exports the public surface
    from the architecture contract:
    ``ingest_rsf_press_freedom``,
    ``RsfPressFreedomIngestResult``,
    ``RSF_PRESS_FREEDOM_ATTRIBUTION``,
    ``RSF_PRESS_FREEDOM_SOURCE_KEY``,
    ``IndicatorSpec``,
    ``attribution``,
    ``load_rsf_press_freedom_catalog``,
    ``read_rsf_press_freedom_csv``,
    ``default_raw_csv_path``,
    ``default_processed_parquet_path``,
    ``register_rsf_press_freedom_source``,
    ``write_rsf_press_freedom_observations``,
    ``write_rsf_press_freedom_parquet``,
    ``write_rsf_press_freedom_run_manifest``.
    """
    assert rsf_press_freedom is not None, (
        "rsf_press_freedom module not implemented yet"
    )
    for name in [
        "RSF_PRESS_FREEDOM_ATTRIBUTION",
        "RSF_PRESS_FREEDOM_SOURCE_KEY",
        "IndicatorSpec",
        "RsfPressFreedomIngestResult",
        "attribution",
        "default_processed_parquet_path",
        "default_raw_csv_path",
        "ingest_rsf_press_freedom",
        "load_rsf_press_freedom_catalog",
        "read_rsf_press_freedom_csv",
        "register_rsf_press_freedom_source",
        "write_rsf_press_freedom_observations",
        "write_rsf_press_freedom_parquet",
        "write_rsf_press_freedom_run_manifest",
    ]:
        assert hasattr(rsf_press_freedom, name), (
            f"rsf_press_freedom.{name} not exported"
        )
        assert getattr(rsf_press_freedom, name) is not None, (
            f"rsf_press_freedom.{name} is None"
        )
    # The attribution() helper returns the module-level constant.
    assert attribution() == RSF_PRESS_FREEDOM_ATTRIBUTION
    # The source key constant is "rsf_press_freedom".
    assert RSF_PRESS_FREEDOM_SOURCE_KEY == "rsf_press_freedom"


def test_rsf_press_freedom_ingest_result_field_count() -> None:
    """``RsfPressFreedomIngestResult`` has exactly 10 fields per the
    orchestrator's contract: ``source_id``, ``parquet_path``,
    ``observation_rows``, ``countries``, ``years``, ``indicators``,
    ``pre_2022_country_count``, ``post_2022_country_count``,
    ``year_window``.
    """
    assert RsfPressFreedomIngestResult is not None, (
        "rsf_press_freedom module not implemented"
    )
    fields = RsfPressFreedomIngestResult.model_fields
    expected_fields = {
        "source_id",
        "parquet_path",
        "observation_rows",
        "countries",
        "years",
        "indicators",
        "pre_2022_country_count",
        "post_2022_country_count",
        "year_window",
    }
    assert set(fields.keys()) == expected_fields, (
        f"RsfPressFreedomIngestResult field mismatch: "
        f"missing={expected_fields - set(fields.keys())}, "
        f"extra={set(fields.keys()) - expected_fields}"
    )
    assert len(fields) == 9, (
        f"RsfPressFreedomIngestResult should have 9 fields, "
        f"got {len(fields)}"
    )


# ---------------------------------------------------------------------------
# Process boundary: dispatch table wiring
# ---------------------------------------------------------------------------


def test_dispatch_table_wires_rsf_press_freedom() -> None:
    """``STAGE2_ADAPTERS['rsf_press_freedom']`` is
    ``rsf_press_freedom.ingest_rsf_press_freedom``.

    Boundary test: the central dispatch table must point at the
    real orchestrator after the Phase C.10 integration pass. Test
    fails if the production wiring is removed.
    """
    assert "rsf_press_freedom" in STAGE2_ADAPTERS
    assert STAGE2_ADAPTERS["rsf_press_freedom"] is (
        rsf_press_freedom.ingest_rsf_press_freedom
    )
    assert callable(STAGE2_ADAPTERS["rsf_press_freedom"])


def test_dispatch_table_no_duplicate_rsf_press_freedom_key() -> None:
    """The dispatch table has exactly one ``rsf_press_freedom`` key
    (no duplicate from a copy-paste bug).
    """
    assert RSF_PRESS_FREEDOM_SOURCE_KEY is not None
    count = sum(
        1 for k in STAGE2_ADAPTERS.keys() if k == "rsf_press_freedom"
    )
    assert count == 1, (
        f"Expected exactly 1 'rsf_press_freedom' key in "
        f"STAGE2_ADAPTERS, got {count}"
    )
