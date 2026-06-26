"""Readiness checks for the clean UNDP HDI adapter."""

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
    UNDP_HDI_CHECKSUM_MISMATCH,
    UNDP_HDI_COVERAGE_END_YEAR,
    UNDP_HDI_COVERAGE_START_YEAR,
    UNDP_HDI_CSV_NAME,
    UNDP_HDI_DEFAULT_VERSION,
    UNDP_HDI_LOCAL_FILES_INVALID,
    UNDP_HDI_METADATA_NAME,
    UNDP_HDI_METADATA_VERSION_MISMATCH,
    UNDP_HDI_PROXY_REQUESTED_YEAR,
    UNDP_HDI_PROXY_YEAR,
    UNDP_HDI_SOURCE_KEY,
    UNDP_HDI_UNSUPPORTED_VERSION,
)


def bundle_dir(request: SourceIngestRequest) -> Path:
    return Path(request.raw_root) / UNDP_HDI_SOURCE_KEY


def metadata_path(request: SourceIngestRequest) -> Path:
    return bundle_dir(request) / UNDP_HDI_METADATA_NAME


def csv_path(request: SourceIngestRequest) -> Path:
    return bundle_dir(request) / UNDP_HDI_CSV_NAME


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
        return f"UNDP HDI metadata.json is missing at {path}", MISSING_METADATA
    payload = read_metadata(path)
    if not payload:
        return f"UNDP HDI metadata.json is not parseable at {path}", MISSING_METADATA
    version = str(payload.get("source_version") or payload.get("version") or "").strip()
    if version != UNDP_HDI_DEFAULT_VERSION:
        return (
            "UNDP HDI metadata version must be "
            f"{UNDP_HDI_DEFAULT_VERSION!r}; got {version!r}",
            UNDP_HDI_METADATA_VERSION_MISMATCH,
        )
    return _local_files_blocker(payload)


def _local_files_blocker(payload: dict[str, Any]) -> tuple[str, str] | None:
    local_files = payload.get("local_files")
    if local_files is None:
        if _checksum_dict_sha(payload):
            return None
        if payload.get("source_key") == UNDP_HDI_SOURCE_KEY and _legacy_sha(payload):
            return None
        return (
            "UNDP HDI metadata without local_files must include either a "
            "canonical checksum_sha256 entry or legacy matching source_key and sha256",
            UNDP_HDI_LOCAL_FILES_INVALID,
        )
    if not isinstance(local_files, list) or not local_files or not all(
        isinstance(item, str) and item.strip() for item in local_files
    ):
        return (
            "UNDP HDI metadata local_files must be a non-empty string list",
            UNDP_HDI_LOCAL_FILES_INVALID,
        )
    if UNDP_HDI_CSV_NAME not in local_files:
        return (
            "UNDP HDI metadata local_files must include the canonical CSV "
            f"{UNDP_HDI_CSV_NAME!r}",
            UNDP_HDI_LOCAL_FILES_INVALID,
        )
    return None


def file_blocker(request: SourceIngestRequest) -> tuple[str, str] | None:
    path = csv_path(request)
    if not path.is_file():
        return f"UNDP HDI CSV is missing at {path}", MISSING_RAW
    expected = expected_checksum(read_metadata(metadata_path(request)))
    if expected:
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual.lower() != expected.lower():
            return (
                f"UNDP HDI CSV checksum mismatch for {UNDP_HDI_CSV_NAME}",
                UNDP_HDI_CHECKSUM_MISMATCH,
            )
    return None


def expected_checksum(metadata: dict[str, Any]) -> str | None:
    checksum = _checksum_dict_sha(metadata)
    if checksum:
        return checksum
    return _legacy_sha(metadata)


def _checksum_dict_sha(metadata: dict[str, Any]) -> str | None:
    checksums = metadata.get("checksum_sha256")
    if isinstance(checksums, dict):
        value = checksums.get(UNDP_HDI_CSV_NAME)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _legacy_sha(metadata: dict[str, Any]) -> str | None:
    value = metadata.get("sha256")
    return value.strip() if isinstance(value, str) and value.strip() else None


def version_blocker(request: SourceIngestRequest) -> tuple[str, str] | None:
    if request.source_version in (None, UNDP_HDI_DEFAULT_VERSION):
        return None
    return (
        "UNDP HDI request source_version must be "
        f"{UNDP_HDI_DEFAULT_VERSION!r}; got {request.source_version!r}",
        UNDP_HDI_UNSUPPORTED_VERSION,
    )


def request_warnings(request: SourceIngestRequest) -> tuple[SourceWarning, ...]:
    warnings: list[SourceWarning] = []
    if request.leaders:
        warnings.append(SourceWarning(
            code=UNSUPPORTED_FILTER,
            message="UNDP HDI is country-year data; leader filters are ignored.",
            severity="warning",
            source_id=request.source_id,
            context={"requested_leaders": list(request.leaders)},
        ))
    for year in request.years or ():
        year_int = int(year)
        if year_int == UNDP_HDI_PROXY_REQUESTED_YEAR:
            warnings.append(SourceWarning(
                code=YEAR_ABSENT,
                message=(
                    f"year={year_int} is outside UNDP HDI coverage "
                    f"({UNDP_HDI_COVERAGE_START_YEAR}-{UNDP_HDI_COVERAGE_END_YEAR}); "
                    f"using {UNDP_HDI_PROXY_YEAR} as a one-year proxy."
                ),
                severity="warning",
                source_id=request.source_id,
                context={"requested_year": year_int, "proxy_year": UNDP_HDI_PROXY_YEAR},
            ))
        elif year_int < UNDP_HDI_COVERAGE_START_YEAR or year_int > UNDP_HDI_COVERAGE_END_YEAR:
            warnings.append(SourceWarning(
                code=YEAR_ABSENT,
                message=(
                    f"year={year_int} is outside UNDP HDI coverage "
                    f"({UNDP_HDI_COVERAGE_START_YEAR}-{UNDP_HDI_COVERAGE_END_YEAR}); "
                    "no observations will be emitted for this year."
                ),
                severity="warning",
                source_id=request.source_id,
                context={"year": year_int},
            ))
    return tuple(warnings)


__all__ = [
    "bundle_dir",
    "csv_path",
    "expected_checksum",
    "file_blocker",
    "metadata_blocker",
    "metadata_path",
    "read_metadata",
    "request_warnings",
    "version_blocker",
]
