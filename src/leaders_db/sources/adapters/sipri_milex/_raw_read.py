"""Raw xlsx reader for the clean SIPRI Milex adapter."""

from __future__ import annotations

from leaders_db.sources.contracts import RawAsset, RawReadResult, SourceIngestRequest

from ._constants import (
    SIPRI_MILEX_DEFAULT_VERSION,
    SIPRI_MILEX_XLSX_ASSET_ID,
)
from ._readiness import metadata_path, read_metadata, xlsx_path


def read_sipri_milex_xlsx(request: SourceIngestRequest) -> RawReadResult:
    """Read the staged SIPRI Milex xlsx through the legacy parser.

    The imports from ``leaders_db.ingest`` are intentionally local so importing
    ``leaders_db.sources.adapters.sipri_milex`` does not import legacy ingest.
    """
    from leaders_db.ingest.sipri_milex_io import load_indicator_catalog
    from leaders_db.ingest.sipri_milex_xlsx import read_sipri_milex

    path = xlsx_path(request)
    metadata = read_metadata(metadata_path(request))
    frame = read_sipri_milex(year=None, xlsx_path=path)
    specs = load_indicator_catalog()
    checksum = metadata.get("checksum_sha256")
    checksum_value = None
    if isinstance(checksum, dict):
        raw_checksum = checksum.get(path.name)
        if isinstance(raw_checksum, str):
            checksum_value = raw_checksum
    asset = RawAsset(
        asset_id=SIPRI_MILEX_XLSX_ASSET_ID,
        source_id=request.source_id,
        version=SIPRI_MILEX_DEFAULT_VERSION,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        path=path,
        url=metadata.get("source_url"),
        checksum_sha256=checksum_value,
        retrieved_at=None,
        immutable=True,
    )
    payload = {"frame": frame, "metadata": metadata, "specs": specs}
    return RawReadResult(source_id=request.source_id, assets=(asset,), payload=payload)


__all__ = ["read_sipri_milex_xlsx"]
