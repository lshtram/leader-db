"""Per-field ``metadata.json`` validators for the
unified-source PTS adapter.

Each validator returns a ``(message, code)`` blocker
tuple or ``None`` when the field is well-formed. Split
out of :mod:`._readiness` so the readiness orchestrator
stays focused on lifecycle ordering. The SHA-256
checksum validators live in :mod:`._checksum_validators`
(a sibling module) so this module stays under the
400-line convention.

Validators accept the canonical PTS bundle metadata
shape: ``source_name`` / ``version`` (or legacy
``source_version``) / ``source_url`` / ``license`` /
``coverage_start_year`` / ``coverage_end_year`` /
``file_format`` / ``file_size_bytes`` / ``sha256`` /
``ingestion_status`` / ``notes`` / ``local_files``.
The canonical PTS bundle metadata carries
``version="2025"`` (bare-year stamp) + ``sha256`` +
``local_files=["PTS-2025.xlsx"]``; the unified adapter
also accepts the legacy ``source_version="PTS-2025"``
field.

Source-version semantics
------------------------

The canonical PTS default version is ``"PTS-2025"``
(the canonical stamp for the staged xlsx / release
metadata + the legacy ``register_pts_source`` upsert
key in ``src/leaders_db/ingest/pts_db.py``). The
staged bundle metadata carries ``version: "2025"`` (a
4-digit year stamp); the unified adapter validates
``version == "2025"`` when present (and
``source_version == "PTS-2025"`` when ``version`` is
absent). A mismatch fires the
``pts_metadata_version_mismatch`` warning code so the
runner raises ``RuntimeError`` BEFORE ``read_raw`` /
``transform``.

Full slice acceptance is proven by
``tests/sources/test_pts_adapter.py``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from leaders_db.sources.warnings import (
    MISSING_METADATA,
    MISSING_RAW,
)

# Module-local structured warning code used to reject
# an unsupported request source-version per SRC-REQ-009.
# Mirrors WGI / V-Dem / UCDP / CPI
# ``UNSUPPORTED_VERSION``.
UNSUPPORTED_VERSION: str = "unsupported_version"

# Structured warning code: bundle ``version`` /
# ``source_version`` mismatch. Distinct from
# ``UNSUPPORTED_VERSION`` because the bundle-stamped
# field is either ``"2025"`` or ``"PTS-2025"``, while
# the request-scoped stamp is always ``"PTS-2025"``.
PTS_METADATA_VERSION_MISMATCH: str = (
    "pts_metadata_version_mismatch"
)

# Re-export the SHA-256 mismatch code from the
# checksum-validators sibling module so callers can
# ``from leaders_db.sources.adapters.pts._metadata_validators
# import PTS_CHECKSUM_MISMATCH``.
from ._checksum_validators import (  # noqa: E402
    PTS_CHECKSUM_MISMATCH,
    _checksum_match_blocker,
    _checksum_shape_blocker,
)

# Required metadata fields (canonical PTS bundle
# shape). The gate tolerates the legacy
# ``source_version`` field when ``version`` is absent
# (and vice versa) via
# :func:`_metadata_source_version_blocker`.
REQUIRED_METADATA_FIELDS: tuple[str, ...] = (
    "source_name",
    "version",
    "source_url",
    "license",
    "coverage_start_year",
    "coverage_end_year",
    "file_format",
    "file_size_bytes",
    "sha256",
    "ingestion_status",
    "notes",
    "local_files",
)

# Acceptable ``ingestion_status`` values. The canonical
# bundle uses ``available`` (verified live 2026-06-18);
# ``pending`` / ``downloaded`` / ``ingested`` also pass.
ACCEPTABLE_INGESTION_STATUSES: frozenset[str] = frozenset(
    {"pending", "downloaded", "available", "ingested"},
)

# Canonical PTS bundle ``local_files`` shape -- the
# single xlsx file the unified adapter reads.
CANONICAL_LOCAL_FILES: tuple[str, ...] = ("PTS-2025.xlsx",)

# Canonical bundle ``version`` stamp (the bare-year
# stamp the staged metadata carries under ``version``).
PTS_BUNDLE_VERSION_STAMP: str = "2025"


def _read_metadata_payload(metadata_path: Path) -> dict[str, Any]:
    """Return the parsed ``metadata.json`` payload, or
    ``{}`` on any error.

    A malformed ``metadata.json`` is treated the same
    as a missing one (downstream failure surfaces a
    structured ``MISSING_METADATA`` blocker).
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
    xlsx_path: Path,
    xlsx_name: str,
) -> tuple[str, str] | None:
    """Block if ``metadata.json`` or the staged xlsx is
    missing.

    The gate returns ``ready=False`` with a structured
    ``MISSING_RAW`` error whenever the staged xlsx is
    NOT on disk, regardless of the metadata's
    ``local_files`` / ``sha256`` shape.
    """
    if not metadata_path.is_file():
        return (
            "PTS readiness gate: metadata.json missing "
            f"at {metadata_path}; place the canonical "
            "data/raw/political_terror_scale/metadata.json "
            "before running Stage 2.",
            MISSING_METADATA,
        )
    if not xlsx_path.is_file():
        return (
            "PTS readiness gate: "
            f"{xlsx_name} missing at {xlsx_path}; place "
            "the canonical PTS-2025.xlsx (download via "
            "the project workflow documented at "
            "https://www.politicalterrorscale.org/) "
            "before running Stage 2. The readiness gate "
            "requires the staged xlsx -- a metadata-only "
            "bundle is NOT runner-ready.",
            MISSING_RAW,
        )
    return None


def _required_fields_blocker(
    payload: dict[str, Any],
) -> tuple[str, str] | None:
    """Block if any canonical required field is absent.

    The ``version`` field is the canonical stamp the
    staged bundle carries; the legacy ``source_version``
    field is accepted when ``version`` is absent.
    """
    for field in REQUIRED_METADATA_FIELDS:
        if field not in payload:
            # Accept the legacy ``source_version``
            # field when ``version`` is absent.
            if field == "version" and (
                "source_version" in payload
            ):
                continue
            return (
                "PTS readiness gate: metadata.json is "
                f"missing required field '{field}'.",
                MISSING_METADATA,
            )
    return None


def _local_files_blocker(
    payload: dict[str, Any],
    xlsx_name: str,
) -> tuple[str, str] | None:
    """Block if ``local_files`` is present but malformed.

    Accepts a list containing the canonical xlsx
    filename, an empty list ``[]``, or the field being
    absent. A present-but-null ``local_files`` is NOT
    accepted.
    """
    if "local_files" not in payload:
        return None
    local_files = payload["local_files"]
    if local_files is None:
        return (
            "PTS readiness gate: metadata.json "
            "'local_files' must be a list (possibly "
            "empty); got null. The canonical PTS bundle "
            "metadata requires 'local_files' as a list.",
            MISSING_METADATA,
        )
    if local_files == []:
        return None
    if not isinstance(local_files, list):
        return (
            "PTS readiness gate: metadata.json "
            "'local_files' must be a list (possibly "
            "empty); got "
            f"{type(local_files).__name__}.",
            MISSING_METADATA,
        )
    if xlsx_name not in local_files:
        return (
            "PTS readiness gate: metadata.json "
            f"'local_files' must include {xlsx_name!r} "
            f"when non-empty; got {local_files!r}",
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
            "PTS readiness gate: metadata.json "
            "'ingestion_status' must be one of "
            f"{sorted(ACCEPTABLE_INGESTION_STATUSES)}; "
            f"got {status!r}.",
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
            "PTS readiness gate: metadata.json "
            f"'{field}' must be a non-empty string naming "
            f"{expected}.",
            MISSING_METADATA,
        )
    return None


def _positive_int_blocker(
    payload: dict[str, Any],
    field: str,
    expected: str,
) -> tuple[str, str] | None:
    """Block if ``payload[field]`` is not a positive
    integer."""
    value = payload.get(field)
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value <= 0
    ):
        return (
            "PTS readiness gate: metadata.json "
            f"'{field}' must be a positive integer naming "
            f"{expected}; got {value!r}.",
            MISSING_METADATA,
        )
    return None


def _metadata_source_version_blocker(
    payload: dict[str, Any],
    *,
    canonical_version: str,
) -> tuple[str, str] | None:
    """Block if metadata ``version`` or
    ``source_version`` is missing or not canonical.

    The staged bundle carries ``version: "2025"`` (the
    bare-year stamp). When the bundle carries
    ``version``, it must equal ``"2025"``; when the
    bundle carries ``source_version``, it must equal
    the canonical ``"PTS-2025"``.
    """
    version_field = payload.get("version")
    source_version_field = payload.get("source_version")

    if isinstance(version_field, str) and version_field.strip():
        if version_field.strip() != PTS_BUNDLE_VERSION_STAMP:
            return (
                "PTS readiness gate: metadata.json "
                f"'version' is {version_field.strip()!r}, "
                f"but the unified PTS adapter supports "
                f"only canonical bundle version "
                f"{PTS_BUNDLE_VERSION_STAMP!r}.",
                PTS_METADATA_VERSION_MISMATCH,
            )
    if isinstance(
        source_version_field, str,
    ) and source_version_field.strip():
        if source_version_field.strip() != canonical_version:
            return (
                "PTS readiness gate: metadata.json "
                "'source_version' is "
                f"{source_version_field.strip()!r}, but "
                "the unified PTS adapter supports only "
                f"canonical version {canonical_version!r}.",
                PTS_METADATA_VERSION_MISMATCH,
            )
    return None


__all__ = [
    "ACCEPTABLE_INGESTION_STATUSES",
    "CANONICAL_LOCAL_FILES",
    "PTS_BUNDLE_VERSION_STAMP",
    "PTS_CHECKSUM_MISMATCH",
    "PTS_METADATA_VERSION_MISMATCH",
    "REQUIRED_METADATA_FIELDS",
    "UNSUPPORTED_VERSION",
    "_checksum_match_blocker",
    "_checksum_shape_blocker",
    "_ingestion_status_blocker",
    "_local_files_blocker",
    "_metadata_source_version_blocker",
    "_non_empty_string_blocker",
    "_positive_int_blocker",
    "_presence_blocker",
    "_read_metadata_payload",
    "_required_fields_blocker",
]
