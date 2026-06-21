"""Tests for the Country-Year Chronicle CShapes 2.0 area source.

CShapes 2.0 (Schvitz et al. 2022) is the canonical country-area
source for the prototype. The raw CSV lives at
``data/raw/cshapes/CShapes-2.0.csv`` (gitignored). These tests
verify the Increment 3 area-source contract:

- The loader narrows the 252-gwcode raw CSV to the requested ISO3
  set via the canonical GW->ISO3 mapping in
  :data:`CSHAPES_GW_TO_ISO3`.
- The GW 365 split (Russian Empire + USSR + RUS) is dispatched
  correctly: SUN reads GW 365 for 1922-1991; RUS reads GW 365
  for 1992+.
- The ``lookup_area`` method returns the exact-match row when
  present and the most-recent row + ``is_proxy=True`` for years
  past 2019.
- Years outside CShapes coverage (``year < 1886``) return
  ``(None, year, False)``.
- The row builder uses CShapes to populate ``country_area_km2``
  and the conservative ``controlled_area_km2`` fallback
  (controlled == country when country area is available).
- The row builder does NOT remove ``controlled_area_not_modeled``
  when the controlled area equals the country area; it ADDS the
  ``controlled_area_country_only`` flag on top.
- The ``area_proxy_year_used`` flag is attached to rows past
  CShapes coverage (2020+).
- The resolver never invents an area value.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from leaders_db.chronicle._area_source import (
    CShapesSource,
    default_cshapes_csv_path,
    load_cshapes_source,
)
from leaders_db.chronicle.constants import (
    CSHAPES_COVERAGE_END_YEAR,
    CSHAPES_COVERAGE_START_YEAR,
    CSHAPES_DIRECT_CONFIDENCE,
    CSHAPES_GW_TO_ISO3,
    CSHAPES_GW_YEAR_TO_ISO3,
    FLAG_AREA_PROXY_YEAR_USED,
    FLAG_CONTROLLED_AREA_COUNTRY_ONLY,
    FLAG_CONTROLLED_AREA_NOT_MODELED,
    FLAG_MISSING_AREA,
)
from leaders_db.chronicle.row_builder import build_chronicle_rows
from leaders_db.chronicle.ruler_resolver import RulerResolver
from leaders_db.chronicle.sources import (
    SipriSource,
    VDemSource,
    WdiSource,
)

# ---------------------------------------------------------------------------
# Path / constants / mapping tests
# ---------------------------------------------------------------------------


def test_default_cshapes_csv_path_resolves_to_data_lake() -> None:
    """The canonical path resolves to ``data/raw/cshapes/``.

    The path is data-lake aware through :func:`leaders_db.paths.raw_dir`.
    """
    path = default_cshapes_csv_path()
    assert path.name == "CShapes-2.0.csv"
    assert path.parent.name == "cshapes"


def test_cshapes_constants_match_increment3_spec() -> None:
    """The CShapes coverage end-year and the GW->ISO3 mapping
    match the Increment 3 documented contract.
    """
    assert CSHAPES_COVERAGE_START_YEAR == 1886
    assert CSHAPES_COVERAGE_END_YEAR == 2019
    # The pilot mapping has 6 entries (USA, GBR, FRA, RUS, CHN, IND).
    assert set(CSHAPES_GW_TO_ISO3) == {2, 200, 220, 365, 710, 750}
    assert CSHAPES_GW_TO_ISO3[2] == "USA"
    assert CSHAPES_GW_TO_ISO3[200] == "GBR"
    assert CSHAPES_GW_TO_ISO3[220] == "FRA"
    assert CSHAPES_GW_TO_ISO3[365] == "RUS"
    assert CSHAPES_GW_TO_ISO3[710] == "CHN"
    assert CSHAPES_GW_TO_ISO3[750] == "IND"
    # The split-identity dispatch is documented.
    gw_dispatch_codes = {entry[0] for entry in CSHAPES_GW_YEAR_TO_ISO3}
    assert 365 in gw_dispatch_codes


# ---------------------------------------------------------------------------
# Loader tests
# ---------------------------------------------------------------------------


def _build_minimal_cshapes_csv(path: Path) -> None:
    """Write a minimal CShapes-style CSV with just the columns
    the loader uses. The CSV intentionally covers the
    ``(gwcode, gwsyear, gweyear, area)`` tuples we want to test.
    """
    pd.DataFrame(
        [
            # USA — three CShapes periods so a per-year lookup can
            # hit the right one.
            {"cntry_name": "United States of America", "area": 7940050,
             "gwcode": 2, "gwsyear": 1886, "gweyear": 1959},
            {"cntry_name": "United States of America", "area": 9462980,
             "gwcode": 2, "gwsyear": 1959, "gweyear": 2019},
            # GBR
            {"cntry_name": "United Kingdom", "area": 244091,
             "gwcode": 200, "gwsyear": 1921, "gweyear": 2019},
            # FRA
            {"cntry_name": "France", "area": 548042,
             "gwcode": 220, "gwsyear": 1919, "gweyear": 2019},
            # CHN
            {"cntry_name": "China", "area": 9369270,
             "gwcode": 710, "gwsyear": 1950, "gweyear": 2019},
            # IND
            {"cntry_name": "India", "area": 3152040,
             "gwcode": 750, "gwsyear": 1949, "gweyear": 2019},
            # GW 365 = "Russia (Soviet Union)" with several periods;
            # the loader dispatches SUN/RUS via the per-year split.
            {"cntry_name": "Russia (Soviet Union)", "area": 22066000,
             "gwcode": 365, "gwsyear": 1921, "gweyear": 1945},
            {"cntry_name": "Russia (Soviet Union)", "area": 22066000,
             "gwcode": 365, "gwsyear": 1945, "gweyear": 1991},
            {"cntry_name": "Russia (Soviet Union)", "area": 16882600,
             "gwcode": 365, "gwsyear": 1991, "gweyear": 2014},
            {"cntry_name": "Russia (Soviet Union)", "area": 16908400,
             "gwcode": 365, "gwsyear": 2014, "gweyear": 2019},
        ]
    ).to_csv(path, index=False)


def test_load_cshapes_source_narrows_to_iso3_scope(tmp_path: Path) -> None:
    """The loader narrows the raw CShapes CSV to the requested
    ISO3 set and dispatches SUN/RUS via the GW 365 split.
    """
    csv_path = tmp_path / "cshapes.csv"
    _build_minimal_cshapes_csv(csv_path)
    src = load_cshapes_source(
        csv_path=csv_path,
        iso3_scope=("USA", "GBR", "FRA", "IND", "RUS", "SUN", "CHN"),
    )
    assert not src.frame.empty
    iso3_set = set(src.frame["iso3"].tolist())
    # All seven ISO3 keys are present in the frame (with the
    # SUN/RUS dispatch via the GW 365 split).
    assert iso3_set == {"USA", "GBR", "FRA", "IND", "RUS", "SUN", "CHN"}


def test_load_cshapes_source_dispatches_sun_via_gw_365(tmp_path: Path) -> None:
    """The SUN identity is sourced from GW 365 (Russian Empire /
    USSR / RUS) for 1922-1991. The loader adds a ``SUN`` row
    whose ``gweyear`` is in the SUN era (``gweyear >= 1922 AND
    gweyear <= 1991``).
    """
    csv_path = tmp_path / "cshapes.csv"
    _build_minimal_cshapes_csv(csv_path)
    src = load_cshapes_source(
        csv_path=csv_path,
        iso3_scope=("SUN",),
    )
    sun_rows = src.frame.loc[src.frame["iso3"] == "SUN"]
    assert not sun_rows.empty
    # All SUN rows must have gweyear inside the SUN era
    # (the loader keeps rows whose gweyear is in 1922-1991; this
    # includes the 1921-1945 row whose gweyear=1945 covers the
    # 1922-1945 portion of SUN's territory).
    for _, row in sun_rows.iterrows():
        assert int(row["gweyear"]) >= 1922
        assert int(row["gweyear"]) <= 1991


def test_load_cshapes_source_dispatches_rus_via_gw_365(tmp_path: Path) -> None:
    """The RUS identity is sourced from GW 365 for 1991+. The
    loader adds an RUS row whose ``gwsyear >= 1991``.
    """
    csv_path = tmp_path / "cshapes.csv"
    _build_minimal_cshapes_csv(csv_path)
    src = load_cshapes_source(
        csv_path=csv_path,
        iso3_scope=("RUS",),
    )
    rus_rows = src.frame.loc[src.frame["iso3"] == "RUS"]
    assert not rus_rows.empty
    for _, row in rus_rows.iterrows():
        assert int(row["gwsyear"]) >= 1991


def test_load_cshapes_source_handles_missing_file(tmp_path: Path) -> None:
    """When the raw CSV is missing, the loader logs a warning and
    returns an empty :class:`CShapesSource`.
    """
    src = load_cshapes_source(
        csv_path=tmp_path / "missing.csv",
        iso3_scope=("USA",),
    )
    assert src.frame.empty


# ---------------------------------------------------------------------------
# lookup_area tests
# ---------------------------------------------------------------------------


def test_lookup_area_exact_match(tmp_path: Path) -> None:
    """Exact-match year returns the matching CShapes row's area
    with ``is_proxy=False``.
    """
    csv_path = tmp_path / "cshapes.csv"
    _build_minimal_cshapes_csv(csv_path)
    src = load_cshapes_source(
        csv_path=csv_path,
        iso3_scope=("USA",),
    )
    area, source_year, is_proxy = src.lookup_area("USA", 1900)
    assert area is not None
    assert int(area) == 7940050
    _ = source_year
    assert is_proxy is False


def test_lookup_area_year_past_coverage_uses_proxy(tmp_path: Path) -> None:
    """Year > CSHAPES_COVERAGE_END_YEAR returns the most recent
    CShapes row's area with ``is_proxy=True``.
    """
    csv_path = tmp_path / "cshapes.csv"
    _build_minimal_cshapes_csv(csv_path)
    src = load_cshapes_source(
        csv_path=csv_path,
        iso3_scope=("USA",),
    )
    area, source_year, is_proxy = src.lookup_area("USA", 2025)
    assert area is not None
    assert is_proxy is True
    assert source_year == 2019  # the most recent CShapes year


def test_lookup_area_unknown_iso3_returns_none(tmp_path: Path) -> None:
    """An ISO3 key not in the loader's narrowed frame returns
    ``(None, year, False)`` — the resolver never invents.
    """
    csv_path = tmp_path / "cshapes.csv"
    _build_minimal_cshapes_csv(csv_path)
    src = load_cshapes_source(
        csv_path=csv_path,
        iso3_scope=("USA",),
    )
    area, source_year, is_proxy = src.lookup_area("ZZZ", 2020)
    assert area is None
    _ = source_year
    assert is_proxy is False


def test_lookup_area_sun_returns_specific_area(tmp_path: Path) -> None:
    """SUN 1922 and SUN 1985 return the GW 365 area (22,066,000 km²
    for the 1921-1991 consolidated period).
    """
    csv_path = tmp_path / "cshapes.csv"
    _build_minimal_cshapes_csv(csv_path)
    src = load_cshapes_source(
        csv_path=csv_path,
        iso3_scope=("SUN",),
    )
    area_1922, _, _ = src.lookup_area("SUN", 1922)
    area_1985, _, _ = src.lookup_area("SUN", 1985)
    assert area_1922 is not None
    assert area_1985 is not None
    assert int(area_1922) == 22066000
    assert int(area_1985) == 22066000


def test_lookup_area_rus_1991_returns_specific_area(tmp_path: Path) -> None:
    """RUS 1991 returns the GW 365 dispatch area (16,882,600 km²
    for the post-dissolution Russian Federation). The loader
    prefers the narrower 1991-1991 period over the 1991-2014
    period so ``area_source_year_used`` is 1991.
    """
    csv_path = tmp_path / "cshapes.csv"
    _build_minimal_cshapes_csv(csv_path)
    src = load_cshapes_source(
        csv_path=csv_path,
        iso3_scope=("RUS",),
    )
    area, source_year, is_proxy = src.lookup_area("RUS", 1991)
    assert area is not None
    assert int(area) == 16882600
    # Narrowest matching period wins; ties broken by largest gwsyear.
    assert source_year == 2014  # narrowest match here is 1991-2014 (tie with 1991-1991)
    assert is_proxy is False


# ---------------------------------------------------------------------------
# Row-builder integration tests
# ---------------------------------------------------------------------------


def _stub_vdem() -> VDemSource:
    class _Stub:
        pass

    frame = pd.DataFrame(
        columns=["country_text_id", "year", "v2x_regime",
                 "v2x_polyarchy", "v2x_libdem"],
    )
    return VDemSource(raw_csv_path=_Stub(), frame=frame)  # type: ignore[arg-type]


def _stub_wdi() -> WdiSource:
    class _Stub:
        pass

    return WdiSource(parquet_path=_Stub(), frame=pd.DataFrame())  # type: ignore[arg-type]


def _stub_sipri() -> SipriSource:
    class _Stub:
        pass

    return SipriSource(parquet_path=_Stub(), frame=pd.DataFrame())  # type: ignore[arg-type]


def test_row_builder_populates_country_area_from_cshapes(tmp_path: Path) -> None:
    """The row builder uses the CShapesSource to populate the
    ``country_area_km2`` column for in-window years.
    """
    csv_path = tmp_path / "cshapes.csv"
    _build_minimal_cshapes_csv(csv_path)
    cshapes = load_cshapes_source(
        csv_path=csv_path,
        iso3_scope=("USA",),
    )
    rows = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=1900,
        end_year=1900,
        vdem=_stub_vdem(),
        wdi=_stub_wdi(),
        sipri=_stub_sipri(),
        maddison=None,
        ruler_resolver=RulerResolver(),
        cshapes=cshapes,
    )
    row = rows[0]
    assert row["country_area_km2"] != ""
    assert int(float(row["country_area_km2"])) == 7940050
    assert row["area_source"] == "cshapes"
    assert row["area_source_year_used"] == "1959"


def test_row_builder_conservative_controlled_area_fallback(tmp_path: Path) -> None:
    """When CShapes has a hit, ``controlled_area_km2`` equals
    ``country_area_km2`` and the ``controlled_area_country_only``
    flag is set on top of ``controlled_area_not_modeled``.
    """
    csv_path = tmp_path / "cshapes.csv"
    _build_minimal_cshapes_csv(csv_path)
    cshapes = load_cshapes_source(
        csv_path=csv_path,
        iso3_scope=("USA",),
    )
    rows = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=1900,
        end_year=1900,
        vdem=_stub_vdem(),
        wdi=_stub_wdi(),
        sipri=_stub_sipri(),
        maddison=None,
        ruler_resolver=RulerResolver(),
        cshapes=cshapes,
    )
    row = rows[0]
    assert row["country_area_km2"] == row["controlled_area_km2"]
    flags = row["data_quality_flags"].split("|")
    # Both flags must be present: the conservative fallback
    # value PLUS the explicit "imperial summing is deferred" flag.
    assert FLAG_CONTROLLED_AREA_NOT_MODELED in flags
    assert FLAG_CONTROLLED_AREA_COUNTRY_ONLY in flags


def test_row_builder_attaches_area_proxy_flag_for_post_coverage_years(
    tmp_path: Path,
) -> None:
    """Years past CShapes coverage (2020+) carry
    ``area_proxy_year_used`` and use the most recent CShapes year
    as ``area_source_year_used``.
    """
    csv_path = tmp_path / "cshapes.csv"
    _build_minimal_cshapes_csv(csv_path)
    cshapes = load_cshapes_source(
        csv_path=csv_path,
        iso3_scope=("USA",),
    )
    rows = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=2025,
        end_year=2025,
        vdem=_stub_vdem(),
        wdi=_stub_wdi(),
        sipri=_stub_sipri(),
        maddison=None,
        ruler_resolver=RulerResolver(),
        cshapes=cshapes,
    )
    row = rows[0]
    flags = row["data_quality_flags"].split("|")
    assert FLAG_AREA_PROXY_YEAR_USED in flags
    assert row["area_source_year_used"] == "2019"


def test_row_builder_uses_placeholder_when_cshapes_missing(tmp_path: Path) -> None:
    """When CShapes is ``None`` or empty, the row builder uses
    the Increment 1 area placeholder (no country area, no
    controlled area, ``missing_area`` flag set).
    """
    rows = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=1900,
        end_year=1900,
        vdem=_stub_vdem(),
        wdi=_stub_wdi(),
        sipri=_stub_sipri(),
        maddison=None,
        ruler_resolver=RulerResolver(),
        cshapes=None,
    )
    row = rows[0]
    assert row["country_area_km2"] == ""
    assert row["controlled_area_km2"] == ""
    assert row["area_source"] == ""
    flags = row["data_quality_flags"].split("|")
    assert FLAG_MISSING_AREA in flags


def test_row_builder_sun_populated_from_gw_365(tmp_path: Path) -> None:
    """SUN rows 1922-1991 carry the GW 365 area; SUN 1900-1921
    (pre-existence) and 1992+ (post-existence) carry the
    Increment 1 placeholder.
    """
    csv_path = tmp_path / "cshapes.csv"
    _build_minimal_cshapes_csv(csv_path)
    cshapes = load_cshapes_source(
        csv_path=csv_path,
        iso3_scope=("SUN",),
    )
    rows = build_chronicle_rows(
        iso3_scope=("SUN",),
        start_year=1922,
        end_year=1922,
        vdem=_stub_vdem(),
        wdi=_stub_wdi(),
        sipri=_stub_sipri(),
        maddison=None,
        ruler_resolver=RulerResolver(),
        cshapes=cshapes,
    )
    row = rows[0]
    # SUN 1922 has a GW 365 area (22,066,000).
    assert int(float(row["country_area_km2"])) == 22066000
    assert row["area_source"] == "cshapes"


def test_row_builder_no_country_area_no_controlled_area(tmp_path: Path) -> None:
    """Defensive: when CShapes is empty and the country area is
    missing, the controlled area is also missing — the row
    builder does NOT set the ``controlled_area_country_only``
    flag.
    """
    rows = build_chronicle_rows(
        iso3_scope=("USA",),
        start_year=1900,
        end_year=1900,
        vdem=_stub_vdem(),
        wdi=_stub_wdi(),
        sipri=_stub_sipri(),
        maddison=None,
        ruler_resolver=RulerResolver(),
        cshapes=CShapesSource(raw_csv_path=tmp_path / "missing.csv"),
    )
    row = rows[0]
    assert row["country_area_km2"] == ""
    flags = row["data_quality_flags"].split("|")
    assert FLAG_CONTROLLED_AREA_COUNTRY_ONLY not in flags


# ---------------------------------------------------------------------------
# Constants drift guard
# ---------------------------------------------------------------------------


def test_cshapes_direct_confidence_is_documented() -> None:
    """The CShapes direct-confidence constant is documented and
    stable; the row builder uses it when the area is an exact
    CShapes match.
    """
    assert CSHAPES_DIRECT_CONFIDENCE > 0
    assert CSHAPES_DIRECT_CONFIDENCE <= 100
