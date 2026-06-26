"""Per-field ``metadata.json`` validators for the
unified-source BTI adapter.

Each validator returns a ``(message, code)`` blocker
tuple or ``None`` when the field is well-formed. Split
out of :mod:`._readiness` so the readiness orchestrator
stays focused on lifecycle ordering. The checksum
shape + match validators live in
:mod:`._checksum_validators` (a sibling module) so
this module stays under the 400-line convention.

Validators accept the canonical BTI bundle metadata
shape: ``source_name`` / ``source_version`` /
``source_url`` / ``license_note`` / ``checksum_sha256``
/ ``local_files`` / ``ingestion_status`` /
``download_date`` / ``coverage`` (the documented
``"country-edition (biennial snapshot, not time
series)"`` string) / ``years_available`` /
``edition_count`` / ``countries_per_edition`` /
``column_count`` / ``format`` / ``notes`` /
``source_url``.

Source-version semantics
------------------------

The canonical BTI default version is ``"BTI 2026"``
(the canonical stamp for the staged xlsx + the
canonical attribution block in
``docs/sources/attributions.md``). The staged bundle
metadata carries a verbose
``source_version`` stamp (``"BTI 2026 (covers
2024-2025); cumulative file covers 2006-2026
(biennial, 12 editions)"``); the unified adapter
accepts either stamp at the bundle's
``source_version`` field so the staged bundle does
not need to be rewritten as part of the migration. A
mismatched stamp fires the
``bti_metadata_version_mismatch`` warning code so
the runner raises ``RuntimeError`` BEFORE ``read_raw``
/ ``transform``.

Full slice acceptance is proven by
``tests/sources/test_bti_adapter.py``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from leaders_db.sources.warnings import (
    MISSING_METADATA,
    MISSING_RAW,
)

# Re-export the SHA-256 mismatch code + the
# checksum shape + match helpers from the
# checksum-validators sibling module so callers can
# ``from leaders_db.sources.adapters.bti
# ._metadata_validators import BTI_CHECKSUM_MISMATCH``.
from ._checksum_validators import (
    BTI_CHECKSUM_MISMATCH,
    _checksum_match_blocker,
    _checksum_shape_blocker,
)

# Module-local structured warning code used to
# reject an unsupported request source-version per
# SRC-REQ-009. Mirrors WGI / V-Dem / UCDP / CPI /
# PTS / RSF ``UNSUPPORTED_VERSION``.
UNSUPPORTED_VERSION: str = "unsupported_version"

# Structured warning code: bundle ``source_version``
# mismatch. Distinct from ``UNSUPPORTED_VERSION``
# because the bundle-stamped field is a verbose
# acquisition stamp (``"BTI 2026 (covers 2024-2025);
# cumulative file covers 2006-2026 (biennial, 12
# editions)"``), while the request-scoped stamp is
# always the brief canonical stamp (``"BTI 2026"``).
BTI_METADATA_VERSION_MISMATCH: str = (
    "bti_metadata_version_mismatch"
)

# Required metadata fields (canonical BTI bundle
# shape; the staged bundle carries every field
# listed below per
# ``data/raw/bti/metadata.json``).
REQUIRED_METADATA_FIELDS: tuple[str, ...] = (
    "source_name",
    "source_version",
    "download_date",
    "coverage",
    "years_available",
    "license_note",
    "local_files",
    "ingestion_status",
    "source_url",
    "checksum_sha256",
    "edition_count",
    "countries_per_edition",
    "column_count",
    "format",
    "notes",
)

# Acceptable ``ingestion_status`` values. The
# canonical BTI bundle uses ``"downloaded"`` (per
# ``data/raw/bti/metadata.json``); ``pending`` and
# ``ingested`` are also acceptable.
ACCEPTABLE_INGESTION_STATUSES: frozenset[str] = frozenset(
    {"pending", "downloaded", "ingested"},
)

# Canonical bundle ``local_files`` shape -- the
# single cumulative xlsx file the unified adapter
# reads (plus the optional codebook PDF; the
# codebook is a documentation artifact, not raw
# data the unified adapter consumes).
CANONICAL_LOCAL_FILES_PRIMARY: str = "BTI_2006-2026_Scores.xlsx"
CANONICAL_LOCAL_FILES_OPTIONAL: str = "BTI2026_Codebook.pdf"


def _read_metadata_payload(metadata_path: Path) -> dict[str, Any]:
    """Return the parsed ``metadata.json`` payload,
    or ``{}`` on any error.

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
    """Block if ``metadata.json`` or the staged xlsx
    is missing.

    The gate returns ``ready=False`` with a structured
    ``MISSING_RAW`` error whenever the staged xlsx is
    NOT on disk, regardless of the metadata's
    ``local_files`` / ``checksum_sha256`` shape.
    """
    if not metadata_path.is_file():
        return (
            "BTI readiness gate: metadata.json missing "
            f"at {metadata_path}; place the canonical "
            "data/raw/bti/metadata.json before running "
            "Stage 2.",
            MISSING_METADATA,
        )
    if not xlsx_path.is_file():
        return (
            "BTI readiness gate: "
            f"{xlsx_name} missing at {xlsx_path}; place "
            "the canonical BTI_2006-2026_Scores.xlsx "
            "(download via the project workflow "
            "documented at https://bti-project.org/) "
            "before running Stage 2. The readiness "
            "gate requires the staged xlsx -- a "
            "metadata-only bundle is NOT runner-ready.",
            MISSING_RAW,
        )
    return None


def _required_fields_blocker(
    payload: dict[str, Any],
) -> tuple[str, str] | None:
    """Block if any canonical required field is
    absent."""
    for field in REQUIRED_METADATA_FIELDS:
        if field not in payload:
            return (
                "BTI readiness gate: metadata.json is "
                f"missing required field '{field}'.",
                MISSING_METADATA,
            )
    return None


def _local_files_blocker(
    payload: dict[str, Any],
    xlsx_name: str,
) -> tuple[str, str] | None:
    """Block if ``local_files`` is present but
    malformed.

    Accepts a list containing the canonical xlsx
    filename or the field being absent. Empty lists and
    present-but-null ``local_files`` are NOT accepted.
    """
    if "local_files" not in payload:
        return None
    local_files = payload["local_files"]
    if local_files is None:
        return (
            "BTI readiness gate: metadata.json "
            "'local_files' must be a non-empty list; "
            "got null. The canonical BTI "
            "bundle metadata requires 'local_files' as "
            "a list.",
            MISSING_METADATA,
        )
    if local_files == []:
        return (
            "BTI readiness gate: metadata.json "
            "'local_files' must include "
            f"{xlsx_name!r}; got an empty list.",
            MISSING_METADATA,
        )
    if not isinstance(local_files, list):
        return (
            "BTI readiness gate: metadata.json "
            "'local_files' must be a non-empty list; got "
            f"{type(local_files).__name__}.",
            MISSING_METADATA,
        )
    if xlsx_name not in local_files:
        return (
            "BTI readiness gate: metadata.json "
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
            "BTI readiness gate: metadata.json "
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
            "BTI readiness gate: metadata.json "
            f"'{field}' must be a non-empty string "
            f"naming {expected}.",
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
            "BTI readiness gate: metadata.json "
            f"'{field}' must be a positive integer "
            f"naming {expected}; got {value!r}.",
            MISSING_METADATA,
        )
    return None


def _metadata_source_version_blocker(
    payload: dict[str, Any],
    *,
    canonical_version: str,
) -> tuple[str, str] | None:
    """Block if metadata ``source_version`` is missing
    or not canonical.

    The staged bundle carries a verbose
    ``source_version`` stamp (``"BTI 2026 (covers
    2024-2025); cumulative file covers 2006-2026
    (biennial, 12 editions)"``). The unified adapter
    accepts either the verbose stamp OR the brief
    canonical stamp (``"BTI 2026"``); any other
    value fires the ``bti_metadata_version_mismatch``
    warning code so the runner raises ``RuntimeError``
    BEFORE ``read_raw`` / ``transform``.
    """
    version_field = payload.get("source_version")
    if not (
        isinstance(version_field, str)
        and version_field.strip()
    ):
        return (
            "BTI readiness gate: metadata.json "
            "'source_version' is missing or not a "
            "non-empty string. The canonical BTI "
            "default version is "
            f"{canonical_version!r}; the staged "
            "bundle carries a verbose acquisition "
            "stamp that the unified adapter accepts "
            "verbatim.",
            BTI_METADATA_VERSION_MISMATCH,
        )
    # Accept either the brief canonical stamp OR
    # the verbose acquisition stamp (the staged
    # bundle's documented ``source_version``). Any
    # other value fires the mismatch warning code.
    stripped = version_field.strip()
    verbose_stamp = (
        "BTI 2026 (covers 2024-2025); cumulative "
        "file covers 2006-2026 (biennial, 12 "
        "editions)"
    )
    accepted_stamps = {canonical_version, verbose_stamp}
    if stripped in accepted_stamps:
        return None
    return (
        "BTI readiness gate: metadata.json "
        f"'source_version' is {stripped!r}, but the "
        f"unified BTI adapter supports only "
        f"canonical version {canonical_version!r} "
        f"(or the verbose acquisition stamp "
        f"{verbose_stamp!r}).",
        BTI_METADATA_VERSION_MISMATCH,
    )


__all__ = [
    "ACCEPTABLE_INGESTION_STATUSES",
    "BTI_CHECKSUM_MISMATCH",
    "BTI_METADATA_VERSION_MISMATCH",
    "CANONICAL_LOCAL_FILES_OPTIONAL",
    "CANONICAL_LOCAL_FILES_PRIMARY",
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
