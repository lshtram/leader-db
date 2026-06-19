"""Action API response parser for the Wikipedia search-extract adapter.

This module owns the Action API JSON -> long-format DataFrame parser
for the two supported actions:

- :func:`parse_extracts_response` -- the ``extracts`` action returns
  a ``query.pages`` dict; the parser flattens it to one row per page
  with the article extract (plain text) as ``raw_value``.
- :func:`parse_search_response` -- the ``search`` action returns a
  ``query.search`` list; the parser flattens it to one row per search
  hit with the snippet + title + pageid as the audit trail.

The Action API response shapes:

``extracts`` action:

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

``search`` action:

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

The parser turns each row into a long-format DataFrame with
columns:

- ``action`` -- the API action name (``"extracts"`` or ``"search"``)
- ``query`` -- the caller-supplied query / title string (the
  pre-normalisation value; the cache key uses the normalised value)
- ``pageid`` -- the Wikipedia page id (integer, or ``None`` when
  missing)
- ``title`` -- the page title (string, or ``None`` when missing)
- ``extract`` -- the article extract plain text (``extracts`` only)
  or the search hit snippet (``search`` only)
- ``raw_value`` -- the verbatim per-row payload as JSON (the audit
  trail)
- ``source_row_reference_hint`` -- the canonical row reference
  prefix (``wikipedia:<pageid>:<title>`` or
  ``wikipedia:search:<query_hash>``); the orchestrator composes the
  final ``source_row_reference`` from this hint plus the catalog's
  ``variable_name``.

The frame is intentionally long-format. No wide pivot is needed
because the catalog's ``variable_name`` is per-action and the long
row already carries the action + query / title.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

import pandas as pd

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# extracts response parser
# ---------------------------------------------------------------------------


def parse_extracts_response(
    payload: dict[str, Any],
    *,
    query: str,
) -> pd.DataFrame:
    """Parse an ``action=query&prop=extracts`` response into a long-format frame.

    Returns a frame with columns
    ``action``, ``query``, ``pageid``, ``title``, ``extract``,
    ``raw_value``, ``source_row_reference_hint``. One row per page
    in the ``query.pages`` dict (usually 1; multiple pages are
    possible when the title is ambiguous and the API follows
    redirects).

    Pages missing ``pageid`` or ``title`` are dropped (defensive --
    the API should always emit both). Pages missing ``extract`` are
    kept with ``extract=None`` (the page exists but the extract is
    empty -- a data-quality signal Stage 11 should flag).
    """
    if not isinstance(payload, dict):
        raise ValueError(
            f"Wikipedia extracts response is not a dict; got "
            f"{type(payload).__name__}"
        )
    pages_obj = (
        payload.get("query", {}).get("pages", {})
        if isinstance(payload.get("query"), dict)
        else {}
    )
    if not isinstance(pages_obj, dict):
        raise ValueError(
            f"Wikipedia extracts response .query.pages is not a "
            f"dict; got {type(pages_obj).__name__}"
        )

    rows: list[dict[str, object]] = []
    for page in pages_obj.values():
        if not isinstance(page, dict):
            continue
        pageid = page.get("pageid")
        title = page.get("title")
        extract_text = page.get("extract")
        # Pageid may be -1 for missing pages; treat that as None.
        if pageid is not None and not isinstance(pageid, int):
            try:
                pageid = int(pageid)
            except (TypeError, ValueError):
                pageid = None
        if pageid is not None and pageid <= 0:
            pageid = None
        if not title:
            # A page without a title is unusual; skip it (the
            # ``query`` column is still in the audit trail via
            # ``raw_value``).
            continue
        rows.append(
            {
                "action": "extracts",
                "query": str(query),
                "pageid": pageid,
                "title": str(title),
                "extract": (
                    str(extract_text) if extract_text is not None else None
                ),
                "raw_value": json.dumps(page, ensure_ascii=False),
                "source_row_reference_hint": (
                    f"wikipedia:{pageid}:{title}"
                    if pageid is not None
                    else f"wikipedia:-:{title}"
                ),
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "action",
            "query",
            "pageid",
            "title",
            "extract",
            "raw_value",
            "source_row_reference_hint",
        ],
    )


# ---------------------------------------------------------------------------
# search response parser
# ---------------------------------------------------------------------------


def parse_search_response(
    payload: dict[str, Any],
    *,
    query: str,
) -> pd.DataFrame:
    """Parse an ``action=query&list=search`` response into a long-format frame.

    Returns a frame with columns
    ``action``, ``query``, ``pageid``, ``title``, ``extract`` (here
    carrying the search snippet), ``raw_value``,
    ``source_row_reference_hint``. One row per search hit in the
    ``query.search`` list.
    """
    if not isinstance(payload, dict):
        raise ValueError(
            f"Wikipedia search response is not a dict; got "
            f"{type(payload).__name__}"
        )
    search_obj = (
        payload.get("query", {}).get("search", [])
        if isinstance(payload.get("query"), dict)
        else []
    )
    if not isinstance(search_obj, list):
        raise ValueError(
            f"Wikipedia search response .query.search is not a "
            f"list; got {type(search_obj).__name__}"
        )

    rows: list[dict[str, object]] = []
    for hit in search_obj:
        if not isinstance(hit, dict):
            continue
        pageid = hit.get("pageid")
        title = hit.get("title")
        snippet = hit.get("snippet")
        if pageid is not None and not isinstance(pageid, int):
            try:
                pageid = int(pageid)
            except (TypeError, ValueError):
                pageid = None
        if pageid is not None and pageid <= 0:
            pageid = None
        if not title:
            continue
        rows.append(
            {
                "action": "search",
                "query": str(query),
                "pageid": pageid,
                "title": str(title),
                "extract": (
                    _strip_html_tags(str(snippet))
                    if snippet is not None
                    else None
                ),
                "raw_value": json.dumps(hit, ensure_ascii=False),
                "source_row_reference_hint": (
                    f"wikipedia:search:{pageid}:{title}"
                    if pageid is not None
                    else f"wikipedia:search:-:{title}"
                ),
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "action",
            "query",
            "pageid",
            "title",
            "extract",
            "raw_value",
            "source_row_reference_hint",
        ],
    )


def _strip_html_tags(snippet: str) -> str:
    """Strip simple HTML tags from a search snippet.

    The Action API returns snippets with `<span class="searchmatch">`
    tags around the matched query terms. The parser strips them
    defensively so the audit-trail ``extract`` column is plain text
    (matching the ``extracts`` action's output). The full HTML is
    still preserved in ``raw_value``.
    """
    # ``str.replace`` is sufficient for the limited HTML the API
    # emits; a full HTML parser would be overkill here.
    cleaned = (
        snippet.replace("<span class=\"searchmatch\">", "")
        .replace("</span>", "")
        .replace("<span>", "")
    )
    return cleaned


def query_hash(query: str) -> str:
    """Return a short SHA-256 prefix that uniquely identifies the query.

    Used by :func:`wikipedia_search_extract_db._make_source_row_reference`
    to build the deterministic ``wikipedia:search:<query_hash>``
    reference for search responses where the pageid + title are
    already part of the row reference.
    """
    return hashlib.sha256(
        str(query or "").strip().lower().encode("utf-8")
    ).hexdigest()[:10]


__all__ = [
    "parse_extracts_response",
    "parse_search_response",
    "query_hash",
]
