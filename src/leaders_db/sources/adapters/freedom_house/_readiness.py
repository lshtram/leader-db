"""Readiness checks for the Freedom House FIW adapter."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from leaders_db.sources.contracts import SourceIngestRequest, SourceWarning
from leaders_db.sources.warnings import (
    MISSING_METADATA,
    MISSING_RAW,
    UNSUPPORTED_FILTER,
    YEAR_ABSENT,
)

from ._constants import (
    FREEDOM_HOUSE_CHECKSUM_MISMATCH,
    FREEDOM_HOUSE_COVERAGE_END_YEAR,
    FREEDOM_HOUSE_COVERAGE_START_YEAR,
    FREEDOM_HOUSE_DEFAULT_VERSION,
    FREEDOM_HOUSE_LOCAL_FILES_INVALID,
    FREEDOM_HOUSE_METADATA_NAME,
    FREEDOM_HOUSE_METADATA_VERSION_MISMATCH,
    FREEDOM_HOUSE_RATINGS_XLSX_NAME,
    FREEDOM_HOUSE_SOURCE_KEY,
    FREEDOM_HOUSE_UNSUPPORTED_VERSION,
)


def bundle_dir(request: SourceIngestRequest) -> Path:
    return Path(request.raw_root) / FREEDOM_HOUSE_SOURCE_KEY


def metadata_path(request: SourceIngestRequest) -> Path:
    return bundle_dir(request) / FREEDOM_HOUSE_METADATA_NAME


def ratings_xlsx_path(request: SourceIngestRequest) -> Path:
    return bundle_dir(request) / FREEDOM_HOUSE_RATINGS_XLSX_NAME


def read_metadata(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def metadata_blocker(request: SourceIngestRequest) -> tuple[str, str] | None:
    path = metadata_path(request)
    if not path.is_file():
        return f"Freedom House metadata.json is missing at {path}", MISSING_METADATA
    payload = read_metadata(path)
    if not payload:
        return f"Freedom House metadata.json is not parseable at {path}", MISSING_METADATA
    version = str(payload.get("source_version", "")).strip()
    if version != FREEDOM_HOUSE_DEFAULT_VERSION:
        return (
            "Freedom House metadata source_version must be "
            f"{FREEDOM_HOUSE_DEFAULT_VERSION!r}; got {version!r}",
            FREEDOM_HOUSE_METADATA_VERSION_MISMATCH,
        )
    local_files = payload.get("local_files")
    if not isinstance(local_files, list) or not all(
        isinstance(x, str) for x in local_files
    ):
        return (
            "Freedom House metadata local_files must be a non-empty string list",
            FREEDOM_HOUSE_LOCAL_FILES_INVALID,
        )
    if FREEDOM_HOUSE_RATINGS_XLSX_NAME not in local_files:
        return (
            "Freedom House metadata local_files must include the canonical "
            f"2026 ratings workbook {FREEDOM_HOUSE_RATINGS_XLSX_NAME!r}",
            FREEDOM_HOUSE_LOCAL_FILES_INVALID,
        )
    return None


def file_blocker(request: SourceIngestRequest) -> tuple[str, str] | None:
    path = ratings_xlsx_path(request)
    if not path.is_file():
        return f"Freedom House ratings workbook is missing at {path}", MISSING_RAW
    metadata = read_metadata(metadata_path(request))
    checksums = metadata.get("checksum_sha256")
    if isinstance(checksums, dict):
        expected = checksums.get(FREEDOM_HOUSE_RATINGS_XLSX_NAME)
        if isinstance(expected, str) and expected.strip():
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual.lower() != expected.strip().lower():
                return (
                    "Freedom House ratings workbook checksum mismatch for "
                    f"{FREEDOM_HOUSE_RATINGS_XLSX_NAME}",
                    FREEDOM_HOUSE_CHECKSUM_MISMATCH,
                )
    return None


def version_blocker(request: SourceIngestRequest) -> tuple[str, str] | None:
    if request.source_version in (None, FREEDOM_HOUSE_DEFAULT_VERSION):
        return None
    return (
        "Freedom House request source_version must be "
        f"{FREEDOM_HOUSE_DEFAULT_VERSION!r}; got {request.source_version!r}",
        FREEDOM_HOUSE_UNSUPPORTED_VERSION,
    )


def request_warnings(request: SourceIngestRequest) -> tuple[SourceWarning, ...]:
    warnings: list[SourceWarning] = []
    if request.leaders:
        warnings.append(
            SourceWarning(
                code=UNSUPPORTED_FILTER,
                message=(
                    "Freedom House FIW is country/territory-year data; "
                    "leader filters are ignored."
                ),
                severity="warning",
                source_id=request.source_id,
                context={"requested_leaders": list(request.leaders)},
            ),
        )
    for year in request.years or ():
        year_int = int(year)
        if (
            year_int < FREEDOM_HOUSE_COVERAGE_START_YEAR
            or year_int > FREEDOM_HOUSE_COVERAGE_END_YEAR
        ):
            warnings.append(
                SourceWarning(
                    code=YEAR_ABSENT,
                    message=(
                        f"year={year_int} is outside Freedom House FIW coverage "
                        f"({FREEDOM_HOUSE_COVERAGE_START_YEAR}-{FREEDOM_HOUSE_COVERAGE_END_YEAR}); "
                        "no observations will be emitted for this year."
                    ),
                    severity="warning",
                    source_id=request.source_id,
                    context={"year": year_int},
                ),
            )
    return tuple(warnings)


__all__ = [
    "bundle_dir",
    "file_blocker",
    "metadata_blocker",
    "metadata_path",
    "ratings_xlsx_path",
    "read_metadata",
    "request_warnings",
    "version_blocker",
]
