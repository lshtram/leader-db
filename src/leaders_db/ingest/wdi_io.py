"""Stage 2 — World Bank WDI: indicator catalog, read orchestrator, parquet write.

This module is the I/O half of the WDI adapter (the cross-cutting I/O
layer; the HTTP-specific layer lives in :mod:`wdi_http`). It owns:

- :data:`WDI_SOURCE_KEY` and :data:`WDI_ATTRIBUTION` -- module-level
  constants consumed by the DB layer and the orchestrator.
- :class:`IndicatorSpec` -- one row of the catalog, typed.
- :func:`load_indicator_catalog` -- read the catalog CSV (handles
  the leading ``#`` comment block + comment-only line filtering).
- :data:`_WDI_AGGREGATE_ISO3_CODES` -- the static denylist used by
  the read orchestrator to filter out WDI's region aggregates.
- :func:`read_wdi` -- the read orchestrator: iterates the
  ``(year, indicator)`` grid, calls into :mod:`wdi_http` for each
  cell (cache-first, HTTP-fallback), pivots the long-format response
  to wide format, and filters the aggregate ISO3 codes.
- :func:`write_wdi_parquet` -- persist the wide frame as parquet
  with the WDI attribution attached to the schema metadata.
- :func:`default_cache_dir` / :func:`default_processed_parquet_path` --
  the conventional data-lake locations.

The HTTP-specific layer (URL building, the requests call, the
retry policy, the response parser, the cache I/O helpers) lives in
:mod:`wdi_http`. The DB-side functions live in :mod:`wdi_db`. The
orchestrator that ties everything together lives in :mod:`wdi`.

The WDI v2 response is a 2-element array ``[metadata, data]``. The
``data`` list contains one record per ``(country, indicator, year)``
with ``countryiso3code``, ``date``, and ``value`` (``null`` for
missing). :func:`read_wdi` pivots the long response to wide format
(one row per ``(iso3, year)``, one column per catalog
``variable_name``) and carries the cached/fetched counts on
``df.attrs`` so the orchestrator can surface them in
:class:`WDIIngestResult`.
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from ..paths import processed_dir, raw_dir
from .wdi_http import fetch_wdi_payload, parse_wdi_payload

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Source key used everywhere in the data lake + CLI dispatch. Lives
#: here (the lowest-level module that does NOT import from siblings)
#: so ``wdi_db`` can import it from us, and ``wdi`` can re-export it.
WDI_SOURCE_KEY: str = "world_bank_wdi"

#: Stable WDI attribution block. The canonical text lives in
#: ``docs/sources/attributions.md`` (world_bank_wdi section). This
#: constant must be a substring of that doc; the
#: :func:`test_wdi_attribution_matches_attributions_doc` test enforces
#: byte-for-byte consistency. The constant lives here to break the
#: import cycle: ``wdi_db`` imports it from us, and ``wdi``
#: re-exports it.
WDI_ATTRIBUTION: str = (
    "World Bank. 2024. World Development Indicators. "
    "Washington, D.C.: The World Bank. https://data.worldbank.org/ "
    "Licensed under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/)."
)

#: Default location of the indicator catalog. Lives here so
#: :func:`write_wdi_run_manifest` in ``wdi_db`` can import it without
#: a cycle.
_DEFAULT_CATALOG_PATH: Path = Path(__file__).resolve().parent / "catalogs" / "wdi.csv"

#: Narrow parquet that Stage 2 writes under ``data/processed/world_bank_wdi/``.
_PROCESSED_PARQUET_NAME: str = "wdi_country_year.parquet"

#: Parquet file-level metadata keys (UTF-8 bytes for pyarrow schema.metadata).
_PARQUET_META_ATTRIBUTION: str = "wdi_attribution"
_PARQUET_META_SOURCE_KEY: str = "wdi_source_key"

#: Static denylist of WDI aggregate / region ISO3 codes. The WDI
#: ``country/all`` endpoint returns aggregate regions (e.g. ``AFE``,
#: ``ARB``, ``WLD``) alongside real countries; we filter them out
#: via this frozenset. See ``docs/architecture/wdi.md`` §2.6 for the
#: rationale (denylist is faster and more deterministic than calling
#: ``/country?per_page=32500`` and filtering on region).
#:
#: This set was derived from the live ``/v2/country?per_page=32500``
#: response on 2026-06-18: every code whose ``region.value == "Aggregates"``
#: in the response was added; every code in the previous set that is
#: no longer in the live API (``HIB``) was removed. After filtering, the
#: adapter returns 217 real-country rows.
_WDI_AGGREGATE_ISO3_CODES: frozenset[str] = frozenset({
    "AFE", "AFR", "AFW", "ARB", "BEA", "BEC", "BHI", "BLA", "BMN",
    "BSS", "CAA", "CEA", "CEB", "CEU", "CLA", "CME", "CSA", "CSS",
    "DEA", "DEC", "DLA", "DMN", "DNS", "DSA", "DSF", "DSS", "EAP",
    "EAR", "EAS", "ECA", "ECS", "EMU", "EUU", "FCS", "FXS", "HIC",
    "HPC", "IBB", "IBD", "IBT", "IDA", "IDB", "IDX", "INX", "LAC",
    "LCN", "LDC", "LIC", "LMC", "LMY", "LTE", "MDE", "MEA", "MIC",
    "MNA", "NAC", "NAF", "NRS", "NXS", "OED", "OSS", "PRE", "PSS",
    "PST", "RRS", "SAS", "SSA", "SSF", "SST", "SXZ", "TEA", "TEC",
    "TLA", "TMN", "TSA", "TSS", "UMC", "WLD", "XZN",
})


# ---------------------------------------------------------------------------
# IndicatorSpec
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IndicatorSpec:
    """One row of the WDI indicator catalog.

    The V-Dem :class:`IndicatorSpec` shape is reused verbatim: every
    Stage 2 adapter resolves its raw column from this dataclass so the
    score modules in Stage 9-10 can normalize and direct indicators
    consistently across sources.
    """

    variable_name: str
    raw_column: str
    rating_category: str
    raw_scale: str
    normalized_scale_target: str
    higher_is_better: bool
    unit: str
    description: str

    @classmethod
    def from_csv_row(cls, row: dict[str, str]) -> IndicatorSpec:
        """Build a spec from one CSV row.

        The catalog may use either ``higher_is_better=1`` for "higher is
        better" and ``0`` otherwise (the WDI / V-Dem convention) or
        the Python ``True`` / ``False`` literals (which is what
        ``csv.DictReader`` emits when a cell contains ``"True"``). The
        constructor normalizes both to a real ``bool``. Empty / missing
        values in the optional fields become ``""``.
        """
        raw_higher = row.get("higher_is_better", "1")
        if isinstance(raw_higher, bool):
            higher_is_better = raw_higher
        else:
            higher_is_better = str(raw_higher).strip().lower() in {"1", "true", "yes"}
        return cls(
            variable_name=row["variable_name"],
            raw_column=row["raw_column"],
            rating_category=row["rating_category"],
            raw_scale=row["raw_scale"],
            normalized_scale_target=row["normalized_scale_target"],
            higher_is_better=higher_is_better,
            unit=row.get("unit", "").strip(),
            description=row.get("description", "").strip(),
        )


def load_indicator_catalog(catalog_path: Path | None = None) -> list[IndicatorSpec]:
    """Load the WDI indicator catalog from ``catalogs/wdi.csv``.

    Mirrors the V-Dem loader: handles the leading ``#`` comment block,
    drops comment-only lines, validates the required column set, and
    returns one :class:`IndicatorSpec` per data row in file order.

    Raises:
        FileNotFoundError: if the catalog file is missing.
        ValueError: if a required column is missing in the catalog header.
    """
    path = catalog_path or _DEFAULT_CATALOG_PATH
    if not path.is_file():
        raise FileNotFoundError(f"WDI indicator catalog not found: {path}")

    required = {
        "variable_name",
        "raw_column",
        "rating_category",
        "raw_scale",
        "normalized_scale_target",
        "higher_is_better",
        "unit",
        "description",
    }

    # Read raw lines, drop comment-only lines, then hand the cleaned text
    # to csv.DictReader. Comment-only means: stripped line starts with ``#``
    # or is blank. Inline ``#`` characters inside a data row are preserved.
    cleaned_lines: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        cleaned_lines.append(raw_line)
    if not cleaned_lines:
        raise ValueError(f"WDI catalog {path} has no data rows after stripping comments")

    reader = csv.DictReader(cleaned_lines)
    missing = required - set(reader.fieldnames or ())
    if missing:
        raise ValueError(
            f"WDI catalog {path} is missing required columns: {sorted(missing)}"
        )

    specs: list[IndicatorSpec] = []
    for row in reader:
        if not row.get("variable_name"):
            continue
        specs.append(IndicatorSpec.from_csv_row(row))
    return specs


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def default_cache_dir() -> Path:
    """Return the conventional WDI JSON cache root inside the data lake.

    Layout: ``<project_root>/data/raw/world_bank_wdi/cache/``. Per-year
    subdirectories hold one ``<CODE>.json`` per indicator.
    """
    return raw_dir(WDI_SOURCE_KEY) / "cache"


def default_processed_parquet_path() -> Path:
    """Return the conventional WDI narrow parquet path.

    Creates the ``data/processed/world_bank_wdi/`` directory if missing.
    """
    processed_dir(WDI_SOURCE_KEY).mkdir(parents=True, exist_ok=True)
    return processed_dir(WDI_SOURCE_KEY) / _PROCESSED_PARQUET_NAME


# ---------------------------------------------------------------------------
# Read orchestrator
# ---------------------------------------------------------------------------


def _resolve_years(year: int | None, cache_root: Path) -> list[int]:
    """Return the list of years to read.

    If ``year`` is given, that single year is returned. Otherwise the
    function scans ``cache_root`` for integer-named subdirectories
    (the per-year cache layout) and returns the sorted list of years.
    A missing cache root returns an empty list.
    """
    if year is not None:
        return [int(year)]
    if not cache_root.is_dir():
        return []
    return sorted(
        int(child.name)
        for child in cache_root.iterdir()
        if child.is_dir() and child.name.isdigit()
    )


def read_wdi(
    *,
    year: int | None = None,
    indicator_codes: list[str] | None = None,
    catalog_path: Path | None = None,
    cache_dir: Path | None = None,
    force_refresh: bool = False,
    request_timeout: float = 30.0,
) -> pd.DataFrame:
    """Read WDI for ``year`` and pivot to wide format (one row per country).

    Steps:

    1. Load the catalog (or use the ``indicator_codes`` override).
    2. For each indicator: if the cache file exists at
       ``<cache_dir>/<year>/<CODE>.json`` AND ``force_refresh`` is
       False, read the cached JSON; else HTTP-GET the WDI v2 endpoint
       via :mod:`wdi_http`, write the verbatim response to the cache,
       then parse.
    3. Filter aggregate ISO3 codes (see
       :data:`_WDI_AGGREGATE_ISO3_CODES`) and rows where
       ``countryiso3code`` is empty.
    4. Pivot from long format (one row per ``(country, indicator, year)``)
       to wide format (one row per ``(iso3, year)``, one column per
       catalog indicator). The wide column for the indicator value
       uses the catalog's ``variable_name``.
    5. Coerce the ``year`` column to ``int`` and the indicator columns
       to ``float`` (NaN for absent values).

    The returned DataFrame carries two extra attributes on
    ``df.attrs`` so the orchestrator can surface them in
    :class:`WDIIngestResult`:

    - ``df.attrs["indicators_cached"]`` — count of catalog indicators
      that were read from the JSON cache.
    - ``df.attrs["indicators_fetched"]`` — count of catalog indicators
      that were HTTP-fetched in this call.

    Args:
        year: filter to a single year (e.g. ``2023``). If ``None``,
            every year present in the cache is loaded (the per-year
            cache layout is ``<year>/<CODE>.json``; the function
            iterates the cache_dir for year subdirectories in that
            case). The prototype's tests exercise both the
            single-year and the no-year paths; the CLI always passes
            a single year.
        indicator_codes: override the catalog. Default: read from
            catalog.
        catalog_path: override the indicator catalog. Default:
            checked-in catalog.
        cache_dir: override the JSON cache root. Default: data-lake
            path.
        force_refresh: re-download even when the cache file exists.
        request_timeout: per-request HTTP timeout in seconds.

    Returns:
        A pandas DataFrame with columns ``iso3``, ``year``, then one
        column per catalog indicator (named with the ``variable_name``).
        ``year`` is integer. Indicator columns are float (NaN = missing).

    Raises:
        FileNotFoundError: no cached file and no network reachability
            (or ``force_refresh=True`` and HTTP fails).
        requests.HTTPError: non-2xx WDI API response.
        ValueError: malformed JSON or a catalog code absent from the
            API.
    """
    specs = load_indicator_catalog(catalog_path=catalog_path)
    if indicator_codes is not None:
        wanted_codes = list(indicator_codes)
    else:
        wanted_codes = [s.raw_column for s in specs]

    cache_root = cache_dir or default_cache_dir()
    years_to_read = _resolve_years(year, cache_root)

    if not years_to_read:
        # Empty cache: return an empty wide frame with the expected
        # columns. The orchestrator still writes a 0-obs parquet /
        # run manifest; the end-to-end test asserts
        # ``observation_rows == 0`` for an empty cache.
        df = pd.DataFrame(columns=["iso3", "year"])
        df.attrs["indicators_cached"] = 0
        df.attrs["indicators_fetched"] = 0
        return df

    long_frames: list[pd.DataFrame] = []
    # Track unique indicators (not per-year) for the
    # ``indicators_cached`` / ``indicators_fetched`` counters. A
    # catalog indicator that has a cache file for *every* requested
    # year counts as 1 cached indicator; an indicator that needed an
    # HTTP call for *any* year counts as 1 fetched indicator. This
    # matches the design doc's intent ("how many of the catalog
    # indicators were read from cache" — not "how many cache
    # files").
    cached_codes: set[str] = set()
    fetched_codes: set[str] = set()

    for one_year in years_to_read:
        cache_year_dir = cache_root / str(one_year)
        if not cache_year_dir.is_dir():
            cache_year_dir.mkdir(parents=True, exist_ok=True)
        for code in wanted_codes:
            cache_path = cache_year_dir / f"{code}.json"
            payload, came_from_cache = fetch_wdi_payload(
                code, one_year, cache_path=cache_path,
                force_refresh=force_refresh, request_timeout=request_timeout,
            )
            if came_from_cache:
                cached_codes.add(code)
            else:
                fetched_codes.add(code)
            long_frames.append(
                parse_wdi_payload(payload, code=code, year=one_year)
            )

    long_df = pd.concat(long_frames, ignore_index=True)
    # Filter aggregate ISO3 codes (WDI region aggregations are noise
    # for country-level scoring; see docs/architecture/wdi.md §2.6).
    long_df = long_df.loc[
        ~long_df["iso3"].isin(_WDI_AGGREGATE_ISO3_CODES)
    ].reset_index(drop=True)
    # Wide pivot: one row per (iso3, year), one column per
    # indicator (named with the catalog's variable_name).
    wide = long_df.pivot_table(
        index=["iso3", "year"],
        columns="indicator_code",
        values="value",
        aggfunc="first",
    )
    # Rename raw WDI codes -> canonical variable_names from the
    # catalog. The catalog's variable_name is the public surface
    # the score modules consume.
    rename_map = {spec.raw_column: spec.variable_name for spec in specs}
    wide = wide.rename(columns=rename_map)
    wide = wide.reset_index()
    # Type coercion: year to int, indicator columns to float.
    wide["year"] = wide["year"].astype(int)
    for col in wide.columns:
        if col in {"iso3", "year"}:
            continue
        wide[col] = pd.to_numeric(wide[col], errors="coerce").astype(float)
    df = wide

    # Carry cached/fetched counts through df.attrs so the orchestrator
    # can populate WDIIngestResult.indicators_cached/_fetched without
    # re-inspecting the cache. Counts are in unique indicators, not
    # per (year, indicator) — see the loop above.
    df.attrs["indicators_cached"] = len(cached_codes)
    df.attrs["indicators_fetched"] = len(fetched_codes)
    return df


# ---------------------------------------------------------------------------
# Parquet write
# ---------------------------------------------------------------------------


def write_wdi_parquet(
    df: pd.DataFrame,
    parquet_path: Path | None = None,
    attribution: str | None = None,
) -> Path:
    """Persist the wide-format frame as parquet with attribution metadata.

    Mirrors :func:`vdem_io.write_vdem_parquet` and the
    :func:`vdem_io._attach_parquet_metadata` helper: writes the parquet
    via ``df.to_parquet``, then re-writes the file with the WDI
    attribution + source key attached as file-level schema metadata
    (Rule #15). Best-effort on the metadata rewrite — if pyarrow fails,
    the data parquet is still valid and a warning is logged.
    """
    out = parquet_path or default_processed_parquet_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, engine="pyarrow", index=False)
    _attach_parquet_metadata(out, attribution=attribution or WDI_ATTRIBUTION)
    return out


def _attach_parquet_metadata(parquet_path: Path, *, attribution: str) -> None:
    """Attach the WDI attribution + source key to the parquet's schema metadata.

    pyarrow exposes arbitrary UTF-8 metadata on the schema. We rewrite
    the parquet in place to add it. This is best-effort: if the
    rewrite fails (corrupt file, race, full disk) the parquet remains
    valid and we log a warning. Schema/data errors are NOT swallowed
    silently — they re-raise so the orchestrator can decide.
    """
    try:
        table = pq.read_table(parquet_path)
        meta = dict(table.schema.metadata or {})
        meta[_PARQUET_META_ATTRIBUTION] = attribution.encode("utf-8")
        meta[_PARQUET_META_SOURCE_KEY] = WDI_SOURCE_KEY.encode("utf-8")
        new_table = table.replace_schema_metadata(meta)
        pq.write_table(new_table, parquet_path, compression="snappy")
    except (OSError, pq.ArrowException) as exc:
        # Transient I/O or pyarrow error. The data is intact; the audit
        # metadata is lost. Log and continue — the attribution is
        # also carried in the run manifest, so the audit trail survives.
        _logger.warning(
            "Failed to attach WDI attribution metadata to %s: %s. "
            "The data parquet is valid; the run manifest is the audit fallback.",
            parquet_path,
            exc,
        )


__all__ = [
    "WDI_ATTRIBUTION",
    "WDI_SOURCE_KEY",
    "IndicatorSpec",
    "default_cache_dir",
    "default_processed_parquet_path",
    "load_indicator_catalog",
    "read_wdi",
    "write_wdi_parquet",
]
