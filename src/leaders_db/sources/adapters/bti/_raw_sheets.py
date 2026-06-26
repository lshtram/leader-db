"""BTI workbook sheet selection and multi-sheet reads."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from leaders_db.sources.contracts import SourceIngestRequest


def read_requested_sheets(
    request: SourceIngestRequest,
    xlsx_path: Path,
    legacy_read_bti: Any,
) -> Any:
    """Read every workbook sheet required by ``request``.

    ``years=None`` means every available BTI sheet in the workbook.
    Explicit ``years=`` requests are resolved to their BTI edition sheets;
    out-of-coverage years are skipped here because readiness already carries
    the structured warning and transform should emit zero rows for them.
    """
    sheet_names = _sheet_names_for_request(request, xlsx_path)
    if not sheet_names:
        return _empty_wide_frame()

    frames = []
    raw_frames = []
    for sheet_name in sheet_names:
        frame = legacy_read_bti(
            xlsx_path=xlsx_path,
            sheet_name=sheet_name,
        )
        frame = frame.copy()
        raw_long = frame.attrs.get("_bti_raw_long")
        frame.attrs = {}
        frame["bti_sheet_name"] = sheet_name
        frames.append(frame)
        if raw_long is not None:
            raw_frames.append(raw_long)

    if not frames:
        return _empty_wide_frame()

    wide_df = pd.concat(frames, ignore_index=True)
    if raw_frames:
        wide_df.attrs["_bti_raw_long"] = pd.concat(
            raw_frames, ignore_index=True,
        )
    wide_df.attrs["_bti_sheet_name"] = sheet_names[-1]
    wide_df.attrs["_bti_sheet_names"] = tuple(sheet_names)
    return wide_df


def _sheet_names_for_request(
    request: SourceIngestRequest,
    xlsx_path: Path,
) -> tuple[str, ...]:
    if request.years:
        return _requested_year_sheets(request.years)
    return _available_bti_sheets(xlsx_path)


def _requested_year_sheets(years: tuple[int, ...]) -> tuple[str, ...]:
    from leaders_db.ingest.bti_io import sheet_for_year

    sheet_names: list[str] = []
    seen: set[str] = set()
    for year in years:
        try:
            sheet_name = sheet_for_year(int(year))
        except ValueError:
            continue
        if sheet_name not in seen:
            sheet_names.append(sheet_name)
            seen.add(sheet_name)
    return tuple(sheet_names)


def _available_bti_sheets(xlsx_path: Path) -> tuple[str, ...]:
    import openpyxl

    from leaders_db.ingest.bti_io import target_year_for_sheet

    wb = openpyxl.load_workbook(
        xlsx_path, read_only=True, data_only=True,
    )
    try:
        return tuple(
            name for name in wb.sheetnames
            if isinstance(name, str)
            and name.startswith("BTI ")
            and target_year_for_sheet(name) is not None
        )
    finally:
        wb.close()


def _empty_wide_frame() -> Any:
    wide_df = pd.DataFrame(columns=["country", "year", "bti_sheet_name"])
    wide_df.attrs["_bti_raw_long"] = pd.DataFrame(
        columns=["country", "year", "variable_name", "value"],
    )
    wide_df.attrs["_bti_sheet_names"] = ()
    return wide_df


__all__ = ["read_requested_sheets"]
