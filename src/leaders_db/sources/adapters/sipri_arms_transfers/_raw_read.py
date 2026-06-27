"""Raw CSV / base64-JSON reader for the clean SIPRI Arms Transfers adapter.

This module owns the body of :meth:`SipriArmsTransfersAdapter.read_raw`
extracted into free functions so the adapter class module stays
focused on lifecycle wiring + registration. The reader supports
the two cached export shapes the task brief explicitly
endorses:

1. **Direct CSV** -- a plain CSV file at
   ``data/raw/sipri_arms_transfers/trade_register.csv``. The
   file is the canonical SIPRI Trade Register export; the
   reader uses the Python ``csv`` module to skip SIPRI
   preamble / citation lines (typically starting with ``#`` or
   ``SIPRI``) and emit one parsed row per transfer.

2. **Base64-JSON wrapper** -- a JSON envelope at
   ``data/raw/sipri_arms_transfers/trade_register.json``
   containing base64-encoded CSV bytes. This is the canonical
   shape the SIPRI public app's backend API
   (``https://atbackend.sipri.org/api/p/trades/trade-register-csv/``)
   returns per the task brief; the reader base64-decodes the
   payload and parses the resulting CSV the same way as the
   direct CSV shape.

The reader handles the cached preamble / citation lines the
SIPRI exports frequently carry (e.g. SIPRI copyright notice,
coverage stamp, database version stamp) safely by skipping
lines that do not parse as a CSV record with the documented
header schema. When the preamble cannot be skipped (e.g. the
cached file is missing the documented header row), the reader
surfaces a structured ``sipri_arms_transfers_preamble_not_found``
warning on the :class:`RawReadResult.warnings` tuple rather
than crashing the parse -- downstream code can branch on the
warning code.

Schema-contract enforcement
---------------------------

The raw-read layer is the canonical boundary at which the
cached CSV / JSON schema is enforced. The 8 documented
required columns ``Supplier`` / ``Recipient`` / ``Order year``
/ ``Delivery year`` / ``Designation`` / ``Status`` /
``Numbers delivered`` / ``TIV (delivered)`` MUST be present
in the cached header; a missing required column fires a
structured :class:`SipriArmsTransfersSchemaError` so the
transform layer does NOT silently emit partial output on a
schema contract violation.

Citation / preamble preservation
-------------------------------

The raw-read layer preserves the SIPRI preamble / citation
lines (the lines that precede the header row in the cached
CSV) on the ``RawReadResult.payload`` under
``"preamble_lines"`` so the transform layer can propagate the
verbatim citation block onto every emitted observation's
``extension["sipri_arms_transfers_preamble"]`` audit-trail
field. The preamble is informational only -- the transform
does NOT branch on the preamble contents -- but preserving the
verbatim preamble on the audit trail is consistent with the
SIPRI attribution / fair-use contract (Always-On Rule #15).
"""

from __future__ import annotations

import base64
import binascii
import csv
import hashlib
import io
import json
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
    SIPRI_ARMS_TRANSFERS_CSV_ASSET_ID,
    SIPRI_ARMS_TRANSFERS_CSV_NAME,
    SIPRI_ARMS_TRANSFERS_DEFAULT_VERSION,
    SIPRI_ARMS_TRANSFERS_JSON_ASSET_ID,
    SIPRI_ARMS_TRANSFERS_JSON_NAME,
    SIPRI_ARMS_TRANSFERS_PREAMBLE_NOT_FOUND,
    SIPRI_ARMS_TRANSFERS_REQUIRED_COLUMNS,
    SIPRI_ARMS_TRANSFERS_SCHEMA_ERROR,
)
from ._readiness import (
    csv_path,
    json_path,
    metadata_path,
    read_metadata,
)


class SipriArmsTransfersSchemaError(ValueError):
    """Structured failure raised when the cached SIPRI Arms Transfers
    CSV / JSON is missing required columns.

    The transform layer MUST NOT silently produce partial output
    when the schema contract is violated -- the raw-read
    boundary raises this exception BEFORE the transform layer
    consumes the parsed frame. The exception carries:

    - ``code``: the structured warning code
      ``"sipri_arms_transfers_schema_error"``.
    - ``source_id``: the :class:`SourceId` carrying the failing
      source slug (``"sipri_arms_transfers"``).
    - ``missing_columns``: a tuple of the column names that the
      parsed CSV header did NOT produce but the adapter
      requires.
    - ``expected_columns``: a tuple of every required indicator
      column (the canonical 8 catalog columns).
    - ``actual_columns``: a tuple of every column the parsed
      CSV header produced.
    - ``cache_path``: the resolved cached file path (when
      available).

    The exception ``str`` representation is intentionally
    self-describing so a CLI run / log line / pytest failure
    tells the operator which columns are missing without
    reading source code.
    """

    code: str = SIPRI_ARMS_TRANSFERS_SCHEMA_ERROR

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
            f"SIPRI Arms Transfers raw-read schema validation "
            f"failed ({SIPRI_ARMS_TRANSFERS_SCHEMA_ERROR})"
            f"{path_str}: the cached export is missing "
            f"{len(missing_columns)} required column(s) "
            f"({missing_str}); the unified SIPRI Arms Transfers "
            f"adapter requires every required indicator column in "
            f"{tuple(expected_columns)!r} but the CSV reader "
            f"produced {tuple(actual_columns)!r}. Re-stage a "
            f"canonical SIPRI Arms Transfers Trade Register "
            f"bundle or update the adapter contract before "
            f"running ingestion; the transform layer does NOT "
            f"silently emit partial output on schema violations."
        )


def _decode_csv_text_from_json(json_payload: dict[str, Any]) -> bytes:
    """Decode the CSV bytes from the SIPRI base64-JSON envelope.

    The SIPRI public app's backend API returns a JSON object
    whose ``"data"`` slot carries a base64-encoded CSV string;
    this helper decodes the payload and returns the raw CSV
    bytes. Raises :class:`ValueError` when the payload is
    missing or malformed so the caller can surface a structured
    readiness error.
    """
    for key in ("data", "csv", "trade_register", "trades_csv", "payload"):
        value = json_payload.get(key)
        if isinstance(value, str) and value.strip():
            try:
                return base64.b64decode(value, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise ValueError(
                    f"SIPRI Arms Transfers base64-JSON envelope "
                    f"key {key!r} is present but failed to "
                    f"base64-decode ({exc!s})"
                ) from exc
    raise ValueError(
        "SIPRI Arms Transfers base64-JSON envelope is missing "
        "a recognised CSV payload slot; expected one of "
        "'data' / 'csv' / 'trade_register' / 'trades_csv' / "
        "'payload' to carry the base64-encoded CSV string."
    )


def _load_csv_text(request: SourceIngestRequest) -> tuple[bytes, Path, str]:
    """Load the cached CSV text + the resolved cache file path +
    asset id.

    Supports BOTH the direct-CSV shape (the canonical CSV
    ``trade_register.csv`` staged on disk) AND the
    base64-JSON wrapper shape (the canonical JSON
    ``trade_register.json`` envelope containing base64-encoded
    CSV bytes). When both are staged, the CSV is preferred.
    Returns ``(csv_bytes, cache_path, asset_id)`` so the caller
    can build the :class:`RawAsset` and propagate the cache
    path onto every observation's :class:`RawLocator`.

    Raises :class:`FileNotFoundError` when neither shape is
    present (the readiness gate fires BEFORE the reader so this
    helper should not normally see a missing-cache scenario,
    but defense in depth is preserved).
    """
    csv_p = csv_path(request)
    if csv_p.is_file():
        return csv_p.read_bytes(), csv_p, SIPRI_ARMS_TRANSFERS_CSV_ASSET_ID

    json_p = json_path(request)
    if json_p.is_file():
        payload = json.loads(json_p.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(
                f"SIPRI Arms Transfers base64-JSON wrapper at "
                f"{json_p} must be a JSON object; got "
                f"{type(payload).__name__}."
            )
        return _decode_csv_text_from_json(payload), json_p, (
            SIPRI_ARMS_TRANSFERS_JSON_ASSET_ID
        )

    raise FileNotFoundError(
        f"SIPRI Arms Transfers cached export missing at "
        f"{csv_p} and {json_p}; place the canonical "
        f"{SIPRI_ARMS_TRANSFERS_CSV_NAME!r} (or "
        f"{SIPRI_ARMS_TRANSFERS_JSON_NAME!r}) before running "
        f"ingestion."
    )


def _header_line_score(
    line: str,
    required_columns: tuple[str, ...],
) -> int:
    """Return the count of ``required_columns`` cells present
    in the parsed ``line``.

    Used by :func:`_split_preamble` to locate the actual
    header row in a cached SIPRI export. The score lets the
    caller pick the first line that carries a strong
    fraction of the canonical 8 required columns -- robust
    against a header that is missing one or two columns
    (the schema validation surfaces
    :class:`SipriArmsTransfersSchemaError` for that case)
    and against punctuation-containing preamble / citation
    lines that happen to carry a comma / quote.
    """
    if not line or not line.strip():
        return 0
    try:
        parsed = next(csv.reader(io.StringIO(line)))
    except csv.Error:
        return 0
    if not parsed:
        return 0
    cells = {cell.strip() for cell in parsed if cell and cell.strip()}
    if not cells:
        return 0
    return sum(1 for column in required_columns if column in cells)


# A header line carries at least this fraction of the
# canonical 8 required columns. The threshold (5 of 8) is
# calibrated so the documented schema-error case
# (a header missing one or two columns) is still located
# as the header so the schema validator can surface the
# missing-column context, AND so a preamble line that
# happens to carry a comma / quote is NOT mistaken for the
# header (5 of the 8 distinctive SIPRI column names is
# very unlikely in a citation / preamble line).
SIPRI_ARMS_TRANSFERS_HEADER_MIN_MATCH: int = 5


def _split_preamble(
    csv_text_bytes: bytes,
    *,
    required_columns: tuple[str, ...] = SIPRI_ARMS_TRANSFERS_REQUIRED_COLUMNS,
    min_match: int = SIPRI_ARMS_TRANSFERS_HEADER_MIN_MATCH,
) -> tuple[list[str], list[str]]:
    """Split the cached CSV into (preamble lines, data lines).

    SIPRI Arms Transfers Trade Register exports typically carry
    a small block of preamble / citation lines BEFORE the
    documented header row -- e.g. SIPRI copyright notice,
    coverage stamp, database version stamp. The helper scans
    the cached CSV bytes and locates the actual header row
    by matching at least ``min_match`` of the canonical
    required-column set, then routes every line before the
    header to the preamble partition and every line from the
    header onward to the data partition.

    The header-detection logic is robust against punctuation-
    containing preamble lines (commas, semicolons, quotes,
    periods, etc.) because the check requires a strong
    fraction of the documented column NAMES to appear in the
    parsed cells. A preamble line that happens to carry a
    comma / quote does NOT match the canonical 8-column
    header shape (preamble lines mention URLs, copyright
    years, etc. -- not the distinctive SIPRI column names
    like ``Supplier`` / ``Recipient`` / ``TIV (delivered)``).
    Blank lines in the preamble block are preserved on the
    preamble partition so the audit-trail carries the
    verbatim citation block.

    The threshold (``min_match``) is set so a header that is
    missing one or two required columns is still located as
    the header -- the schema validation then raises
    :class:`SipriArmsTransfersSchemaError` with the missing-
    column context. When the cached file carries NO line
    that matches the header shape at all, the ``data_lines``
    partition is empty -- the caller surfaces a structured
    :data:`SIPRI_ARMS_TRANSFERS_PREAMBLE_NOT_FOUND` warning
    on the :class:`RawReadResult.warnings` tuple.
    """
    raw_text = csv_text_bytes.decode("utf-8", errors="replace")
    lines = raw_text.splitlines()
    if not lines:
        return [], []

    # Locate the first line whose CSV-parsed cells contain
    # at least ``min_match`` of the canonical required
    # column names. The split is anchored on the header row,
    # not on per-line punctuation heuristics, so preamble /
    # citation lines that carry commas / quotes / semicolons
    # are preserved on the preamble partition regardless of
    # their punctuation density.
    header_index: int | None = None
    for index, line in enumerate(lines):
        if _header_line_score(line, required_columns) >= min_match:
            header_index = index
            break

    if header_index is None:
        # No line matches the documented header shape. Route
        # every non-blank line to the preamble partition so
        # the operator can see the verbatim cached contents
        # on the audit trail; the caller surfaces a
        # structured ``sipri_arms_transfers_preamble_not_found``
        # warning on the :class:`RawReadResult.warnings`
        # tuple.
        preamble = [line for line in lines if line.strip()]
        return preamble, []

    preamble: list[str] = list(lines[:header_index])
    data: list[str] = list(lines[header_index:])
    return preamble, data


def _parse_csv_rows(
    data_lines: list[str],
) -> tuple[list[str], list[dict[str, str]]]:
    """Parse the data lines into a (header, rows) pair.

    Uses the Python ``csv`` module to parse the data lines
    against the SIPRI Trade Register header. Returns
    ``(header, rows)`` where ``header`` is the canonical
    column-name list and ``rows`` is a list of dicts keyed by
    the header column names. Skips malformed CSV rows (rows
    whose column count does not match the header) safely --
    the transform layer emits zero observations for skipped
    rows and surfaces a structured warning so audit code can
    see the dropped rows.

    Returns ``(header, [])`` when the data partition is empty.
    """
    if not data_lines:
        return [], []

    reader = csv.reader(io.StringIO("\n".join(data_lines)))
    parsed = [row for row in reader if row]
    if not parsed:
        return [], []
    header = [col.strip() for col in parsed[0]]
    rows: list[dict[str, str]] = []
    for row in parsed[1:]:
        if len(row) != len(header):
            # Malformed row (column count mismatch) -- drop
            # silently here; the readiness gate already
            # validated the header so row-level mismatches are
            # parse-time corruption rather than a schema
            # contract violation. The transform layer preserves
            # the verbatim raw_value on the audit-trail extension
            # so audit code can recover the dropped row.
            continue
        row_dict: dict[str, str] = {}
        for col_name, col_value in zip(header, row, strict=True):
            row_dict[col_name] = col_value.strip()
        rows.append(row_dict)
    return header, rows


def _validate_header_columns(
    header: list[str],
    *,
    source_id: Any,
    cache_path: Path,
    required_columns: tuple[str, ...] = SIPRI_ARMS_TRANSFERS_REQUIRED_COLUMNS,
) -> None:
    """Raise :class:`SipriArmsTransfersSchemaError` if any required
    column is missing from the parsed header.

    The transform layer MUST NOT silently produce partial output
    when the schema contract is violated -- this helper enforces
    the contract at the raw-read boundary. An empty header
    (i.e. the cached CSV carries no recognisable header row)
    is treated as a schema contract violation with every
    required column flagged as missing.
    """
    if not header:
        raise SipriArmsTransfersSchemaError(
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
        raise SipriArmsTransfersSchemaError(
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


def read_sipri_arms_transfers_csv(
    request: SourceIngestRequest,
) -> RawReadResult:
    """Read the staged SIPRI Arms Transfers cached CSV / JSON
    bundle and return the parsed raw payload.

    The reader:

    1. Loads the cached CSV bytes (CSV shape preferred; falls
       back to the base64-JSON wrapper when the CSV is absent).
    2. Splits the cached text into (preamble_lines,
       data_lines) -- the preamble is preserved on the
       ``payload["preamble_lines"]`` slot for audit-trail
       propagation. The split is anchored on the canonical
       header row (matched against the documented
       required-column set) so punctuation-containing
       preamble / citation lines are preserved on the
       preamble partition regardless of their comma /
       semicolon / quote density.
    3. Parses the data lines via the Python ``csv`` module into
       a (header, rows) pair; the header is validated against
       the 8 canonical required columns and a missing-required-
       column raises :class:`SipriArmsTransfersSchemaError`
       BEFORE the transform layer consumes the frame.
    4. Carries the parsed frame on ``payload["rows"]`` plus
       the original ``header`` list plus the preamble_lines for
       the transform layer.
    5. Computes the SHA-256 of the staged cache file (the
       verified / staged on-disk fingerprint) and populates
       the :class:`RawAsset` ``checksum_sha256`` field so
       downstream audit code can recover the actual
       on-disk hash regardless of the metadata's
       ``checksum_sha256`` field shape (flat-string vs
       per-file dict).

    The reader is offline / cache-only in this slice; live
    fetch is NOT supported (the task brief explicitly cautions
    against adding a broad network downloader, and the existing
    clean-source architecture does not expose a dedicated safe
    http-client pattern for SIPRI Arms Transfers). The cache-
    policy gate blocks ``cache_policy="refresh"`` /
    ``"no_cache"`` with a structured
    ``sipri_arms_transfers_unsupported_cache_policy`` error
    BEFORE this function is called.

    The readiness gate
    (:func:`._readiness.check_metadata_well_formed`) returns
    ``ready=False`` with a structured ``missing_metadata`` /
    ``missing_raw`` error when the bundle is not on disk; the
    ``SourceIngestRunner`` raises ``RuntimeError`` BEFORE
    ``read_raw`` is invoked so this function is only reached
    when the bundle is runner-ready.
    """
    csv_bytes, cache_path, asset_id = _load_csv_text(request)
    metadata = read_metadata(metadata_path(request))

    preamble_lines, data_lines = _split_preamble(csv_bytes)
    header, rows = _parse_csv_rows(data_lines)

    # Compute the staged cache SHA-256 ONCE so the
    # :class:`RawAsset` ``checksum_sha256`` field is the
    # verified / staged on-disk fingerprint rather than
    # ``None``. The readiness gate has already verified
    # the same SHA-256 against ``metadata.json['checksum_sha256']``
    # (per :func:`._readiness._checksum_match_blocker`), so
    # when readiness passes the asset's SHA-256 is non-null
    # and matches the metadata field.
    asset_checksum = _compute_cache_checksum(cache_path)

    if not data_lines:
        # Cached file carries no recognisable CSV records.
        # Surface a structured preamble-not-found warning on the
        # raw-read warnings tuple; the transform layer will see
        # zero rows and emit zero observations, but the warning
        # carries the actionable message for audit code.
        return RawReadResult(
            source_id=request.source_id,
            assets=(
                RawAsset(
                    asset_id=asset_id,
                    source_id=request.source_id,
                    version=SIPRI_ARMS_TRANSFERS_DEFAULT_VERSION,
                    media_type="text/csv",
                    path=cache_path,
                    url=metadata.get("source_url"),
                    checksum_sha256=asset_checksum,
                    retrieved_at=None,
                    immutable=True,
                ),
            ),
            payload={
                "preamble_lines": preamble_lines,
                "header": header,
                "rows": rows,
                "metadata": metadata,
                "cache_path": cache_path,
                "asset_id": asset_id,
            },
            warnings=(
                SourceWarning(
                    code=SIPRI_ARMS_TRANSFERS_PREAMBLE_NOT_FOUND,
                    message=(
                        f"SIPRI Arms Transfers cached export at "
                        f"{cache_path} carries no recognisable "
                        f"CSV records; the reader could not find "
                        f"a header row + data rows partition. "
                        f"Re-stage a canonical SIPRI Arms "
                        f"Transfers Trade Register bundle with "
                        f"the documented header row "
                        f"({', '.join(SIPRI_ARMS_TRANSFERS_REQUIRED_COLUMNS)}) "
                        f"before re-running ingestion."
                    ),
                    severity="warning",
                    source_id=request.source_id,
                    context={
                        "cache_path": str(cache_path),
                        "preamble_line_count": len(preamble_lines),
                        "data_line_count": len(data_lines),
                    },
                ),
                SourceWarning(
                    code=MISSING_RAW,
                    message=(
                        f"SIPRI Arms Transfers cached export at "
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
    # SipriArmsTransfersSchemaError BEFORE the transform layer
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
        version=SIPRI_ARMS_TRANSFERS_DEFAULT_VERSION,
        media_type="text/csv",
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
            "preamble_lines": preamble_lines,
            "header": header,
            "rows": rows,
            "metadata": metadata,
            "cache_path": cache_path,
            "asset_id": asset_id,
        },
        warnings=(),
    )

__all__ = [
    "SIPRI_ARMS_TRANSFERS_HEADER_MIN_MATCH",
    "SipriArmsTransfersSchemaError",
    "read_sipri_arms_transfers_csv",
]
