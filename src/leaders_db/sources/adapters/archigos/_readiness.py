"""Readiness checks for the clean Archigos adapter."""

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
    ARCHIGOS_CHECKSUM_MISMATCH,
    ARCHIGOS_COVERAGE_END_YEAR,
    ARCHIGOS_COVERAGE_START_YEAR,
    ARCHIGOS_DEFAULT_VERSION,
    ARCHIGOS_DTA_NAME,
    ARCHIGOS_LOCAL_FILES_INVALID,
    ARCHIGOS_METADATA_NAME,
    ARCHIGOS_METADATA_VERSION_MISMATCH,
    ARCHIGOS_SOURCE_KEY,
    ARCHIGOS_UNSUPPORTED_VERSION,
)


def bundle_dir(request: SourceIngestRequest) -> Path:
    return Path(request.raw_root) / ARCHIGOS_SOURCE_KEY


def metadata_path(request: SourceIngestRequest) -> Path:
    return bundle_dir(request) / ARCHIGOS_METADATA_NAME


def dta_path(request: SourceIngestRequest) -> Path:
    return bundle_dir(request) / ARCHIGOS_DTA_NAME


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
        return f"Archigos metadata.json is missing at {path}", MISSING_METADATA
    payload = read_metadata(path)
    if not payload:
        return f"Archigos metadata.json is not parseable at {path}", MISSING_METADATA
    version = str(payload.get("source_version", "")).strip()
    if version != ARCHIGOS_DEFAULT_VERSION:
        return (
            "Archigos metadata source_version must be "
            f"{ARCHIGOS_DEFAULT_VERSION!r}; got {version!r}",
            ARCHIGOS_METADATA_VERSION_MISMATCH,
        )
    local_files = payload.get("local_files")
    if not isinstance(local_files, list) or not local_files or not all(
        isinstance(item, str) and item.strip() for item in local_files
    ):
        return (
            "Archigos metadata local_files must be a non-empty string list",
            ARCHIGOS_LOCAL_FILES_INVALID,
        )
    if ARCHIGOS_DTA_NAME not in local_files:
        return (
            "Archigos metadata local_files must include the canonical Stata "
            f"file {ARCHIGOS_DTA_NAME!r}",
            ARCHIGOS_LOCAL_FILES_INVALID,
        )
    return None


def file_blocker(request: SourceIngestRequest) -> tuple[str, str] | None:
    path = dta_path(request)
    if not path.is_file():
        return f"Archigos Stata file is missing at {path}", MISSING_RAW
    metadata = read_metadata(metadata_path(request))
    checksums = metadata.get("checksum_sha256")
    if isinstance(checksums, dict):
        expected = checksums.get(ARCHIGOS_DTA_NAME)
        if isinstance(expected, str) and expected.strip():
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual.lower() != expected.strip().lower():
                return (
                    f"Archigos Stata file checksum mismatch for {ARCHIGOS_DTA_NAME}",
                    ARCHIGOS_CHECKSUM_MISMATCH,
                )
    return None


def version_blocker(request: SourceIngestRequest) -> tuple[str, str] | None:
    if request.source_version in (None, ARCHIGOS_DEFAULT_VERSION):
        return None
    return (
        "Archigos request source_version must be "
        f"{ARCHIGOS_DEFAULT_VERSION!r}; got {request.source_version!r}",
        ARCHIGOS_UNSUPPORTED_VERSION,
    )


def request_warnings(request: SourceIngestRequest) -> tuple[SourceWarning, ...]:
    warnings: list[SourceWarning] = []
    if request.leaders:
        warnings.append(
            SourceWarning(
                code=UNSUPPORTED_FILTER,
                message=(
                    "Archigos clean adapter does not apply leader filters; "
                    "leader names remain source-native spell attributes."
                ),
                severity="warning",
                source_id=request.source_id,
                context={"requested_leaders": list(request.leaders)},
            ),
        )
    for year in request.years or ():
        year_int = int(year)
        if year_int < ARCHIGOS_COVERAGE_START_YEAR or year_int > ARCHIGOS_COVERAGE_END_YEAR:
            warnings.append(
                SourceWarning(
                    code=YEAR_ABSENT,
                    message=(
                        f"year={year_int} is outside Archigos start-year "
                        f"coverage ({ARCHIGOS_COVERAGE_START_YEAR}-"
                        f"{ARCHIGOS_COVERAGE_END_YEAR}); no observations "
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
    "dta_path",
    "file_blocker",
    "metadata_blocker",
    "metadata_path",
    "read_metadata",
    "request_warnings",
    "version_blocker",
]
