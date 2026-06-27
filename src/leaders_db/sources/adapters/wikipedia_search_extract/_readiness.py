"""Readiness checks for the clean Wikipedia Action API adapter.

The orchestrator :func:`check_ready` composes the query-presence gate
(the clean slice requires explicit ``leaders=`` query strings; missing
or empty fails readiness), the cache-policy gate, the cache-availability
gate, the metadata-version gate, the request-version gate, and the
request-scoping warning builders (the ``unsupported_filter`` warning
for ``years=`` / ``countries=``).

Cache-policy semantics
----------------------

The unified Wikipedia Action API adapter is cache-only in this slice.
The legacy HTTP layer
(:func:`leaders_db.ingest.wikipedia_search_extract_http.fetch_wikipedia_action_api_payload`)
is intentionally NEVER invoked by the unified read path. For supported
cache policies (``"offline_only"`` / ``"prefer_cache"``), the gate
blocks when:

1. The cache policy is ``"refresh"`` / ``"no_cache"`` -- the unified
   adapter never invokes the network.
2. ``request.leaders`` is empty or missing -- the Stage 2 contract is
   "do not browse / score"; the caller MUST pass explicit query
   strings.
3. For every requested query and every catalog action, the legacy
   :func:`build_cache_key` cache file is missing on disk OR the JSON
   payload does not have the documented Action API shape
   (``extracts`` -> ``query.pages`` dict; ``search`` ->
   ``query.search`` list).
4. ``request.source_version`` is set to a value other than the
   canonical ``"Action API"``.
5. The bundle ``metadata.json`` is present but unparseable or carries
   an unsupported ``source_version`` / legacy alias (the staged
   metadata is OPTIONAL for a cache-only bundle; when absent, the
   gate accepts the bundle).

Request-scoping semantics
-------------------------

The clean slice maps the Wikipedia Action API query input to
``request.leaders`` (this source is a cached web/knowledge snippet
helper, ``leaders=`` here means query strings, NOT resolved leader
IDs). ``years=`` and ``countries=`` are **unsupported** filters -- the
Action API does not return year-scoped rows and does not return
country-coded rows. The readiness envelope surfaces a structured
``UNSUPPORTED_FILTER`` warning per request filter when set; the runner
ignores the filters and still emits the cached rows. The unified
adapter never invents years, country codes, or leader IDs.
"""

from __future__ import annotations

from pathlib import Path

from leaders_db.sources.contracts import SourceIngestRequest
from leaders_db.sources.warnings import MISSING_METADATA

from ._cache_readiness import (
    unsupported_cache_policy_message,
    validate_cache_json_shape,
)
from ._constants import (
    WIKIPEDIA_SEARCH_EXTRACT_DEFAULT_VERSION,
    WIKIPEDIA_SEARCH_EXTRACT_INDICATOR_TO_ACTION,
    WIKIPEDIA_SEARCH_EXTRACT_LEGACY_VERSION_ALIAS,
    WIKIPEDIA_SEARCH_EXTRACT_METADATA_VERSION_MISMATCH,
    WIKIPEDIA_SEARCH_EXTRACT_MISSING_QUERIES,
    WIKIPEDIA_SEARCH_EXTRACT_MISSING_RAW,
    WIKIPEDIA_SEARCH_EXTRACT_UNSUPPORTED_VERSION,
)
from ._paths import (
    bundle_dir,
    cache_file,
    cache_root,
    metadata_path,
)
from ._request_warnings import request_warnings

# ---------------------------------------------------------------------------
# Metadata helpers
# ---------------------------------------------------------------------------


def read_metadata(path: Path) -> dict[str, object]:
    """Return the parsed ``metadata.json`` payload, or ``{}`` on any error."""
    if not path.is_file():
        return {}
    import json

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

    Returns ``(blocker_message, code)`` when the metadata is missing,
    unparseable, or carries an unsupported source version. Returns
    ``None`` for a well-formed metadata file whose
    ``version`` / ``source_version`` is the canonical ``"Action API"``
    OR the legacy alias ``"Action API (no version)"``.

    The staged ``metadata.json`` is OPTIONAL for the clean slice --
    the adapter does not depend on the staged metadata (the cache
    files are the source of truth). Missing metadata is acceptable
    so callers can stage a cache-only bundle without rewriting
    legacy metadata.
    """
    path = metadata_path(request)
    if not path.is_file():
        return None
    payload = read_metadata(path)
    if not payload:
        return (
            f"Wikipedia Action API metadata.json is not parseable at "
            f"{path}",
        ), MISSING_METADATA
    version = _coalesce(payload, "source_version", "version")
    if version is None:
        return None
    if not isinstance(version, str) or not version.strip():
        return (
            "Wikipedia Action API metadata source_version / version "
            "must be one of "
            f"{WIKIPEDIA_SEARCH_EXTRACT_DEFAULT_VERSION!r} "
            "(canonical) or "
            f"{WIKIPEDIA_SEARCH_EXTRACT_LEGACY_VERSION_ALIAS!r} "
            "(legacy alias); missing or empty.",
        ), WIKIPEDIA_SEARCH_EXTRACT_METADATA_VERSION_MISMATCH
    stripped = version.strip()
    if stripped not in {
        WIKIPEDIA_SEARCH_EXTRACT_DEFAULT_VERSION,
        WIKIPEDIA_SEARCH_EXTRACT_LEGACY_VERSION_ALIAS,
    }:
        return (
            "Wikipedia Action API metadata source_version / version "
            "must be one of "
            f"{WIKIPEDIA_SEARCH_EXTRACT_DEFAULT_VERSION!r} "
            "(canonical) or "
            f"{WIKIPEDIA_SEARCH_EXTRACT_LEGACY_VERSION_ALIAS!r} "
            "(legacy alias); got {stripped!r}.",
        ), WIKIPEDIA_SEARCH_EXTRACT_METADATA_VERSION_MISMATCH
    return None


# ---------------------------------------------------------------------------
# Query-presence gate
# ---------------------------------------------------------------------------


def queries_blocker(
    request: SourceIngestRequest,
) -> tuple[str, str] | None:
    """Validate the explicit ``leaders=`` query-string list.

    The clean slice maps the Wikipedia Action API query input to
    ``request.leaders`` (NOT resolved leader IDs). Missing or empty
    ``leaders=`` fails readiness with a structured error BEFORE
    ``read_raw`` / ``transform`` are called -- the helper does not
    browse / discover (per the Stage 2 contract).
    """
    leaders = request.leaders or ()
    if not leaders or any(not str(query).strip() for query in leaders):
        return (
            "Wikipedia Action API readiness gate: the explicit "
            "queries= list (request.leaders) is missing or empty; the "
            "Stage 2 contract is 'do not browse / score'; the helper "
            "requires explicit query strings. Pass request.leaders= "
            "with at least one non-empty query / title string.",
        ), WIKIPEDIA_SEARCH_EXTRACT_MISSING_QUERIES
    return None


# ---------------------------------------------------------------------------
# Cache-policy gate
# ---------------------------------------------------------------------------


def cache_policy_blocker(
    request: SourceIngestRequest,
) -> tuple[str, str] | None:
    """Block when ``cache_policy`` is one of the unsupported values.

    The unified Wikipedia Action API adapter is cache-only in this
    slice; the legacy HTTP layer is intentionally NEVER invoked. For
    supported cache policies (``"offline_only"`` / ``"prefer_cache"``)
    the gate accepts the request; for ``"refresh"`` / ``"no_cache"``
    the gate refuses with a structured ``unsupported_cache_policy``
    error.
    """
    if request.cache_policy in {"refresh", "no_cache"}:
        return unsupported_cache_policy_message(
            request.cache_policy, cache_root(request),
        )
    return None


# ---------------------------------------------------------------------------
# Cache-availability gate
# ---------------------------------------------------------------------------


def check_cache_availability(
    request: SourceIngestRequest,
) -> tuple[bool, str | None, str | None]:
    """Validate the per-``(query, action)`` cache gate for the request.

    Returns ``(ready, blocker, code)`` so the adapter can surface a
    structured :class:`SourceWarning` with the canonical code.

    The gate iterates every (query, action) pair from
    ``request.leaders`` x ``WIKIPEDIA_SEARCH_EXTRACT_INDICATOR_TO_ACTION``
    and verifies the cache file is present AND the JSON payload has
    the documented Action API shape (``extracts`` -> ``query.pages``
    dict; ``search`` -> ``query.search`` list) via the lazy
    :func:`._cache_readiness.validate_cache_json_shape` helper.

    The unsupported-policy branch fires BEFORE the cache-availability
    check so callers cannot bypass the ``cache_policy`` gate with
    missing queries.
    """
    if request.cache_policy in {"refresh", "no_cache"}:
        return False, *unsupported_cache_policy_message(
            request.cache_policy, cache_root(request),
        )

    leaders = request.leaders or ()
    if not leaders or any(not str(query).strip() for query in leaders):
        return False, (
            "Wikipedia Action API readiness gate: no query strings to "
            "validate against the cache; pass request.leaders= with "
            "at least one explicit query / title string.",
        ), WIKIPEDIA_SEARCH_EXTRACT_MISSING_QUERIES

    cache_root_path = cache_root(request)
    if not cache_root_path.is_dir():
        return False, (
            "Wikipedia Action API readiness gate: cache directory "
            f"missing at {cache_root_path} for cache_policy="
            f"{request.cache_policy!r}; place the per-(query, action) "
            "JSON cache under "
            f"{cache_root_path}/wikipedia_<action>_<query_hash>_<params_hash>.json "
            "before running ingestion.",
        ), WIKIPEDIA_SEARCH_EXTRACT_MISSING_RAW

    for query in leaders:
        normalised_query = str(query)
        for indicator_code, action in (
            WIKIPEDIA_SEARCH_EXTRACT_INDICATOR_TO_ACTION.items()
        ):
            cache_path = cache_file(
                request,
                action=action,
                query=normalised_query,
                extra_params=_extra_params_for_action(action),
            )
            blocker = validate_cache_json_shape(cache_path, action)
            if blocker is not None:
                message, code = blocker
                return False, (
                    f"{message} Required by the {action} request for "
                    f"query={normalised_query!r} (indicator "
                    f"{indicator_code!r}) under "
                    f"cache_policy={request.cache_policy!r}; re-stage "
                    "the cache before running ingestion."
                ), code
    return True, None, None


def _extra_params_for_action(action: str) -> dict[str, object] | None:
    """Return the canonical extra_params dict for one Action API action.

    The legacy cache key is parameter-sensitive: the ``search`` action
    carries ``{"limit": 10}`` (the canonical prototype default), so
    two callers using different ``search_limit`` values produce
    different cache keys. The unified slice reads only the canonical
    default; a caller who wants a different ``search_limit`` must
    stage a new cache file under that key.

    For ``extracts``, ``extra_params`` is empty (the URL already
    encodes the deterministic params ``exintro=1&explaintext=1``).
    """
    if action == "search":
        return {"limit": 10}
    return None


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
        == WIKIPEDIA_SEARCH_EXTRACT_DEFAULT_VERSION
    ):
        return None
    return (
        "Wikipedia Action API request source_version must be "
        f"{WIKIPEDIA_SEARCH_EXTRACT_DEFAULT_VERSION!r} (canonical); "
        "the legacy alias "
        f"{WIKIPEDIA_SEARCH_EXTRACT_LEGACY_VERSION_ALIAS!r} is "
        "accepted only on the staged bundle metadata, not on the "
        f"request; got {request.source_version!r}",
    ), WIKIPEDIA_SEARCH_EXTRACT_UNSUPPORTED_VERSION


# ---------------------------------------------------------------------------
# Request-scoping warning builders
# ---------------------------------------------------------------------------


__all__ = [
    "bundle_dir",
    "cache_file",
    "cache_policy_blocker",
    "cache_root",
    "check_cache_availability",
    "metadata_blocker",
    "metadata_path",
    "queries_blocker",
    "read_metadata",
    "request_warnings",
    "version_blocker",
]
