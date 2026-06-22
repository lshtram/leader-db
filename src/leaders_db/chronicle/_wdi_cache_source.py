"""WDI coverage-cache loader for the Country-Year Chronicle slice.

The local data lake carries a set of WDI v2 API coverage-cache JSON
files under ``data/raw/world_bank_wdi/coverage_cache/`` (one file per
indicator + window, e.g. ``NY.GDP.MKTP.KD_1960_2024.json``). The
processed WDI parquet (``data/processed/world_bank_wdi/wdi_country_year.parquet``)
only contains the year the Stage 2 ingest was last run for (2022
today); the cache contains the rest of the 1960-2024 window. The
Chronicle loaders can read the cache as exact country-year
observations in addition to the processed parquet.

Per the Increment 6 (WDI cache GDP improvement) contract:

- The cache loader only adds cache rows whose ``year`` is in
  ``[1960, MAX_CACHE_YEAR]`` where ``MAX_CACHE_YEAR`` is the
  ``_1960_2024`` window's last calendar year. Years outside the
  window are dropped, including any 2025/2026 rows that a future
  cache might carry; we do NOT proxy from 2024 to 2025/2026 in
  this pass.
- Cache indicator IDs are mapped to the canonical WDI narrow
  schema columns used by :class:`WdiSource`. Cache rows are
  emitted in the same long-ish shape as the Stage 2 narrow parquet
  so the merge in :func:`load_wdi_source` is a simple frame
  concatenation + deduplication.
- WDI cache rows OVERRIDE rows from the processed parquet for the
  same ``(iso3, year)`` pair. The cache is the more recent WDI
  v2 release (``lastupdated=2026-04-08``) and the canonical
  source for exact-year observations.
- The cache loader does not invent historical / colonial / pre-1960
  GDP values; if the cache file does not carry a year, that year
  is not in the frame.

This module is intentionally tiny (one loader function + one
indicator map). The decision to override the processed parquet is
encapsulated in :func:`load_wdi_source` (in
:mod:`leaders_db.chronicle.sources`); this module only owns the
cache-to-narrow-schema mapping.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Indicator mapping
# ---------------------------------------------------------------------------

#: WDI v2 indicator ID -> canonical WDI narrow-schema column. Only
#: the four GDP / GDP-per-capita indicators documented in the
#: Increment 6 plan are mapped; the cache also carries population,
#: FDI, literacy, and other series that are out of scope for this
#: pass.
WDI_CACHE_INDICATOR_TO_COLUMN: dict[str, str] = {
    "NY.GDP.MKTP.KD": "wdi_gdp_constant_2015_usd",
    "NY.GDP.MKTP.CD": "wdi_gdp_current_usd",
    "NY.GDP.PCAP.CD": "wdi_gdp_per_capita",
    "NY.GDP.PCAP.PP.KD": "wdi_gdp_per_capita_ppp_constant_2017",
}

#: World Bank aggregate / regional codes that the cache carries
#: but the Chronicle does not want in the lookup frame. Aggregates
#: start with letters A-Z + digits and have no real-country status
#: (e.g. ``AFE`` Africa Eastern and Southern, ``WLD`` World).
#: We filter them by name, not by a 3-letter-vs-digit rule,
#: because the cache ``countryiso3code`` field for real countries
#: is the standard ISO3 code.
WORLD_BANK_AGGREGATE_CODES: frozenset[str] = frozenset({
    "AFE", "AFW", "ARB", "CEB", "CSS", "EAP", "EAR", "EAS",
    "ECA", "ECS", "EMU", "EUU", "FCS", "HIC", "HPC", "IBD",
    "IBT", "IDA", "IDB", "IDX", "INX", "LAC", "LCN", "LDC",
    "LIC", "LMC", "LMY", "LTE", "MEA", "MIC", "MNA", "NAC",
    "OED", "OSS", "PRE", "PSS", "PST", "SAS", "SSA", "SSF",
    "SST", "TEA", "TEC", "TLA", "TMN", "TSA", "TSS", "UMC",
    "WLD",
})


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def load_wdi_cache_frame(
    *,
    cache_dir: Path,
    iso3_scope: tuple[str, ...] = (),
) -> pd.DataFrame:
    """Load the WDI v2 coverage-cache JSON into a narrow-schema frame.

    Parameters
    ----------
    cache_dir:
        Directory containing ``<INDICATOR>_<YEAR_LO>_<YEAR_HI>.json``
        files. Typically ``data/raw/world_bank_wdi/coverage_cache/``.
    iso3_scope:
        ISO3 keys to keep. When empty the loader keeps every real
        country (aggregates are filtered regardless of scope).

    Returns
    -------
    pandas.DataFrame
        Frame with the same columns as the Stage 2 WDI narrow
        parquet: ``iso3``, ``year``,
        ``wdi_gdp_current_usd``, ``wdi_gdp_constant_2015_usd``,
        ``wdi_gdp_per_capita``,
        ``wdi_gdp_per_capita_ppp_constant_2017``. Cache rows for
        one indicator only populate the matching column. Empty
        frame with the expected columns when the cache directory
        is missing or carries no recognized indicators.
    """
    columns = [
        "iso3",
        "year",
        "wdi_gdp_current_usd",
        "wdi_gdp_constant_2015_usd",
        "wdi_gdp_per_capita",
        "wdi_gdp_per_capita_ppp_constant_2017",
    ]
    if not cache_dir.is_dir():
        _logger.debug(
            "WDI coverage cache dir %s not found; cache-backed "
            "WDI lookups are disabled for this run.",
            cache_dir,
        )
        return pd.DataFrame(columns=columns)

    iso3_filter = set(iso3_scope) if iso3_scope else set()
    long_records: list[dict[str, object]] = []

    for cache_file in sorted(cache_dir.glob("*_1960_2024.json")):
        indicator_id = cache_file.name.split("_1960_2024.json", 1)[0]
        if indicator_id not in WDI_CACHE_INDICATOR_TO_COLUMN:
            continue
        column = WDI_CACHE_INDICATOR_TO_COLUMN[indicator_id]
        try:
            with cache_file.open(encoding="utf-8") as fh:
                payload = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            _logger.warning(
                "Could not read WDI cache file %s (%s); skipping.",
                cache_file, exc,
            )
            continue
        if not isinstance(payload, list) or len(payload) < 2:
            _logger.debug(
                "WDI cache file %s has unexpected shape; skipping.",
                cache_file,
            )
            continue
        records = payload[1]
        if not isinstance(records, list):
            continue
        for record in records:
            if not isinstance(record, dict):
                continue
            iso3 = record.get("countryiso3code")
            if not iso3 or iso3 in WORLD_BANK_AGGREGATE_CODES:
                continue
            if iso3_filter and iso3 not in iso3_filter:
                continue
            try:
                year = int(record.get("date"))  # type: ignore[arg-type]
            except (TypeError, ValueError):
                continue
            if year < 1960 or year > 2024:
                # The cache window is 1960-2024. We drop any
                # out-of-window record defensively (e.g. a future
                # cache that pre-extends to 2025/2026). The
                # row builder MUST NOT see 2025/2026 WDI data
                # sourced from this cache.
                continue
            value = record.get("value")
            if value is None:
                continue
            try:
                value_f = float(value)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                continue
            if pd.isna(value_f):
                continue
            long_records.append(
                {
                    "iso3": str(iso3),
                    "year": year,
                    column: value_f,
                }
            )

    if not long_records:
        return pd.DataFrame(columns=columns)

    frame = pd.DataFrame.from_records(long_records)
    # One row per (iso3, year) with the matched indicator's column
    # populated. The dict-of-records input already enforces
    # (iso3, year, indicator) uniqueness, but we coalesce
    # defensively in case the cache carries duplicate rows.
    frame = frame.groupby(["iso3", "year"], as_index=False, sort=True).first()
    for col in columns:
        if col not in frame.columns:
            frame[col] = pd.NA
    return frame[columns]


__all__ = [
    "WDI_CACHE_INDICATOR_TO_COLUMN",
    "WORLD_BANK_AGGREGATE_CODES",
    "load_wdi_cache_frame",
]
