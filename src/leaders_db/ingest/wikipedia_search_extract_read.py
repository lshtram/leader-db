"""Stage 2 -- Wikipedia search-extract read orchestrator.

This module holds the read orchestrator
(:func:`read_wikipedia_search_extract`) that drives the
Action API fetch + parse + concat. The frame stays long-format
(one row per Action API response page / search hit).

The HTTP + cache layer lives in
:mod:`wikipedia_search_extract_http`. The catalog + paths + parquet
write live in :mod:`wikipedia_search_extract_io`. The parser lives
in :mod:`wikipedia_search_extract_parse`. The DB writes live in
:mod:`wikipedia_search_extract_db`. The orchestrator that ties
everything together lives in
:mod:`wikipedia_search_extract`.

Helper-blocked / needs downstream inputs (per the user's Stage 2
contract):

The Action API helper needs explicit input terms to query; the
orchestrator does NOT browse, score, or do leader resolution. The
caller's ``queries`` list is the deterministic input interface. The
orchestrator iterates the queries list and calls the action per
catalog ``IndicatorSpec`` -- the action set is determined by the
catalog (``extracts`` and ``search`` in the prototype). The
verbatim Action API response is persisted as the
``source_observations.raw_value`` audit trail; Stage 3 / Stage 4
resolve country / leader from the persisted
``source_row_reference`` + ``raw_value`` fields.
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from .wikipedia_search_extract_http import (
    SUPPORTED_ACTIONS,
    WIKIPEDIA_ACTION_API_BASE,
    build_cache_key,
    build_extracts_url,
    build_search_url,
    fetch_wikipedia_action_api_payload,
)
from .wikipedia_search_extract_io import (
    default_cache_dir,
    load_indicator_catalog,
)
from .wikipedia_search_extract_parse import (
    parse_extracts_response,
    parse_search_response,
)

_logger = logging.getLogger(__name__)

__all__ = ["read_wikipedia_search_extract"]


# ---------------------------------------------------------------------------
# Read orchestrator
# ---------------------------------------------------------------------------


def read_wikipedia_search_extract(
    *,
    queries: list[str] | None = None,
    actions: list[str] | None = None,
    base_url: str = WIKIPEDIA_ACTION_API_BASE,
    catalog_path: object = None,
    cache_dir: object = None,
    force_refresh: bool = False,
    request_timeout: float = 30.0,
    search_limit: int = 10,
) -> pd.DataFrame:
    """Read the Wikipedia Action API for the given queries + actions.

    Steps:

    1. Load the catalog (or use the explicit ``actions`` override).
       The catalog's ``raw_column`` is the API action name; the
       orchestrator picks one Action API request per (query, action)
       pair.
    2. For each (query, action) pair: build the cache key from the
       (action, query, action-specific extra params) tuple and look
       up the cached payload at
       ``<cache_dir>/<cache_key>.json``. If the cache file exists
       AND ``force_refresh`` is ``False``, read the cached JSON;
       else HTTP-GET the Wikipedia Action API endpoint via
       :mod:`wikipedia_search_extract_http`, write the verbatim
       response to the cache, then parse.
    3. The parser (per action: ``extracts`` or ``search``) turns
       the JSON response into a long-format DataFrame. The reader
       concats the per-(query, action) frames.
    4. No wide pivot -- the long row already carries the action
       + query / title, so the DB writer can join on
       action -> catalog spec.

    The returned DataFrame carries two extra attributes on
    ``df.attrs`` so the orchestrator can surface them in
    :class:`WikipediaSearchExtractIngestResult`:

    - ``df.attrs["indicators_cached"]`` -- count of (query, action)
      pairs that were read from the JSON cache.
    - ``df.attrs["indicators_fetched"]`` -- count of (query, action)
      pairs that were HTTP-fetched in this call.

    Args:
        queries: explicit list of query / title strings to send to
            the Action API. ``None`` or an empty list raises
            ``ValueError`` -- the Stage 2 contract is "do not
            browse / score"; the adapter requires explicit input.
        actions: optional list of action names to scope the call.
            Default: every action in the catalog (``extracts`` and
            ``search`` in the prototype). Must be a subset of
            :data:`wikipedia_search_extract_http.SUPPORTED_ACTIONS`.
        base_url: override the Action API base URL (default: English
            Wikipedia). Other language wikis use a different host
            (e.g. ``https://de.wikipedia.org/w/api.php``).
        catalog_path: override the indicator catalog. Default:
            checked-in.
        cache_dir: override the JSON cache root. Default: data-lake
            path (``data/raw/wikipedia_search_extract/cache/``).
        force_refresh: re-download even when the cache file exists.
        request_timeout: per-request HTTP timeout in seconds.
        search_limit: per-request ``srlimit`` for the ``search``
            action (1..50 per the API docs; default 10).

    Returns:
        A long-format pandas DataFrame with columns ``action``,
        ``query``, ``pageid``, ``title``, ``extract``, ``raw_value``,
        ``source_row_reference_hint``. One row per Action API page /
        search hit.

    Raises:
        ValueError: ``queries`` is ``None`` or empty (the Stage 2
            contract requires explicit input).
        ValueError: an ``actions`` value is not in
            :data:`wikipedia_search_extract_http.SUPPORTED_ACTIONS`.
        FileNotFoundError: no cached file and no network reachability
            (or ``force_refresh=True`` and HTTP fails).
        RuntimeError: the Action API returned a 4xx error.
    """
    if not queries:
        raise ValueError(
            "queries must be a non-empty list of explicit terms; "
            "the Stage 2 contract is 'do not browse / score' "
            "(the caller passes the terms)."
        )

    specs = load_indicator_catalog(catalog_path=catalog_path)
    available_actions = [spec.raw_column for spec in specs]
    if actions is None:
        actions = list(available_actions)
    else:
        actions = list(actions)
    if not actions:
        raise ValueError(
            "actions must be a non-empty list; the catalog has no "
            "actions"
        )
    unknown = [a for a in actions if a not in SUPPORTED_ACTIONS]
    if unknown:
        raise ValueError(
            f"unsupported actions: {unknown}; expected one of "
            f"{sorted(SUPPORTED_ACTIONS)}"
        )

    cache_root = cache_dir or default_cache_dir()
    cache_root.mkdir(parents=True, exist_ok=True)

    long_frames: list[pd.DataFrame] = []
    cached_pairs: set[tuple[str, str]] = set()
    fetched_pairs: set[tuple[str, str]] = set()

    for query in queries:
        for action in actions:
            url, extra_params = _build_url_for_action(
                base_url, action, query, search_limit=search_limit,
            )
            cache_key = build_cache_key(
                action=action,
                query=query,
                extra_params=extra_params,
            )
            cache_path = cache_root / f"{cache_key}.json"
            payload, came_from_cache = (
                fetch_wikipedia_action_api_payload(
                    url,
                    cache_path=cache_path,
                    force_refresh=force_refresh,
                    request_timeout=request_timeout,
                )
            )
            if came_from_cache:
                cached_pairs.add((query, action))
            else:
                fetched_pairs.add((query, action))
            parsed = _parse_for_action(
                payload, action=action, query=query,
            )
            if not parsed.empty:
                long_frames.append(parsed)

    if not long_frames:
        df = pd.DataFrame(
            columns=[
                "action",
                "query",
                "pageid",
                "title",
                "extract",
                "raw_value",
                "source_row_reference_hint",
            ]
        )
        df.attrs["indicators_cached"] = 0
        df.attrs["indicators_fetched"] = 0
        return df

    long_df = pd.concat(long_frames, ignore_index=True)
    df = long_df
    # Carry cached/fetched counts through df.attrs so the
    # orchestrator can populate
    # ``WikipediaSearchExtractIngestResult.indicators_cached/_fetched``
    # without re-inspecting the cache. Counts are in unique
    # (query, action) pairs, not per-row -- matches the design doc's
    # intent ("how many of the catalog indicators were read from
    # cache" -- not "how many cache files").
    df.attrs["indicators_cached"] = len(cached_pairs)
    df.attrs["indicators_fetched"] = len(fetched_pairs)
    return df


def _build_url_for_action(
    base_url: str,
    action: str,
    query: str,
    *,
    search_limit: int,
) -> tuple[str, dict[str, Any]]:
    """Build the Action API URL + extra-params dict for one (query, action).

    Returns a 2-tuple ``(url, extra_params)`` where ``extra_params``
    is the dict the cache-key builder hashes for the parameter
    sensitivity (e.g. ``{"limit": 10}`` for ``search``). For
    ``extracts``, ``extra_params`` is empty (the URL already
    encodes the deterministic params ``exintro=1&explaintext=1``).
    """
    if action == "extracts":
        url = build_extracts_url(
            base_url, query, exintro=True, explaintext=True,
        )
        return url, {}
    if action == "search":
        url = build_search_url(
            base_url, query, limit=search_limit,
        )
        return url, {"limit": int(search_limit)}
    raise ValueError(
        f"unsupported action {action!r}; expected one of "
        f"{sorted(SUPPORTED_ACTIONS)}"
    )


def _parse_for_action(
    payload: dict[str, Any], *, action: str, query: str,
) -> pd.DataFrame:
    """Parse one Action API response for the given action.

    Thin dispatch to :func:`parse_extracts_response` or
    :func:`parse_search_response`. Defensive: an unknown action
    returns an empty frame (the orchestrator should never pass an
    unknown action because the action set is filtered at the read
    step).
    """
    if action == "extracts":
        return parse_extracts_response(payload, query=query)
    if action == "search":
        return parse_search_response(payload, query=query)
    return pd.DataFrame(
        columns=[
            "action",
            "query",
            "pageid",
            "title",
            "extract",
            "raw_value",
            "source_row_reference_hint",
        ]
    )
