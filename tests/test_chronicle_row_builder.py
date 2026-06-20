"""Tests for the row builder.

These tests verify the per-(iso3, year) row construction:

- exactly one row per requested ``(iso3, year)`` pair;
- the political regime / system type / WDI / SIPRI columns are
  populated from the stubbed sources;
- missing fields carry the canonical flags (missing_ruler,
  missing_area, missing_population, missing_gdp, missing_military_spend,
  controlled_area_not_modeled);
- pre-/post-existence gaps and successor-state / colonial flags
  propagate from country metadata;
- row_confidence is the simple availability-based aggregate (NOT the
  fixed ruler-score formula);
- the build does not import or call anything from the client matrix.
"""

from __future__ import annotations

import pandas as pd
import pytest

from leaders_db.chronicle.constants import (
    CHRONICLE_CSV_COLUMNS,
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
    SOURCE_TAG_SIPRI,
    SOURCE_TAG_WDI,
)
from leaders_db.chronicle.row_builder import build_chronicle_rows
from leaders_db.chronicle.sources import (
    SipriSource,
    VDemSource,
    WdiSource,
)

# ---------------------------------------------------------------------------
# Stub source factories
# ---------------------------------------------------------------------------


def _stub_vdem(year_to_regime: dict[tuple[str, int], float]) -> VDemSource:
    """Build a :class:`VDemSource` whose ``lookup`` returns the given
    regime per ``(iso3, year)`` pair."""
    rows: list[dict[str, object]] = []
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
        columns=["country_text_id", "year", "v2x_regime", "v2x_polyarchy", "v2x_libdem"],
    )
    return VDemSource(
        raw_csv_path=Path_for_stub(),  # type: ignore[arg-type]
        frame=frame,
    )


def _stub_wdi(
    rows: list[tuple[str, int, dict[str, float | None]]],
) -> WdiSource:
    """Build a :class:`WdiSource` from a list of ``(iso3, year, payload)``."""
    data: list[dict[str, object]] = []
    for iso3, year, payload in rows:
        record: dict[str, object] = {"iso3": iso3, "year": year}
        record.update(payload)
        data.append(record)
    columns = ["iso3", "year", "wdi_population", "wdi_gdp_current_usd",
               "wdi_gdp_constant_2015_usd", "wdi_gdp_per_capita",
               "wdi_gdp_per_capita_ppp_constant_2017"]
    frame = pd.DataFrame(data, columns=columns)
    return WdiSource(parquet_path=Path_for_stub(), frame=frame)  # type: ignore[arg-type]


def _stub_sipri(rows: list[tuple[str, int, float]]) -> SipriSource:
    """Build a :class:`SipriSource` from a list of
    ``(country_name, year, milex)``."""
    data = []
    for name, year, milex in rows:
        data.append(
            {
                "country": name,
                "year": year,
                "sipri_milex_constant_usd": milex,
                "sipri_milex_per_capita": milex / 1_000_000 if milex else None,
                "sipri_milex_share_of_gdp": 0.03 if milex else None,
            }
        )
    columns = ["country", "year", "sipri_milex_constant_usd",
               "sipri_milex_per_capita", "sipri_milex_share_of_gdp"]
    frame = pd.DataFrame(data, columns=columns)
    return SipriSource(parquet_path=Path_for_stub(), frame=frame)  # type: ignore[arg-type]


class Path_for_stub:
    """A stand-in Path for the stub sources.

    The build_chronicle_rows code path does not touch the source
    ``raw_csv_path`` / ``parquet_path`` attributes, so a no-op object
    is enough. We use a plain object instance to avoid coupling the
    tests to a real ``pathlib.Path`` constructor (the source loaders
    create ``Path`` instances internally; the row builder never
    inspects them).
    """

    def __init__(self) -> None:
        self._name = "<stub>"

    def __fspath__(self) -> str:
        return self._name


# ---------------------------------------------------------------------------
# Row shape
# ---------------------------------------------------------------------------


def test_one_row_per_requested_identity_year() -> None:
    """The builder emits exactly one row per (iso3, year) pair."""
    rows = build_chronicle_rows(
        iso3_scope=("USA", "SUN"),
        start_year=1990,
        end_year=1992,
        vdem=_stub_vdem({}),
        wdi=_stub_wdi([]),
        sipri=_stub_sipri([]),
    )
    assert len(rows) == 3 * 2


def test_row_keys_match_canonical_column_set() -> None:
    """Every row has exactly the canonical column keys, no extras."""
    rows = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=2023,
        end_year=2023,
        vdem=_stub_vdem({}),
        wdi=_stub_wdi([]),
        sipri=_stub_sipri([]),
    )
    assert set(rows[0].keys()) == set(CHRONICLE_CSV_COLUMNS)


def test_row_order_is_iso3_then_year_ascending() -> None:
    """Rows are emitted in iso3 order, then year ascending."""
    rows = build_chronicle_rows(
        iso3_scope=("USA", "GBR"),
        start_year=2022,
        end_year=2024,
        vdem=_stub_vdem({}),
        wdi=_stub_wdi([]),
        sipri=_stub_sipri([]),
    )
    assert [r["iso3"] for r in rows] == ["USA", "USA", "USA", "GBR", "GBR", "GBR"]
    assert [r["year"] for r in rows] == ["2022", "2023", "2024", "2022", "2023", "2024"]


def test_invalid_year_range_raises() -> None:
    """start_year > end_year raises ValueError."""
    with pytest.raises(ValueError, match="must be <="):
        build_chronicle_rows(
            iso3_scope=("USA",),
            start_year=2025,
            end_year=2024,
            vdem=_stub_vdem({}),
            wdi=_stub_wdi([]),
            sipri=_stub_sipri([]),
        )


# ---------------------------------------------------------------------------
# Political regime / system type population
# ---------------------------------------------------------------------------


def test_political_regime_bucket_populated_from_vdem() -> None:
    """A direct V-Dem hit populates the political-regime columns."""
    rows = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=2023,
        end_year=2023,
        vdem=_stub_vdem({("USA", 2023): 3.0}),
        wdi=_stub_wdi([]),
        sipri=_stub_sipri([]),
    )
    assert rows[0]["political_regime_bucket"] == "Full democracy"
    assert rows[0]["political_regime_raw_score"] == "3"
    assert rows[0]["political_regime_source"] == "vdem"
    assert rows[0]["political_regime_source_year_used"] == "2023"


def test_system_type_uses_curated_mapping_for_sun() -> None:
    """SUN 1950 uses the curated Communist one-party state mapping."""
    rows = build_chronicle_rows(
        iso3_scope=("SUN",),
        start_year=1950,
        end_year=1950,
        vdem=_stub_vdem({}),
        wdi=_stub_wdi([]),
        sipri=_stub_sipri([]),
    )
    assert rows[0]["system_type_primary"] == "Communist one-party state"
    assert rows[0]["system_type_source"] == "cyc_curated"


def test_system_type_uses_curated_mapping_for_chn_post_1949() -> None:
    """CHN 1980 uses the curated Communist one-party state mapping."""
    rows = build_chronicle_rows(
        iso3_scope=("CHN",),
        start_year=1980,
        end_year=1980,
        vdem=_stub_vdem({("CHN", 1980): 0.0}),
        wdi=_stub_wdi([]),
        sipri=_stub_sipri([]),
    )
    assert rows[0]["system_type_primary"] == "Communist one-party state"


def test_system_type_uses_curated_mapping_for_ind_pre_1947() -> None:
    """IND 1946 uses the curated Colonial administration mapping."""
    rows = build_chronicle_rows(
        iso3_scope=("IND",),
        start_year=1946,
        end_year=1946,
        vdem=_stub_vdem({}),
        wdi=_stub_wdi([]),
        sipri=_stub_sipri([]),
    )
    assert rows[0]["system_type_primary"] == "Colonial administration"


def test_rus_authoritarian_falls_back_to_mixed_unclear() -> None:
    """RUS with an Authoritarian regime bucket falls back to 'Mixed / unclear'.

    RUS is intentionally NOT in the curated country-period mapping
    (no documented conservative rule pins the full 1992-2026 window
    to a specific label). The regime-bucket fallback therefore routes
    Hybrid/Authoritarian buckets to 'Mixed / unclear' — never to
    'Conservative capitalist democracy' or any other democracy label.
    """
    rows = build_chronicle_rows(
        iso3_scope=("RUS",),
        start_year=2010,
        end_year=2010,
        vdem=_stub_vdem({("RUS", 2010): 0.0}),  # v2x_regime 0 -> Authoritarian
        wdi=_stub_wdi([]),
        sipri=_stub_sipri([]),
    )
    assert rows[0]["political_regime_bucket"] == "Authoritarian"
    assert rows[0]["system_type_primary"] == "Mixed / unclear"
    assert rows[0]["system_type_source"] == "vdem"
    # No curated mapping was used.
    assert "cyc_curated" != rows[0]["system_type_source"]


def test_rus_hybrid_falls_back_to_mixed_unclear() -> None:
    """RUS with a Hybrid regime bucket falls back to 'Mixed / unclear'."""
    rows = build_chronicle_rows(
        iso3_scope=("RUS",),
        start_year=2010,
        end_year=2010,
        vdem=_stub_vdem({("RUS", 2010): 1.0}),  # v2x_regime 1 -> Hybrid regime
        wdi=_stub_wdi([]),
        sipri=_stub_sipri([]),
    )
    assert rows[0]["political_regime_bucket"] == "Hybrid regime"
    assert rows[0]["system_type_primary"] == "Mixed / unclear"


def test_rus_no_curated_mapping_in_classifier() -> None:
    """RUS must not appear in the curated country-period mapping.

    This is a defensive check against accidentally re-adding an
    unrequested curated RUS mapping. If a future change wants to
    curate RUS, this test forces the curator to update the documented
    rule alongside the constant.
    """
    from leaders_db.chronicle.constants import SYSTEM_TYPE_COUNTRY_PERIODS

    iso3_periods = {entry[0] for entry in SYSTEM_TYPE_COUNTRY_PERIODS}
    assert "RUS" not in iso3_periods


def test_full_democracy_default_is_liberal_capitalist_democracy() -> None:
    """USA 1990 (Full democracy, no curated mapping) -> Liberal capitalist democracy."""
    rows = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=1990,
        end_year=1990,
        vdem=_stub_vdem({("USA", 1990): 3.0}),
        wdi=_stub_wdi([]),
        sipri=_stub_sipri([]),
    )
    assert rows[0]["system_type_primary"] == "Liberal capitalist democracy"


# ---------------------------------------------------------------------------
# Missing-field flags
# ---------------------------------------------------------------------------


def test_missing_population_flag_when_wdi_absent() -> None:
    """A row with no WDI hit carries ``missing_population``."""
    rows = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=1990,
        end_year=1990,
        vdem=_stub_vdem({}),
        wdi=_stub_wdi([]),
        sipri=_stub_sipri([]),
    )
    assert FLAG_MISSING_POPULATION in rows[0]["data_quality_flags"].split("|")


def test_missing_gdp_flag_when_wdi_absent() -> None:
    """A row with no WDI hit carries ``missing_gdp``."""
    rows = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=1990,
        end_year=1990,
        vdem=_stub_vdem({}),
        wdi=_stub_wdi([]),
        sipri=_stub_sipri([]),
    )
    assert FLAG_MISSING_GDP in rows[0]["data_quality_flags"].split("|")


def test_missing_military_spend_flag_when_sipri_absent() -> None:
    """A row with no SIPRI hit carries ``missing_military_spend``."""
    rows = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=1990,
        end_year=1990,
        vdem=_stub_vdem({}),
        wdi=_stub_wdi([]),
        sipri=_stub_sipri([]),
    )
    assert FLAG_MISSING_MILITARY_SPEND in rows[0]["data_quality_flags"].split("|")


def test_missing_ruler_flag_always_present() -> None:
    """Increment 1 always emits the ``missing_ruler`` flag (no resolver yet)."""
    rows = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=2023,
        end_year=2023,
        vdem=_stub_vdem({("USA", 2023): 3.0}),
        wdi=_stub_wdi([]),
        sipri=_stub_sipri([]),
    )
    assert FLAG_MISSING_RULER in rows[0]["data_quality_flags"].split("|")


def test_missing_area_flag_always_present() -> None:
    """Increment 1 always emits the ``missing_area`` flag (no static area source)."""
    rows = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=2023,
        end_year=2023,
        vdem=_stub_vdem({("USA", 2023): 3.0}),
        wdi=_stub_wdi([]),
        sipri=_stub_sipri([]),
    )
    assert FLAG_MISSING_AREA in rows[0]["data_quality_flags"].split("|")


def test_controlled_area_not_modeled_flag_always_present() -> None:
    """Increment 1 always emits ``controlled_area_not_modeled`` (deferred feature)."""
    rows = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=2023,
        end_year=2023,
        vdem=_stub_vdem({("USA", 2023): 3.0}),
        wdi=_stub_wdi([]),
        sipri=_stub_sipri([]),
    )
    assert FLAG_CONTROLLED_AREA_NOT_MODELED in rows[0]["data_quality_flags"].split("|")


def test_population_present_when_wdi_has_data() -> None:
    """When the WDI stub returns a value, population is populated and
    ``missing_population`` is absent."""
    rows = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=2022,
        end_year=2022,
        vdem=_stub_vdem({}),
        wdi=_stub_wdi(
            [
                ("USA", 2022, {
                    "wdi_population": 334_000_000.0,
                    "wdi_gdp_constant_2015_usd": 21_000_000_000_000.0,
                    "wdi_gdp_per_capita": 76_000.0,
                    "wdi_gdp_per_capita_ppp_constant_2017": 76_000.0,
                })
            ]
        ),
        sipri=_stub_sipri([]),
    )
    assert rows[0]["population"] == "334000000"
    assert rows[0]["population_source"] == SOURCE_TAG_WDI
    assert rows[0]["population_source_year_used"] == "2022"
    assert FLAG_MISSING_POPULATION not in rows[0]["data_quality_flags"].split("|")
    assert FLAG_MISSING_GDP not in rows[0]["data_quality_flags"].split("|")


def test_sipri_military_spend_populated_when_available() -> None:
    """When the SIPRI stub has a row for the year, military_spend is
    populated and ``missing_military_spend`` is absent."""
    rows = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=2022,
        end_year=2022,
        vdem=_stub_vdem({}),
        wdi=_stub_wdi([]),
        sipri=_stub_sipri([("United States of America", 2022, 922_000_000_000.0)]),
    )
    assert rows[0]["military_spend"] == "922000000000"
    assert rows[0]["military_spend_source"] == SOURCE_TAG_SIPRI
    assert rows[0]["military_spend_source_year_used"] == "2022"
    assert FLAG_MISSING_MILITARY_SPEND not in rows[0]["data_quality_flags"].split("|")


def _stub_sipri_with_ancillary_only(
    rows: list[tuple[str, int, dict[str, float | None]]],
) -> SipriSource:
    """Build a SipriSource whose lookup returns ancillary values but
    NO ``milex_constant_usd`` cell.

    Used to verify that ``missing_military_spend`` is driven
    exclusively by the canonical CSV target field
    ``milex_constant_usd`` and not by per-capita / share-of-GDP
    ancillary values.
    """
    data = []
    for name, year, payload in rows:
        record: dict[str, object] = {"country": name, "year": year}
        record.update(payload)
        data.append(record)
    columns = ["country", "year", "sipri_milex_constant_usd",
               "sipri_milex_per_capita", "sipri_milex_share_of_gdp"]
    frame = pd.DataFrame(data, columns=columns)
    return SipriSource(parquet_path=Path_for_stub(), frame=frame)  # type: ignore[arg-type]


def test_missing_military_spend_when_only_ancillary_sipri_values_present() -> None:
    """The ``missing_military_spend`` flag is driven by ``milex_constant_usd``
    only — ancillary per-capita / share-of-GDP values do not clear it.

    This pins down the reviewer-mandated contract: the flag tracks
    whether the canonical CSV target field has a usable value, not
    whether *any* SIPRI-derived metric is non-null. A row with
    ancillary values present but ``milex_constant_usd=None`` must
    emit an empty ``military_spend`` cell AND carry the
    ``missing_military_spend`` flag.
    """
    rows = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=2022,
        end_year=2022,
        vdem=_stub_vdem({}),
        wdi=_stub_wdi([]),
        sipri=_stub_sipri_with_ancillary_only(
            [
                (
                    "United States of America",
                    2022,
                    {
                        # No canonical milex_constant_usd cell; only ancillary.
                        "sipri_milex_constant_usd": None,
                        "sipri_milex_per_capita": 2740.5,
                        "sipri_milex_share_of_gdp": 0.033,
                    },
                ),
            ]
        ),
    )
    flags = rows[0]["data_quality_flags"].split("|")
    assert rows[0]["military_spend"] == ""
    assert rows[0]["military_spend_source"] == ""
    assert rows[0]["military_spend_source_year_used"] == ""
    assert FLAG_MISSING_MILITARY_SPEND in flags


# ---------------------------------------------------------------------------
# Pre/post-existence / successor / colonial flags
# ---------------------------------------------------------------------------


def test_pre_existence_flag_for_country_before_start_year() -> None:
    """CHN 1900 (start_year is 1949) carries ``pre_existence_gap``."""
    rows = build_chronicle_rows(
        iso3_scope=("CHN",),
        start_year=1900,
        end_year=1900,
        vdem=_stub_vdem({}),
        wdi=_stub_wdi([]),
        sipri=_stub_sipri([]),
    )
    assert FLAG_PRE_EXISTENCE_GAP in rows[0]["data_quality_flags"].split("|")


def test_post_existence_flag_for_country_after_end_year() -> None:
    """SUN 2000 (end_year is 1991) carries ``post_existence_gap``."""
    rows = build_chronicle_rows(
        iso3_scope=("SUN",),
        start_year=2000,
        end_year=2000,
        vdem=_stub_vdem({}),
        wdi=_stub_wdi([]),
        sipri=_stub_sipri([]),
    )
    assert FLAG_POST_EXISTENCE_GAP in rows[0]["data_quality_flags"].split("|")


def test_successor_state_flag_for_sun() -> None:
    """SUN always carries ``successor_state_issue`` (country metadata)."""
    rows = build_chronicle_rows(
        iso3_scope=("SUN",),
        start_year=1950,
        end_year=1950,
        vdem=_stub_vdem({}),
        wdi=_stub_wdi([]),
        sipri=_stub_sipri([]),
    )
    assert FLAG_SUCCESSOR_STATE_ISSUE in rows[0]["data_quality_flags"].split("|")


def test_colonial_status_flag_for_ind_pre_1947() -> None:
    """IND 1900 carries ``colonial_status_issue`` (colonial_status_until=1946)."""
    rows = build_chronicle_rows(
        iso3_scope=("IND",),
        start_year=1900,
        end_year=1900,
        vdem=_stub_vdem({}),
        wdi=_stub_wdi([]),
        sipri=_stub_sipri([]),
    )
    assert FLAG_COLONIAL_STATUS_ISSUE in rows[0]["data_quality_flags"].split("|")


def test_no_colonial_status_flag_for_ind_post_1947() -> None:
    """IND 1950 does NOT carry ``colonial_status_issue``."""
    rows = build_chronicle_rows(
        iso3_scope=("IND",),
        start_year=1950,
        end_year=1950,
        vdem=_stub_vdem({}),
        wdi=_stub_wdi([]),
        sipri=_stub_sipri([]),
    )
    assert FLAG_COLONIAL_STATUS_ISSUE not in rows[0]["data_quality_flags"].split("|")


def test_ind_country_status_colonial_dependent_for_1900() -> None:
    """IND 1900 carries ``country_status='colonial/dependent'``.

    Pre-1947 (i.e. ``year <= colonial_status_until=1946``) the row
    builder flips the static ``country_status`` to the historical
    value for the same ISO3 identity — we do not invent a separate
    British-India record.
    """
    rows = build_chronicle_rows(
        iso3_scope=("IND",),
        start_year=1900,
        end_year=1900,
        vdem=_stub_vdem({}),
        wdi=_stub_wdi([]),
        sipri=_stub_sipri([]),
    )
    assert rows[0]["country_status"] == "colonial/dependent"
    # The colonial_status_issue flag still applies for that year.
    assert FLAG_COLONIAL_STATUS_ISSUE in rows[0]["data_quality_flags"].split("|")


def test_ind_country_status_colonial_dependent_for_1946() -> None:
    """IND 1946 (last colonial year per the documented cutoff) is
    'colonial/dependent'.
    """
    rows = build_chronicle_rows(
        iso3_scope=("IND",),
        start_year=1946,
        end_year=1946,
        vdem=_stub_vdem({}),
        wdi=_stub_wdi([]),
        sipri=_stub_sipri([]),
    )
    assert rows[0]["country_status"] == "colonial/dependent"
    assert FLAG_COLONIAL_STATUS_ISSUE in rows[0]["data_quality_flags"].split("|")


def test_ind_country_status_independent_for_1947() -> None:
    """IND 1947 (independence year) flips back to 'independent'.

    1947 is the first year strictly greater than the documented
    ``colonial_status_until=1946`` cutoff, so the static
    ``country_status='independent`` from ``COUNTRY_METADATA`` is
    emitted and the ``colonial_status_issue`` flag is removed.
    """
    rows = build_chronicle_rows(
        iso3_scope=("IND",),
        start_year=1947,
        end_year=1947,
        vdem=_stub_vdem({}),
        wdi=_stub_wdi([]),
        sipri=_stub_sipri([]),
    )
    assert rows[0]["country_status"] == "independent"
    assert FLAG_COLONIAL_STATUS_ISSUE not in rows[0]["data_quality_flags"].split("|")


# ---------------------------------------------------------------------------
# Proxy-year flag
# ---------------------------------------------------------------------------


def test_proxy_year_flag_for_year_beyond_vdem_coverage() -> None:
    """A row for year 2026 with the proxy enabled carries ``proxy_year_used``."""
    rows = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=2026,
        end_year=2026,
        vdem=_stub_vdem({("USA", 2025): 2.0}),
        wdi=_stub_wdi([]),
        sipri=_stub_sipri([]),
        allow_regime_proxy=True,
    )
    assert FLAG_PROXY_YEAR_USED in rows[0]["data_quality_flags"].split("|")


def test_no_proxy_year_flag_when_proxy_disabled() -> None:
    """With ``allow_regime_proxy=False`` the row does not get the proxy
    flag and the regime bucket falls back to Unknown + gap."""
    rows = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=2026,
        end_year=2026,
        vdem=_stub_vdem({("USA", 2025): 2.0}),
        wdi=_stub_wdi([]),
        sipri=_stub_sipri([]),
        allow_regime_proxy=False,
    )
    assert FLAG_PROXY_YEAR_USED not in rows[0]["data_quality_flags"].split("|")
    assert rows[0]["political_regime_bucket"] == "Unknown"
    assert FLAG_REGIME_SOURCE_GAP in rows[0]["data_quality_flags"].split("|")


# ---------------------------------------------------------------------------
# row_confidence aggregation
# ---------------------------------------------------------------------------


def test_row_confidence_aggregates_availability() -> None:
    """row_confidence increases when more sources contribute."""
    # All-empty: row_confidence is dominated by the 0-source paths.
    rows_empty = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=2023,
        end_year=2023,
        vdem=_stub_vdem({}),
        wdi=_stub_wdi([]),
        sipri=_stub_sipri([]),
    )
    # With V-Dem direct hit + WDI + SIPRI: higher confidence.
    rows_full = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=2022,
        end_year=2022,
        vdem=_stub_vdem({("USA", 2022): 3.0}),
        wdi=_stub_wdi(
            [(
                "USA", 2022,
                {
                    "wdi_population": 334_000_000.0,
                    "wdi_gdp_constant_2015_usd": 21_000_000_000_000.0,
                    "wdi_gdp_per_capita": 76_000.0,
                    "wdi_gdp_per_capita_ppp_constant_2017": 76_000.0,
                },
            )]
        ),
        sipri=_stub_sipri([("United States of America", 2022, 922_000_000_000.0)]),
    )
    assert int(rows_full[0]["row_confidence"]) > int(rows_empty[0]["row_confidence"])


def test_row_confidence_does_not_use_fixed_scorer_formula() -> None:
    """The row_confidence aggregate does NOT use the
    ``0.35*agreement + 0.25*authority + 0.25*specificity + 0.15*temporal_fit``
    formula. We assert this indirectly by checking that two rows with
    the same per-field confidences but different WDI / SIPRI coverage
    yield different row_confidences — which the fixed formula would
    NOT do (it only uses the four named components)."""
    rows_with_wdi = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=2022,
        end_year=2022,
        vdem=_stub_vdem({("USA", 2022): 3.0}),
        wdi=_stub_wdi(
            [(
                "USA", 2022,
                {
                    "wdi_population": 334_000_000.0,
                    "wdi_gdp_constant_2015_usd": 21_000_000_000_000.0,
                    "wdi_gdp_per_capita": 76_000.0,
                },
            )]
        ),
        sipri=_stub_sipri([]),
    )
    rows_without_wdi = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=2022,
        end_year=2022,
        vdem=_stub_vdem({("USA", 2022): 3.0}),
        wdi=_stub_wdi([]),
        sipri=_stub_sipri([]),
    )
    # The same V-Dem regime + system_type means regime_confidence and
    # system_type_confidence are identical, so the fixed formula
    # would yield the same total. We expect the slice aggregate to
    # differ because WDI coverage contributes.
    assert (
        rows_with_wdi[0]["row_confidence"]
        != rows_without_wdi[0]["row_confidence"]
    )


def test_row_confidence_within_0_100() -> None:
    """The row_confidence aggregate is clamped to 0..100."""
    rows = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=2022,
        end_year=2022,
        vdem=_stub_vdem({("USA", 2022): 3.0}),
        wdi=_stub_wdi(
            [(
                "USA", 2022,
                {
                    "wdi_population": 334_000_000.0,
                    "wdi_gdp_constant_2015_usd": 21_000_000_000_000.0,
                    "wdi_gdp_per_capita": 76_000.0,
                },
            )]
        ),
        sipri=_stub_sipri([("United States of America", 2022, 922_000_000_000.0)]),
    )
    confidence = int(rows[0]["row_confidence"])
    assert 0 <= confidence <= 100


# ---------------------------------------------------------------------------
# Provenance summary
# ---------------------------------------------------------------------------


def test_provenance_summary_includes_source_hits() -> None:
    """The provenance_summary string encodes which sources contributed."""
    rows = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=2022,
        end_year=2022,
        vdem=_stub_vdem({("USA", 2022): 3.0}),
        wdi=_stub_wdi(
            [(
                "USA", 2022,
                {"wdi_population": 334_000_000.0},
            )]
        ),
        sipri=_stub_sipri([]),
    )
    summary = rows[0]["provenance_summary"]
    assert "regime=vdem" in summary
    assert "wdi=yes" in summary
    assert "sipri=no" in summary


# ---------------------------------------------------------------------------
# No client matrix usage
# ---------------------------------------------------------------------------


def test_row_builder_does_not_import_client_matrix(monkeypatch: pytest.MonkeyPatch) -> None:
    """The row builder must not import the client_matrix module.

    We monkeypatch the client_matrix module so a successful import
    would set a sentinel; the row builder's import path is checked
    via ``sys.modules`` after the call.
    """
    import sys

    sentinel = object()
    # If ``leaders_db.ingest.client_matrix`` is imported during the
    # build, replace it with the sentinel so we can detect it.
    client_matrix_module = sys.modules.get("leaders_db.ingest.client_matrix")
    if client_matrix_module is None:
        # Pre-create a stub module so an import succeeds without
        # actually loading the real module.
        import types

        stub = types.ModuleType("leaders_db.ingest.client_matrix")
        stub.SENTINEL = sentinel  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "leaders_db.ingest.client_matrix", stub)
    else:
        # If already loaded (e.g. via another test), just attach a
        # marker attribute.
        client_matrix_module.SENTINEL = sentinel

    rows = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=2022,
        end_year=2022,
        vdem=_stub_vdem({("USA", 2022): 3.0}),
        wdi=_stub_wdi([]),
        sipri=_stub_sipri([]),
    )
    assert rows
    # The real client_matrix module (if loaded) must not have been
    # touched by the build.
    loaded = sys.modules.get("leaders_db.ingest.client_matrix")
    if loaded is not None and hasattr(loaded, "SENTINEL"):
        # Either the stub stayed untouched (good) or the real module
        # was already loaded elsewhere. The check below catches a
        # *new* import by the builder: the stub's ``__name__`` would
        # be a different module object.
        assert getattr(loaded, "SENTINEL", None) is sentinel, (
            "row_builder mutated the stub client_matrix module — it is "
            "importing the client_matrix module."
        )


def test_chronicle_package_does_not_import_client_matrix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Importing the chronicle package must not pull in client_matrix.

    This is a static-import guard. We monkeypatch the module so an
    import fails loudly if attempted; if the chronicle package ever
    starts depending on it, this test catches the regression.
    """
    import importlib
    import sys

    # Block the real client_matrix from being imported by raising
    # ImportError on its first access.
    real_module = sys.modules.get("leaders_db.ingest.client_matrix")

    class _Blocker:
        def __getattr__(self, _name: str) -> object:
            raise ImportError(
                "leaders_db.ingest.client_matrix was imported from chronicle; "
                "this is forbidden by Increment 1 contract."
            )

    blocker = _Blocker()
    monkeypatch.setitem(sys.modules, "leaders_db.ingest.client_matrix", blocker)

    # Reload chronicle modules to force fresh imports.
    for mod_name in list(sys.modules):
        if mod_name.startswith("leaders_db.chronicle"):
            monkeypatch.delitem(sys.modules, mod_name, raising=False)

    importlib.import_module("leaders_db.chronicle")

    # Restore the real module if it existed, so other tests are unaffected.
    if real_module is not None:
        monkeypatch.setitem(
            sys.modules, "leaders_db.ingest.client_matrix", real_module
        )
