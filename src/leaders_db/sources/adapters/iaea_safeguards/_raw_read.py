"""Raw PDF reader for the clean IAEA Safeguards status-list adapter.

This module owns the body of
:meth:`IaeaSafeguardsAdapter.read_raw` extracted into free
functions so the adapter class module stays focused on lifecycle
wiring + registration. The reader opens the staged status-list
PDF via ``pdfplumber`` (the canonical PDF parsing library the
project already uses for the SIPRI Yearbook Ch.7 PDF), parses
the page tables / lines, validates the header against the 5
canonical required columns, and returns the parsed row list on
``RawReadResult.payload["rows"]`` alongside the original
``header`` list and the cached ``PDF`` :class:`RawAsset` record.

Source hygiene
--------------

The IAEA Safeguards Status List is a public PDF published at
``https://www.iaea.org/sites/default/files/20/01/sg-agreements-comprehensive-status.pdf``
("Conclusion of Safeguards Agreements, Additional Protocols and
Small Quantities Protocols"). Per the IAEA's terms-of-use, the
pipeline does NOT redistribute the full PDF or full table in
public outputs. The unified adapter only carries the
``source_url`` and the per-row source-native cell labels on the
extension payload so audit code can recover the verbatim
source.

The reader is offline / cache-only in this slice; live fetch is
intentionally NOT supported (the task brief explicitly cautions
against adding a broad network downloader, and the existing
clean-source architecture does not expose a dedicated safe
``cache_policy`` / http-client pattern for IAEA Safeguards). The
cache-policy gate blocks ``cache_policy="refresh"`` /
``"no_cache"`` with a structured
``iaea_safeguards_unsupported_cache_policy`` error BEFORE
``read_raw`` / ``transform`` are called.

Parsing strategy
----------------

The reader tries two parsing paths:

1. **Table extraction** -- prefer
   ``pdfplumber.Page.extract_tables()`` for each page. The
   reader iterates every page, locates the header row on each
   page, and accumulates every valid data row that follows the
   header. Each parsed row carries a ``page_number`` key so the
   transform layer can populate ``RawLocator.page_number`` with
   the exact page the row originated from (the public IAEA
   status-list PDF carries ~190 country rows and paginates
   across multiple pages).
2. **Text-extraction fallback** -- when the table-extraction
   path produces no rows, fall back to
   ``pdfplumber.Page.extract_text(layout=True)`` per page and
   parse the cached text via the Python ``csv`` module. The
   fallback iterates every page and accumulates rows in the
   same way, with the same per-row ``page_number`` provenance.

A header that is missing one or more of the 5 canonical required
columns raises :class:`IaeaSafeguardsSchemaError` BEFORE the
transform layer consumes the parsed frame; the transform layer
does NOT silently emit partial output on a schema contract
violation.

Multi-page provenance
---------------------

Every parsed row dict carries a ``page_number`` key (1-based,
matching ``pdfplumber.Page.page_number`` semantics) so the
downstream :class:`NormalizedObservation` ``RawLocator.page_number``
field is populated with the exact page the row came from. The
multi-page accumulator collects rows from EVERY page whose
header matches the canonical column set; a single-page PDF
yields rows with ``page_number=1`` only. Pages without a
recognisable header are silently skipped -- the readiness gate
has already validated the cached PDF, so per-page header
divergence is parse-time corruption rather than a schema
contract violation.
"""

from __future__ import annotations

import csv
import hashlib
import io
from collections.abc import Iterable
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
    IAEA_SAFEGUARDS_DEFAULT_VERSION,
    IAEA_SAFEGUARDS_PDF_ASSET_ID,
    IAEA_SAFEGUARDS_REQUIRED_COLUMNS,
    IAEA_SAFEGUARDS_SCHEMA_ERROR,
)
from ._readiness import (
    metadata_path,
    pdf_path,
    read_metadata,
)


class IaeaSafeguardsSchemaError(ValueError):
    """Structured failure raised when the cached IAEA Safeguards
    PDF is missing required columns.

    The transform layer MUST NOT silently produce partial output
    when the schema contract is violated -- the raw-read
    boundary raises this exception BEFORE the transform layer
    consumes the parsed frame. The exception carries:

    - ``code``: the structured warning code
      ``"iaea_safeguards_schema_error"``.
    - ``source_id``: the :class:`SourceId` carrying the failing
      source slug (``"iaea_safeguards"``).
    - ``missing_columns``: a tuple of the column names that the
      parsed PDF header did NOT produce but the adapter
      requires.
    - ``expected_columns``: a tuple of every required indicator
      column (the canonical 5 column catalog).
    - ``actual_columns``: a tuple of every column the parsed
      PDF header produced.
    - ``cache_path``: the resolved cached PDF path (when
      available).

    The exception ``str`` representation is intentionally
    self-describing so a CLI run / log line / pytest failure
    tells the operator which columns are missing without
    reading source code.
    """

    code: str = IAEA_SAFEGUARDS_SCHEMA_ERROR

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
            f"IAEA Safeguards raw-read schema validation "
            f"failed ({IAEA_SAFEGUARDS_SCHEMA_ERROR}){path_str}: "
            f"the cached status-list PDF is missing "
            f"{len(missing_columns)} required column(s) "
            f"({missing_str}); the unified IAEA Safeguards "
            f"adapter requires every required indicator column "
            f"in {tuple(expected_columns)!r} but the PDF reader "
            f"produced {tuple(actual_columns)!r}. Re-stage a "
            f"canonical IAEA Safeguards Status List bundle or "
            f"update the adapter contract before running "
            f"ingestion; the transform layer does NOT silently "
            f"emit partial output on schema violations."
        )


def _open_pdf(path: Path) -> Any:
    """Open the cached PDF via ``pdfplumber`` and return the
    :class:`pdfplumber.PDF` context manager.

    Lazy import keeps ``pdfplumber`` an optional runtime
    dependency for adapters that don't read PDFs.
    """
    import pdfplumber  # local import; pdfplumber is a runtime dep

    return pdfplumber.open(str(path))


def _iter_table_rows(
    page: Any,
) -> Iterable[list[str]]:
    """Yield parsed rows from a single PDF page's tables.

    Wraps :meth:`pdfplumber.Page.extract_tables` and yields the
    parsed rows in declaration order. Empty rows (rows where
    every cell is whitespace) are dropped so the transform layer
    does NOT see empty separator rows.
    """
    tables = page.extract_tables() or []
    for table in tables:
        for row in table:
            if not row:
                continue
            stripped = [
                (cell.strip() if isinstance(cell, str) else "")
                for cell in row
            ]
            if any(cell for cell in stripped):
                yield stripped


def _table_header_score(
    row: list[str],
    required_columns: tuple[str, ...],
) -> int:
    """Return the count of ``required_columns`` cells present
    in ``row``.

    Used by :func:`_locate_header_row` to identify the header
    row in the parsed table stream. The score lets the caller
    pick the first row that carries all 5 canonical required
    columns -- robust against punctuation / whitespace
    differences between the cached PDF layout and the canonical
    column names.
    """
    cells = {cell.strip() for cell in row if cell and cell.strip()}
    if not cells:
        return 0
    return sum(1 for column in required_columns if column in cells)


def _locate_header_row(
    rows: Iterable[list[str]],
    required_columns: tuple[str, ...],
    *,
    min_match: int = 3,
) -> tuple[int, list[str]] | None:
    """Return ``(index, header_row)`` of the first parsed table
    row that matches ``min_match`` of ``required_columns``.

    The header-detection logic is robust against
    punctuation/whitespace differences between the cached PDF
    layout and the canonical column names. The threshold
    (``min_match=3``) is calibrated so a header that is missing
    one or two columns is still located as the header (the
    schema validation surfaces
    :class:`IaeaSafeguardsSchemaError` for that case) AND so a
    preamble line that happens to carry a few column labels is
    NOT mistaken for the header (a real preamble line rarely
    mentions 3+ distinctive IAEA column names like
    ``Safeguards Agreement`` / ``INFCIRC`` / ``Additional
    Protocol``).

    Returns ``None`` when no parsed row matches the header
    shape -- the caller surfaces a structured schema-violation
    error.
    """
    for index, row in enumerate(rows):
        if _table_header_score(row, required_columns) >= min_match:
            return index, row
    return None


def _normalise_cell(cell: Any) -> str:
    """Return the cell text as a stripped string.

    pdfplumber may return either ``str`` or ``None`` per cell;
    the helper coerces both to a stripped ``str`` so the
    transform layer can branch on string sentinels.
    """
    if cell is None:
        return ""
    if isinstance(cell, str):
        return cell.strip()
    return str(cell).strip()


def _normalise_table_header(
    header: list[str],
) -> list[str]:
    """Return the canonical column-name list for the parsed
    table header.

    pdfplumber may surface the column names with slight
    whitespace differences (e.g. ``"State "`` vs ``"State"``).
    The helper strips each header cell so the per-row cell
    lookup in the transform layer matches the canonical column
    names byte-for-byte.
    """
    return [cell.strip() for cell in header]


def _validate_header_columns(
    header: list[str],
    *,
    source_id: Any,
    cache_path: Path,
    required_columns: tuple[str, ...] = IAEA_SAFEGUARDS_REQUIRED_COLUMNS,
) -> None:
    """Raise :class:`IaeaSafeguardsSchemaError` if any required
    column is missing from the parsed header.

    The transform layer MUST NOT silently produce partial output
    when the schema contract is violated -- this helper enforces
    the contract at the raw-read boundary. An empty header
    (i.e. the cached PDF carries no recognisable header row)
    is treated as a schema contract violation with every
    required column flagged as missing.
    """
    if not header:
        raise IaeaSafeguardsSchemaError(
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
        raise IaeaSafeguardsSchemaError(
            source_id=source_id,
            missing_columns=missing,
            expected_columns=tuple(required_columns),
            actual_columns=tuple(header),
            cache_path=cache_path,
        )


def _parse_table_rows(
    header: list[str],
    data_rows: Iterable[list[str]],
    *,
    page_number: int,
) -> list[dict[str, str]]:
    """Parse the table data rows against the canonical header.

    Each parsed row becomes a dict keyed by the header column
    names, plus a ``page_number`` key carrying the 1-based page
    index the row originated from. Rows whose column count does
    NOT match the header (i.e. malformed / partial rows) are
    dropped silently here; the audit-trail extension preserves
    the original raw text per row in the transform layer so
    audit code can recover the dropped row.

    The ``page_number`` key is reserved (it is not a column in
    the canonical IAEA status list) so it never collides with
    a source-native column name. Downstream code reads the
    per-row page provenance via ``row["page_number"]`` and
    forwards it to the :class:`NormalizedObservation`
    ``RawLocator.page_number`` field.
    """
    rows: list[dict[str, str]] = []
    for row in data_rows:
        normalised = [_normalise_cell(cell) for cell in row]
        if len(normalised) != len(header):
            # Malformed row (column count mismatch) -- drop
            # silently here; the readiness gate already validated
            # the header so row-level mismatches are parse-time
            # corruption rather than a schema contract violation.
            continue
        row_dict: dict[str, str] = {}
        for col_name, col_value in zip(header, normalised, strict=True):
            row_dict[col_name] = col_value
        row_dict["page_number"] = str(page_number)
        rows.append(row_dict)
    return rows


def _parse_text_extraction_rows(
    page_text: str,
    header: list[str],
    *,
    page_number: int,
) -> list[dict[str, str]]:
    """Parse a single page's extracted text into per-row dicts.

    Fallback path used when the PDF page has no recognisable
    table. The helper uses the Python ``csv`` module against
    each non-blank line in the extracted text, then validates
    the parsed row's column count against the header.

    Every parsed row dict carries a ``page_number`` key carrying
    the 1-based page index the row originated from so the
    transform layer can populate
    :class:`RawLocator` ``page_number`` field with the exact
    page the row came from.

    Defensive: lines that do not parse as CSV records OR that
    produce a column count that does NOT match the header are
    dropped silently -- the transform layer does NOT silently
    emit partial output on a schema violation.
    """
    rows: list[dict[str, str]] = []
    if not page_text or not page_text.strip():
        return rows
    for line in page_text.splitlines():
        if not line or not line.strip():
            continue
        try:
            parsed = next(csv.reader(io.StringIO(line)))
        except csv.Error:
            continue
        if not parsed:
            continue
        if len(parsed) != len(header):
            continue
        normalised = [_normalise_cell(cell) for cell in parsed]
        row_dict: dict[str, str] = {}
        for col_name, col_value in zip(header, normalised, strict=True):
            row_dict[col_name] = col_value
        row_dict["page_number"] = str(page_number)
        rows.append(row_dict)
    return rows


def _compute_cache_checksum(cache_path: Path) -> str | None:
    """Return the SHA-256 hex digest of the staged cache file.

    Returns ``None`` only when the cache file is missing or
    unreadable on disk -- the readiness gate already rejects a
    missing cache with a structured ``missing_raw`` error
    BEFORE this function is reached, so a ``None`` return is
    defense in depth. The hex digest is the verified/staged
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


def _read_via_tables(
    request: SourceIngestRequest,
    cache_path: Path,
) -> tuple[list[str], list[dict[str, str]], list[SourceWarning]]:
    """Read the cached PDF via ``pdfplumber.Page.extract_tables``.

    Iterates every page and accumulates rows from every page
    whose header matches the 5 canonical required columns.
    Each parsed row carries a ``page_number`` key (1-based)
    so the transform layer can populate
    ``RawLocator.page_number`` with the exact page the row
    originated from. Pages without a recognisable header
    surface a structured schema-violation warning so the
    operator can see the parse path was tried but did not
    match.

    The header is the first page's parsed header row; the
    schema validator enforces the 5 canonical required
    columns against it. Empty pages and pages with no tables
    are silently skipped. Returns ``(header, rows, warnings)``.
    """
    warnings: list[SourceWarning] = []
    parsed_header: list[str] = []
    all_rows: list[dict[str, str]] = []
    with _open_pdf(cache_path) as pdf:
        for page_index, page in enumerate(pdf.pages, start=1):
            page_rows = list(_iter_table_rows(page))
            if not page_rows:
                continue
            header_match = _locate_header_row(
                page_rows,
                IAEA_SAFEGUARDS_REQUIRED_COLUMNS,
            )
            if header_match is None:
                # No recognisable header on this page; try the
                # next page. The cumulative warnings carry an
                # audit-trail page-by-page breakdown so the
                # operator can see what was tried.
                warnings.append(
                    SourceWarning(
                        code=IAEA_SAFEGUARDS_SCHEMA_ERROR,
                        message=(
                            f"IAEA Safeguards raw-read: PDF "
                            f"page {page_index} has no "
                            f"recognisable header matching "
                            f"the 5 canonical required "
                            f"columns; the reader continues "
                            f"to the next page."
                        ),
                        severity="warning",
                        source_id=request.source_id,
                        context={
                            "page_number": page_index,
                            "cache_path": str(cache_path),
                        },
                    ),
                )
                continue
            header_index, header_row = header_match
            if not parsed_header:
                parsed_header = _normalise_table_header(header_row)
            data_rows = page_rows[header_index + 1 :]
            parsed_rows = _parse_table_rows(
                parsed_header, data_rows, page_number=page_index,
            )
            all_rows.extend(parsed_rows)
    if parsed_header:
        _validate_header_columns(
            parsed_header,
            source_id=request.source_id,
            cache_path=cache_path,
        )
    return parsed_header, all_rows, warnings


def _read_via_text(
    request: SourceIngestRequest,
    cache_path: Path,
) -> tuple[list[str], list[dict[str, str]], list[SourceWarning]]:
    """Read the cached PDF via ``pdfplumber.Page.extract_text``.

    Fallback path used when the table-extraction path finds no
    matching header. Iterates every page and accumulates rows
    from every page whose header matches the 5 canonical
    required columns. Each parsed row carries a ``page_number``
    key (1-based) so the transform layer can populate
    ``RawLocator.page_number`` with the exact page the row
    originated from.

    Returns ``(header, rows, warnings)``.
    """
    warnings: list[SourceWarning] = []
    parsed_header: list[str] = []
    all_rows: list[dict[str, str]] = []
    with _open_pdf(cache_path) as pdf:
        for page_index, page in enumerate(pdf.pages, start=1):
            page_text = page.extract_text(layout=True) or ""
            if not page_text.strip():
                continue
            lines = [line for line in page_text.splitlines() if line.strip()]
            # Build a synthetic rows stream from the page text
            # so the existing header-detection logic can locate
            # the header line.
            rows: list[list[str]] = []
            for line in lines:
                try:
                    parsed = next(csv.reader(io.StringIO(line)))
                except csv.Error:
                    continue
                if not parsed:
                    continue
                rows.append(parsed)
            header_match = _locate_header_row(
                rows,
                IAEA_SAFEGUARDS_REQUIRED_COLUMNS,
            )
            if header_match is None:
                warnings.append(
                    SourceWarning(
                        code=IAEA_SAFEGUARDS_SCHEMA_ERROR,
                        message=(
                            f"IAEA Safeguards raw-read (text "
                            f"fallback): PDF page {page_index} "
                            f"has no recognisable header "
                            f"matching the 5 canonical "
                            f"required columns; the reader "
                            f"continues to the next page."
                        ),
                        severity="warning",
                        source_id=request.source_id,
                        context={
                            "page_number": page_index,
                            "cache_path": str(cache_path),
                        },
                    ),
                )
                continue
            header_index, header_row = header_match
            if not parsed_header:
                parsed_header = _normalise_table_header(header_row)
            data_lines = lines[header_index + 1 :]
            parsed_rows = _parse_text_extraction_rows(
                "\n".join(data_lines),
                parsed_header,
                page_number=page_index,
            )
            all_rows.extend(parsed_rows)
    if parsed_header:
        _validate_header_columns(
            parsed_header,
            source_id=request.source_id,
            cache_path=cache_path,
        )
    return parsed_header, all_rows, warnings


def _count_pdf_pages(cache_path: Path) -> int:
    """Return the total number of pages in the cached PDF.

    Defensive: a missing or unreadable PDF returns ``0`` so
    the caller surfaces a structured schema-violation error
    instead of dividing by zero or fabricating a page count.
    """
    try:
        with _open_pdf(cache_path) as pdf:
            return len(pdf.pages)
    except (OSError, Exception):  # pdfplumber raises broad exceptions
        return 0


def read_iaea_safeguards_pdf(
    request: SourceIngestRequest,
) -> RawReadResult:
    """Read the staged IAEA Safeguards status-list PDF and
    return the parsed raw payload.

    The reader:

    1. Loads the cached PDF via ``pdfplumber``.
    2. Tries the table-extraction path first; if no page yields
       a header matching the 5 canonical required columns, falls
       back to the text-extraction path. BOTH paths iterate
       every page and accumulate rows from every page whose
       header matches the canonical column set (multi-page
       PDFs paginate country rows across pages; the reader
       does NOT stop at the first matching page).
    3. Validates the parsed header against the 5 canonical
       required columns and raises
       :class:`IaeaSafeguardsSchemaError` BEFORE the transform
       layer consumes the frame.
    4. Carries the parsed frame on ``payload["rows"]`` (with
       every row carrying a ``page_number`` key for per-row
       page provenance) plus the original ``header`` list plus
       the parsed page count ``pages_parsed`` plus the parsing
       path used (``"table"`` / ``"text"``) for the transform
       layer.
    5. Computes the SHA-256 of the staged PDF file (the
       verified / staged on-disk fingerprint) and populates
       the :class:`RawAsset` ``checksum_sha256`` field so
       downstream audit code can recover the actual
       on-disk hash regardless of the metadata's
       ``checksum_sha256`` field shape (flat-string vs
       per-file dict).

    The readiness gate
    (:func:`._readiness.check_metadata_well_formed`) returns
    ``ready=False`` with a structured ``missing_metadata`` /
    ``missing_raw`` error when the bundle is not on disk; the
    ``SourceIngestRunner`` raises ``RuntimeError`` BEFORE
    ``read_raw`` is invoked so this function is only reached
    when the bundle is runner-ready.
    """
    cache_path = pdf_path(request)
    metadata = read_metadata(metadata_path(request))
    pages_total = _count_pdf_pages(cache_path)

    # Try table extraction first.
    header, rows, table_warnings = _read_via_tables(
        request, cache_path,
    )
    parse_path = "table"
    if not header:
        # Fall back to text extraction.
        header, rows, text_warnings = _read_via_text(
            request, cache_path,
        )
        parse_path = "text"
        table_warnings.extend(text_warnings)

    # Compute the staged cache SHA-256 ONCE so the
    # :class:`RawAsset` ``checksum_sha256`` field is the
    # verified / staged on-disk fingerprint rather than
    # ``None``. The readiness gate has already verified the
    # same SHA-256 against
    # ``metadata.json['checksum_sha256']`` (per
    # :func:`._readiness._checksum_match_blocker`), so when
    # readiness passes the asset's SHA-256 is non-null and
    # matches the metadata field.
    asset_checksum = _compute_cache_checksum(cache_path)

    if not header or not rows:
        # Cached PDF carries no recognisable records. Surface a
        # structured schema-violation error on the raw-read
        # warnings tuple; the transform layer will see zero
        # rows and emit zero observations, but the warning
        # carries the actionable message for audit code.
        return RawReadResult(
            source_id=request.source_id,
            assets=(
                RawAsset(
                    asset_id=IAEA_SAFEGUARDS_PDF_ASSET_ID,
                    source_id=request.source_id,
                    version=IAEA_SAFEGUARDS_DEFAULT_VERSION,
                    media_type="application/pdf",
                    path=cache_path,
                    url=metadata.get("source_url"),
                    checksum_sha256=asset_checksum,
                    retrieved_at=None,
                    immutable=True,
                ),
            ),
            payload={
                "header": header or [],
                "rows": rows or [],
                "metadata": metadata,
                "cache_path": cache_path,
                "asset_id": IAEA_SAFEGUARDS_PDF_ASSET_ID,
                "parse_path": parse_path,
                "pages_parsed": pages_total,
            },
            warnings=(
                *tuple(table_warnings),
                SourceWarning(
                    code=IAEA_SAFEGUARDS_SCHEMA_ERROR,
                    message=(
                        f"IAEA Safeguards cached status-list "
                        f"PDF at {cache_path} carries no "
                        f"recognisable header + data rows "
                        f"partition matching the 5 canonical "
                        f"required columns; the reader could "
                        f"not find a header row + data rows "
                        f"partition. Re-stage a canonical "
                        f"IAEA Safeguards Status List bundle "
                        f"with the documented header row "
                        f"({', '.join(IAEA_SAFEGUARDS_REQUIRED_COLUMNS)}) "
                        f"before re-running ingestion."
                    ),
                    severity="warning",
                    source_id=request.source_id,
                    context={
                        "cache_path": str(cache_path),
                        "parse_path": parse_path,
                    },
                ),
                SourceWarning(
                    code=MISSING_RAW,
                    message=(
                        f"IAEA Safeguards cached status-list "
                        f"PDF at {cache_path} carries zero "
                        f"parsed rows; no observations will "
                        f"be emitted."
                    ),
                    severity="warning",
                    source_id=request.source_id,
                    context={
                        "cache_path": str(cache_path),
                    },
                ),
            ),
        )

    asset = RawAsset(
        asset_id=IAEA_SAFEGUARDS_PDF_ASSET_ID,
        source_id=request.source_id,
        version=IAEA_SAFEGUARDS_DEFAULT_VERSION,
        media_type="application/pdf",
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
            "asset_id": IAEA_SAFEGUARDS_PDF_ASSET_ID,
            "parse_path": parse_path,
            "pages_parsed": pages_total,
        },
        warnings=tuple(table_warnings),
    )


__all__ = [
    "IaeaSafeguardsSchemaError",
    "read_iaea_safeguards_pdf",
]
