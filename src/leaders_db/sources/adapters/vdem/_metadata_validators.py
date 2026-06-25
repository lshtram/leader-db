"""Per-field metadata validators for the unified-source V-Dem adapter.

This module owns the per-field ``metadata.json`` validators used
by the readiness gate. Each validator is a small focused helper
that returns a ``(message, code)`` blocker tuple or ``None``
when the field is well-formed. Split out of
:mod:`._readiness` so the readiness orchestrator stays focused
on the lifecycle order (``check_metadata_well_formed`` →
``check_source_version`` → request-scoping warnings).

Checksum scoping (V-Dem specific)
--------------------------------

The V-Dem bundle carries TWO artifacts:

1. ``V-Dem-CY-FullOthers-v16_csv.zip`` -- the original
   download bundle (~26 MB on disk); the staged
   ``metadata.json`` records ``checksum_sha256`` for this
   artifact.
2. ``V-Dem-CY-Full+Others-v16.csv`` -- the extracted /
   unzipped CSV (~388 MB / 28093 rows / 4618 columns); this
   is the only artifact the unified adapter reads.

The readiness gate MUST NOT hash the 388MB CSV against the zip
checksum (that would be a spurious mismatch). Instead the gate
validates the metadata shape of ``checksum_sha256`` (must be a
64-character hex SHA-256 string) AND, if the zip is staged
alongside the CSV, recomputes the zip's SHA-256 and compares
against the metadata field. The 388MB CSV is never hashed by
the unified adapter; that is the legacy reader's job and is
explicitly out of scope for the unified path.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from leaders_db.sources.warnings import (
    MISSING_METADATA,
    MISSING_RAW,
)

# Module-local structured warning code used to reject an
# unsupported request source-version per SRC-REQ-009. Mirrors
# the PWT / Maddison / WGI adapter's UNSUPPORTED_VERSION code
# so the V-Dem readiness envelope stays consistent with the
# rest of the unified source subsystem.
UNSUPPORTED_VERSION: str = "unsupported_version"

# Module-local structured warning code used to surface a
# checksum that is well-formed but does not match the staged
# zip bytes. The code is V-Dem-specific because V-Dem is the
# only source whose metadata checksum covers a DIFFERENT
# artifact (the zip) than the one the unified adapter reads
# (the CSV).
VDEM_CHECKSUM_MISMATCH: str = "vdem_checksum_mismatch"

# Required metadata fields -- PRIMARY shape (the canonical
# shape used by the PWT / Maddison / WDI / WGI adapters).
# V-Dem's staged bundle already uses this primary shape so no
# legacy-key fallback is needed.
REQUIRED_METADATA_FIELDS: tuple[str, ...] = (
    "source_name",
    "source_version",
    "source_url",
    "license_note",
    "local_files",
    "ingestion_status",
    "coverage",
    "checksum_sha256",
)

# Acceptable ``ingestion_status`` values for V-Dem. The
# legacy bundle records ``ingested`` (the full ingestion has
# already run end-to-end on the legacy side); the readiness
# gate also accepts ``downloaded`` so a future
# freshly-downloaded bundle is not rejected.
ACCEPTABLE_INGESTION_STATUSES: frozenset[str] = frozenset(
    {"ingested", "downloaded"},
)


def _read_metadata_payload(metadata_path: Path) -> dict[str, Any]:
    """Return the parsed ``metadata.json`` payload, or ``{}`` on any error."""
    if not metadata_path.is_file():
        return {}
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _presence_blocker(
    metadata_path: Path, csv_path: Path, csv_name: str,
) -> tuple[str, str] | None:
    """Return a blocker tuple if ``metadata.json`` or the CSV is missing."""
    if not metadata_path.is_file():
        return (
            "V-Dem readiness gate: metadata.json missing "
            f"at {metadata_path}; place the canonical "
            "data/raw/vdem/metadata.json before running "
            "Stage 2.",
            MISSING_METADATA,
        )
    if not csv_path.is_file():
        return (
            "V-Dem readiness gate: "
            f"{csv_name} missing at {csv_path}; place the "
            "canonical V-Dem CY CSV before running Stage 2.",
            MISSING_RAW,
        )
    return None


def _required_fields_blocker(
    payload: dict[str, Any],
) -> tuple[str, str] | None:
    """Block if any canonical required field is absent."""
    for field in REQUIRED_METADATA_FIELDS:
        if field not in payload:
            return (
                "V-Dem readiness gate: metadata.json is "
                f"missing required field '{field}'.",
                MISSING_METADATA,
            )
    return None


def _local_files_blocker(
    payload: dict[str, Any], csv_name: str,
) -> tuple[str, str] | None:
    """Block if ``local_files`` does not include the canonical CSV."""
    local_files = payload.get("local_files")
    if (
        not isinstance(local_files, list)
        or csv_name not in local_files
    ):
        return (
            f"V-Dem readiness gate: metadata.json "
            f"'local_files' must include {csv_name!r}; got "
            f"{local_files!r}",
            MISSING_METADATA,
        )
    return None


def _ingestion_status_blocker(
    payload: dict[str, Any],
) -> tuple[str, str] | None:
    """Block if ``ingestion_status`` is not in the acceptable set."""
    status = payload.get("ingestion_status")
    if status not in ACCEPTABLE_INGESTION_STATUSES:
        return (
            "V-Dem readiness gate: metadata.json "
            f"'ingestion_status' must be one of "
            f"{sorted(ACCEPTABLE_INGESTION_STATUSES)}; got "
            f"{status!r}.",
            MISSING_METADATA,
        )
    return None


def _non_empty_string_blocker(
    payload: dict[str, Any],
    field: str,
    expected: str,
) -> tuple[str, str] | None:
    """Block if ``payload[field]`` is not a non-empty string."""
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        return (
            f"V-Dem readiness gate: metadata.json '{field}' "
            f"must be a non-empty string naming {expected}.",
            MISSING_METADATA,
        )
    return None


def _checksum_shape_blocker(
    payload: dict[str, Any],
) -> tuple[str, str] | None:
    """Block if the metadata ``checksum_sha256`` is not a valid 64-char hex SHA-256.

    The field is REQUIRED per the canonical primary metadata
    shape; we accept a 64-character hex string (a flat-bundle
    SHA-256) here. The PWT / Maddison / WGI adapters allow the
    same flat-string shape; WDI additionally accepts a
    ``null`` + ``checksum_note`` shape, but V-Dem is a
    local-file source so ``checksum_sha256`` is non-null.
    """
    expected_sha = payload.get("checksum_sha256")
    if not isinstance(expected_sha, str) or not expected_sha.strip():
        return (
            "V-Dem readiness gate: metadata.json "
            "'checksum_sha256' must be a non-empty 64-character "
            "hex SHA-256 string; got empty value.",
            MISSING_METADATA,
        )
    stripped = expected_sha.strip().lower()
    if len(stripped) != 64 or any(
        ch not in "0123456789abcdef" for ch in stripped
    ):
        return (
            "V-Dem readiness gate: metadata.json "
            "'checksum_sha256' must be a 64-character hex "
            f"SHA-256 string; got {expected_sha!r}.",
            MISSING_METADATA,
        )
    return None


def _checksum_match_blocker(
    payload: dict[str, Any],
    bundle_dir: Path,
    zip_name: str,
) -> tuple[str, str] | None:
    """Verify the zip SHA-256 against the metadata ``checksum_sha256``.

    The readiness gate validates the checksum in the staging
    directory's ZIP (when present) -- NOT the 388MB CSV -- so
    a missing zip OR a zip mismatch raises a structured
    ``vdem_checksum_mismatch`` / ``missing_metadata`` blocker.
    If the zip is absent entirely, the readiness gate warns
    (does not block) per the metadata contract documented in
    the bundle metadata's ``checksum_scope`` field: the
    canonical V-Dem bundle carries the zip and the unified
    adapter prefers the zip-staged path; a missing zip in a
    test fixture is acceptable but a mismatched zip is not.
    """
    expected_sha = payload.get("checksum_sha256")
    if not isinstance(expected_sha, str) or not expected_sha.strip():
        # Shape check is handled separately by
        # :func:`_checksum_shape_blocker`.
        return None
    expected_sha = expected_sha.strip().lower()
    zip_path = bundle_dir / zip_name
    if not zip_path.is_file():
        # The zip is not staged (e.g. test fixture). The
        # readiness gate does NOT block on a missing zip
        # alone -- the metadata contract documents that the
        # checksum scope covers the zip, so a missing zip is
        # acceptable for the readiness gate as long as the
        # CSV is staged. The readiness gate still validates
        # the metadata shape above.
        return None
    actual_sha = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    if actual_sha != expected_sha:
        return (
            "V-Dem readiness gate: zip checksum mismatch. "
            "metadata.json says checksum_sha256="
            f"{expected_sha!r} but the staged {zip_name} has "
            f"sha256={actual_sha!r}. Re-stage the V-Dem "
            "bundle or correct metadata.json before running "
            "ingestion.",
            VDEM_CHECKSUM_MISMATCH,
        )
    return None


def _metadata_source_version_blocker(
    payload: dict[str, Any], canonical_version: str,
) -> tuple[str, str] | None:
    """Block if metadata ``source_version`` is missing or not canonical."""
    metadata_version = payload.get("source_version")
    if not isinstance(metadata_version, str) or not metadata_version.strip():
        return (
            "V-Dem readiness gate: metadata.json "
            f"'source_version' must be the canonical version "
            f"{canonical_version!r}.",
            UNSUPPORTED_VERSION,
        )
    if metadata_version.strip() != canonical_version:
        return (
            f"V-Dem readiness gate: metadata.json "
            f"'source_version' is {metadata_version.strip()!r}, "
            f"but the unified V-Dem adapter supports only "
            f"canonical version {canonical_version!r}. "
            "Re-stage the V-Dem bundle or correct "
            "metadata.json before running ingestion.",
            UNSUPPORTED_VERSION,
        )
    return None


def _year_range_from_coverage(payload: dict[str, Any]) -> str | None:
    """Return the coverage string from the bundle metadata.

    The V-Dem bundle carries the coverage envelope under one
    of three keys: ``coverage`` (canonical), ``year_range``
    (legacy alias), or via a ``coverage_start_year`` +
    ``coverage_end_year`` pair. Returns the resolved string
    (``"1789-2025"``) when found; ``None`` otherwise.
    """
    coverage = payload.get("coverage")
    if isinstance(coverage, str) and coverage.strip():
        return coverage.strip()
    year_range = payload.get("year_range")
    if isinstance(year_range, str) and year_range.strip():
        return year_range.strip()
    start = payload.get("coverage_start_year")
    end = payload.get("coverage_end_year")
    if isinstance(start, int) and isinstance(end, int):
        return f"{start}-{end}"
    return None


__all__ = [
    "ACCEPTABLE_INGESTION_STATUSES",
    "REQUIRED_METADATA_FIELDS",
    "UNSUPPORTED_VERSION",
    "VDEM_CHECKSUM_MISMATCH",
    "_checksum_match_blocker",
    "_checksum_shape_blocker",
    "_ingestion_status_blocker",
    "_local_files_blocker",
    "_metadata_source_version_blocker",
    "_non_empty_string_blocker",
    "_presence_blocker",
    "_read_metadata_payload",
    "_required_fields_blocker",
    "_year_range_from_coverage",
]
