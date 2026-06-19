"""HTTP + JSON cache layer for the Wikipedia Action API adapter.

This module owns the Wikipedia Action API-specific networking
concerns:

- The API base URL (:data:`WIKIPEDIA_ACTION_API_BASE`).
- The mandatory descriptive ``User-Agent`` header (per the
  Wikimedia User-Agent policy, identical to the Wikidata adapter's
  requirement).
- The cache file I/O helpers (:func:`_read_cached_json`,
  :func:`_write_cached_json`).
- The cache-key builder (:func:`build_cache_key`) that hashes the
  full action + parameters so the cache is content-addressed and
  re-runs with the same inputs skip HTTP.
- The URL builders for the two supported actions
  (:func:`build_extracts_url`,
  :func:`build_search_url`) and the generic single HTTP fetch +
  cache write helper (:func:`fetch_wikipedia_action_api_payload`).
- One automatic retry on ``ConnectionError`` / ``Timeout``; no
  retry on 4xx.

This module is the lowest level of the Wikipedia Action API split:

- :mod:`leaders_db.ingest.wikipedia_search_extract_http` (this) --
  Action API endpoint, HTTP + cache I/O.
- :mod:`leaders_db.ingest.wikipedia_search_extract_parse` --
  Action API JSON -> long-format DataFrame parser.
- :mod:`leaders_db.ingest.wikipedia_search_extract_io` --
  catalog + paths + parquet write + attribution.
- :mod:`leaders_db.ingest.wikipedia_search_extract_db` --
  source / observation DB writes + run manifest.
- :mod:`leaders_db.ingest.wikipedia_search_extract` --
  public orchestrator + Pydantic result + re-exports.

The Action API response shape:

```json
{
  "batchcomplete": "",
  "query": {
    "pages": {
      "736": {
        "pageid": 736,
        "ns": 0,
        "title": "Joe Biden",
        "extract": "Joseph Robinette Biden Jr. ..."
      }
    }
  }
}
```

or for the ``search`` action:

```json
{
  "batchcomplete": "",
  "query": {
    "search": [
      {"ns": 0, "title": "Joe Biden", "pageid": 736, "size": 234567,
       "wordcount": 37654, "snippet": "...", "timestamp": "..."}
    ]
  }
}
```

The parser extracts the title + pageid + extract / snippet and
emits one long-format observation row per page (extracts) or per
search hit (search).
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Wikipedia Action API base URL (English Wikipedia). The full URL is
#: built as ``WIKIPEDIA_ACTION_API_BASE + ?action=query&prop=...`` or
#: ``WIKIPEDIA_ACTION_API_BASE + ?action=query&list=...``.
WIKIPEDIA_ACTION_API_BASE: str = "https://en.wikipedia.org/w/api.php"

#: Required User-Agent header. Per the Wikimedia User-Agent policy
#: (https://meta.wikimedia.org/wiki/User-Agent_policy), generic /
#: bot User-Agents are rate-limited and may be blocked. The header
#: identifies the project and provides a contact URL.
#:
#: Tests can monkeypatch this constant via
#: ``monkeypatch.setattr(http_mod, "WIKIPEDIA_USER_AGENT", "...")`` if
#: a different UA is required for offline integration tests.
WIKIPEDIA_USER_AGENT: str = (
    "leaders-db/0.1.0 (https://github.com/leaders-db/leaders-db; "
    "contact: leaders-db@example.org) python-requests"
)

#: How many times to retry a failed HTTP call. The first attempt is
#: ``0``; we retry once on ``ConnectionError`` / ``Timeout`` (4xx is
#: not retried -- it would just fail again).
WIKIPEDIA_HTTP_MAX_ATTEMPTS: int = 2

#: How long to wait on a single HTTP request before timing out.
WIKIPEDIA_HTTP_TIMEOUT: float = 30.0

#: Action names recognised by :func:`build_cache_key` /
#: :func:`build_extracts_url` / :func:`build_search_url`. The orchestrator
#: validates caller-supplied action names against this set so a
#: mistyped action does not silently hit the wrong endpoint.
SUPPORTED_ACTIONS: frozenset[str] = frozenset({"extracts", "search"})


# ---------------------------------------------------------------------------
# Cache I/O
# ---------------------------------------------------------------------------


def _read_cached_json(cache_path: Path) -> dict[str, Any] | None:
    """Read a Wikipedia Action API JSON cache file and return the parsed object.

    Returns ``None`` if the file is missing or unparseable (the
    caller treats both cases the same -- fall through to HTTP).
    """
    if not cache_path.is_file():
        return None
    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _logger.warning(
            "Wikipedia Action API cache file %s is corrupt (%s); "
            "falling through to HTTP",
            cache_path,
            exc,
        )
        return None


def _write_cached_json(
    cache_path: Path, payload: dict[str, Any] | list[Any]
) -> None:
    """Write a Wikipedia Action API payload to the cache as JSON.

    Creates parent directories as needed. The verbatim API response
    is preserved so a future caller can verify the data matches what
    the server returned.
    """
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Cache-key builder
# ---------------------------------------------------------------------------


def build_cache_key(
    *,
    action: str,
    query: str,
    extra_params: dict[str, Any] | None = None,
) -> str:
    """Build a deterministic cache key for one Action API request.

    The key is ``wikipedia_<action>_<query_hash>_<params_hash>``
    where ``<query_hash>`` is a 10-character SHA-256 prefix of the
    query string (URL-encoded query, defensively normalised), and
    ``<params_hash>`` is a 10-character SHA-256 prefix of the
    JSON-serialised extra params (or ``"default"`` when no extra
    params are set).

    The query string is encoded by ``urllib.parse.quote`` so the
    cache key is stable across URL encoding differences (``+`` vs
    ``%20`` vs ``_`` for spaces). The query is **also** normalised to
    lower-case + stripped of leading / trailing whitespace so case
    differences do not produce different cache keys for the same
    logical query.
    """
    if action not in SUPPORTED_ACTIONS:
        raise ValueError(
            f"unsupported action {action!r}; expected one of "
            f"{sorted(SUPPORTED_ACTIONS)}"
        )
    normalised_query = str(query or "").strip()
    if not normalised_query:
        raise ValueError("query must be a non-empty string")
    query_hash = hashlib.sha256(
        normalised_query.lower().encode("utf-8")
    ).hexdigest()[:10]
    if extra_params is None or len(extra_params) == 0:
        params_part = "default"
    else:
        # Sort the params by key so two callers passing the same
        # logical params in different orders produce the same cache
        # key.
        serialised = json.dumps(
            dict(sorted(extra_params.items())),
            sort_keys=True,
            ensure_ascii=False,
        )
        params_part = hashlib.sha256(
            serialised.encode("utf-8")
        ).hexdigest()[:10]
    return f"wikipedia_{action}_{query_hash}_{params_part}"


# ---------------------------------------------------------------------------
# URL builders
# ---------------------------------------------------------------------------


def build_extracts_url(
    base_url: str, title: str, *, exintro: bool = True, explaintext: bool = True
) -> str:
    """Build the Wikipedia Action API URL for the ``extracts`` action.

    The URL targets ``action=query&prop=extracts`` and returns the
    article lead / intro paragraph (``exintro=1``) as plain text
    (``explaintext=1``) so the parser can read it without HTML
    stripping. ``exintro`` and ``explaintext`` are configurable for
    callers who want the full article or HTML output.
    """
    params: list[tuple[str, str]] = [
        ("action", "query"),
        ("prop", "extracts"),
        ("format", "json"),
        ("titles", str(title)),
        ("redirects", "1"),
    ]
    if exintro:
        params.append(("exintro", "1"))
    if explaintext:
        params.append(("explaintext", "1"))
    return _build_action_api_url(base_url, params)


def build_search_url(base_url: str, srsearch: str, *, limit: int = 10) -> str:
    """Build the Wikipedia Action API URL for the ``search`` action.

    The URL targets ``action=query&list=search`` and returns a hit
    list (titles + snippets) for the given search query. ``limit``
    defaults to 10 (the API's default is 10; the cap is 50 for
    non-bot users per the API docs).
    """
    if limit < 1 or limit > 50:
        raise ValueError(
            f"limit must be in 1..50 per the Wikipedia Action API "
            f"docs; got {limit}"
        )
    params: list[tuple[str, str]] = [
        ("action", "query"),
        ("list", "search"),
        ("format", "json"),
        ("srsearch", str(srsearch)),
        ("srlimit", str(int(limit))),
    ]
    return _build_action_api_url(base_url, params)


def _build_action_api_url(
    base_url: str, params: list[tuple[str, str]]
) -> str:
    """Build a Wikipedia Action API URL with the given params.

    Uses :mod:`urllib.parse` to encode the params so spaces,
    special characters, and non-ASCII Unicode in the query / title
    are percent-encoded correctly. The base URL is used verbatim --
    the caller controls whether to hit English Wikipedia or another
    language wiki by passing a different ``base_url``.
    """
    query_string = urlencode(params)
    return f"{base_url}?{query_string}"


# ---------------------------------------------------------------------------
# HTTP fetch
# ---------------------------------------------------------------------------


def fetch_wikipedia_action_api_payload(
    url: str,
    *,
    cache_path: Path,
    force_refresh: bool = False,
    request_timeout: float = WIKIPEDIA_HTTP_TIMEOUT,
) -> tuple[dict[str, Any], bool]:
    """Fetch the Wikipedia Action API payload for one URL.

    Cache-first, HTTP-fallback. Returns a 2-tuple ``(parsed_payload,
    came_from_cache)``. If the cache file exists and ``force_refresh``
    is ``False``, the payload is read from the cache and
    ``came_from_cache`` is ``True``. Otherwise the payload is
    HTTP-fetched (one automatic retry on ``ConnectionError`` /
    ``Timeout``; no retry on 4xx), written to the cache verbatim, and
    ``came_from_cache`` is ``False``. The race-with-cache-eviction
    case (file disappears between the existence check and the read)
    is handled transparently -- if the cache read returns ``None``,
    the call falls through to HTTP.

    The mandatory ``User-Agent`` header is set on every HTTP call per
    the Wikimedia User-Agent policy.
    """
    if not force_refresh:
        cached = _read_cached_json(cache_path)
        if cached is not None:
            return cached, True

    payload = _http_get_action(
        url,
        cache_path=cache_path,
        timeout=request_timeout,
    )
    return payload, False


def _http_get_action(
    url: str,
    *,
    cache_path: Path,
    timeout: float,
) -> dict[str, Any]:
    """HTTP-GET one Wikipedia Action API request; cache the response on disk.

    Writes the verbatim API response to ``cache_path`` (creating
    parent dirs as needed) so the next call can skip HTTP. One
    automatic retry on ``ConnectionError`` / ``Timeout``; no retry
    on 4xx.
    """
    last_exc: Exception | None = None
    for attempt in range(WIKIPEDIA_HTTP_MAX_ATTEMPTS):
        try:
            response = requests.get(
                url,
                headers={"User-Agent": WIKIPEDIA_USER_AGENT},
                timeout=timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_exc = exc
            if attempt == 0:
                continue
            raise FileNotFoundError(
                f"Wikipedia Action API HTTP failed: {exc}. Cache file "
                f"{cache_path} is missing and the network is "
                "unreachable."
            ) from exc
        except requests.HTTPError as exc:
            # 4xx is not retried. The most common cause is a malformed
            # title / query (400) or rate-limiting (429). Surface the
            # error verbatim so the caller can debug the request.
            raise RuntimeError(
                f"Wikipedia Action API HTTP error "
                f"{exc.response.status_code} for URL {url}: "
                f"{exc.response.text[:512]}"
            ) from exc
        # Success -- write the verbatim response to the cache.
        _write_cached_json(cache_path, payload)
        return payload
    # Defensive: the loop above always returns or raises. If we land
    # here, the retry policy produced no exception but also no
    # payload.
    raise FileNotFoundError(
        f"Wikipedia Action API HTTP failed: {last_exc!r}"
    )


__all__ = [
    "SUPPORTED_ACTIONS",
    "WIKIPEDIA_ACTION_API_BASE",
    "WIKIPEDIA_HTTP_MAX_ATTEMPTS",
    "WIKIPEDIA_HTTP_TIMEOUT",
    "WIKIPEDIA_USER_AGENT",
    "build_cache_key",
    "build_extracts_url",
    "build_search_url",
    "fetch_wikipedia_action_api_payload",
]
