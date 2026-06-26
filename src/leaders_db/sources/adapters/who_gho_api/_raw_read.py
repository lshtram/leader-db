"""Raw cache reader for the clean WHO GHO API adapter.

Reads the per-``(year, IndicatorCode)`` JSON cache files from
``<raw_root>/who_gho_api/cache/<year>/<IndicatorCode>.json``
through the lazy legacy catalog + parser. The legacy parser is
the canonical Stage 2 reader (per
``docs/architecture/sources.md`` §5.3 -- the WDI / WGI / UCDP /
SIPRI / PTS / UNDP HDI pattern: "reuse the legacy parser, do
not duplicate parsing logic").

The cache-first HTTP-fallback contract of the legacy
:func:`read_who_gho_api` is preserved by the readiness gate
above: the unified adapter NEVER falls through to HTTP because
``check_cache_availability`` blocks unsupported cache policies
AND incomplete explicit-year requests before ``read_raw`` is
called. The ``cache_policy="prefer_cache"`` default falls back
to the legacy cache-first read; in this slice the readiness gate
treats ``prefer_cache`` and ``offline_only`` identically (the
adapter never invokes the network once readiness passes).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from leaders_db.sources.contracts import RawAsset, RawReadResult, SourceIngestRequest

from ._constants import (
    WHO_GHO_API_CACHE_DIR_NAME,
    WHO_GHO_API_DEFAULT_VERSION,
    WHO_GHO_API_INDICATOR_CODES,
    WHO_GHO_API_SOURCE_KEY,
)
from ._readiness import (
    _enumerate_cache_files,
    cache_root,
    metadata_path,
    read_metadata,
)


def read_who_gho_api_cache(request: SourceIngestRequest) -> RawReadResult:
    """Read the WHO GHO API cache through the legacy parser via lazy imports.

    Steps:

    1. Enumerate every valid ``(year, IndicatorCode)`` cache file
       on disk (the readiness gate already proved the cache policy
       is supported + the explicit-year requests have complete
       cache).
    2. Iterate the valid files, read each via
       :func:`leaders_db.ingest.who_gho_api_io.parse_who_gho_api_payload`
       (the canonical Stage 2 long-format parser).
    3. Return the long-format frames wrapped in a
       :class:`RawReadResult` plus a :class:`RawAsset` per
       enumerated cache file. The transform layer pivots the
       long frames to wide + applies the request year / country
       filters.

    Imports from ``leaders_db.ingest`` are intentionally local so
    importing ``leaders_db.sources.adapters.who_gho_api`` does not
    pull in legacy ingest at module-import time (verified by
    ``test_who_gho_api_adapter_import_does_not_import_legacy_ingest``
    in the unified test suite).

    Args:
        request: the unified :class:`SourceIngestRequest`.

    Returns:
        :class:`RawReadResult` with one :class:`RawAsset` per
        enumerated cache file and a ``payload`` dict containing
        the long-format pandas DataFrame, the catalog specs, a
        ``(iso3, year, indicator_code) -> raw_value`` lookup for
        the audit trail, and the raw metadata payload.
    """
    from leaders_db.ingest.who_gho_api_io import (
        load_indicator_catalog,
        parse_who_gho_api_payload,
    )

    cache_root_path = cache_root(request)
    valid, _malformed = _enumerate_cache_files(cache_root_path)

    metadata = read_metadata(metadata_path(request))
    specs = load_indicator_catalog()

    requested_years: set[int] | None = (
        {int(year) for year in request.years}
        if request.years else None
    )

    long_frames: list[Any] = []
    assets: list[RawAsset] = []
    for year_int, code, cache_file in valid:
        if requested_years is not None and year_int not in requested_years:
            continue
        if code not in WHO_GHO_API_INDICATOR_CODES:
            # Cache files outside the in-scope catalog are silently
            # ignored (the readiness gate enumerates every JSON in
            # the cache root; non-catalog files are harmless).
            continue
        payload = _json_load(cache_file)
        long_df = parse_who_gho_api_payload(
            payload, code=code, year=year_int,
        )
        if long_df is None or getattr(long_df, "empty", False):
            continue
        long_frames.append(long_df)
        assets.append(_build_asset(
            request=request,
            cache_file=cache_file,
            year=year_int,
            code=code,
            source_url=_metadata_source_url(metadata),
        ))

    raw_value_lookup = _build_raw_value_lookup(long_frames)

    return RawReadResult(
        source_id=request.source_id,
        assets=tuple(assets),
        payload={
            "long_frames": long_frames,
            "specs": specs,
            "metadata": metadata,
            "raw_value_lookup": raw_value_lookup,
            "cache_root": str(cache_root_path),
        },
    )


def _build_asset(
    *,
    request: SourceIngestRequest,
    cache_file: Path,
    year: int,
    code: str,
    source_url: str | None,
) -> RawAsset:
    """Build a :class:`RawAsset` record for one cache file."""
    asset_id = f"{WHO_GHO_API_SOURCE_KEY}:cache:{year}:{code}"
    return RawAsset(
        asset_id=asset_id,
        source_id=request.source_id,
        version=WHO_GHO_API_DEFAULT_VERSION,
        media_type="application/json",
        path=cache_file,
        url=source_url,
        checksum_sha256=None,
        retrieved_at=None,
        immutable=True,
    )


def _metadata_source_url(metadata: dict[str, object]) -> str | None:
    """Return the canonical WHO GHO API source URL from the metadata payload."""
    source_url = metadata.get("source_url")
    if isinstance(source_url, str) and source_url.strip():
        return source_url.strip()
    return None


def _json_load(cache_file: Path) -> dict[str, object]:
    """Read a WHO GHO API cache JSON file.

    The readiness gate already proved the file is JSON and
    structurally valid, so this helper just opens it.
    """
    text = cache_file.read_text(encoding="utf-8")
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError(
            f"WHO GHO API cache file {cache_file} is not a JSON "
            f"object (got {type(payload).__name__})"
        )
    return payload


def _build_raw_value_lookup(
    long_frames: list[Any],
) -> dict[tuple[str, int, str], str]:
    """Build a ``(iso3, year, indicator_code) -> raw_value`` lookup.

    Mirrors the legacy ``<variable_name>_raw_value`` wide column:
    preserves the verbatim ``Value`` field (e.g.
    ``"76.4 [76.3-76.5]"`` with bounds) for the audit trail so
    the transform layer can emit it on each
    :class:`NormalizedObservation`.

    The WHO GHO API may return multiple ``COUNTRY`` records per
    ``(iso3, year, indicator_code)`` (e.g. WEALTHQUINTILE_WQ5 +
    WEALTHQUINTILE_TOTL disaggregations on
    ``MDG_0000000007``). The legacy Stage 2 reader uses
    ``pd.pivot_table(..., aggfunc="first")`` to pick the first
    value per ``(iso3, year, indicator)`` -- this helper
    preserves that "first-match wins" semantics by NOT
    overwriting existing keys.
    """
    lookup: dict[tuple[str, int, str], str] = {}
    for frame in long_frames:
        if frame is None or getattr(frame, "empty", True):
            continue
        for row in frame.itertuples(index=False):
            iso3 = _str(getattr(row, "iso3", None))
            year = _int(getattr(row, "year", None))
            code = _str(getattr(row, "indicator_code", None))
            raw_value = _str(getattr(row, "raw_value", None))
            if not iso3 or year is None or not code:
                continue
            key = (iso3, year, code)
            if key not in lookup:
                lookup[key] = raw_value
    return lookup


def _str(value: object) -> str:
    if value is None:
        return ""
    try:
        if _pd_isna(value):
            return ""
    except (ImportError, TypeError, ValueError):
        pass
    return str(value).strip()


def _int(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _pd_isna(value: object) -> bool:
    """Return ``True`` if ``value`` is NaN/NaT/None."""
    try:
        import pandas as pd
    except ImportError:
        return False
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


__all__ = [
    "read_who_gho_api_cache",
]


# Reference WHO_GHO_API_CACHE_DIR_NAME / WHO_GHO_API_SOURCE_KEY so the
# imports above stay live for future audit-trail hooks that need
# the cache dir name string. The constants are also re-exported
# from the package ``__init__`` for downstream callers.
_ = (WHO_GHO_API_CACHE_DIR_NAME, WHO_GHO_API_SOURCE_KEY)
