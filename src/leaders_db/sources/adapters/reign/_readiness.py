"""Readiness checks for the clean REIGN adapter."""

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
    REIGN_CHECKSUM_MISMATCH,
    REIGN_COVERAGE_END_YEAR,
    REIGN_COVERAGE_START_YEAR,
    REIGN_CSV_NAME,
    REIGN_DEFAULT_VERSION,
    REIGN_LOCAL_FILES_INVALID,
    REIGN_METADATA_NAME,
    REIGN_METADATA_VERSION_MISMATCH,
    REIGN_SOURCE_KEY,
    REIGN_UNSUPPORTED_VERSION,
)


def bundle_dir(request: SourceIngestRequest) -> Path:
    return Path(request.raw_root) / REIGN_SOURCE_KEY


def metadata_path(request: SourceIngestRequest) -> Path:
    return bundle_dir(request) / REIGN_METADATA_NAME


def csv_path(request: SourceIngestRequest) -> Path:
    return bundle_dir(request) / REIGN_CSV_NAME


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
        return f"REIGN metadata.json is missing at {path}", MISSING_METADATA
    payload = read_metadata(path)
    if not payload:
        return f"REIGN metadata.json is not parseable at {path}", MISSING_METADATA
    version = str(payload.get("source_version", "")).strip()
    if version != REIGN_DEFAULT_VERSION:
        return (
            "REIGN metadata source_version must be "
            f"{REIGN_DEFAULT_VERSION!r}; got {version!r}",
            REIGN_METADATA_VERSION_MISMATCH,
        )
    local_files = payload.get("local_files")
    if not isinstance(local_files, list) or not local_files or not all(
        isinstance(item, str) and item.strip() for item in local_files
    ):
        return (
            "REIGN metadata local_files must be a non-empty string list",
            REIGN_LOCAL_FILES_INVALID,
        )
    if REIGN_CSV_NAME not in local_files:
        return (
            "REIGN metadata local_files must include the canonical CSV "
            f"file {REIGN_CSV_NAME!r}",
            REIGN_LOCAL_FILES_INVALID,
        )
    return None


def file_blocker(request: SourceIngestRequest) -> tuple[str, str] | None:
    path = csv_path(request)
    if not path.is_file():
        return f"REIGN CSV file is missing at {path}", MISSING_RAW
    metadata = read_metadata(metadata_path(request))
    checksums = metadata.get("checksum_sha256")
    if isinstance(checksums, dict):
        expected = checksums.get(REIGN_CSV_NAME)
        if isinstance(expected, str) and expected.strip():
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual.lower() != expected.strip().lower():
                return (
                    f"REIGN CSV file checksum mismatch for {REIGN_CSV_NAME}",
                    REIGN_CHECKSUM_MISMATCH,
                )
    return None


def version_blocker(request: SourceIngestRequest) -> tuple[str, str] | None:
    if request.source_version in (None, REIGN_DEFAULT_VERSION):
        return None
    return (
        "REIGN request source_version must be "
        f"{REIGN_DEFAULT_VERSION!r}; got {request.source_version!r}",
        REIGN_UNSUPPORTED_VERSION,
    )


def request_warnings(request: SourceIngestRequest) -> tuple[SourceWarning, ...]:
    warnings: list[SourceWarning] = []
    if request.leaders:
        warnings.append(
            SourceWarning(
                code=UNSUPPORTED_FILTER,
                message=(
                    "REIGN clean adapter does not apply leader filters; "
                    "leader names remain source-native monthly row attributes."
                ),
                severity="warning",
                source_id=request.source_id,
                context={"requested_leaders": list(request.leaders)},
            ),
        )
    for year in request.years or ():
        year_int = int(year)
        if year_int < REIGN_COVERAGE_START_YEAR or year_int > REIGN_COVERAGE_END_YEAR:
            warnings.append(
                SourceWarning(
                    code=YEAR_ABSENT,
                    message=(
                        f"year={year_int} is outside REIGN leader-month "
                        f"coverage ({REIGN_COVERAGE_START_YEAR}-"
                        f"{REIGN_COVERAGE_END_YEAR}); no observations will "
                        "be emitted for this year."
                    ),
                    severity="warning",
                    source_id=request.source_id,
                    context={"year": year_int},
                ),
            )
    return tuple(warnings)


__all__ = [
    "bundle_dir",
    "csv_path",
    "file_blocker",
    "metadata_blocker",
    "metadata_path",
    "read_metadata",
    "request_warnings",
    "version_blocker",
]
