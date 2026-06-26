"""Readiness checks for the clean SIPRI Milex adapter."""

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
    SIPRI_MILEX_CHECKSUM_MISMATCH,
    SIPRI_MILEX_COVERAGE_END_YEAR,
    SIPRI_MILEX_COVERAGE_START_YEAR,
    SIPRI_MILEX_DEFAULT_VERSION,
    SIPRI_MILEX_LOCAL_FILES_INVALID,
    SIPRI_MILEX_METADATA_NAME,
    SIPRI_MILEX_METADATA_VERSION_MISMATCH,
    SIPRI_MILEX_SOURCE_KEY,
    SIPRI_MILEX_UNSUPPORTED_VERSION,
    SIPRI_MILEX_XLSX_NAME,
)


def bundle_dir(request: SourceIngestRequest) -> Path:
    return Path(request.raw_root) / SIPRI_MILEX_SOURCE_KEY


def metadata_path(request: SourceIngestRequest) -> Path:
    return bundle_dir(request) / SIPRI_MILEX_METADATA_NAME


def xlsx_path(request: SourceIngestRequest) -> Path:
    return bundle_dir(request) / SIPRI_MILEX_XLSX_NAME


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
        return f"SIPRI Milex metadata.json is missing at {path}", MISSING_METADATA
    payload = read_metadata(path)
    if not payload:
        return f"SIPRI Milex metadata.json is not parseable at {path}", MISSING_METADATA
    version = str(payload.get("source_version", "")).strip()
    if version != SIPRI_MILEX_DEFAULT_VERSION:
        return (
            "SIPRI Milex metadata source_version must be "
            f"{SIPRI_MILEX_DEFAULT_VERSION!r}; got {version!r}",
            SIPRI_MILEX_METADATA_VERSION_MISMATCH,
        )
    local_files = payload.get("local_files")
    if not isinstance(local_files, list) or not local_files or not all(
        isinstance(item, str) and item.strip() for item in local_files
    ):
        return (
            "SIPRI Milex metadata local_files must be a non-empty string list",
            SIPRI_MILEX_LOCAL_FILES_INVALID,
        )
    if SIPRI_MILEX_XLSX_NAME not in local_files:
        return (
            "SIPRI Milex metadata local_files must include the canonical xlsx "
            f"file {SIPRI_MILEX_XLSX_NAME!r}",
            SIPRI_MILEX_LOCAL_FILES_INVALID,
        )
    return None


def file_blocker(request: SourceIngestRequest) -> tuple[str, str] | None:
    path = xlsx_path(request)
    if not path.is_file():
        return f"SIPRI Milex xlsx file is missing at {path}", MISSING_RAW
    metadata = read_metadata(metadata_path(request))
    checksums = metadata.get("checksum_sha256")
    if isinstance(checksums, dict):
        expected = checksums.get(SIPRI_MILEX_XLSX_NAME)
        if isinstance(expected, str) and expected.strip():
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual.lower() != expected.strip().lower():
                return (
                    f"SIPRI Milex xlsx checksum mismatch for {SIPRI_MILEX_XLSX_NAME}",
                    SIPRI_MILEX_CHECKSUM_MISMATCH,
                )
    return None


def version_blocker(request: SourceIngestRequest) -> tuple[str, str] | None:
    if request.source_version in (None, SIPRI_MILEX_DEFAULT_VERSION):
        return None
    return (
        "SIPRI Milex request source_version must be "
        f"{SIPRI_MILEX_DEFAULT_VERSION!r}; got {request.source_version!r}",
        SIPRI_MILEX_UNSUPPORTED_VERSION,
    )


def request_warnings(request: SourceIngestRequest) -> tuple[SourceWarning, ...]:
    warnings: list[SourceWarning] = []
    if request.leaders:
        warnings.append(
            SourceWarning(
                code=UNSUPPORTED_FILTER,
                message=(
                    "SIPRI Milex clean adapter does not apply leader filters; "
                    "the source is country-year military expenditure data."
                ),
                severity="warning",
                source_id=request.source_id,
                context={"requested_leaders": list(request.leaders)},
            ),
        )
    for year in request.years or ():
        year_int = int(year)
        if (
            year_int < SIPRI_MILEX_COVERAGE_START_YEAR
            or year_int > SIPRI_MILEX_COVERAGE_END_YEAR
        ):
            warnings.append(
                SourceWarning(
                    code=YEAR_ABSENT,
                    message=(
                        f"year={year_int} is outside SIPRI Milex coverage "
                        f"({SIPRI_MILEX_COVERAGE_START_YEAR}-"
                        f"{SIPRI_MILEX_COVERAGE_END_YEAR}); no observations "
                        "will be emitted for this year."
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
