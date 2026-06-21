"""CShapes 2.0 raw-file loader for the Country-Year Chronicle slice.

This module owns the data-lake file reader that supplies the
``country_area_km2`` column for the Chronicle slice. CShapes 2.0
(Schvitz et al. 2022) is the canonical historical country-area
source for the prototype: it provides per-country-area (km^2) by
``(gwcode, gwsyear, gweyear)`` for the Gleditsch-Ward state system
from 1886 to 2019.

Two derived accessors are exposed:

- :class:`CShapesSource` — an in-memory narrow frame of the pilot
  country-year rows, keyed by ``(iso3, year)`` lookups.
- :func:`default_cshapes_csv_path` — the canonical raw CSV path
  inside the data lake.

The CSV columns we use are:

    ``cntry_name``, ``area`` (km^2), ``gwcode``, ``gwsyear``,
    ``gweyear``.

The Chronicle-side resolver picks the CShapes row whose
``gwsyear <= year <= gweyear`` for the ISO3's mapped GW code. Years
beyond CShapes coverage (2020+) carry the ``area_proxy_year_used``
flag (the resolver copies the most recent available CShapes row
and emits the proxy-year tag).

The module is split out of ``row_builder.py`` to keep that file
focused on row composition logic and under the 400-line convention.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from ..paths import raw_dir
from .source_constants import CSHAPES_GW_TO_ISO3, CSHAPES_GW_YEAR_TO_ISO3

_logger = logging.getLogger(__name__)


def default_cshapes_csv_path() -> Path:
    """Return the canonical CShapes raw CSV path inside the data lake."""
    return raw_dir("cshapes") / "CShapes-2.0.csv"


def _read_cshapes_csv(csv_path: Path) -> pd.DataFrame:
    """Read the raw CShapes 2.0 CSV.

    The CSV carries ``the_geom`` and ``cap_geom`` WKT columns with
    large polygons; we drop those columns at read time to keep the
    in-memory footprint small (the area column is what the Chronicle
    needs). ``gwsyear`` / ``gweyear`` are cast to ``int`` so the
    per-row lookup is O(1) in a sorted index.
    """
    usecols = ["cntry_name", "area", "gwcode", "gwsyear", "gweyear"]
    # The CSV has a comma-delimited ``the_geom`` WKT that can contain
    # commas inside ``MULTIPOLYGON`` parentheses; pyarrow's CSV engine
    # does not handle that well, but the legacy ``c`` engine does
    # because the WKT is quoted. The default engine is ``c`` in
    # modern pandas, which works.
    df = pd.read_csv(csv_path, usecols=usecols, low_memory=False)
    df["gwcode"] = df["gwcode"].astype("Int64")
    df["gwsyear"] = pd.to_numeric(df["gwsyear"], errors="coerce").astype("Int64")
    df["gweyear"] = pd.to_numeric(df["gweyear"], errors="coerce").astype("Int64")
    df["area"] = pd.to_numeric(df["area"], errors="coerce")
    return df.dropna(subset=["gwcode", "gwsyear", "gweyear", "area"])


def _split_gw_for_iso3(
    df: pd.DataFrame, iso3_scope: tuple[str, ...]
) -> pd.DataFrame:
    """Expand the CShapes GW 365 record into SUN / RUS rows.

    CShapes 2.0 carries a single GW 365 record for the Russian
    Empire + USSR + Russian Federation. The Chronicle treats SUN
    (1922-1991) and RUS (1991+) as separate identities. This helper
    REPLACES the direct-mapping GW 365 rows with dispatch rows:
    one row per ``(gwcode, start_year, end_year)`` slice from
    :data:`CSHAPES_GW_YEAR_TO_ISO3`.

    The dispatch uses **asymmetric containment rules** to avoid
    leaking SUN-era territory values to RUS rows (or vice
    versa) while still picking up rows that span the identity's
    existence window:

    - For the SUN dispatch (1922-1991): a row qualifies if its
      original ``gweyear >= 1922`` (the row's measurement end
      year is in SUN's existence). This keeps the 1921-1945 row
      (which covers 1922-1945 SUN territory) but does NOT
      accept any post-1991 rows. SUN's territory area
      (22,066,000 km² for 1945-1991, 22,015,200 km² for
      1921-1945) is the canonical USSR area.
    - For the RUS dispatch (1991+): a row qualifies if its
      original ``gwsyear >= 1991`` (the row's measurement start
      year is at or after RUS's start). This drops the
      pre-1991 SUN-era rows from RUS's dispatch but accepts
      the 1991-1991, 1991-2014, and 2014-2019 rows.

    The 1991-1991 record qualifies for both dispatches (its
    gweyear=1991 >= 1922 AND its gwsyear=1991 >= 1991); the
    per-year lookup resolves the dispatch correctly (the
    1991 area value, 16,882,600 km², is appropriate for both
    SUN's last year and RUS's first year).

    Adding a new split-identity source means a new
    ``(gwcode, start_year, end_year, iso3)`` tuple in
    :data:`CSHAPES_GW_YEAR_TO_ISO3`.
    """
    if df.empty or not CSHAPES_GW_YEAR_TO_ISO3:
        return df
    # Identify the GW codes that need splitting (so we can drop
    # the original direct-mapped rows before adding dispatch rows).
    split_gwcodes = {entry[0] for entry in CSHAPES_GW_YEAR_TO_ISO3}
    base = df.loc[~df["gwcode"].isin(split_gwcodes)].copy()
    expanded: list[pd.DataFrame] = []
    for gwcode, start_year, end_year, iso3 in CSHAPES_GW_YEAR_TO_ISO3:
        if iso3_scope and iso3 not in iso3_scope:
            continue
        rows = df.loc[df["gwcode"] == gwcode]
        if rows.empty:
            continue
        # Asymmetric dispatch rule.
        # SUN dispatch (1922-1991): keep rows whose original
        # gweyear is in SUN's existence (the row ends no later
        # than SUN's end). This includes the 1921-1945 row
        # (whose 1922-1945 portion is SUN territory).
        # RUS dispatch (1991+): keep rows whose original
        # gwsyear is at or after RUS's start (the row starts
        # no earlier than RUS's start). This excludes
        # pre-1991 SUN-era rows from RUS's dispatch.
        if end_year < 9999:
            # SUN-style dispatch: keep rows whose gweyear is
            # within the dispatch window.
            mask = (rows["gweyear"] <= end_year) & (rows["gweyear"] >= start_year)
        else:
            # RUS-style dispatch (end_year=9999 sentinel): keep
            # rows whose gwsyear is at or after the dispatch
            # start.
            mask = rows["gwsyear"] >= start_year
        sliced = rows.loc[mask].copy()
        if sliced.empty:
            continue
        sliced["iso3"] = iso3
        expanded.append(
            sliced[["iso3", "cntry_name", "area", "gwcode", "gwsyear", "gweyear"]]
        )
    if not expanded:
        return base
    extras = pd.concat(expanded, ignore_index=True)
    return pd.concat([base, extras], ignore_index=True)


@dataclass(frozen=True)
class CShapesSource:
    """In-memory CShapes 2.0 slice narrowed to the pilot ISO3 set.

    The loader narrows the raw 252-gwcode frame down to the pilot
    ISO3 set mapped via :data:`CSHAPES_GW_TO_ISO3`. The
    :func:`lookup_area` method returns the
    ``(area_km2, source_year_used, is_proxy)`` triple for an
    ``(iso3, year)`` pair, or ``(None, year, False)`` when the
    request falls outside CShapes coverage entirely.

    The CShapes 2.0 coverage ends in 2019. For years 2020+, the
    loader returns the most recent CShapes row for the ISO3 and
    tags the lookup as ``is_proxy=True`` so the row builder can
    emit the ``area_proxy_year_used`` flag.

    Attributes:
        raw_csv_path: Absolute path to the raw CShapes CSV.
        frame: Narrow ``DataFrame`` with columns
            ``iso3``, ``area``, ``gwcode``, ``gwsyear``, ``gweyear``,
            ``source_year_used``. ``source_year_used`` carries the
            year from which the area was read (used for the
            proxy-year tag when ``is_proxy=True``).
    """

    raw_csv_path: Path
    frame: pd.DataFrame = field(default_factory=pd.DataFrame)

    @property
    def max_year(self) -> int | None:
        """Maximum CShapes coverage year across the loaded frame."""
        if self.frame.empty:
            return None
        return int(self.frame["gweyear"].max())

    @property
    def min_year(self) -> int | None:
        """Minimum CShapes coverage year across the loaded frame."""
        if self.frame.empty:
            return None
        return int(self.frame["gwsyear"].min())

    def lookup_area(
        self, iso3: str, year: int
    ) -> tuple[float | None, int, bool]:
        """Return ``(area_km2, source_year_used, is_proxy)`` for ``(iso3, year)``.

        The helper prefers an exact-match row whose
        ``gwsyear <= year <= gweyear``. When no exact match exists
        but CShapes has data for the ISO3 and ``year > max_year``,
        the helper falls back to the most recent CShapes row and
        returns ``is_proxy=True`` so the row builder emits
        ``area_proxy_year_used``. Years before CShapes coverage
        (``year < min_year``) return ``(None, year, False)``.
        """
        if self.frame.empty:
            return (None, year, False)
        rows = self.frame.loc[self.frame["iso3"] == iso3]
        if rows.empty:
            return (None, year, False)
        # Exact match.
        exact = rows.loc[
            (rows["gwsyear"] <= year) & (rows["gweyear"] >= year)
        ]
        if not exact.empty:
            # Pick the row with the SMALLEST gweyear, then the
            # LARGEST gwsyear (narrowest period covering year).
            # This makes a 1991-only dispatch record win over a
            # 1991-2014 record when both match. Territory
            # adjustments within the same year are still honored
            # because the narrower row is by definition a more
            # specific measurement.
            row = exact.sort_values(
                ["gweyear", "gwsyear"], ascending=[True, False],
            ).iloc[0]
            return (
                float(row["area"]),
                int(row["gweyear"]),
                False,
            )
        # Out-of-coverage fallback (post-2019).
        if self.max_year is not None and year > self.max_year:
            latest = rows.sort_values("gweyear", ascending=False).iloc[0]
            return (
                float(latest["area"]),
                int(latest["gweyear"]),
                True,
            )
        return (None, year, False)


def load_cshapes_source(
    *,
    csv_path: Path | None = None,
    iso3_scope: tuple[str, ...] = (),
) -> CShapesSource:
    """Read the raw CShapes 2.0 CSV and narrow it to the requested ISO3 set.

    When the file is missing the loader logs a warning and returns
    a :class:`CShapesSource` with an empty frame so the row builder
    degrades gracefully (area columns empty with the canonical
    ``missing_area`` flag).
    """
    path = csv_path or default_cshapes_csv_path()
    if not path.is_file():
        _logger.warning(
            "CShapes raw CSV not found at %s; country area will be "
            "empty with the missing_area flag.",
            path,
        )
        return CShapesSource(raw_csv_path=path)
    df = _read_cshapes_csv(path)
    # Map GW -> ISO3 only for the requested scope; the inverse map is
    # built once from the full GW->ISO3 dictionary.
    iso3_to_gw = {iso3: gw for gw, iso3 in CSHAPES_GW_TO_ISO3.items()}
    gw_set = {iso3_to_gw[i] for i in iso3_scope if i in iso3_to_gw}
    if gw_set:
        df = df[df["gwcode"].isin(gw_set)].copy()
    df["iso3"] = df["gwcode"].map(CSHAPES_GW_TO_ISO3)
    df = df.dropna(subset=["iso3"])
    # Expand split-identity GW codes (e.g. GW 365 -> SUN 1922-1991,
    # RUS 1992+) so the per-year lookup can dispatch on ISO3.
    df = _split_gw_for_iso3(df, iso3_scope)
    return CShapesSource(
        raw_csv_path=path,
        frame=df.reset_index(drop=True),
    )


__all__ = [
    "CShapesSource",
    "default_cshapes_csv_path",
    "load_cshapes_source",
]
