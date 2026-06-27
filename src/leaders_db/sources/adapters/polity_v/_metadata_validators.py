"""Per-field ``metadata.json`` validators for the
unified-source Polity V adapter.

Each validator returns a ``(message, code)`` blocker tuple or
``None`` when the field is well-formed. Split out of
:mod:`._readiness` so the readiness orchestrator stays focused
on lifecycle ordering.

Validators accept the canonical Polity V bundle metadata shape:
``source_name`` / ``source_version`` / ``source_url`` /
``license_note`` / ``coverage`` / ``local_files`` /
``ingestion_status`` / ``checksum_sha256`` /
``download_date`` / ``notes``. The canonical Polity V bundle
metadata is the user's runtime-local
``data/raw/polity_v/metadata.json``; the unified adapter never
auto-commits the raw .sav bundle (the raw .sav is gitignored
per Always-On Rule #9).

Source-version semantics
------------------------

The canonical Polity V default version is ``"p5v2018"`` (the
canonical stamp for the staged SPSS file + the canonical
citation block in ``docs/sources/attributions.md`` §
``polity_v``). The staged bundle metadata must carry
``source_version == "p5v2018"`` byte-for-byte for readiness to
pass; a mismatch fires ``unsupported_version`` so the runner
raises ``RuntimeError`` BEFORE ``read_raw`` / ``transform``
(SRC-REQ-009).
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
# WGI / V-Dem / UCDP / CPI / PTS ``UNSUPPORTED_VERSION``.
UNSUPPORTED_VERSION: str = "unsupported_version"

# Required metadata fields (canonical Polity V bundle shape).
# The staged ``data/raw/polity_v/metadata.json`` must list
# every field below; missing fields fire a structured
# ``missing_metadata`` error so the runner raises ``RuntimeError``
# BEFORE the reader opens the .sav.
REQUIRED_METADATA_FIELDS: tuple[str, ...] = (
    "source_name",
    "source_version",
    "source_url",
    "license_note",
    "coverage",
    "local_files",
    "ingestion_status",
    "checksum_sha256",
    "download_date",
    "notes",
)


def _read_metadata_payload(metadata_path: Path) -> dict[str, Any]:
    """Return the parsed ``metadata.json`` payload, or ``{}`` on
    any error.

    The unified ``check_metadata_well_formed`` helper uses this
    helper to load the staged bundle's metadata fields. A
    malformed / unreadable ``metadata.json`` is treated as
    missing-metadata so the readiness gate returns
    ``ready=False`` with a structured ``missing_metadata``
    blocker.
    """
    if not metadata_path.is_file():
        return {}
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _presence_blocker(
    metadata_path: Path,
    sav_path: Path,
    sav_name: str,
) -> tuple[str, str] | None:
    """Return a blocker tuple if ``metadata.json`` or the ``.sav`` is missing.

    The mandatory readiness requirement is on raw-file presence:
    a metadata-only bundle is intentionally NOT runner-ready; the
    gate fires ``MISSING_RAW`` whenever the staged ``.sav`` is
    NOT on disk, regardless of the metadata's ``local_files``
    shape. The check fires AFTER the ``metadata.json``
    presence check so a metadata-only bundle is still reported
    as ``missing_metadata`` rather than ``missing_raw``.
    """
    if not metadata_path.is_file():
        return (
            f"Polity V readiness gate: metadata.json missing at "
            f"{metadata_path}; place the canonical "
            "data/raw/polity_v/metadata.json before running "
            "Stage 2.",
            MISSING_METADATA,
        )
    if not sav_path.is_file():
        return (
            f"Polity V readiness gate: {sav_name} missing at "
            f"{sav_path}; place the canonical "
            f"data/raw/polity_v/{sav_name} before running "
            "Stage 2.",
            MISSING_RAW,
        )
    return None


def _required_fields_blocker(
    payload: dict[str, Any],
) -> tuple[str, str] | None:
    """Block if any canonical required metadata field is absent."""
    for field in REQUIRED_METADATA_FIELDS:
        if field not in payload:
            return (
                f"Polity V readiness gate: metadata.json is "
                f"missing required field '{field}'.",
                MISSING_METADATA,
            )
    return None


def _local_files_blocker(
    payload: dict[str, Any], sav_name: str,
) -> tuple[str, str] | None:
    """Block if ``local_files`` does not include the canonical ``.sav``."""
    local_files = payload.get("local_files")
    if (
        not isinstance(local_files, list)
        or sav_name not in local_files
    ):
        return (
            f"Polity V readiness gate: metadata.json "
            f"'local_files' must include {sav_name!r}; got "
            f"{local_files!r}",
            MISSING_METADATA,
        )
    return None


def _ingestion_status_blocker(
    payload: dict[str, Any],
) -> tuple[str, str] | None:
    """Block if ``ingestion_status`` is not ``'downloaded'``."""
    if payload.get("ingestion_status") != "downloaded":
        return (
            "Polity V readiness gate: metadata.json "
            "'ingestion_status' must be 'downloaded'; got "
            f"{payload.get('ingestion_status')!r}.",
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
            f"Polity V readiness gate: metadata.json '{field}' "
            f"must be a non-empty string naming {expected}.",
            MISSING_METADATA,
        )
    return None


def _checksum_match_blocker(
    payload: dict[str, Any], sav_path: Path,
) -> tuple[str, str] | None:
    """Block if the staged ``.sav`` SHA-256 disagrees with the metadata field."""
    expected_sha = payload.get("checksum_sha256")
    if not isinstance(expected_sha, str) or not expected_sha.strip():
        return (
            "Polity V readiness gate: metadata.json "
            "'checksum_sha256' must be a non-empty hex SHA-256 "
            "string.",
            MISSING_METADATA,
        )
    actual_sha = hashlib.sha256(sav_path.read_bytes()).hexdigest()
    if actual_sha.lower() != expected_sha.strip().lower():
        return (
            f"Polity V readiness gate: .sav checksum mismatch. "
            f"metadata.json says checksum_sha256="
            f"{expected_sha.strip().lower()!r} but the staged "
            f".sav has sha256="
            f"{actual_sha.lower()!r}.",
            MISSING_METADATA,
        )
    return None


def _metadata_source_version_blocker(
    payload: dict[str, Any], canonical_version: str,
) -> tuple[str, str] | None:
    """Block if metadata ``source_version`` is missing or not canonical."""
    metadata_version = payload.get("source_version")
    if not isinstance(metadata_version, str) or not metadata_version.strip():
        return (
            "Polity V readiness gate: metadata.json "
            "'source_version' must be the canonical version "
            f"{canonical_version!r}.",
            UNSUPPORTED_VERSION,
        )
    if metadata_version.strip() != canonical_version:
        return (
            f"Polity V readiness gate: metadata.json "
            f"'source_version' is {metadata_version.strip()!r}, "
            f"but the unified Polity V adapter supports only "
            f"canonical version {canonical_version!r}. Re-stage "
            f"a Polity5 v2018 bundle or correct metadata.json "
            f"before running ingestion.",
            UNSUPPORTED_VERSION,
        )
    return None


__all__ = [
    "MISSING_METADATA",
    "MISSING_RAW",
    "REQUIRED_METADATA_FIELDS",
    "UNSUPPORTED_VERSION",
    "_checksum_match_blocker",
    "_ingestion_status_blocker",
    "_local_files_blocker",
    "_metadata_source_version_blocker",
    "_non_empty_string_blocker",
    "_presence_blocker",
    "_read_metadata_payload",
    "_required_fields_blocker",
]
