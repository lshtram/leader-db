"""Stage 2 -- FAS Nuclear Notebook HTML table reader.

This module owns the FAS HTML reader: turn the verbatim cached
or fetched "Status of World Nuclear Forces" HTML page into a
wide-format ``pandas.DataFrame`` with columns
``[country, year, snapshot_year, <5 indicator columns>,
<5 _raw_value columns>, source_row_url]``.

Owns:

- :func:`read_fas_status_html` -- the public reader (one page
  per call; returns a wide-format DataFrame + snapshot_year).
- :func:`_parse_meta_date` -- parse the snapshot year from the
  page's ``<meta name="date" content="...">`` element. The
  FAS page has ``Wed, 30 Apr 2014 12:42:33 -0380`` per probe.
- :func:`_parse_country_cell` -- parse the country name from the
  first column of a row (strip leading ``&nbsp;`` and trailing
  whitespace).
- :func:`_parse_count_cell` -- parse a numeric cell into
  ``(value, raw_value)`` handling the 5 sentinels
  (``n.a.``, ``?``, ``<10``, ranges ``100-120``, footnote-letter
  suffixes ``1,600a``).
- :func:`_strip_footnote_letter` -- strip a trailing footnote
  letter from a numeric cell (``1,600a`` -> ``1,600``).
- :func:`_split_table_rows` -- split the verbatim HTML into one
  row per country using regex (the table is well-structured but
  uses inline styles + spans; BeautifulSoup is overkill for the
  prototype).

The HTTP + cache I/O lives in :mod:`fas_http`. The catalog +
paths + parquet write live in :mod:`fas_io`. The DB writes live
in :mod:`fas_db`. The orchestrator lives in :mod:`fas`.

The HTML parsing strategy is intentionally simple (regex-based,
no HTML parser dependency). The FAS status page uses a single
``<table id="table1">`` with a known structure (1 header row +
9 country rows + 1 aggregate ``Total`` row + 1 footer row with
notes). Regex on ``<tr>...</tr>`` blocks with a known column
order is robust and avoids adding a new dependency.

The page's columns are:

  - col 0: country name
  - col 1: Operational Strategic
  - col 2: Operational Nonstrategic
  - col 3: Reserve / Nondeployed
  - col 4: Military Stockpile
  - col 5: Total Inventory

Each numeric cell has the form ``<span style="font-size:
small;">&nbsp;<digits><sup><em>a</em></sup></span>`` (the
``<sup>`` footnote letter is present for some cells). The
reader strips the ``<sup>`` element, the HTML entities, and the
footnote letter, then normalizes the numeric value.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import pandas as pd

from .fas_io import _DEFAULT_SNAPSHOT_YEAR, FAS_STATUS_PAGE_URL

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: The 5 catalog columns in the order they appear in the FAS
#: table. The order is stable per the FAS page layout; if FAS
#: adds a column, this constant must be updated.
_FAS_TABLE_COLUMNS: tuple[str, ...] = (
    "Operational Strategic",
    "Operational Nonstrategic",
    "Reserve/Nondeployed",
    "Military Stockpile",
    "Total Inventory",
)

#: Regex for a single ``<tr>...</tr>`` row in the FAS table. The
#: regex is permissive about whitespace and inline elements; the
#: goal is to capture each table row as a chunk of HTML for
#: further parsing. The regex requires the row to start with a
#: ``<td>`` that contains either ``Country`` (the header row),
#: a country name (a data row), or ``&nbsp;`` (the empty cell
#: that opens the aggregate ``Total`` row).
_ROW_RE = re.compile(
    r"<tr[^>]*>\s*(.*?)\s*</tr>",
    re.IGNORECASE | re.DOTALL,
)

#: Regex for a single ``<td>...</td>`` cell within a row. Used
#: to split a row into its 6 columns (country + 5 numeric).
_CELL_RE = re.compile(
    r"<td[^>]*>(.*?)</td>",
    re.IGNORECASE | re.DOTALL,
)

#: Regex for the footnote letter suffix. The FAS cells use
#: ``<sup><em>a</em></sup>`` (or ``<sup><em>b</em></sup>`` etc.)
#: to attach footnote letters. We strip the entire ``<sup>...``
#: element.
_SUPP_RE = re.compile(
    r"<sup[^>]*>.*?</sup>",
    re.IGNORECASE | re.DOTALL,
)

#: Regex for HTML tags (for cell-text cleanup). Used to strip
#: ``<span>``, ``<em>``, ``<sup>``, etc.
_TAG_RE = re.compile(
    r"<[^>]+>",
)

#: Regex for HTML entities (``&nbsp;``, ``&amp;``, etc.).
_ENTITY_RE = re.compile(
    r"&nbsp;|&amp;|&#160;",
    re.IGNORECASE,
)

#: Regex for the page's meta date. The FAS page has
#: ``<meta content="Wed, 30 Apr 2014 12:42:33 -0380" name="date">``.
#: We extract the year from the 4-digit group.
_META_DATE_RE = re.compile(
    r"<meta[^>]+name=[\"']date[\"'][^>]+content=[\"']([^\"']+)[\"']",
    re.IGNORECASE,
)

#: Regex for the page footer "Current update: April 30, 2014".
#: Used as a fallback when the meta date element is missing.
_FOOTER_DATE_RE = re.compile(
    r"Current update:\s*<strong>([A-Za-z]+\s+\d+,\s+\d{4})</strong>",
    re.IGNORECASE,
)

#: Regex for a numeric range (e.g. ``100-120``). Used to extract
#: the midpoint.
_RANGE_RE = re.compile(r"(\d[\d,]*)\s*-\s*(\d[\d,]*)")

#: Aggregate TOTAL row indicator. The FAS table has one row
#: whose first cell is empty / ``&nbsp;`` and whose numeric
#: cells start with ``~`` or are bolded; this constant is the
#: filter to drop the aggregate row from the per-country frame.
_AGGREGATE_ROW_INDICATOR: str = "~"

#: The list of country names on the FAS status page. Used as a
#: defensive sanity check: if a row's country cell doesn't
#: match any of these, it's either the header row or the
#: aggregate TOTAL row and is filtered out.
_FAS_COUNTRY_WHITELIST: frozenset[str] = frozenset(
    {
        "Russia",
        "United States",
        "France",
        "China",
        "United Kingdom",
        "Israel",
        "Pakistan",
        "India",
        "North Korea",
    }
)


# ---------------------------------------------------------------------------
# Meta + footer date parsing
# ---------------------------------------------------------------------------


def _parse_meta_date(html: str) -> int | None:
    """Parse the snapshot year from the page's meta date element.

    Returns ``None`` if the meta date is missing or unparseable.
    The FAS page has ``<meta content="Wed, 30 Apr 2014 12:42:33
    -0380" name="date">`` -- the regex extracts the full content
    string; we then take the 4-digit year.
    """
    match = _META_DATE_RE.search(html)
    if match is None:
        return None
    content = match.group(1)
    year_match = re.search(r"\b(19|20)\d{2}\b", content)
    if year_match is None:
        return None
    return int(year_match.group(0))


def _parse_footer_date(html: str) -> int | None:
    """Parse the snapshot year from the page's footer "Current update" text."""
    match = _FOOTER_DATE_RE.search(html)
    if match is None:
        return None
    text = match.group(1)
    year_match = re.search(r"\b(19|20)\d{2}\b", text)
    if year_match is None:
        return None
    return int(year_match.group(0))


def resolve_snapshot_year(html: str) -> int:
    """Return the snapshot year for a FAS HTML page.

    Tries the meta date first, then the footer text, then falls
    back to the conservative default. The ``snapshot_year`` is
    recorded in the run manifest so downstream stages know the
    freshness of the data (the FAS page is updated
    "continuously" but the consolidated snapshot may be stale).
    """
    year = _parse_meta_date(html)
    if year is not None:
        return year
    year = _parse_footer_date(html)
    if year is not None:
        return year
    return _DEFAULT_SNAPSHOT_YEAR


# ---------------------------------------------------------------------------
# Cell coercion
# ---------------------------------------------------------------------------


def _strip_html(cell: str) -> str:
    """Strip HTML tags + entities from a table cell, return the text.

    The FAS cells use ``<span>``, ``<em>``, ``<sup>`` for
    formatting; the underlying text is the number or sentinel.
    """
    no_tags = _TAG_RE.sub("", cell)
    no_entities = _ENTITY_RE.sub("", no_tags)
    return no_entities.strip()


def _strip_sup(cell: str) -> str:
    """Strip the ``<sup>...</sup>`` element from a cell (preserves the digit text)."""
    return _SUPP_RE.sub("", cell)


def _coerce_count_cell(cell: str) -> tuple[int | None, str]:
    """Coerce a FAS numeric cell to ``(value, raw_value)``.

    Sentinels:

    - ``n.a.`` -> ``(None, "n.a.")``
    - ``?`` -> ``(None, "?")``
    - ``<10`` (or HTML-encoded ``&lt;10``) -> ``(10, "<10")``
      (upper bound per FAS convention)
    - ``100-120`` -> midpoint int ``(110, "100-120")``
    - ``1,600`` or ``1,600a`` -> int after stripping commas +
      footnote letter -> ``(1600, "1,600a")``

    Returns a 2-tuple ``(value, raw_value)``. ``value`` is
    ``int | None``; ``raw_value`` is ``str`` (the literal cell
    text, or ``""`` for an empty cell).
    """
    if cell is None:
        return None, ""
    cleaned = _strip_sup(cell)
    cleaned = _strip_html(cleaned).strip()
    if not cleaned:
        return None, ""
    raw = cleaned
    # Sentinel dispatch (order matters).
    if raw.lower() == "n.a.":
        return None, raw
    if raw == "?":
        return None, raw
    # HTML-encoded "<" sentinel. The FAS HTML uses ``&lt;10``
    # (with the ``<`` HTML-encoded) for the "<10" sentinel. The
    # ``raw`` value passed to this function has already had HTML
    # tags stripped, but HTML entities (e.g. ``&lt;``) survive.
    # Decode ``&lt;`` to ``<`` for the sentinel check, but
    # preserve the original literal in ``raw_value``.
    if raw.startswith("&lt;"):
        try:
            return int(raw[4:]), raw
        except ValueError:
            return None, raw
    if raw.startswith("<"):
        try:
            return int(raw[1:]), raw
        except ValueError:
            return None, raw
    # Range "100-120"
    range_match = _RANGE_RE.match(raw)
    if range_match is not None:
        try:
            low = int(range_match.group(1).replace(",", ""))
            high = int(range_match.group(2).replace(",", ""))
            return (low + high) // 2, raw
        except ValueError:
            return None, raw
    # Plain numeric "1,600" or with footnote "1,600a"
    no_commas = raw.replace(",", "").replace(" ", "")
    # Strip any trailing letter (footnote letter)
    stripped = re.sub(r"[a-z]+\s*$", "", no_commas, flags=re.IGNORECASE)
    try:
        return int(stripped), raw
    except ValueError:
        # The cell is not a recognizable number; preserve as raw.
        return None, raw


def _parse_country_cell(cell: str) -> str | None:
    """Parse the country name from a row's first cell.

    Returns ``None`` for the header row (where the cell is
    ``Country``) and for the aggregate TOTAL row (where the
    cell is empty). Returns the cleaned country name for valid
    data rows.
    """
    cleaned = _strip_html(cell).strip()
    # The FAS HTML uses ``&nbsp;`` (the HTML entity) AND the
    # Unicode non-breaking-space ``\u00a0`` as padding. Strip
    # both forms defensively.
    cleaned = (
        cleaned.replace("&nbsp;", "")
        .replace("\u00a0", "")
        .strip()
    )
    if not cleaned:
        return None
    if cleaned == "Country":
        return None
    # The aggregate TOTAL row has the country cell empty but the
    # numeric cells start with ``~``. The caller checks this.
    return cleaned


# ---------------------------------------------------------------------------
# Row splitting
# ---------------------------------------------------------------------------


def _split_table_rows(html: str) -> list[list[str]]:
    """Split the FAS HTML table into a list of rows (each row is a list of 6 cell strings).

    The table layout is well-defined: 1 header row + 9 country
    rows + 1 aggregate TOTAL row + 1 footer (notes) row. The
    function extracts every ``<tr>...</tr>`` block from the
    ``<table id="table1">`` element, splits each into its 6
    ``<td>...</td>`` cells, and returns the cell-text list.

    The function is defensive about duplicate ``id="table1"``
    blocks: the FAS page renders the table twice (once as an
    empty placeholder, once with the actual data); the
    function picks the longest match (the one with content).
    Rows with fewer than 6 cells (the header row has 6 cells
    with different text alignment; the footer row has 1
    colspan=6 cell) are skipped.
    """
    # Restrict the extraction to the table with id="table1" so
    # the navigation bar (which has other <tr> elements) is
    # excluded.
    table_matches = list(
        re.finditer(
            r'<table[^>]+id="table1"[^>]*>(.*?)</table>',
            html,
            re.IGNORECASE | re.DOTALL,
        )
    )
    if not table_matches:
        return []
    # Pick the longest match (the data table). The FAS page
    # has 2 matches: one empty placeholder (~225 chars) and
    # one with the actual data (~19 KB). The data match is
    # much longer.
    table_match = max(table_matches, key=lambda m: len(m.group(1)))
    table_html = table_match.group(1)
    rows: list[list[str]] = []
    for row_match in _ROW_RE.finditer(table_html):
        row_html = row_match.group(1)
        cells = _CELL_RE.findall(row_html)
        if len(cells) < 6:
            continue
        # Keep only the first 6 cells (the canonical table has 6
        # columns; defensive against future additions).
        rows.append(cells[:6])
    return rows


# ---------------------------------------------------------------------------
# Public reader
# ---------------------------------------------------------------------------


def read_fas_status_html(
    html: str,
    *,
    catalog: list[Any] | None = None,
    snapshot_year: int | None = None,
) -> tuple[pd.DataFrame, int]:
    """Read the FAS Status of World Nuclear Forces HTML into a wide DataFrame.

    The wide frame has 9 country rows x 1 snapshot year x 5
    indicator columns + 5 ``_raw_value`` sibling columns +
    ``source_row_url``. Sorted by ``country`` ascending for
    deterministic idempotency.

    Args:
        html: the verbatim FAS HTML (from cache or HTTP fetch).
        catalog: reserved for future per-spec filtering; not
            consumed.
        snapshot_year: override the parsed snapshot year. Default:
            parse from the page's meta date + footer text.

    Returns:
        A 2-tuple ``(df, snapshot_year)``. The DataFrame has
        columns ``country``, ``year``, ``<5 indicator columns>``,
        ``<5 _raw_value columns>``, ``source_row_url``. The
        ``snapshot_year`` is the integer year the page documents
        (e.g. ``2014`` for the live page as of probe).
    """
    rows = _split_table_rows(html)
    if not rows:
        return _empty_wide_frame(), (
            int(snapshot_year)
            if snapshot_year is not None
            else resolve_snapshot_year(html)
        )

    parsed_snapshot_year = (
        int(snapshot_year)
        if snapshot_year is not None
        else resolve_snapshot_year(html)
    )

    out_rows: list[dict[str, object]] = []
    for cells in rows:
        country = _parse_country_cell(cells[0])
        if country is None:
            continue
        # The aggregate TOTAL row has the country cell empty
        # (caught above) AND the numeric cells start with
        # ``~``. Defensive: drop any row whose country name is
        # not in the whitelist OR whose first numeric cell starts
        # with ``~``.
        if country not in _FAS_COUNTRY_WHITELIST:
            continue
        first_numeric_raw = _strip_html(_strip_sup(cells[1]))
        first_numeric_raw = (
            first_numeric_raw.replace("&nbsp;", "")
            .replace("\u00a0", "")
            .strip()
        )
        if first_numeric_raw.startswith(_AGGREGATE_ROW_INDICATOR):
            # Aggregate row (e.g. ``~4,000``). Skip.
            continue

        row_dict: dict[str, object] = {
            "country": country,
            "year": int(parsed_snapshot_year),
            "source_row_url": FAS_STATUS_PAGE_URL,
        }
        for i, col_name in enumerate(_FAS_TABLE_COLUMNS, start=1):
            value, raw_value = _coerce_count_cell(cells[i])
            # The variable name is derived from the column header
            # by lowercasing + replacing spaces with underscores.
            # This matches the catalog's ``raw_column`` values.
            var_name = "fas_" + col_name.lower().replace(" ", "_").replace(
                "/", "_"
            )
            row_dict[var_name] = value
            row_dict[f"{var_name}_raw_value"] = raw_value
        out_rows.append(row_dict)

    if not out_rows:
        return _empty_wide_frame(), parsed_snapshot_year

    df = pd.DataFrame(out_rows)
    # Sort by country for deterministic idempotency.
    df = df.sort_values("country", kind="mergesort").reset_index(
        drop=True
    )
    df["year"] = df["year"].astype(int)
    return df, parsed_snapshot_year


def _empty_wide_frame() -> pd.DataFrame:
    """Return an empty DataFrame with the canonical wide schema.

    Used when the HTML has no parseable rows. The schema matches
    the columns produced by :func:`read_fas_status_html` so
    downstream code can iterate uniformly.
    """
    columns = [
        "country",
        "year",
        "source_row_url",
    ]
    for col_name in _FAS_TABLE_COLUMNS:
        var_name = "fas_" + col_name.lower().replace(" ", "_").replace(
            "/", "_"
        )
        columns.append(var_name)
        columns.append(f"{var_name}_raw_value")
    return pd.DataFrame(columns=columns)


__all__ = ["read_fas_status_html", "resolve_snapshot_year"]
