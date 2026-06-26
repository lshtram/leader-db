"""Unified-source PTS raw-read orchestration.

Owns the body of :meth:`PTSAdapter.read_raw` extracted
into a free function :func:`read_pts_xlsx` so the
adapter class module stays focused on lifecycle wiring
+ registration. The function lazy-imports the legacy
reader (:func:`leaders_db.ingest.pts_xlsx.read_pts`)
inside the call so the unified package boundary is
preserved; the local-file-only read path emits a
:class:`RawReadResult` carrying the long-format
country-year DataFrame under ``payload['long_df']`` for
the transform layer plus the staged metadata bundle.

The PTS unified path is local-file only (no network).
The ``read_raw`` call loads the canonical
``PTS-2025.xlsx`` through the legacy reader, which
returns a wide-format DataFrame (one row per
``(COW_Code_A, Year)`` with columns ``country``,
``cow_code``, ``year``, ``region``, and one column per
catalog ``variable_name``). The transform layer
consumes this wide frame and emits one
:class:`NormalizedObservation` per
``(COW_Code_A, year, variable_name)`` triple (the
canonical PTS catalog has 3 indicator rows).

The canonical xlsx filename is derived from the
descriptor's
:data:`PTS_XLSX_NAME <._descriptor.PTS_XLSX_NAME>`
constant (matching the live download filename and the
staged ``local_files`` annotation). The bundle directory
is the canonical ``data/raw/political_terror_scale/``
folder (the human-readable bundle name; per
``docs/architecture/sources.md`` §7.5 reconciliation the
canonical slug is ``pts`` but the disk folder alias is
``political_terror_scale``).

The PTS unified path is local-file only (no network).
The xlsx is NEVER hashed by the unified adapter
beyond the optional metadata-checksum verification at
the readiness gate -- the readiness gate optionally
verifies the staged xlsx's SHA-256 against the
metadata ``sha256`` field (the canonical PTS bundle
ships ``"6f4d1ccd...88832"`` per
``docs/architecture/pts.md`` §2). The raw asset's
``checksum_sha256`` field is intentionally left as
``None`` so the raw asset does not lie about a
checksum that the unified adapter does not actually
record.

The readiness gate
(:func:`check_metadata_well_formed`) returns
``ready=False`` with a structured ``MISSING_RAW`` error
when the xlsx is not staged on disk. The
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
    PTS_DEFAULT_VERSION,
    PTS_METADATA_NAME,
    PTS_XLSX_ASSET_ID,
    PTS_XLSX_NAME,
)


def _bundle_dir(request: SourceIngestRequest) -> Path:
    """Return the resolved
    ``<raw_root>/political_terror_scale/`` bundle
    directory.

    The canonical PTS bundle folder is the
    human-readable ``political_terror_scale/`` (NOT
    ``pts/``) per the source-key / folder-alias
    reconciliation documented in
    ``docs/architecture/sources.md`` §7.5: the
    canonical slug is ``pts`` (CLI dispatch + adapter
    key) but the disk folder alias is
    ``political_terror_scale`` (the human-readable
    bundle name, preserved from the live download +
    the staged ``metadata.json`` shape).
    """
    return Path(request.raw_root) / "political_terror_scale"


def _xlsx_path(request: SourceIngestRequest) -> Path:
    """Return the canonical xlsx path for the request
    scope.

    The PTS canonical bundle ships one xlsx at
    ``data/raw/political_terror_scale/PTS-2025.xlsx``
    (the canonical xlsx download). The unified adapter
    always reads the canonical xlsx -- the request's
    ``years=`` filter is applied on the wide frame
    after the legacy read so out-of-coverage year
    requests still pass readiness and the transform
    emits zero observations plus a structured
    ``YEAR_ABSENT`` warning per offending year.
    """
    return _bundle_dir(request) / PTS_XLSX_NAME


def _metadata_path(request: SourceIngestRequest) -> Path:
    """Return the request-scoped ``metadata.json``
    path."""
    return _bundle_dir(request) / PTS_METADATA_NAME


def _read_metadata_payload(metadata_path: Path) -> dict[str, Any]:
    """Return the parsed ``metadata.json`` payload, or
    ``{}`` on any error.

    The unified ``read_raw`` call uses this helper to
    load the staged bundle's ``source_url`` /
    ``alternate_url`` / ``license`` metadata fields so
    the raw asset can carry the canonical citation URL
    forward to the observation layer.
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


def read_pts_xlsx(
    request: SourceIngestRequest,
) -> RawReadResult:
    """Open the staged ``PTS-2025.xlsx`` and return the
    raw bundle.

    Lazy-imports the legacy reader so the unified
    package boundary is preserved. The wide-format
    DataFrame (one row per ``(COW_Code_A, Year)`` with
    one column per catalog ``variable_name``, plus the
    audit-trail columns ``country``, ``cow_code``,
    ``region``, and the per-cell ``_pts_raw_lookup``
    attribute carrying the original cell text for the
    ``raw_value`` audit trail) is carried in
    :attr:`RawReadResult.payload` under ``"wide_df"``
    for the transform layer. The ``read_raw`` call
    loads the full xlsx so the transform layer applies
    the request year + country filters on the wide
    frame.

    The PTS unified path is local-file only (no
    network). The xlsx is NEVER hashed by the unified
    adapter beyond the readiness gate's optional
    metadata-checksum verification. The raw asset's
    ``checksum_sha256`` field is intentionally left as
    ``None`` so the raw asset does not lie about a
    checksum that the unified adapter does not
    actually record.

    The legacy ``read_pts`` reader also accepts a
    ``catalog_path`` kwarg. The unified adapter passes
    the catalog path resolved from the canonical
    checked-in location (``DEFAULT_CATALOG_PATH`` in
    :mod:`._catalog`) via the transform layer's
    catalog loader, so the ``read_raw`` call here does
    not need to thread the catalog path through.

    When the staged xlsx is absent, the readiness gate
    (:func:`check_metadata_well_formed`) fires the
    structured ``MISSING_RAW`` error BEFORE
    ``read_raw`` is invoked, and the
    ``SourceIngestRunner`` raises ``RuntimeError`` --
    so this function is only reached when the bundle
    is runner-ready (the staged xlsx is present on
    disk).
    """
    # Lazy import: keeps ``leaders_db.sources``
    # importable without ``leaders_db.ingest``
    # (docs/architecture/sources.md §10.1 +
    # docs/requirements/sources.md §12 SRC-MIG-007).
    from leaders_db.ingest.pts_xlsx import read_pts as _legacy_read_pts

    xlsx_path = _xlsx_path(request)
    wide_df = _legacy_read_pts(xlsx_path=xlsx_path)
    metadata = _read_metadata_payload(_metadata_path(request))

    # Carry the canonical PTS source URL metadata onto
    # the RawAsset. The staged bundle's ``source_url``
    # field is the canonical xlsx download URL; the
    # ``alternate_url`` field carries the optional CSV
    # mirror URL. Prefer the staged source_url when
    # present because the staged bundle carries the
    # canonical citation landing page.
    asset_url: str | None = None
    staged_url = metadata.get("source_url")
    if isinstance(staged_url, str) and staged_url.strip():
        asset_url = staged_url.strip()

    asset = RawAsset(
        asset_id=PTS_XLSX_ASSET_ID,
        source_id=request.source_id,
        version=PTS_DEFAULT_VERSION,
        media_type=(
            "application/vnd.openxmlformats-officedocument"
            ".spreadsheetml.sheet"
        ),
        path=xlsx_path,
        url=asset_url,
        # The unified adapter does NOT hash the staged
        # xlsx -- the readiness gate optionally verifies
        # the xlsx SHA-256 against the metadata
        # ``sha256`` field (the canonical PTS bundle
        # ships ``"6f4d1ccd...88832"`` per design doc
        # §2). The raw asset's checksum field stays
        # ``None`` so downstream code does not assume a
        # checksum that the unified adapter does not
        # actually record.
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
            "xlsx_name": PTS_XLSX_NAME,
        },
        warnings=(),
    )


__all__ = [
    "_bundle_dir",
    "_metadata_path",
    "_read_metadata_payload",
    "_xlsx_path",
    "read_pts_xlsx",
]
