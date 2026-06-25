"""Per-field metadata validators for the unified-source UCDP adapter.

This module owns the per-field ``metadata.json`` validators used
by the readiness gate. Each validator is a small focused helper
that returns a ``(message, code)`` blocker tuple or ``None``
when the field is well-formed. Split out of
:mod:`._readiness` so the readiness orchestrator stays focused
on the lifecycle order (``check_metadata_well_formed`` →
``check_source_version`` → request-scoping warnings).

The validators accept the canonical primary metadata shape
(``source_version`` / ``source_url`` / ``license_note`` /
``local_files`` / ``ingestion_status`` / ``coverage`` /
``checksum_sha256``). The staged UCDP bundle metadata
(``data/raw/ucdp/metadata.json``) already uses this shape
(plus the UCDP-specific ``expected_local_files`` /
``adapter`` / ``attribution`` / ``blocker_note`` extras that
the gate ignores rather than blocks on).

UCDP bundle reality
-------------------

The canonical ``data/raw/ucdp/`` bundle's ``metadata.json``
carries ``local_files=[]`` and ``checksum_sha256=null`` --
the metadata describes the bundle in a deliberately minimal
shape so the operator can update the metadata without
having to first re-compute the staged zip SHA-256. The
gate therefore accepts:

- ``local_files`` is an empty list (the canonical bundle
  metadata shape) OR a list containing the canonical
  ``ged231-csv.zip``;
- ``checksum_sha256`` is ``null`` (the canonical bundle
  metadata shape) OR a 64-character hex SHA-256 string
  (when the zip is staged AND the metadata has been
  updated with the zip SHA-256).

The **mandatory** gate is on raw-file presence: the gate
returns ``ready=False`` with a structured ``MISSING_RAW``
error if ``ged231-csv.zip`` is not staged on disk, even
when the metadata otherwise passes. This guarantees that
the ``SourceIngestRunner`` never proceeds to ``read_raw``
and surfaces an unhandled ``FileNotFoundError``; the
readiness envelope is the single dispatch gate, and a
metadata-only bundle (no staged zip) is NOT runner-ready
(it still has value for readiness-only inspection --
metadata shape validation, schema migrations,
sanity-checking ``expected_local_files`` annotations -- but
the runner raises ``RuntimeError`` BEFORE ``read_raw`` /
``transform`` whenever ``ready=False``).

A missing required field, an ``ingestion_status`` other
than ``downloaded`` / ``pending`` / ``ingested``, or a
checksum that does not match the staged zip each surface
a structured ``SourceWarning`` with ``severity='error'``.
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
# the PWT / Maddison / WGI / V-Dem adapters' UNSUPPORTED_VERSION
# code so the UCDP readiness envelope stays consistent with the
# rest of the unified source subsystem.
UNSUPPORTED_VERSION: str = "unsupported_version"

# Module-local structured warning code used to surface a
# checksum that is well-formed but does not match the staged
# zip bytes. Mirrors the V-Dem ``vdem_checksum_mismatch`` code
# pattern so the UCDP readiness envelope stays consistent.
UCDP_CHECKSUM_MISMATCH: str = "ucdp_checksum_mismatch"

# Required metadata fields -- PRIMARY shape (the canonical
# shape used by the PWT / Maddison / WDI / WGI / V-Dem
# adapters). The UCDP staged bundle already uses this primary
# shape so no legacy-key fallback is needed.
REQUIRED_METADATA_FIELDS: tuple[str, ...] = (
    "source_name",
    "source_version",
    "source_url",
    "license_note",
    "local_files",
    "ingestion_status",
    "coverage",
)

# Acceptable ``ingestion_status`` values for UCDP. The
# canonical UCDP bundle uses ``pending`` when the zip is not
# staged locally; ``downloaded`` / ``ingested`` are also
# acceptable so freshly-downloaded or already-ingested bundles
# are not rejected.
ACCEPTABLE_INGESTION_STATUSES: frozenset[str] = frozenset(
    {"pending", "downloaded", "ingested"},
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
    metadata_path: Path, zip_path: Path, zip_name: str,
) -> tuple[str, str] | None:
    """Return a blocker tuple if ``metadata.json`` or the zip is missing.

    The UCDP canonical bundle metadata ships with
    ``local_files=[]`` and ``checksum_sha256=null`` -- a
    minimal shape so the operator can update the metadata
    once the zip is staged. The mandatory readiness
    requirement is on raw-file presence: the gate returns
    ``ready=False`` with a structured ``MISSING_RAW`` error
    whenever ``ged231-csv.zip`` is NOT staged on disk,
    regardless of the metadata's ``local_files`` /
    ``checksum_sha256`` shape.

    A metadata-only bundle is intentionally NOT runner-ready
    so the runner never dispatches ``read_raw`` against a
    missing zip (the structured gate that the
    ``SourceIngestRunner`` consumes). The metadata-only
    bundle still has value for readiness-only inspection --
    callers can still ``adapter.check_ready(request)`` to
    validate metadata shape, but
    ``adapter.check_ready(request).ready`` is ``False`` until
    the zip is staged.
    """
    if not metadata_path.is_file():
        return (
            "UCDP readiness gate: metadata.json missing "
            f"at {metadata_path}; place the canonical data/raw/"
            "ucdp/metadata.json before running Stage 2.",
            MISSING_METADATA,
        )
    if not zip_path.is_file():
        # Mandatory raw-file presence: the runner must not dispatch
        # ``read_raw``/``transform`` against a metadata-only bundle.
        return (
            "UCDP readiness gate: "
            f"{zip_name} missing at {zip_path}; place the "
            "canonical UCDP GED 23.1 zip (download via the "
            "project workflow documented at "
            "https://ucdp.uu.se/downloads/ged/ged231-csv.zip) "
            "before running Stage 2. The readiness gate "
            "requires the staged zip -- a metadata-only "
            "bundle is NOT runner-ready.",
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
                "UCDP readiness gate: metadata.json is "
                f"missing required field '{field}'.",
                MISSING_METADATA,
            )
    return None


def _local_files_blocker(
    payload: dict[str, Any], zip_name: str,
) -> tuple[str, str] | None:
    """Block if ``local_files`` is present but malformed.

    The UCDP canonical bundle metadata carries
    ``local_files=[]`` -- a deliberately minimal shape so the
    operator can update the metadata once the zip is staged
    without first re-computing the staged zip SHA-256. The gate
    accepts:

    - an empty list ``[]`` (the canonical bundle metadata
      shape);
    - a list containing the canonical ``ged231-csv.zip``;
    - an empty / missing ``local_files`` (deprecated but
      acceptable for legacy-style bundles -- the gate only
      blocks on a non-list, non-empty shape that omits the
      canonical zip).

    The gate does NOT block on ``local_files=[]`` alone --
    the ``_presence_blocker`` separately enforces
    raw-file presence (the staged zip must exist on disk)
    so the runner never dispatches ``read_raw`` against a
    missing zip.
    """
    local_files = payload.get("local_files")
    if local_files is None or local_files == []:
        return None
    if not isinstance(local_files, list):
        return (
            "UCDP readiness gate: metadata.json 'local_files' "
            f"must be a list (possibly empty); got {type(local_files).__name__}.",
            MISSING_METADATA,
        )
    if local_files and zip_name not in local_files:
        return (
            f"UCDP readiness gate: metadata.json 'local_files' "
            f"must include {zip_name!r} when non-empty; got "
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
            "UCDP readiness gate: metadata.json "
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
            f"UCDP readiness gate: metadata.json '{field}' "
            f"must be a non-empty string naming {expected}.",
            MISSING_METADATA,
        )
    return None


def _checksum_shape_blocker(
    payload: dict[str, Any],
) -> tuple[str, str] | None:
    """Block if ``checksum_sha256`` is not null and not a valid 64-char hex SHA-256.

    The UCDP canonical bundle records ``checksum_sha256: null``
    when the zip is not staged locally. The gate accepts:

    - ``None`` (the canonical empty-bundle shape);
    - a 64-character hex SHA-256 string (when the zip is
      staged with a known SHA-256).

    A non-null, non-string, non-hex-64-character value fails
    readiness with a structured ``missing_metadata`` error.
    """
    expected_sha = payload.get("checksum_sha256")
    if expected_sha is None:
        return None
    if not isinstance(expected_sha, str) or not expected_sha.strip():
        return (
            "UCDP readiness gate: metadata.json "
            "'checksum_sha256' must be either null (no zip "
            "staged) or a non-empty 64-character hex SHA-256 "
            "string; got empty value.",
            MISSING_METADATA,
        )
    stripped = expected_sha.strip().lower()
    if len(stripped) != 64 or any(
        ch not in "0123456789abcdef" for ch in stripped
    ):
        return (
            "UCDP readiness gate: metadata.json "
            "'checksum_sha256' must be a 64-character hex "
            f"SHA-256 string; got {expected_sha!r}.",
            MISSING_METADATA,
        )
    return None


def _checksum_match_blocker(
    payload: dict[str, Any],
    zip_path: Path,
    zip_name: str,
) -> tuple[str, str] | None:
    """Verify the staged zip SHA-256 against ``checksum_sha256``.

    The UCDP canonical bundle metadata carries
    ``checksum_sha256: null`` -- a deliberately minimal shape
    so the operator can update the metadata once the zip is
    staged and the SHA-256 has been computed. The gate:

    - returns ``None`` (no blocker) when the metadata
      ``checksum_sha256`` is ``null`` (the canonical bundle
      metadata shape);
    - returns ``None`` (no blocker) when the metadata
      ``checksum_sha256`` is null AND the staged zip is
      present (the staged-zip without SHA-256-stamped
      metadata shape);
    - returns ``None`` when the staged zip SHA-256 matches
      the metadata ``checksum_sha256``;
    - returns a structured ``ucdp_checksum_mismatch`` blocker
      when the staged zip SHA-256 disagrees with the metadata
      field.

    The raw-file presence (staged zip must exist on disk) is
    enforced separately by :func:`_presence_blocker` -- this
    helper is conditional on the zip being staged AND the
    metadata carrying a non-null ``checksum_sha256``. The
    shape check is handled separately by
    :func:`_checksum_shape_blocker`.
    """
    expected_sha = payload.get("checksum_sha256")
    if not isinstance(expected_sha, str) or not expected_sha.strip():
        # Shape / null is handled by _checksum_shape_blocker.
        return None
    if not zip_path.is_file():
        # The zip is not staged. The presence check already
        # blocks via :func:`_presence_blocker` with
        # ``missing_raw``; this helper does not double-fire
        # the missing-zip signal here.
        return None
    expected_sha = expected_sha.strip().lower()
    actual_sha = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    if actual_sha != expected_sha:
        return (
            "UCDP readiness gate: zip checksum mismatch. "
            "metadata.json says checksum_sha256="
            f"{expected_sha!r} but the staged {zip_name} has "
            f"sha256={actual_sha!r}. Re-stage the UCDP "
            "bundle or correct metadata.json before running "
            "ingestion.",
            UCDP_CHECKSUM_MISMATCH,
        )
    return None


def _metadata_source_version_blocker(
    payload: dict[str, Any], canonical_version: str,
) -> tuple[str, str] | None:
    """Block if metadata ``source_version`` is missing or not canonical."""
    metadata_version = payload.get("source_version")
    if not isinstance(metadata_version, str) or not metadata_version.strip():
        return (
            "UCDP readiness gate: metadata.json "
            f"'source_version' must be the canonical version "
            f"{canonical_version!r}.",
            UNSUPPORTED_VERSION,
        )
    if metadata_version.strip() != canonical_version:
        return (
            f"UCDP readiness gate: metadata.json "
            f"'source_version' is {metadata_version.strip()!r}, "
            f"but the unified UCDP adapter supports only "
            f"canonical version {canonical_version!r}. "
            "Re-stage the UCDP bundle or correct "
            "metadata.json before running ingestion.",
            UNSUPPORTED_VERSION,
        )
    return None


__all__ = [
    "ACCEPTABLE_INGESTION_STATUSES",
    "REQUIRED_METADATA_FIELDS",
    "UCDP_CHECKSUM_MISMATCH",
    "UNSUPPORTED_VERSION",
    "_checksum_match_blocker",
    "_checksum_shape_blocker",
    "_ingestion_status_blocker",
    "_local_files_blocker",
    "_metadata_source_version_blocker",
    "_non_empty_string_blocker",
    "_presence_blocker",
    "_read_metadata_payload",
    "_required_fields_blocker",
]
