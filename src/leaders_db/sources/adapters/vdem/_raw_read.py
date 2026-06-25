"""Unified-source V-Dem raw-read orchestration.

Owns the body of :meth:`VDemAdapter.read_raw` extracted into a
free function :func:`read_vdem_csv` so the adapter class
module stays focused on lifecycle wiring + registration. The
function lazy-imports the legacy reader
(:func:`leaders_db.ingest.vdem_io.read_vdem_csv`) so the
unified package boundary is preserved; the local-file-only
read path emits a :class:`RawReadResult` carrying the narrow
DataFrame under ``payload["narrow_df"]`` for the transform
layer plus the staged metadata bundle.

The V-Dem unified path is local-file only (no network). The
``read_raw`` call passes ``year=None`` so the legacy reader
returns the full frame; the transform layer applies the
request year / country filters on the narrow frame so the
request-scoping semantics stay in one place.
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
    VDEM_CSV_ASSET_ID,
    VDEM_CSV_NAME,
    VDEM_DEFAULT_VERSION,
)


def _bundle_dir(request: SourceIngestRequest) -> Path:
    """Return the resolved ``<raw_root>/vdem/`` bundle directory."""
    return Path(request.raw_root) / "vdem"


def _csv_path(request: SourceIngestRequest) -> Path:
    """Return the request-scoped ``V-Dem-CY-Full+Others-v16.csv`` path."""
    return _bundle_dir(request) / VDEM_CSV_NAME


def _metadata_path(request: SourceIngestRequest) -> Path:
    """Return the request-scoped ``metadata.json`` path."""
    return _bundle_dir(request) / "metadata.json"


def _read_metadata_payload(metadata_path: Path) -> dict[str, Any]:
    """Return the parsed ``metadata.json`` payload, or ``{}`` on any error."""
    if not metadata_path.is_file():
        return {}
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def read_vdem_csv(request: SourceIngestRequest) -> RawReadResult:
    """Open the staged ``V-Dem-CY-Full+Others-v16.csv`` and return the raw bundle.

    Lazy-imports the legacy reader so the unified package
    boundary is preserved. The narrow DataFrame (one row per
    ``(country_text_id, year)`` with one column per catalog
    ``raw_column``, plus the four identity columns) is carried
    in :attr:`RawReadResult.payload` under ``"narrow_df"`` for
    the transform layer. The ``read_raw`` call passes
    ``year=None`` so the legacy reader returns the full frame;
    the transform layer applies the request year + country
    filters on the narrow frame so the request-scoping
    semantics stay in one place.

    The V-Dem unified path is local-file only (no network).
    The CSV is NEVER hashed by the unified adapter -- the
    388MB file would dwarf the readiness gate's cost for
    no benefit. The metadata checksum (which covers the
    zip, NOT the CSV) is validated by the readiness gate in
    :func:`._readiness.check_metadata_well_formed`; the
    raw asset's ``checksum_sha256`` field is intentionally
    left as ``None`` because the unified adapter does not
    know the canonical CSV SHA-256 from the metadata (the
    metadata records the zip's SHA-256). Audit code can
    re-hash the CSV at the read site if a per-CSV checksum
    is required.

    The legacy ``read_vdem_csv`` reader also accepts a
    ``catalog_path`` kwarg. The unified adapter passes the
    catalog path resolved from the canonical checked-in
    location (``DEFAULT_CATALOG_PATH`` in :mod:`._catalog`)
    via the transform layer's catalog loader, so the
    ``read_raw`` call here does not need to thread the
    catalog path through.
    """
    # Lazy import: keeps ``leaders_db.sources`` importable
    # without ``leaders_db.ingest`` (docs/architecture/sources.md
    # §10.1 + docs/requirements/sources.md §12 SRC-MIG-007).
    from leaders_db.ingest.vdem_io import (
        read_vdem_csv as _legacy_read_vdem_csv,
    )

    csv_path = _csv_path(request)
    # Pass ``year=None`` so the legacy reader returns the
    # full narrow frame; the transform layer applies the
    # request year filter + the request country filter.
    # This keeps the legacy reader's behaviour intact while
    # giving the new transform full control over the
    # request-scoping decisions.
    narrow_df = _legacy_read_vdem_csv(csv_path=csv_path)
    metadata = _read_metadata_payload(_metadata_path(request))

    # Carry the source URL metadata onto the RawAsset. The
    # staged bundle's ``source_url`` field is the canonical
    # V-Dem data landing page; the descriptor's homepage_url
    # field is the DOI. Prefer the staged URL when present
    # because the staged bundle carries the canonical page.
    asset_url = None
    staged_url = metadata.get("source_url")
    if isinstance(staged_url, str) and staged_url.strip():
        asset_url = staged_url.strip()

    asset = RawAsset(
        asset_id=VDEM_CSV_ASSET_ID,
        source_id=request.source_id,
        version=VDEM_DEFAULT_VERSION,
        media_type="text/csv",
        path=csv_path,
        url=asset_url,
        # The unified adapter does NOT hash the 388MB CSV --
        # see the function docstring for the rationale.
        # Audit code can compute the per-CSV SHA-256 at
        # the read site if needed.
        checksum_sha256=None,
        retrieved_at=None,
        immutable=True,
    )
    return RawReadResult(
        source_id=request.source_id,
        assets=(asset,),
        payload={
            "narrow_df": narrow_df,
            "metadata": metadata,
            "csv_path": csv_path,
        },
        warnings=(),
    )


__all__ = [
    "_bundle_dir",
    "_csv_path",
    "_metadata_path",
    "_read_metadata_payload",
    "read_vdem_csv",
]
