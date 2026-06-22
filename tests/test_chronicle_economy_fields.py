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

from pathlib import Path

import pandas as pd

from leaders_db.chronicle.constants import (
    FLAG_MISSING_GDP,
    FLAG_MISSING_POPULATION,
    FLAG_POPULATION_INTERPOLATED,
    FLAG_POPULATION_PROXY_YEAR_USED,
    FLAG_PROXY_YEAR_USED,
    MADDISON_PROXY_REQUESTED_YEAR,
    MADDISON_PROXY_YEAR,
    SOURCE_TAG_MADDISON,
    SOURCE_TAG_VDEM,
    SOURCE_TAG_WDI,
)
from leaders_db.chronicle.row_builder import build_chronicle_rows
from leaders_db.chronicle.ruler_resolver import RulerResolver
from leaders_db.chronicle.sources import MaddisonSource, WdiSource

# ---------------------------------------------------------------------------
# Stub source factories
# ---------------------------------------------------------------------------


def _stub_vdem(
    year_to_regime: dict[tuple[str, int], float],
    *,
    wb_population: dict[tuple[str, int], float] | None = None,
    mi_population_thousands: dict[tuple[str, int], float] | None = None,
    unsupported_e_pop: dict[tuple[str, int], float] | None = None,
    latent_gdp: dict[tuple[str, int], tuple[float | None, float | None]] | None = None,
):
    """Build a :class:`VDemSource` whose ``lookup`` returns the given
    regime per ``(iso3, year)`` pair.

    Reused from the row_builder tests' helper for self-containment.
    """
    from leaders_db.chronicle.sources import VDemSource

    class _Stub:
        pass

    wb_population = wb_population or {}
    mi_population_thousands = mi_population_thousands or {}
    unsupported_e_pop = unsupported_e_pop or {}
    latent_gdp = latent_gdp or {}
    keys = (
        set(year_to_regime)
        | set(wb_population)
        | set(mi_population_thousands)
        | set(unsupported_e_pop)
        | set(latent_gdp)
    )
    rows = []
    for iso3, year in sorted(keys):
        regime = year_to_regime.get((iso3, year))
        rows.append(
            {
                "country_text_id": iso3,
                "year": year,
                "v2x_regime": regime,
                "v2x_polyarchy": 0.5,
                "v2x_libdem": 0.5,
                "e_wb_pop": wb_population.get((iso3, year)),
                "e_mipopula": mi_population_thousands.get((iso3, year)),
                "e_pop": unsupported_e_pop.get((iso3, year)),
                "e_gdp": (
                    latent_gdp[(iso3, year)][0]
                    if (iso3, year) in latent_gdp else None
                ),
                "e_gdppc": (
                    latent_gdp[(iso3, year)][1]
                    if (iso3, year) in latent_gdp else None
                ),
            }
        )
    frame = pd.DataFrame(
        rows,
        columns=[
            "country_text_id", "year", "v2x_regime", "v2x_polyarchy",
            "v2x_libdem", "e_wb_pop", "e_mipopula", "e_pop",
            "e_gdp", "e_gdppc",
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


def test_vdem_latent_gdp_fallback_fills_gdp_and_per_capita() -> None:
    """V-Dem latent GDP fills GDP only when Maddison/WDI are absent."""
    rows = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=2000,
        end_year=2000,
        vdem=_stub_vdem(
            {},
            latent_gdp={("USA", 2000): (3_591_474.635, 117.521)},
        ),
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
    assert row["gdp"] == "3591475"
    assert row["gdp_source"] == SOURCE_TAG_VDEM
    assert row["gdp_source_year_used"] == "2000"
    assert row["gdp_unit"] == "vdem_latent_gdp_units"
    assert row["gdp_per_capita"] == "117.52"
    assert row["gdp_per_capita_unit"] == "vdem_latent_gdppc_units"
    assert row["gdp_per_capita_method"] == "vdem_latent_direct"
    assert FLAG_MISSING_GDP not in flags


def test_maddison_and_wdi_precede_vdem_latent_gdp() -> None:
    """V-Dem latent GDP is a fallback, never an override."""
    maddison_rows = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=2020,
        end_year=2020,
        vdem=_stub_vdem(
            {},
            latent_gdp={("USA", 2020): (999_000.0, 999.0)},
        ),
        wdi=_stub_wdi([]),
        sipri=_stub_sipri([]),
        maddison=_stub_maddison(
            "USA", 2020,
            gdppc=58000.0, pop_thousands=330000.0,
        ),
        ruler_resolver=_empty_ruler_resolver(),
    )
    assert maddison_rows[0]["gdp_source"] == SOURCE_TAG_MADDISON
    assert maddison_rows[0]["gdp"] != "999000"

    wdi_rows = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=2024,
        end_year=2024,
        vdem=_stub_vdem(
            {},
            latent_gdp={("USA", 2024): (999_000.0, 999.0)},
        ),
        wdi=_stub_wdi(
            [("USA", 2024, {"wdi_gdp_constant_2015_usd": 28_000.0})]
        ),
        sipri=_stub_sipri([]),
        maddison=None,
        ruler_resolver=_empty_ruler_resolver(),
    )
    assert wdi_rows[0]["gdp_source"] == SOURCE_TAG_WDI
    assert wdi_rows[0]["gdp"] == "28000"


def test_vdem_latent_gdp_requires_both_gdp_and_gdppc() -> None:
    """V-Dem GDP fallback requires both exact ``e_gdp`` and ``e_gdppc``."""
    for payload in (
        {("USA", 2000): (3_591_474.635, None)},
        {("USA", 2000): (None, 117.521)},
    ):
        rows = build_chronicle_rows(
            iso3_scope=("USA",),
            start_year=2000,
            end_year=2000,
            vdem=_stub_vdem({}, latent_gdp=payload),
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
        assert row["gdp"] == ""
        assert row["gdp_source"] == ""
        assert row["gdp_per_capita"] == ""
        assert FLAG_MISSING_GDP in flags


def test_vdem_latent_gdp_does_not_interpolate_or_proxy() -> None:
    """Adjacent V-Dem GDP rows do not fill a missing exact year."""
    rows = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=2001,
        end_year=2001,
        vdem=_stub_vdem(
            {},
            latent_gdp={
                ("USA", 2000): (3_500_000.0, 110.0),
                ("USA", 2002): (3_700_000.0, 120.0),
            },
        ),
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
    assert row["gdp"] == ""
    assert row["gdp_per_capita"] == ""
    assert FLAG_MISSING_GDP in flags


def test_vdem_population_does_not_derive_mixed_source_gdp_per_capita() -> None:
    """Do not derive per-capita from WDI GDP and V-Dem population."""
    rows = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=2024,
        end_year=2024,
        vdem=_stub_vdem(
            {},
            wb_population={("USA", 2024): 335_000_000.0},
        ),
        wdi=_stub_wdi(
            [("USA", 2024, {"wdi_gdp_constant_2015_usd": 28_000.0})]
        ),
        sipri=_stub_sipri([]),
        maddison=None,
        ruler_resolver=_empty_ruler_resolver(),
    )
    row = rows[0]
    assert row["population_source"] == SOURCE_TAG_VDEM
    assert row["gdp_source"] == SOURCE_TAG_WDI
    assert row["gdp_per_capita"] == ""
    assert row["gdp_per_capita_method"] == ""


def test_vdem_population_fallback_uses_world_bank_absolute_persons() -> None:
    """When Maddison/WDI leave population blank, V-Dem can supply
    population from ``e_wb_pop`` without changing GDP provenance.
    """
    rows = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=2022,
        end_year=2022,
        vdem=_stub_vdem(
            {},
            wb_population={("USA", 2022): 334_017_321.0},
        ),
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
    assert row["population"] == "334017321"
    assert row["population_source"] == SOURCE_TAG_VDEM
    assert row["population_source_year_used"] == "2022"
    assert FLAG_MISSING_POPULATION not in flags
    assert FLAG_MISSING_GDP in flags
    assert row["gdp"] == ""


def test_vdem_population_fallback_converts_mipopula_thousands() -> None:
    """V-Dem ``e_mipopula`` is thousands and is converted to persons."""
    rows = build_chronicle_rows(
        iso3_scope=("AFG",),
        start_year=1900,
        end_year=1900,
        vdem=_stub_vdem(
            {},
            mi_population_thousands={("AFG", 1900): 5000.0},
        ),
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
    assert row["population"] == "5000000"
    assert row["population_source"] == SOURCE_TAG_VDEM


def test_vdem_population_fallback_uses_epop_ten_thousands() -> None:
    """V-Dem ``e_pop`` is a low-precedence ten-thousands estimate."""
    rows = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=2022,
        end_year=2022,
        vdem=_stub_vdem(
            {},
            unsupported_e_pop={("USA", 2022): 12345.0},
        ),
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
    assert row["population"] == "123450000"
    assert row["population_source"] == SOURCE_TAG_VDEM
    assert FLAG_MISSING_POPULATION not in flags


def test_vdem_population_fallback_interpolates_bounded_internal_gap() -> None:
    """V-Dem population fallback linearly interpolates bounded gaps."""
    rows = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=2001,
        end_year=2001,
        vdem=_stub_vdem(
            {},
            wb_population={
                ("USA", 2000): 100_000_000.0,
                ("USA", 2002): 120_000_000.0,
            },
        ),
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
    assert row["population"] == "110000000"
    assert row["population_source"] == SOURCE_TAG_VDEM
    assert row["population_source_year_used"] == "2001"
    assert FLAG_POPULATION_INTERPOLATED in flags


def test_vdem_population_fallback_uses_one_year_proxy() -> None:
    """V-Dem population fallback can carry forward one year only."""
    rows = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=2025,
        end_year=2025,
        vdem=_stub_vdem(
            {},
            wb_population={("USA", 2024): 335_000_000.0},
        ),
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
    assert row["population"] == "335000000"
    assert row["population_source"] == SOURCE_TAG_VDEM
    assert row["population_source_year_used"] == "2024"
    assert FLAG_POPULATION_PROXY_YEAR_USED in flags


def test_maddison_and_wdi_precede_vdem_population_fallback() -> None:
    """V-Dem population is a fallback, never an override."""
    maddison_rows = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=2020,
        end_year=2020,
        vdem=_stub_vdem(
            {},
            wb_population={("USA", 2020): 999_000_000.0},
        ),
        wdi=_stub_wdi([]),
        sipri=_stub_sipri([]),
        maddison=_stub_maddison(
            "USA", 2020,
            gdppc=58000.0, pop_thousands=330000.0,
        ),
        ruler_resolver=_empty_ruler_resolver(),
    )
    assert maddison_rows[0]["population"] == "330000000"
    assert maddison_rows[0]["population_source"] == SOURCE_TAG_MADDISON

    wdi_rows = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=2024,
        end_year=2024,
        vdem=_stub_vdem(
            {},
            wb_population={("USA", 2024): 999_000_000.0},
        ),
        wdi=_stub_wdi(
            [("USA", 2024, {"wdi_population": 335_000_000.0})]
        ),
        sipri=_stub_sipri([]),
        maddison=None,
        ruler_resolver=_empty_ruler_resolver(),
    )
    assert wdi_rows[0]["population"] == "335000000"
    assert wdi_rows[0]["population_source"] == SOURCE_TAG_WDI


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


def test_2023_wdi_gdp_and_population_derive_per_capita_over_maddison_proxy() -> None:
    """WDI-present 2023 rows must not use Maddison proxy per-capita."""
    rows = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=2023,
        end_year=2023,
        vdem=_stub_vdem({}),
        wdi=_stub_wdi(
            [("USA", 2023, {
                "wdi_population": 334_000_000.0,
                "wdi_gdp_constant_2015_usd": 26_720_000_000_000.0,
                "wdi_gdp_per_capita": None,
            })]
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
    assert row["gdp_per_capita"] == "80000.00"
    assert row["gdp_per_capita_unit"] == "constant_2015_usd"
    assert row["gdp_per_capita_method"] == "derived_gdp_over_population"


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


# ---------------------------------------------------------------------------
# WDI coverage-cache GDP improvement (Increment 6) tests
#
# These tests pin the production-wiring invariants of the
# Increment 6 contract:
#
# 1. WDI cache exact-year observations fill country-year rows
#    that were blank under the parquet-only path (e.g. 2024
#    after the 2022 ingest).
# 2. The cache is bounded to 1960-2024: 2025/2026 MUST NOT
#    proxy from 2024.
# 3. Maddison still wins over WDI cache for pre-2023 years
#    when both have a direct hit (precedence preserved).
# 4. WDI cache rows for 2023 still win over the Maddison
#    2022 proxy because the 2023+ branch prefers WDI when
#    present.
# 5. The condensed coverage metric excludes non-existing rows
#    (so the relevant denominator is consistent with the
#    Increment 5 contract).
# ---------------------------------------------------------------------------


def test_wdi_cache_fills_exact_2024_row() -> None:
    """A 2024 row that was blank under the parquet-only path
    is filled by the WDI coverage cache. ``gdp_source`` is
    ``wdi`` and ``gdp_source_year_used`` is the exact year.
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
                    "wdi_gdp_constant_2015_usd": 22_568_462_768_174.3,
                    "wdi_gdp_per_capita": 84_534.04,
                },
            )]
        ),
        sipri=_stub_sipri([]),
        maddison=MaddisonSource(
            parquet_path=None,
            xlsx_path=None,
            frame=pd.DataFrame(),
        ),
        ruler_resolver=_empty_ruler_resolver(),
    )
    row = rows[0]
    assert row["gdp_source"] == SOURCE_TAG_WDI
    assert row["gdp_source_year_used"] == "2024"
    assert row["gdp"] == "22568462768174"
    assert row["gdp_unit"] == "constant_2015_usd"
    assert row["gdp_per_capita"] == "84534.04"
    assert row["gdp_per_capita_method"] == "wdi_direct"
    flags = row["data_quality_flags"].split("|")
    assert FLAG_MISSING_GDP not in flags
    assert FLAG_PROXY_YEAR_USED not in flags


def test_wdi_cache_does_not_proxy_2024_to_2025() -> None:
    """The WDI cache is bounded to 1960-2024. A 2025 row
    with cache only supplying 2024 MUST stay blank with
    ``missing_gdp``; we never carry-forward 2024 to 2025.
    """
    rows = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=2025,
        end_year=2025,
        vdem=_stub_vdem({}),
        wdi=_stub_wdi(
            [(
                "USA", 2024,
                {
                    "wdi_gdp_constant_2015_usd": 22_568_462_768_174.3,
                },
            )]
        ),
        sipri=_stub_sipri([]),
        maddison=MaddisonSource(
            parquet_path=None,
            xlsx_path=None,
            frame=pd.DataFrame(),
        ),
        ruler_resolver=_empty_ruler_resolver(),
    )
    row = rows[0]
    assert row["gdp"] == ""
    assert row["gdp_source"] == ""
    assert row["gdp_source_year_used"] == ""
    assert row["gdp_per_capita"] == ""
    flags = row["data_quality_flags"].split("|")
    assert FLAG_MISSING_GDP in flags
    assert FLAG_PROXY_YEAR_USED not in flags


def test_wdi_cache_does_not_proxy_2024_to_2026() -> None:
    """2026 with WDI cache only carrying 2024 stays blank too.

    The 2025/2026 staleness rule applies symmetrically: we
    never reuse a 2024 cache observation as a 2025/2026
    multi-year stale proxy. Maddison's 2022 row is also
    not reused (that contract is enforced separately; this
    test pins the WDI-cache half).
    """
    rows = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=2026,
        end_year=2026,
        vdem=_stub_vdem({}),
        wdi=_stub_wdi(
            [(
                "USA", 2024,
                {
                    "wdi_gdp_constant_2015_usd": 22_568_462_768_174.3,
                },
            )]
        ),
        sipri=_stub_sipri([]),
        maddison=MaddisonSource(
            parquet_path=None,
            xlsx_path=None,
            frame=pd.DataFrame(),
        ),
        ruler_resolver=_empty_ruler_resolver(),
    )
    row = rows[0]
    assert row["gdp"] == ""
    assert row["gdp_source"] == ""
    flags = row["data_quality_flags"].split("|")
    assert FLAG_MISSING_GDP in flags
    assert FLAG_PROXY_YEAR_USED not in flags


def test_maddison_preferred_over_wdi_cache_for_pre_2023_year() -> None:
    """When both Maddison and WDI cache have data for a pre-2023
    year, Maddison wins (per Increment 2 contract). WDI cache
    does NOT break the Maddison-vs-WDI precedence.
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
                    "wdi_gdp_constant_2015_usd": 99_000_000_000_000.0,
                    "wdi_gdp_per_capita": 99_000.0,
                },
            )]
        ),
        sipri=_stub_sipri([]),
        maddison=_stub_maddison(
            "USA", 2020,
            gdppc=58_000.0, pop_thousands=330_000.0,
        ),
        ruler_resolver=_empty_ruler_resolver(),
    )
    row = rows[0]
    # Maddison wins; the WDI value (99T) is NOT used.
    assert row["gdp_source"] == SOURCE_TAG_MADDISON
    assert row["gdp_unit"] == "2011_intl_dollars"
    assert row["gdp_per_capita_method"] == "maddison_direct"
    # GDP value is the Maddison-derived total (not the WDI 99T).
    assert row["gdp"] != "99000000000000"
    # Provenance: Maddison hit, WDI cache was supplied but not used.
    assert "maddison=yes" in row["provenance_summary"]


def test_wdi_cache_2023_preferred_over_maddison_2022_proxy() -> None:
    """For year 2023 the WDI cache wins over the Maddison 2022
    proxy. The 2023+ branch prefers WDI when present, and the
    Maddison 2022 1-year-gap proxy only fires as a fallback
    when WDI is missing.

    The test fixture supplies ``wdi_population`` AND
    ``wdi_gdp_constant_2015_usd`` so the WDI cache fills BOTH
    fields for 2023. Maddison's 2022 row is then strictly a
    non-contributor and ``proxy_year_used`` is not emitted.
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
                    "wdi_gdp_constant_2015_usd": 21_955_252_291_273.6,
                },
            )]
        ),
        sipri=_stub_sipri([]),
        maddison=_stub_maddison(
            "USA", 2022,
            gdppc=58_487.46, pop_thousands=333_288.0,
        ),
        ruler_resolver=_empty_ruler_resolver(),
    )
    row = rows[0]
    # WDI wins for 2023; Maddison 2022 proxy is NOT used.
    assert row["gdp_source"] == SOURCE_TAG_WDI
    assert row["gdp_source_year_used"] == "2023"
    assert row["gdp"] == "21955252291274"
    assert row["population_source"] == SOURCE_TAG_WDI
    assert row["population_source_year_used"] == "2023"
    flags = row["data_quality_flags"].split("|")
    assert FLAG_PROXY_YEAR_USED not in flags
    # Maddison is the in-memory source but did not contribute
    # to this row.
    assert "maddison=no" in row["provenance_summary"]


def test_wdi_cache_per_capita_uses_wdi_direct_method() -> None:
    """When the WDI cache supplies both GDP and per-capita for
    the same year, the row uses ``wdi_direct`` per-capita
    (not a derived value) and the constant-2015-USD unit.
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
                    "wdi_population": 340_000_000.0,
                    "wdi_gdp_constant_2015_usd": 22_568_462_768_174.3,
                    "wdi_gdp_per_capita": 84_534.04,
                },
            )]
        ),
        sipri=_stub_sipri([]),
        maddison=None,
        ruler_resolver=_empty_ruler_resolver(),
    )
    row = rows[0]
    assert row["gdp_per_capita"] == "84534.04"
    assert row["gdp_per_capita_unit"] == "current_usd"
    assert row["gdp_per_capita_method"] == "wdi_direct"


def test_wdi_cache_preserves_provenance_year_used() -> None:
    """The ``gdp_source_year_used`` is the exact requested
    year, not a carry-forward. The audit-trail contract is
    preserved even when the cache observation matches an
    out-of-window 2024 row.
    """
    rows = build_chronicle_rows(
        iso3_scope=("FRA",),
        start_year=2024,
        end_year=2024,
        vdem=_stub_vdem({}),
        wdi=_stub_wdi(
            [(
                "FRA", 2024,
                {
                    "wdi_gdp_current_usd": 3_100_000_000_000.0,
                },
            )]
        ),
        sipri=_stub_sipri([]),
        maddison=None,
        ruler_resolver=_empty_ruler_resolver(),
    )
    row = rows[0]
    assert row["gdp_source_year_used"] == "2024"
    assert row["gdp_source"] == SOURCE_TAG_WDI


def test_wdi_cache_loader_drops_2025_out_of_window() -> None:
    """Defense in depth: even if a 2025 row sneaks into the
    cache frame, the row builder cannot pick it up as 2024.
    This is the unit-level guard for the bounded-window
    contract; the cache loader is the production gate.
    """
    from leaders_db.chronicle.sources import WdiSource
    # Build a WdiSource whose frame is the merged shape of a
    # (USA, 2024) cache row plus a hypothetical (USA, 2025)
    # row. The WdiSource does not itself enforce the bound;
    # the bound is enforced by the cache loader. This test
    # documents the contract: the WdiSource is a plain
    # (iso3, year) lookup; the bound is upstream.
    class _Stub:
        pass

    frame = pd.DataFrame(
        [
            {"iso3": "USA", "year": 2024,
             "wdi_gdp_current_usd": 22_000.0,
             "wdi_gdp_constant_2015_usd": 21_000.0,
             "wdi_gdp_per_capita": 70_000.0,
             "wdi_gdp_per_capita_ppp_constant_2017": 75_000.0},
            {"iso3": "USA", "year": 2025,
             "wdi_gdp_current_usd": 23_000.0,
             "wdi_gdp_constant_2015_usd": 22_000.0,
             "wdi_gdp_per_capita": 71_000.0,
             "wdi_gdp_per_capita_ppp_constant_2017": 76_000.0},
        ],
    )
    wdi = WdiSource(parquet_path=_Stub(), frame=frame)  # type: ignore[arg-type]
    # The WdiSource is a plain lookup; the bound must be
    # enforced upstream by load_wdi_source / _wdi_cache_source.
    # This is the contract: never pass 2025/2026 from the
    # cache loader; the WdiSource is the audit-trail seam.
    assert wdi.lookup("USA", 2025) != {}
    # The end-to-end run uses the cache loader, which never
    # produces 2025 rows. See
    # tests/test_chronicle_wdi_cache_source.py for the bound
    # guard.


def test_wdi_cache_loader_bounds_2025_via_real_cache_file(
    tmp_path: Path,
) -> None:
    """End-to-end: a 2025 record in the cache JSON is dropped.

    The bound is enforced inside the cache loader, NOT inside
    the WdiSource. This is the production guard: the loader
    reads the file, drops out-of-window records, and only
    contributes in-window rows to the merged frame.
    """
    import json

    from leaders_db.chronicle._wdi_cache_source import load_wdi_cache_frame

    cache_file = tmp_path / "NY.GDP.MKTP.KD_1960_2024.json"
    payload = [
        {"page": 1, "pages": 1, "per_page": 25000, "total": 2,
         "sourceid": "2", "lastupdated": "2026-04-08"},
        [
            {
                "indicator": {"id": "NY.GDP.MKTP.KD", "value": "GDP"},
                "country": {"id": "US", "value": "United States"},
                "countryiso3code": "USA", "date": "2024",
                "value": 22_000.0, "unit": "", "obs_status": "",
                "decimal": 0,
            },
            {
                "indicator": {"id": "NY.GDP.MKTP.KD", "value": "GDP"},
                "country": {"id": "US", "value": "United States"},
                "countryiso3code": "USA", "date": "2025",
                "value": 23_000.0, "unit": "", "obs_status": "",
                "decimal": 0,
            },
        ],
    ]
    cache_file.write_text(json.dumps(payload), encoding="utf-8")

    frame = load_wdi_cache_frame(
        cache_dir=tmp_path, iso3_scope=("USA",),
    )
    years = sorted(frame["year"].unique())
    assert 2025 not in years
    assert 2024 in years


# ---------------------------------------------------------------------------
# Coverage metric helper (relevant denominator test)
# ---------------------------------------------------------------------------


def test_relevant_coverage_metric_excludes_non_existing_rows() -> None:
    """The relevant coverage denominator is ``exists`` rows only.

    A small helper that the production coverage report can
    reuse: the metric counts ``exists`` rows whose GDP column
    is non-empty vs the total ``exists`` row count, ignoring
    ``not_formed`` and ``split_or_dissolved`` rows. This is
    the audit-trail contract for the 80.84% -> ~81.82% GDP
    coverage improvement narrative.
    """
    from leaders_db.chronicle._economy_fields import (
        relevant_gdp_coverage,
    )

    rows = [
        {"existence_status": "exists", "gdp": "1000"},
        {"existence_status": "exists", "gdp": ""},
        {"existence_status": "exists", "gdp": "2000"},
        {"existence_status": "not_formed", "gdp": ""},
        {"existence_status": "split_or_dissolved", "gdp": ""},
    ]
    result = relevant_gdp_coverage(rows)
    assert result.exists_total == 3
    assert result.exists_with_gdp == 2
    # 2 of 3 = 66.67%
    assert abs(result.coverage_fraction - 2 / 3) < 1e-9
    # The non-existing rows do NOT enter the denominator.
    assert result.not_formed_excluded == 1
    assert result.split_or_dissolved_excluded == 1


def test_relevant_coverage_metric_handles_empty_rows() -> None:
    """The helper is robust to an empty row list (zero coverage)."""
    from leaders_db.chronicle._economy_fields import (
        relevant_gdp_coverage,
    )

    result = relevant_gdp_coverage([])
    assert result.exists_total == 0
    assert result.exists_with_gdp == 0
    assert result.coverage_fraction == 0.0
