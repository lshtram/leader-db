"""Source loaders for the Country-Year Chronicle slice.

Each loader returns a small typed result model that the row builder
consumes. The loaders are deliberately tiny:

- :class:`VDemSource` reads the raw V-Dem CSV, narrows to the columns
  we need (``country_text_id``, ``year``, ``v2x_regime``,
  ``v2x_polyarchy``, ``v2x_libdem``), and filters to the requested
  ``iso3`` set. We always read the raw CSV (not the processed parquet)
  because the processed artifact only contains 2022 — Increment 1 needs
  the full 1789-2025 range. The raw CSV is 388 MB but ``usecols=`` +
  ``nrows=None`` + a single ``pandas`` read is still acceptable for
  the 7-country pilot window.
- :class:`WdiSource` reads the processed WDI parquet and looks up
  population / GDP / GDP per capita by ``(iso3, year)``. The processed
  parquet only contains 2022 today; for any other year the lookup
  returns ``None`` and the row builder emits the
  ``missing_population`` / ``missing_gdp`` flags.
- :class:`SipriSource` reads the processed SIPRI milex parquet and
  looks up military spend by ``(country_name, year)``. The processed
  parquet uses country display names, not ISO3 codes; we keep a small
  ISO3->display-name map. Same caveat: only 2022 is available locally.

The Maddison Project loader (:class:`MaddisonSource` +
:func:`load_maddison_source`) lives in
:mod:`leaders_db.chronicle._maddison_source` to keep this module
focused on the WDI / SIPRI / V-Dem trio and under the 400-line
convention. It is re-exported below for back-compat with callers
that already import from here.

All loaders are pure functions with no module-level mutable state, so
the runner can instantiate them once and reuse them across rows.

The module deliberately does NOT import the prototype ``Stage 2``
adapters (which write to the database). Increment 1 is a read-only
slice and the database is not touched.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

import pandas as pd

from ._maddison_source import MaddisonSource, load_maddison_source
from .constants import DEFAULT_PROXY_YEAR, VDEM_MAX_COVERED_YEAR

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# V-Dem source
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VDemSource:
    """In-memory V-Dem slice narrowed to the requested iso3 set.

    The data is loaded from the raw V-Dem CSV
    (``data/raw/vdem/V-Dem-CY-Full+Others-v16.csv``) once per runner
    invocation. We use ``usecols=`` to skip the 530+ columns we do not
    need. The frame is then narrowed to the requested iso3 set so the
    per-row lookup is O(1) in a dict.

    Attributes:
        raw_csv_path: Absolute path to the raw V-Dem CSV.
        frame: Narrow ``DataFrame`` with columns
            ``country_text_id``, ``year``, ``v2x_regime``,
            ``v2x_polyarchy``, ``v2x_libdem``.
    """

    raw_csv_path: Path
    frame: pd.DataFrame

    @property
    def min_year(self) -> int:
        if self.frame.empty:
            return VDEM_MAX_COVERED_YEAR
        return int(self.frame["year"].min())

    @property
    def max_year(self) -> int:
        if self.frame.empty:
            return VDEM_MAX_COVERED_YEAR
        return int(self.frame["year"].max())

    def lookup(
        self, iso3: str, year: int
    ) -> tuple[float | None, float | None, float | None]:
        """Return ``(v2x_regime, v2x_polyarchy, v2x_libdem)`` for the given year.

        We use the V-Dem ``country_text_id`` column directly because it
        matches the project's ISO3 keys for the pilot countries (verified
        during Increment 0 recon). Returns ``(None, None, None)`` if no
        row matches.
        """
        if year > VDEM_MAX_COVERED_YEAR:
            return (None, None, None)
        # ``eq`` on a string-typed Series returns a boolean mask; the
        # narrowed frame is small (< 300 rows per country) so a boolean
        # filter is fast enough.
        mask = (self.frame["country_text_id"] == iso3) & (self.frame["year"] == year)
        matches = self.frame.loc[mask]
        if matches.empty:
            return (None, None, None)
        row = matches.iloc[0]
        regime = row.get("v2x_regime")
        polyarchy = row.get("v2x_polyarchy")
        libdem = row.get("v2x_libdem")
        return (
            None if pd.isna(regime) else float(regime),
            None if pd.isna(polyarchy) else float(polyarchy),
            None if pd.isna(libdem) else float(libdem),
        )


def load_vdem_source(
    *,
    raw_csv_path: Path,
    iso3_scope: tuple[str, ...],
) -> VDemSource:
    """Read the raw V-Dem CSV and narrow it to the requested iso3 set.

    Parameters
    ----------
    raw_csv_path:
        Path to ``V-Dem-CY-Full+Others-v16.csv``. If the file is missing
        we return an empty :class:`VDemSource` and log a warning; the
        row builder will then mark every regime row with
        ``regime_source_gap``.
    iso3_scope:
        ISO3 keys to keep (e.g. ``("USA", "GBR", ...)"``).
    """
    if not raw_csv_path.is_file():
        _logger.warning(
            "V-Dem raw CSV not found at %s; regime buckets will be empty.",
            raw_csv_path,
        )
        return VDemSource(
            raw_csv_path=raw_csv_path,
            frame=pd.DataFrame(
                columns=[
                    "country_text_id",
                    "year",
                    "v2x_regime",
                    "v2x_polyarchy",
                    "v2x_libdem",
                ]
            ),
        )

    # Read the entire CSV (pandas can stream large files; pyarrow's CSV
    # engine is also fine but pandas is more uniform across our test
    # environments). We restrict the columns we read with ``usecols=``
    # to keep the peak memory low (5 columns out of ~4700).
    usecols = ["country_text_id", "year", "v2x_regime", "v2x_polyarchy", "v2x_libdem"]
    df = pd.read_csv(raw_csv_path, usecols=usecols, low_memory=False)
    df = df[df["country_text_id"].isin(set(iso3_scope))].copy()
    return VDemSource(raw_csv_path=raw_csv_path, frame=df)


# ---------------------------------------------------------------------------
# WDI source
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WdiSource:
    """In-memory WDI slice keyed by ``(iso3, year)``.

    The processed parquet only contains 2022 today. For any other
    ``(iso3, year)`` the lookup returns all-``None``. This is by design
    — Increment 1 does not pretend to have pre-2023 WDI values that
    the local processed artifact does not contain.
    """

    parquet_path: Path
    frame: pd.DataFrame = field(default_factory=pd.DataFrame)

    def lookup(
        self, iso3: str, year: int
    ) -> dict[str, float | None]:
        """Return a dict with the WDI fields, or empty-dict when no match.

        Returned keys (only present when a value is non-null):
            ``population``, ``gdp_current_usd``,
            ``gdp_constant_2015_usd``, ``gdp_per_capita``,
            ``gdp_per_capita_ppp``.
        """
        if self.frame.empty:
            return {}
        mask = (self.frame["iso3"] == iso3) & (self.frame["year"] == year)
        matches = self.frame.loc[mask]
        if matches.empty:
            return {}
        row = matches.iloc[0]
        out: dict[str, float | None] = {}
        for key, col in (
            ("population", "wdi_population"),
            ("gdp_current_usd", "wdi_gdp_current_usd"),
            ("gdp_constant_2015_usd", "wdi_gdp_constant_2015_usd"),
            ("gdp_per_capita", "wdi_gdp_per_capita"),
            ("gdp_per_capita_ppp", "wdi_gdp_per_capita_ppp_constant_2017"),
        ):
            if col in self.frame.columns:
                value = row[col]
                out[key] = None if pd.isna(value) else float(value)
        return out


def load_wdi_source(
    *,
    parquet_path: Path,
    iso3_scope: tuple[str, ...],
) -> WdiSource:
    """Read the processed WDI parquet and narrow it to the requested iso3 set."""
    if not parquet_path.is_file():
        _logger.warning(
            "WDI processed parquet not found at %s; "
            "population/GDP will be empty with flags.",
            parquet_path,
        )
        return WdiSource(parquet_path=parquet_path, frame=pd.DataFrame())
    df = pd.read_parquet(parquet_path)
    df = df[df["iso3"].isin(set(iso3_scope))].copy()
    return WdiSource(parquet_path=parquet_path, frame=df)


# ---------------------------------------------------------------------------
# SIPRI milex source
# ---------------------------------------------------------------------------

#: SIPRI uses display names in the processed parquet (no ISO3 column).
#: This small map resolves the seven pilot ISO3 codes to their SIPRI
#: display names. Verified against
#: ``data/processed/sipri_milex/sipri_milex_country_year.parquet`` on
#: 2026-06-20.
SIPRI_NAME_BY_ISO3: Final[dict[str, str]] = {
    "USA": "United States of America",
    "GBR": "United Kingdom",
    "FRA": "France",
    "IND": "India",
    "RUS": "Russia",
    # SUN is not present in the SIPRI processed parquet (it ended in
    # 1991 and the local artifact has only 2022). The lookup returns
    # ``None`` for SUN rows and the row builder flags
    # ``missing_military_spend``.
    "SUN": "",
    "CHN": "China",
}


@dataclass(frozen=True)
class SipriSource:
    """In-memory SIPRI milex slice keyed by ``(country_name, year)``."""

    parquet_path: Path
    frame: pd.DataFrame = field(default_factory=pd.DataFrame)

    def lookup(
        self, iso3: str, year: int
    ) -> dict[str, float | None]:
        """Return a dict with the SIPRI fields, or empty-dict when no match.

        Returned keys (only present when a value is non-null):
            ``milex_constant_usd``, ``milex_per_capita``,
            ``milex_share_of_gdp``.
        """
        if self.frame.empty:
            return {}
        name = SIPRI_NAME_BY_ISO3.get(iso3, "")
        if not name:
            return {}
        mask = (self.frame["country"] == name) & (self.frame["year"] == year)
        matches = self.frame.loc[mask]
        if matches.empty:
            return {}
        row = matches.iloc[0]
        out: dict[str, float | None] = {}
        for key, col in (
            ("milex_constant_usd", "sipri_milex_constant_usd"),
            ("milex_per_capita", "sipri_milex_per_capita"),
            ("milex_share_of_gdp", "sipri_milex_share_of_gdp"),
        ):
            if col in self.frame.columns:
                value = row[col]
                out[key] = None if pd.isna(value) else float(value)
        return out


def load_sipri_source(
    *,
    parquet_path: Path,
    iso3_scope: tuple[str, ...],
) -> SipriSource:
    """Read the processed SIPRI milex parquet and narrow it to the pilot set."""
    if not parquet_path.is_file():
        _logger.warning(
            "SIPRI milex processed parquet not found at %s; "
            "military spend will be empty with flags.",
            parquet_path,
        )
        return SipriSource(parquet_path=parquet_path, frame=pd.DataFrame())
    df = pd.read_parquet(parquet_path)
    sipri_names = {SIPRI_NAME_BY_ISO3.get(iso3, "") for iso3 in iso3_scope}
    sipri_names.discard("")
    df = df[df["country"].isin(sipri_names)].copy()
    return SipriSource(parquet_path=parquet_path, frame=df)


# ---------------------------------------------------------------------------
# RegimeSource — typed lookup result for the row builder
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RegimeSource:
    """Result of a single V-Dem lookup for the row builder.

    The row builder uses ``source_year_used`` (which may differ from the
    requested year when the proxy path is taken) and the regime metadata
    to populate the political-regime columns.

    Attributes:
        regime: V-Dem native ``v2x_regime`` integer (0-3) or ``None``
            when no row matched even the proxy year.
        polyarchy: V-Dem ``v2x_polyarchy`` (0-1) or ``None``.
        libdem: V-Dem ``v2x_libdem`` (0-1) or ``None``.
        source_year_used: The year actually read (equals the requested
            year for direct matches; equals :data:`DEFAULT_PROXY_YEAR`
            for proxy matches).
        is_proxy: True when ``source_year_used != requested year``.
    """

    regime: float | None
    polyarchy: float | None
    libdem: float | None
    source_year_used: int
    is_proxy: bool

    @staticmethod
    def from_vdem_lookup(
        vdem: VDemSource, iso3: str, year: int
    ) -> RegimeSource:
        """Build a :class:`RegimeSource` honoring the 2025 proxy default.

        The 2025 proxy default is chosen because Increment 0 §5.1 says:
        "For 2026, use 2025 V-Dem as a one-year proxy only if the
        CLI/config explicitly allows proxy years; otherwise emit
        ``Unknown`` with ``regime_source_gap``."

        We treat the CLI's ``--allow-regime-proxy`` flag as the explicit
        opt-in. When the flag is False and ``year > VDEM_MAX_COVERED_YEAR``
        we return a fully-empty :class:`RegimeSource` so the row builder
        emits ``Unknown`` + ``regime_source_gap``. When the flag is True
        we read V-Dem for ``DEFAULT_PROXY_YEAR`` and tag the row with
        ``proxy_year_used``.
        """
        # Direct lookup first.
        regime, polyarchy, libdem = vdem.lookup(iso3, year)
        if regime is not None or polyarchy is not None or libdem is not None:
            return RegimeSource(
                regime=regime,
                polyarchy=polyarchy,
                libdem=libdem,
                source_year_used=year,
                is_proxy=False,
            )
        # Direct failed. Try the proxy year if the requested year is
        # beyond V-Dem coverage and the caller opted in.
        if year > VDEM_MAX_COVERED_YEAR:
            proxy_year = DEFAULT_PROXY_YEAR
            # Note: we always try the proxy path here; the row builder
            # decides whether to consume it. This keeps the loader
            # policy-free.
            if proxy_year <= VDEM_MAX_COVERED_YEAR:
                regime, polyarchy, libdem = vdem.lookup(iso3, proxy_year)
                if (
                    regime is not None
                    or polyarchy is not None
                    or libdem is not None
                ):
                    return RegimeSource(
                        regime=regime,
                        polyarchy=polyarchy,
                        libdem=libdem,
                        source_year_used=proxy_year,
                        is_proxy=True,
                    )
        return RegimeSource(
            regime=None,
            polyarchy=None,
            libdem=None,
            source_year_used=year,
            is_proxy=False,
        )


__all__ = [
    "SIPRI_NAME_BY_ISO3",
    "MaddisonSource",
    "RegimeSource",
    "SipriSource",
    "VDemSource",
    "WdiSource",
    "load_maddison_source",
    "load_sipri_source",
    "load_vdem_source",
    "load_wdi_source",
]
