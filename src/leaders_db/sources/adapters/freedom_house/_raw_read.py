"""Raw workbook reader for Freedom House FIW."""

from __future__ import annotations

from leaders_db.sources.contracts import RawAsset, RawReadResult, SourceIngestRequest

from ._constants import (
    FREEDOM_HOUSE_DEFAULT_VERSION,
    FREEDOM_HOUSE_RATING_SHEETS,
    FREEDOM_HOUSE_RATINGS_ASSET_ID,
)
from ._readiness import metadata_path, ratings_xlsx_path, read_metadata


def read_fiw_ratings_workbook(request: SourceIngestRequest) -> RawReadResult:
    """Read country and territory ratings sheets as headerless frames."""
    import pandas as pd

    path = ratings_xlsx_path(request)
    payload = {
        "metadata": read_metadata(metadata_path(request)),
        "frames": {
            sheet: pd.read_excel(path, sheet_name=sheet, header=None)
            for sheet in FREEDOM_HOUSE_RATING_SHEETS
        },
    }
    asset = RawAsset(
        asset_id=FREEDOM_HOUSE_RATINGS_ASSET_ID,
        source_id=request.source_id,
        version=FREEDOM_HOUSE_DEFAULT_VERSION,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        path=path,
        url=payload["metadata"].get("source_url"),
        checksum_sha256=None,
        retrieved_at=None,
        immutable=True,
    )
    return RawReadResult(source_id=request.source_id, assets=(asset,), payload=payload)


__all__ = ["read_fiw_ratings_workbook"]
