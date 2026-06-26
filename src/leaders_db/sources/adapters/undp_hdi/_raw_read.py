"""Raw CSV reader for UNDP HDI."""

from __future__ import annotations

from leaders_db.sources.contracts import RawAsset, RawReadResult, SourceIngestRequest

from ._constants import UNDP_HDI_CSV_ASSET_ID, UNDP_HDI_DEFAULT_VERSION
from ._readiness import csv_path, expected_checksum, metadata_path, read_metadata


def read_undp_hdi_csv_raw(request: SourceIngestRequest) -> RawReadResult:
    """Read the UNDP HDI CSV with the legacy parser via lazy imports."""
    from leaders_db.ingest.undp_hdi_csv import read_undp_hdi_csv
    from leaders_db.ingest.undp_hdi_io import load_undp_hdi_catalog
    from leaders_db.ingest.undp_hdi_unpivot import build_undp_hdi_observations

    path = csv_path(request)
    specs = load_undp_hdi_catalog()
    wide_frame = read_undp_hdi_csv(path, year=None)
    frame = build_undp_hdi_observations(wide_frame, year=None)
    metadata = read_metadata(metadata_path(request))
    asset = RawAsset(
        asset_id=UNDP_HDI_CSV_ASSET_ID,
        source_id=request.source_id,
        version=UNDP_HDI_DEFAULT_VERSION,
        media_type="text/csv",
        path=path,
        url=metadata.get("source_url"),
        checksum_sha256=expected_checksum(metadata),
        retrieved_at=None,
        immutable=True,
    )
    return RawReadResult(
        source_id=request.source_id,
        assets=(asset,),
        payload={"frame": frame, "metadata": metadata, "specs": specs},
    )


__all__ = ["read_undp_hdi_csv_raw"]
