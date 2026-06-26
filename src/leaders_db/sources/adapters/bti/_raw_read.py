"""Unified-source BTI raw-read orchestration.

Owns the body of :meth:`BTIAdapter.read_raw` extracted
into a free function :func:`read_bti_xlsx` so the
adapter class module stays focused on lifecycle
wiring + registration. The function lazy-imports the
legacy reader (:func:`leaders_db.ingest.bti_xlsx.read_bti`)
inside the call so the unified package boundary is
preserved; the local-file-only read path emits a
:class:`RawReadResult` carrying the wide-format
country-year DataFrame under ``payload["wide_df"]``
for the transform layer plus the staged metadata
bundle.

The BTI unified path is local-file only (no network).
The ``read_raw`` call loads the canonical cumulative
``BTI_2006-2026_Scores.xlsx`` through the legacy
reader, which returns a wide-format DataFrame (one
row per ``(country, year)`` with columns ``country``,
``year``, and one column per catalog
``variable_name``). The pre-coercion raw cell text
is attached to ``df.attrs["_bti_raw_long"]``; the
resolved BTI edition sheet name is attached to
``df.attrs["_bti_sheet_name"]``. The transform layer
consumes this wide frame and emits one
:class:`NormalizedObservation` per
``(country, year, variable_name)`` triple (the
canonical BTI catalog has 12 indicator rows across 3
categories).

The canonical xlsx filename is derived from the
descriptor's
:data:`BTI_XLSX_NAME <._descriptor.BTI_XLSX_NAME>`
constant (matching the live download filename and the
staged ``local_files`` annotation). The bundle
directory is the canonical ``data/raw/bti/`` folder
(the slug is the folder name; no source-key /
folder-alias reconciliation needed, unlike ``pts`` /
``political_terror_scale``).

The BTI unified path is local-file only (no network).
The xlsx is NEVER hashed by the unified adapter
beyond the optional metadata-checksum verification at
the readiness gate -- the readiness gate optionally
verifies the staged xlsx's SHA-256 against the
metadata ``checksum_sha256`` field (the canonical BTI
bundle ships per-file SHA-256 values per
``data/raw/bti/metadata.json``). The raw asset's
``checksum_sha256`` field is intentionally left as
``None`` so the raw asset does not lie about a
checksum that the unified adapter does not actually
record.

The readiness gate
(:func:`check_metadata_well_formed`) returns
``ready=False`` with a structured ``MISSING_RAW``
error when the xlsx is not staged on disk. The
``SourceIngestRunner`` raises ``RuntimeError`` BEFORE
``read_raw`` is invoked so the legacy reader never
sees a missing-xlsx scenario in production -- this
``read_raw`` function is only reached when the bundle
is runner-ready.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from leaders_db.sources.contracts import (
    RawAsset,
    RawReadResult,
    SourceIngestRequest,
)

from ._descriptor import (
    BTI_DEFAULT_VERSION,
    BTI_METADATA_NAME,
    BTI_XLSX_ASSET_ID,
    BTI_XLSX_NAME,
)
from ._raw_sheets import read_requested_sheets


def _bundle_dir(request: SourceIngestRequest) -> Path:
    """Return the resolved ``<raw_root>/bti/`` bundle
    directory.

    The canonical BTI bundle folder is ``bti/`` (the
    slug is the folder name; no source-key /
    folder-alias reconciliation needed, unlike
    ``pts`` / ``political_terror_scale``).
    """
    from ._descriptor import BTI_SOURCE_KEY

    return Path(request.raw_root) / BTI_SOURCE_KEY


def _xlsx_path(request: SourceIngestRequest) -> Path:
    """Return the canonical xlsx path for the
    request scope.

    The BTI canonical bundle ships one cumulative
    xlsx at ``data/raw/bti/BTI_2006-2026_Scores.xlsx``
    (12 edition sheets; the request's ``years=``
    filter is applied on the wide frame after the
    legacy read so out-of-coverage year requests
    still pass readiness and the transform emits
    zero observations plus a structured
    ``YEAR_ABSENT`` warning per offending year).
    """
    return _bundle_dir(request) / BTI_XLSX_NAME


def _metadata_path(request: SourceIngestRequest) -> Path:
    """Return the request-scoped ``metadata.json``
    path."""
    return _bundle_dir(request) / BTI_METADATA_NAME


def _read_metadata_payload(metadata_path: Path) -> dict[str, Any]:
    """Return the parsed ``metadata.json`` payload,
    or ``{}`` on any error.

    The unified ``read_raw`` call uses this helper
    to load the staged bundle's ``source_url`` /
    ``license_note`` / ``checksum_sha256`` metadata
    fields so the raw asset can carry the canonical
    citation URL forward to the observation layer.
    """
    if not metadata_path.is_file():
        return {}
    try:
        payload = json.loads(
            metadata_path.read_text(encoding="utf-8"),
        )
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _resolve_xlsx_override(
    request: SourceIngestRequest,
) -> Path | None:
    """Return an xlsx override path from the raw
    payload, or ``None``.

    Reserved for future adapters that pass an
    alternate xlsx through ``raw.payload``. BTI
    always reads the canonical cumulative xlsx via
    :func:`_xlsx_path`; the helper exists for
    signature symmetry with the WGI / V-Dem /
    CPI / UCDP / PTS / RSF raw-read orchestrators.
    """
    if not isinstance(request.raw_root, Path):
        return None
    return None


def read_bti_xlsx(
    request: SourceIngestRequest,
) -> RawReadResult:
    """Open the staged cumulative
    ``BTI_2006-2026_Scores.xlsx`` and return the raw
    bundle.

    Lazy-imports the legacy reader so the unified
    package boundary is preserved. The wide-format
    DataFrame (one row per ``(country, year)`` with
    columns ``country``, ``year``, and one column
    per catalog ``variable_name``; the pre-coercion
    raw cell text attached to
    ``df.attrs["_bti_raw_long"]``; the resolved BTI
    edition sheet name attached to
    ``df.attrs["_bti_sheet_name"]``) is carried in
    :attr:`RawReadResult.payload` under
    ``"wide_df"`` for the transform layer. The
    ``read_raw`` call loads the cumulative xlsx (the
    request's ``years=`` / ``sheet_name=`` filters
    are applied inside the legacy reader so the
    transform layer applies only the request year +
    country filters on the wide frame).

    The BTI unified path is local-file only (no
    network). The xlsx is NEVER hashed by the
    unified adapter beyond the readiness gate's
    optional metadata-checksum verification. The raw
    asset's ``checksum_sha256`` field is
    intentionally left as ``None`` so downstream
    code does not assume a checksum that the
    unified adapter does not actually record.

    The legacy ``read_bti`` reader also accepts a
    ``catalog_path`` kwarg. The unified adapter
    passes the catalog path resolved from the
    canonical checked-in location
    (``DEFAULT_CATALOG_PATH`` in :mod:`._catalog`)
    via the transform layer's catalog loader, so
    the ``read_raw`` call here does not need to
    thread the catalog path through.

    When the staged xlsx is absent, the readiness
    gate (:func:`check_metadata_well_formed`) fires
    the structured ``MISSING_RAW`` error BEFORE
    ``read_raw`` is invoked, and the
    ``SourceIngestRunner`` raises ``RuntimeError``
    -- so this function is only reached when the
    bundle is runner-ready (the staged xlsx is
    present on disk).
    """
    # Lazy import: keeps ``leaders_db.sources``
    # importable without ``leaders_db.ingest``
    # (docs/architecture/sources.md §10.1 +
    # docs/requirements/sources.md §12
    # SRC-MIG-007).
    from leaders_db.ingest.bti_xlsx import read_bti as _legacy_read_bti

    xlsx_path = _xlsx_path(request)
    wide_df = read_requested_sheets(
        request, xlsx_path, _legacy_read_bti,
    )
    metadata = _read_metadata_payload(_metadata_path(request))

    # Carry the canonical BTI source URL metadata
    # onto the RawAsset. The staged bundle's
    # ``source_url`` field is the canonical BTI
    # downloads page URL; prefer the staged
    # source_url when present because the staged
    # bundle carries the canonical citation
    # landing page.
    asset_url: str | None = None
    staged_url = metadata.get("source_url")
    if isinstance(staged_url, str) and staged_url.strip():
        asset_url = staged_url.strip()

    asset = RawAsset(
        asset_id=BTI_XLSX_ASSET_ID,
        source_id=request.source_id,
        version=BTI_DEFAULT_VERSION,
        media_type=(
            "application/vnd.openxmlformats-officedocument"
            ".spreadsheetml.sheet"
        ),
        path=xlsx_path,
        url=asset_url,
        # The unified adapter does NOT hash the
        # staged xlsx -- the readiness gate
        # optionally verifies the xlsx SHA-256
        # against the metadata ``checksum_sha256``
        # field (the canonical BTI bundle ships
        # per-file SHA-256 values per
        # ``data/raw/bti/metadata.json``). The raw
        # asset's checksum field stays ``None`` so
        # downstream code does not assume a
        # checksum that the unified adapter does
        # not actually record.
        checksum_sha256=None,
        retrieved_at=None,
        immutable=True,
    )
    return RawReadResult(
        source_id=request.source_id,
        assets=(asset,),
        payload={
            "wide_df": wide_df,
            "metadata": metadata,
            "xlsx_path": xlsx_path,
            "xlsx_name": BTI_XLSX_NAME,
        },
        warnings=(),
    )


__all__ = [
    "_bundle_dir",
    "_metadata_path",
    "_read_metadata_payload",
    "_resolve_xlsx_override",
    "_xlsx_path",
    "read_bti_xlsx",
]
