"""Cache-shape + cache-policy message helpers for the clean Wikipedia adapter.

The orchestrator
:func:`leaders_db.sources.adapters.wikipedia_search_extract._readiness.check_cache_availability`
delegates to :func:`validate_cache_json_shape` (per-(query,
action) JSON shape validation) and to
:func:`unsupported_cache_policy_message` (the canonical
``unsupported_cache_policy`` blocker). The actual JSON-shape
validation lives in this module (kept under the 400-line
convention).

The gate accepts the canonical legacy Action API shape:

- ``extracts`` -- ``query.pages`` dict (one entry per page).
- ``search`` -- ``query.search`` list (one entry per search hit).

Missing files, unparseable JSON, non-dict payloads, missing
``query`` object, and action-specific sub-object shape mismatches
each surface a structured
``wikipedia_search_extract_missing_raw`` error envelope. An
unknown action (i.e. ``action`` not in ``{"extracts", "search"}``)
surfaces a structured
``wikipedia_search_extract_unsupported_request`` error envelope.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ._constants import (
    WIKIPEDIA_SEARCH_EXTRACT_MISSING_RAW,
    WIKIPEDIA_SEARCH_EXTRACT_UNSUPPORTED_CACHE_POLICY,
    WIKIPEDIA_SEARCH_EXTRACT_UNSUPPORTED_REQUEST,
)

# Sentinel returned by :func:`_read_cache_payload` when the cache
# file is missing on disk; the readiness gate translates this into
# the structured missing-raw error envelope.
_MISSING_FILE_SENTINEL: object = object()

# Local alias so the structured blocker can stay near the message
# in :func:`unsupported_cache_policy_message` without importing the
# long constant chain.
_UNSUPPORTED_CACHE_POLICY_CODE = WIKIPEDIA_SEARCH_EXTRACT_UNSUPPORTED_CACHE_POLICY


def validate_cache_json_shape(
    cache_path: Path, action: str,
) -> tuple[str, str] | None:
    """Return the structured (message, code) blocker for a cache file.

    Returns ``None`` when the cache file exists AND the JSON payload
    has the documented Action API shape for ``action``. Returns
    ``(message, code)`` otherwise -- the readiness gate forwards the
    message + code to the :class:`ReadinessResult`.
    """
    payload = _read_cache_payload(cache_path)
    if payload is _MISSING_FILE_SENTINEL:
        return (
            f"Wikipedia Action API cache file is missing at "
            f"{cache_path}",
        ), WIKIPEDIA_SEARCH_EXTRACT_MISSING_RAW
    if isinstance(payload, tuple):
        _detail, exc = payload
        return _cache_json_shape_error(
            cache_path, f"is not parseable as JSON "
            f"({type(exc).__name__}: {exc}); "
            "re-stage the cache before running ingestion.",
        )
    if not isinstance(payload, dict):
        return _cache_json_shape_error(
            cache_path, "is not a JSON object; re-stage the cache "
            "before running ingestion.",
        )
    return _validate_query_shape(cache_path, payload, action)


def unsupported_cache_policy_message(
    cache_policy: str, cache_root_path: Path,
) -> tuple[str, str]:
    """Return the structured blocker for unsupported cache policies."""
    return (
        "Wikipedia Action API readiness gate: cache_policy="
        f"{cache_policy!r} is not supported by the unified adapter in "
        "this slice; the adapter is offline / cache-only and never "
        "invokes the network. Stage the per-(query, action) JSON "
        "cache under "
        f"<raw_root>/wikipedia_search_extract/cache/"
        "wikipedia_<action>_<query_hash>_<params_hash>.json and "
        "re-run with cache_policy='offline_only' or 'prefer_cache'.",
    ), _UNSUPPORTED_CACHE_POLICY_CODE


def _validate_query_shape(
    cache_path: Path,
    payload: dict[str, Any],
    action: str,
) -> tuple[str, str] | None:
    """Validate the ``query`` sub-object shape for one (path, payload, action)."""
    query_obj = payload.get("query")
    if not isinstance(query_obj, dict):
        return _cache_json_shape_error(
            cache_path,
            "is missing the documented 'query' object; re-stage the "
            "cache before running ingestion.",
        )
    if action == "extracts":
        if not isinstance(query_obj.get("pages"), dict):
            return _cache_json_shape_error(
                cache_path,
                "is missing the documented 'query.pages' dict for "
                "the extracts action; re-stage the cache before "
                "running ingestion.",
            )
        return None
    if action == "search":
        if not isinstance(query_obj.get("search"), list):
            return _cache_json_shape_error(
                cache_path,
                "is missing the documented 'query.search' list for "
                "the search action; re-stage the cache before "
                "running ingestion.",
            )
        return None
    return (
        f"Wikipedia Action API cache file at {cache_path} targets an "
        f"unsupported action {action!r}; expected one of "
        "('extracts', 'search').",
    ), WIKIPEDIA_SEARCH_EXTRACT_UNSUPPORTED_REQUEST


def _read_cache_payload(cache_path: Path) -> Any:
    """Read the cache JSON payload.

    Returns:
        - ``_MISSING_FILE_SENTINEL`` when the cache file is missing.
        - ``(detail_message, exception)`` when the file is
          unparseable.
        - The parsed JSON value otherwise.
    """
    if not cache_path.is_file():
        return _MISSING_FILE_SENTINEL
    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return ("unparseable", exc)


def _cache_json_shape_error(
    cache_path: Path, detail: str,
) -> tuple[str, str]:
    """Return the structured (message, code) blocker for a malformed cache file."""
    return (
        f"Wikipedia Action API cache file at {cache_path} {detail}",
    ), WIKIPEDIA_SEARCH_EXTRACT_MISSING_RAW


# Reference the constants so the static analyzer keeps them live
# for any future audit-trail hooks that need the cache-readiness
# code list. The constants are also re-exported from the package
# ``__init__`` for downstream callers.
_ = (
    WIKIPEDIA_SEARCH_EXTRACT_MISSING_RAW,
    WIKIPEDIA_SEARCH_EXTRACT_UNSUPPORTED_REQUEST,
)


__all__ = [
    "unsupported_cache_policy_message",
    "validate_cache_json_shape",
]
