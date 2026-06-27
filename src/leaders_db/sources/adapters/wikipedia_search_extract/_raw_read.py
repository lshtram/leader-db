"""Raw cache reader for the clean Wikipedia Action API adapter.

Reads the per-``(query, action)`` JSON cache files from
``<raw_root>/wikipedia_search_extract/cache/<cache_key>.json`` through
the lazy legacy parser. The legacy parser is the canonical Stage 2
reader (per ``docs/architecture/sources.md`` §5.3 -- the WDI / WGI /
UCDP / SIPRI / PTS / UNDP HDI / WHO GHO API / Wikidata / FAS pattern:
"reuse the legacy parser, do not duplicate parsing logic").

The cache-first HTTP-fallback contract of the legacy
:func:`read_wikipedia_search_extract` is preserved by the readiness
gate above: the unified adapter NEVER falls through to HTTP because
:func:`check_cache_availability` blocks unsupported cache policies
AND missing cache files AND missing query lists before ``read_raw`` is
called. The ``cache_policy="prefer_cache"`` default falls back to the
legacy cache-first read; in this slice the readiness gate treats
``prefer_cache`` and ``offline_only`` identically (the adapter never
invokes the network once readiness passes).

Query semantics
---------------

The unified adapter accepts an **explicit ``queries=`` list** through
``request.leaders`` (the clean-slice contract: this source is a
cached web/knowledge snippet helper, ``leaders=`` here means query
strings, NOT resolved leader IDs). For every requested query and
every catalog action (``extracts`` and ``search``), the reader
locates the matching cache file via the lazy legacy
:func:`build_cache_key` and parses it through the lazy legacy
``parse_extracts_response`` / ``parse_search_response`` helpers. The
reader returns one :class:`RawAsset` per read cache file (the asset id
is the cache key basename so audit-trail locators can be reconstructed
from a parquet row).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from leaders_db.sources.contracts import (
    RawAsset,
    RawReadResult,
    SourceIngestRequest,
)

from ._constants import (
    WIKIPEDIA_SEARCH_EXTRACT_CACHE_DIR_NAME,
    WIKIPEDIA_SEARCH_EXTRACT_DEFAULT_VERSION,
    WIKIPEDIA_SEARCH_EXTRACT_HOMEPAGE_URL,
    WIKIPEDIA_SEARCH_EXTRACT_INDICATOR_TO_ACTION,
    WIKIPEDIA_SEARCH_EXTRACT_SOURCE_KEY,
)
from ._paths import (
    cache_file,
    cache_root,
    metadata_path,
)
from ._readiness import (
    _extra_params_for_action,
    read_metadata,
)


def read_wikipedia_search_extract_cache(
    request: SourceIngestRequest,
) -> RawReadResult:
    """Read the Wikipedia Action API JSON cache through the legacy parser.

    Steps:

    1. Iterate every ``(query, action)`` pair from
       ``request.leaders`` x ``WIKIPEDIA_SEARCH_EXTRACT_INDICATOR_TO_ACTION``.
    2. For each pair, build the canonical cache key via the lazy
       legacy :func:`build_cache_key` and locate the cache file under
       ``<raw_root>/wikipedia_search_extract/cache/``.
    3. Read the verbatim JSON payload from each cache file via the
       lazy-imported legacy catalog + parser so the canonical Stage 2
       long-format DataFrame is reused without duplication.
    4. Build :class:`RawAsset` records for every read cache file (the
       asset id is the cache key basename so audit-trail locators can
       be reconstructed from a parquet row).
    5. Carry the long-format DataFrames + the legacy catalog specs +
       the raw metadata + the cache root + the parsed cache-key
       payloads on the :class:`RawReadResult.payload` so the transform
       layer can pivot the long frame to per-row
       :class:`NormalizedObservation` records.

    Imports from ``leaders_db.ingest`` are intentionally local so
    importing ``leaders_db.sources.adapters.wikipedia_search_extract``
    does not pull in legacy ingest at module-import time (verified by
    ``test_wikipedia_search_extract_adapter_does_not_import_legacy_ingest``
    in the unified test suite).

    Args:
        request: the unified :class:`SourceIngestRequest`.

    Returns:
        :class:`RawReadResult` with one :class:`RawAsset` per read
        cache file and a ``payload`` dict containing the long-format
        pandas DataFrames, the catalog specs, the parsed metadata,
        the cache root path, and the read cache-key payloads (the
        verbatim JSON dict per cache file).
    """
    from leaders_db.ingest.wikipedia_search_extract_io import (
        load_indicator_catalog,
    )
    from leaders_db.ingest.wikipedia_search_extract_parse import (
        parse_extracts_response,
        parse_search_response,
    )

    cache_root_path = _cache_root(request)
    metadata = read_metadata(metadata_path(request))
    specs = load_indicator_catalog()

    cache_files = _select_cache_files(request, cache_root_path)

    long_frames: list[Any] = []
    raw_payloads: list[tuple[str, str, dict[str, Any]]] = []
    assets: list[RawAsset] = []

    for (
        cache_file_path,
        action,
        indicator_code,
        query,
        payload,
        cache_key,
    ) in cache_files:
        parser_kwargs: dict[str, Any] = {"query": query}
        if action == "extracts":
            long_df = parse_extracts_response(payload, **parser_kwargs)
        else:
            long_df = parse_search_response(payload, **parser_kwargs)
        if long_df is None or getattr(long_df, "empty", False):
            continue
        long_frames.append(long_df)
        raw_payloads.append((action, cache_key, payload))
        assets.append(
            _build_asset(
                request=request,
                cache_file_path=cache_file_path,
                cache_key=cache_key,
                action=action,
                indicator_code=indicator_code,
                query=query,
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
            "queries": list(request.leaders or ()),
            "actions": sorted(
                WIKIPEDIA_SEARCH_EXTRACT_INDICATOR_TO_ACTION.values()
            ),
        },
    )


def _cache_root(request: SourceIngestRequest) -> Path:
    """Return the canonical cache root directory."""
    return cache_root(request)


def _select_cache_files(
    request: SourceIngestRequest,
    cache_root_path: Path,
) -> list[tuple[Path, str, str, str, dict[str, Any], str]]:
    """Return the cache files matching the request's query / action scope.

    The unified adapter follows the legacy orchestrator's
    one-cache-per-(query, action) pair pattern: for each requested
    query the reader enumerates both ``extracts`` and ``search``
    cache files. The reader does NOT auto-create cache files and does
    NOT invoke the network; missing cache files are silently
    skipped at the read step (the readiness gate has already proven
    they are present).
    """
    if not cache_root_path.is_dir():
        return []
    leaders = request.leaders or ()
    selected: list[tuple[Path, str, str, str, dict[str, Any], str]] = []
    for query in leaders:
        normalised_query = str(query)
        for (
            indicator_code,
            action,
        ) in WIKIPEDIA_SEARCH_EXTRACT_INDICATOR_TO_ACTION.items():
            target = cache_file(
                request,
                action=action,
                query=normalised_query,
                extra_params=_extra_params_for_action(action),
            )
            if not target.is_file():
                continue
            try:
                payload = json.loads(target.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            cache_key = target.stem
            selected.append((
                target, action, indicator_code,
                normalised_query, payload, cache_key,
            ))
    return selected


def _build_asset(
    *,
    request: SourceIngestRequest,
    cache_file_path: Path,
    cache_key: str,
    action: str,
    indicator_code: str,
    query: str,
) -> RawAsset:
    """Build a :class:`RawAsset` record for one cache file."""
    asset_id = (
        f"{WIKIPEDIA_SEARCH_EXTRACT_SOURCE_KEY}:cache:"
        f"{action}:{cache_key}"
    )
    return RawAsset(
        asset_id=asset_id,
        source_id=request.source_id,
        version=WIKIPEDIA_SEARCH_EXTRACT_DEFAULT_VERSION,
        media_type="application/json",
        path=cache_file_path,
        url=WIKIPEDIA_SEARCH_EXTRACT_HOMEPAGE_URL,
        checksum_sha256=None,
        retrieved_at=None,
        immutable=True,
    )


__all__ = [
    "read_wikipedia_search_extract_cache",
]


# Reference the cache dir name + indicator/action map so the static
# analyzer keeps them live for any future audit-trail hooks. The
# constants are also re-exported from the package ``__init__`` for
# downstream callers.
_ = (
    WIKIPEDIA_SEARCH_EXTRACT_CACHE_DIR_NAME,
    WIKIPEDIA_SEARCH_EXTRACT_INDICATOR_TO_ACTION,
    WIKIPEDIA_SEARCH_EXTRACT_SOURCE_KEY,
    WIKIPEDIA_SEARCH_EXTRACT_HOMEPAGE_URL,
    WIKIPEDIA_SEARCH_EXTRACT_DEFAULT_VERSION,
)
