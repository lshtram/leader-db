"""Raw cache reader for the clean Wikidata heads-of-state-and-government adapter.

Reads the per-``(year, country_qids)`` JSON cache files from
``<raw_root>/wikidata_heads_of_state_government/cache/<cache_key>.json``
through the lazy legacy parser. The legacy parser is the
canonical Stage 2 reader (per ``docs/architecture/sources.md``
§5.3 -- the WDI / WGI / UCDP / SIPRI / PTS / UNDP HDI / WHO GHO
API pattern: "reuse the legacy parser, do not duplicate parsing
logic").

The cache-first HTTP-fallback contract of the legacy
:func:`read_wikidata_heads_of_state_government` is preserved by
the readiness gate above: the unified adapter NEVER falls through
to HTTP because :func:`check_cache_availability` blocks
unsupported cache policies AND incomplete explicit-year requests
before ``read_raw`` is called. The
``cache_policy="prefer_cache"`` default falls back to the legacy
cache-first read; in this slice the readiness gate treats
``prefer_cache`` and ``offline_only`` identically (the adapter
never invokes the network once readiness passes).

Years semantics
---------------

The unified adapter reads the cache file matching the FIRST
requested year (the legacy orchestrator issues one SPARQL query
per ``(year, country_qids)`` parameter set with all offices in
the catalog scoped via ``VALUES``). For ``years=None`` (the
all-current-holders run) the adapter enumerates every cache file
on disk and the parser reads each cache's bindings. The transform
layer preserves the original ``start_date`` / ``end_date``
qualifiers on every emitted observation's extension payload so
downstream audit code can see the full temporal envelope of each
binding. For multi-year explicit requests the readiness gate
fails with a structured blocker; the legacy orchestrator's
per-year cache layout is preserved.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from leaders_db.sources.contracts import (
    RawAsset,
    RawReadResult,
    SourceIngestRequest,
)

from ._constants import (
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_CACHE_DIR_NAME,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_DEFAULT_VERSION,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_METADATA_NAME,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_KEY,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SPARQL_ENDPOINT_URL,
)
from ._paths import (
    cache_file,
    canonical_template_hash,
    current_cache_file,
)
from ._readiness import metadata_path, read_metadata
from ._request_warnings import normalize_country_qids as _normalize_country_qids


def read_wikidata_heads_of_state_government_cache(
    request: SourceIngestRequest,
) -> RawReadResult:
    """Read the Wikidata SPARQL JSON cache through the legacy parser.

    Steps:

    1. Locate the per-``(year, country_qids)`` cache file for the
       first requested year (the legacy orchestrator issues one
       SPARQL query per parameter set); for ``years=None``
       enumerate every cache file on disk.
    2. Read the verbatim JSON payload from each cache file via
       the lazy-imported legacy catalog + parser so the canonical
       Stage 2 long-format DataFrame is reused without
       duplication.
    3. Build :class:`RawAsset` records for every read cache file
       (the asset id is the cache key basename so audit-trail
       locators can be reconstructed from a parquet row).
    4. Carry the long-format DataFrame + the legacy catalog
       specs + the raw metadata + the cache root + the parsed
       cache-key payload on the :class:`RawReadResult.payload`
       so the transform layer can pivot the long frame to per-
       binding :class:`NormalizedObservation` records.

    Imports from ``leaders_db.ingest`` are intentionally local so
    importing ``leaders_db.sources.adapters.wikidata_heads_of_state_government``
    does not pull in legacy ingest at module-import time
    (verified by
    ``test_importing_wikidata_heads_of_state_government_adapter_does_not_import_legacy_ingest``
    in the unified test suite).

    Args:
        request: the unified :class:`SourceIngestRequest`.

    Returns:
        :class:`RawReadResult` with one :class:`RawAsset` per read
        cache file and a ``payload`` dict containing the long-
        format pandas DataFrame, the catalog specs, the parsed
        metadata, the cache root path, and the read cache-key
        payload list (the verbatim JSON dict per cache file).
    """
    from leaders_db.ingest.wikidata_heads_of_state_government_io import (
        load_indicator_catalog,
    )
    cache_root_path = _cache_root(request)
    metadata = read_metadata(metadata_path(request))
    specs = load_indicator_catalog()

    cache_files = _select_cache_files(request, cache_root_path)

    long_frames: list[Any] = []
    raw_payloads: list[tuple[str, dict[str, Any]]] = []
    assets: list[RawAsset] = []
    for cache_file_path, payload, cache_kind in cache_files:
        cache_key = cache_file_path.stem
        long_df = _parse_cache_payload(
            cache_key=cache_key,
            cache_kind=cache_kind,
            payload=payload,
            specs=specs,
        )
        if long_df is None or getattr(long_df, "empty", False):
            continue
        long_frames.append(long_df)
        raw_payloads.append((cache_key, payload))
        assets.append(
            _build_asset(
                request=request,
                cache_file_path=cache_file_path,
                cache_key=cache_key,
                payload=payload,
            )
        )

    return RawReadResult(
        source_id=request.source_id,
        assets=tuple(assets),
        payload={
            "long_frames": long_frames,
            "specs": specs,
            "metadata": metadata,
            "cache_root": str(cache_root_path),
            "raw_payloads": raw_payloads,
            "request_countries": _normalize_country_qids(
                request.countries
            ),
        },
    )


def _cache_root(request: SourceIngestRequest) -> Path:
    """Return the canonical cache root directory."""
    return Path(request.raw_root) / (
        f"{WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_KEY}"
        f"/{WIKIDATA_HEADS_OF_STATE_GOVERNMENT_CACHE_DIR_NAME}"
    )


def _select_cache_files(
    request: SourceIngestRequest,
    cache_root_path: Path,
) -> list[tuple[Path, dict[str, Any], str]]:
    """Return the cache files matching the request's year / country scope.

    The unified adapter follows the legacy orchestrator's
    single-cache-per-parameter-set pattern: for ``years=(YYYY,)``
    read only the cache file matching the first requested year;
    for ``years=None`` read only the canonical current-holders
    cache file (``wd_ALL_current_...``). The reader does NOT
    enumerate every cache file on disk because the legacy
    orchestrator issues one SPARQL query per parameter set and
    each cache file corresponds to one parameter set.
    """
    if not cache_root_path.is_dir():
        return []
    if not request.years:
        target = current_cache_file(request)
    else:
        countries = _normalize_country_qids(request.countries)
        first_year = int(request.years[0])
        target = cache_file(
            request,
            year=first_year,
            country_qids=countries,
            query_template_hash=canonical_template_hash(),
        )
    selected = _read_cache_payload(target)
    if selected is not None:
        return [(target, selected, "wd")]
    if request.years and request.countries is None:
        recent_target = _recent_rulers_cache_file(
            cache_root_path, year=int(request.years[0]),
        )
        selected = _read_cache_payload(recent_target)
        if selected is not None:
            return [(recent_target, selected, "cyc")]
    return []


def _read_cache_payload(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _recent_rulers_cache_file(cache_root_path: Path, *, year: int) -> Path:
    """Return the canonical Chronicle recent-rulers cache file for ``year``.

    The Chronicle cache is a Wikidata SPARQL response with projected ISO3
    values. It is safe to consume here because it lives under the same
    source bundle and preserves verbatim Wikidata bindings.
    """
    from leaders_db.chronicle._wikidata_recent_rulers import _cache_key

    return cache_root_path / f"{_cache_key(year=year)}.json"


def _parse_cache_payload(
    *,
    cache_key: str,
    cache_kind: str,
    payload: dict[str, Any],
    specs: Iterable[Any],
) -> Any:
    if cache_kind == "cyc":
        return _parse_recent_rulers_payload(cache_key, payload)
    from leaders_db.ingest.wikidata_heads_of_state_government_parse import (
        parse_sparql_bindings,
    )

    office_qids = [getattr(spec, "raw_column", "") for spec in specs]
    office_qid = office_qids[0] if office_qids else "ALL"
    return parse_sparql_bindings(
        payload, office_qid=office_qid, year=_year_from_cache_key(cache_key),
    )


def _parse_recent_rulers_payload(
    cache_key: str,
    payload: dict[str, Any],
) -> Any:
    from leaders_db.chronicle._wikidata_recent_rulers import (
        parse_recent_rulers_payload,
    )

    year = _year_from_cache_key(cache_key)
    if year is None:
        year = 0
    frame = parse_recent_rulers_payload(payload, year=year)
    if getattr(frame, "empty", True):
        return frame
    raw_values = [
        json.dumps(binding, ensure_ascii=False)
        for binding in payload.get("results", {}).get("bindings", [])
        if isinstance(binding, dict)
    ]
    frame = frame.rename(
        columns={
            "iso3": "country_iso3",
            "role_qid": "role_qid",
        }
    )
    frame["requested_year"] = int(year)
    frame["raw_value"] = raw_values[: len(frame)]
    frame["statement_uri"] = ""
    frame["binding_index"] = range(len(frame))
    return frame


def _build_asset(
    *,
    request: SourceIngestRequest,
    cache_file_path: Path,
    cache_key: str,
    payload: dict[str, object],
) -> RawAsset:
    """Build a :class:`RawAsset` record for one cache file."""
    asset_id = (
        f"{WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_KEY}:cache:{cache_key}"
    )
    return RawAsset(
        asset_id=asset_id,
        source_id=request.source_id,
        version=WIKIDATA_HEADS_OF_STATE_GOVERNMENT_DEFAULT_VERSION,
        media_type="application/json",
        path=cache_file_path,
        url=WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SPARQL_ENDPOINT_URL,
        checksum_sha256=None,
        retrieved_at=None,
        immutable=True,
    )


def _year_from_cache_key(cache_key: str) -> int | None:
    """Return the ``year`` embedded in a legacy cache key, or ``None``.

    Legacy cache-key format:
    ``wd_ALL_<year>_<country_hash>_<template_hash>``. The
    ``<year>`` slot is ``YYYY`` for explicit-year requests and
    ``current`` for the all-current-holders run (which the
    parser treats as a non-explicit-year run; the parser's
    ``year`` argument only stamps the ``requested_year`` audit
    column).
    """
    parts = cache_key.split("_")
    if len(parts) < 4:
        return None
    year_token = parts[1] if parts[0] == "cyc" else parts[2]
    if not year_token.isdigit():
        return None
    return int(year_token)


__all__ = [
    "read_wikidata_heads_of_state_government_cache",
]


# Reference metadata name / source key so the import above stays
# live for future audit-trail hooks that need the bundle metadata
# filename string. The constants are also re-exported from the
# package ``__init__`` for downstream callers.
_ = (
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_METADATA_NAME,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_KEY,
)
