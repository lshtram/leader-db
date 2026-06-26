"""Per-field ``metadata.json`` validators for the
unified-source Transparency International CPI adapter.

Each validator returns a ``(message, code)`` blocker
tuple or ``None`` when the field is well-formed. Split
out of :mod:`._readiness` so the readiness orchestrator
stays focused on lifecycle ordering.

Validators accept the canonical primary metadata shape
(``source_name`` / ``source_version`` / ``source_url``
/ ``license_note`` / ``local_files`` /
``ingestion_status`` / ``coverage`` / optional
``checksum_sha256``). The staged CPI bundle metadata
already uses this primary shape so no legacy-key fallback
is needed. Mirror-vs-publisher attribution contract is
documented in ``docs/sources/attributions.md``
``transparency_cpi`` section. Full slice acceptance is
proven by ``tests/sources/test_transparency_cpi_adapter.py``.
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
# unsupported request source-version per SRC-REQ-009.
# Mirrors the PWT / Maddison / WGI / V-Dem / UCDP adapters'
# ``UNSUPPORTED_VERSION`` code so the CPI readiness
# envelope stays consistent.
UNSUPPORTED_VERSION: str = "unsupported_version"

# Module-local structured warning code used to surface a
# CSV checksum that is well-formed but does not match the
# staged CSV bytes. Mirrors the UCDP
# ``ucdp_checksum_mismatch`` / V-Dem
# ``vdem_checksum_mismatch`` pattern.
TRANSPARENCY_CPI_CHECKSUM_MISMATCH: str = (
    "transparency_cpi_checksum_mismatch"
)

# Required metadata fields -- PRIMARY shape (the canonical
# shape used by the PWT / Maddison / WDI / WGI / V-Dem /
# UCDP adapters). The CPI staged bundle already uses this
# primary shape so no legacy-key fallback is needed.
REQUIRED_METADATA_FIELDS: tuple[str, ...] = (
    "source_name",
    "source_version",
    "source_url",
    "license_note",
    "local_files",
    "ingestion_status",
    "coverage",
)

# Acceptable ``ingestion_status`` values. The canonical
# bundle uses ``downloaded``; ``pending`` and ``ingested``
# are also acceptable.
ACCEPTABLE_INGESTION_STATUSES: frozenset[str] = frozenset(
    {"pending", "downloaded", "ingested"},
)


def _read_metadata_payload(metadata_path: Path) -> dict[str, Any]:
    """Return the parsed ``metadata.json`` payload, or
    ``{}`` on any error.

    The readiness gate treats a malformed ``metadata.json``
    the same way as a missing one (downstream failure
    surfaces a structured ``MISSING_METADATA`` blocker).
    """
    if not metadata_path.is_file():
        return {}
    try:
        payload = json.loads(
            metadata_path.read_text(encoding="utf-8"),
        )
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _presence_blocker(
    metadata_path: Path,
    csv_path: Path,
    csv_name: str,
) -> tuple[str, str] | None:
    """Return a blocker tuple if ``metadata.json`` or the
    per-year CSV is missing.

    The mandatory readiness requirement is on raw-file
    presence: the gate returns ``ready=False`` with a
    structured ``MISSING_RAW`` error whenever the per-year
    CSV is NOT staged on disk, regardless of the
    metadata's ``local_files`` / ``checksum_sha256`` shape.
    A metadata-only bundle is intentionally NOT
    runner-ready.
    """
    if not metadata_path.is_file():
        return (
            "Transparency International CPI readiness gate: "
            "metadata.json missing at "
            f"{metadata_path}; place the canonical "
            "data/raw/transparency_cpi/metadata.json before "
            "running Stage 2.",
            MISSING_METADATA,
        )
    if not csv_path.is_file():
        # Mandatory raw-file presence: the runner must
        # not dispatch ``read_raw``/``transform`` against
        # a metadata-only bundle.
        return (
            "Transparency International CPI readiness "
            f"gate: {csv_name} missing at {csv_path}; "
            "place the canonical HDX-mirrored Transparency "
            "International CPI per-year CSV (download via "
            "the project workflow documented at "
            f"{csv_name}) before running Stage 2. The "
            "readiness gate requires the staged CSV -- "
            "a metadata-only bundle is NOT runner-ready.",
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
                "Transparency International CPI readiness "
                f"gate: metadata.json is missing required "
                f"field '{field}'.",
                MISSING_METADATA,
            )
    return None


def _local_files_blocker(
    payload: dict[str, Any],
    csv_name: str,
) -> tuple[str, str] | None:
    """Block if ``local_files`` is present but malformed.

    The canonical bundle metadata carries
    ``local_files=["transparency_cpi_2023.csv"]`` -- a
    list. The gate accepts:

    - a list containing the canonical per-year CSV;
    - an empty list ``[]`` (legacy-shape bundles that
      record the file later);
    - the field being absent entirely (older bundles
      predate the ``local_files`` annotation).

    A present-but-null ``local_files`` (e.g. an explicit
    ``"local_files": null`` in the staged JSON) is NOT
    accepted: the canonical metadata requires the field
    as a list, and a null value indicates a malformed
    bundle. The gate fires ``missing_metadata`` so the
    runner raises ``RuntimeError`` BEFORE ``read_raw`` /
    ``transform``.
    """
    # Distinguish absent vs. present-but-null: ``payload.get``
    # conflates both as ``None``. The absent case is
    # legacy-tolerant; the present-but-null case is a
    # malformed bundle and must block readiness.
    if "local_files" not in payload:
        return None
    local_files = payload["local_files"]
    if local_files is None:
        return (
            "Transparency International CPI readiness "
            "gate: metadata.json 'local_files' must be a "
            "list (possibly empty); got null. The canonical "
            "CPI bundle metadata requires 'local_files' as "
            "a list.",
            MISSING_METADATA,
        )
    if local_files == []:
        return None
    if not isinstance(local_files, list):
        return (
            "Transparency International CPI readiness "
            "gate: metadata.json 'local_files' must be a "
            "list (possibly empty); got "
            f"{type(local_files).__name__}.",
            MISSING_METADATA,
        )
    if csv_name not in local_files:
        return (
            "Transparency International CPI readiness "
            f"gate: metadata.json 'local_files' must "
            f"include {csv_name!r} when non-empty; got "
            f"{local_files!r}",
            MISSING_METADATA,
        )
    return None


def _ingestion_status_blocker(
    payload: dict[str, Any],
) -> tuple[str, str] | None:
    """Block if ``ingestion_status`` is not in the
    acceptable set."""
    status = payload.get("ingestion_status")
    if status not in ACCEPTABLE_INGESTION_STATUSES:
        return (
            "Transparency International CPI readiness "
            "gate: metadata.json 'ingestion_status' must "
            f"be one of "
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
    """Block if ``payload[field]`` is not a non-empty
    string."""
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        return (
            "Transparency International CPI readiness "
            f"gate: metadata.json '{field}' must be a "
            f"non-empty string naming {expected}.",
            MISSING_METADATA,
        )
    return None


def _checksum_shape_blocker(
    payload: dict[str, Any],
) -> tuple[str, str] | None:
    """Block if ``checksum_sha256`` is not null and not a
    valid 64-char hex SHA-256.

    Accepts ``None`` (canonical bundle shape) and a
    64-character hex SHA-256 string. A non-null,
    non-string, non-hex-64-character value fails with
    ``missing_metadata``.
    """
    expected_sha = payload.get("checksum_sha256")
    if expected_sha is None:
        return None
    if not isinstance(expected_sha, str) or not expected_sha.strip():
        return (
            "Transparency International CPI readiness "
            "gate: metadata.json 'checksum_sha256' must be "
            "either null (no CSV staged) or a non-empty "
            "64-character hex SHA-256 string; got empty "
            "value.",
            MISSING_METADATA,
        )
    stripped = expected_sha.strip().lower()
    if len(stripped) != 64 or any(
        ch not in "0123456789abcdef" for ch in stripped
    ):
        return (
            "Transparency International CPI readiness "
            "gate: metadata.json 'checksum_sha256' must be "
            f"a 64-character hex SHA-256 string; got "
            f"{expected_sha!r}.",
            MISSING_METADATA,
        )
    return None


def _checksum_match_blocker(
    payload: dict[str, Any],
    csv_path: Path,
    csv_name: str,
) -> tuple[str, str] | None:
    """Verify the staged CSV SHA-256 against
    ``checksum_sha256``.

    Returns a structured
    ``transparency_cpi_checksum_mismatch`` blocker when
    the staged CSV SHA-256 disagrees with the metadata
    field. The raw-file presence (staged CSV must exist
    on disk) is enforced separately by
    :func:`_presence_blocker`.
    """
    expected_sha = payload.get("checksum_sha256")
    if not isinstance(expected_sha, str) or not expected_sha.strip():
        # Shape / null is handled by
        # ``_checksum_shape_blocker``.
        return None
    if not csv_path.is_file():
        # The CSV is not staged. The presence check
        # already blocks via :func:`_presence_blocker`
        # with ``missing_raw``; this helper does not
        # double-fire the missing-CSV signal here.
        return None
    expected_sha = expected_sha.strip().lower()
    actual_sha = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    if actual_sha != expected_sha:
        return (
            "Transparency International CPI readiness "
            "gate: CSV checksum mismatch. metadata.json "
            f"says checksum_sha256={expected_sha!r} but "
            f"the staged {csv_name} has sha256="
            f"{actual_sha!r}. Re-stage the CPI bundle or "
            "correct metadata.json before running "
            "ingestion.",
            TRANSPARENCY_CPI_CHECKSUM_MISMATCH,
        )
    return None


def _metadata_source_version_blocker(
    payload: dict[str, Any],
    canonical_version: str,
) -> tuple[str, str] | None:
    """Block if metadata ``source_version`` is missing or
    not canonical."""
    metadata_version = payload.get("source_version")
    if not isinstance(metadata_version, str) or not metadata_version.strip():
        return (
            "Transparency International CPI readiness "
            "gate: metadata.json 'source_version' must be "
            f"the canonical version {canonical_version!r}.",
            UNSUPPORTED_VERSION,
        )
    if metadata_version.strip() != canonical_version:
        return (
            "Transparency International CPI readiness "
            "gate: metadata.json 'source_version' is "
            f"{metadata_version.strip()!r}, but the unified "
            "CPI adapter supports only canonical version "
            f"{canonical_version!r}. Re-stage the CPI "
            "bundle or correct metadata.json before "
            "running ingestion.",
            UNSUPPORTED_VERSION,
        )
    return None


__all__ = [
    "ACCEPTABLE_INGESTION_STATUSES",
    "REQUIRED_METADATA_FIELDS",
    "TRANSPARENCY_CPI_CHECKSUM_MISMATCH",
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
