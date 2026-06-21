"""Tests for the Maddison-backed Chronicle economy fields.

These tests verify the Increment 2 source-precedence contract:

- Maddison Project is the canonical historical real-economy source
  (1-2022 direct; 2023 proxied to 2022 per the 1-year-gap
  pattern) and is preferred for years 1900-2022 when its data is
  present.
- WDI is the fallback for all years, and the preferred source for
  years beyond Maddison coverage (2023+ today). Maddison 2022 is
  used only as a final proxy when WDI is missing for 2023+.
- The row builder must preserve source/year/unit/method columns
  and emit ``proxy_year_used`` when the Maddison 2022 proxy
  fires.
"""

from __future__ import annotations

import pandas as pd

from leaders_db.chronicle.constants import (
    FLAG_MISSING_GDP,
    FLAG_MISSING_POPULATION,
    FLAG_PROXY_YEAR_USED,
    MADDISON_PROXY_REQUESTED_YEAR,
    MADDISON_PROXY_YEAR,
    SOURCE_TAG_MADDISON,
    SOURCE_TAG_WDI,
)
from leaders_db.chronicle.row_builder import build_chronicle_rows
from leaders_db.chronicle.ruler_resolver import RulerResolver
from leaders_db.chronicle.sources import MaddisonSource, WdiSource

# ---------------------------------------------------------------------------
# Stub source factories
# ---------------------------------------------------------------------------


def _stub_vdem(year_to_regime: dict[tuple[str, int], float]):
    """Build a :class:`VDemSource` whose ``lookup`` returns the given
    regime per ``(iso3, year)`` pair.

    Reused from the row_builder tests' helper for self-containment.
    """
    from leaders_db.chronicle.sources import VDemSource

    class _Stub:
        pass

    rows = []
    for (iso3, year), regime in year_to_regime.items():
        rows.append(
            {
                "country_text_id": iso3,
                "year": year,
                "v2x_regime": regime,
                "v2x_polyarchy": 0.5,
                "v2x_libdem": 0.5,
            }
        )
    frame = pd.DataFrame(
        rows,
        columns=[
            "country_text_id", "year", "v2x_regime",
            "v2x_polyarchy", "v2x_libdem",
        ],
    )
    return VDemSource(raw_csv_path=_Stub(), frame=frame)  # type: ignore[arg-type]


def _stub_wdi(rows: list[tuple[str, int, dict[str, float | None]]]) -> WdiSource:
    """Build a :class:`WdiSource` from a list of ``(iso3, year, payload)``."""
    class _Stub:
        pass

    data: list[dict[str, object]] = []
    for iso3, year, payload in rows:
        record: dict[str, object] = {"iso3": iso3, "year": year}
        record.update(payload)
        data.append(record)
    columns = [
        "iso3", "year", "wdi_population", "wdi_gdp_current_usd",
        "wdi_gdp_constant_2015_usd", "wdi_gdp_per_capita",
        "wdi_gdp_per_capita_ppp_constant_2017",
    ]
    frame = pd.DataFrame(data, columns=columns)
    return WdiSource(parquet_path=_Stub(), frame=frame)  # type: ignore[arg-type]


def _stub_sipri(rows: list[tuple[str, int, float]]):
    """Build a :class:`SipriSource` with one row per ``(country_name, year, milex)``."""
    from leaders_db.chronicle.sources import SipriSource

    class _Stub:
        pass

    data = []
    for name, year, milex in rows:
        data.append(
            {
                "country": name,
                "year": year,
                "sipri_milex_constant_usd": milex,
            }
        )
    columns = ["country", "year", "sipri_milex_constant_usd"]
    frame = pd.DataFrame(data, columns=columns)
    return SipriSource(parquet_path=_Stub(), frame=frame)  # type: ignore[arg-type]


def _stub_maddison(
    iso3: str, year: int,
    *, gdppc: float | None = None, pop_thousands: float | None = None,
) -> MaddisonSource:
    """Build a :class:`MaddisonSource` with one ``(iso3, year)`` row.

    The frame shape matches the Stage 2 narrow parquet schema so
    the resolver code path is identical.
    """
    class _Stub:
        pass

    records: list[dict[str, object]] = []
    if gdppc is not None:
        records.append(
            {
                "countrycode": iso3,
                "year": year,
                "country": iso3,
                "region": "",
                "variable_name": "maddison_project_gdp_per_capita_2011_intl",
                "raw_column": "gdppc",
                "raw_value": str(gdppc),
                "normalized_value": float(gdppc),
            }
        )
    if pop_thousands is not None:
        records.append(
            {
                "countrycode": iso3,
                "year": year,
                "country": iso3,
                "region": "",
                "variable_name": "maddison_project_population_thousands",
                "raw_column": "pop",
                "raw_value": str(pop_thousands),
                "normalized_value": float(pop_thousands),
            }
        )
    if gdppc is not None and pop_thousands is not None:
        derived = float(gdppc) * float(pop_thousands) * 1000.0
        records.append(
            {
                "countrycode": iso3,
                "year": year,
                "country": iso3,
                "region": "",
                "variable_name": "maddison_project_gdp_total_2011_intl_derived",
                "raw_column": "__derived_gdp_total__",
                "raw_value": f"{derived:.6f}",
                "normalized_value": derived,
            }
        )
    frame = pd.DataFrame(
        records,
        columns=[
            "countrycode", "year", "country", "region",
            "variable_name", "raw_column", "raw_value", "normalized_value",
        ],
    )
    return MaddisonSource(parquet_path=_Stub(), xlsx_path=_Stub(), frame=frame)


def _empty_ruler_resolver() -> RulerResolver:
    return RulerResolver()


# ---------------------------------------------------------------------------
# Maddison source precedence
# ---------------------------------------------------------------------------


def test_maddison_preferred_over_wdi_for_pre_2023_year() -> None:
    """When both Maddison and WDI have data for a pre-2023 year,
    Maddison wins (per Increment 2 contract). The ``gdp_unit``
    column carries the Maddison unit (``2011_intl_dollars``).
    """
    rows = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=2020,
        end_year=2020,
        vdem=_stub_vdem({}),
        wdi=_stub_wdi(
            [(
                "USA", 2020,
                {
                    "wdi_population": 330_000_000.0,
                    "wdi_gdp_constant_2015_usd": 21_000_000_000_000.0,
                },
            )]
        ),
        sipri=_stub_sipri([]),
        maddison=_stub_maddison(
            "USA", 2020,
            gdppc=58000.0, pop_thousands=330000.0,
        ),
        ruler_resolver=_empty_ruler_resolver(),
    )
    row = rows[0]
    assert row["population_source"] == SOURCE_TAG_MADDISON
    assert row["population_source_year_used"] == "2020"
    # Maddison pop is in thousands; we multiply by 1000 to lift to
    # absolute persons.
    assert row["population"] == "330000000"
    assert row["gdp_source"] == SOURCE_TAG_MADDISON
    assert row["gdp_unit"] == "2011_intl_dollars"
    assert row["gdp_per_capita_method"] == "maddison_direct"


def test_wdi_used_when_maddison_absent_for_pre_2023_year() -> None:
    """When Maddison has no data for a pre-2023 year, the row falls
    back to WDI. ``missing_population`` / ``missing_gdp`` are not
    emitted because the WDI source supplied the values.
    """
    rows = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=2020,
        end_year=2020,
        vdem=_stub_vdem({}),
        wdi=_stub_wdi(
            [(
                "USA", 2020,
                {
                    "wdi_population": 330_000_000.0,
                    "wdi_gdp_constant_2015_usd": 21_000_000_000_000.0,
                    "wdi_gdp_per_capita": 65000.0,
                },
            )]
        ),
        sipri=_stub_sipri([]),
        maddison=MaddisonSource(
            parquet_path=None,
            xlsx_path=None,
            frame=pd.DataFrame(
                columns=[
                    "countrycode", "year", "country", "region",
                    "variable_name", "raw_column",
                    "raw_value", "normalized_value",
                ]
            ),
        ),
        ruler_resolver=_empty_ruler_resolver(),
    )
    row = rows[0]
    assert row["population_source"] == SOURCE_TAG_WDI
    assert row["gdp_source"] == SOURCE_TAG_WDI
    assert row["gdp_unit"] == "constant_2015_usd"
    assert row["gdp_per_capita_method"] == "wdi_direct"
    assert FLAG_MISSING_POPULATION not in row["data_quality_flags"].split("|")
    assert FLAG_MISSING_GDP not in row["data_quality_flags"].split("|")


def test_wdi_preferred_for_2023_when_present() -> None:
    """For 2023+ years the row builder prefers WDI (the canonical
    recent source) and does NOT use the Maddison 2022 proxy."""
    rows = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=2023,
        end_year=2023,
        vdem=_stub_vdem({}),
        wdi=_stub_wdi(
            [(
                "USA", 2023,
                {
                    "wdi_population": 334_000_000.0,
                    "wdi_gdp_constant_2015_usd": 27_000_000_000_000.0,
                },
            )]
        ),
        sipri=_stub_sipri([]),
        maddison=_stub_maddison(
            "USA", 2022,
            gdppc=58487.46, pop_thousands=333288.0,
        ),
        ruler_resolver=_empty_ruler_resolver(),
    )
    row = rows[0]
    assert row["population_source"] == SOURCE_TAG_WDI
    assert row["population_source_year_used"] == "2023"
    assert row["gdp_source"] == SOURCE_TAG_WDI
    # Maddison is not used, so no proxy_year_used flag.
    assert FLAG_PROXY_YEAR_USED not in row["data_quality_flags"].split("|")


def test_maddison_proxy_used_for_2023_when_wdi_missing() -> None:
    """When 2023 is requested and WDI has no row but Maddison has
    2022 data, the row builder uses the Maddison 2022 proxy and
    adds the ``proxy_year_used`` flag."""
    rows = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=2023,
        end_year=2023,
        vdem=_stub_vdem({}),
        wdi=_stub_wdi([]),
        sipri=_stub_sipri([]),
        maddison=_stub_maddison(
            "USA", 2022,
            gdppc=58487.46, pop_thousands=333288.0,
        ),
        ruler_resolver=_empty_ruler_resolver(),
    )
    row = rows[0]
    assert row["population_source"] == SOURCE_TAG_MADDISON
    assert row["population_source_year_used"] == str(MADDISON_PROXY_YEAR)
    assert row["gdp_source"] == SOURCE_TAG_MADDISON
    assert FLAG_PROXY_YEAR_USED in row["data_quality_flags"].split("|")


def test_missing_population_and_gdp_when_no_sources_have_data() -> None:
    """A year where neither Maddison nor WDI has data carries both
    ``missing_population`` and ``missing_gdp``."""
    rows = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=2024,
        end_year=2024,
        vdem=_stub_vdem({}),
        wdi=_stub_wdi([]),
        sipri=_stub_sipri([]),
        maddison=MaddisonSource(
            parquet_path=None,
            xlsx_path=None,
            frame=pd.DataFrame(),
        ),
        ruler_resolver=_empty_ruler_resolver(),
    )
    row = rows[0]
    flags = row["data_quality_flags"].split("|")
    assert FLAG_MISSING_POPULATION in flags
    assert FLAG_MISSING_GDP in flags
    assert row["population"] == ""
    assert row["gdp"] == ""
    assert row["population_source"] == ""
    assert row["gdp_source"] == ""


def test_maddison_preferred_for_early_historical_year() -> None:
    """Pre-1960 Maddison data is the only source (WDI starts at
    1960). The row populates the Maddison-backed fields and
    carries the canonical 2011-intl-dollar unit."""
    rows = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=1900,
        end_year=1900,
        vdem=_stub_vdem({}),
        wdi=_stub_wdi([]),
        sipri=_stub_sipri([]),
        maddison=_stub_maddison(
            "USA", 1900,
            gdppc=4090.0, pop_thousands=76221.0,
        ),
        ruler_resolver=_empty_ruler_resolver(),
    )
    row = rows[0]
    assert row["population_source"] == SOURCE_TAG_MADDISON
    assert row["population"] == "76221000"
    assert row["gdp_source"] == SOURCE_TAG_MADDISON
    assert row["gdp_unit"] == "2011_intl_dollars"
    assert row["gdp_per_capita_method"] == "maddison_direct"


def test_no_maddison_source_means_only_wdi_economy_path() -> None:
    """When ``maddison=None`` is passed to the row builder (older
    test fixtures) the economy path falls back to WDI-only. No
    Maddison flags are added.
    """
    rows = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=2022,
        end_year=2022,
        vdem=_stub_vdem({}),
        wdi=_stub_wdi(
            [(
                "USA", 2022,
                {
                    "wdi_population": 334_000_000.0,
                    "wdi_gdp_constant_2015_usd": 25_000_000_000_000.0,
                },
            )]
        ),
        sipri=_stub_sipri([]),
        maddison=None,
        ruler_resolver=_empty_ruler_resolver(),
    )
    row = rows[0]
    assert row["population_source"] == SOURCE_TAG_WDI
    assert row["gdp_source"] == SOURCE_TAG_WDI
    # The provenance summary should not claim Maddison hit.
    assert "maddison=no" in row["provenance_summary"]


def test_maddison_proxy_constant_year_is_documented_in_row() -> None:
    """The Maddison proxy constants are the documented
    ``MADDISON_PROXY_YEAR=2022`` /
    ``MADDISON_PROXY_REQUESTED_YEAR=2023`` values. This guards
    against accidental drift in the constant."""
    assert MADDISON_PROXY_YEAR == 2022
    assert MADDISON_PROXY_REQUESTED_YEAR == 2023


def test_provenance_summary_records_maddison_hit() -> None:
    """The provenance_summary string includes a ``maddison=yes``
    marker when Maddison supplied at least one economy field."""
    rows = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=1920,
        end_year=1920,
        vdem=_stub_vdem({}),
        wdi=_stub_wdi([]),
        sipri=_stub_sipri([]),
        maddison=_stub_maddison(
            "USA", 1920,
            gdppc=5500.0, pop_thousands=106500.0,
        ),
        ruler_resolver=_empty_ruler_resolver(),
    )
    row = rows[0]
    assert "maddison=yes" in row["provenance_summary"]


# ---------------------------------------------------------------------------
# Reviewer-blocker regression tests (Increment 2 sign-off)
#
# These tests pin the audit-trail invariants the reviewer called
# out as blockers. Each one is named for the bug it guards:
#
# 1. Maddison-only rows must NOT report WDI as a hit.
# 2. The Maddison 2022 proxy is restricted to year == 2023 only;
#    2024/2025/2026 with no WDI must show blank GDP/population
#    (and no Maddison proxy flag) -- not silently reuse Maddison
#    2022 as a multi-year stale proxy.
# 3. The Maddison direct-proxy per-capita branch must agree with
#    the GDP/population branch (no orphaned per_capita value with
#    an empty GDP).
# ---------------------------------------------------------------------------


def test_maddison_only_row_reports_wdi_no_and_maddison_yes() -> None:
    """Reviewer blocker: Maddison-only rows must report ``wdi=no``.

    Maddison alone populating a row (e.g. a 1920 Maddison hit with
    no WDI row in the local parquet) used to compute ``wdi_hit``
    from ``has_population or has_gdp``, which set ``wdi=yes`` even
    though no WDI cell was actually used. The fix computes
    ``wdi_hit`` from the row's per-field source tags, so a row
    whose ``population_source == "maddison_project"`` reports
    ``wdi=no``.
    """
    rows = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=1920,
        end_year=1920,
        vdem=_stub_vdem({}),
        wdi=_stub_wdi([]),  # WDI has nothing for 1920
        sipri=_stub_sipri([]),
        maddison=_stub_maddison(
            "USA", 1920,
            gdppc=5500.0, pop_thousands=106500.0,
        ),
        ruler_resolver=_empty_ruler_resolver(),
    )
    row = rows[0]
    assert row["population_source"] == SOURCE_TAG_MADDISON
    assert row["gdp_source"] == SOURCE_TAG_MADDISON
    assert row["population"] == "106500000"
    assert row["gdp"] != ""
    # The audit-trail invariant: Maddison populated the row, WDI
    # did NOT. The provenance_summary must reflect that.
    assert "wdi=no" in row["provenance_summary"]
    assert "maddison=yes" in row["provenance_summary"]


def test_wdi_only_row_reports_wdi_yes_and_maddison_no() -> None:
    """WDI-only rows report ``wdi=yes`` and ``maddison=no``."""
    rows = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=2020,
        end_year=2020,
        vdem=_stub_vdem({}),
        wdi=_stub_wdi(
            [(
                "USA", 2020,
                {
                    "wdi_population": 330_000_000.0,
                    "wdi_gdp_constant_2015_usd": 21_000_000_000_000.0,
                    "wdi_gdp_per_capita": 65000.0,
                },
            )]
        ),
        sipri=_stub_sipri([]),
        maddison=None,
        ruler_resolver=_empty_ruler_resolver(),
    )
    row = rows[0]
    assert row["population_source"] == SOURCE_TAG_WDI
    assert row["gdp_source"] == SOURCE_TAG_WDI
    assert "wdi=yes" in row["provenance_summary"]
    assert "maddison=no" in row["provenance_summary"]


def test_maddison_proxy_fires_for_2023_only() -> None:
    """Reviewer blocker: Maddison 2022 proxy fires for year == 2023
    (when WDI is missing). For year > 2023 (2024, 2025, 2026) with
    no WDI the proxy MUST NOT fire -- the row is left blank with
    ``missing_population`` / ``missing_gdp`` flags.
    """
    maddison = _stub_maddison(
        "USA", 2022,
        gdppc=58487.46, pop_thousands=333288.0,
    )
    # 2023 -> proxy fires (Maddison 2022 fills GDP + population)
    rows_2023 = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=2023,
        end_year=2023,
        vdem=_stub_vdem({}),
        wdi=_stub_wdi([]),
        sipri=_stub_sipri([]),
        maddison=maddison,
        ruler_resolver=_empty_ruler_resolver(),
    )
    row_2023 = rows_2023[0]
    assert row_2023["population_source"] == SOURCE_TAG_MADDISON
    assert row_2023["population_source_year_used"] == str(MADDISON_PROXY_YEAR)
    assert row_2023["gdp_source"] == SOURCE_TAG_MADDISON
    assert row_2023["gdp_source_year_used"] == str(MADDISON_PROXY_YEAR)
    assert FLAG_PROXY_YEAR_USED in row_2023["data_quality_flags"].split("|")

    # 2024 -> proxy MUST NOT fire (no WDI, so the row is blank)
    rows_2024 = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=2024,
        end_year=2024,
        vdem=_stub_vdem({}),
        wdi=_stub_wdi([]),
        sipri=_stub_sipri([]),
        maddison=maddison,
        ruler_resolver=_empty_ruler_resolver(),
    )
    row_2024 = rows_2024[0]
    assert row_2024["population"] == ""
    assert row_2024["gdp"] == ""
    assert row_2024["population_source"] == ""
    assert row_2024["gdp_source"] == ""
    assert row_2024["gdp_per_capita"] == ""
    assert row_2024["gdp_per_capita_method"] == ""
    flags_2024 = row_2024["data_quality_flags"].split("|")
    assert FLAG_MISSING_POPULATION in flags_2024
    assert FLAG_MISSING_GDP in flags_2024
    assert FLAG_PROXY_YEAR_USED not in flags_2024


def test_maddison_proxy_does_not_fire_for_2025_or_2026() -> None:
    """2025/2026 with no WDI MUST NOT reuse Maddison 2022 as a
    multi-year stale proxy (only year == 2023 is documented to
    use the 1-year-gap proxy). All values blank + missing flags.
    """
    maddison = _stub_maddison(
        "USA", 2022,
        gdppc=58487.46, pop_thousands=333288.0,
    )
    for year in (2025, 2026):
        rows = build_chronicle_rows(
            iso3_scope=("USA",),
            start_year=year,
            end_year=year,
            vdem=_stub_vdem({}),
            wdi=_stub_wdi([]),
            sipri=_stub_sipri([]),
            maddison=maddison,
            ruler_resolver=_empty_ruler_resolver(),
        )
        row = rows[0]
        assert row["population"] == "", (
            f"year {year}: expected blank population, "
            f"got {row['population']!r}"
        )
        assert row["gdp"] == "", (
            f"year {year}: expected blank gdp, got {row['gdp']!r}"
        )
        assert row["gdp_per_capita"] == "", (
            f"year {year}: expected blank gdp_per_capita, "
            f"got {row['gdp_per_capita']!r}"
        )
        flags = row["data_quality_flags"].split("|")
        assert FLAG_MISSING_POPULATION in flags
        assert FLAG_MISSING_GDP in flags
        assert FLAG_PROXY_YEAR_USED not in flags, (
            f"year {year}: proxy_year_used fired for year > 2023 "
            "with no WDI -- this is the reviewer blocker"
        )
        # Provenance must not claim Maddison hit either.
        assert "maddison=no" in row["provenance_summary"]


def test_maddison_proxy_wdi_present_takes_precedence_in_2023() -> None:
    """When WDI has 2023 data AND Maddison has 2022 data, WDI
    wins (WDI is the canonical recent source). The proxy is only
    a fallback for missing WDI; Maddison 2022 is not used.
    """
    rows = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=2023,
        end_year=2023,
        vdem=_stub_vdem({}),
        wdi=_stub_wdi(
            [(
                "USA", 2023,
                {
                    "wdi_population": 334_000_000.0,
                    "wdi_gdp_constant_2015_usd": 27_000_000_000_000.0,
                },
            )]
        ),
        sipri=_stub_sipri([]),
        maddison=_stub_maddison(
            "USA", 2022,
            gdppc=58487.46, pop_thousands=333288.0,
        ),
        ruler_resolver=_empty_ruler_resolver(),
    )
    row = rows[0]
    assert row["population_source"] == SOURCE_TAG_WDI
    assert row["population_source_year_used"] == "2023"
    assert row["gdp_source"] == SOURCE_TAG_WDI
    assert "wdi=yes" in row["provenance_summary"]
    flags = row["data_quality_flags"].split("|")
    assert FLAG_PROXY_YEAR_USED not in flags


def test_wdi_present_for_2024_preferred_over_maddison_2022() -> None:
    """When WDI has 2024 data, Maddison's 2022 row is not consulted.
    WDI wins regardless of Maddison having data for any year.
    """
    rows = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=2024,
        end_year=2024,
        vdem=_stub_vdem({}),
        wdi=_stub_wdi(
            [(
                "USA", 2024,
                {
                    "wdi_population": 335_000_000.0,
                    "wdi_gdp_constant_2015_usd": 28_000_000_000_000.0,
                    "wdi_gdp_per_capita": 80000.0,
                },
            )]
        ),
        sipri=_stub_sipri([]),
        maddison=_stub_maddison(
            "USA", 2022,
            gdppc=58487.46, pop_thousands=333288.0,
        ),
        ruler_resolver=_empty_ruler_resolver(),
    )
    row = rows[0]
    assert row["population_source"] == SOURCE_TAG_WDI
    assert row["gdp_source"] == SOURCE_TAG_WDI
    assert "wdi=yes" in row["provenance_summary"]
    assert "maddison=no" in row["provenance_summary"]


def test_maddison_proxy_2023_per_capita_uses_maddison_direct_proxy() -> None:
    """For year 2023 with WDI missing and Maddison 2022 proxy
    firing, the per-capita value carries the
    ``maddison_direct_proxy`` method (NOT ``derived`` -- the
    Maddison ``gdppc`` cell is the canonical 2011-intl-dollar
    value).
    """
    rows = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=2023,
        end_year=2023,
        vdem=_stub_vdem({}),
        wdi=_stub_wdi([]),
        sipri=_stub_sipri([]),
        maddison=_stub_maddison(
            "USA", 2022,
            gdppc=58487.46, pop_thousands=333288.0,
        ),
        ruler_resolver=_empty_ruler_resolver(),
    )
    row = rows[0]
    assert row["gdp_per_capita_method"] == "maddison_direct_proxy"
    assert row["gdp_per_capita_unit"] == "2011_intl_dollars"


# ---------------------------------------------------------------------------
# Direct ``_provenance`` helper tests (the row-level wdi/maddison
# hit computation is now source-tag-driven; these tests pin the
# helper behavior so a future refactor that switches the
# computation back to ``has_*`` booleans fails loud).
# ---------------------------------------------------------------------------


def test_wdi_hit_from_row_only_true_for_wdi_tag() -> None:
    """``wdi_hit_from_row`` returns True iff a per-field source tag
    equals ``wdi``. Maddison tags do NOT make wdi_hit True.
    """
    from leaders_db.chronicle._provenance import wdi_hit_from_row

    assert wdi_hit_from_row({"population_source": "wdi"}) is True
    assert wdi_hit_from_row({"gdp_source": "wdi"}) is True
    # Maddison tag does NOT imply a WDI hit.
    assert wdi_hit_from_row(
        {"population_source": "maddison_project"}
    ) is False
    assert wdi_hit_from_row({"gdp_source": "maddison_project"}) is False
    assert wdi_hit_from_row({}) is False
    assert wdi_hit_from_row({"population_source": ""}) is False


def test_maddison_hit_from_row_only_true_for_maddison_tag() -> None:
    """``maddison_hit_from_row`` returns True iff a per-field source
    tag equals ``maddison_project``. WDI tags do NOT make
    maddison_hit True.
    """
    from leaders_db.chronicle._provenance import maddison_hit_from_row

    assert maddison_hit_from_row(
        {"population_source": "maddison_project"}
    ) is True
    assert maddison_hit_from_row(
        {"gdp_source": "maddison_project"}
    ) is True
    # WDI tag does NOT imply a Maddison hit.
    assert maddison_hit_from_row({"population_source": "wdi"}) is False
    assert maddison_hit_from_row({"gdp_source": "wdi"}) is False
    assert maddison_hit_from_row({}) is False
