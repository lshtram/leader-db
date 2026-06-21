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
  resolver returns a missing-ruler result with the
  ``missing_ruler`` flag carried by the row builder.

The :class:`RulerResolver` is the single entry point. It is a
thin layer over three caches (Archigos spells, REIGN leader-months,
SUN curated spells) and the :class:`RulerResult` dataclass. The
raw-file loaders themselves live in :mod:`._ruler_loader` (Archigos
+ REIGN) and :mod:`._sun_ruler_loader` (SUN curated).
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
    SOVIET_LEADERS_DIRECT_CONFIDENCE,
    SOVIET_LEADERS_MULTI_LEADER_CONFIDENCE,
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
    """Resolver for one ``(iso3, year)`` pair using Archigos, REIGN, and SUN curated.

    The resolver caches the source frames (Archigos spells narrowed
    to the pilot ISO3 set, REIGN leader-months narrowed to the
    same, SUN curated spells) so the per-row lookup is O(1) in a
    dict. The class is immutable; instantiate once per runner
    invocation.

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
    """

    archigos_frame: pd.DataFrame = field(default_factory=pd.DataFrame)
    reign_frame: pd.DataFrame = field(default_factory=pd.DataFrame)
    sun_frame: pd.DataFrame = field(default_factory=pd.DataFrame)

    def resolve(self, iso3: str, year: int) -> RulerResult:
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
          - Else :func:`RulerResult.missing`.
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
            hit = self._lookup_archigos(iso3, year)
            if hit is not None:
                return hit

        if (
            not self.reign_frame.empty
            and REIGN_COVERAGE_START_YEAR <= year <= REIGN_COVERAGE_END_YEAR
        ):
            hit = self._lookup_reign(iso3, year)
            if hit is not None:
                return hit

        return RulerResult.missing(source_year_used=year)

    def _lookup_archigos(self, iso3: str, year: int) -> RulerResult | None:
        """Find the Archigos leader for ``(iso3, year)``."""
        start_year = pd.to_datetime(
            self.archigos_frame["startdate"], errors="coerce"
        ).dt.year
        end_year = pd.to_datetime(
            self.archigos_frame["enddate"], errors="coerce"
        ).dt.year
        mask = (
            (self.archigos_frame["iso3"] == iso3)
            & (start_year <= year)
            & (end_year >= year)
        )
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

    def _lookup_reign(self, iso3: str, year: int) -> RulerResult | None:
        """Find the REIGN leader with the most months for ``(iso3, year)``."""
        mask = (
            (self.reign_frame["iso3"] == iso3)
            & (self.reign_frame["year"] == year)
        )
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
) -> RulerResolver:
    """Load Archigos + REIGN + SUN curated into a :class:`RulerResolver`.

    The loader is best-effort: when a source is missing (the raw
    file is not staged or the COW->ISO3 mapping does not cover a
    requested country) the helper logs a warning and returns a
    resolver with an empty frame for that source. The resolver's
    :func:`resolve` method then degrades gracefully (missing ruler).
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
    return RulerResolver(
        archigos_frame=archigos_frame,
        reign_frame=reign_frame,
        sun_frame=sun_frame,
    )


__all__ = [
    "RulerResolver",
    "RulerResult",
    "default_archigos_dta_path",
    "default_reign_csv_path",
    "default_sun_csv_path",
    "load_ruler_resolver",
]
