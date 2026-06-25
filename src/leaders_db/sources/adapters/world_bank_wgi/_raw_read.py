"""Unified-source World Bank WGI raw-read orchestration.

Owns the body of :meth:`WGIAdapter.read_raw` extracted into
a free function :func:`read_world_bank_wgi_xlsx` so the adapter
class module stays focused on lifecycle wiring + registration.
The function lazy-imports the legacy reader
(:func:`leaders_db.ingest.wgi_xlsx.read_wgi`) so the unified
package boundary is preserved; the local-file-only read path
emits a :class:`RawReadResult` carrying the wide-format
DataFrame under ``payload["wide_df"]`` for the transform layer
plus the staged metadata bundle.

The WGI unified path is local-file only (no network). The
``read_raw`` call passes ``year=None`` so the legacy reader
returns the full frame; the transform layer applies the request
year / country filters on the wide frame so the
request-scoping semantics stay in one place.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from leaders_db.sources.contracts import (
    RawAsset,
    RawReadResult,
    SourceIngestRequest,
)

from ._descriptor import (
    WORLD_BANK_WGI_DEFAULT_VERSION,
    WORLD_BANK_WGI_XLSX_NAME,
)
from ._transform import WORLD_BANK_WGI_XLSX_ASSET_ID


def _bundle_dir(request: SourceIngestRequest) -> Path:
    """Return the resolved ``<raw_root>/world_bank_wgi/`` bundle directory."""
    return Path(request.raw_root) / "world_bank_wgi"


def _xlsx_path(request: SourceIngestRequest) -> Path:
    """Return the request-scoped ``wgidataset.xlsx`` path."""
    return _bundle_dir(request) / WORLD_BANK_WGI_XLSX_NAME


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


def read_world_bank_wgi_xlsx(
    request: SourceIngestRequest,
) -> RawReadResult:
    """Open the staged ``wgidataset.xlsx`` and return the raw bundle.

    Lazy-imports the legacy reader so the unified package
    boundary is preserved. The wide-format DataFrame (one row
    per ``(iso3, year)`` with one column per catalog
    ``variable_name``) is carried in
    :attr:`RawReadResult.payload` under ``"wide_df"`` for the
    transform layer. The ``read_raw`` call passes ``year=None``
    so the legacy reader returns the full frame; the transform
    layer applies the request year filter on the wide frame so
    the request-scoping semantics stay in one place.

    The WGI unified path is local-file only (no network).
    """
    # Lazy import: keeps ``leaders_db.sources`` importable
    # without ``leaders_db.ingest`` (docs/architecture/sources.md
    # §10.1 + docs/requirements/sources.md §12 SRC-MIG-007).
    from leaders_db.ingest.wgi_xlsx import read_wgi

    xlsx_path = _xlsx_path(request)
    # Pass ``year=None`` so the legacy reader returns the
    # full wide-format frame; the transform layer applies
    # the request year filter + the request country
    # filter. This keeps the legacy reader's behaviour
    # intact while giving the new transform full control
    # over the request-scoping decisions.
    wide_df = read_wgi(xlsx_path=xlsx_path)
    metadata = _read_metadata_payload(_metadata_path(request))

    # Accept either canonical ``checksum_sha256`` or
    # legacy ``sha256`` -- the metadata shape for the
    # staged WGI bundle is documented in the brief.
    expected_sha = metadata.get("checksum_sha256")
    if not isinstance(expected_sha, str):
        expected_sha = metadata.get("sha256")
    if isinstance(expected_sha, str) and expected_sha.strip():
        actual_sha = hashlib.sha256(
            xlsx_path.read_bytes(),
        ).hexdigest()
        asset_checksum: str | None = (
            actual_sha
            if actual_sha.lower() == expected_sha.strip().lower()
            else None
        )
    else:
        asset_checksum = None

    # Carry the source URL / canonical page metadata onto
    # the RawAsset. The staged bundle carries both
    # ``source_url`` (canonical xlsx download) and
    # ``canonical_page`` (the user-facing WGI page); we
    # prefer ``canonical_page`` for the asset ``url``
    # because it is the canonical landing page.
    asset_url = None
    for candidate_key in ("canonical_page", "source_url"):
        candidate = metadata.get(candidate_key)
        if isinstance(candidate, str) and candidate.strip():
            asset_url = candidate.strip()
            break

    asset = RawAsset(
        asset_id=WORLD_BANK_WGI_XLSX_ASSET_ID,
        source_id=request.source_id,
        version=WORLD_BANK_WGI_DEFAULT_VERSION,
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        path=xlsx_path,
        url=asset_url,
        checksum_sha256=asset_checksum,
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
        },
        warnings=(),
    )


__all__ = [
    "_bundle_dir",
    "_metadata_path",
    "_read_metadata_payload",
    "_xlsx_path",
    "read_world_bank_wgi_xlsx",
]
