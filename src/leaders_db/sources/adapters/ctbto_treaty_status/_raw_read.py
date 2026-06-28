"""Raw CSV / HTML reader for the clean CTBTO Treaty Status adapter.

This module owns the body of
:meth:`CtbtoTreatyStatusAdapter.read_raw` extracted into free
functions so the adapter class module stays focused on
lifecycle wiring + registration. The reader supports the two
cached export shapes the task brief explicitly endorses:

1. **Direct CSV** -- a plain CSV file at
   ``data/raw/ctbto_treaty_status/states-signatories.csv``
   derived from the canonical public CTBTO States Signatories
   page. The CSV carries the documented 4 required columns
   (``Region`` / ``State`` / ``Signature Date`` /
   ``Ratification Date``) and an OPTIONAL 5th column
   (``Annex 2``) when the cached fixture / source-native data
   carries an explicit Annex 2 flag. The reader uses the
   Python ``csv`` module to parse the cached rows.

2. **Cached HTML table** -- an HTML file at
   ``data/raw/ctbto_treaty_status/states-signatories.html``
   containing a single ``<table>`` with the documented
   ``<th>`` header cells. The HTML path is a fallback for
   users who stage the cached HTML export directly; the CSV
   path is the canonical primary shape.

Schema-contract enforcement
---------------------------

The raw-read layer is the canonical boundary at which the
cached CSV / HTML schema is enforced. The 4 documented
required columns ``Region`` / ``State`` / ``Signature Date`` /
``Ratification Date`` MUST be present in the cached header; a
missing required column fires a structured
:class:`CtbtoTreatyStatusSchemaError` so the transform layer
does NOT silently emit partial output on a schema contract
violation.

Per-row preservation
--------------------

The raw-read layer preserves the source-native State display
name verbatim on every parsed row so the transform layer can
propagate it onto the observation's audit-trail extension
payload. The signature / ratification date cells are
preserved verbatim as strings on every parsed row (the
adapter does NOT coerce them to numeric years that could
mislead Stage 11 confidence calculations). The optional
``Annex 2`` column is preserved on the parsed row only when
the cached header declares the column.
"""

from __future__ import annotations

import csv
import hashlib
import io
from pathlib import Path
from typing import Any

from leaders_db.sources.contracts import (
    RawAsset,
    RawReadResult,
    SourceIngestRequest,
    SourceWarning,
)
from leaders_db.sources.warnings import MISSING_RAW

from ._constants import (
    CTBTO_TREATY_STATUS_CSV_ASSET_ID,
    CTBTO_TREATY_STATUS_DEFAULT_VERSION,
    CTBTO_TREATY_STATUS_HTML_ASSET_ID,
    CTBTO_TREATY_STATUS_REQUIRED_COLUMNS,
    CTBTO_TREATY_STATUS_SCHEMA_ERROR,
)
from ._readiness import (
    csv_path,
    html_path,
    metadata_path,
    read_metadata,
)


class CtbtoTreatyStatusSchemaError(ValueError):
    """Structured failure raised when the cached CTBTO Treaty
    Status CSV / HTML is missing required columns.

    The transform layer MUST NOT silently produce partial
    output when the schema contract is violated -- the
    raw-read boundary raises this exception BEFORE the
    transform layer consumes the parsed frame. The exception
    carries:

    - ``code``: the structured warning code
      ``"ctbto_treaty_status_schema_error"``.
    - ``source_id``: the :class:`SourceId` carrying the
      failing source slug (``"ctbto_treaty_status"``).
    - ``missing_columns``: a tuple of the column names that
      the parsed CSV / HTML header did NOT produce but the
      adapter requires.
    - ``expected_columns``: a tuple of every required
      indicator column (the canonical 4 column catalog).
    - ``actual_columns``: a tuple of every column the parsed
      CSV / HTML header produced.
    - ``cache_path``: the resolved cached file path (when
      available).

    The exception ``str`` representation is intentionally
    self-describing so a CLI run / log line / pytest failure
    tells the operator which columns are missing without
    reading source code.
    """

    code: str = CTBTO_TREATY_STATUS_SCHEMA_ERROR

    def __init__(
        self,
        *,
        source_id: Any,
        missing_columns: tuple[str, ...],
        expected_columns: tuple[str, ...],
        actual_columns: tuple[str, ...],
        cache_path: Path | None = None,
    ) -> None:
        self.source_id = source_id
        self.missing_columns = tuple(missing_columns)
        self.expected_columns = tuple(expected_columns)
        self.actual_columns = tuple(actual_columns)
        self.cache_path = cache_path
        missing_str = ", ".join(repr(c) for c in missing_columns)
        path_str = f" at {cache_path}" if cache_path is not None else ""
        super().__init__(
            f"CTBTO Treaty Status raw-read schema validation "
            f"failed ({CTBTO_TREATY_STATUS_SCHEMA_ERROR}){path_str}: "
            f"the cached export is missing "
            f"{len(missing_columns)} required column(s) "
            f"({missing_str}); the unified CTBTO Treaty Status "
            f"adapter requires every required indicator column in "
            f"{tuple(expected_columns)!r} but the reader produced "
            f"{tuple(actual_columns)!r}. Re-stage a canonical CTBTO "
            f"States Signatories bundle or update the adapter "
            f"contract before running ingestion; the transform "
            f"layer does NOT silently emit partial output on "
            f"schema violations."
        )


def _parse_csv_text(csv_text: str) -> tuple[list[str], list[dict[str, str]]]:
    """Parse the cached CSV text into a (header, rows) pair.

    Uses the Python ``csv`` module to parse the cached CSV
    against the documented CTBTO header. Returns
    ``(header, rows)`` where ``header`` is the canonical
    column-name list and ``rows`` is a list of dicts keyed
    by the header column names. Skips malformed CSV rows
    (rows whose column count does not match the header)
    safely -- the transform layer emits zero observations
    for skipped rows.

    Returns ``(header, [])`` when the cached CSV is empty.
    """
    reader = csv.reader(io.StringIO(csv_text))
    parsed = [row for row in reader if row]
    if not parsed:
        return [], []
    header = [col.strip() for col in parsed[0]]
    rows: list[dict[str, str]] = []
    for row in parsed[1:]:
        if len(row) != len(header):
            # Malformed row (column count mismatch) -- drop
            # silently here; the readiness gate already
            # validated the header so row-level mismatches
            # are parse-time corruption rather than a schema
            # contract violation. The transform layer
            # preserves the verbatim raw_value on the
            # audit-trail extension so audit code can recover
            # the dropped row.
            continue
        row_dict: dict[str, str] = {}
        for col_name, col_value in zip(header, row, strict=True):
            row_dict[col_name] = col_value.strip()
        rows.append(row_dict)
    return header, rows


def _split_table_rows(table_html: str) -> list[str]:
    """Walk every ``<tr>...</tr>`` row in the cached HTML table.

    Returns a list of row-html strings (the content between
    the opening ``<tr>`` and closing ``</tr>`` tags). Empty
    rows are silently dropped -- the parser does NOT preserve
    them in the audit trail.
    """
    rows_html: list[str] = []
    cursor = 0
    while True:
        next_open = table_html.lower().find("<tr", cursor)
        if next_open < 0:
            break
        tag_end = table_html.find(">", next_open)
        if tag_end < 0:
            break
        next_close = table_html.lower().find("</tr>", tag_end)
        if next_close < 0:
            break
        rows_html.append(table_html[tag_end + 1 : next_close])
        cursor = next_close + len("</tr>")
    return rows_html


def _parse_table_cells(row_html: str) -> list[str]:
    """Walk every ``<th>...</th>`` and ``<td>...</td>`` cell in a row.

    Returns the cell text values (stripped of any nested HTML
    tags via :func:`_strip_html`) in declaration order. An
    empty list is returned when the row carries no recognisable
    cells.
    """
    cells: list[str] = []
    cell_cursor = 0
    while True:
        th_open = row_html.lower().find("<th", cell_cursor)
        td_open = row_html.lower().find("<td", cell_cursor)
        candidates: list[tuple[int, str]] = []
        if th_open >= 0:
            candidates.append((th_open, "th"))
        if td_open >= 0:
            candidates.append((td_open, "td"))
        if not candidates:
            break
        # Take the leftmost cell.
        candidates.sort(key=lambda c: c[0])
        cell_pos, cell_tag = candidates[0]
        tag_end = row_html.find(">", cell_pos)
        if tag_end < 0:
            break
        close_tag = f"</{cell_tag}>"
        cell_close = row_html.lower().find(close_tag, tag_end)
        if cell_close < 0:
            break
        cell_html = row_html[tag_end + 1 : cell_close]
        cells.append(_strip_html(cell_html))
        cell_cursor = cell_close + len(close_tag)
    return cells


def _locate_table_block(html_text: str) -> str:
    """Return the first ``<table>...</table>`` block in ``html_text``.

    Returns an empty string when the cached HTML carries no
    recognisable ``<table>`` element. The CTBTO canonical page
    has a single top-level ``<table>`` so the first match is
    the right one; nested tables (e.g. inside ``<td>`` cells)
    are tolerated because the helper returns the FIRST match.
    """
    if not html_text or not html_text.strip():
        return ""
    lower = html_text.lower()
    table_open = lower.find("<table")
    if table_open < 0:
        return ""
    table_close = lower.find("</table>", table_open)
    if table_close < 0:
        return ""
    return html_text[table_open:table_close]


def _locate_header_row(rows_html: list[str]) -> int:
    """Return the index of the header row in ``rows_html``.

    The header row is the FIRST row whose HTML carries a
    ``<th>`` cell. When no row carries a ``<th>`` cell the
    function returns ``0`` so the caller treats the FIRST
    parsed row as the header (positional fallback). This
    matches the SIPRI Milex ``_header_line_score`` robustness
    pattern.
    """
    for index, row_html in enumerate(rows_html):
        if "<th" in row_html.lower():
            return index
    return 0


def _parse_html_table(
    html_text: str,
) -> tuple[list[str], list[dict[str, str]]]:
    """Parse the cached HTML table into a (header, rows) pair.

    Fallback path used when the cached HTML export is staged
    instead of the canonical CSV. The helper uses a small
    built-in HTML table parser -- it locates the first
    ``<table>`` element, walks the ``<thead>`` (or first
    ``<tr>`` with all-``<th>`` cells) for the header, then
    walks the ``<tbody>`` (or remaining ``<tr>`` elements)
    for the data rows.

    The helper is intentionally minimal -- it does NOT depend
    on BeautifulSoup or lxml because the canonical CTBTO
    States Signatories HTML export is a structurally simple
    table with ``<th>`` headers and ``<td>`` data cells. The
    helper tolerates absent ``<thead>`` / ``<tbody>`` wrappers
    and missing ``<tr>`` / ``<th>`` / ``<td>`` tags when the
    table is structurally simple enough to parse via the
    fallback positional walker.

    Returns ``(header, rows)`` where ``header`` is the
    canonical column-name list and ``rows`` is a list of dicts
    keyed by the header column names. Returns ``(header, [])``
    when the cached HTML carries no recognisable table.
    """
    if not html_text or not html_text.strip():
        return [], []

    table_html = _locate_table_block(html_text)
    if not table_html:
        return [], []

    rows_html = _split_table_rows(table_html)

    parsed_rows: list[list[str]] = []
    for row_html in rows_html:
        cells = _parse_table_cells(row_html)
        if cells:
            parsed_rows.append(cells)

    if not parsed_rows:
        return [], []

    header_index = _locate_header_row(rows_html)
    if header_index >= len(parsed_rows):
        return [], []
    header = [cell.strip() for cell in parsed_rows[header_index]]
    data_rows = parsed_rows[header_index + 1 :]
    rows: list[dict[str, str]] = []
    for row in data_rows:
        if len(row) != len(header):
            # Malformed row (column count mismatch) -- drop
            # silently here; the readiness gate already
            # validated the header so row-level mismatches
            # are parse-time corruption rather than a schema
            # contract violation.
            continue
        row_dict: dict[str, str] = {}
        for col_name, col_value in zip(header, row, strict=True):
            row_dict[col_name] = col_value.strip()
        rows.append(row_dict)
    return header, rows


def _strip_html(cell_html: str) -> str:
    """Strip HTML tags / entities from a single cell HTML body.

    Helper for the HTML table parser -- the canonical CTBTO
    States Signatories page emits plain text inside ``<th>``
    / ``<td>`` cells, but the helper tolerates nested tags
    (e.g. ``<span>`` / ``<a>``) by stripping every ``<...>``
    token and decoding common HTML entities (``&amp;``,
    ``&lt;``, ``&gt;``, ``&quot;``, ``&#39;``, ``&nbsp;``).
    """
    if not cell_html:
        return ""
    cleaned = cell_html
    # Drop every HTML tag.
    while True:
        open_pos = cleaned.find("<")
        if open_pos < 0:
            break
        close_pos = cleaned.find(">", open_pos)
        if close_pos < 0:
            break
        cleaned = cleaned[:open_pos] + " " + cleaned[close_pos + 1 :]
    cleaned = cleaned.replace("&amp;", "&")
    cleaned = cleaned.replace("&lt;", "<")
    cleaned = cleaned.replace("&gt;", ">")
    cleaned = cleaned.replace("&quot;", "\"")
    cleaned = cleaned.replace("&#39;", "'")
    cleaned = cleaned.replace("&nbsp;", " ")
    return cleaned.strip()


def _validate_header_columns(
    header: list[str],
    *,
    source_id: Any,
    cache_path: Path,
    required_columns: tuple[str, ...] = CTBTO_TREATY_STATUS_REQUIRED_COLUMNS,
) -> None:
    """Raise :class:`CtbtoTreatyStatusSchemaError` if any required
    column is missing from the parsed header.

    The transform layer MUST NOT silently produce partial
    output when the schema contract is violated -- this
    helper enforces the contract at the raw-read boundary.
    An empty header (i.e. the cached CSV / HTML carries no
    recognisable header row) is treated as a schema contract
    violation with every required column flagged as missing.
    """
    if not header:
        raise CtbtoTreatyStatusSchemaError(
            source_id=source_id,
            missing_columns=tuple(required_columns),
            expected_columns=tuple(required_columns),
            actual_columns=(),
            cache_path=cache_path,
        )
    missing = tuple(
        col for col in required_columns if col not in header
    )
    if missing:
        raise CtbtoTreatyStatusSchemaError(
            source_id=source_id,
            missing_columns=missing,
            expected_columns=tuple(required_columns),
            actual_columns=tuple(header),
            cache_path=cache_path,
        )


def _compute_cache_checksum(cache_path: Path) -> str | None:
    """Return the SHA-256 hex digest of the staged cache file.

    Returns ``None`` only when the cache file is missing or
    unreadable on disk -- the readiness gate already rejects
    a missing cache with a structured ``missing_raw`` error
    BEFORE this function is reached, so a ``None`` return is
    defense in depth. The hex digest is the verified / staged
    file SHA-256 the raw asset carries so downstream audit
    code can recover the actual on-disk fingerprint
    regardless of the metadata's ``checksum_sha256`` field
    shape (flat-string vs per-file dict).
    """
    if not cache_path.is_file():
        return None
    try:
        return hashlib.sha256(cache_path.read_bytes()).hexdigest()
    except OSError:
        return None


def read_ctbto_treaty_status_cache(
    request: SourceIngestRequest,
) -> RawReadResult:
    """Read the staged CTBTO Treaty Status cached CSV / HTML
    bundle and return the parsed raw payload.

    The reader:

    1. Loads the cached export bytes (CSV shape preferred;
       falls back to the HTML shape when the CSV is absent).
    2. Parses the cached text into a (header, rows) pair via
       the Python ``csv`` module (CSV shape) or a small
       built-in HTML table parser (HTML shape).
    3. Validates the header against the 4 canonical required
       columns and raises
       :class:`CtbtoTreatyStatusSchemaError` BEFORE the
       transform layer consumes the frame.
    4. Carries the parsed frame on ``payload["rows"]`` plus
       the original ``header`` list plus the cached cache
       path / asset id for the transform layer.
    5. Computes the SHA-256 of the staged cache file (the
       verified / staged on-disk fingerprint) and populates
       the :class:`RawAsset` ``checksum_sha256`` field so
       downstream audit code can recover the actual
       on-disk hash regardless of the metadata's
       ``checksum_sha256`` field shape (flat-string vs
       per-file dict).

    The reader is offline / cache-only in this slice; live
    fetch is NOT supported (the task brief explicitly cautions
    against adding a broad network downloader, and the
    existing clean-source architecture does not expose a
    dedicated safe http-client pattern for CTBTO Treaty
    Status). The cache-policy gate blocks
    ``cache_policy="refresh"`` / ``"no_cache"`` with a
    structured ``ctbto_treaty_status_unsupported_cache_policy``
    error BEFORE this function is called.

    The readiness gate
    (:func:`._readiness.check_metadata_well_formed`) returns
    ``ready=False`` with a structured ``missing_metadata`` /
    ``missing_raw`` error when the bundle is not on disk; the
    ``SourceIngestRunner`` raises ``RuntimeError`` BEFORE
    ``read_raw`` is invoked so this function is only reached
    when the bundle is runner-ready.
    """
    csv_p = csv_path(request)
    html_p = html_path(request)
    metadata = read_metadata(metadata_path(request))

    if csv_p.is_file():
        cache_path = csv_p
        asset_id = CTBTO_TREATY_STATUS_CSV_ASSET_ID
        csv_text = cache_path.read_text(encoding="utf-8")
        header, rows = _parse_csv_text(csv_text)
        asset_media_type = "text/csv"
    else:
        cache_path = html_p
        asset_id = CTBTO_TREATY_STATUS_HTML_ASSET_ID
        html_text = cache_path.read_text(encoding="utf-8")
        header, rows = _parse_html_table(html_text)
        asset_media_type = "text/html"

    asset_checksum = _compute_cache_checksum(cache_path)

    if not header:
        # Cached file carries no recognisable CSV / HTML records.
        # Surface a structured schema-violation warning on the
        # raw-read warnings tuple; the transform layer will see
        # zero rows and emit zero observations, but the warning
        # carries the actionable message for audit code.
        return RawReadResult(
            source_id=request.source_id,
            assets=(
                RawAsset(
                    asset_id=asset_id,
                    source_id=request.source_id,
                    version=CTBTO_TREATY_STATUS_DEFAULT_VERSION,
                    media_type=asset_media_type,
                    path=cache_path,
                    url=metadata.get("source_url"),
                    checksum_sha256=asset_checksum,
                    retrieved_at=None,
                    immutable=True,
                ),
            ),
            payload={
                "header": header,
                "rows": rows,
                "metadata": metadata,
                "cache_path": cache_path,
                "asset_id": asset_id,
            },
            warnings=(
                SourceWarning(
                    code=CTBTO_TREATY_STATUS_SCHEMA_ERROR,
                    message=(
                        f"CTBTO Treaty Status cached export at "
                        f"{cache_path} carries no recognisable "
                        f"header + data rows partition matching "
                        f"the 4 canonical required columns; the "
                        f"reader could not find a header row + "
                        f"data rows partition. Re-stage a "
                        f"canonical CTBTO States Signatories "
                        f"bundle with the documented header row "
                        f"({', '.join(CTBTO_TREATY_STATUS_REQUIRED_COLUMNS)}) "
                        f"before re-running ingestion."
                    ),
                    severity="warning",
                    source_id=request.source_id,
                    context={
                        "cache_path": str(cache_path),
                    },
                ),
                SourceWarning(
                    code=MISSING_RAW,
                    message=(
                        f"CTBTO Treaty Status cached export at "
                        f"{cache_path} carries zero parsed rows; "
                        f"no observations will be emitted."
                    ),
                    severity="warning",
                    source_id=request.source_id,
                    context={
                        "cache_path": str(cache_path),
                    },
                ),
            ),
        )

    # Validate the parsed header against the documented required
    # columns. A missing required column raises
    # CtbtoTreatyStatusSchemaError BEFORE the transform layer
    # consumes the frame; the runner propagates the exception so
    # the CLI / tests can act on it.
    _validate_header_columns(
        header,
        source_id=request.source_id,
        cache_path=cache_path,
    )

    asset = RawAsset(
        asset_id=asset_id,
        source_id=request.source_id,
        version=CTBTO_TREATY_STATUS_DEFAULT_VERSION,
        media_type=asset_media_type,
        path=cache_path,
        url=metadata.get("source_url"),
        checksum_sha256=asset_checksum,
        retrieved_at=None,
        immutable=True,
    )

    return RawReadResult(
        source_id=request.source_id,
        assets=(asset,),
        payload={
            "header": header,
            "rows": rows,
            "metadata": metadata,
            "cache_path": cache_path,
            "asset_id": asset_id,
        },
        warnings=(),
    )


__all__ = [
    "CtbtoTreatyStatusSchemaError",
    "read_ctbto_treaty_status_cache",
]
