"""Tests for the Country-Year Chronicle ruler resolver.

These tests verify the Increment 2 ruler-resolver contract:

- Archigos v4.1 is used for historical leader spells through 2015.
  The resolver picks the Archigos record whose
  ``start_year <= year <= end_year``.
- REIGN 2021-8 is used for monthly leader records 1950-2021. The
  resolver picks the leader with the most months in the requested
  year; ties go to the leader string that sorts first.
- SUN rows always resolve to missing (no vetted source covers the
  Soviet Union identity separately).
- Rows the resolver cannot resolve (e.g. year > 2021) keep the
  ``missing_ruler`` flag (the row builder surfaces it through
  :func:`assemble_flags`).
- The resolver never invents a ruler and never consults the client
  matrix or an LLM.
- The resolver handles missing-data edge cases (empty frames) by
  returning the missing-ruler placeholder.
"""

from __future__ import annotations

import pandas as pd

from leaders_db.chronicle.constants import (
    ARCHIGOS_DIRECT_CONFIDENCE,
    FLAG_MISSING_RULER,
    REIGN_DIRECT_CONFIDENCE,
    REIGN_MULTI_LEADER_CONFIDENCE,
    SOURCE_TAG_ARCHIGOS,
    SOURCE_TAG_REIGN,
)
from leaders_db.chronicle.row_builder import build_chronicle_rows
from leaders_db.chronicle.ruler_resolver import (
    RulerResolver,
    RulerResult,
)
from leaders_db.chronicle.sources import (
    SipriSource,
    VDemSource,
    WdiSource,
)

# ---------------------------------------------------------------------------
# Stub source factories
# ---------------------------------------------------------------------------


def _stub_vdem(year_to_regime: dict[tuple[str, int], float]) -> VDemSource:
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
    frame = pd.DataFrame(data, columns=columns) if rows else pd.DataFrame(
        columns=columns,
    )
    return WdiSource(parquet_path=_Stub(), frame=frame)  # type: ignore[arg-type]


def _stub_sipri() -> SipriSource:
    class _Stub:
        pass

    frame = pd.DataFrame(
        columns=["country", "year", "sipri_milex_constant_usd"],
    )
    return SipriSource(parquet_path=_Stub(), frame=frame)  # type: ignore[arg-type]


def _archigos_frame(spells: list[dict[str, object]]) -> pd.DataFrame:
    """Build a fake Archigos frame for the resolver tests."""
    return pd.DataFrame(spells, columns=["iso3", "leader", "startdate", "enddate"])


def _reign_frame(
    rows: list[dict[str, object]],
) -> pd.DataFrame:
    """Build a fake REIGN frame for the resolver tests."""
    return pd.DataFrame(
        rows,
        columns=["iso3", "year", "month", "leader", "government"],
    )


# ---------------------------------------------------------------------------
# RulerResolver direct tests
# ---------------------------------------------------------------------------


def test_archigos_resolves_usa_1900_mckinley() -> None:
    """USA 1900 resolves to McKinley via Archigos (his spell ran
    1897-03-04 to 1901-09-14 in real Archigos data)."""
    archigos = _archigos_frame(
        [
            {
                "iso3": "USA",
                "leader": "McKinley",
                "startdate": pd.Timestamp("1897-03-04"),
                "enddate": pd.Timestamp("1901-09-14"),
            },
            {
                "iso3": "USA",
                "leader": "Roosevelt",
                "startdate": pd.Timestamp("1901-09-14"),
                "enddate": pd.Timestamp("1909-03-04"),
            },
        ]
    )
    resolver = RulerResolver(archigos_frame=archigos)
    result = resolver.resolve("USA", 1900)
    assert result.has_ruler is True
    assert result.ruler_name == "McKinley"
    assert result.ruler_source == SOURCE_TAG_ARCHIGOS
    assert result.ruler_source_year_used == 1900
    assert result.ruler_confidence == ARCHIGOS_DIRECT_CONFIDENCE


def test_archigos_resolves_usa_1950_truman() -> None:
    """USA 1950 resolves to Truman via Archigos (his spell ran
    1945-04-12 to 1953-01-20)."""
    archigos = _archigos_frame(
        [
            {
                "iso3": "USA",
                "leader": "Truman",
                "startdate": pd.Timestamp("1945-04-12"),
                "enddate": pd.Timestamp("1953-01-20"),
            },
        ]
    )
    resolver = RulerResolver(archigos_frame=archigos)
    result = resolver.resolve("USA", 1950)
    assert result.has_ruler is True
    assert result.ruler_name == "Truman"
    assert result.ruler_source == SOURCE_TAG_ARCHIGOS


def test_reign_picks_leader_with_most_months() -> None:
    """REIGN: the resolver picks the leader with the most months
    in the requested year. The ``ruler_type`` carries the
    ``government`` string from the same rows (mode of the most-
    common value).
    """
    reign = _reign_frame(
        [
            # Year 2000: Bush wins 12 months vs Gore 0
            {"iso3": "USA", "year": 2000, "month": m,
             "leader": "Bush", "government": "Presidential Democracy"}
            for m in range(1, 13)
        ]
    )
    resolver = RulerResolver(reign_frame=reign)
    result = resolver.resolve("USA", 2000)
    assert result.has_ruler is True
    assert result.ruler_name == "Bush"
    assert result.ruler_source == SOURCE_TAG_REIGN
    assert result.ruler_type == "Presidential Democracy"
    assert result.ruler_confidence == REIGN_DIRECT_CONFIDENCE
    assert result.multiple_rulers is False


def test_reign_multiple_leaders_uses_multi_leader_confidence() -> None:
    """When two or more leaders share the year, the resolver picks
    the leader with the most months but applies the lower
    ``REIGN_MULTI_LEADER_CONFIDENCE`` and emits the
    ``multiple_rulers`` flag (the row builder adds the flag to
    ``data_quality_flags``).
    """
    reign = _reign_frame(
        [
            {"iso3": "RUS", "year": 1991, "month": m,
             "leader": "Gorbachev", "government": "Communist"}
            for m in range(1, 9)
        ] + [
            {"iso3": "RUS", "year": 1991, "month": m,
             "leader": "Yeltsin", "government": "Presidential Democracy"}
            for m in range(9, 13)
        ]
    )
    resolver = RulerResolver(reign_frame=reign)
    result = resolver.resolve("RUS", 1991)
    assert result.multiple_rulers is True
    # Yeltsin had 4 months vs Gorbachev's 8 -> Gorbachev wins.
    assert result.ruler_name == "Gorbachev"
    assert result.ruler_confidence == REIGN_MULTI_LEADER_CONFIDENCE


def test_modern_gap_after_2021_returns_missing_ruler() -> None:
    """Year > 2021 (beyond REIGN coverage) with no Archigos hit
    returns the missing-ruler placeholder. The resolver does
    NOT invent a leader.
    """
    resolver = RulerResolver(
        archigos_frame=_archigos_frame([]),
        reign_frame=_reign_frame([]),
    )
    result = resolver.resolve("USA", 2024)
    assert result.has_ruler is False
    assert result.ruler_name == ""
    assert result.ruler_source == ""
    assert result.ruler_confidence == 0


def test_sun_always_returns_missing_ruler() -> None:
    """SUN rows always resolve to missing. The resolver does not
    look up the RUS ccode because the merged Russian-Empire +
    USSR + RUS record does not cleanly map to SUN.
    """
    archigos = _archigos_frame(
        [
            {
                "iso3": "RUS",
                "leader": "Stalin",
                "startdate": pd.Timestamp("1924-01-21"),
                "enddate": pd.Timestamp("1953-03-05"),
            },
        ]
    )
    reign = _reign_frame(
        [
            {"iso3": "RUS", "year": 1950, "month": m,
             "leader": "Stalin", "government": "Dominant Party"}
            for m in range(1, 13)
        ]
    )
    resolver = RulerResolver(
        archigos_frame=archigos, reign_frame=reign,
    )
    result = resolver.resolve("SUN", 1950)
    assert result.has_ruler is False


def test_missing_ruler_factory_returns_canonical_placeholder() -> None:
    """The :func:`RulerResult.missing` factory returns the canonical
    placeholder fields (no leader name / source / confidence)."""
    result = RulerResult.missing(source_year_used=1950)
    assert result.has_ruler is False
    assert result.ruler_name == ""
    assert result.ruler_source == ""
    assert result.ruler_confidence == 0
    assert result.ruler_source_year_used == 1950


def test_resolver_handles_empty_frames_gracefully() -> None:
    """When both Archigos and REIGN frames are empty, the resolver
    returns the missing-ruler placeholder (no exception)."""
    resolver = RulerResolver()
    result = resolver.resolve("USA", 1950)
    assert result.has_ruler is False


# ---------------------------------------------------------------------------
# Integration with the row builder (data-quality flag emission)
# ---------------------------------------------------------------------------


def _build_one_row_iso3_year(
    *,
    iso3: str,
    year: int,
    ruler_resolver: RulerResolver,
    vdem_regime: float | None = None,
) -> dict[str, str]:
    vdem_lookup: dict[tuple[str, int], float] = {}
    if vdem_regime is not None:
        vdem_lookup[(iso3, year)] = vdem_regime
    rows = build_chronicle_rows(
        iso3_scope=(iso3,),
        start_year=year,
        end_year=year,
        vdem=_stub_vdem(vdem_lookup),
        wdi=_stub_wdi([]),
        sipri=_stub_sipri(),
        maddison=None,
        ruler_resolver=ruler_resolver,
    )
    return rows[0]


def test_row_builder_emits_missing_ruler_flag_when_resolver_cannot_find() -> None:
    """When the resolver returns has_ruler=False the row carries
    ``missing_ruler`` in ``data_quality_flags``.
    """
    resolver = RulerResolver()
    row = _build_one_row_iso3_year(
        iso3="USA", year=2024,
        ruler_resolver=resolver,
    )
    flags = row["data_quality_flags"].split("|")
    assert FLAG_MISSING_RULER in flags


def test_row_builder_drops_missing_ruler_flag_when_resolver_finds() -> None:
    """When the resolver returns has_ruler=True the row does NOT
    carry ``missing_ruler``."""
    archigos = _archigos_frame(
        [
            {
                "iso3": "USA",
                "leader": "McKinley",
                "startdate": pd.Timestamp("1897-03-04"),
                "enddate": pd.Timestamp("1901-09-14"),
            },
        ]
    )
    resolver = RulerResolver(archigos_frame=archigos)
    row = _build_one_row_iso3_year(
        iso3="USA", year=1900, ruler_resolver=resolver,
    )
    assert row["ruler_name"] == "McKinley"
    assert row["ruler_source"] == SOURCE_TAG_ARCHIGOS
    assert row["ruler_confidence"] == str(ARCHIGOS_DIRECT_CONFIDENCE)
    flags = row["data_quality_flags"].split("|")
    assert FLAG_MISSING_RULER not in flags


def test_row_builder_emits_multiple_rulers_flag() -> None:
    """When the REIGN resolver returns multiple_rulers=True the
    row builder adds ``multiple_rulers`` to ``data_quality_flags``.
    """
    reign = _reign_frame(
        [
            {"iso3": "RUS", "year": 1991, "month": m,
             "leader": "Gorbachev", "government": "Communist"}
            for m in range(1, 9)
        ] + [
            {"iso3": "RUS", "year": 1991, "month": m,
             "leader": "Yeltsin", "government": "Presidential Democracy"}
            for m in range(9, 13)
        ]
    )
    resolver = RulerResolver(reign_frame=reign)
    row = _build_one_row_iso3_year(
        iso3="RUS", year=1991, ruler_resolver=resolver,
    )
    flags = row["data_quality_flags"].split("|")
    assert "multiple_rulers" in flags


def test_row_builder_no_ruler_resolver_drops_ruler_to_placeholder() -> None:
    """Backward-compat: when ``ruler_resolver=None`` is passed the
    row builder uses an empty resolver, the ruler columns are
    empty, and ``missing_ruler`` is set."""
    rows = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=2023,
        end_year=2023,
        vdem=_stub_vdem({("USA", 2023): 3.0}),
        wdi=_stub_wdi([]),
        sipri=_stub_sipri(),
        maddison=None,
        ruler_resolver=None,
    )
    row = rows[0]
    assert row["ruler_name"] == ""
    assert row["ruler_source"] == ""
    assert row["ruler_confidence"] == "0"
    assert FLAG_MISSING_RULER in row["data_quality_flags"].split("|")


def test_provenance_summary_includes_ruler_source() -> None:
    """The provenance_summary string carries ``ruler=archigos``
    when the resolver returns an Archigos hit."""
    archigos = _archigos_frame(
        [
            {
                "iso3": "USA",
                "leader": "McKinley",
                "startdate": pd.Timestamp("1897-03-04"),
                "enddate": pd.Timestamp("1901-09-14"),
            },
        ]
    )
    resolver = RulerResolver(archigos_frame=archigos)
    row = _build_one_row_iso3_year(
        iso3="USA", year=1900, ruler_resolver=resolver,
    )
    assert "ruler=archigos" in row["provenance_summary"]
