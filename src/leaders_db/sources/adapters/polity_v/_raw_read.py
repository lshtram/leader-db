"""Unified-source Polity V raw-read orchestration.

Owns the body of :meth:`PolityVAdapter.read_raw` extracted into
a free function :func:`read_polity_v_sav` so the adapter class
module stays focused on lifecycle wiring + registration. The
function opens the staged ``p5v2018.sav`` via
``pyreadstat.read_sav`` (lazy-imported so the unified package
boundary is preserved), filters the raw frame to the canonical
1800-2018 coverage envelope (dropping the historical 1776-1799
backfill + the 2019-2020 stray rows), and emits a
:class:`RawReadResult` carrying the filtered frame under
``payload['wide_df']`` for the transform layer plus the staged
metadata bundle.

The Polity V unified path is local-file only (no network). The
``read_raw`` call uses ``pyreadstat.read_sav`` to load the SPSS
file (no legacy Stage 2 module to reuse -- Polity V is the
first source with no legacy Stage 2 implementation per the
workplan Done History). The returned DataFrame is one row per
``(ccode, country, year)`` triple with the 11 catalog indicator
columns + 26 other Polity V columns (which are preserved in
``df.attrs`` for audit code but NOT emitted as observations).

The transform layer consumes the filtered frame and emits one
:class:`NormalizedObservation` per ``(country, year,
variable_name)`` triple (the canonical Polity V catalog has 11
indicator rows). The canonical documented coverage is
1800-2018 per ``docs/sources/attributions.md`` § ``polity_v``;
the staged ``p5v2018.sav`` carries a small number of rows
outside that envelope (1776-1799 historical backfill + a few
2019-2020 strays) which the unified transform filters to the
canonical envelope. The descriptor advertises the canonical
envelope so downstream query code can refuse to dispatch
out-of-coverage year requests.

Schema-contract enforcement
--------------------------

The raw-read layer is the canonical boundary at which the
``p5v2018.sav`` schema is enforced (SPSS file presence +
metadata fields + SHA-256 match are validated by the readiness
gate BEFORE ``read_raw`` is invoked; the schema contract --
"every required identity column + every catalog indicator
column must be present" -- is enforced HERE because a
syntactically well-formed .sav can still be malformed: e.g.
a user-staged alternative Polity V variant without the
canonical 11 indicator columns, or a downstream user-edited
file that has dropped one or more columns). The transform
layer MUST NOT silently produce partial output when the
schema contract is violated; :class:`PolityVSchemaError`
carries the structured failure context (missing columns +
expected columns + actual columns + source id) so callers +
tests can act on it.

The readiness gate (:func:`check_metadata_well_formed`) returns
``ready=False`` with a structured ``missing_raw`` error when
the staged ``.sav`` is not on disk. The ``SourceIngestRunner``
raises ``RuntimeError`` BEFORE ``read_raw`` is invoked so the
SPSS reader never sees a missing-``sav`` scenario in
production -- this ``read_raw`` function is only reached when
the bundle is runner-ready.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from leaders_db.sources.contracts import (
    RawAsset,
    RawReadResult,
    SourceId,
    SourceIngestRequest,
)

from ._descriptor import (
    POLITY_V_COVERAGE_END_YEAR,
    POLITY_V_COVERAGE_START_YEAR,
    POLITY_V_DEFAULT_VERSION,
    POLITY_V_METADATA_NAME,
    POLITY_V_RAW_COLUMN_CCODE,
    POLITY_V_RAW_COLUMN_COUNTRY,
    POLITY_V_RAW_COLUMN_SCODE,
    POLITY_V_RAW_COLUMN_YEAR,
    POLITY_V_RAW_COLUMNS,
    POLITY_V_SAV_ASSET_ID,
    POLITY_V_SAV_NAME,
    POLITY_V_SOURCE_KEY,
)

# Identity columns the raw-read layer requires on every row.
# The transform layer uses these columns to build the per-row
# ``source_row_reference`` (``polity_v:<scode>:<year>:<raw_column>``)
# + the audit-trail extension dict; a missing identity column
# is a schema contract violation (the row would never be able
# to emit a valid ``NormalizedObservation``).
POLITY_V_REQUIRED_IDENTITY_COLUMNS: tuple[str, ...] = (
    POLITY_V_RAW_COLUMN_COUNTRY,
    POLITY_V_RAW_COLUMN_YEAR,
    POLITY_V_RAW_COLUMN_SCODE,
    POLITY_V_RAW_COLUMN_CCODE,
)


class PolityVSchemaError(ValueError):
    """Structured failure raised when the staged .sav is missing
    required columns.

    The transform layer MUST NOT silently produce partial output
    when the schema contract is violated -- the raw-read
    boundary raises this exception BEFORE the transform layer
    consumes the frame. The exception carries:

    - ``code``: the structured warning code ``"polity_v_schema_error"``
      (matches the shared :data:`MISSING_RAW`-style naming used
      by the readiness gate; the runner / CLI can dispatch on it).
    - ``source_id``: the :class:`SourceId` carrying the failing
      source slug (``"polity_v"``).
    - ``missing_columns``: a tuple of the column names that the
      SPSS reader did NOT produce but the adapter requires.
    - ``expected_columns``: a tuple of every required indicator
      column (the canonical 11 catalog columns).
    - ``actual_columns``: a tuple of every column the SPSS
      reader produced; useful for diff against ``expected_columns``.
    - ``sav_path``: the resolved ``p5v2018.sav`` path (when
      available).

    The exception ``str`` representation is intentionally
    self-describing so a CLI run / log line / pytest failure
    tells the operator which columns are missing without
    reading source code.
    """

    code: str = "polity_v_schema_error"

    def __init__(
        self,
        *,
        source_id: SourceId,
        missing_columns: tuple[str, ...],
        expected_columns: tuple[str, ...],
        actual_columns: tuple[str, ...],
        sav_path: Path | None = None,
    ) -> None:
        self.source_id = source_id
        self.missing_columns = tuple(missing_columns)
        self.expected_columns = tuple(expected_columns)
        self.actual_columns = tuple(actual_columns)
        self.sav_path = sav_path
        missing_str = ", ".join(repr(c) for c in missing_columns)
        path_str = f" at {sav_path}" if sav_path is not None else ""
        super().__init__(
            f"Polity V raw-read schema validation failed{path_str}: "
            f"the staged .sav is missing {len(missing_columns)} "
            f"required column(s) ({missing_str}); the unified "
            f"Polity V adapter requires every identity + "
            f"indicator column in {tuple(expected_columns)!r} "
            f"plus {tuple(POLITY_V_REQUIRED_IDENTITY_COLUMNS)!r} "
            f"but the SPSS reader produced "
            f"{tuple(actual_columns)!r}. Re-stage a canonical "
            f"Polity5 v2018 p5v2018.sav bundle (SHA-256 "
            f"c0405a807777610a65fe430e4b4828fda16717afc4b5d6e34bf56f1ca100f2f6) "
            f"or update the adapter contract before running "
            f"ingestion; the transform layer does NOT silently "
            f"emit partial output on schema violations."
        )


def _validate_wide_df_columns(
    wide_df: pd.DataFrame,
    *,
    source_id: SourceId,
    sav_path: Path | None,
    expected_columns: tuple[str, ...] = POLITY_V_RAW_COLUMNS,
    identity_columns: tuple[str, ...] = POLITY_V_REQUIRED_IDENTITY_COLUMNS,
) -> None:
    """Validate the loaded wide frame has every required column.

    Raises :class:`PolityVSchemaError` if any of the expected
    indicator or identity columns is missing. The transform
    layer MUST NOT silently emit partial output when the
    schema contract is violated -- this helper enforces the
    contract at the raw-read boundary.

    An empty frame (e.g. ``pyreadstat.read_sav`` returned zero
    rows for an essentially empty file) is also a schema
    contract violation -- the Polity V canonical bundle MUST
    carry at least one country-year row, so an empty frame
    raises :class:`PolityVSchemaError` with the
    ``missing_columns`` set to the full ``expected_columns``
    union so the operator sees the contract violation rather
    than a downstream ``KeyError`` from the transform layer.

    Parameters
    ----------
    wide_df:
        The wide-format DataFrame returned by
        :func:`pyreadstat.read_sav`.
    source_id:
        The :class:`SourceId` carrying the failing source slug
        (``"polity_v"``); propagated onto the raised
        :class:`PolityVSchemaError` so callers can route the
        failure by source.
    sav_path:
        Optional resolved ``p5v2018.sav`` path; propagated
        onto the raised exception's diagnostic context.
    expected_columns:
        The catalog indicator columns the adapter requires
        (defaults to :data:`POLITY_V_RAW_COLUMNS`).
    identity_columns:
        The identity columns the adapter requires on every row
        (defaults to
        :data:`POLITY_V_REQUIRED_IDENTITY_COLUMNS`).
    """
    if wide_df is None:
        raise PolityVSchemaError(
            source_id=source_id,
            missing_columns=tuple(
                (*identity_columns, *expected_columns),
            ),
            expected_columns=expected_columns,
            actual_columns=(),
            sav_path=sav_path,
        )
    actual_columns = tuple(wide_df.columns)
    if wide_df.empty:
        # Empty frame: the SPSS reader produced zero rows. The
        # canonical Polity V bundle MUST carry at least one
        # row, so the empty-frame case is treated as a schema
        # contract violation with every required column flagged
        # as missing.
        raise PolityVSchemaError(
            source_id=source_id,
            missing_columns=tuple(
                (*identity_columns, *expected_columns),
            ),
            expected_columns=expected_columns,
            actual_columns=actual_columns,
            sav_path=sav_path,
        )
    missing = tuple(
        col
        for col in (*identity_columns, *expected_columns)
        if col not in actual_columns
    )
    if missing:
        raise PolityVSchemaError(
            source_id=source_id,
            missing_columns=missing,
            expected_columns=expected_columns,
            actual_columns=actual_columns,
            sav_path=sav_path,
        )


def _bundle_dir(request: SourceIngestRequest) -> Path:
    """Return the resolved ``<raw_root>/polity_v/`` bundle directory.

    The canonical Polity V bundle folder is ``polity_v/`` (the
    slug is the folder name; no source-key / folder-alias
    reconciliation is needed).
    """
    return Path(request.raw_root) / POLITY_V_SOURCE_KEY


def _sav_path(request: SourceIngestRequest) -> Path:
    """Return the request-scoped ``p5v2018.sav`` path."""
    return _bundle_dir(request) / POLITY_V_SAV_NAME


def _metadata_path(request: SourceIngestRequest) -> Path:
    """Return the request-scoped ``metadata.json`` path."""
    return _bundle_dir(request) / POLITY_V_METADATA_NAME


def _read_metadata_payload(metadata_path: Path) -> dict[str, Any]:
    """Return the parsed ``metadata.json`` payload, or ``{}`` on any error."""
    if not metadata_path.is_file():
        return {}
    try:
        payload = json.loads(
            metadata_path.read_text(encoding="utf-8"),
        )
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _filter_to_canonical_coverage(
    wide_df: pd.DataFrame,
    *,
    coverage_start_year: int = POLITY_V_COVERAGE_START_YEAR,
    coverage_end_year: int = POLITY_V_COVERAGE_END_YEAR,
) -> pd.DataFrame:
    """Return the wide frame filtered to the canonical 1800-2018 envelope.

    The staged ``p5v2018.sav`` carries a small number of rows
    outside the canonical envelope (1776-1799 historical
    backfill + a few 2019-2020 strays). The unified transform
    filters the frame to the canonical envelope so the
    descriptor's coverage hint is the authoritative public
    contract; out-of-coverage rows surface a structured
    ``YEAR_ABSENT`` warning on the readiness envelope so the
    operator can see the gap (no stale-proxy fill per
    SRC-COV-002 / SRC-COV-003).
    """
    if wide_df.empty:
        return wide_df
    if "year" not in wide_df.columns:
        return wide_df
    # The SPSS file stores ``year`` as a float64 column; the
    # canonical coverage filter uses ``int(year)`` so the
    # comparison is exact (the Polity V year column is always
    # whole-number). NaN year values are dropped by the
    # comparison (NaN comparisons are always False).
    year_series = wide_df["year"].astype("Int64")
    mask = (
        (year_series >= coverage_start_year)
        & (year_series <= coverage_end_year)
    )
    return wide_df.loc[mask].reset_index(drop=True)


def read_polity_v_sav(request: SourceIngestRequest) -> RawReadResult:
    """Open the staged ``p5v2018.sav`` and return the raw bundle.

    Lazy-imports ``pyreadstat`` (no legacy Stage 2 module to
    reuse -- Polity V is the first source with no legacy Stage
    2 implementation per the workplan Done History). The
    wide-format DataFrame (one row per ``(ccode, country,
    year)`` triple with the 11 catalog indicator columns + 26
    other Polity V columns) is carried in
    :attr:`RawReadResult.payload` under ``"wide_df"`` for the
    transform layer.

    The Polity V unified path is local-file only (no network).
    The staged ``.sav`` is hashed by the readiness gate's
    per-file SHA-256 verification; the raw asset's
    ``checksum_sha256`` field is set to the SHA-256 of the
    staged file when the readiness gate confirms a match.

    The readiness gate (:func:`check_metadata_well_formed`)
    returns ``ready=False`` with a structured ``missing_raw``
    error when the staged ``.sav`` is not on disk; the
    ``SourceIngestRunner`` raises ``RuntimeError`` BEFORE
    ``read_raw`` is invoked so the SPSS reader never sees a
    missing-``sav`` scenario in production -- this function is
    only reached when the bundle is runner-ready.
    """
    sav_path = _sav_path(request)
    metadata = _read_metadata_payload(_metadata_path(request))

    # Compute the staged .sav SHA-256 + carry it on the raw
    # asset. The readiness gate verifies the same SHA-256
    # against ``metadata.json['checksum_sha256']`` BEFORE this
    # function is invoked; when readiness passes, the asset's
    # SHA-256 is non-null and matches the metadata field.
    actual_sha = hashlib.sha256(sav_path.read_bytes()).hexdigest()

    asset_url: str | None = None
    staged_source_url = metadata.get("source_url")
    if (
        isinstance(staged_source_url, str)
        and staged_source_url.strip()
    ):
        asset_url = staged_source_url.strip()

    # Lazy import: keeps ``leaders_db.sources`` importable
    # without the SPSS dependency at import time. The
    # ``pyreadstat`` import is module-level lazy, not adapter
    # module-level eager -- the adapter package boundary
    # (SRC-MIG-007, docs/architecture/sources.md §10.1) only
    # forbids eager ``leaders_db.ingest`` imports.
    import pyreadstat

    wide_df, _sav_meta = pyreadstat.read_sav(str(sav_path))

    # Schema-contract enforcement at the raw-read boundary: a
    # syntactically well-formed .sav can still be malformed
    # (e.g. a user-staged alternative Polity V variant without
    # the canonical 11 indicator columns, or a downstream
    # user-edited file that dropped one or more columns). The
    # transform layer MUST NOT silently emit partial output on
    # a schema violation -- the helper raises
    # :class:`PolityVSchemaError` BEFORE the transform layer
    # consumes the frame, carrying the structured missing-
    # columns context. The runner propagates the exception so
    # the CLI / tests can act on it.
    _validate_wide_df_columns(
        wide_df,
        source_id=request.source_id,
        sav_path=sav_path,
    )

    # Filter to the canonical 1800-2018 envelope. The staged
    # .sav carries rows outside that envelope (1776-1799
    # historical backfill + 2019-2020 strays); the unified
    # transform filters them out per the documented
    # canonical-coverage contract.
    filtered_df = _filter_to_canonical_coverage(wide_df)

    # Preserve the per-row ``source_row_reference`` value the
    # transform layer will use. The pattern is
    # ``polity_v:<scode>:<year>`` (scode is the Polity V
    # 3-letter alphabetic country code; the canonical pattern
    # matches the legacy Stage 2 ingestion plan).
    asset = RawAsset(
        asset_id=POLITY_V_SAV_ASSET_ID,
        source_id=request.source_id,
        version=POLITY_V_DEFAULT_VERSION,
        media_type="application/x-spss-sav",
        path=sav_path,
        url=asset_url,
        checksum_sha256=actual_sha,
        retrieved_at=None,
        immutable=True,
    )

    return RawReadResult(
        source_id=request.source_id,
        assets=(asset,),
        payload={
            "wide_df": filtered_df,
            "metadata": metadata,
            "sav_path": sav_path,
            "expected_columns": list(POLITY_V_RAW_COLUMNS),
        },
        warnings=(),
    )


__all__ = [
    "POLITY_V_REQUIRED_IDENTITY_COLUMNS",
    "PolityVSchemaError",
    "_bundle_dir",
    "_filter_to_canonical_coverage",
    "_metadata_path",
    "_read_metadata_payload",
    "_sav_path",
    "_validate_wide_df_columns",
    "read_polity_v_sav",
]
