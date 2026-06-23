"""Tests for the V-Dem Stage 2 adapter (REQ-SRC-002, REQ-SRC-008, REQ-SRC-005).

The adapter is the canonical Stage 2 example. These tests define what
"done" means for the V-Dem adapter — they would fail if any of the
production wiring (catalog load, CSV read, parquet write, sources
upsert, source_observations write, end-to-end orchestrator) regresses.

Tests use a 5-country x 2-year fixture extracted from the real V-Dem
v16 CSV (``tests/fixtures/vdem/sample.csv``, 10 rows x 27 cols, real
values, no invented data). The fixture is small enough to keep the test
suite fast (~1 s) and large enough to exercise the column-narrowing +
year-filtering + DB-write paths.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest
from sqlalchemy import func, select
from typer.testing import CliRunner

from leaders_db.cli import app
from leaders_db.db.engine import init_database
from leaders_db.db.models import Source, SourceObservation
from leaders_db.db.session import default_sqlite_url, session_scope
from leaders_db.ingest import STAGE2_ADAPTERS, vdem
from leaders_db.ingest.vdem import (
    VDEM_ATTRIBUTION,
    VDEM_SOURCE_KEY,
    IndicatorSpec,
    IngestResult,
)
from leaders_db.ingest.vdem_db import (
    _coerce_float,
    _coerce_float_from_string,
    _raw_value_to_string,
)
from leaders_db.ingest.vdem_io import (
    default_processed_parquet_path,
    default_raw_csv_path,
    load_indicator_catalog,
    read_vdem_csv,
    write_vdem_parquet,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def vdem_raw_dir(isolated_data_lake: Path) -> Path:
    """Stage the fixture CSV under ``data/raw/vdem/`` in the test data lake.

    Also copies ``data/raw/vdem/metadata.json`` if the project's real one
    is present, so :func:`register_vdem_source` exercises the bundle
    metadata path. If the real ``metadata.json`` is missing (e.g. on a
    clean checkout) we leave it absent; the adapter handles that case.
    """
    target = isolated_data_lake / "data" / "raw" / VDEM_SOURCE_KEY
    target.mkdir(parents=True, exist_ok=True)

    # Copy the fixture CSV
    fixtures_dir = Path(__file__).resolve().parent / "fixtures" / VDEM_SOURCE_KEY
    src_csv = fixtures_dir / "sample.csv"
    shutil.copy2(src_csv, target / "V-Dem-CY-Full+Others-v16.csv")

    # Copy the real metadata.json if it exists in the project's data lake.
    project_root = Path(__file__).resolve().parents[1]
    real_meta = project_root / "data" / "raw" / VDEM_SOURCE_KEY / "metadata.json"
    if real_meta.is_file():
        shutil.copy2(real_meta, target / "metadata.json")

    return target


@pytest.fixture()
def vdem_catalog_path() -> Path:
    """Return the absolute path of the checked-in V-Dem indicator catalog.

    Test file lives at ``<root>/tests/test_ingest_vdem.py``; the catalog
    lives at ``<root>/src/leaders_db/ingest/catalogs/vdem.csv``. So
    ``parents[1]`` is the project root, not ``parents[2]``.
    """
    catalog = Path(__file__).resolve().parents[1] / "src"
    return catalog / "leaders_db" / "ingest" / "catalogs" / "vdem.csv"


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


def test_load_indicator_catalog_returns_22_specs(vdem_catalog_path: Path) -> None:
    """The checked-in catalog has 22 indicators (matches workplan §"Phase C")."""
    specs = load_indicator_catalog(vdem_catalog_path)
    assert len(specs) == 22
    # Every spec has a non-empty variable_name and raw_column.
    assert all(s.variable_name and s.raw_column for s in specs)


def test_load_indicator_catalog_required_columns(vdem_catalog_path: Path) -> None:
    """The catalog's required columns are present and well-typed."""
    specs = load_indicator_catalog(vdem_catalog_path)
    categories = {s.rating_category for s in specs}
    # The 5 categories V-Dem feeds (the other 3 - economic, nuclear,
    # international peace - are filled by other sources).
    assert categories == {
        "political_freedom",
        "integrity",
        "effectiveness",
        "domestic_violence",
        "social_wellbeing",
    }


def test_load_indicator_catalog_missing_file(tmp_path: Path) -> None:
    """Missing catalog raises FileNotFoundError, not a silent empty list."""
    with pytest.raises(FileNotFoundError):
        load_indicator_catalog(tmp_path / "does-not-exist.csv")


def test_indicator_spec_from_csv_row() -> None:
    """``higher_is_better=0``/``=1`` round-trips to a bool."""
    good = IndicatorSpec.from_csv_row(
        {
            "variable_name": "vdem_v2x_polyarchy",
            "raw_column": "v2x_polyarchy",
            "rating_category": "political_freedom",
            "raw_scale": "0-1",
            "normalized_scale_target": "0-1",
            "higher_is_better": "1",
            "unit": "index",
            "description": "Electoral Democracy Index",
        }
    )
    assert good.higher_is_better is True
    bad = IndicatorSpec.from_csv_row(
        {
            "variable_name": "vdem_v2x_corr",
            "raw_column": "v2x_corr",
            "rating_category": "integrity",
            "raw_scale": "0-1",
            "normalized_scale_target": "0-1",
            "higher_is_better": "0",
            "unit": "index",
            "description": "Political Corruption Index",
        }
    )
    assert bad.higher_is_better is False


# ---------------------------------------------------------------------------
# CSV read
# ---------------------------------------------------------------------------


def test_read_vdem_csv_returns_full_fixture(
    vdem_raw_dir: Path, vdem_catalog_path: Path
) -> None:
    """The fixture is 5 countries x 2 years = 10 rows; 4 identity + 22 indicator columns."""
    csv_path = vdem_raw_dir / "V-Dem-CY-Full+Others-v16.csv"
    df = read_vdem_csv(csv_path=csv_path, catalog_path=vdem_catalog_path)
    assert len(df) == 10
    assert df.shape[1] == 4 + 22
    # The narrow frame renames V-Dem's ``country_id`` to ``vdem_country_id``
    # to avoid collision with the ``countries.id`` foreign key.
    assert "vdem_country_id" in df.columns
    assert "country_id" not in df.columns
    # Year is int
    assert pd.api.types.is_integer_dtype(df["year"])


def test_read_vdem_csv_filters_to_year(
    vdem_raw_dir: Path, vdem_catalog_path: Path
) -> None:
    """Filtering to year=2023 keeps only the 5 rows for 2023."""
    csv_path = vdem_raw_dir / "V-Dem-CY-Full+Others-v16.csv"
    df = read_vdem_csv(csv_path=csv_path, year=2023, catalog_path=vdem_catalog_path)
    assert len(df) == 5
    assert set(df["year"].unique()) == {2023}
    assert set(df["country_text_id"].unique()) == {
        "MEX",
        "USA",
        "SWE",
        "IND",
        "NGA",
    }


def test_read_vdem_csv_missing_file(tmp_path: Path, vdem_catalog_path: Path) -> None:
    """Missing raw CSV raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        read_vdem_csv(
            csv_path=tmp_path / "missing.csv", catalog_path=vdem_catalog_path
        )


# ---------------------------------------------------------------------------
# Parquet write + attribution metadata
# ---------------------------------------------------------------------------


def test_write_vdem_parquet_creates_file(
    vdem_raw_dir: Path, vdem_catalog_path: Path, isolated_data_lake: Path
) -> None:
    """``write_vdem_parquet`` writes a valid parquet under processed/vdem/."""
    csv_path = vdem_raw_dir / "V-Dem-CY-Full+Others-v16.csv"
    df = read_vdem_csv(csv_path=csv_path, catalog_path=vdem_catalog_path)
    out = write_vdem_parquet(df)
    assert out.exists()
    assert out.suffix == ".parquet"
    # The processed/vdem/ folder lives under the isolated data lake root.
    assert out.parent == isolated_data_lake / "data" / "processed" / VDEM_SOURCE_KEY

    # Round-trip: parquet can be re-read as the same DataFrame shape.
    round_tripped = pd.read_parquet(out)
    assert round_tripped.shape == df.shape
    assert set(round_tripped.columns) == set(df.columns)


def test_write_vdem_parquet_attaches_attribution_metadata(
    vdem_raw_dir: Path, vdem_catalog_path: Path
) -> None:
    """The parquet's file-level metadata carries the V-Dem attribution (Rule #15).

    This is the proof surface for Rule #15 on the artifact side: an
    analyst who finds the parquet in a few years should be able to
    recover the attribution without re-reading the attributions doc.
    """
    csv_path = vdem_raw_dir / "V-Dem-CY-Full+Others-v16.csv"
    df = read_vdem_csv(csv_path=csv_path, catalog_path=vdem_catalog_path)
    out = write_vdem_parquet(df)
    table = pq.read_table(out)
    meta = table.schema.metadata or {}
    attribution_bytes = meta.get(b"vdem_attribution")
    assert attribution_bytes is not None, "parquet missing vdem_attribution metadata"
    assert attribution_bytes.decode("utf-8") == VDEM_ATTRIBUTION
    # Source key also present so downstream stages know which adapter
    # produced this file.
    assert meta.get(b"vdem_source_key") == b"vdem"


def test_default_path_helpers() -> None:
    """The default path helpers point at the conventional data-lake locations."""
    raw_default = default_raw_csv_path()
    assert raw_default.name == "V-Dem-CY-Full+Others-v16.csv"
    assert VDEM_SOURCE_KEY in raw_default.parts
    parquet_default = default_processed_parquet_path()
    assert parquet_default.name == "vdem_country_year.parquet"
    assert VDEM_SOURCE_KEY in parquet_default.parts


# ---------------------------------------------------------------------------
# Source registration + observations (DB)
# ---------------------------------------------------------------------------


def _init_test_db(database_url: str) -> None:
    """Apply migrations to the test DB so the ORM has its tables."""
    init_database(database_url)


def test_register_vdem_source_is_idempotent(vdem_raw_dir: Path, database_url: str) -> None:
    """``register_vdem_source`` returns the same id on repeated calls."""
    _init_test_db(database_url)
    with session_scope(database_url) as session:
        first_id = vdem.register_vdem_source(session)
    with session_scope(database_url) as session:
        second_id = vdem.register_vdem_source(session)
    assert first_id == second_id
    # And the row has the expected shape.
    with session_scope(database_url) as session:
        row = session.execute(
            select(Source).where(Source.id == first_id)
        ).scalar_one()
        assert row.source_name == "V-Dem (Varieties of Democracy)"
        assert row.version == "v16"
        assert row.source_type == "academic"
        if row.coverage_start_year is not None:
            assert row.coverage_start_year == 1789
        if row.coverage_end_year is not None:
            assert row.coverage_end_year == 2025


def test_register_vdem_source_non_destructive_update(
    vdem_raw_dir: Path, database_url: str
) -> None:
    """``register_vdem_source`` keeps existing fields when bundle metadata is missing.

    Per the docstring of :func:`register_vdem_source`: when the bundle's
    ``metadata.json`` is missing a field, the existing row keeps the
    OLD value. This is the non-destructive update policy.
    """
    _init_test_db(database_url)
    # First call: writes the row from the real bundle metadata (or NULLs).
    with session_scope(database_url) as session:
        first_id = vdem.register_vdem_source(session)
    with session_scope(database_url) as session:
        first = session.execute(
            select(Source).where(Source.id == first_id)
        ).scalar_one()
        first_url = first.source_url
        first_license = first.license_note

    # Wipe the bundle metadata.json so the second call sees no fields.
    bundle_meta = vdem_raw_dir / "metadata.json"
    if bundle_meta.is_file():
        bundle_meta.unlink()

    # Second call: bundle is empty, so source_url and license_note should
    # keep their old values (non-destructive).
    with session_scope(database_url) as session:
        second_id = vdem.register_vdem_source(session)
    assert first_id == second_id
    with session_scope(database_url) as session:
        second = session.execute(
            select(Source).where(Source.id == second_id)
        ).scalar_one()
        assert second.source_url == first_url
        assert second.license_note == first_license


def test_write_vdem_observations_row_count(
    vdem_raw_dir: Path, vdem_catalog_path: Path, database_url: str
) -> None:
    """The fixture produces len(df) * len(specs) observations."""
    _init_test_db(database_url)
    csv_path = vdem_raw_dir / "V-Dem-CY-Full+Others-v16.csv"
    df = read_vdem_csv(csv_path=csv_path, catalog_path=vdem_catalog_path)
    specs = load_indicator_catalog(vdem_catalog_path)
    expected_rows = len(df) * len(specs)

    with session_scope(database_url) as session:
        source_id = vdem.register_vdem_source(session)
        rows_written = vdem.write_vdem_observations(
            session, source_id, df, catalog_path=vdem_catalog_path
        )
    assert rows_written == expected_rows

    with session_scope(database_url) as session:
        count = session.execute(
            select(func.count(SourceObservation.id)).where(
                SourceObservation.source_id == source_id
            )
        ).scalar_one()
    assert count == expected_rows


def test_write_vdem_observations_is_idempotent(
    vdem_raw_dir: Path, vdem_catalog_path: Path, database_url: str
) -> None:
    """Re-running ``write_vdem_observations`` does not duplicate rows."""
    _init_test_db(database_url)
    csv_path = vdem_raw_dir / "V-Dem-CY-Full+Others-v16.csv"
    df = read_vdem_csv(csv_path=csv_path, catalog_path=vdem_catalog_path)
    specs = load_indicator_catalog(vdem_catalog_path)
    expected_rows = len(df) * len(specs)

    with session_scope(database_url) as session:
        source_id = vdem.register_vdem_source(session)
        vdem.write_vdem_observations(session, source_id, df, catalog_path=vdem_catalog_path)
    with session_scope(database_url) as session:
        vdem.write_vdem_observations(session, source_id, df, catalog_path=vdem_catalog_path)

    with session_scope(database_url) as session:
        count = session.execute(
            select(func.count(SourceObservation.id)).where(
                SourceObservation.source_id == source_id
            )
        ).scalar_one()
    assert count == expected_rows


def test_write_vdem_observations_country_id_is_null(
    vdem_raw_dir: Path, vdem_catalog_path: Path, database_url: str
) -> None:
    """Stage 2 leaves ``country_id`` NULL - Stage 3 fills it in."""
    _init_test_db(database_url)
    csv_path = vdem_raw_dir / "V-Dem-CY-Full+Others-v16.csv"
    df = read_vdem_csv(csv_path=csv_path, catalog_path=vdem_catalog_path)

    with session_scope(database_url) as session:
        source_id = vdem.register_vdem_source(session)
        vdem.write_vdem_observations(session, source_id, df, catalog_path=vdem_catalog_path)

    with session_scope(database_url) as session:
        rows = session.execute(
            select(SourceObservation).where(SourceObservation.source_id == source_id)
        ).scalars().all()
    assert len(rows) == len(df) * len(load_indicator_catalog(vdem_catalog_path))
    # Every row has country_id == None, leader_id == None.
    assert all(r.country_id is None for r in rows)
    assert all(r.leader_id is None for r in rows)
    # source_row_reference is the V-Dem COW code prefixed with "vdem:".
    assert all(
        r.source_row_reference and r.source_row_reference.startswith("vdem:")
        for r in rows
    )


# ---------------------------------------------------------------------------
# Missing-value coercion
# ---------------------------------------------------------------------------


def test_coerce_float_v_dem_missing_sentinel() -> None:
    """V-Dem uses ``-999`` as the canonical missing sentinel (per the codebook)."""
    # Float sentinel at the boundary.
    assert _coerce_float(-999.0) is None
    assert _coerce_float(-999.5) is None
    assert _coerce_float(-1234.0) is None
    # Int sentinel.
    assert _coerce_float(-999) is None
    # Just above the boundary is NOT missing.
    assert _coerce_float(-998.999) is not None
    # Normal values are preserved.
    assert _coerce_float(0.5) == 0.5
    assert _coerce_float(0) == 0.0
    assert _coerce_float(3) == 3.0
    # Negative on the continuous C-type scale is NOT missing (e.g. v2csreprss).
    # The sentinel is only at or below VDEM_MISSING_SENTINEL.
    assert _coerce_float(-1.042) == -1.042
    assert _coerce_float(-3.72) == -3.72


def test_coerce_float_pandas_nan() -> None:
    """pandas NaN, None, and the ``nan`` string are missing."""
    assert _coerce_float(None) is None
    assert _coerce_float(float("nan")) is None
    assert _coerce_float_from_string("nan") is None
    assert _coerce_float_from_string("NaN") is None
    assert _coerce_float_from_string("NA") is None
    # Important 7: empty string is missing (defense in depth against
    # any pandas read that emits "" instead of NaN).
    assert _coerce_float_from_string("") is None
    assert _coerce_float_from_string("   ") is None
    # String "-999" is missing.
    assert _coerce_float_from_string("-999") is None
    # String "-999.0" parses to -999.0 which is the sentinel.
    assert _coerce_float_from_string("-999.0") is None


def test_coerce_float_string_numeric() -> None:
    """A string-encoded number is coerced to float."""
    assert _coerce_float_from_string("0.584") == 0.584
    assert _coerce_float_from_string("-1.042") == -1.042
    assert _coerce_float_from_string("0") == 0.0


def test_coerce_float_unknown_type() -> None:
    """Unknown types (list, dict) return None for safety."""
    assert _coerce_float([1, 2, 3]) is None
    assert _coerce_float({"a": 1}) is None


def test_raw_value_to_string_preserves_audit_trail() -> None:
    """``raw_value`` preserves the original cell for the audit trail."""
    assert _raw_value_to_string(0.584) == "0.584"
    assert _raw_value_to_string(-999.0) == "-999.0"
    assert _raw_value_to_string(float("nan")) == "nan"
    assert _raw_value_to_string(None) == ""
    assert _raw_value_to_string("0.5") == "0.5"


def test_write_vdem_observations_handles_missing_values(
    vdem_raw_dir: Path, vdem_catalog_path: Path, database_url: str
) -> None:
    """``-999`` and NaN cells become NULL ``normalized_value``; ``raw_value`` preserves them."""
    _init_test_db(database_url)
    csv_path = vdem_raw_dir / "V-Dem-CY-Full+Others-v16.csv"
    df = read_vdem_csv(csv_path=csv_path, catalog_path=vdem_catalog_path)
    # Wipe one column's values to simulate V-Dem's missing-data sentinel.
    df.loc[df.index[0], "v2x_polyarchy"] = -999.0
    df.loc[df.index[1], "v2x_libdem"] = float("nan")

    with session_scope(database_url) as session:
        source_id = vdem.register_vdem_source(session)
        vdem.write_vdem_observations(session, source_id, df, catalog_path=vdem_catalog_path)

    with session_scope(database_url) as session:
        rows = (
            session.execute(
                select(SourceObservation).where(
                    SourceObservation.source_id == source_id,
                    SourceObservation.variable_name.in_(
                        ["vdem_v2x_polyarchy", "vdem_v2x_libdem"]
                    ),
                )
            )
            .scalars()
            .all()
        )
    by_var: dict[str, list[SourceObservation]] = {}
    for r in rows:
        by_var.setdefault(r.variable_name, []).append(r)
    # The -999 row has NULL normalized_value and raw_value "-999.0".
    polyarchy = by_var["vdem_v2x_polyarchy"]
    assert any(r.raw_value == "-999.0" and r.normalized_value is None for r in polyarchy)
    # The NaN row has NULL normalized_value; raw_value is the string "nan".
    libdem = by_var["vdem_v2x_libdem"]
    assert any(r.normalized_value is None for r in libdem)
    assert any(r.raw_value == "nan" for r in libdem)
    # And the "good" rows still have real values.
    assert any(r.normalized_value is not None for r in polyarchy)
    assert any(r.normalized_value is not None for r in libdem)


# ---------------------------------------------------------------------------
# End-to-end orchestrator
# ---------------------------------------------------------------------------


def test_ingest_vdem_end_to_end(
    vdem_raw_dir: Path, vdem_catalog_path: Path, database_url: str
) -> None:
    """``ingest_vdem`` writes parquet + observations + sources + manifest in one call."""
    _init_test_db(database_url)
    result = vdem.ingest_vdem(
        csv_path=vdem_raw_dir / "V-Dem-CY-Full+Others-v16.csv",
        catalog_path=vdem_catalog_path,
    )
    assert isinstance(result, IngestResult)
    assert result.source_id > 0
    assert result.parquet_path.exists()
    expected_rows = 10 * 22  # 5 countries x 2 years x 22 indicators
    assert result.observation_rows == expected_rows
    assert result.countries == 5
    assert result.years == (2022, 2023)
    assert result.indicators == 22
    # The IngestResult carries the attribution (Rule #15).
    assert result.attribution == VDEM_ATTRIBUTION
    # The run manifest is auto-written (Important 8).
    manifest = result.parquet_path.parent / "vdem_run_manifest.json"
    assert manifest.exists()
    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert manifest_payload["attribution"] == VDEM_ATTRIBUTION
    assert manifest_payload["source_id"] == result.source_id
    assert manifest_payload["observation_rows"] == expected_rows


def test_ingest_vdem_filters_to_year(
    vdem_raw_dir: Path, vdem_catalog_path: Path, database_url: str
) -> None:
    """``year=2023`` keeps only 2023 rows in both the parquet and the DB."""
    _init_test_db(database_url)
    result = vdem.ingest_vdem(
        year=2023,
        csv_path=vdem_raw_dir / "V-Dem-CY-Full+Others-v16.csv",
        catalog_path=vdem_catalog_path,
    )
    assert result.countries == 5
    assert result.years == (2023,)
    expected_rows = 5 * 22
    assert result.observation_rows == expected_rows


def test_ingest_vdem_is_idempotent(
    vdem_raw_dir: Path, vdem_catalog_path: Path, database_url: str
) -> None:
    """Re-running ``ingest_vdem`` produces the same row count, not double."""
    _init_test_db(database_url)
    csv_path = vdem_raw_dir / "V-Dem-CY-Full+Others-v16.csv"
    first = vdem.ingest_vdem(csv_path=csv_path, catalog_path=vdem_catalog_path)
    second = vdem.ingest_vdem(csv_path=csv_path, catalog_path=vdem_catalog_path)
    assert first.source_id == second.source_id
    assert first.observation_rows == second.observation_rows == 10 * 22


# ---------------------------------------------------------------------------
# Run manifest + attribution (Rule #15)
# ---------------------------------------------------------------------------


def test_write_run_manifest(isolated_data_lake: Path) -> None:
    """The run manifest lives next to the parquet and includes the attribution."""
    result = IngestResult(
        source_id=1,
        parquet_path=isolated_data_lake / "data" / "processed" / VDEM_SOURCE_KEY / "x.parquet",
        observation_rows=220,
        countries=5,
        years=(2022, 2023),
        indicators=22,
    )
    manifest_path = vdem.write_run_manifest(result)
    assert manifest_path.exists()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["source_id"] == 1
    assert payload["observation_rows"] == 220
    assert payload["years"] == [2022, 2023]
    assert payload["attribution"] == VDEM_ATTRIBUTION


def test_attribution_matches_constant() -> None:
    """``attribution()`` returns the module-level constant."""
    assert vdem.attribution() == VDEM_ATTRIBUTION
    # The constant references the V-Dem DOI and the v16 version.
    assert "vdemds26" in vdem.attribution()
    assert "V-Dem" in vdem.attribution()
    assert "v16" in vdem.attribution()


def test_vdem_attribution_matches_attributions_doc() -> None:
    """The constant is a substring of ``docs/sources/attributions.md`` (drift guard).

    This is the Rule #15 contract: the code's attribution text and the
    doc's citation text are byte-for-byte consistent. If the doc is
    updated (e.g. a new V-Dem version is released), update
    ``VDEM_ATTRIBUTION`` in the same commit.
    """
    doc_path = Path(__file__).resolve().parents[1] / "docs" / "sources/attributions.md"
    doc_text = doc_path.read_text(encoding="utf-8")
    # The code constant must be a substring of the doc. The doc may
    # include additional text (e.g. the "And:" Measurement Model paper);
    # the code constant is just the dataset citation.
    assert VDEM_ATTRIBUTION in doc_text, (
        f"VDEM_ATTRIBUTION is not present in {doc_path}. "
        "Update both in the same commit (Rule #15)."
    )
    # The "Attribution text in reports" footer in the doc is the
    # short form the Stage 15 reports will use.
    assert "V-Dem v16 (Coppedge et al. 2026)" in doc_text


# ---------------------------------------------------------------------------
# CLI dispatch (Important 4)
# ---------------------------------------------------------------------------


def test_stage2_adapters_dispatch_table() -> None:
    """The dispatch table registers the V-Dem orchestrator (Important 4)."""
    assert STAGE2_ADAPTERS[VDEM_SOURCE_KEY] is vdem.ingest_vdem
    # All other 22 priority sources are listed (None = not implemented yet).
    expected_keys = {
        "vdem", "world_bank_wdi", "world_bank_wgi", "ucdp",
        "sipri_milex", "sipri_yearbook_ch7", "pts", "undp_hdi",
        "who_gho_api", "polity_v", "pwt", "archigos", "reign",
        "leader_survival", "transparency_cpi", "fas",
        "wikidata_heads_of_state_government", "wikipedia_search_extract",
        "freedom_house", "imf_weo", "cow_mid", "cirights",
        "nti", "bti", "cia_world_leaders", "rsf_press_freedom",
        "maddison_project",
    }
    assert expected_keys == set(STAGE2_ADAPTERS.keys())


def test_cli_ingest_source_rejects_unknown() -> None:
    """The CLI's ``ingest-source`` command rejects unknown source keys."""
    runner = CliRunner()
    result = runner.invoke(app, ["ingest-source", "--source", "nope"])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# session_scope env override (Blocker 5 regression test)
# ---------------------------------------------------------------------------


def test_session_scope_respects_leader_sdb_project_root_env(
    isolated_data_lake: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``session_scope()`` writes to the env-var-resolved DB, not the CWD-relative one.

    Regression test for the pre-existing bug where
    ``make_session_factory`` hard-coded ``sqlite:///data/catalog/...``;
    after the fix in :mod:`leaders_db.db.session`, the default URL
    resolves through :func:`leaders_db.paths.project_root` and honors
    ``LEADERSDB_PROJECT_ROOT``. Without this test, the
    ``isolated_data_lake`` fixture could be re-broken silently.
    """
    # The fixture has set LEADERSDB_PROJECT_ROOT; the resolved URL must
    # point inside the isolated data lake.
    assert str(isolated_data_lake) in default_sqlite_url()
    # The URL must NOT be a CWD-relative one (which would be
    # ``sqlite:///data/catalog/leaders_db.sqlite`` with three slashes).
    assert default_sqlite_url().count("/") >= 4
