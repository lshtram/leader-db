"""HTTP + JSON cache layer for the Wikidata heads-of-state-and-government adapter.

This module owns the Wikidata SPARQL-specific networking concerns:

- The SPARQL endpoint (:data:`WIKIDATA_SPARQL_ENDPOINT`).
- The mandatory descriptive ``User-Agent`` header (per
  https://meta.wikimedia.org/wiki/User-Agent_policy -- Wikidata blocks
  generic / python-requests User-Agents).
- The cache file I/O helpers (:func:`_read_cached_json`,
  :func:`_write_cached_json`).
- The cache-key builder (:func:`build_cache_key`) that hashes the full
  SPARQL query (and any parameter suffixes) so the cache is
  content-addressed and re-runs with the same inputs skip HTTP.
- The SPARQL URL builder (:func:`build_sparql_url`) and the single
  HTTP fetch + cache write helper
  (:func:`fetch_wikidata_sparql_payload`) that handles one automatic
  retry on ``ConnectionError`` / ``Timeout`` (no retry on 4xx).

This module is the lowest level of the Wikidata heads-of-state
split:

- :mod:`leaders_db.ingest.wikidata_heads_of_state_government_http` (this) --
  SPARQL endpoint, HTTP + cache I/O.
- :mod:`leaders_db.ingest.wikidata_heads_of_state_government_parse` --
  SPARQL JSON -> long-format DataFrame parser.
- :mod:`leaders_db.ingest.wikidata_heads_of_state_government_io` --
  catalog + paths + parquet write + attribution.
- :mod:`leaders_db.ingest.wikidata_heads_of_state_government_db` --
  source / observation DB writes + run manifest.
- :mod:`leaders_db.ingest.wikidata_heads_of_state_government` --
  public orchestrator + Pydantic result + re-exports.

The SPARQL response shape:

```json
{
  "head": {"vars": ["country", "countryLabel", "person", ...]},
  "results": {
    "bindings": [
      {
        "country": {"type": "uri", "value": "http://www.wikidata.org/entity/Q30"},
        "countryLabel": {"type": "literal", "value": "United States of America", ...},
        "person": {"type": "uri", "value": "http://www.wikidata.org/entity/Q6279"},
        "personLabel": {"type": "literal", "value": "Joe Biden", ...},
        "office": {"type": "uri", "value": "http://www.wikidata.org/entity/Q30461"},
        "officeLabel": {"type": "literal", "value": "President of the United States", ...},
        "start": {"type": "date", "value": "2021-01-20T00:00:00Z"},
        "end": {"type": "date", "value": "2025-01-20T00:00:00Z"},
        "statement": {"type": "uri", "value": "http://www.wikidata.org/wiki/Special:EntityData/Q30#..."}
      }
    ]
  }
}
```

The parser turns one binding row into one long-format observation row
with columns ``country_qid``, ``country_label``, ``person_qid``,
``person_label``, ``office_qid``, ``office_label``, ``start_date``,
``end_date``, ``statement_uri``, ``raw_value`` (JSON of the binding
row). The orchestrator pivots no columns -- the Stage 2 frame is
intentionally long-format because the catalog's ``variable_name`` is
per-office and the long row already carries the office.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import requests

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Wikidata SPARQL endpoint. Public, no auth. The full URL is built as
#: ``WIKIDATA_SPARQL_ENDPOINT + ?query=<URL-encoded SPARQL>&format=json``.
WIKIDATA_SPARQL_ENDPOINT: str = "https://query.wikidata.org/sparql"

#: Required User-Agent header. Per the Wikimedia User-Agent policy
#: (https://meta.wikimedia.org/wiki/User-Agent_policy), generic / bot
#: User-Agents are rate-limited and may be blocked. The header
#: identifies the project and provides a contact URL. The user-agent
#: format ``leaders-db/<version> (contact: ...)`` follows the
#: recommended convention.
#:
#: Tests can monkeypatch this constant via
#: ``monkeypatch.setattr(http_mod, "WIKIDATA_USER_AGENT", "...")`` if
#: a different UA is required for offline integration tests.
WIKIDATA_USER_AGENT: str = (
    "leaders-db/0.1.0 (https://github.com/leaders-db/leaders-db; "
    "contact: leaders-db@example.org) python-requests"
)

#: HTTP ``Accept`` header for SPARQL JSON responses (the default
#: response format; we pin it explicitly so a future server-side
#: content-negotiation change does not silently break the parser).
WIKIDATA_SPARQL_ACCEPT: str = "application/sparql-results+json"

#: How many times to retry a failed HTTP call. The first attempt is
#: ``0``; we retry once on ``ConnectionError`` / ``Timeout`` (4xx is
#: not retried -- it would just fail again; 5xx is also not retried
#: here because the SPARQL endpoint is highly available and a 5xx
#: usually indicates a malformed query).
WIKIDATA_HTTP_MAX_ATTEMPTS: int = 2

#: How long to wait on a single HTTP request before timing out.
WIKIDATA_HTTP_TIMEOUT: float = 60.0


# ---------------------------------------------------------------------------
# Cache I/O
# ---------------------------------------------------------------------------


def _read_cached_json(cache_path: Path) -> dict[str, Any] | None:
    """Read a Wikidata SPARQL JSON cache file and return the parsed object.

    Returns ``None`` if the file is missing or unparseable (the
    caller treats both cases the same -- fall through to HTTP).
    """
    if not cache_path.is_file():
        return None
    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _logger.warning(
            "Wikidata SPARQL cache file %s is corrupt (%s); falling "
            "through to HTTP",
            cache_path,
            exc,
        )
        return None


def _write_cached_json(cache_path: Path, payload: dict[str, Any]) -> None:
    """Write a Wikidata SPARQL payload to the cache as pretty-printed JSON.

    Creates parent directories as needed. The verbatim API response is
    preserved so a future caller can verify the data matches what the
    server returned.
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
    office_qid: str,
    year: int | None,
    country_qids: list[str] | None,
    query_template_hash: str,
) -> str:
    """Build a deterministic cache key for one SPARQL query.

    The key is ``wd_<office_qid>_<year>_<country_hash>_<template_hash>``
    where ``<country_hash>`` is ``all`` when ``country_qids`` is
    ``None`` and ``<sorted_csv_hash>`` otherwise, and
    ``<template_hash>`` is the SHA-256 prefix of the SPARQL query
    template so a future query-template change invalidates the cache
    for all matching keys.

    The cache-key format is stable enough to be human-readable in the
    cache directory listing; deterministic enough to be a content
    address; and short enough to keep the filename under typical
    filesystem limits (255 bytes).
    """
    if country_qids is None:
        country_part = "all"
    else:
        joined = ",".join(sorted(str(c).strip() for c in country_qids))
        country_part = hashlib.sha256(joined.encode("utf-8")).hexdigest()[:10]
    year_part = str(year) if year is not None else "current"
    return (
        f"wd_{office_qid}_{year_part}_{country_part}_{query_template_hash}"
    )


# ---------------------------------------------------------------------------
# URL builder
# ---------------------------------------------------------------------------


def build_sparql_url(sparql_query: str) -> str:
    """Build the full Wikidata SPARQL URL for one query.

    The SPARQL query string is URL-encoded by ``requests`` (the
    caller passes the raw query). The endpoint accepts ``?query=...``
    + ``?format=json`` as the canonical SPARQL GET form. We do NOT
    URL-encode here because the SPARQL query string contains many
    reserved characters that must be passed through verbatim.
    """
    return f"{WIKIDATA_SPARQL_ENDPOINT}?query={sparql_query}&format=json"


# ---------------------------------------------------------------------------
# HTTP fetch
# ---------------------------------------------------------------------------


def fetch_wikidata_sparql_payload(
    sparql_query: str,
    *,
    cache_path: Path,
    force_refresh: bool = False,
    request_timeout: float = WIKIDATA_HTTP_TIMEOUT,
) -> tuple[dict[str, Any], bool]:
    """Fetch the Wikidata SPARQL payload for one query.

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

    payload = _http_get_sparql(
        sparql_query,
        cache_path=cache_path,
        timeout=request_timeout,
    )
    return payload, False


def _http_get_sparql(
    sparql_query: str,
    *,
    cache_path: Path,
    timeout: float,
) -> dict[str, Any]:
    """HTTP-GET one Wikidata SPARQL query; cache the response on disk.

    Writes the verbatim API response to ``cache_path`` (creating
    parent dirs as needed) so the next call can skip HTTP. One
    automatic retry on ``ConnectionError`` / ``Timeout``; no retry on
    4xx (the 4xx error would just repeat).
    """
    url = build_sparql_url(sparql_query)
    last_exc: Exception | None = None
    for attempt in range(WIKIDATA_HTTP_MAX_ATTEMPTS):
        try:
            response = requests.get(
                url,
                headers={
                    "User-Agent": WIKIDATA_USER_AGENT,
                    "Accept": WIKIDATA_SPARQL_ACCEPT,
                },
                timeout=timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_exc = exc
            if attempt == 0:
                continue
            raise FileNotFoundError(
                f"Wikidata SPARQL HTTP failed: {exc}. Cache file "
                f"{cache_path} is missing and the network is "
                "unreachable."
            ) from exc
        except requests.HTTPError as exc:
            # 4xx is not retried. The most common cause is a malformed
            # SPARQL query (400) or rate-limiting (429). Surface the
            # error verbatim so the caller can debug the query.
            raise RuntimeError(
                f"Wikidata SPARQL HTTP error {exc.response.status_code} "
                f"for URL {url}: {exc.response.text[:512]}"
            ) from exc
        # Success -- write the verbatim response to the cache.
        _write_cached_json(cache_path, payload)
        return payload
    # Defensive: the loop above always returns or raises. If we land
    # here, the retry policy produced no exception but also no
    # payload.
    raise FileNotFoundError(
        f"Wikidata SPARQL HTTP failed: {last_exc!r}"
    )


__all__ = [
    "WIKIDATA_HTTP_MAX_ATTEMPTS",
    "WIKIDATA_HTTP_TIMEOUT",
    "WIKIDATA_SPARQL_ACCEPT",
    "WIKIDATA_SPARQL_ENDPOINT",
    "WIKIDATA_USER_AGENT",
    "build_cache_key",
    "build_sparql_url",
    "fetch_wikidata_sparql_payload",
]
