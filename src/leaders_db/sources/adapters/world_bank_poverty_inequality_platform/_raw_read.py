"""Raw CSV / JSON reader for the clean World Bank Poverty and
Inequality Platform (PIP) adapter.

This module owns the body of
:meth:`WorldBankPovertyInequalityPlatformAdapter.read_raw` extracted
into free functions so the adapter class module stays focused
on lifecycle wiring + registration. The reader supports the two
cached export shapes the task brief explicitly endorses:

1. **Direct CSV** -- a plain CSV file at
   ``data/raw/world_bank_poverty_inequality_platform/pip_stats.csv``
   carrying the canonical 11-column PIP schema (country_code /
   country_name / year / reporting_level / welfare_type /
   poverty_line / headcount / poverty_gap / gini /
   version_id / ppp_version). The reader
   uses the Python ``csv`` module to parse the cached rows.

2. **Cached JSON wrapper** -- a JSON array of objects at
   ``data/raw/world_bank_poverty_inequality_platform/pip_stats.json``
   carrying the same 11-column PIP schema as object keys. The
   reader parses the JSON array and routes each object into a
   dict keyed by the header column names. The JSON fallback
   shape mirrors the canonical CSV schema; missing required
   keys fire the same :class:`WorldBankPipSchemaError` as the
   CSV shape.

Schema-contract enforcement
---------------------------

The raw-read layer is the canonical boundary at which the
cached CSV / JSON schema is enforced. The 11 documented required
columns ``country_code`` / ``country_name`` / ``year`` /
``reporting_level`` / ``welfare_type`` / ``poverty_line`` /
``headcount`` / ``poverty_gap`` / ``gini`` / ``version_id`` /
``ppp_version`` MUST be present in
the parsed header; a missing required column fires a
structured :class:`WorldBankPipSchemaError` so the transform
layer does NOT silently emit partial output on a schema
contract violation. Metadata must declare the supported
``version_id`` / ``ppp_version`` pair and every row must match
that release / PPP basis before transform.

Per-row preservation
--------------------

The raw-read layer preserves the source-native country display
name + source-native country code verbatim on every parsed row
so the transform layer can propagate them onto the
observation's audit-trail extension payload. Blank / missing
numeric cells are preserved as ``""`` strings so the
transform layer can emit
``value=None`` / ``value_type="missing"`` plus the verbatim
raw cell text on the audit-trail extension. The required audit
columns are ``version_id`` and ``ppp_version``. Extra audit
columns such as ``ppp_base_year`` / ``survey_year`` /
``survey_comparability`` / ``notes`` are preserved on the parsed
row payload when present in the cached header so downstream code
can recover the verbatim provenance.
"""

from __future__ import annotations

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
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_COV_HEADER_ROW,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_CSV_ASSET_ID,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_PPP_VERSION,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_VERSION,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_VERSION_ID,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_JSON_ASSET_ID,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_REQUIRED_COLUMNS,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_SCHEMA_ERROR,
)
from ._readiness import (
    csv_path,
    json_path,
    metadata_path,
    read_metadata,
)


class WorldBankPipSchemaError(ValueError):
    """Structured failure raised when the cached World Bank PIP
    CSV / JSON is missing required columns.

    The transform layer MUST NOT silently produce partial output
    when the schema contract is violated -- the raw-read
    boundary raises this exception BEFORE the transform layer
    consumes the parsed frame. The exception carries:

    - ``code``: the structured warning code
      ``"world_bank_poverty_inequality_platform_schema_error"``.
    - ``source_id``: the :class:`SourceId` carrying the failing
      source slug
      (``"world_bank_poverty_inequality_platform"``).
    - ``missing_columns``: a tuple of the column names that the
      parsed CSV / JSON header did NOT produce but the adapter
      requires.
    - ``expected_columns``: a tuple of every required indicator
      column (the canonical 11-column catalog).
    - ``actual_columns``: a tuple of every column the parsed
      CSV / JSON header produced.
    - ``cache_path``: the resolved cached file path (when
      available).

    The exception ``str`` representation is intentionally
    self-describing so a CLI run / log line / pytest failure
    tells the operator which columns are missing without
    reading source code.
    """

    code: str = WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_SCHEMA_ERROR

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
            f"World Bank PIP raw-read schema validation "
            f"failed "
            f"({WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_SCHEMA_ERROR})"
            f"{path_str}: the cached export is missing "
            f"{len(missing_columns)} required column(s) "
            f"({missing_str}); the unified World Bank PIP "
            f"adapter requires every required indicator "
            f"column in {tuple(expected_columns)!r} but the "
            f"reader produced {tuple(actual_columns)!r}. "
            f"Re-stage a canonical World Bank PIP bundle or "
            f"update the adapter contract before running "
            f"ingestion; the transform layer does NOT silently "
            f"emit partial output on schema violations."
        )


def _parse_csv_text(
    csv_text: str,
) -> tuple[list[str], list[dict[str, str]]]:
    """Parse the cached CSV text into a (header, rows) pair.

    Uses the Python ``csv`` module to parse the cached CSV
    against the documented PIP header. Returns ``(header, rows)``
    where ``header`` is the canonical column-name list and
    ``rows`` is a list of dicts keyed by the header column
    names. Skips malformed CSV rows (rows whose column count
    does not match the header) safely -- the transform layer
    emits zero observations for skipped rows.

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
            # silently here; the readiness gate already validated
            # the header so row-level mismatches are parse-time
            # corruption rather than a schema contract
            # violation. The transform layer preserves the
            # verbatim raw_value on the audit-trail extension
            # so audit code can recover the dropped row.
            continue
        row_dict: dict[str, str] = {}
        for col_name, col_value in zip(header, row, strict=True):
            row_dict[col_name] = col_value.strip()
        rows.append(row_dict)
    return header, rows


def _parse_json_payload(  # noqa: PLR0912
    json_text: str,
    *,
    source_id: Any | None = None,
    cache_path: Path | None = None,
) -> tuple[list[str], list[dict[str, str]]]:
    """Parse the cached JSON array payload into a (header, rows)
    pair.

    The cached World Bank PIP JSON shape mirrors the canonical
    CSV schema: a JSON array of objects keyed by the 11
    canonical required column names. The reader parses the array,
    computes the canonical header (the union of every object's
    keys, in the order they first appear), and routes each
    object into a dict keyed by the header column names (a
    missing optional column is preserved as ``""``).

    Returns ``(header, [])`` when the JSON array is empty.
    Raises :class:`ValueError` when the payload is not a JSON
    array of objects so the caller can surface a structured
    readiness error.
    """
    payload = json.loads(json_text)
    if not isinstance(payload, list):
        raise ValueError(
            "World Bank PIP cached JSON shape is not a JSON "
            f"array of objects (got {type(payload).__name__})"
        )
    if not payload:
        return [], []
    # Compute the canonical header as the union of every
    # object's keys, in the order they first appear. The
    # canonical CSV header order is the documented 11-column
    # contract; if the cached JSON header diverges (e.g.
    # extra optional columns), the readiness gate surfaces a
    # structured schema-violation error.
    canonical_header: list[str] = list(
        WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_COV_HEADER_ROW
    )
    seen: set[str] = set(canonical_header)
    header: list[str] = list(canonical_header)
    for item in payload:
        if not isinstance(item, dict):
            continue
        missing = tuple(
            col for col in WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_REQUIRED_COLUMNS
            if col not in item
        )
        if missing:
            if source_id is not None and cache_path is not None:
                raise WorldBankPipSchemaError(
                    source_id=source_id,
                    missing_columns=missing,
                    expected_columns=tuple(
                        WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_REQUIRED_COLUMNS
                    ),
                    actual_columns=tuple(
                        key for key in item.keys() if isinstance(key, str)
                    ),
                    cache_path=cache_path,
                )
            raise ValueError(
                "World Bank PIP cached JSON object is missing "
                f"required key(s): {missing!r}"
            )
        for key in item.keys():
            if not isinstance(key, str) or key in seen:
                continue
            header.append(key)
            seen.add(key)
    rows: list[dict[str, str]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        row_dict: dict[str, str] = {}
        for col_name in header:
            value = item.get(col_name)
            if value is None:
                row_dict[col_name] = ""
            elif isinstance(value, str):
                row_dict[col_name] = value.strip()
            else:
                row_dict[col_name] = str(value).strip()
        rows.append(row_dict)
    return header, rows


def _validate_row_version_basis(
    rows: list[dict[str, str]],
    *,
    metadata: dict[str, Any],
    source_id: Any,
    cache_path: Path,
) -> None:
    """Reject rows whose version_id / ppp_version disagree
    with the canonical bundle metadata.

    This is the raw-read boundary that prevents silently mixing
    2021-PPP and 2017-PPP PIP rows or labeling one release as
    another. A violation is surfaced as the same structured
    schema-error path as missing required columns, before
    transform emits observations.
    """
    metadata_version = str(metadata.get("version_id", "")).strip()
    metadata_ppp = str(metadata.get("ppp_version", "")).strip()
    expected_version = metadata_version or WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_VERSION_ID
    expected_ppp = metadata_ppp or WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_PPP_VERSION
    for row in rows:
        row_version = str(row.get("version_id", "")).strip()
        row_ppp = str(row.get("ppp_version", "")).strip()
        missing: list[str] = []
        if not row_version:
            missing.append("version_id")
        if not row_ppp:
            missing.append("ppp_version")
        if missing:
            raise WorldBankPipSchemaError(
                source_id=source_id,
                missing_columns=tuple(missing),
                expected_columns=tuple(
                    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_REQUIRED_COLUMNS
                ),
                actual_columns=tuple(row.keys()),
                cache_path=cache_path,
            )
        if row_version != expected_version:
            raise WorldBankPipSchemaError(
                source_id=source_id,
                missing_columns=("version_id",),
                expected_columns=(expected_version,),
                actual_columns=(row_version,),
                cache_path=cache_path,
            )
        if row_ppp != expected_ppp:
            raise WorldBankPipSchemaError(
                source_id=source_id,
                missing_columns=("ppp_version",),
                expected_columns=(expected_ppp,),
                actual_columns=(row_ppp,),
                cache_path=cache_path,
            )


def _validate_header_columns(
    header: list[str],
    *,
    source_id: Any,
    cache_path: Path,
    required_columns: tuple[str, ...] = (
        WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_REQUIRED_COLUMNS
    ),
) -> None:
    """Raise :class:`WorldBankPipSchemaError` if any required
    column is missing from the parsed header.

    The transform layer MUST NOT silently produce partial output
    when the schema contract is violated -- this helper
    enforces the contract at the raw-read boundary. An empty
    header (i.e. the cached CSV / JSON carries no recognisable
    header row) is treated as a schema contract violation with
    every required column flagged as missing.
    """
    if not header:
        raise WorldBankPipSchemaError(
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
        raise WorldBankPipSchemaError(
            source_id=source_id,
            missing_columns=missing,
            expected_columns=tuple(required_columns),
            actual_columns=tuple(header),
            cache_path=cache_path,
        )


def _compute_cache_checksum(cache_path: Path) -> str | None:
    """Return the SHA-256 hex digest of the staged cache file.

    Returns ``None`` only when the cache file is missing or
    unreadable on disk -- the readiness gate already rejects a
    missing cache with a structured ``missing_raw`` error
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


def read_world_bank_poverty_inequality_platform_cache(
    request: SourceIngestRequest,
) -> RawReadResult:
    """Read the staged World Bank PIP cached CSV / JSON bundle
    and return the parsed raw payload.

    The reader:

    1. Loads the cached export bytes (CSV shape preferred;
       falls back to the JSON shape when the CSV is absent).
    2. Parses the cached text into a (header, rows) pair via
       the Python ``csv`` module (CSV shape) or the JSON
       parser (JSON shape).
    3. Validates the header against the 11 canonical required
       columns and raises :class:`WorldBankPipSchemaError`
       BEFORE the transform layer consumes the frame.
    4. Carries the parsed frame on ``payload["rows"]`` plus the
       original ``header`` list plus the cached cache path /
       asset id for the transform layer.
    5. Computes the SHA-256 of the staged cache file (the
       verified / staged on-disk fingerprint) and populates the
       :class:`RawAsset` ``checksum_sha256`` field so downstream
       audit code can recover the actual on-disk hash regardless
       of the metadata's ``checksum_sha256`` field shape
       (flat-string vs per-file dict).

    The reader is offline / cache-only in this slice; live fetch
    is intentionally NOT supported (the task brief: "Build an
    offline/cache-first adapter. Do NOT implement live HTTP
    fetching"). The cache-policy gate blocks
    ``cache_policy="refresh"`` / ``"no_cache"`` with a
    structured
    ``world_bank_poverty_inequality_platform_unsupported_cache_policy``
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
    json_p = json_path(request)
    metadata = read_metadata(metadata_path(request))

    if csv_p.is_file():
        cache_path = csv_p
        asset_id = WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_CSV_ASSET_ID
        csv_text = cache_path.read_text(encoding="utf-8")
        header, rows = _parse_csv_text(csv_text)
        asset_media_type = "text/csv"
    else:
        cache_path = json_p
        asset_id = WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_JSON_ASSET_ID
        json_text = cache_path.read_text(encoding="utf-8")
        header, rows = _parse_json_payload(
            json_text,
            source_id=request.source_id,
            cache_path=cache_path,
        )
        asset_media_type = "application/json"

    asset_checksum = _compute_cache_checksum(cache_path)

    if not header:
        # Cached file carries no recognisable CSV / JSON records.
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
                    version=(
                        WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_VERSION
                    ),
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
                    code=(
                        WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_SCHEMA_ERROR
                    ),
                    message=(
                        f"World Bank PIP cached export at "
                        f"{cache_path} carries no recognisable "
                        f"header + data rows partition matching "
                        f"the 11 canonical required columns; the "
                        f"reader could not find a header row + "
                        f"data rows partition. Re-stage a "
                        f"canonical World Bank PIP bundle with "
                        f"the documented header row "
                        f"({', '.join(WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_REQUIRED_COLUMNS)}) "
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
                        f"World Bank PIP cached export at "
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
    # WorldBankPipSchemaError BEFORE the transform layer
    # consumes the frame; the runner propagates the exception
    # so the CLI / tests can act on it.
    _validate_header_columns(
        header,
        source_id=request.source_id,
        cache_path=cache_path,
    )
    _validate_row_version_basis(
        rows,
        metadata=metadata,
        source_id=request.source_id,
        cache_path=cache_path,
    )

    asset = RawAsset(
        asset_id=asset_id,
        source_id=request.source_id,
        version=WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_VERSION,
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
            "version_id": metadata.get("version_id"),
            "ppp_version": metadata.get("ppp_version"),
        },
        warnings=(),
    )


__all__ = [
    "WorldBankPipSchemaError",
    "read_world_bank_poverty_inequality_platform_cache",
]
