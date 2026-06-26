"""Readiness checks for the clean CIRIGHTS adapter."""

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
    CIRIGHTS_CHECKSUM_MISMATCH,
    CIRIGHTS_COVERAGE_END_YEAR,
    CIRIGHTS_COVERAGE_START_YEAR,
    CIRIGHTS_DEFAULT_VERSION,
    CIRIGHTS_LOCAL_FILES_INVALID,
    CIRIGHTS_METADATA_NAME,
    CIRIGHTS_METADATA_VERSION_MISMATCH,
    CIRIGHTS_PROXY_REQUESTED_YEAR,
    CIRIGHTS_PROXY_YEAR,
    CIRIGHTS_SOURCE_KEY,
    CIRIGHTS_UNSUPPORTED_VERSION,
    CIRIGHTS_XLSX_NAME,
)


def bundle_dir(request: SourceIngestRequest) -> Path:
    return Path(request.raw_root) / CIRIGHTS_SOURCE_KEY


def metadata_path(request: SourceIngestRequest) -> Path:
    return bundle_dir(request) / CIRIGHTS_METADATA_NAME


def xlsx_path(request: SourceIngestRequest) -> Path:
    return bundle_dir(request) / CIRIGHTS_XLSX_NAME


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
        return f"CIRIGHTS metadata.json is missing at {path}", MISSING_METADATA
    payload = read_metadata(path)
    if not payload:
        return f"CIRIGHTS metadata.json is not parseable at {path}", MISSING_METADATA
    version = str(payload.get("source_version", "")).strip()
    if version != CIRIGHTS_DEFAULT_VERSION:
        return (
            "CIRIGHTS metadata source_version must be "
            f"{CIRIGHTS_DEFAULT_VERSION!r}; got {version!r}",
            CIRIGHTS_METADATA_VERSION_MISMATCH,
        )
    local_files = payload.get("local_files")
    if not isinstance(local_files, list) or not local_files or not all(
        isinstance(item, str) and item.strip() for item in local_files
    ):
        return (
            "CIRIGHTS metadata local_files must be a non-empty string list",
            CIRIGHTS_LOCAL_FILES_INVALID,
        )
    if CIRIGHTS_XLSX_NAME not in local_files:
        return (
            "CIRIGHTS metadata local_files must include the canonical xlsx "
            f"{CIRIGHTS_XLSX_NAME!r}",
            CIRIGHTS_LOCAL_FILES_INVALID,
        )
    return None


def file_blocker(request: SourceIngestRequest) -> tuple[str, str] | None:
    path = xlsx_path(request)
    if not path.is_file():
        return f"CIRIGHTS xlsx is missing at {path}", MISSING_RAW
    checksums = read_metadata(metadata_path(request)).get("checksum_sha256")
    if isinstance(checksums, dict):
        expected = checksums.get(CIRIGHTS_XLSX_NAME)
        if isinstance(expected, str) and expected.strip():
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual.lower() != expected.strip().lower():
                return (
                    f"CIRIGHTS xlsx checksum mismatch for {CIRIGHTS_XLSX_NAME}",
                    CIRIGHTS_CHECKSUM_MISMATCH,
                )
    return None


def version_blocker(request: SourceIngestRequest) -> tuple[str, str] | None:
    if request.source_version in (None, CIRIGHTS_DEFAULT_VERSION):
        return None
    return (
        "CIRIGHTS request source_version must be "
        f"{CIRIGHTS_DEFAULT_VERSION!r}; got {request.source_version!r}",
        CIRIGHTS_UNSUPPORTED_VERSION,
    )


def request_warnings(request: SourceIngestRequest) -> tuple[SourceWarning, ...]:
    warnings: list[SourceWarning] = []
    if request.leaders:
        warnings.append(
            SourceWarning(
                code=UNSUPPORTED_FILTER,
                message="CIRIGHTS is country-year data; leader filters are ignored.",
                severity="warning",
                source_id=request.source_id,
                context={"requested_leaders": list(request.leaders)},
            ),
        )
    for year in request.years or ():
        year_int = int(year)
        if year_int == CIRIGHTS_PROXY_REQUESTED_YEAR:
            warnings.append(
                SourceWarning(
                    code=YEAR_ABSENT,
                    message=(
                        f"year={year_int} is outside CIRIGHTS coverage "
                        f"({CIRIGHTS_COVERAGE_START_YEAR}-{CIRIGHTS_COVERAGE_END_YEAR}); "
                        f"using {CIRIGHTS_PROXY_YEAR} as a one-year proxy."
                    ),
                    severity="warning",
                    source_id=request.source_id,
                    context={"requested_year": year_int, "proxy_year": CIRIGHTS_PROXY_YEAR},
                ),
            )
        elif year_int < CIRIGHTS_COVERAGE_START_YEAR or year_int > CIRIGHTS_COVERAGE_END_YEAR:
            warnings.append(
                SourceWarning(
                    code=YEAR_ABSENT,
                    message=(
                        f"year={year_int} is outside CIRIGHTS coverage "
                        f"({CIRIGHTS_COVERAGE_START_YEAR}-{CIRIGHTS_COVERAGE_END_YEAR}); "
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
    "read_metadata",
    "request_warnings",
    "version_blocker",
    "xlsx_path",
]
