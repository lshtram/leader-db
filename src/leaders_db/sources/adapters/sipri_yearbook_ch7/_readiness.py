"""Readiness checks for the clean SIPRI Yearbook Ch.7 adapter."""

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
    SIPRI_YEARBOOK_CH7_CHECKSUM_MISMATCH,
    SIPRI_YEARBOOK_CH7_COVERAGE_END_YEAR,
    SIPRI_YEARBOOK_CH7_COVERAGE_START_YEAR,
    SIPRI_YEARBOOK_CH7_DEFAULT_VERSION,
    SIPRI_YEARBOOK_CH7_LOCAL_FILES_INVALID,
    SIPRI_YEARBOOK_CH7_METADATA_NAME,
    SIPRI_YEARBOOK_CH7_METADATA_VERSION_MISMATCH,
    SIPRI_YEARBOOK_CH7_PDF_NAME,
    SIPRI_YEARBOOK_CH7_SOURCE_KEY,
    SIPRI_YEARBOOK_CH7_UNSUPPORTED_VERSION,
)


def bundle_dir(request: SourceIngestRequest) -> Path:
    return Path(request.raw_root) / SIPRI_YEARBOOK_CH7_SOURCE_KEY


def metadata_path(request: SourceIngestRequest) -> Path:
    return bundle_dir(request) / SIPRI_YEARBOOK_CH7_METADATA_NAME


def pdf_path(request: SourceIngestRequest) -> Path:
    return bundle_dir(request) / SIPRI_YEARBOOK_CH7_PDF_NAME


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
        return f"SIPRI Yearbook Ch.7 metadata.json is missing at {path}", MISSING_METADATA
    payload = read_metadata(path)
    if not payload:
        return f"SIPRI Yearbook Ch.7 metadata.json is not parseable at {path}", MISSING_METADATA
    version = str(payload.get("source_version", "")).strip()
    if version != SIPRI_YEARBOOK_CH7_DEFAULT_VERSION:
        return (
            "SIPRI Yearbook Ch.7 metadata source_version must be "
            f"{SIPRI_YEARBOOK_CH7_DEFAULT_VERSION!r}; got {version!r}",
            SIPRI_YEARBOOK_CH7_METADATA_VERSION_MISMATCH,
        )
    local_files = payload.get("local_files")
    if not isinstance(local_files, list) or not local_files or not all(
        isinstance(item, str) and item.strip() for item in local_files
    ):
        return (
            "SIPRI Yearbook Ch.7 metadata local_files must be a non-empty string list",
            SIPRI_YEARBOOK_CH7_LOCAL_FILES_INVALID,
        )
    if SIPRI_YEARBOOK_CH7_PDF_NAME not in local_files:
        return (
            "SIPRI Yearbook Ch.7 metadata local_files must include the "
            f"canonical PDF file {SIPRI_YEARBOOK_CH7_PDF_NAME!r}",
            SIPRI_YEARBOOK_CH7_LOCAL_FILES_INVALID,
        )
    return None


def file_blocker(request: SourceIngestRequest) -> tuple[str, str] | None:
    path = pdf_path(request)
    if not path.is_file():
        return f"SIPRI Yearbook Ch.7 PDF file is missing at {path}", MISSING_RAW
    metadata = read_metadata(metadata_path(request))
    checksums = metadata.get("checksum_sha256")
    if isinstance(checksums, dict):
        expected = checksums.get(SIPRI_YEARBOOK_CH7_PDF_NAME)
        if isinstance(expected, str) and expected.strip():
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual.lower() != expected.strip().lower():
                return (
                    "SIPRI Yearbook Ch.7 PDF checksum mismatch for "
                    f"{SIPRI_YEARBOOK_CH7_PDF_NAME}",
                    SIPRI_YEARBOOK_CH7_CHECKSUM_MISMATCH,
                )
    return None


def version_blocker(request: SourceIngestRequest) -> tuple[str, str] | None:
    if request.source_version in (None, SIPRI_YEARBOOK_CH7_DEFAULT_VERSION):
        return None
    return (
        "SIPRI Yearbook Ch.7 request source_version must be "
        f"{SIPRI_YEARBOOK_CH7_DEFAULT_VERSION!r}; got {request.source_version!r}",
        SIPRI_YEARBOOK_CH7_UNSUPPORTED_VERSION,
    )


def request_warnings(request: SourceIngestRequest) -> tuple[SourceWarning, ...]:
    warnings: list[SourceWarning] = []
    if request.leaders:
        warnings.append(
            SourceWarning(
                code=UNSUPPORTED_FILTER,
                message=(
                    "SIPRI Yearbook Ch.7 clean adapter does not apply leader "
                    "filters; the source is nuclear country-year snapshot data."
                ),
                severity="warning",
                source_id=request.source_id,
                context={"requested_leaders": list(request.leaders)},
            ),
        )
    for year in request.years or ():
        year_int = int(year)
        if (
            year_int < SIPRI_YEARBOOK_CH7_COVERAGE_START_YEAR
            or year_int > SIPRI_YEARBOOK_CH7_COVERAGE_END_YEAR
        ):
            warnings.append(
                SourceWarning(
                    code=YEAR_ABSENT,
                    message=(
                        f"year={year_int} is outside SIPRI Yearbook Ch.7 "
                        f"snapshot coverage ({SIPRI_YEARBOOK_CH7_COVERAGE_START_YEAR}); "
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
    "pdf_path",
    "read_metadata",
    "request_warnings",
    "version_blocker",
]
