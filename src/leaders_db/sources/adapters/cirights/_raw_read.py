"""Raw xlsx reader for CIRIGHTS."""

from __future__ import annotations

from leaders_db.sources.contracts import RawAsset, RawReadResult, SourceIngestRequest

from ._constants import CIRIGHTS_DEFAULT_VERSION, CIRIGHTS_XLSX_ASSET_ID
from ._readiness import metadata_path, read_metadata, xlsx_path


def read_cirights_xlsx(request: SourceIngestRequest) -> RawReadResult:
    """Read the CIRIGHTS workbook with the legacy parser via lazy imports."""
    from leaders_db.ingest.cirights_io import load_indicator_catalog
    from leaders_db.ingest.cirights_xlsx import read_xlsx_to_wide_dataframe

    path = xlsx_path(request)
    specs = load_indicator_catalog()
    years = _data_years(request.years)
    frames = [read_xlsx_to_wide_dataframe(path, specs, year=year) for year in years]
    if request.years is None:
        frame = read_xlsx_to_wide_dataframe(path, specs, year=None)
    elif frames:
        frame = _concat_frames(frames)
    else:
        frame = read_xlsx_to_wide_dataframe(path, specs, year=0)
    metadata = read_metadata(metadata_path(request))
    asset = RawAsset(
        asset_id=CIRIGHTS_XLSX_ASSET_ID,
        source_id=request.source_id,
        version=CIRIGHTS_DEFAULT_VERSION,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        path=path,
        url=metadata.get("source_url"),
        checksum_sha256=_xlsx_checksum(metadata),
        retrieved_at=None,
        immutable=True,
    )
    return RawReadResult(
        source_id=request.source_id,
        assets=(asset,),
        payload={"frame": frame, "metadata": metadata, "specs": specs},
    )


def _data_years(years: tuple[int, ...] | None) -> tuple[int, ...]:
    from ._constants import (
        CIRIGHTS_COVERAGE_END_YEAR,
        CIRIGHTS_COVERAGE_START_YEAR,
        CIRIGHTS_PROXY_REQUESTED_YEAR,
        CIRIGHTS_PROXY_YEAR,
    )

    if years is None:
        return ()
    data_years: list[int] = []
    for year in years:
        year_int = int(year)
        if year_int == CIRIGHTS_PROXY_REQUESTED_YEAR:
            year_int = CIRIGHTS_PROXY_YEAR
        if CIRIGHTS_COVERAGE_START_YEAR <= year_int <= CIRIGHTS_COVERAGE_END_YEAR:
            data_years.append(year_int)
    return tuple(sorted(set(data_years)))


def _concat_frames(frames):
    import pandas as pd

    frame = pd.concat(frames, ignore_index=True)
    raw_lookup = {}
    starts: list[int] = []
    ends: list[int] = []
    for one_frame in frames:
        raw_lookup.update(one_frame.attrs.get("_cirights_raw_lookup", {}) or {})
        start, end = one_frame.attrs.get("year_window", (0, 0))
        if start:
            starts.append(int(start))
        if end:
            ends.append(int(end))
    frame.attrs["_cirights_raw_lookup"] = raw_lookup
    frame.attrs["year_window"] = (min(starts), max(ends)) if starts and ends else (0, 0)
    return frame


def _xlsx_checksum(metadata: dict[str, object]) -> str | None:
    from ._constants import CIRIGHTS_XLSX_NAME

    checksums = metadata.get("checksum_sha256")
    if not isinstance(checksums, dict):
        return None
    value = checksums.get(CIRIGHTS_XLSX_NAME)
    return value if isinstance(value, str) and value.strip() else None


__all__ = ["read_cirights_xlsx"]
