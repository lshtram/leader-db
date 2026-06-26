"""Raw CSV reader for the clean REIGN adapter."""

from __future__ import annotations

from leaders_db.sources.contracts import RawAsset, RawReadResult, SourceIngestRequest

from ._constants import REIGN_CSV_ASSET_ID, REIGN_DEFAULT_VERSION
from ._readiness import csv_path, metadata_path, read_metadata


def read_reign_csv(request: SourceIngestRequest) -> RawReadResult:
    """Read the staged REIGN CSV through the legacy parser.

    The imports from ``leaders_db.ingest`` are intentionally local so importing
    ``leaders_db.sources.adapters.reign`` does not import legacy ingest.
    """
    from leaders_db.ingest.reign_io import load_reign_catalog, read_reign

    path = csv_path(request)
    metadata = read_metadata(metadata_path(request))
    frame = read_reign(csv_path=path, year=None)
    specs = load_reign_catalog()
    checksum = metadata.get("checksum_sha256")
    checksum_value = None
    if isinstance(checksum, dict):
        raw_checksum = checksum.get(path.name)
        if isinstance(raw_checksum, str):
            checksum_value = raw_checksum
    asset = RawAsset(
        asset_id=REIGN_CSV_ASSET_ID,
        source_id=request.source_id,
        version=REIGN_DEFAULT_VERSION,
        media_type="text/csv",
        path=path,
        url=metadata.get("source_url"),
        checksum_sha256=checksum_value,
        retrieved_at=None,
        immutable=True,
    )
    payload = {"frame": frame, "metadata": metadata, "specs": specs}
    return RawReadResult(source_id=request.source_id, assets=(asset,), payload=payload)


__all__ = ["read_reign_csv"]
