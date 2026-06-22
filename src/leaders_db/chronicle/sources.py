"""Source loaders for the Country-Year Chronicle slice.

Each loader returns a small typed result model that the row builder
consumes. The loaders are deliberately tiny:

- :class:`VDemSource` reads the raw V-Dem CSV, narrows to the columns
  we need (``country_text_id``, ``year``, ``v2x_regime``,
  ``v2x_polyarchy``, ``v2x_libdem``, ``v2svindep``, selected population
  columns), and filters to the requested ``iso3`` set. We always read
  the raw CSV (not the processed parquet)
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

_MAX_POPULATION_INTERPOLATION_SPAN_YEARS: Final[int] = 75
_MAX_POPULATION_PROXY_LAG_YEARS: Final[int] = 1


# ---------------------------------------------------------------------------
# V-Dem source
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VDemPopulationLookup:
    """V-Dem-backed population lookup result.

    ``method`` is one of ``exact``, ``interpolated``, or ``proxy``.
    ``source_year_used`` is the requested year for exact/interpolated
    estimates and the copied source year for a proxy estimate.
    """

    value: float
    source_year_used: int
    method: str


@dataclass(frozen=True)
class VDemGdpLookup:
    """V-Dem latent GDP lookup result.

    V-Dem ``e_gdp`` and ``e_gdppc`` are Fariss et al. latent-variable
    estimates, not Maddison/WDI currency values. The economy layer writes
    explicit V-Dem latent unit labels when it uses these values.
    """

    gdp: float
    gdppc: float
    source_year_used: int


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
            ``v2x_polyarchy``, ``v2x_libdem``, ``v2svindep``, ``COWcode``.
    """

    raw_csv_path: Path
    frame: pd.DataFrame
    population_observations_by_iso: dict[str, dict[int, float]] = field(
        default_factory=dict, init=False, repr=False, compare=False,
    )
    gdp_observations_by_iso: dict[str, dict[int, VDemGdpLookup]] = field(
        default_factory=dict, init=False, repr=False, compare=False,
    )

    def __post_init__(self) -> None:
        """Precompute V-Dem population observations for O(1) lookups."""
        object.__setattr__(
            self,
            "population_observations_by_iso",
            self._build_population_observation_cache(),
        )
        object.__setattr__(
            self,
            "gdp_observations_by_iso",
            self._build_gdp_observation_cache(),
        )

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

    def population_lookup(
        self, iso3: str, year: int,
    ) -> VDemPopulationLookup | None:
        """Return V-Dem population as absolute persons when available.

        ``e_wb_pop`` is the World Bank population series in absolute
        persons. ``e_mipopula`` is V-Dem's Maddison-like population
        series in thousands of persons, so it is multiplied by 1000 to
        match the Chronicle ``population`` column contract. ``e_pop`` is
        a Fariss et al. latent-variable population estimate; V-Dem's
        observed scale is ten-thousands, so the fallback multiplies by
        10000 and uses it after the two direct total-population fields.

        When no exact row has a usable value, the lookup interpolates
        bounded internal gaps between the nearest same-country V-Dem
        population observations, and then allows a one-year carry-forward
        proxy for the latest year (currently 2025, from 2024). Non-exact
        results are flagged by the economy layer.
        """
        if self.frame.empty or year > VDEM_MAX_COVERED_YEAR:
            return None
        observations = self._population_observations(iso3)
        if not observations:
            return None
        if year in observations:
            return VDemPopulationLookup(
                value=observations[year],
                source_year_used=year,
                method="exact",
            )

        interpolated = self._interpolate_population(observations, year)
        if interpolated is not None:
            return VDemPopulationLookup(
                value=interpolated,
                source_year_used=year,
                method="interpolated",
            )

        proxy_year = self._population_proxy_year(observations, year)
        if proxy_year is not None:
            return VDemPopulationLookup(
                value=observations[proxy_year],
                source_year_used=proxy_year,
                method="proxy",
            )
        return None

    def _population_observations(self, iso3: str) -> dict[int, float]:
        """Return safe V-Dem population observations by year."""
        return self.population_observations_by_iso.get(iso3, {})

    def _build_population_observation_cache(self) -> dict[str, dict[int, float]]:
        """Build safe V-Dem population observations by ISO3 and year."""
        if self.frame.empty:
            return {}
        observations_by_iso: dict[str, dict[int, float]] = {}
        for row in self.frame.itertuples(index=False):
            iso3 = str(row.country_text_id)
            year = int(row.year)
            value = self._population_value_from_row(row)
            if value is not None:
                observations_by_iso.setdefault(iso3, {})[year] = value
        return observations_by_iso

    @staticmethod
    def _population_value_from_row(row: object) -> float | None:
        """Return one row's population value in absolute persons."""
        wb_value = getattr(row, "e_wb_pop", None)
        if wb_value is not None and not pd.isna(wb_value):
            return float(wb_value)
        mi_value = getattr(row, "e_mipopula", None)
        if mi_value is not None and not pd.isna(mi_value):
            return float(mi_value) * 1000.0
        e_pop_value = getattr(row, "e_pop", None)
        if e_pop_value is not None and not pd.isna(e_pop_value):
            return float(e_pop_value) * 10000.0
        return None

    @staticmethod
    def _interpolate_population(
        observations: dict[int, float], year: int,
    ) -> float | None:
        """Linearly interpolate a bounded internal population gap."""
        previous_years = [candidate for candidate in observations if candidate < year]
        following_years = [candidate for candidate in observations if candidate > year]
        if not previous_years or not following_years:
            return None
        previous_year = max(previous_years)
        following_year = min(following_years)
        span = following_year - previous_year
        if span > _MAX_POPULATION_INTERPOLATION_SPAN_YEARS:
            return None
        previous_value = observations[previous_year]
        following_value = observations[following_year]
        fraction = (year - previous_year) / span
        return previous_value + ((following_value - previous_value) * fraction)

    @staticmethod
    def _population_proxy_year(
        observations: dict[int, float], year: int,
    ) -> int | None:
        """Return a one-year prior source year for recent population proxying."""
        candidates = [
            candidate
            for candidate in observations
            if 0 < year - candidate <= _MAX_POPULATION_PROXY_LAG_YEARS
        ]
        if not candidates:
            return None
        return max(candidates)

    def gdp_lookup(self, iso3: str, year: int) -> VDemGdpLookup | None:
        """Return exact V-Dem latent GDP/GDPpc for ``(iso3, year)``."""
        return self.gdp_observations_by_iso.get(iso3, {}).get(year)

    def _build_gdp_observation_cache(self) -> dict[str, dict[int, VDemGdpLookup]]:
        """Build exact V-Dem latent GDP observations by ISO3 and year."""
        if self.frame.empty:
            return {}
        observations_by_iso: dict[str, dict[int, VDemGdpLookup]] = {}
        for row in self.frame.itertuples(index=False):
            e_gdp = getattr(row, "e_gdp", None)
            e_gdppc = getattr(row, "e_gdppc", None)
            if e_gdp is None or e_gdppc is None:
                continue
            if pd.isna(e_gdp) or pd.isna(e_gdppc):
                continue
            iso3 = str(row.country_text_id)
            year = int(row.year)
            observations_by_iso.setdefault(iso3, {})[year] = VDemGdpLookup(
                gdp=float(e_gdp),
                gdppc=float(e_gdppc),
                source_year_used=year,
            )
        return observations_by_iso

    def _legacy_population_lookup(self, iso3: str, year: int) -> float | None:
        """Legacy exact-only lookup retained for reference in tests/debugging."""
        mask = (self.frame["country_text_id"] == iso3) & (self.frame["year"] == year)
        matches = self.frame.loc[mask]
        if matches.empty:
            return None
        row = matches.iloc[0]
        if "e_wb_pop" in self.frame.columns:
            wb_value = row.get("e_wb_pop")
            if not pd.isna(wb_value):
                return float(wb_value)
        if "e_mipopula" in self.frame.columns:
            mi_value = row.get("e_mipopula")
            if not pd.isna(mi_value):
                return float(mi_value) * 1000.0
        return None

    def cowcode_lookup(self, iso3: str, year: int) -> int | None:
        """Return V-Dem's COW code for ``(iso3, year)`` when available.

        Archigos and REIGN are keyed by COW/ccode. The all-country
        Chronicle path uses this source-backed bridge so the ruler
        resolver can cover more than the hand-mapped pilot identities.
        The lookup first tries the exact country-year. When V-Dem has
        no row for that exact year (common around wartime interruptions
        and other historical coding gaps), it falls back to the
        country's unambiguous COW code across the loaded V-Dem slice.
        Ambiguous or blank COW codes return ``None`` rather than guessing.
        """
        if self.frame.empty or year > VDEM_MAX_COVERED_YEAR:
            return None
        if "COWcode" not in self.frame.columns:
            return None
        mask = (self.frame["country_text_id"] == iso3) & (self.frame["year"] == year)
        matches = self.frame.loc[mask]
        if not matches.empty:
            exact = self._coerce_cowcode(matches.iloc[0].get("COWcode"))
            if exact is not None:
                return exact

        country_rows = self.frame.loc[self.frame["country_text_id"] == iso3]
        if country_rows.empty:
            return None
        cowcodes = {
            code
            for value in country_rows["COWcode"].dropna().tolist()
            if (code := self._coerce_cowcode(value)) is not None
        }
        if len(cowcodes) != 1:
            return None
        return next(iter(cowcodes))

    @staticmethod
    def _coerce_cowcode(value: object) -> int | None:
        """Coerce a V-Dem COW code cell to ``int`` when possible."""
        if pd.isna(value):
            return None
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

    def is_colonial_or_dependent_year(self, iso3: str, year: int) -> bool:
        """Return ``True`` when V-Dem marks ``(iso3, year)`` non-independent.

        The temporary Chronicle ruler placeholder uses V-Dem's
        ``v2svindep`` independence indicator. A value of ``0`` means the
        country-year is coded as not independent, which we currently treat
        as colonial/dependent for the coarse ``colonial-rule`` fill. Missing
        rows, post-coverage years, or absent columns return ``False``.
        When V-Dem has an internal year gap, a year bracketed by the
        same country's non-independent rows is also treated as
        colonial/dependent; this prevents scope-derived internal gaps
        from being counted as ruler-source failures.
        """
        value = None
        if (
            not self.frame.empty
            and year <= VDEM_MAX_COVERED_YEAR
            and "v2svindep" in self.frame.columns
        ):
            country_rows = self.frame.loc[self.frame["country_text_id"] == iso3]
            matches = country_rows.loc[country_rows["year"] == year]
            if not matches.empty:
                value = matches.iloc[0].get("v2svindep")
            if value is None or pd.isna(value):
                return self._is_bracketed_by_non_independent_rows(
                    country_rows, year,
                )
        if value is None or pd.isna(value):
            return False
        try:
            return int(float(value)) == 0
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _is_bracketed_by_non_independent_rows(
        country_rows: pd.DataFrame, year: int,
    ) -> bool:
        """Return True for an internal V-Dem gap bracketed by ``v2svindep=0``.

        This is a conservative interpolation for the temporary
        ``colonial-rule`` placeholder only. It requires both the previous
        and next coded rows for the same ISO3 to be non-independent.
        """
        if country_rows.empty or "v2svindep" not in country_rows.columns:
            return False
        coded = country_rows.dropna(subset=["v2svindep"]).sort_values("year")
        previous = coded.loc[coded["year"] < year].tail(1)
        following = coded.loc[coded["year"] > year].head(1)
        if previous.empty or following.empty:
            return False
        try:
            return (
                int(float(previous.iloc[0]["v2svindep"])) == 0
                and int(float(following.iloc[0]["v2svindep"])) == 0
            )
        except (TypeError, ValueError):
            return False


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
                    "v2svindep",
                    "COWcode",
                    "e_wb_pop",
                    "e_mipopula",
                    "e_pop",
                    "e_gdp",
                    "e_gdppc",
                ]
            ),
        )

    # Read the entire CSV (pandas can stream large files; pyarrow's CSV
    # engine is also fine but pandas is more uniform across our test
    # environments). We restrict the columns we read with ``usecols=``
    # to keep the peak memory low (5 columns out of ~4700).
    desired_usecols = [
        "country_text_id",
        "year",
        "v2x_regime",
        "v2x_polyarchy",
        "v2x_libdem",
        "v2svindep",
        "COWcode",
        "e_wb_pop",
        "e_mipopula",
        "e_pop",
        "e_gdp",
        "e_gdppc",
    ]
    available_columns = set(pd.read_csv(raw_csv_path, nrows=0).columns)
    usecols = [col for col in desired_usecols if col in available_columns]
    df = pd.read_csv(raw_csv_path, usecols=usecols, low_memory=False)
    if "COWcode" not in df.columns:
        df["COWcode"] = pd.NA
    if "v2svindep" not in df.columns:
        df["v2svindep"] = pd.NA
    if "e_wb_pop" not in df.columns:
        df["e_wb_pop"] = pd.NA
    if "e_mipopula" not in df.columns:
        df["e_mipopula"] = pd.NA
    if "e_pop" not in df.columns:
        df["e_pop"] = pd.NA
    if "e_gdp" not in df.columns:
        df["e_gdp"] = pd.NA
    if "e_gdppc" not in df.columns:
        df["e_gdppc"] = pd.NA
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
    cache_dir: Path | None = None,
) -> WdiSource:
    """Read the processed WDI parquet (and optional coverage cache) for the iso3 set.

    Parameters
    ----------
    parquet_path:
        Path to the Stage 2 narrow WDI parquet
        (``data/processed/world_bank_wdi/wdi_country_year.parquet``).
    iso3_scope:
        ISO3 keys the row builder will iterate over.
    cache_dir:
        Optional path to the WDI v2 coverage-cache directory
        (``data/raw/world_bank_wdi/coverage_cache/``). When the
        directory exists it is read as exact country-year
        observations; cache rows override processed-parquet rows
        for the same ``(iso3, year)`` pair (the cache is the
        more recent WDI release). When the directory is missing
        the loader behaves as before (parquet only, no coverage
        improvement). The cache loader is bounded to 1960-2024
        and never contributes 2025/2026 rows, preserving the
        exact-year-only contract.
    """
    iso3_filter = set(iso3_scope)

    if not parquet_path.is_file():
        _logger.warning(
            "WDI processed parquet not found at %s; "
            "population/GDP will be empty with flags unless the "
            "WDI coverage cache supplies them.",
            parquet_path,
        )
        df = pd.DataFrame()
    else:
        df = pd.read_parquet(parquet_path)
        if iso3_filter:
            df = df[df["iso3"].isin(iso3_filter)].copy()

    if cache_dir is None:
        return WdiSource(parquet_path=parquet_path, frame=df)

    # Lazy import to keep the WDI source module surface focused
    # and to avoid a circular import via the runner / orchestration
    # boundary. The helper module owns the cache-to-narrow-schema
    # mapping.
    from ._wdi_cache_source import load_wdi_cache_frame

    cache_df = load_wdi_cache_frame(
        cache_dir=cache_dir, iso3_scope=iso3_scope,
    )
    if cache_df.empty:
        return WdiSource(parquet_path=parquet_path, frame=df)

    # Cache overlay: keep every parquet column (including
    # ``wdi_population`` and any future narrow-schema columns) and
    # let the cache win only on the GDP / GDP-per-capita columns it
    # actually carries. Parquet is the structural base; cache rows
    # for matching ``(iso3, year)`` keys overwrite only the cache
    # columns. Cache-only rows (rows with no parquet match) are
    # appended and inherit ``NA`` for the parquet-only columns.
    # When the parquet is missing or empty (no columns), the cache
    # IS the merged frame.
    if df.empty:
        return WdiSource(parquet_path=parquet_path, frame=cache_df.copy())
    cache_indexed = cache_df.set_index(["iso3", "year"])
    parquet_indexed = df.set_index(["iso3", "year"])
    overlay_columns = [
        c for c in cache_indexed.columns if c in parquet_indexed.columns
    ]
    if overlay_columns:
        parquet_indexed.update(cache_indexed[overlay_columns])
    cache_only = cache_indexed.loc[
        ~cache_indexed.index.isin(parquet_indexed.index)
    ]
    if not cache_only.empty:
        cache_only = cache_only.reindex(columns=parquet_indexed.columns)
        merged_indexed = pd.concat([parquet_indexed, cache_only])
    else:
        merged_indexed = parquet_indexed
    merged = merged_indexed.reset_index()
    return WdiSource(parquet_path=parquet_path, frame=merged)


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
    "VDemPopulationLookup",
    "VDemSource",
    "WdiSource",
    "load_maddison_source",
    "load_sipri_source",
    "load_vdem_source",
    "load_wdi_source",
]
