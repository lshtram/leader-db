"""Ruler resolver for the Country-Year Chronicle slice.

This module owns the narrow read-only ruler resolver used by the
Increment 2 / Increment 3 row builder. It deliberately does NOT
use the client matrix or the LLM (per Always-On Rule #6 and the
explicit Increment 2 contract).

Sources used:

- Archigos v4.1 (Goemans, Gleditsch, and Chiozza 2009) for
  ``(countrycode, year)`` leader-spell records through 2015.
  Archigos is the canonical historical ruler source; we read the
  raw ``.dta`` file once and narrow to the pilot ISO3 set.
- REIGN 2021-8 (Bell 2016, OEF Research) for monthly leader
  records 1950-2021. REIGN is the canonical recent ruler source;
  the resolver picks the leader with the most months in the
  requested year (the REIGN frame has one row per
  ``(ccode, year, month)`` triple).
- Soviet leaders (curated, Wikipedia-anchored) — Increment 3.
  A small static, versioned CSV at
  ``data/raw/soviet_leaders_curated/soviet_leaders.csv`` carries
  the documented spell list for the Soviet Union identity
  (Lenin, Stalin, Malenkov, Khrushchev, Brezhnev, Andropov,
  Chernenko, Gorbachev, 1922-12-30 to 1991-12-25). The SUN
  resolver picks the leader with the most days in the requested
  year; transition years (1924, 1953, 1985) emit
  ``multiple_rulers``.
- Wikidata recent-rulers fallback — 2022-2026 (and any later
  years). Archigos ends 2015 and REIGN ends 2021; the prototype
  fills the 2022-2026 gap via a Wikidata SPARQL query against
  the WikiProject Heads of state and government endpoint. The
  Wikidata frame is the lowest-precedence source: Archigos and
  REIGN rows are NEVER overridden for the years they cover.

Per Increment 2 / Increment 3 contract:

- For SUN rows: prefer the curated source. If empty, fall back
  to missing (the resolver never invents a SUN ruler).
- For ``year <= 2015``: prefer Archigos when available. Fall back
  to REIGN. Archigos wins for pre-1950 years (REIGN starts in
  1950).
- For ``year`` in ``1950..2021``: prefer REIGN (the recent
  monthly record is more accurate than Archigos's leader-spell
  representation).
- For ``year > 2021``: both Archigos and REIGN have no data; the
  resolver consults the Wikidata recent-rulers frame as the
  documented fallback (per Increment 6 — 2022-2026 ruler
  coverage). If the Wikidata frame is empty (cache miss and
  network unreachable) the resolver returns the missing-ruler
  placeholder.

The :class:`RulerResolver` is the single entry point. It is a
thin layer over four caches (Archigos spells, REIGN leader-months,
SUN curated spells, Wikidata recent-rulers long frame) and the
:class:`RulerResult` dataclass. The raw-file loaders themselves
live in :mod:`._ruler_loader` (Archigos + REIGN),
:mod:`._sun_ruler_loader` (SUN curated), and
:mod:`._wikidata_recent_rulers` (Wikidata recent-rulers adapter).
    """

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pandas as pd

from ._ruler_loader import (
    default_archigos_dta_path,
    default_reign_csv_path,
    load_archigos_frame,
    load_reign_frame,
)
from ._sun_ruler_loader import (
    default_sun_csv_path,
    load_sun_frame,
)
from ._wikidata_recent_rulers import (
    WikidataRecentRulersSource,
    load_wikidata_recent_rulers_source,
)
from .constants import SOURCE_NA
from .source_constants import (
    ARCHIGOS_COVERAGE_END_YEAR,
    ARCHIGOS_DIRECT_CONFIDENCE,
    REIGN_COVERAGE_END_YEAR,
    REIGN_COVERAGE_START_YEAR,
    REIGN_DIRECT_CONFIDENCE,
    REIGN_MULTI_LEADER_CONFIDENCE,
    SOURCE_TAG_ARCHIGOS,
    SOURCE_TAG_REIGN,
    SOURCE_TAG_SOVIET_LEADERS_CURATED,
    SOURCE_TAG_WIKIDATA_RECENT_RULERS,
    SOVIET_LEADERS_DIRECT_CONFIDENCE,
    SOVIET_LEADERS_MULTI_LEADER_CONFIDENCE,
    WIKIDATA_RECENT_RULERS_DIRECT_CONFIDENCE,
)

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RulerResult:
    """The resolver's output for one ``(iso3, year)`` pair.

    The fields map directly to the chronicle CSV columns:
    ``ruler_name``, ``ruler_title``, ``ruler_type``, ``ruler_source``,
    ``ruler_source_year_used``, ``ruler_confidence``. The two flag
    fields (``has_ruler``, ``multiple_rulers``) are not part of the
    CSV; the row builder uses them to drive the
    ``missing_ruler`` / ``multiple_rulers`` data-quality flags.
    """

    ruler_name: str
    ruler_title: str
    ruler_type: str
    ruler_source: str
    ruler_source_year_used: int
    ruler_confidence: int
    has_ruler: bool
    multiple_rulers: bool

    @staticmethod
    def missing(*, source_year_used: int = 0) -> RulerResult:
        """Return the canonical "no ruler resolved" placeholder."""
        return RulerResult(
            ruler_name="",
            ruler_title="",
            ruler_type="",
            ruler_source=SOURCE_NA,
            ruler_source_year_used=source_year_used,
            ruler_confidence=0,
            has_ruler=False,
            multiple_rulers=False,
        )


# ---------------------------------------------------------------------------
# Ruler resolver
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RulerResolver:
    """Resolve one ``(iso3, year)`` pair from ruler source frames.

    The resolver caches the source frames (Archigos spells narrowed
    to the pilot ISO3 set, REIGN leader-months narrowed to the
    same, SUN curated spells, Wikidata recent-rulers long frame)
    so the per-row lookup is O(1) in a dict. The class is
    immutable; instantiate once per runner invocation.

    Attributes:
        archigos_frame: ``pd.DataFrame`` with columns ``iso3``,
            ``leader``, ``startdate``, ``enddate`` for the pilot
            ISO3 set. Empty if the raw Archigos dta is missing.
        reign_frame: ``pd.DataFrame`` with columns ``iso3``,
            ``year``, ``month``, ``leader``, ``government`` for
            the pilot ISO3 set. Empty if the raw REIGN csv is
            missing.
        sun_frame: ``pd.DataFrame`` with columns ``iso3``,
            ``leader``, ``startdate``, ``enddate``, ``office``,
            ``ruler_title``, ``ruler_type`` for the Soviet Union
            identity. Empty if the raw curated CSV is missing.
        wikidata_recent_source: Optional :class:`WikidataRecentRulersSource`
            for the 2022-2026 (and later) fallback. ``None``
            disables the fallback (the resolver then returns
            missing for any year past REIGN coverage). When the
            source's frame is empty (network failure, no cache),
            the resolver still degrades to missing.
    """

    archigos_frame: pd.DataFrame = field(default_factory=pd.DataFrame)
    reign_frame: pd.DataFrame = field(default_factory=pd.DataFrame)
    sun_frame: pd.DataFrame = field(default_factory=pd.DataFrame)
    wikidata_recent_source: WikidataRecentRulersSource | None = None

    def resolve(self, iso3: str, year: int, *, cowcode: int | None = None) -> RulerResult:
        """Resolve the ruler for ``(iso3, year)``.

        Returns a :class:`RulerResult`. The helper honours the
        documented precedence:

        - For ``iso3 == "SUN"``: prefer the curated source. The
          curated source covers 1922-12-30 to 1991-12-25 with
          documented transition dates; years outside that window
          return missing.
        - For other ISO3 keys:
          - Archigos when ``year <= ARCHIGOS_COVERAGE_END_YEAR``
            and a record matches.
          - REIGN when ``REIGN_COVERAGE_START_YEAR <= year <=
            REIGN_COVERAGE_END_YEAR`` and a record matches.
          - Wikidata recent-rulers fallback when ``year >
            REIGN_COVERAGE_END_YEAR`` (the 2022-2026 gap) and the
            frame has a matching ``(iso3, year)`` row.
          - Else :func:`RulerResult.missing`.

        The Wikidata fallback is the LOWEST-precedence source;
        Archigos and REIGN rows are NEVER overridden for the years
        they cover, and SUN rows bypass Wikidata entirely (SUN
        is a curated-only identity).
        """
        if iso3 == "SUN":
            hit = self._lookup_sun(year)
            if hit is not None:
                return hit
            return RulerResult.missing(source_year_used=year)

        if (
            not self.archigos_frame.empty
            and year <= ARCHIGOS_COVERAGE_END_YEAR
        ):
            hit = self._lookup_archigos(iso3, year, cowcode=cowcode)
            if hit is not None:
                return hit

        if (
            not self.reign_frame.empty
            and REIGN_COVERAGE_START_YEAR <= year <= REIGN_COVERAGE_END_YEAR
        ):
            hit = self._lookup_reign(iso3, year, cowcode=cowcode)
            if hit is not None:
                return hit

        if (
            self.wikidata_recent_source is not None
            and not self.wikidata_recent_source.is_empty
            and year > REIGN_COVERAGE_END_YEAR
        ):
            hit = self._lookup_wikidata_recent(iso3, year)
            if hit is not None:
                return hit

        return RulerResult.missing(source_year_used=year)

    def _lookup_archigos(
        self, iso3: str, year: int, *, cowcode: int | None = None
    ) -> RulerResult | None:
        """Find the Archigos leader for ``(iso3, year)``."""
        start_year = pd.to_datetime(
            self.archigos_frame["startdate"], errors="coerce"
        ).dt.year
        end_year = pd.to_datetime(
            self.archigos_frame["enddate"], errors="coerce"
        ).dt.year
        if cowcode is not None and "ccode" in self.archigos_frame.columns:
            country_mask = self.archigos_frame["ccode"] == cowcode
        else:
            country_mask = self.archigos_frame["iso3"] == iso3
        mask = country_mask & (start_year <= year) & (end_year >= year)
        matches = self.archigos_frame.loc[mask]
        if matches.empty:
            return None
        # Deterministic tie-break: pick the earliest startdate.
        row = matches.sort_values("startdate").iloc[0]
        leader = str(row["leader"]).strip()
        if not leader:
            return None
        return RulerResult(
            ruler_name=leader,
            ruler_title="",  # Archigos does not carry titles
            ruler_type="",  # Archigos does not carry government type
            ruler_source=SOURCE_TAG_ARCHIGOS,
            ruler_source_year_used=year,
            ruler_confidence=ARCHIGOS_DIRECT_CONFIDENCE,
            has_ruler=True,
            multiple_rulers=False,
        )

    def _lookup_reign(
        self, iso3: str, year: int, *, cowcode: int | None = None
    ) -> RulerResult | None:
        """Find the REIGN leader with the most months for ``(iso3, year)``."""
        if cowcode is not None and "ccode" in self.reign_frame.columns:
            country_mask = self.reign_frame["ccode"] == cowcode
        else:
            country_mask = self.reign_frame["iso3"] == iso3
        mask = country_mask & (self.reign_frame["year"] == year)
        rows = self.reign_frame.loc[mask]
        if rows.empty:
            return None
        leader_counts = rows.groupby("leader").size().sort_values(ascending=False)
        if leader_counts.empty:
            return None
        leader = str(leader_counts.index[0])
        multiple_rulers = len(leader_counts) > 1
        # Pick the most common government string for this leader
        # in the year (REIGN sometimes has multiple governments
        # in a year).
        gov_rows = rows.loc[rows["leader"] == leader, "government"].dropna()
        ruler_type = ""
        if not gov_rows.empty:
            ruler_type = str(gov_rows.mode().iloc[0])
        confidence = (
            REIGN_DIRECT_CONFIDENCE if not multiple_rulers
            else REIGN_MULTI_LEADER_CONFIDENCE
        )
        return RulerResult(
            ruler_name=leader,
            ruler_title="",  # REIGN does not carry titles
            ruler_type=ruler_type,
            ruler_source=SOURCE_TAG_REIGN,
            ruler_source_year_used=year,
            ruler_confidence=confidence,
            has_ruler=True,
            multiple_rulers=multiple_rulers,
        )

    def _lookup_wikidata_recent(
        self, iso3: str, year: int
    ) -> RulerResult | None:
        """Find the Wikidata recent-rulers holder for ``(iso3, year)``.

        The lookup delegates to
        :class:`WikidataRecentRulersSource.resolve`, which applies
        the documented office-precedence tie-break (head of
        government > head of state) and the start-date / person-
        label tie-break. Returns ``None`` when the source has no
        matching row so the resolver's fallback chain can keep
        searching.
        """
        source = self.wikidata_recent_source
        if source is None or source.is_empty:
            return None
        hit = source.resolve(iso3, year)
        if hit is None:
            return None
        person_label = hit.get("person_label", "").strip()
        if not person_label:
            return None
        office_label = hit.get("office_label", "").strip()
        return RulerResult(
            ruler_name=person_label,
            ruler_title=office_label,
            ruler_type="",  # Wikidata office_label IS the title
            ruler_source=SOURCE_TAG_WIKIDATA_RECENT_RULERS,
            ruler_source_year_used=year,
            ruler_confidence=WIKIDATA_RECENT_RULERS_DIRECT_CONFIDENCE,
            has_ruler=True,
            multiple_rulers=False,
        )

    def _lookup_sun(self, year: int) -> RulerResult | None:
        """Find the SUN curated leader with the most days for ``year``.

        The helper intersects each spell's ``[startdate, enddate]``
        range with ``[year-01-01, year-12-31]`` and picks the leader
        with the most overlap days. When the year contains more than
        one spell (e.g. 1924 Lenin->Stalin, 1953
        Stalin->Malenkov->Khrushchev, 1985 Chernenko->Gorbachev) the
        helper emits ``multiple_rulers=True`` and the lower
        :data:`SOVIET_LEADERS_MULTI_LEADER_CONFIDENCE` confidence.
        """
        if self.sun_frame.empty:
            return None
        start = pd.to_datetime(self.sun_frame["startdate"], errors="coerce")
        end = pd.to_datetime(self.sun_frame["enddate"], errors="coerce")
        # Drop rows whose dates did not parse.
        valid = start.notna() & end.notna()
        frame = self.sun_frame.loc[valid].copy()
        if frame.empty:
            return None
        start = start.loc[valid]
        end = end.loc[valid]
        year_start = pd.Timestamp(year=year, month=1, day=1)
        year_end = pd.Timestamp(year=year, month=12, day=31)
        overlap_start = start.clip(lower=year_start)
        overlap_end = end.clip(upper=year_end)
        days = (overlap_end - overlap_start).dt.days + 1
        positive = days > 0
        if not positive.any():
            return None
        frame = frame.loc[positive].copy()
        days = days.loc[positive]
        # Pick the leader with the most days; tie-break by earlier
        # startdate for determinism.
        sorted_idx = days.sort_values(ascending=False).index
        if len(sorted_idx) == 0:
            return None
        leaders = frame.loc[sorted_idx].copy()
        leaders["__days"] = days.loc[sorted_idx]
        # The leader of record is the one with the most days.
        top_row = leaders.sort_values(
            ["__days", "startdate"], ascending=[False, True]
        ).iloc[0]
        leader = str(top_row["leader"]).strip()
        if not leader:
            return None
        # Multi-leader years: any year where two or more leaders have
        # positive overlap days (i.e. a transition happened).
        unique_leaders = leaders["leader"].nunique()
        multiple_rulers = bool(unique_leaders > 1)
        confidence = (
            SOVIET_LEADERS_DIRECT_CONFIDENCE
            if not multiple_rulers
            else SOVIET_LEADERS_MULTI_LEADER_CONFIDENCE
        )
        ruler_title = self._clean_text(top_row.get("ruler_title", ""))
        ruler_type = self._clean_text(top_row.get("ruler_type", ""))
        return RulerResult(
            ruler_name=leader,
            ruler_title=ruler_title,
            ruler_type=ruler_type,
            ruler_source=SOURCE_TAG_SOVIET_LEADERS_CURATED,
            ruler_source_year_used=year,
            ruler_confidence=confidence,
            has_ruler=True,
            multiple_rulers=multiple_rulers,
        )

    @staticmethod
    def _clean_text(value: object) -> str:
        """Coerce a cell value to its CSV-string representation.

        ``None``, ``NaN``, ``float('nan')``, and empty strings
        become ``""``; other values pass through ``str()``. Used for
        the optional SUN row columns ``ruler_title`` / ``ruler_type``
        so a missing value never emits the literal ``"nan"``.
        """
        if value is None:
            return ""
        try:
            import math

            if isinstance(value, float) and math.isnan(value):
                return ""
        except TypeError:
            pass
        text = str(value).strip()
        return "" if text == "nan" else text


# ---------------------------------------------------------------------------
# Loader facade
# ---------------------------------------------------------------------------


def load_ruler_resolver(
    *,
    archigos_dta_path=None,
    reign_csv_path=None,
    sun_csv_path=None,
    iso3_scope: tuple[str, ...] = (),
    wikidata_recent_years: tuple[int, ...] = (),
    wikidata_recent_cache_dir=None,
    wikidata_recent_force_refresh: bool = False,
    wikidata_recent_timeout: float = 60.0,
) -> RulerResolver:
    """Load Archigos + REIGN + SUN curated + Wikidata recent-rulers.

    The loader is best-effort: when a source is missing the helper
    logs a warning and returns a resolver with an empty frame for
    that source. The resolver's :func:`resolve` method then
    degrades gracefully (missing ruler).

    Args:
        archigos_dta_path: Override path for the Archigos raw
            ``.dta`` file.
        reign_csv_path: Override path for the REIGN raw CSV.
        sun_csv_path: Override path for the Soviet leaders
            curated CSV.
        iso3_scope: Tuple of ISO3 keys the Archigos + REIGN frames
            should be narrowed to. SUN curated is not narrowed
            (it only carries SUN).
        wikidata_recent_years: Tuple of calendar years for which
            the resolver should consult the Wikidata fallback.
            Empty (the default) disables the fallback entirely so
            older callers see no behaviour change. The CLI passes
            every year past REIGN coverage so the fallback fires
            for 2022-2026 (and any later year the user asks for).
        wikidata_recent_cache_dir: Override cache directory for
            the Wikidata SPARQL JSON cache.
        wikidata_recent_force_refresh: When ``True``, re-download
            the SPARQL JSON even when a cache file exists.
            Defaults to ``False`` (cache-first, HTTP-fallback).
        wikidata_recent_timeout: Per-request HTTP timeout in
            seconds. Defaults to 60s.

    When a source is missing (the raw file is not staged, the
    COW->ISO3 mapping does not cover a requested country, the
    SPARQL endpoint is unreachable) the helper logs a warning
    and returns a resolver with an empty frame for that source.
    The resolver's :func:`resolve` method then degrades gracefully
    (missing ruler).
"""
    iso3_set = set(iso3_scope)
    archigos_frame = load_archigos_frame(
        archigos_dta_path=archigos_dta_path,
        iso3_scope=iso3_set,
    )
    reign_frame = load_reign_frame(
        reign_csv_path=reign_csv_path,
        iso3_scope=iso3_set,
    )
    sun_frame = load_sun_frame(sun_csv_path=sun_csv_path)
    wikidata_recent_source: WikidataRecentRulersSource | None = None
    if wikidata_recent_years:
        wikidata_recent_source = load_wikidata_recent_rulers_source(
            years=tuple(int(y) for y in wikidata_recent_years),
            cache_dir=wikidata_recent_cache_dir,
            force_refresh=wikidata_recent_force_refresh,
            timeout=wikidata_recent_timeout,
        )
    return RulerResolver(
        archigos_frame=archigos_frame,
        reign_frame=reign_frame,
        sun_frame=sun_frame,
        wikidata_recent_source=wikidata_recent_source,
    )


__all__ = [
    "RulerResolver",
    "RulerResult",
    "default_archigos_dta_path",
    "default_reign_csv_path",
    "default_sun_csv_path",
    "load_ruler_resolver",
]
