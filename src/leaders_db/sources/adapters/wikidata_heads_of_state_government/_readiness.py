"""Readiness checks for the clean Wikidata heads-of-state-and-government adapter.

The orchestrator :func:`check_ready` composes the per-``(year,
country_qids)`` cache gate, the cache-policy gate, the metadata
version gate, the request-version gate, and the request-scoping
warning builders. The actual JSON-shape validation lives in
:func:`._cache_readiness._validate_cached_sparql_json_shape`;
the path + cache-key helpers live in :mod:`._paths`; the
request-warning builder + QID normalization helpers live in
:mod:`._request_warnings`. The three carve-outs keep this
module under the documented 400-line convention.

The gate accepts BOTH the canonical primary metadata shape
(``source_version``) AND the legacy raw-local bundle shape
(``version``); the version stamp accepts BOTH the canonical
``"SPARQL"`` value AND the legacy alias ``"SPARQL endpoint
(no version)"`` so the existing staged bundle does not need
to be rewritten as part of the migration.

Cache-policy semantics
----------------------

The Wikidata HoS/HoG unified adapter is cache-only in this
slice. The legacy HTTP layer
(:func:`leaders_db.ingest.wikidata_heads_of_state_government_http.fetch_wikidata_sparql_payload`)
is intentionally NEVER invoked by the unified read path. For
supported cache policies (``"offline_only"`` /
``"prefer_cache"``), the gate blocks when:

1. The cache policy is ``"refresh"`` / ``"no_cache"`` -- the
   unified adapter never invokes the network.
2. The bundle ``metadata.json`` is missing or unparseable.
3. The bundle metadata's ``version`` / ``source_version`` is
   not the canonical ``"SPARQL"`` AND not the legacy alias
   ``"SPARQL endpoint (no version)"``.
4. ``request.years`` is explicit AND the per-``(year,
   country_qids)`` cache file is missing for the request.
5. ``request.years`` is explicit AND the matched cache file is
   not a valid SPARQL JSON response (no ``results.bindings``
   list).
6. ``request.years=None`` AND the cache root is missing
   entirely (the cache directory must exist for the readiness
   gate to detect any staged files).
7. ``request.source_version`` is set to a value other than the
   canonical ``"SPARQL"`` (the legacy alias is accepted on the
   staged metadata for backward compatibility but the request
   version contract is the canonical short stamp per
   SRC-REQ-009).
"""

from __future__ import annotations

import json
from pathlib import Path

from leaders_db.sources.contracts import SourceIngestRequest
from leaders_db.sources.warnings import (
    MISSING_METADATA,
    MISSING_RAW,
    NETWORK_CACHE_UNAVAILABLE,
)

from ._cache_readiness import _validate_cached_sparql_json_shape
from ._constants import (
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_CHECKSUM_MISMATCH,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_DEFAULT_VERSION,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_LEGACY_VERSION_ALIAS,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_METADATA_VERSION_MISMATCH,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_UNSUPPORTED_CACHE_POLICY,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_UNSUPPORTED_MULTI_YEAR,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_UNSUPPORTED_VERSION,
)
from ._paths import (
    bundle_dir,
    cache_file,
    cache_root,
    canonical_sparql_endpoint_url,
    current_cache_file,
    metadata_path,
)
from ._request_warnings import (
    normalize_country_qids,
    request_warnings,
)

# ---------------------------------------------------------------------------
# Metadata helpers
# ---------------------------------------------------------------------------


def read_metadata(path: Path) -> dict[str, object]:
    """Return the parsed ``metadata.json`` payload, or ``{}`` on any error."""
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _coalesce(
    payload: dict[str, object],
    primary: str,
    legacy: str | None = None,
) -> object:
    """Return the first non-None value among ``primary`` and ``legacy`` keys."""
    value = payload.get(primary)
    if value is not None:
        return value
    if legacy is not None:
        return payload.get(legacy)
    return None


def metadata_blocker(
    request: SourceIngestRequest,
) -> tuple[str, str] | None:
    """Validate the bundle's ``metadata.json`` shape.

    Returns ``(blocker_message, code)`` when the metadata is
    missing, unparseable, or carries an unsupported source
    version. Returns ``None`` for a well-formed metadata file
    whose ``version`` / ``source_version`` is the canonical
    ``"SPARQL"`` OR the legacy alias
    ``"SPARQL endpoint (no version)"``.
    """
    path = metadata_path(request)
    if not path.is_file():
        return (
            f"Wikidata heads-of-state metadata.json is missing at "
            f"{path}"
        ), MISSING_METADATA
    payload = read_metadata(path)
    if not payload:
        return (
            f"Wikidata heads-of-state metadata.json is not "
            f"parseable at {path}"
        ), MISSING_METADATA
    version = _coalesce(payload, "source_version", "version")
    if not isinstance(version, str) or not version.strip():
        return (
            "Wikidata heads-of-state metadata source_version / "
            f"version must be one of "
            f"{WIKIDATA_HEADS_OF_STATE_GOVERNMENT_DEFAULT_VERSION!r} "
            f"(canonical) or "
            f"{WIKIDATA_HEADS_OF_STATE_GOVERNMENT_LEGACY_VERSION_ALIAS!r} "
            f"(legacy alias); missing or empty."
        ), WIKIDATA_HEADS_OF_STATE_GOVERNMENT_METADATA_VERSION_MISMATCH
    stripped = version.strip()
    if stripped not in {
        WIKIDATA_HEADS_OF_STATE_GOVERNMENT_DEFAULT_VERSION,
        WIKIDATA_HEADS_OF_STATE_GOVERNMENT_LEGACY_VERSION_ALIAS,
    }:
        return (
            "Wikidata heads-of-state metadata source_version / "
            f"version must be one of "
            f"{WIKIDATA_HEADS_OF_STATE_GOVERNMENT_DEFAULT_VERSION!r} "
            f"(canonical) or "
            f"{WIKIDATA_HEADS_OF_STATE_GOVERNMENT_LEGACY_VERSION_ALIAS!r} "
            f"(legacy alias); got {stripped!r}."
        ), WIKIDATA_HEADS_OF_STATE_GOVERNMENT_METADATA_VERSION_MISMATCH
    return None


# ---------------------------------------------------------------------------
# Cache-policy gate
# ---------------------------------------------------------------------------


def _unsupported_cache_policy_blocker(
    cache_policy: str, cache_root_path: Path,
) -> tuple[str, str]:
    """Return the structured blocker for unsupported cache policies."""
    return (
        f"Wikidata heads-of-state readiness gate: cache_policy="
        f"{cache_policy!r} is not supported by the unified "
        f"Wikidata HoS/HoG adapter in this slice; the adapter is "
        f"offline / cache-only and never invokes the network. "
        f"Stage the per-(year, country_qids) JSON cache under "
        f"{cache_root_path}/wd_ALL_<year>_<country_hash>_<template_hash>.json "
        f"and re-run with cache_policy='offline_only' or "
        f"'prefer_cache'."
    ), WIKIDATA_HEADS_OF_STATE_GOVERNMENT_UNSUPPORTED_CACHE_POLICY


def cache_policy_blocker(
    request: SourceIngestRequest,
) -> tuple[str, str] | None:
    """Block when ``cache_policy`` is one of the unsupported values."""
    if request.cache_policy in {"refresh", "no_cache"}:
        return _unsupported_cache_policy_blocker(
            request.cache_policy, cache_root(request),
        )
    return None


# ---------------------------------------------------------------------------
# Cache-file availability gate
# ---------------------------------------------------------------------------


def check_cache_availability(
    request: SourceIngestRequest,
) -> tuple[bool, str | None, str | None]:
    """Validate the per-``(year, country_qids)`` cache gate for the request.

    Returns ``(ready, blocker, code)`` so the adapter can surface
    a structured :class:`SourceWarning` with the canonical code.

    For ``years=None`` the gate uses ONLY the canonical
    current-holders cache file; for explicit-year requests the
    gate uses the cache file matching the first requested year
    + the (sorted) country_qids set. The template hash is the
    canonical 10-character SHA-256 prefix of the sorted office
    QIDs CSV (computed lazily from the legacy catalog).

    The unsupported-policy branch fires BEFORE the
    cache-availability check so callers cannot bypass the
    ``cache_policy`` gate with ``years=None``.
    """
    cache_root_path = cache_root(request)

    if request.cache_policy in {"refresh", "no_cache"}:
        return False, *_unsupported_cache_policy_blocker(
            request.cache_policy, cache_root_path,
        )

    if not request.years:
        if not cache_root_path.is_dir():
            return False, (
                f"Wikidata heads-of-state readiness gate: cache "
                f"directory missing at {cache_root_path} for "
                f"cache_policy={request.cache_policy!r}; place "
                f"the per-(year, country_qids) JSON cache under "
                f"{cache_root_path}/wd_ALL_<year>_<country_hash>_<template_hash>.json "
                f"before running ingestion."
            ), NETWORK_CACHE_UNAVAILABLE
        current_path = current_cache_file(request)
        blocker = _validate_cached_sparql_json_shape(current_path)
        if blocker is not None:
            message, _ = blocker
            return False, (
                f"{message} Required by the all-current-holders "
                f"request under "
                f"cache_policy={request.cache_policy!r}; re-stage "
                f"the cache before running ingestion."
            ), MISSING_RAW
        return True, None, None

    return _check_explicit_year_cache_files(request)


def _check_explicit_year_cache_files(
    request: SourceIngestRequest,
) -> tuple[bool, str | None, str | None]:
    """Validate the per-(year, country_qids) cache gate for explicit-year requests."""
    cache_root_path = cache_root(request)
    if not cache_root_path.is_dir():
        return False, (
            f"Wikidata heads-of-state readiness gate: cache "
            f"directory missing at {cache_root_path} for "
            f"cache_policy={request.cache_policy!r}; place the "
            f"per-(year, country_qids) JSON cache under "
            f"{cache_root_path}/wd_ALL_<year>_<country_hash>_<template_hash>.json "
            f"before running ingestion."
        ), NETWORK_CACHE_UNAVAILABLE

    if request.years and len(request.years) > 1:
        return False, (
            "Wikidata heads-of-state readiness gate: multi-year "
            f"requests are not supported in this cache-only slice; "
            f"received years={request.years!r}. Run one year per "
            "request so the cache key maps unambiguously to the "
            "SPARQL JSON file."
        ), WIKIDATA_HEADS_OF_STATE_GOVERNMENT_UNSUPPORTED_MULTI_YEAR

    countries = normalize_country_qids(request.countries)
    if request.countries and countries == ():
        return True, None, None

    first_year = int(request.years[0])
    cache_file_path = cache_file(
        request,
        year=first_year,
        country_qids=countries,
    )
    blocker = _validate_cached_sparql_json_shape(cache_file_path)
    if blocker is not None:
        message, _ = blocker
        return False, (
            f"{message} Required by the explicit "
            f"year={first_year} country_qids="
            f"{request.countries!r} request under "
            f"cache_policy={request.cache_policy!r}; re-stage "
            f"the cache before running ingestion."
        ), MISSING_RAW
    return True, None, None


# ---------------------------------------------------------------------------
# Version gate
# ---------------------------------------------------------------------------


def version_blocker(
    request: SourceIngestRequest,
) -> tuple[str, str] | None:
    """Block if ``request.source_version`` differs from the canonical version."""
    if request.source_version is None:
        return None
    if (
        request.source_version
        == WIKIDATA_HEADS_OF_STATE_GOVERNMENT_DEFAULT_VERSION
    ):
        return None
    return (
        "Wikidata heads-of-state request source_version must be "
        f"{WIKIDATA_HEADS_OF_STATE_GOVERNMENT_DEFAULT_VERSION!r}; "
        f"got {request.source_version!r}"
    ), WIKIDATA_HEADS_OF_STATE_GOVERNMENT_UNSUPPORTED_VERSION


# Public surface -----------------------------------------------------------


__all__ = [
    "WIKIDATA_HEADS_OF_STATE_GOVERNMENT_CHECKSUM_MISMATCH",
    "bundle_dir",
    "cache_file",
    "cache_policy_blocker",
    "cache_root",
    "canonical_sparql_endpoint_url",
    "check_cache_availability",
    "metadata_blocker",
    "metadata_path",
    "read_metadata",
    "request_warnings",
    "version_blocker",
]
