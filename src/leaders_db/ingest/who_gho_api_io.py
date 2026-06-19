"""Stage 2 -- WHO Global Health Observatory (GHO) OData API: catalog + paths.

This module is the I/O half of the WHO GHO API adapter. It owns:

- :data:`WHO_GHO_API_SOURCE_KEY` and :data:`WHO_GHO_API_ATTRIBUTION` --
  module-level constants consumed by the DB layer and the orchestrator.
- :class:`IndicatorSpec` -- one row of the catalog, typed. The
  catalog extends the standard Stage 2 shape with a ``dim1_filter``
  field (the OData ``Dim1`` filter to apply for SEX-disaggregated
  indicators; empty if the indicator has no SEX dimension).
- :func:`load_indicator_catalog` -- read the catalog CSV (handles
  the leading ``#`` comment block + comment-only line filtering).
- :func:`default_cache_dir` / :func:`default_processed_parquet_path` --
  the conventional data-lake locations.
- :func:`parse_who_gho_api_payload` -- the WHO GHO OData response
  parser (turns a ``{"@odata.context": ..., "value": [...]}``
  response into a long-format ``pandas.DataFrame``; filters
  non-country ``SpatialDimType`` records). The parser lives in
  the I/O module (not the HTTP module) per the WDI / WGI / UCDP /
  SIPRI / PTS / UNDP HDI split pattern: the http module owns
  the network + cache I/O, the I/O module owns the
  response-shape -> long DataFrame parser.
- :func:`write_who_gho_api_parquet` -- persist the narrow frame as
  parquet with the WHO GHO API attribution attached to the schema
  metadata.

The HTTP-specific layer (URL building, the requests call, the
retry policy, the response parser, the cache I/O helpers) lives in
:mod:`who_gho_api_http`. The DB-side functions live in
:mod:`who_gho_api_db`. The orchestrator that ties everything
together lives in :mod:`who_gho_api`.

The WHO GHO API v1 (OData 4.0, Azure-backed, public, no auth) is
documented at https://www.who.int/data/gho/info/gho-odata-api. The
Stage 2 contract is:

- One HTTP call per uncached ``(indicator_code, year)`` pair.
- The default response is a JSON object with a ``value`` array
  (no wrapping envelope). Each element carries ``IndicatorCode``,
  ``SpatialDimType``, ``SpatialDim`` (ISO3 country code for
  country-level records), ``TimeDim`` (year as int), ``Dim1``
  (disaggregation, e.g. ``SEX_BTSX`` / ``SEX_MLE`` / ``SEX_FMLE``
  / ``None``), ``Value`` (display string with bounds), and
  ``NumericValue`` (the float the score module consumes).
- The API has a hard $top cap of 1000. For a year-filtered
  ``(country, both-sexes)`` query the response is < 1000 records so
  no pagination is needed. The reader is defensive anyway: it
  iterates pages with ``$skip`` if a ``@odata.nextLink`` is
  present.
- ``SpatialDimType`` other than ``COUNTRY`` (e.g. ``REGION``,
  ``WORLDBANKINCOMEGROUP``, ``GLOBAL``) is filtered out so the
  Stage 2 frame is country-only.

For the prototype we filter on ``Dim1 eq 'SEX_BTSX'`` (both-sexes
aggregate) for the SEX-disaggregated indicators so the frame is
one row per ``(country, year)`` -- per the catalog. Indicators
that have no SEX dimension (immunization coverage) skip the
``Dim1`` filter. The 5 in-scope indicators are all in
``social_wellbeing`` per the architecture §3.
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq

from ..paths import processed_dir, raw_dir

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Source key used everywhere in the data lake + CLI dispatch. Lives
#: here (the lowest-level module that does NOT import from siblings)
#: so ``who_gho_api_db`` can import it from us, and ``who_gho_api``
#: can re-export it.
WHO_GHO_API_SOURCE_KEY: str = "who_gho_api"

#: Stable WHO GHO API attribution block. The canonical text lives in
#: ``docs/source-attributions.md`` (``who_gho_api`` section, lines
#: 177-183 + the citation-cheat-sheet summary table row). This
#: constant must be a substring of that doc; the
#: :func:`test_who_gho_api_attribution_matches_attributions_doc`
#: test enforces byte-for-byte consistency (Always-On Rule #15).
#: The constant lives here to break the import cycle:
#: ``who_gho_api_db`` imports it from us, and ``who_gho_api``
#: re-exports it.
WHO_GHO_API_ATTRIBUTION: str = (
    "World Health Organization. *Global Health Observatory*. "
    "Geneva: WHO. https://www.who.int/data/gho"
)

#: Default location of the indicator catalog. Lives here so
#: :func:`write_who_gho_api_run_manifest` in ``who_gho_api_db`` can
#: import it without a cycle.
_DEFAULT_CATALOG_PATH: Path = (
    Path(__file__).resolve().parent / "catalogs" / "who_gho_api.csv"
)

#: Narrow parquet that Stage 2 writes under ``data/processed/who_gho_api/``.
_PROCESSED_PARQUET_NAME: str = "who_gho_api_country_year.parquet"

#: Parquet file-level metadata keys (UTF-8 bytes for pyarrow schema.metadata).
_PARQUET_META_ATTRIBUTION: str = "who_gho_api_attribution"
_PARQUET_META_SOURCE_KEY: str = "who_gho_api_source_key"

#: The static filter the reader applies to drop non-country records
#: (REGION, WORLDBANKINCOMEGROUP, GLOBAL, etc.). Per the WHO GHO
#: OData API, country-level records are tagged
#: ``SpatialDimType eq 'COUNTRY'`` and the ``SpatialDim`` value is
#: the ISO3 country code.
_COUNTRY_SPATIAL_DIM_TYPE: str = "COUNTRY"

#: The default ``Dim1`` filter for SEX-disaggregated indicators --
#: both-sexes aggregate. The catalog's ``dim1_filter`` field is the
#: per-spec override; this is the default used when the catalog
#: field is non-empty.
_DEFAULT_DIM1_BOTH_SEXES: str = "SEX_BTSX"

#: API ``$top`` cap. The WHO GHO API rejects ``$top > 1000`` with a
#: 400 response. The reader is defensive about pagination (uses
#: ``@odata.nextLink``) but the year + SEX_BTSX + COUNTRY filter
#: combinator returns < 1000 records in practice, so pagination is
#: rarely triggered.
_API_TOP_CAP: int = 1000


# ---------------------------------------------------------------------------
# IndicatorSpec
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IndicatorSpec:
    """One row of the WHO GHO API indicator catalog.

    Mirrors the V-Dem / WDI / WGI / UCDP / SIPRI milex / SIPRI
    Yearbook Ch.7 / PTS / UNDP HDI :class:`IndicatorSpec` shape, with
    one extension: the WHO GHO API catalog needs a ``dim1_filter``
    field to scope SEX-disaggregated indicators to the both-sexes
    aggregate. Empty string when the indicator has no SEX dimension.

    Every Stage 2 adapter resolves its raw column from this
    dataclass so the score modules in Stage 9-10 can normalize and
    direct indicators consistently across sources.
    """

    variable_name: str
    raw_column: str
    rating_category: str
    raw_scale: str
    normalized_scale_target: str
    higher_is_better: bool
    unit: str
    dim1_filter: str
    description: str

    @classmethod
    def from_csv_row(cls, row: dict[str, str]) -> IndicatorSpec:
        """Build a spec from one CSV row.

        The catalog uses ``higher_is_better=1`` for "higher is
        better" and ``0`` otherwise (the V-Dem / WDI / WGI / UCDP /
        SIPRI milex / SIPRI Yearbook Ch.7 / PTS / UNDP HDI
        convention). The constructor normalizes both string and
        bool values to a real ``bool``. Empty / missing values in
        the optional fields become ``""``.
        """
        raw_higher = row.get("higher_is_better", "1")
        if isinstance(raw_higher, bool):
            higher_is_better = raw_higher
        else:
            higher_is_better = (
                str(raw_higher).strip().lower() in {"1", "true", "yes"}
            )
        return cls(
            variable_name=row["variable_name"],
            raw_column=row["raw_column"],
            rating_category=row["rating_category"],
            raw_scale=row["raw_scale"],
            normalized_scale_target=row["normalized_scale_target"],
            higher_is_better=higher_is_better,
            unit=row.get("unit", "").strip(),
            dim1_filter=row.get("dim1_filter", "").strip(),
            description=row.get("description", "").strip(),
        )


def load_indicator_catalog(
    catalog_path: Path | None = None,
) -> list[IndicatorSpec]:
    """Load the WHO GHO API indicator catalog from ``catalogs/who_gho_api.csv``.

    Mirrors the V-Dem / WDI / WGI / UCDP / SIPRI / PTS / UNDP HDI
    loaders: handles the leading ``#`` comment block, drops
    comment-only lines, validates the required column set, and
    returns one :class:`IndicatorSpec` per data row in file order.

    The required column set is the 9 columns of the WHO GHO API
    catalog (8 standard + 1 GHO-specific ``dim1_filter``):
    ``variable_name``, ``raw_column``, ``rating_category``,
    ``raw_scale``, ``normalized_scale_target``, ``higher_is_better``,
    ``unit``, ``dim1_filter``, ``description``.

    Raises:
        FileNotFoundError: if the catalog file is missing.
        ValueError: if a required column is missing in the catalog
            header.
    """
    path = catalog_path or _DEFAULT_CATALOG_PATH
    if not path.is_file():
        raise FileNotFoundError(
            f"WHO GHO API indicator catalog not found: {path}"
        )

    required = {
        "variable_name",
        "raw_column",
        "rating_category",
        "raw_scale",
        "normalized_scale_target",
        "higher_is_better",
        "unit",
        "dim1_filter",
        "description",
    }

    # Read raw lines, drop comment-only lines, then hand the cleaned
    # text to csv.DictReader. Comment-only means: stripped line
    # starts with ``#`` or is blank. Inline ``#`` characters inside
    # a data row are preserved.
    cleaned_lines: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        cleaned_lines.append(raw_line)
    if not cleaned_lines:
        raise ValueError(
            f"WHO GHO API catalog {path} has no data rows after "
            "stripping comments"
        )

    reader = csv.DictReader(cleaned_lines)
    missing = required - set(reader.fieldnames or ())
    if missing:
        raise ValueError(
            f"WHO GHO API catalog {path} is missing required "
            f"columns: {sorted(missing)}"
        )

    specs: list[IndicatorSpec] = []
    for row in reader:
        if not row.get("variable_name"):
            continue
        specs.append(IndicatorSpec.from_csv_row(row))
    return specs


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------


def parse_who_gho_api_payload(
    payload: dict[str, Any] | list[Any],
    *,
    code: str,
    year: int,
) -> pd.DataFrame:
    """Parse a WHO GHO OData response into a long-format DataFrame.

    Returns a frame with columns ``["iso3", "year", "indicator_code",
    "value", "raw_value", "spatial_dim_type", "dim1", "value_str"]``.
    Rows where ``NumericValue`` is null/missing are kept (the
    orchestrator's NaN conversion handles the missing-data path).
    Non-country ``SpatialDimType`` records (REGION,
    WORLDBANKINCOMEGROUP, GLOBAL) are filtered out at the parser
    level so the wide frame is country-only.

    The ``raw_value`` column preserves the verbatim ``Value`` field
    (e.g. ``"48.0 [46.7-49.6]"`` with bounds) for the
    ``source_observations.raw_value`` audit-trail. The ``value``
    column is the float from ``NumericValue`` (``None`` when
    missing).

    Args:
        payload: a parsed WHO GHO OData response (the
            ``{"@odata.context": ..., "value": [...]}`` shape). A
            list is also accepted (the API occasionally returns a
            bare array in error paths; we treat it as a value list).
        code: the indicator code (used as the ``indicator_code``
            column value; defensive against records that omit it).
        year: the requested year (used as the ``year`` column
            value; the ``TimeDim`` field on the record is preserved
            as a sanity check but the caller's year wins if they
            conflict because the Stage 2 frame is year-scoped at
            the reader level).
    """
    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict):
        records = payload.get("value", [])
    else:
        raise ValueError(
            f"WHO GHO API response for {code} year {year} is not a "
            f"dict or list; got {type(payload).__name__}"
        )
    if not isinstance(records, list):
        raise ValueError(
            f"WHO GHO API response for {code} year {year} .value is "
            f"not a list; got {type(records).__name__}"
        )

    rows: list[dict[str, object]] = []
    for entry in records:
        if not isinstance(entry, dict):
            continue
        # Defensive: filter out non-country records at the parser
        # level so the wide frame is country-only. The reader
        # layer also filters, but doing it here keeps the cache
        # contract explicit (the cache stores the verbatim API
        # response; the parser produces the country-only long
        # frame).
        spatial_dim_type = entry.get("SpatialDimType") or ""
        if spatial_dim_type != _COUNTRY_SPATIAL_DIM_TYPE:
            continue
        iso3 = entry.get("SpatialDim")
        if not isinstance(iso3, str) or len(iso3) != 3:
            # Empty SpatialDim, or a non-3-letter code (defensive).
            continue
        # The API uses ``Dim1`` for the SEX dimension; some
        # indicators do not disaggregate and emit null. Preserve
        # the raw value for the audit trail.
        dim1 = entry.get("Dim1")
        # The API's ``NumericValue`` is the float the score
        # module consumes. When the API has no data, the field is
        # null -- leave ``value`` as None and let the orchestrator
        # convert to NaN.
        numeric_value = entry.get("NumericValue")
        value_str = entry.get("Value") or ""
        indicator_code = entry.get("IndicatorCode") or code
        try:
            time_dim_value = int(entry.get("TimeDim") or year)
        except (TypeError, ValueError):
            time_dim_value = int(year)
        rows.append(
            {
                "iso3": str(iso3).strip().upper(),
                "year": int(year),
                "indicator_code": str(indicator_code),
                "value": (
                    float(numeric_value)
                    if isinstance(numeric_value, (int, float))
                    else None
                ),
                "raw_value": str(value_str),
                "spatial_dim_type": str(spatial_dim_type),
                "dim1": (str(dim1) if dim1 is not None else None),
                "time_dim": time_dim_value,
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "iso3",
            "year",
            "indicator_code",
            "value",
            "raw_value",
            "spatial_dim_type",
            "dim1",
            "time_dim",
        ],
    )


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def default_cache_dir() -> Path:
    """Return the conventional WHO GHO API JSON cache root.

    Layout: ``<project_root>/data/raw/who_gho_api/cache/``. Per-year
    subdirectories hold one ``<raw_column>.json`` per indicator.
    Creates the cache root directory if missing so a caller can
    write into it without an extra ``mkdir`` call.
    """
    cache = raw_dir(WHO_GHO_API_SOURCE_KEY) / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    return cache


def default_processed_parquet_path() -> Path:
    """Return the conventional WHO GHO API narrow parquet path.

    Creates the ``data/processed/who_gho_api/`` directory if
    missing.
    """
    processed_dir(WHO_GHO_API_SOURCE_KEY).mkdir(parents=True, exist_ok=True)
    return processed_dir(WHO_GHO_API_SOURCE_KEY) / _PROCESSED_PARQUET_NAME


# ---------------------------------------------------------------------------
# Parquet write
# ---------------------------------------------------------------------------


def write_who_gho_api_parquet(
    df: pd.DataFrame,
    parquet_path: Path | None = None,
    attribution: str | None = None,
) -> Path:
    """Persist the wide-format frame as parquet with attribution metadata.

    Mirrors the WDI / UNDP HDI pattern: writes the parquet via
    ``df.to_parquet``, then re-writes the file with the WHO GHO API
    attribution + source key attached as file-level schema metadata
    (Rule #15). Best-effort on the metadata rewrite -- if pyarrow
    fails, the data parquet is still valid and a warning is logged.
    """
    out = parquet_path or default_processed_parquet_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, engine="pyarrow", index=False)
    _attach_parquet_metadata(
        out, attribution=attribution or WHO_GHO_API_ATTRIBUTION
    )
    return out


def _attach_parquet_metadata(parquet_path: Path, *, attribution: str) -> None:
    """Attach the WHO GHO API attribution + source key to the parquet's schema metadata.

    pyarrow exposes arbitrary UTF-8 metadata on the schema. We
    rewrite the parquet in place to add it. This is best-effort: if
    the rewrite fails (corrupt file, race, full disk) the parquet
    remains valid and we log a warning. Schema/data errors are NOT
    swallowed silently -- they re-raise so the orchestrator can
    decide.
    """
    try:
        table = pq.read_table(parquet_path)
        meta = dict(table.schema.metadata or {})
        meta[_PARQUET_META_ATTRIBUTION] = attribution.encode("utf-8")
        meta[_PARQUET_META_SOURCE_KEY] = WHO_GHO_API_SOURCE_KEY.encode("utf-8")
        new_table = table.replace_schema_metadata(meta)
        pq.write_table(new_table, parquet_path, compression="snappy")
    except (OSError, pq.ArrowException) as exc:
        _logger.warning(
            "Failed to attach WHO GHO API attribution metadata to %s: %s. "
            "The data parquet is valid; the run manifest is the audit fallback.",
            parquet_path,
            exc,
        )


__all__ = [
    "WHO_GHO_API_ATTRIBUTION",
    "WHO_GHO_API_SOURCE_KEY",
    "IndicatorSpec",
    "default_cache_dir",
    "default_processed_parquet_path",
    "load_indicator_catalog",
    "parse_who_gho_api_payload",
    "write_who_gho_api_parquet",
]
