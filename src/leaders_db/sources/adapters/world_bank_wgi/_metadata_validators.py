"""Per-field metadata validators for the unified-source WGI adapter.

This module owns the per-field ``metadata.json`` validators used
by the readiness gate. Each validator is a small focused helper
that returns a ``(message, code)`` blocker tuple or ``None``
when the field is well-formed. Split out of
:mod:`._readiness` so the readiness orchestrator stays focused
on the lifecycle order (``check_metadata_well_formed`` →
``check_source_version`` → request-scoping warnings).

The validators accept BOTH the canonical primary metadata shape
(``source_version`` / ``checksum_sha256`` / ``local_files`` /
``license_note`` / ``coverage``) AND the legacy WGI shape
(``version`` / ``sha256`` / ``local_file`` / ``license`` /
``coverage_start_year`` + ``coverage_end_year``) so the existing
staged bundle metadata does not need to be rewritten as part
of the migration. Each per-field validator probes the primary
key first via the :func:`_coalesce` helper, then falls back to
the legacy alias.
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

# All descriptor constants are re-exported from the package
# ``__init__``; this module reuses the legacy-key metadata
# constants directly without pulling in coverage-hint
# constants that are owned by :mod:`._readiness`.

# Module-local structured warning code used to reject an
# unsupported request source-version per SRC-REQ-009. Mirrors
# the PWT / Maddison adapter's UNSUPPORTED_VERSION code so the
# WGI readiness envelope stays consistent with the rest of the
# unified source subsystem.
UNSUPPORTED_VERSION: str = "unsupported_version"

# Required metadata fields -- PRIMARY shape (the canonical
# shape used by the PWT / Maddison / WDI adapters). Each field
# has a legacy alias in the staged ``world_bank_wgi/metadata.json``
# bundle; the per-field validators below probe the primary key
# first, then fall back to the legacy alias. The set is exposed
# via :data:`REQUIRED_METADATA_FIELDS_PRIMARY_KEYS` so the
# ``tests/sources/test_import_boundary.py`` canonical submodule
# list can introspect it if needed.
REQUIRED_METADATA_FIELDS_PRIMARY_KEYS: tuple[str, ...] = (
    "source_version",
    "source_url",
    "license_note",
    "checksum_sha256",
    "local_files",
    "ingestion_status",
    "coverage",
)

# Legacy aliases accepted by the per-field validators. The
# staged ``world_bank_wgi/metadata.json`` carries these legacy
# keys; rewriting the bundle as part of the migration is out of
# scope so the readiness gate must accept both shapes.
REQUIRED_METADATA_FIELDS_LEGACY_KEYS: tuple[str, ...] = (
    "version",        # -> source_version
    "source_url",     # unchanged
    "license",        # -> license_note
    "sha256",         # -> checksum_sha256
    "local_file",     # -> local_files (single-string)
    "ingestion_status",
    "coverage",       # may also be the structured coverage_*_year pair
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


def _coalesce(
    payload: dict[str, Any],
    primary: str,
    legacy: str | None = None,
) -> Any:
    """Return the first non-None value among ``primary`` and ``legacy`` keys."""
    value = payload.get(primary)
    if value is not None:
        return value
    if legacy is not None:
        return payload.get(legacy)
    return None


def _presence_blocker(
    metadata_path: Path, xlsx_path: Path, xlsx_name: str,
) -> tuple[str, str] | None:
    """Return a blocker tuple if ``metadata.json`` or the xlsx is missing."""
    if not metadata_path.is_file():
        return (
            "World Bank WGI readiness gate: metadata.json missing "
            f"at {metadata_path}; place the canonical data/raw/"
            "world_bank_wgi/metadata.json before running Stage 2.",
            MISSING_METADATA,
        )
    if not xlsx_path.is_file():
        return (
            "World Bank WGI readiness gate: "
            f"{xlsx_name} missing at {xlsx_path}; place the "
            "canonical World Bank WGI xlsx before running Stage 2.",
            MISSING_RAW,
        )
    return None


def _required_fields_blocker(
    payload: dict[str, Any],
) -> tuple[str, str] | None:
    """Block if any canonical required field is absent (in either shape).

    The ``coverage`` field additionally accepts the legacy
    ``coverage_start_year`` + ``coverage_end_year`` numeric
    pair as a substitute for the canonical ``coverage`` string.
    """
    required_pairs: tuple[tuple[str, str | None], ...] = (
        ("source_version", "version"),
        ("source_url", None),
        ("license_note", "license"),
        ("checksum_sha256", "sha256"),
        ("local_files", "local_file"),
        ("ingestion_status", None),
        ("coverage", None),
    )
    for primary, legacy in required_pairs:
        primary_value = payload.get(primary)
        legacy_value = payload.get(legacy) if legacy else None
        if (
            primary == "coverage"
            and primary_value is None
            and legacy_value is None
        ):
            if _has_coverage_pair(payload):
                continue
        if primary_value is None and legacy_value is None:
            return (
                "World Bank WGI readiness gate: metadata.json is "
                f"missing required field '{primary}' (legacy alias: "
                f"{legacy!r}).",
                MISSING_METADATA,
            )
    return None


def _has_coverage_pair(payload: dict[str, Any]) -> bool:
    """Return True iff ``payload`` carries a legacy coverage-year pair."""
    start = payload.get("coverage_start_year")
    end = payload.get("coverage_end_year")
    return (
        isinstance(start, int)
        and isinstance(end, int)
        and start <= end
    )


def _local_files_blocker(
    payload: dict[str, Any], xlsx_name: str,
) -> tuple[str, str] | None:
    """Block if ``local_files`` / ``local_file`` does not include the canonical xlsx."""
    local_files = _coalesce(payload, "local_files", "local_file")
    if isinstance(local_files, list):
        if xlsx_name not in local_files:
            return (
                f"World Bank WGI readiness gate: metadata.json "
                f"'local_files' must include {xlsx_name!r}; got "
                f"{local_files!r}",
                MISSING_METADATA,
            )
        return None
    if isinstance(local_files, str):
        if local_files.strip() != xlsx_name:
            return (
                f"World Bank WGI readiness gate: metadata.json "
                f"'local_file' must be {xlsx_name!r}; got "
                f"{local_files!r}",
                MISSING_METADATA,
            )
        return None
    return (
        "World Bank WGI readiness gate: metadata.json 'local_files' "
        f"must be a non-empty list or the legacy 'local_file' string "
        f"naming {xlsx_name!r}; got {local_files!r}",
        MISSING_METADATA,
    )


def _ingestion_status_blocker(
    payload: dict[str, Any],
) -> tuple[str, str] | None:
    """Block if ``ingestion_status`` is not ``'downloaded'``."""
    if payload.get("ingestion_status") != "downloaded":
        return (
            "World Bank WGI readiness gate: metadata.json "
            f"'ingestion_status' must be 'downloaded'; got "
            f"{payload.get('ingestion_status')!r}.",
            MISSING_METADATA,
        )
    return None


def _non_empty_string_blocker(
    payload: dict[str, Any],
    primary: str,
    legacy: str | None,
    expected: str,
) -> tuple[str, str] | None:
    """Block if the coalesced ``primary`` / ``legacy`` value is not a non-empty string."""
    value = _coalesce(payload, primary, legacy)
    if not isinstance(value, str) or not value.strip():
        return (
            f"World Bank WGI readiness gate: metadata.json "
            f"'{primary}' (legacy alias: {legacy!r}) must be a "
            f"non-empty string naming {expected}.",
            MISSING_METADATA,
        )
    return None


def _checksum_match_blocker(
    payload: dict[str, Any], xlsx_path: Path,
) -> tuple[str, str] | None:
    """Block if the staged xlsx SHA-256 disagrees with the metadata field."""
    expected_sha = _coalesce(payload, "checksum_sha256", "sha256")
    if not isinstance(expected_sha, str) or not expected_sha.strip():
        return (
            "World Bank WGI readiness gate: metadata.json "
            "'checksum_sha256' (legacy alias: 'sha256') must be "
            "a non-empty hex SHA-256 string.",
            MISSING_METADATA,
        )
    actual_sha = hashlib.sha256(xlsx_path.read_bytes()).hexdigest()
    if actual_sha.lower() != expected_sha.strip().lower():
        return (
            "World Bank WGI readiness gate: xlsx checksum "
            f"mismatch. metadata.json says checksum_sha256="
            f"{expected_sha.strip().lower()!r} but the staged "
            f"xlsx has sha256={actual_sha.lower()!r}.",
            MISSING_METADATA,
        )
    return None


def _metadata_source_version_blocker(
    payload: dict[str, Any], canonical_version: str,
) -> tuple[str, str] | None:
    """Block if metadata ``source_version`` / ``version`` is missing or not canonical."""
    metadata_version = _coalesce(
        payload, "source_version", "version",
    )
    if not isinstance(metadata_version, str) or not metadata_version.strip():
        return (
            "World Bank WGI readiness gate: metadata.json "
            f"'source_version' (legacy alias: 'version') must be "
            f"the canonical version {canonical_version!r}.",
            UNSUPPORTED_VERSION,
        )
    if metadata_version.strip() != canonical_version:
        return (
            f"World Bank WGI readiness gate: metadata.json "
            f"'source_version' (legacy alias: 'version') is "
            f"{metadata_version.strip()!r}, but the unified "
            f"World Bank WGI adapter supports only canonical "
            f"version {canonical_version!r}. Re-stage the WGI "
            f"bundle or correct metadata.json before running "
            f"ingestion.",
            UNSUPPORTED_VERSION,
        )
    return None


__all__ = [
    "REQUIRED_METADATA_FIELDS_LEGACY_KEYS",
    "REQUIRED_METADATA_FIELDS_PRIMARY_KEYS",
    "UNSUPPORTED_VERSION",
    "_checksum_match_blocker",
    "_coalesce",
    "_has_coverage_pair",
    "_ingestion_status_blocker",
    "_local_files_blocker",
    "_metadata_source_version_blocker",
    "_non_empty_string_blocker",
    "_presence_blocker",
    "_read_metadata_payload",
    "_required_fields_blocker",
]
