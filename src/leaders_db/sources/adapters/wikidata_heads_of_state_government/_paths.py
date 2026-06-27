"""Path + cache-key helpers for the clean Wikidata HoS/HoG adapter.

Owns the canonical ``<raw_root>/wikidata_heads_of_state_government/``
directory layout:

- ``bundle_dir(request)`` -- ``<raw_root>/wikidata_heads_of_state_government/``
- ``metadata_path(request)`` -- ``<raw_root>/wikidata_heads_of_state_government/metadata.json``
- ``cache_root(request)`` -- ``<raw_root>/wikidata_heads_of_state_government/cache/``
- ``cache_file(request, year, country_qids, query_template_hash=None)``
  -- the canonical
  ``wd_ALL_<year>_<country_hash>_<template_hash>.json``
  filename. The hash slot is either an explicit hash OR the
  canonical 10-character SHA-256 prefix of the sorted office
  QIDs CSV (computed lazily from the legacy catalog).
- ``current_cache_file(request)`` -- the canonical
  ``wd_ALL_current_all_<template_hash>.json`` filename used
  by the all-current-holders request (``years=None``).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from leaders_db.sources.contracts import SourceIngestRequest

from ._constants import (
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_CACHE_DIR_NAME,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_METADATA_NAME,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_KEY,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SPARQL_ENDPOINT_URL,
)


def bundle_dir(request: SourceIngestRequest) -> Path:
    """Return the canonical Wikidata HoS/HoG bundle directory."""
    return Path(request.raw_root) / WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_KEY


def metadata_path(request: SourceIngestRequest) -> Path:
    """Return the canonical Wikidata HoS/HoG ``metadata.json`` path."""
    return bundle_dir(request) / WIKIDATA_HEADS_OF_STATE_GOVERNMENT_METADATA_NAME


def cache_root(request: SourceIngestRequest) -> Path:
    """Return the canonical Wikidata HoS/HoG cache root directory."""
    return (
        bundle_dir(request)
        / WIKIDATA_HEADS_OF_STATE_GOVERNMENT_CACHE_DIR_NAME
    )


def canonical_sparql_endpoint_url() -> str:
    """Return the canonical Wikidata SPARQL endpoint URL."""
    return WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SPARQL_ENDPOINT_URL


def _short_sha256(value: str, *, length: int = 10) -> str:
    """Return the first ``length`` characters of SHA-256(value)."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def canonical_template_hash() -> str:
    """Return the canonical SPARQL query template hash.

    Mirrors
    :func:`leaders_db.ingest.wikidata_heads_of_state_government_parse.query_template_hash`
    -- a 10-character SHA-256 prefix of the sorted office QIDs
    CSV. The current catalog has ``["Q30461", "Q22857062"]`` so
    the canonical hash is ``"6a945a3130"`` (matching the staged
    fixture cache filenames). The lazy lookup ensures the
    readiness gate does NOT import legacy ingest at import time.
    """
    from leaders_db.ingest.wikidata_heads_of_state_government_io import (
        load_indicator_catalog,
    )

    office_qids = sorted(
        spec.raw_column for spec in load_indicator_catalog()
    )
    joined = ",".join(office_qids)
    return _short_sha256(joined, length=10)


def cache_file(
    request: SourceIngestRequest,
    year: int | None,
    country_qids: tuple[str, ...] | None,
    query_template_hash: str | None = None,
) -> Path:
    """Return the canonical Wikidata HoS/HoG cache file path.

    Mirrors the legacy
    :func:`leaders_db.ingest.wikidata_heads_of_state_government_http.build_cache_key`
    shape: ``wd_ALL_<year>_<country_hash>_<template_hash>.json``.
    """
    year_part = str(year) if year is not None else "current"
    if country_qids is None:
        country_part = "all"
    else:
        joined = ",".join(sorted(country_qids))
        country_part = _short_sha256(joined, length=10)
    template_hash = (
        query_template_hash
        if query_template_hash is not None
        else canonical_template_hash()
    )
    return cache_root(request) / (
        f"wd_ALL_{year_part}_{country_part}_{template_hash}.json"
    )


def current_cache_file(request: SourceIngestRequest) -> Path:
    """Return the canonical current-holders cache file path."""
    return cache_file(
        request,
        year=None,
        country_qids=None,
        query_template_hash=canonical_template_hash(),
    )


__all__ = [
    "bundle_dir",
    "cache_file",
    "cache_root",
    "canonical_sparql_endpoint_url",
    "canonical_template_hash",
    "current_cache_file",
    "metadata_path",
]
