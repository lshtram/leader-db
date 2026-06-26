"""Raw Stata reader for the clean Archigos adapter."""

from __future__ import annotations

from leaders_db.sources.contracts import RawAsset, RawReadResult, SourceIngestRequest

from ._constants import ARCHIGOS_DEFAULT_VERSION, ARCHIGOS_DTA_ASSET_ID
from ._readiness import dta_path, metadata_path, read_metadata


def read_archigos_dta(request: SourceIngestRequest) -> RawReadResult:
    """Read the staged Archigos Stata file through the legacy parser.

    The imports from ``leaders_db.ingest`` are intentionally inside this
    function so importing ``leaders_db.sources.adapters.archigos`` preserves the
    clean source-system boundary.
    """
    from leaders_db.ingest.archigos_io import load_archigos_catalog, read_archigos

    path = dta_path(request)
    metadata = read_metadata(metadata_path(request))
    frame = read_archigos(dta_path=path)
    specs = load_archigos_catalog()
    checksum = metadata.get("checksum_sha256")
    checksum_value = None
    if isinstance(checksum, dict):
        raw_checksum = checksum.get(path.name)
        if isinstance(raw_checksum, str):
            checksum_value = raw_checksum
    asset = RawAsset(
        asset_id=ARCHIGOS_DTA_ASSET_ID,
        source_id=request.source_id,
        version=ARCHIGOS_DEFAULT_VERSION,
        media_type="application/x-stata-dta",
        path=path,
        url=metadata.get("source_url"),
        checksum_sha256=checksum_value,
        retrieved_at=None,
        immutable=True,
    )
    payload = {"frame": frame, "metadata": metadata, "specs": specs}
    return RawReadResult(source_id=request.source_id, assets=(asset,), payload=payload)


__all__ = ["read_archigos_dta"]
