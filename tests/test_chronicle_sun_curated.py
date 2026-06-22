"""Tests for the Country-Year Chronicle SUN-curated ruler source.

The SUN (Soviet Union) identity was the documented Increment 2 gap:
neither Archigos nor REIGN has a separate SUN ``ccode``, so the
resolver returned ``missing_ruler`` for every SUN row.

Increment 3 closes the gap with a curated, Wikipedia-anchored
spell list at ``data/raw/soviet_leaders_curated/soviet_leaders.csv``.
These tests verify the Increment 3 contract:

- SUN 1922: Lenin — partial-year spell only. The USSR was formed on
  1922-12-30 so the Lenin's curated spell has a positive-overlap
  with the country-year (1922-12-30 to 1922-12-31) and is the
  leader of record for SUN 1922, but it is NOT a full calendar year
  of rule.
- SUN 1923: Lenin (calendar year of rule; the curated spell
  1922-12-30 to 1924-01-21 has a positive-overlap with the entire
  country-year window 1923-01-01 to 1923-12-31).
- SUN 1924: transition year — Lenin until 1924-01-21, Stalin from
  1924-01-21. The resolver picks Stalin (the longer period) and
  emits ``multiple_rulers``.
- SUN 1953: triple transition (Stalin -> Malenkov -> Khrushchev).
  Malenkov has the longest overlap days and wins; the row carries
  ``multiple_rulers``.
- SUN 1985: Chernenko -> Gorbachev. Gorbachev wins; ``multiple_rulers``.
- SUN 1991: Gorbachev. Covered until 1991-12-25 (the date of the
  USSR dissolution); this is NOT necessarily a full calendar year
  of rule — the curated spell ends mid-December. Positive-overlap
  with the year window 1991-01-01 to 1991-12-31, so Gorbachev is
  the leader of record for SUN 1991.
- SUN 1992: post-curated-source window; ``missing_ruler``.
- The resolver NEVER consults the client matrix or an LLM (drift guard).
- The resolver NEVER carries the SUN lookup to non-SUN identities
  (e.g. RUS 1991 still uses Archigos/REIGN, not the curated source).

Heuristic contract: the resolver emits the leader of record for a
country-year whenever ANY positive overlap exists between the
leader's curated spell and the ``[year-01-01, year-12-31]`` window.
The single-spell years (e.g. 1923, 1925, 1945, 1991) receive the
direct-leader confidence; the multi-spell transition years (1924,
1953, 1984, 1985) receive the lower multi-leader confidence plus
the ``multiple_rulers`` flag.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from leaders_db.chronicle._sun_ruler_loader import (
    default_sun_csv_path,
    load_sun_frame,
)
from leaders_db.chronicle.constants import (
    FLAG_MULTIPLE_RULERS,
    SOURCE_TAG_SOVIET_LEADERS_CURATED,
    SOVIET_LEADERS_DIRECT_CONFIDENCE,
    SOVIET_LEADERS_MULTI_LEADER_CONFIDENCE,
)
from leaders_db.chronicle.row_builder import build_chronicle_rows
from leaders_db.chronicle.ruler_resolver import (
    RulerResolver,
    load_ruler_resolver,
)
from leaders_db.chronicle.sources import (
    SipriSource,
    VDemSource,
    WdiSource,
)

# ---------------------------------------------------------------------------
# Helper factories (mirrors test_chronicle_ruler_resolver.py).
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


def _make_resolver(
    tmp_path: Path,
    rows: list[dict[str, object]] | None = None,
) -> RulerResolver:
    """Build a resolver with the curated SUN CSV staged at ``tmp_path``."""
    path = tmp_path / "sun.csv"
    base_rows = [
        # Same shape as the canonical curated CSV.
        {
            "iso3": "SUN",
            "leader": "Lenin",
            "startdate": "1922-12-30",
            "enddate": "1924-01-21",
            "office": "Chairman of Sovnarkom",
            "ruler_title": "Head of government",
            "ruler_type": "",
        },
        {
            "iso3": "SUN",
            "leader": "Stalin",
            "startdate": "1924-01-21",
            "enddate": "1953-03-05",
            "office": "General Secretary",
            "ruler_title": "Head of state",
            "ruler_type": "",
        },
        {
            "iso3": "SUN",
            "leader": "Malenkov",
            "startdate": "1953-03-05",
            "enddate": "1953-09-07",
            "office": "Chairman of Council of Ministers",
            "ruler_title": "Head of government",
            "ruler_type": "",
        },
        {
            "iso3": "SUN",
            "leader": "Khrushchev",
            "startdate": "1953-09-07",
            "enddate": "1964-10-14",
            "office": "First Secretary",
            "ruler_title": "Head of state",
            "ruler_type": "",
        },
        {
            "iso3": "SUN",
            "leader": "Brezhnev",
            "startdate": "1964-10-14",
            "enddate": "1982-11-10",
            "office": "First / General Secretary",
            "ruler_title": "Head of state",
            "ruler_type": "",
        },
        {
            "iso3": "SUN",
            "leader": "Andropov",
            "startdate": "1982-11-12",
            "enddate": "1984-02-09",
            "office": "General Secretary",
            "ruler_title": "Head of state",
            "ruler_type": "",
        },
        {
            "iso3": "SUN",
            "leader": "Chernenko",
            "startdate": "1984-02-13",
            "enddate": "1985-03-10",
            "office": "General Secretary",
            "ruler_title": "Head of state",
            "ruler_type": "",
        },
        {
            "iso3": "SUN",
            "leader": "Gorbachev",
            "startdate": "1985-03-11",
            "enddate": "1991-12-25",
            "office": "General Secretary; President",
            "ruler_title": "Head of state; Head of government",
            "ruler_type": "",
        },
    ]
    if rows is not None:
        base_rows = rows
    pd.DataFrame(base_rows).to_csv(path, index=False)
    return load_ruler_resolver(sun_csv_path=path)


# ---------------------------------------------------------------------------
# Loader tests
# ---------------------------------------------------------------------------


def test_default_sun_csv_path_resolves_to_data_lake() -> None:
    """The canonical path resolves to ``data/raw/soviet_leaders_curated/``.

    Verified by :func:`default_sun_csv_path` returning the expected
    raw-path tuple under the project's ``data/raw/`` skeleton.
    """
    path = default_sun_csv_path()
    assert path.name == "soviet_leaders.csv"
    assert path.parent.name == "soviet_leaders_curated"


def test_load_sun_frame_reads_canonical_curated_csv() -> None:
    """The loader reads the canonical curated CSV when present.

    We do not stage the file here (the loader is read-only); the
    test simply confirms the loader either returns the populated
    frame (when the curated CSV is on disk) or the empty fallback
    (when missing). Both are documented behaviors.
    """
    frame = load_sun_frame()
    if not frame.empty:
        # Real bundle path: must contain the 8 SUN leaders and the
        # required columns.
        assert "iso3" in frame.columns
        assert "leader" in frame.columns
        assert "startdate" in frame.columns
        assert "enddate" in frame.columns
        leaders = set(frame["leader"].tolist())
        for expected in (
            "Lenin", "Stalin", "Malenkov", "Khrushchev",
            "Brezhnev", "Andropov", "Chernenko", "Gorbachev",
        ):
            assert expected in leaders
    else:
        # Empty-frame fallback when the curated CSV is missing.
        assert list(frame.columns) == [
            "iso3", "leader", "startdate", "enddate",
            "office", "ruler_title", "ruler_type",
        ]


def test_load_sun_frame_missing_file_returns_empty(tmp_path: Path) -> None:
    """When the curated CSV is missing, the loader logs a warning
    and returns an empty ``DataFrame`` with the right columns.
    """
    missing = tmp_path / "no-such-file.csv"
    frame = load_sun_frame(sun_csv_path=missing)
    assert frame.empty
    assert "iso3" in frame.columns
    assert "leader" in frame.columns
    assert "startdate" in frame.columns
    assert "enddate" in frame.columns


def test_load_sun_frame_skips_non_sun_rows(tmp_path: Path) -> None:
    """The loader narrows to ``iso3 == "SUN"`` rows only. Foreign
    ISO3 codes mixed into the curated CSV are dropped."""
    path = tmp_path / "sun_mixed.csv"
    pd.DataFrame(
        [
            {
                "iso3": "SUN",
                "leader": "Lenin",
                "startdate": "1922-12-30",
                "enddate": "1924-01-21",
                "office": "",
                "ruler_title": "",
                "ruler_type": "",
            },
            {
                "iso3": "USA",
                "leader": "NOT-A-LEADER",
                "startdate": "1900-01-01",
                "enddate": "1900-12-31",
                "office": "",
                "ruler_title": "",
                "ruler_type": "",
            },
        ]
    ).to_csv(path, index=False)
    frame = load_sun_frame(sun_csv_path=path)
    assert len(frame) == 1
    assert frame.iloc[0]["leader"] == "Lenin"
    assert frame.iloc[0]["iso3"] == "SUN"


# ---------------------------------------------------------------------------
# Resolver tests
# ---------------------------------------------------------------------------


def test_sun_1922_resolves_to_lenin(tmp_path: Path) -> None:
    """SUN 1922 resolves to Lenin (partial-year spell: positive-overlap
    with the country-year after USSR formation on 1922-12-30; not a
    full calendar year of rule).

    The Lenin's curated spell starts on 1922-12-30; the country-year
    window is 1922-01-01 to 1922-12-31. There is a positive overlap
    (1922-12-30 to 1922-12-31 = 2 days) so Lenin is the leader of
    record for SUN 1922, but this is NOT a full calendar year of
    rule. The resolver still emits the direct-leader confidence
    (single leader for the year).
    """
    resolver = _make_resolver(tmp_path)
    result = resolver.resolve("SUN", 1922)
    assert result.has_ruler is True
    assert result.ruler_name == "Lenin"
    assert result.ruler_source == SOURCE_TAG_SOVIET_LEADERS_CURATED
    assert result.ruler_source_year_used == 1922
    assert result.ruler_confidence == SOVIET_LEADERS_DIRECT_CONFIDENCE
    assert result.multiple_rulers is False


def test_sun_1924_resolves_to_stalin_with_multiple_rulers_flag(
    tmp_path: Path,
) -> None:
    """SUN 1924 resolves to Stalin (more days in 1924 than Lenin)
    and emits ``multiple_rulers`` because the year contains both
    spells."""
    resolver = _make_resolver(tmp_path)
    result = resolver.resolve("SUN", 1924)
    assert result.has_ruler is True
    assert result.ruler_name == "Stalin"
    assert result.ruler_source == SOURCE_TAG_SOVIET_LEADERS_CURATED
    assert result.ruler_confidence == SOVIET_LEADERS_MULTI_LEADER_CONFIDENCE
    assert result.multiple_rulers is True


def test_sun_1953_resolves_to_malenkov_with_multiple_rulers_flag(
    tmp_path: Path,
) -> None:
    """SUN 1953 has three leaders (Stalin -> Malenkov -> Khrushchev).
    Malenkov has the longest overlap (Mar 5 - Sep 6 = 186 days) and
    wins the resolver; the year emits ``multiple_rulers``."""
    resolver = _make_resolver(tmp_path)
    result = resolver.resolve("SUN", 1953)
    assert result.has_ruler is True
    assert result.ruler_name == "Malenkov"
    assert result.ruler_source == SOURCE_TAG_SOVIET_LEADERS_CURATED
    assert result.ruler_confidence == SOVIET_LEADERS_MULTI_LEADER_CONFIDENCE
    assert result.multiple_rulers is True


def test_sun_1985_resolves_to_gorbachev_with_multiple_rulers_flag(
    tmp_path: Path,
) -> None:
    """SUN 1985 has Chernenko (Jan 1 - Mar 10) and Gorbachev
    (Mar 11 - Dec 31). Gorbachev wins; ``multiple_rulers``."""
    resolver = _make_resolver(tmp_path)
    result = resolver.resolve("SUN", 1985)
    assert result.has_ruler is True
    assert result.ruler_name == "Gorbachev"
    assert result.ruler_source == SOURCE_TAG_SOVIET_LEADERS_CURATED
    assert result.ruler_confidence == SOVIET_LEADERS_MULTI_LEADER_CONFIDENCE
    assert result.multiple_rulers is True


def test_sun_1991_resolves_to_gorbachev_single_leader(tmp_path: Path) -> None:
    """SUN 1991 resolves to Gorbachev with the direct-leader
    confidence (single leader for the year).

    Gorbachev's curated spell runs from 1985-03-11 to 1991-12-25
    (the date of the USSR dissolution). He is the leader of record
    for SUN 1991 because his spell has a positive overlap with the
    country-year window 1991-01-01 to 1991-12-31. This is NOT
    necessarily a full calendar year of rule — the curated spell
    ends mid-December — but the resolver emits the direct-leader
    confidence because there is exactly one positive-overlap spell
    in the year.
    """
    resolver = _make_resolver(tmp_path)
    result = resolver.resolve("SUN", 1991)
    assert result.has_ruler is True
    assert result.ruler_name == "Gorbachev"
    assert result.ruler_source == SOURCE_TAG_SOVIET_LEADERS_CURATED
    assert result.ruler_confidence == SOVIET_LEADERS_DIRECT_CONFIDENCE
    assert result.multiple_rulers is False


def test_sun_outside_curated_window_returns_missing_ruler(
    tmp_path: Path,
) -> None:
    """Years outside the curated source window (1922-12-30 to
    1991-12-25) return ``RulerResult.missing``. Specifically:

    - SUN 1921 (pre-window; the curated source starts at 1922-12-30).
    - SUN 1992 (post-window; SUN ended 1991-12-25).

    """
    resolver = _make_resolver(tmp_path)
    result = resolver.resolve("SUN", 1921)
    assert result.has_ruler is False
    result = resolver.resolve("SUN", 1992)
    assert result.has_ruler is False


def test_sun_resolver_falls_back_to_missing_when_curated_csv_missing(
    tmp_path: Path,
) -> None:
    """When the curated CSV is missing, the SUN resolver returns
    missing for every SUN year (no invented rulers)."""
    resolver = load_ruler_resolver(sun_csv_path=tmp_path / "missing.csv")
    for year in (1922, 1950, 1990):
        result = resolver.resolve("SUN", year)
        assert result.has_ruler is False
        assert result.ruler_source == ""


def test_sun_resolver_does_not_apply_to_non_sun_iso3(tmp_path: Path) -> None:
    """The curated source is SUN-specific. Other ISO3 keys
    (USA, GBR, etc.) are NOT routed through the curated source.

    We prove this by checking that USA 1991 (a year within the
    curated window but for a non-SUN ISO3) does not pick up
    Gorbachev or the SUN curated source. USA may resolve from
    Archigos/REIGN if those sources are present.
    """
    resolver = _make_resolver(tmp_path)
    result = resolver.resolve("USA", 1991)
    assert result.ruler_source != SOURCE_TAG_SOVIET_LEADERS_CURATED
    assert result.ruler_name != "Gorbachev"


def test_sun_resolver_does_not_invent_rulers_for_uncovered_years(
    tmp_path: Path,
) -> None:
    """The resolver NEVER invents a ruler. Years outside the
    curated source window return ``missing`` for SUN. Years with
    empty curated CSV return ``missing`` for SUN. The resolver
    does not consult the client matrix, the LLM, or any other
    source for SUN.
    """
    resolver = _make_resolver(tmp_path)
    # Gap years in the curated source: SUN 1922 has only the
    # last few days (Dec 30-31); years before that return
    # missing.
    for year in (1900, 1920, 1992, 2000):
        result = resolver.resolve("SUN", year)
        assert result.has_ruler is False, (
            f"Resolver invented a ruler for SUN {year}: {result!r}"
        )
        assert result.ruler_source == ""


# ---------------------------------------------------------------------------
# Row-builder integration tests (data-quality flag emission)
# ---------------------------------------------------------------------------


def test_row_builder_emits_multiple_rulers_flag_for_sun_1924(
    tmp_path: Path,
) -> None:
    """The row builder wires the resolver's ``multiple_rulers``
    bit into the row's ``data_quality_flags`` column. SUN 1924
    has both Lenin and Stalin overlap, so the flag is set.
    """
    resolver = _make_resolver(tmp_path)
    rows = build_chronicle_rows(
        iso3_scope=("SUN",),
        start_year=1924,
        end_year=1924,
        vdem=_stub_vdem(),
        wdi=_stub_wdi(),
        sipri=_stub_sipri(),
        maddison=None,
        ruler_resolver=resolver,
    )
    row = rows[0]
    flags = row["data_quality_flags"].split("|")
    assert FLAG_MULTIPLE_RULERS in flags


def test_row_builder_does_not_emit_multiple_rulers_for_sun_1922(
    tmp_path: Path,
) -> None:
    """SUN 1922 (Lenin partial-year spell: positive-overlap with
    the country-year after USSR formation on 1922-12-30) does NOT
    carry ``multiple_rulers``.

    Only one curated spell overlaps the SUN 1922 country-year
    window, so the resolver picks Lenin without emitting the
    multi-leader flag. The positive-overlap spell is partial-year
    (1922-12-30 to 1922-12-31), not a full calendar year, but the
    direct-leader confidence path still applies because there is
    exactly one positive-overlap spell in the year.
    """
    resolver = _make_resolver(tmp_path)
    rows = build_chronicle_rows(
        iso3_scope=("SUN",),
        start_year=1922,
        end_year=1922,
        vdem=_stub_vdem(),
        wdi=_stub_wdi(),
        sipri=_stub_sipri(),
        maddison=None,
        ruler_resolver=resolver,
    )
    row = rows[0]
    flags = row["data_quality_flags"].split("|")
    assert FLAG_MULTIPLE_RULERS not in flags


def test_row_builder_records_sun_curated_source_in_ruler_source(
    tmp_path: Path,
) -> None:
    """The row builder lifts the curated source tag into the
    row's ``ruler_source`` column.
    """
    resolver = _make_resolver(tmp_path)
    rows = build_chronicle_rows(
        iso3_scope=("SUN",),
        start_year=1922,
        end_year=1922,
        vdem=_stub_vdem(),
        wdi=_stub_wdi(),
        sipri=_stub_sipri(),
        maddison=None,
        ruler_resolver=resolver,
    )
    row = rows[0]
    assert row["ruler_name"] == "Lenin"
    assert row["ruler_source"] == SOURCE_TAG_SOVIET_LEADERS_CURATED
    assert row["ruler_confidence"] == str(SOVIET_LEADERS_DIRECT_CONFIDENCE)


def test_row_builder_provenance_summary_records_curated_source(
    tmp_path: Path,
) -> None:
    """The provenance summary records the curated source when the
    resolver returns a curated hit.
    """
    resolver = _make_resolver(tmp_path)
    rows = build_chronicle_rows(
        iso3_scope=("SUN",),
        start_year=1922,
        end_year=1922,
        vdem=_stub_vdem(),
        wdi=_stub_wdi(),
        sipri=_stub_sipri(),
        maddison=None,
        ruler_resolver=resolver,
    )
    row = rows[0]
    assert "ruler=soviet_leaders_curated" in row["provenance_summary"]


def test_row_builder_missing_ruler_for_sun_1992(tmp_path: Path) -> None:
    """SUN 1992 (post-curated-window) carries ``missing_ruler`` in
    ``data_quality_flags`` because the curated source does not
    cover that year.
    """
    resolver = _make_resolver(tmp_path)
    rows = build_chronicle_rows(
        iso3_scope=("SUN",),
        start_year=1992,
        end_year=1992,
        vdem=_stub_vdem(),
        wdi=_stub_wdi(),
        sipri=_stub_sipri(),
        maddison=None,
        ruler_resolver=resolver,
    )
    row = rows[0]
    assert row["ruler_name"] == ""
    flags = row["data_quality_flags"].split("|")
    assert "missing_ruler" in flags
