"""Path + cache-key helpers for the clean Wikipedia Action API adapter.

Owns the canonical ``<raw_root>/wikipedia_search_extract/`` directory
layout:

- ``bundle_dir(request)`` -- ``<raw_root>/wikipedia_search_extract/``
- ``metadata_path(request)`` --
  ``<raw_root>/wikipedia_search_extract/metadata.json``
- ``cache_root(request)`` --
  ``<raw_root>/wikipedia_search_extract/cache/``
- ``cache_file(request, action, query, extra_params=None)`` -- the
  canonical ``wikipedia_<action>_<query_hash>_<params_hash>.json``
  filename, built via the lazy legacy
  :func:`leaders_db.ingest.wikipedia_search_extract_http.build_cache_key`.
"""

from __future__ import annotations

from pathlib import Path

from leaders_db.sources.contracts import SourceIngestRequest

from ._constants import (
    WIKIPEDIA_SEARCH_EXTRACT_CACHE_DIR_NAME,
    WIKIPEDIA_SEARCH_EXTRACT_METADATA_NAME,
    WIKIPEDIA_SEARCH_EXTRACT_SOURCE_KEY,
)


def bundle_dir(request: SourceIngestRequest) -> Path:
    """Return the canonical Wikipedia Action API bundle directory."""
    return (
        Path(request.raw_root) / WIKIPEDIA_SEARCH_EXTRACT_SOURCE_KEY
    )


def metadata_path(request: SourceIngestRequest) -> Path:
    """Return the canonical Wikipedia Action API ``metadata.json`` path."""
    return bundle_dir(request) / WIKIPEDIA_SEARCH_EXTRACT_METADATA_NAME


def cache_root(request: SourceIngestRequest) -> Path:
    """Return the canonical Wikipedia Action API cache root directory."""
    return (
        bundle_dir(request)
        / WIKIPEDIA_SEARCH_EXTRACT_CACHE_DIR_NAME
    )


def cache_file(
    request: SourceIngestRequest,
    *,
    action: str,
    query: str,
    extra_params: dict[str, object] | None = None,
) -> Path:
    """Return the canonical Wikipedia Action API cache file path.

    Mirrors the legacy
    :func:`leaders_db.ingest.wikipedia_search_extract_http.build_cache_key`
    shape: ``wikipedia_<action>_<query_hash>_<params_hash>.json``. The
    canonical fixture filenames are
    ``wikipedia_extracts_62f100bfa4_default.json`` (Joe Biden, extracts),
    ``wikipedia_search_62f100bfa4_7d0587b5ac.json`` (Joe Biden, search),
    and ``wikipedia_extracts_6f47c90e93_default.json`` (AMLO, extracts).

    Args:
        request: the unified :class:`SourceIngestRequest`.
        action: Action API action name (``"extracts"`` or ``"search"``).
        query: the raw query / title string (the cache key uses the
            normalised, lower-cased query).
        extra_params: optional action-specific extra params; the
            ``search`` action carries ``{"limit": <int>}`` so the cache
            key is sensitive to the search-limit override.

    Returns:
        The canonical ``<cache_root>/<cache_key>.json`` path.
    """
    cache_key = build_cache_key(
        action=action, query=query, extra_params=extra_params,
    )
    return cache_root(request) / f"{cache_key}.json"


def build_cache_key(
    *,
    action: str,
    query: str,
    extra_params: dict[str, object] | None = None,
) -> str:
    """Build the canonical Wikipedia Action API cache key.

    Lazy-imports the legacy
    :func:`leaders_db.ingest.wikipedia_search_extract_http.build_cache_key`
    so the canonical Stage 2 cache-key shape is reused without
    duplication (mirrors the WDI / WHO GHO API / Wikidata pattern). The
    lazy import ensures the package boundary is preserved: importing
    :mod:`leaders_db.sources.adapters.wikipedia_search_extract` does NOT
    pull in :mod:`leaders_db.ingest`.

    Args:
        action: Action API action name (``"extracts"`` or ``"search"``).
        query: the raw query / title string.
        extra_params: optional action-specific extra params dict.

    Returns:
        The canonical cache key string of the form
        ``wikipedia_<action>_<query_hash>_<params_hash>``.
    """
    from leaders_db.ingest.wikipedia_search_extract_http import (
        build_cache_key as _legacy_build_cache_key,
    )

    return _legacy_build_cache_key(
        action=action, query=query, extra_params=extra_params,
    )


__all__ = [
    "build_cache_key",
    "bundle_dir",
    "cache_file",
    "cache_root",
    "metadata_path",
]
