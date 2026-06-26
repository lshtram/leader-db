"""Raw PDF reader for the clean SIPRI Yearbook Ch.7 adapter."""

from __future__ import annotations

from leaders_db.sources.contracts import RawAsset, RawReadResult, SourceIngestRequest

from ._constants import (
    SIPRI_YEARBOOK_CH7_DEFAULT_VERSION,
    SIPRI_YEARBOOK_CH7_PDF_ASSET_ID,
)
from ._readiness import metadata_path, pdf_path, read_metadata


def read_sipri_yearbook_ch7_pdf(request: SourceIngestRequest) -> RawReadResult:
    """Read the staged SIPRI Yearbook Ch.7 PDF through the legacy parser.

    The imports from ``leaders_db.ingest`` are intentionally local so importing
    ``leaders_db.sources.adapters.sipri_yearbook_ch7`` does not import legacy
    ingest.
    """
    from leaders_db.ingest.sipri_yearbook_ch7_io import (
        load_indicator_catalog,
        read_sipri_yearbook_ch7,
    )

    path = pdf_path(request)
    metadata = read_metadata(metadata_path(request))
    frame = read_sipri_yearbook_ch7(year=None, pdf_path=path)
    specs = load_indicator_catalog()
    checksum = metadata.get("checksum_sha256")
    checksum_value = None
    if isinstance(checksum, dict):
        raw_checksum = checksum.get(path.name)
        if isinstance(raw_checksum, str):
            checksum_value = raw_checksum
    asset = RawAsset(
        asset_id=SIPRI_YEARBOOK_CH7_PDF_ASSET_ID,
        source_id=request.source_id,
        version=SIPRI_YEARBOOK_CH7_DEFAULT_VERSION,
        media_type="application/pdf",
        path=path,
        url=metadata.get("source_url"),
        checksum_sha256=checksum_value,
        retrieved_at=None,
        immutable=True,
    )
    payload = {"frame": frame, "metadata": metadata, "specs": specs}
    return RawReadResult(source_id=request.source_id, assets=(asset,), payload=payload)


__all__ = ["read_sipri_yearbook_ch7_pdf"]
