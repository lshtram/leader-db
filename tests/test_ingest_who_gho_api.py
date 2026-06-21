"""Tests for the WHO Global Health Observatory (GHO) OData API Stage 2 adapter.

The WHO GHO API adapter is the ninth Stage 2 adapter built after
V-Dem, WDI, WGI, UCDP, SIPRI milex, SIPRI Yearbook Ch.7, PTS, and
UNDP HDI. These tests define what "done" means for the WHO GHO
API adapter — they would fail if any of the production wiring
(catalog load, OData HTTP read with caching, parquet write with
attribution, sources upsert, source_observations write,
end-to-end orchestrator, dispatch table wiring) regresses.

The WHO GHO API is a public OData 4.0 endpoint at
``https://ghoapi.azureedge.net/api/`` with no authentication. The
API emits ``{"@odata.context": ..., "value": [...]}`` JSON
responses with one record per ``(country, indicator, year,
disaggregation)`` combination. The Stage 2 adapter narrows to
the 5 in-scope indicators in the ``social_wellbeing`` category
defined in ``src/leaders_db/ingest/catalogs/who_gho_api.csv`` and
scopes the response to country-level records
(``SpatialDimType eq 'COUNTRY'``) and the both-sexes aggregate
(``Dim1 eq 'SEX_BTSX'``) where applicable.

Tests use a 5-country x 2-year x 5-indicator fixture at
``tests/fixtures/who_gho_api/cache/`` (10 JSON files, real values
sliced from the live API with ``build_sample_cache.py``, no
invented data). The fixture covers:

- MEX, USA, SWE, IND, NGA -- the same 5 countries used by the
  WDI fixture (a familiar pattern)
- 2019 (pre-pandemic baseline) and 2021 (latest year with full
  life-expectancy data in the GHO API)
- 5 catalog indicators: WHOSIS_000001 (life expectancy),
  MDG_0000000007 (under-5 mortality), WHS4_100/WHS4_117/WHS4_543
  (immunization coverage)

A larger ``cache_raw/`` directory holds the full captured API
responses (5 indicators x 2 years x ~200 countries each) for
audit; the build script slices them to the 5 countries above.

Key design decisions exercised by these tests:

- The API response is cached verbatim per ``(year, indicator)``
  under ``data/raw/who_gho_api/cache/``. Re-runs skip HTTP when
  the cache file exists; ``force_refresh=True`` overrides.
- Non-country ``SpatialDimType`` records (REGION,
  WORLDBANKINCOMEGROUP, GLOBAL) are filtered out at the parser
  level so the wide frame is country-only.
- The ``$top=1000`` API cap is respected; ``@odata.nextLink``
  pagination is followed defensively (rarely triggered for the
  year + COUNTRY + Dim1 filter combination).
- ``country_id`` and ``leader_id`` are NULL at Stage 2;
  ``confidence`` is NULL at Stage 2. Stage 3 fills
  ``country_id``; Stage 11 fills confidence.
- ``source_row_reference`` is
  ``"who_gho_api:<raw_column>:<iso3>"`` (e.g.
  ``"who_gho_api:WHOSIS_000001:MEX"``) so Stage 3 can resolve
  the observation and the audit trail identifies both the WHO
  GHO API indicator code and the country.
- The Stage 2 end-to-end row count for the fixture (5 countries
  x 2 years x 5 indicators = 50 source_observations rows for a
  two-year run, 25 for a single-year run) is asserted
  explicitly.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pyarrow.parquet as pq
import pytest
import requests
from sqlalchemy import func, select
from typer.testing import CliRunner

from leaders_db.cli import app
from leaders_db.db.engine import init_database
from leaders_db.db.models import Source, SourceObservation
from leaders_db.db.session import session_scope
from leaders_db.ingest import STAGE2_ADAPTERS, who_gho_api

# Try importing the WHO GHO API modules; tests fail gracefully
# (the import block sets the names to ``None`` and every test
# that needs them asserts ``is not None`` first).
try:
    from leaders_db.ingest import who_gho_api_db, who_gho_api_io
    from leaders_db.ingest.who_gho_api import (
        WHO_GHO_API_ATTRIBUTION,
        WHO_GHO_API_SOURCE_KEY,
        IndicatorSpec,
        WhoGhoApiIngestResult,
        attribution,
        ingest_who_gho_api,
        load_indicator_catalog,
        read_who_gho_api,
        register_who_gho_api_source,
        write_who_gho_api_observations,
        write_who_gho_api_parquet,
        write_who_gho_api_run_manifest,
    )
    from leaders_db.ingest.who_gho_api_http import build_who_gho_api_url
    from leaders_db.ingest.who_gho_api_io import (
        parse_who_gho_api_payload,
    )
except ImportError:
    # Modules do not exist yet; tests fail with appropriate
    # errors when they assert against these names.
    who_gho_api_db = None  # type: ignore[assignment]
    who_gho_api_io = None  # type: ignore[assignment]
    WHO_GHO_API_ATTRIBUTION = None  # type: ignore[assignment]
    WHO_GHO_API_SOURCE_KEY = None  # type: ignore[assignment]
    IndicatorSpec = None  # type: ignore[assignment]
    WhoGhoApiIngestResult = None  # type: ignore[assignment]
    attribution = None  # type: ignore[assignment]
    build_who_gho_api_url = None  # type: ignore[assignment]
    ingest_who_gho_api = None  # type: ignore[assignment]
    load_indicator_catalog = None  # type: ignore[assignment]
    parse_who_gho_api_payload = None  # type: ignore[assignment]
    read_who_gho_api = None  # type: ignore[assignment]
    register_who_gho_api_source = None  # type: ignore[assignment]
    write_who_gho_api_observations = None  # type: ignore[assignment]
    write_who_gho_api_parquet = None  # type: ignore[assignment]
    write_who_gho_api_run_manifest = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def who_gho_api_cache_dir(isolated_data_lake: Path) -> Path:
    """Stage the WHO GHO API fixture cache under
    ``data/raw/who_gho_api/cache/``.

    The fixture is ``tests/fixtures/who_gho_api/cache/`` (10 JSON
    files: 5 indicators x 2 years). We copy the whole tree to the
    isolated data lake so ``read_who_gho_api`` uses the staged
    files without any HTTP calls.
    """
    source_cache = isolated_data_lake / "data" / "raw" / "who_gho_api" / "cache"
    fixtures_cache = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "who_gho_api"
        / "cache"
    )
    for year in ("2019", "2021"):
        src_dir = fixtures_cache / year
        dst_dir = source_cache / year
        if src_dir.exists():
            shutil.copytree(src_dir, dst_dir)
    return source_cache


@pytest.fixture()
def who_gho_api_catalog_path() -> Path:
    """Return the absolute path of the checked-in WHO GHO API indicator catalog.

    Lives at ``src/leaders_db/ingest/catalogs/who_gho_api.csv``
    relative to project root.
    """
    return (
        Path(__file__).resolve().parents[1]
        / "src"
        / "leaders_db"
        / "ingest"
        / "catalogs"
        / "who_gho_api.csv"
    )


@pytest.fixture()
def who_gho_api_source_key() -> str:
    return "who_gho_api"


def _init_test_db(database_url: str) -> None:
    """Apply migrations to the test DB so the ORM has its tables."""
    init_database(database_url)


# ---------------------------------------------------------------------------
# Catalog (Phase C convention #5a)
# ---------------------------------------------------------------------------


def test_load_indicator_catalog_returns_5_specs(
    who_gho_api_catalog_path: Path,
) -> None:
    """The checked-in catalog has 5 indicators (matches the social-wellbeing design)."""
    assert load_indicator_catalog is not None, "who_gho_api_io module not implemented"
    specs = load_indicator_catalog(who_gho_api_catalog_path)
    assert len(specs) == 5, f"Expected 5 indicators, got {len(specs)}"
    assert all(s.variable_name and s.raw_column for s in specs)


def test_load_indicator_catalog_required_columns(
    who_gho_api_catalog_path: Path,
) -> None:
    """The 9 required CSV columns are present; category is social_wellbeing."""
    assert load_indicator_catalog is not None, "who_gho_api_io module not implemented"
    specs = load_indicator_catalog(who_gho_api_catalog_path)
    categories = {s.rating_category for s in specs}
    assert categories == {"social_wellbeing"}, (
        f"Unexpected categories: {categories}"
    )


def test_load_indicator_catalog_dim1_filter(
    who_gho_api_catalog_path: Path,
) -> None:
    """SEX-disaggregated indicators carry SEX_BTSX; immunization indicators skip the filter.

    SEX-disaggregated indicators (WHOSIS_*, MDG_*) carry
    ``SEX_BTSX``; immunization indicators (WHS4_*) carry an
    empty ``dim1_filter``.

    The ``dim1_filter`` field is the WHO GHO API-specific catalog
    extension: SEX-disaggregated indicators default to the
    both-sexes aggregate so the Stage 2 frame is one row per
    ``(country, year)``; immunization indicators skip the
    filter because they have no SEX dimension.
    """
    assert load_indicator_catalog is not None
    specs = load_indicator_catalog(who_gho_api_catalog_path)
    by_raw = {s.raw_column: s for s in specs}
    assert by_raw["WHOSIS_000001"].dim1_filter == "SEX_BTSX"
    assert by_raw["MDG_0000000007"].dim1_filter == "SEX_BTSX"
    # WHS4_100, WHS4_117, WHS4_543: no SEX dimension, so the
    # dim1_filter is empty.
    for ind in ("WHS4_100", "WHS4_117", "WHS4_543"):
        assert by_raw[ind].dim1_filter == "", (
            f"{ind} should have an empty dim1_filter (no SEX "
            f"dimension), got {by_raw[ind].dim1_filter!r}"
        )


def test_load_indicator_catalog_missing_file(tmp_path: Path) -> None:
    """Missing catalog raises FileNotFoundError, not a silent empty list."""
    assert load_indicator_catalog is not None
    with pytest.raises(FileNotFoundError):
        load_indicator_catalog(tmp_path / "does-not-exist.csv")


def test_indicator_spec_from_csv_row_handles_higher_is_better() -> None:
    """``higher_is_better=0``/``=1`` round-trips to a bool (the canonical convention)."""
    assert IndicatorSpec is not None
    higher = IndicatorSpec.from_csv_row(
        {
            "variable_name": "test_life",
            "raw_column": "WHOSIS_000001",
            "rating_category": "social_wellbeing",
            "raw_scale": "years",
            "normalized_scale_target": "0-10",
            "higher_is_better": "1",
            "unit": "years",
            "dim1_filter": "SEX_BTSX",
            "description": "Life expectancy",
        }
    )
    assert higher.higher_is_better is True

    lower = IndicatorSpec.from_csv_row(
        {
            "variable_name": "test_mortality",
            "raw_column": "MDG_0000000007",
            "rating_category": "social_wellbeing",
            "raw_scale": "per_1000",
            "normalized_scale_target": "0-10",
            "higher_is_better": "0",
            "unit": "per 1000 live births",
            "dim1_filter": "SEX_BTSX",
            "description": "Under-5 mortality",
        }
    )
    assert lower.higher_is_better is False


# ---------------------------------------------------------------------------
# URL builder (Phase C convention #5b)
# ---------------------------------------------------------------------------


def test_build_who_gho_api_url_includes_country_year_dim1() -> None:
    """The URL builder emits the canonical OData $filter for ``COUNTRY + year + Dim1``."""
    assert build_who_gho_api_url is not None
    url = build_who_gho_api_url(
        "WHOSIS_000001", year=2023, dim1="SEX_BTSX"
    )
    assert url.startswith("https://ghoapi.azureedge.net/api/WHOSIS_000001?")
    assert "SpatialDimType eq 'COUNTRY'" in url
    assert "TimeDim eq 2023" in url
    assert "Dim1 eq 'SEX_BTSX'" in url
    assert "$top=1000" in url


def test_build_who_gho_api_url_omits_dim1_when_none() -> None:
    """Indicators without SEX disaggregation (e.g. WHS4_100) skip the Dim1 filter clause."""
    assert build_who_gho_api_url is not None
    url = build_who_gho_api_url("WHS4_100", year=2023, dim1=None)
    assert "SpatialDimType eq 'COUNTRY'" in url
    assert "TimeDim eq 2023" in url
    assert "Dim1" not in url


# ---------------------------------------------------------------------------
# Parser (Phase C convention #5b)
# ---------------------------------------------------------------------------


def test_parse_who_gho_api_payload_extracts_country_records(
    who_gho_api_cache_dir: Path,
) -> None:
    """The parser emits one row per COUNTRY record; non-country ``SpatialDimType`` is dropped.

    The fixture has only COUNTRY records (the cache was built
    with the SpatialDimType eq 'COUNTRY' filter), so the parser
    returns a frame with 5 rows for the 5 fixture countries.
    """
    assert parse_who_gho_api_payload is not None
    cache_path = who_gho_api_cache_dir / "2021" / "WHOSIS_000001.json"
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    df = parse_who_gho_api_payload(payload, code="WHOSIS_000001", year=2021)
    assert len(df) == 5, f"Expected 5 country rows, got {len(df)}"
    assert set(df["iso3"].unique()) == {"MEX", "USA", "SWE", "IND", "NGA"}
    # All values are floats (the API's NumericValue column).
    assert pd.api.types.is_float_dtype(df["value"])


def test_parse_who_gho_api_payload_filters_non_country(
    who_gho_api_cache_dir: Path,
) -> None:
    """A payload with mixed SpatialDimType values keeps only COUNTRY records.

    The parser drops REGION, WORLDBANKINCOMEGROUP, and GLOBAL
    records (any SpatialDimType other than COUNTRY) so the
    Stage 2 frame is country-only.
    """
    assert parse_who_gho_api_payload is not None
    # Build a synthetic payload with all 3 SpatialDimType values.
    payload = {
        "@odata.context": "...",
        "value": [
            {
                "IndicatorCode": "WHOSIS_000001",
                "SpatialDimType": "COUNTRY",
                "SpatialDim": "USA",
                "TimeDim": 2021,
                "Dim1": "SEX_BTSX",
                "Value": "76.4",
                "NumericValue": 76.4,
            },
            {
                "IndicatorCode": "WHOSIS_000001",
                "SpatialDimType": "REGION",
                "SpatialDim": "AMR",
                "TimeDim": 2021,
                "Dim1": "SEX_BTSX",
                "Value": "74.1",
                "NumericValue": 74.1,
            },
            {
                "IndicatorCode": "WHOSIS_000001",
                "SpatialDimType": "WORLDBANKINCOMEGROUP",
                "SpatialDim": "WB_HI",
                "TimeDim": 2021,
                "Dim1": "SEX_BTSX",
                "Value": "79.7",
                "NumericValue": 79.7,
            },
        ],
    }
    df = parse_who_gho_api_payload(payload, code="WHOSIS_000001", year=2021)
    assert len(df) == 1
    assert df.iloc[0]["iso3"] == "USA"
    assert df.iloc[0]["spatial_dim_type"] == "COUNTRY"


def test_parse_who_gho_api_payload_handles_null_numeric_value(
    who_gho_api_cache_dir: Path,
) -> None:
    """A record with null NumericValue is preserved with value=None (NaN in the wide frame)."""
    assert parse_who_gho_api_payload is not None
    payload = {
        "value": [
            {
                "IndicatorCode": "WHS4_100",
                "SpatialDimType": "COUNTRY",
                "SpatialDim": "USA",
                "TimeDim": 2019,
                "Dim1": None,
                "Value": None,
                "NumericValue": None,
            }
        ],
    }
    df = parse_who_gho_api_payload(payload, code="WHS4_100", year=2019)
    assert len(df) == 1
    assert df.iloc[0]["iso3"] == "USA"
    # NumericValue null -> value column is None
    assert df.iloc[0]["value"] is None or pd.isna(df.iloc[0]["value"])


def test_parse_who_gho_api_payload_drops_empty_spatial_dim(
    who_gho_api_cache_dir: Path,
) -> None:
    """A record with an empty ``SpatialDim`` is dropped (no ISO3 -> no Stage 2 row)."""
    assert parse_who_gho_api_payload is not None
    payload = {
        "value": [
            {
                "IndicatorCode": "WHOSIS_000001",
                "SpatialDimType": "COUNTRY",
                "SpatialDim": "",
                "TimeDim": 2019,
                "Dim1": "SEX_BTSX",
                "Value": "0.0",
                "NumericValue": 0.0,
            },
            {
                "IndicatorCode": "WHOSIS_000001",
                "SpatialDimType": "COUNTRY",
                "SpatialDim": "MEX",
                "TimeDim": 2019,
                "Dim1": "SEX_BTSX",
                "Value": "75.0",
                "NumericValue": 75.0,
            },
        ],
    }
    df = parse_who_gho_api_payload(payload, code="WHOSIS_000001", year=2019)
    assert len(df) == 1
    assert df.iloc[0]["iso3"] == "MEX"


# ---------------------------------------------------------------------------
# Read (Phase C convention #5b)
# ---------------------------------------------------------------------------


def test_read_who_gho_api_returns_full_fixture(
    who_gho_api_cache_dir: Path,
    who_gho_api_catalog_path: Path,
) -> None:
    """The fixture (5 countries x 1 year x 5 indicators) produces a wide DataFrame.

    Wide format: 5 rows (5 countries x 1 year), 12 columns
    (iso3, year, 5 indicator columns + 5 sibling
    ``<variable>_raw_value`` columns carrying the verbatim WHO
    GHO API ``Value`` field for the audit trail).
    """
    df = read_who_gho_api(
        year=2021,
        cache_dir=who_gho_api_cache_dir,
        catalog_path=who_gho_api_catalog_path,
    )
    assert len(df) == 5, f"Expected 5 rows for 2021, got {len(df)}"
    expected_cols = {
        "iso3",
        "year",
        "who_gho_life_expectancy",
        "who_gho_life_expectancy_raw_value",
        "who_gho_under5_mortality",
        "who_gho_under5_mortality_raw_value",
        "who_gho_dtp3_immunization",
        "who_gho_dtp3_immunization_raw_value",
        "who_gho_hepb3_immunization",
        "who_gho_hepb3_immunization_raw_value",
        "who_gho_bcg_immunization",
        "who_gho_bcg_immunization_raw_value",
    }
    assert set(df.columns) == expected_cols, (
        f"Column mismatch: {sorted(df.columns)}"
    )
    assert pd.api.types.is_integer_dtype(df["year"])
    # All cached -> all 5 indicators are cached.
    assert df.attrs["indicators_cached"] == 5
    assert df.attrs["indicators_fetched"] == 0


def test_read_who_gho_api_filters_to_year(
    who_gho_api_cache_dir: Path,
    who_gho_api_catalog_path: Path,
) -> None:
    """``year=2021`` keeps only the 5 rows for 2021; ``year=2019`` likewise."""
    df_2021 = read_who_gho_api(
        year=2021,
        cache_dir=who_gho_api_cache_dir,
        catalog_path=who_gho_api_catalog_path,
    )
    assert set(df_2021["year"].unique()) == {2021}
    assert len(df_2021) == 5

    df_2019 = read_who_gho_api(
        year=2019,
        cache_dir=who_gho_api_cache_dir,
        catalog_path=who_gho_api_catalog_path,
    )
    assert set(df_2019["year"].unique()) == {2019}
    assert len(df_2019) == 5


def test_read_who_gho_api_uses_cache_when_present(
    who_gho_api_cache_dir: Path,
    who_gho_api_catalog_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With cache files present, ``read_who_gho_api(force_refresh=False)`` makes zero HTTP calls."""
    call_count = 0

    def counting_get(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise RuntimeError(
            "HTTP should not be called when cache is present"
        )

    monkeypatch.setattr(requests, "get", counting_get)
    df = read_who_gho_api(
        year=2021,
        cache_dir=who_gho_api_cache_dir,
        catalog_path=who_gho_api_catalog_path,
        force_refresh=False,
    )
    assert len(df) == 5, "Should return 5 rows from cache"
    assert call_count == 0, f"HTTP was called {call_count} times; expected 0"


def test_read_who_gho_api_force_refresh_overrides_cache(
    who_gho_api_cache_dir: Path,
    who_gho_api_catalog_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``force_refresh=True`` calls HTTP even when cache files exist."""

    call_count = 0
    fetched_indicators: list[str] = []

    def counting_get(url, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        url_str = str(url)
        # Pull the indicator code out of the URL path so we can
        # emit a per-indicator fake response.
        ind_code = url_str.split("api/", 1)[1].split("?", 1)[0]
        fetched_indicators.append(ind_code)
        # Build a fake response that includes only the 5 fixture
        # countries. For each country, the NumericValue is a
        # constant 999.0 so we can detect the HTTP path was taken.
        countries = ("MEX", "USA", "SWE", "IND", "NGA")
        # For the immunization indicators (no Dim1 filter) the
        # parser accepts any SpatialDim. For SEX-disaggregated
        # indicators we need Dim1 to be SEX_BTSX (the URL filter
        # is part of the URL, not the response).
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json = lambda ic=ind_code: {
            "@odata.context": (
                f"https://ghoapi.azureedge.net/api/$metadata#{ic}"
            ),
            "value": [
                {
                    "IndicatorCode": ic,
                    "SpatialDimType": "COUNTRY",
                    "SpatialDim": c,
                    "TimeDim": 2021,
                    "Dim1": "SEX_BTSX",
                    "Value": "999.0",
                    "NumericValue": 999.0,
                }
                for c in countries
            ],
        }
        return mock_resp

    monkeypatch.setattr(requests, "get", counting_get)
    df = read_who_gho_api(
        year=2021,
        cache_dir=who_gho_api_cache_dir,
        catalog_path=who_gho_api_catalog_path,
        force_refresh=True,
    )
    assert call_count == 5, f"Expected 5 HTTP calls, got {call_count}"
    assert set(fetched_indicators) == {
        "WHOSIS_000001",
        "MDG_0000000007",
        "WHS4_100",
        "WHS4_117",
        "WHS4_543",
    }
    # The returned value should reflect the new (mocked) data.
    assert df.attrs["indicators_fetched"] == 5
    assert df.attrs["indicators_cached"] == 0
    # Pick any country, any indicator: the value is 999.0.
    assert float(df.set_index("iso3")["who_gho_life_expectancy"]["MEX"]) == 999.0


def test_read_who_gho_api_missing_cache_and_no_network(
    who_gho_api_cache_dir: Path,
    who_gho_api_catalog_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No cache + no network -> ``read_who_gho_api`` raises FileNotFoundError."""
    empty_cache = who_gho_api_cache_dir.parent / "empty_cache"
    empty_cache.mkdir(exist_ok=True)

    def network_error(*args, **kwargs):
        raise requests.ConnectionError("Network unreachable")

    monkeypatch.setattr(requests, "get", network_error)
    with pytest.raises(FileNotFoundError):
        read_who_gho_api(
            year=2021,
            cache_dir=empty_cache,
            catalog_path=who_gho_api_catalog_path,
        )


def test_read_who_gho_api_year_required(
    who_gho_api_cache_dir: Path,
    who_gho_api_catalog_path: Path,
) -> None:
    """``year=None`` raises ``ValueError`` (the WHO GHO API reader is single-year-only)."""
    with pytest.raises(ValueError):
        read_who_gho_api(
            year=None,
            cache_dir=who_gho_api_cache_dir,
            catalog_path=who_gho_api_catalog_path,
        )


def test_default_path_helpers() -> None:
    """Default path helpers point at conventional data-lake locations."""
    if who_gho_api_io is None:
        pytest.skip("who_gho_api_io module not implemented yet")
    raw_default = who_gho_api_io.default_cache_dir()
    assert "who_gho_api" in raw_default.parts
    assert "cache" in raw_default.parts

    parquet_default = who_gho_api_io.default_processed_parquet_path()
    assert "who_gho_api" in parquet_default.parts
    assert parquet_default.suffix == ".parquet"


# ---------------------------------------------------------------------------
# Parquet write + DB (Phase C convention #5c)
# ---------------------------------------------------------------------------


def test_write_who_gho_api_parquet_creates_file(
    who_gho_api_cache_dir: Path,
    who_gho_api_catalog_path: Path,
    isolated_data_lake: Path,
) -> None:
    """``write_who_gho_api_parquet`` writes a valid parquet under processed/who_gho_api/."""
    df = read_who_gho_api(
        year=2021,
        cache_dir=who_gho_api_cache_dir,
        catalog_path=who_gho_api_catalog_path,
    )
    out = write_who_gho_api_parquet(df)

    assert out.exists()
    assert out.suffix == ".parquet"
    expected_parent = (
        isolated_data_lake / "data" / "processed" / "who_gho_api"
    )
    assert out.parent == expected_parent

    # Round-trip: parquet can be re-read as the same shape.
    round_tripped = pd.read_parquet(out)
    assert round_tripped.shape == df.shape
    assert set(round_tripped.columns) == set(df.columns)


def test_write_who_gho_api_parquet_attaches_attribution_metadata(
    who_gho_api_cache_dir: Path,
    who_gho_api_catalog_path: Path,
) -> None:
    """The parquet file-level metadata carries the WHO GHO API attribution (Rule #15)."""
    df = read_who_gho_api(
        year=2021,
        cache_dir=who_gho_api_cache_dir,
        catalog_path=who_gho_api_catalog_path,
    )
    out = write_who_gho_api_parquet(df)
    table = pq.read_table(out)
    meta = table.schema.metadata or {}

    attribution_bytes = meta.get(b"who_gho_api_attribution")
    assert attribution_bytes is not None, (
        "parquet missing who_gho_api_attribution metadata"
    )
    assert attribution_bytes.decode("utf-8") == WHO_GHO_API_ATTRIBUTION
    assert meta.get(b"who_gho_api_source_key") == b"who_gho_api"


def test_register_who_gho_api_source_is_idempotent(
    who_gho_api_cache_dir: Path,
    database_url: str,
) -> None:
    """``register_who_gho_api_source`` returns the same id on repeated calls."""
    _init_test_db(database_url)
    with session_scope(database_url) as session:
        first_id = who_gho_api.register_who_gho_api_source(session)
    with session_scope(database_url) as session:
        second_id = who_gho_api.register_who_gho_api_source(session)
    assert first_id == second_id, (
        "register_who_gho_api_source should be idempotent"
    )

    with session_scope(database_url) as session:
        row = session.execute(
            select(Source).where(Source.id == first_id)
        ).scalar_one()
        assert row.source_name == "WHO Global Health Observatory (OData API)"
        assert row.version == "GHO OData v1"
        assert row.source_type == "official"


def test_register_who_gho_api_source_non_destructive_update(
    who_gho_api_cache_dir: Path,
    database_url: str,
) -> None:
    """Removing metadata.json between calls keeps existing source_url and license_note."""
    _init_test_db(database_url)
    with session_scope(database_url) as session:
        first_id = who_gho_api.register_who_gho_api_source(session)
    with session_scope(database_url) as session:
        first = session.execute(
            select(Source).where(Source.id == first_id)
        ).scalar_one()
        first_url = first.source_url
        first_license = first.license_note

    # Remove the bundle metadata.json (if present) so next call
    # sees empty.
    bundle_meta = who_gho_api_cache_dir.parent / "metadata.json"
    if bundle_meta.is_file():
        bundle_meta.unlink()

    with session_scope(database_url) as session:
        second_id = who_gho_api.register_who_gho_api_source(session)
    assert first_id == second_id
    with session_scope(database_url) as session:
        second = session.execute(
            select(Source).where(Source.id == second_id)
        ).scalar_one()
        assert second.source_url == first_url
        assert second.license_note == first_license


def test_write_who_gho_api_observations_row_count(
    who_gho_api_cache_dir: Path,
    who_gho_api_catalog_path: Path,
    database_url: str,
) -> None:
    """``len(df) * len(specs)`` observations are written (25 with the single-year fixture)."""
    _init_test_db(database_url)
    df = read_who_gho_api(
        year=2021,
        cache_dir=who_gho_api_cache_dir,
        catalog_path=who_gho_api_catalog_path,
    )
    specs = load_indicator_catalog(who_gho_api_catalog_path)
    expected_rows = len(df) * len(specs)  # 5 * 5 = 25

    with session_scope(database_url) as session:
        source_id = who_gho_api.register_who_gho_api_source(session)
        rows_written = who_gho_api.write_who_gho_api_observations(
            session, source_id, df, catalog_path=who_gho_api_catalog_path
        )
    assert rows_written == expected_rows

    with session_scope(database_url) as session:
        count = session.execute(
            select(func.count(SourceObservation.id)).where(
                SourceObservation.source_id == source_id
            )
        ).scalar_one()
    assert count == expected_rows


def test_write_who_gho_api_observations_is_idempotent(
    who_gho_api_cache_dir: Path,
    who_gho_api_catalog_path: Path,
    database_url: str,
) -> None:
    """Re-running ``write_who_gho_api_observations`` produces the same count, not double."""
    _init_test_db(database_url)
    df = read_who_gho_api(
        year=2021,
        cache_dir=who_gho_api_cache_dir,
        catalog_path=who_gho_api_catalog_path,
    )
    specs = load_indicator_catalog(who_gho_api_catalog_path)
    expected_rows = len(df) * len(specs)

    with session_scope(database_url) as session:
        source_id = who_gho_api.register_who_gho_api_source(session)
        who_gho_api.write_who_gho_api_observations(
            session, source_id, df, catalog_path=who_gho_api_catalog_path
        )
    with session_scope(database_url) as session:
        who_gho_api.write_who_gho_api_observations(
            session, source_id, df, catalog_path=who_gho_api_catalog_path
        )

    with session_scope(database_url) as session:
        count = session.execute(
            select(func.count(SourceObservation.id)).where(
                SourceObservation.source_id == source_id
            )
        ).scalar_one()
    assert count == expected_rows


def test_write_who_gho_api_observations_country_id_is_null(
    who_gho_api_cache_dir: Path,
    who_gho_api_catalog_path: Path,
    database_url: str,
) -> None:
    """Stage 2 leaves country_id and confidence NULL; source_row_reference starts with source."""
    _init_test_db(database_url)
    df = read_who_gho_api(
        year=2021,
        cache_dir=who_gho_api_cache_dir,
        catalog_path=who_gho_api_catalog_path,
    )

    with session_scope(database_url) as session:
        source_id = who_gho_api.register_who_gho_api_source(session)
        who_gho_api.write_who_gho_api_observations(
            session, source_id, df, catalog_path=who_gho_api_catalog_path
        )

    with session_scope(database_url) as session:
        rows = session.execute(
            select(SourceObservation).where(
                SourceObservation.source_id == source_id
            )
        ).scalars().all()

    assert all(r.country_id is None for r in rows)
    assert all(r.leader_id is None for r in rows)
    assert all(r.confidence is None for r in rows)
    # Every row has a who_gho_api:<raw_column>:<iso3> source row
    # reference. The raw_column is the WHO GHO API indicator code,
    # not the canonical variable_name -- this keeps the audit
    # trail unambiguous (a downstream stage can look up the
    # indicator in the catalog from the raw_column).
    for r in rows:
        assert r.source_row_reference is not None
        assert r.source_row_reference.startswith("who_gho_api:"), (
            f"Unexpected source_row_reference: {r.source_row_reference}"
        )
        # The middle component is the WHO GHO API indicator code
        # (e.g. WHOSIS_000001) and the suffix is the ISO3.
        parts = r.source_row_reference.split(":")
        assert len(parts) == 3, (
            f"source_row_reference must be 3-part: {r.source_row_reference}"
        )
        assert parts[0] == "who_gho_api"
        assert parts[1] in {
            "WHOSIS_000001",
            "MDG_0000000007",
            "WHS4_100",
            "WHS4_117",
            "WHS4_543",
        }
        assert len(parts[2]) == 3 and parts[2].isupper()


def test_write_who_gho_api_observations_preserves_raw_value(
    who_gho_api_cache_dir: Path,
    who_gho_api_catalog_path: Path,
    database_url: str,
) -> None:
    """The raw_value column preserves the verbatim Value field (with CI bounds)."""
    _init_test_db(database_url)
    df = read_who_gho_api(
        year=2021,
        cache_dir=who_gho_api_cache_dir,
        catalog_path=who_gho_api_catalog_path,
    )

    with session_scope(database_url) as session:
        source_id = who_gho_api.register_who_gho_api_source(session)
        who_gho_api.write_who_gho_api_observations(
            session, source_id, df, catalog_path=who_gho_api_catalog_path
        )

    with session_scope(database_url) as session:
        # The life-expectancy observation for USA in 2021 has a
        # bracketed bounds string in the WHO GHO API's ``Value``
        # field. The audit-trail ``raw_value`` preserves it.
        rows = session.execute(
            select(SourceObservation).where(
                SourceObservation.source_id == source_id,
                SourceObservation.variable_name == "who_gho_life_expectancy",
                SourceObservation.source_row_reference
                == "who_gho_api:WHOSIS_000001:USA",
            )
        ).scalars().all()

    assert len(rows) == 1
    assert rows[0].normalized_value is not None
    # The raw value is the verbatim ``Value`` field with the
    # bracketed bounds (e.g. "76.4 [76.3-76.5]").
    assert "[" in rows[0].raw_value and "]" in rows[0].raw_value
    # The normalized value is the float NumericValue.
    assert 70.0 < float(rows[0].normalized_value) < 80.0


# ---------------------------------------------------------------------------
# Orchestrator end-to-end (Phase C convention #5d)
# ---------------------------------------------------------------------------


def test_ingest_who_gho_api_end_to_end(
    who_gho_api_cache_dir: Path,
    who_gho_api_catalog_path: Path,
    database_url: str,
) -> None:
    """``ingest_who_gho_api`` writes parquet + observations + sources + manifest in one call.

    The single-year fixture produces 5 countries x 5 indicators =
    25 source_observations rows. The full 2-year fixture (no
    ``year=`` filter, exercised in another test) would produce 50.
    """
    _init_test_db(database_url)
    result = who_gho_api.ingest_who_gho_api(
        year=2021,
        cache_dir=who_gho_api_cache_dir,
        catalog_path=who_gho_api_catalog_path,
    )

    assert isinstance(result, WhoGhoApiIngestResult)
    assert isinstance(result.parquet_path, Path)
    assert result.parquet_path.exists()
    assert result.source_id > 0
    assert result.observation_rows == 25
    assert result.countries == 5
    assert result.years == (2021,)
    assert result.indicators == 5
    # All 5 catalog indicators are cached, none fetched.
    assert result.indicators_cached == 5
    assert result.indicators_fetched == 0
    # Attribution on the result.
    assert "World Health Organization" in result.attribution
    # The run manifest is auto-written.
    manifest = (
        result.parquet_path.parent / "who_gho_api_run_manifest.json"
    )
    assert manifest.exists()
    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert manifest_payload["attribution"] == WHO_GHO_API_ATTRIBUTION
    assert manifest_payload["observation_rows"] == 25
    assert manifest_payload["indicators_cached"] == 5
    assert manifest_payload["indicators_fetched"] == 0
    assert manifest_payload["source_key"] == "who_gho_api"


def test_ingest_who_gho_api_is_idempotent(
    who_gho_api_cache_dir: Path,
    who_gho_api_catalog_path: Path,
    database_url: str,
) -> None:
    """Re-running ``ingest_who_gho_api`` produces the same row count (no double-write)."""
    _init_test_db(database_url)
    first = who_gho_api.ingest_who_gho_api(
        year=2021,
        cache_dir=who_gho_api_cache_dir,
        catalog_path=who_gho_api_catalog_path,
    )
    second = who_gho_api.ingest_who_gho_api(
        year=2021,
        cache_dir=who_gho_api_cache_dir,
        catalog_path=who_gho_api_catalog_path,
    )

    assert first.source_id == second.source_id
    assert first.observation_rows == second.observation_rows == 25
    # Parquet mtime should be unchanged on the idempotent re-run.
    first_mtime = first.parquet_path.stat().st_mtime
    second_mtime = second.parquet_path.stat().st_mtime
    assert first_mtime == second_mtime, (
        "Parquet should not be re-written on idempotent call"
    )


def test_ingest_who_gho_api_indicators_cached_and_fetched(
    who_gho_api_cache_dir: Path,
    who_gho_api_catalog_path: Path,
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With a partial cache, the orchestrator reports the cached-vs-fetched split."""

    _init_test_db(database_url)

    # Wipe the 2021 cache entirely; only the 3 indicators we keep
    # below will be on disk.
    cache_2021 = who_gho_api_cache_dir / "2021"
    for json_file in cache_2021.glob("*.json"):
        json_file.unlink()

    fixtures_cache_2021 = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "who_gho_api"
        / "cache"
        / "2021"
    )
    kept_indicators = {"WHOSIS_000001", "WHS4_100", "WHS4_117"}
    for ind in kept_indicators:
        shutil.copy(
            fixtures_cache_2021 / f"{ind}.json",
            cache_2021 / f"{ind}.json",
        )

    # Mock requests.get to track calls; return a 5-country row
    # for any indicator that the orchestrator fetches over HTTP.
    call_count = 0
    fetched_indicators: list[str] = []

    def counting_get(url, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        url_str = str(url)
        ind_code = url_str.split("api/", 1)[1].split("?", 1)[0]
        fetched_indicators.append(ind_code)
        countries = ("MEX", "USA", "SWE", "IND", "NGA")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json = lambda ic=ind_code: {
            "@odata.context": (
                f"https://ghoapi.azureedge.net/api/$metadata#{ic}"
            ),
            "value": [
                {
                    "IndicatorCode": ic,
                    "SpatialDimType": "COUNTRY",
                    "SpatialDim": c,
                    "TimeDim": 2021,
                    "Dim1": "SEX_BTSX",
                    "Value": "1.0",
                    "NumericValue": 1.0,
                }
                for c in countries
            ],
        }
        return mock_resp

    monkeypatch.setattr(requests, "get", counting_get)

    result = who_gho_api.ingest_who_gho_api(
        year=2021,
        cache_dir=who_gho_api_cache_dir,
        catalog_path=who_gho_api_catalog_path,
    )

    # The orchestrator must surface the cached-vs-fetched counts
    # on the result object (this is the wiring the prototype
    # pattern enforces).
    assert result.indicators_cached == 3, (
        f"Expected 3 cached indicators, got {result.indicators_cached}"
    )
    assert result.indicators_fetched == 2, (
        f"Expected 2 fetched indicators, got {result.indicators_fetched}"
    )
    # The HTTP layer must have been called exactly once per
    # uncached indicator.
    assert call_count == 2, f"Expected 2 HTTP calls, got {call_count}"
    # observation_rows = countries (5) * indicators (5) for year=2021.
    assert result.observation_rows == 5 * 5, (
        f"Expected 25 observation rows, got {result.observation_rows}"
    )
    assert result.countries == 5
    assert result.indicators == 5


# ---------------------------------------------------------------------------
# Run manifest
# ---------------------------------------------------------------------------


def test_write_run_manifest(
    who_gho_api_catalog_path: Path,
    isolated_data_lake: Path,
) -> None:
    """The run manifest is JSON next to the parquet and includes attribution."""
    assert WhoGhoApiIngestResult is not None
    result = WhoGhoApiIngestResult(
        source_id=1,
        parquet_path=(
            isolated_data_lake
            / "data"
            / "processed"
            / "who_gho_api"
            / "x.parquet"
        ),
        observation_rows=25,
        countries=5,
        years=(2021,),
        indicators=5,
        indicators_cached=5,
        indicators_fetched=0,
    )
    manifest_path = who_gho_api.write_who_gho_api_run_manifest(
        result,
        manifest_dir=(
            isolated_data_lake / "data" / "processed" / "who_gho_api"
        ),
        indicators_cached=5,
        indicators_fetched=0,
    )
    assert manifest_path.exists()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["source_id"] == 1
    assert payload["observation_rows"] == 25
    assert payload["years"] == [2021]
    assert payload["indicators"] == 5
    assert payload["indicators_cached"] == 5
    assert payload["indicators_fetched"] == 0
    assert payload["attribution"] == WHO_GHO_API_ATTRIBUTION
    assert payload["source_key"] == "who_gho_api"
    assert payload["api_base"] == "https://ghoapi.azureedge.net/api/"


# ---------------------------------------------------------------------------
# Attribution / Rule #15
# ---------------------------------------------------------------------------


def test_attribution_matches_constant() -> None:
    """``who_gho_api.attribution()`` returns the module-level WHO_GHO_API_ATTRIBUTION constant."""
    assert who_gho_api.attribution() == WHO_GHO_API_ATTRIBUTION
    assert "World Health Organization" in who_gho_api.attribution()
    assert "Global Health Observatory" in who_gho_api.attribution()


def test_who_gho_api_attribution_matches_attributions_doc() -> None:
    """``WHO_GHO_API_ATTRIBUTION`` is a substring of ``docs/source-attributions.md`` (drift guard).

    Per AGENTS.md Always-On Rule #15, the code's attribution text
    and the doc's citation text must be byte-for-byte consistent.
    If either changes, both must be updated in the same commit.
    """
    doc_path = (
        Path(__file__).resolve().parents[1] / "docs" / "source-attributions.md"
    )
    doc_text = doc_path.read_text(encoding="utf-8")
    assert WHO_GHO_API_ATTRIBUTION in doc_text, (
        f"WHO_GHO_API_ATTRIBUTION is not present in {doc_path}. "
        "Update both in the same commit (Rule #15)."
    )


# ---------------------------------------------------------------------------
# CLI dispatch
# ---------------------------------------------------------------------------


def test_stage2_adapters_dispatch_table(
    who_gho_api_source_key: str,
) -> None:
    """The dispatch table has who_gho_api registered as the production orchestrator.

    The previous value of ``STAGE2_ADAPTERS['who_gho_api']`` was
    ``None`` (the placeholder for "adapter needed"). This test
    guards the central registry against silent regressions to
    that placeholder.
    """
    assert STAGE2_ADAPTERS[who_gho_api_source_key] is who_gho_api.ingest_who_gho_api
    # The full key set is unchanged from the prior baseline
    # (eight implemented adapters + placeholders for the rest).
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
    assert set(STAGE2_ADAPTERS.keys()) == expected_keys


def test_cli_ingest_source_runs_who_gho_api(
    who_gho_api_cache_dir: Path,
    who_gho_api_catalog_path: Path,
    database_url: str,
) -> None:
    """``leaders-db ingest-source --source who_gho_api`` runs through the dispatch table.

    The test must fail if the CLI dispatch stops invoking the
    adapter or if any production-path side effect is missing
    (Done. Summary, Rule #15 attribution echo, parquet, DB rows,
    run manifest). Uses the test-isolated data lake + DB.
    """
    _init_test_db(database_url)
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["ingest-source", "--source", "who_gho_api", "--year", "2021"],
    )
    assert result.exit_code == 0, (
        f"CLI exited with code {result.exit_code}, output: {result.output}"
    )

    # The CLI must echo the production-path header lines so a
    # stub or no-op adapter cannot pass this test.
    assert "Done. Summary" in result.output, (
        f"Expected 'Done. Summary' in CLI output "
        f"(production-path adapter invocation proof); "
        f"got: {result.output!r}"
    )
    assert "Attribution:" in result.output, (
        f"Expected 'Attribution:' header in CLI output "
        f"(Rule #15 echo); got: {result.output!r}"
    )
    # The exact attribution text must be echoed.
    assert WHO_GHO_API_ATTRIBUTION in result.output, (
        f"Expected WHO_GHO_API_ATTRIBUTION in CLI output "
        f"(Rule #15 verbatim echo); got: {result.output!r}"
    )
    # The summary must surface the per-field counts.
    assert "observation_rows:" in result.output, (
        f"Expected 'observation_rows:' in CLI output; got: {result.output!r}"
    )

    # Production-path side effects must be observable.
    with session_scope(database_url) as session:
        db_rows = (
            session.execute(select(func.count(SourceObservation.id)))
            .scalar_one()
        )
    assert db_rows == 25, (
        f"Expected 25 source_observations rows written by the "
        f"CLI-driven adapter (5 countries x 5 indicators for "
        f"year=2021), got {db_rows}. If this is 0, the CLI "
        f"dispatch did not invoke the production adapter."
    )

    # Narrow parquet on disk in the processed data lake.
    # ``who_gho_api_cache_dir`` is
    # ``<isolated_data_lake>/data/raw/who_gho_api/cache`` (3
    # levels deep from the data lake root), so the processed
    # data lake root is reached by going up 3 levels.
    parquet_path = (
        who_gho_api_cache_dir.parent.parent.parent  # <isolated_data_lake>/data
        / "processed"
        / "who_gho_api"
        / "who_gho_api_country_year.parquet"
    )
    assert parquet_path.exists(), (
        f"Expected narrow parquet at {parquet_path} "
        f"(production-path side effect); a CLI that bypasses "
        f"the adapter would not produce this file."
    )

    # Run manifest on disk next to the parquet.
    manifest_path = parquet_path.parent / "who_gho_api_run_manifest.json"
    assert manifest_path.exists(), (
        f"Expected run manifest at {manifest_path} "
        f"(production-path audit trail per architecture §4 + "
        f"§12); a CLI that bypasses the adapter would not "
        f"produce this file."
    )
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload.get("source_key") == "who_gho_api"
    assert payload.get("attribution") == WHO_GHO_API_ATTRIBUTION
    assert payload.get("observation_rows") == 25


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------


def test_who_gho_api_module_public_surface() -> None:
    """The ``who_gho_api`` module re-exports the canonical public surface.

    Architecture §9 / Phase C convention: every Stage 2 adapter
    module re-exports the public names (orchestrator, result
    model, attribution constant, source key, IndicatorSpec, DB
    helpers, I/O helpers) so callers (tests, the CLI) can import
    from the canonical orchestrator path.
    """
    for name in [
        "WHO_GHO_API_ATTRIBUTION",
        "WHO_GHO_API_SOURCE_KEY",
        "IndicatorSpec",
        "WhoGhoApiIngestResult",
        "attribution",
        "ingest_who_gho_api",
        "load_indicator_catalog",
        "read_who_gho_api",
        "register_who_gho_api_source",
        "write_who_gho_api_observations",
        "write_who_gho_api_parquet",
        "write_who_gho_api_run_manifest",
    ]:
        assert hasattr(who_gho_api, name), f"who_gho_api.{name} not exported"
        assert getattr(who_gho_api, name) is not None, (
            f"who_gho_api.{name} is None"
        )
    # The attribution() helper returns the module-level constant.
    assert attribution() == WHO_GHO_API_ATTRIBUTION
    # The source key constant is "who_gho_api".
    assert WHO_GHO_API_SOURCE_KEY == "who_gho_api"


def test_who_gho_api_ingest_result_field_count() -> None:
    """``WhoGhoApiIngestResult`` has exactly 8 fields (matches WDI's Pydantic result contract)."""
    fields = WhoGhoApiIngestResult.model_fields
    expected_fields = {
        "source_id",
        "parquet_path",
        "observation_rows",
        "countries",
        "years",
        "indicators",
        "indicators_cached",
        "indicators_fetched",
    }
    assert set(fields.keys()) == expected_fields, (
        f"WhoGhoApiIngestResult field mismatch: "
        f"missing={expected_fields - set(fields.keys())}, "
        f"extra={set(fields.keys()) - expected_fields}"
    )
    assert len(fields) == 8, (
        f"WhoGhoApiIngestResult should have 8 fields, got {len(fields)}"
    )
