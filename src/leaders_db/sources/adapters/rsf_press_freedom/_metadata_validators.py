"""Per-field ``metadata.json`` validators for the
unified-source RSF adapter.

Each validator returns a ``(message, code)`` blocker
tuple or ``None`` when the field is well-formed. Split
out of :mod:`._readiness` so the readiness orchestrator
stays focused on lifecycle ordering.

Validators accept the canonical primary metadata shape
(``source_name`` / ``source_version`` / ``source_url``
/ ``license_note`` / ``local_files`` /
``ingestion_status`` / ``coverage`` / per-file
``files`` array) used by the canonical RSF bundle at
``data/raw/rsf_press_freedom/metadata.json``. The RSF
bundle ships ``source_version="annual CSV series
2002-2026, acquired 2026-06-18"`` (the verbose
acquisition-date stamp); the unified adapter accepts
the brief canonical stamp ``"RSF Press Freedom Index
2026"`` OR the verbose acquisition stamp. The
canonical version stamp is the brief
``"RSF Press Freedom Index 2026"`` form so the report-
facing attribution block matches the staged metadata
version byte-for-byte.

Checksum semantics
------------------

The RSF canonical bundle metadata does NOT carry a
top-level SHA-256 field; instead it carries a per-file
``files`` array with one record per year file
(``year`` / ``file`` / ``bytes`` / ``sha256``). The
unified adapter's readiness gate validates the
metadata shape + the per-file SHA-256 of the staged
per-year CSVs (when present). A metadata-only bundle
(``local_files=[]`` or a ``files`` array with no
matching per-year record) is intentionally NOT
runner-ready; the gate returns ``ready=False`` with a
structured ``MISSING_RAW`` error before the runner
dispatches ``read_raw`` / ``transform``.

Source-version semantics
------------------------

The canonical RSF default version is ``"RSF Press
Freedom Index 2026"`` (the brief canonical stamp
matching the live 2026 RSF release + the canonical
attribution block in ``docs/sources/attributions.md``).
The staged bundle carries the verbose acquisition-
date stamp ``"annual CSV series 2002-2026, acquired
2026-06-18"`` (per the bundle's ``source_version``
field). The unified adapter validates either stamp at
the bundle's ``source_version`` field; a mismatched
stamp fires the
``rsf_metadata_version_mismatch`` warning code so the
runner raises ``RuntimeError`` BEFORE ``read_raw`` /
``transform``.

Full slice acceptance is proven by
``tests/sources/test_rsf_press_freedom_adapter.py``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from leaders_db.sources.warnings import (
    MISSING_METADATA,
)

# Re-export the per-file checksum + files array
# helpers from the sibling :mod:`._files_validators`
# module so callers can ``from
# leaders_db.sources.adapters.rsf_press_freedom
# ._metadata_validators import
# _checksum_match_blocker`` (and the legacy
# :mod:`._readiness` orchestrator resolves them via
# the same import path).
from ._files_validators import (
    _checksum_match_blocker,
    _find_files_entry,
)

# Re-export the per-file ``files`` array + bundle
# ``source_version`` stamp validators from the sibling
# :mod:`._metadata_version_validators` module so
# callers can ``from
# leaders_db.sources.adapters.rsf_press_freedom
# ._metadata_validators import
# _files_blocker`` (and the legacy :mod:`._readiness`
# orchestrator resolves them via the same import
# path).
from ._metadata_version_validators import (
    _files_blocker as _files_blocker_impl,
)
from ._metadata_version_validators import (
    _metadata_source_version_blocker as _metadata_source_version_blocker_impl,
)

# Module-local structured warning code used to reject
# an unsupported request source-version per SRC-REQ-009.
# Mirrors the PTS / UCDP / V-Dem / CPI / PWT / Maddison
# / WGI / WDI ``UNSUPPORTED_VERSION`` code so the RSF
# readiness envelope stays consistent.
UNSUPPORTED_VERSION: str = "unsupported_version"

# Module-local structured warning code used to surface a
# bundle ``source_version`` stamp that does not match
# the canonical stamp. Distinct from
# ``UNSUPPORTED_VERSION`` because the bundle-stamped
# field is a verbose acquisition stamp ("annual CSV
# series 2002-2026, acquired 2026-06-18") while the
# request-scoped stamp is always the brief canonical
# stamp ("RSF Press Freedom Index 2026").
RSF_PRESS_FREEDOM_METADATA_VERSION_MISMATCH: str = (
    "rsf_press_freedom_metadata_version_mismatch"
)

# Module-local structured warning code used to surface
# a per-year CSV SHA-256 that is well-formed but does
# not match the staged file. Mirrors the CPI / UCDP /
# V-Dem ``*_checksum_mismatch`` pattern.
RSF_PRESS_FREEDOM_CHECKSUM_MISMATCH: str = (
    "rsf_press_freedom_checksum_mismatch"
)

# Required metadata fields -- the canonical primary
# shape used by the PWT / Maddison / WDI / WGI / V-Dem /
# UCDP / CPI adapters. The RSF staged bundle already
# uses this primary shape so no legacy-key fallback is
# needed. ``source_version`` is a string stamp
# (validated below in
# :func:`_metadata_source_version_blocker`).
REQUIRED_METADATA_FIELDS: tuple[str, ...] = (
    "source_name",
    "source_version",
    "source_url",
    "license_note",
    "local_files",
    "ingestion_status",
    "coverage",
    "files",
)

# Acceptable ``ingestion_status`` values. The canonical
# bundle uses ``downloaded`` (per
# ``data/raw/rsf_press_freedom/metadata.json``);
# ``pending`` and ``ingested`` are also acceptable.
ACCEPTABLE_INGESTION_STATUSES: frozenset[str] = frozenset(
    {"pending", "downloaded", "ingested"},
)

# Canonical bundle ``source_version`` stamps. The brief
# canonical stamp is the report-facing version
# (``"RSF Press Freedom Index 2026"``); the verbose
# acquisition stamp is the staged metadata's
# ``source_version`` (``"annual CSV series 2002-2026,
# acquired 2026-06-18"``). The unified adapter accepts
# either stamp at the bundle's ``source_version`` field
# so the staged bundle does not need to be rewritten
# as part of the migration.
RSF_PRESS_FREEDOM_CANONICAL_VERSION_STAMP: str = (
    "RSF Press Freedom Index 2026"
)
RSF_PRESS_FREEDOM_BUNDLE_VERSION_STAMP: str = (
    "annual CSV series 2002-2026, acquired 2026-06-18"
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
) -> tuple[str, str] | None:
    """Block if ``metadata.json`` is missing.

    The gate returns ``ready=False`` with a structured
    ``MISSING_METADATA`` error when the metadata is
    absent. The raw-file presence check is enforced
    per-year in the readiness orchestrator
    (:func:`check_metadata_well_formed` in
    :mod:`._readiness`) so a metadata-only bundle is
    intentionally NOT runner-ready.
    """
    if not metadata_path.is_file():
        return (
            "RSF readiness gate: metadata.json missing "
            f"at {metadata_path}; place the canonical "
            "data/raw/rsf_press_freedom/metadata.json "
            "before running Stage 2.",
            MISSING_METADATA,
        )
    return None


def _required_fields_blocker(
    payload: dict[str, Any],
) -> tuple[str, str] | None:
    """Block if any canonical required field is absent."""
    for field in REQUIRED_METADATA_FIELDS:
        if field not in payload:
            return (
                "RSF readiness gate: metadata.json is "
                f"missing required field '{field}'.",
                MISSING_METADATA,
            )
    return None


def _local_files_blocker(
    payload: dict[str, Any],
) -> tuple[str, str] | None:
    """Block if ``local_files`` is present-but-malformed.

    Accepts a list of per-year CSV filenames (the
    canonical shape: 24 entries), an empty list ``[]``,
    or the field being absent. A present-but-null
    ``local_files`` is NOT accepted.
    """
    if "local_files" not in payload:
        return None
    local_files = payload["local_files"]
    if local_files is None:
        return (
            "RSF readiness gate: metadata.json "
            "'local_files' must be a list (possibly "
            "empty); got null. The canonical RSF bundle "
            "metadata requires 'local_files' as a list.",
            MISSING_METADATA,
        )
    if not isinstance(local_files, list):
        return (
            "RSF readiness gate: metadata.json "
            "'local_files' must be a list (possibly "
            "empty); got "
            f"{type(local_files).__name__}.",
            MISSING_METADATA,
        )
    for entry in local_files:
        if not isinstance(entry, str) or not entry.strip():
            return (
                "RSF readiness gate: metadata.json "
                "'local_files' entries must be non-empty "
                "strings; got "
                f"{local_files!r}.",
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
            "RSF readiness gate: metadata.json "
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
            "RSF readiness gate: metadata.json "
            f"'{field}' must be a non-empty string naming "
            f"{expected}.",
            MISSING_METADATA,
        )
    return None


def _files_blocker(
    payload: dict[str, Any],
) -> tuple[str, str] | None:
    """Re-exported from
    :mod:`._metadata_version_validators` for
    symmetry with the readiness orchestrator's import
    path. See the canonical helper for the full
    docstring.
    """
    return _files_blocker_impl(payload)


def _metadata_source_version_blocker(
    payload: dict[str, Any],
    *,
    canonical_version: str,
) -> tuple[str, str] | None:
    """Re-exported from
    :mod:`._metadata_version_validators` for
    symmetry with the readiness orchestrator's import
    path. See the canonical helper for the full
    docstring.
    """
    return _metadata_source_version_blocker_impl(
        payload, canonical_version=canonical_version,
    )


__all__ = [
    "ACCEPTABLE_INGESTION_STATUSES",
    "REQUIRED_METADATA_FIELDS",
    "RSF_PRESS_FREEDOM_BUNDLE_VERSION_STAMP",
    "RSF_PRESS_FREEDOM_CANONICAL_VERSION_STAMP",
    "RSF_PRESS_FREEDOM_CHECKSUM_MISMATCH",
    "RSF_PRESS_FREEDOM_METADATA_VERSION_MISMATCH",
    "UNSUPPORTED_VERSION",
    "_checksum_match_blocker",
    "_files_blocker",
    "_find_files_entry",
    "_ingestion_status_blocker",
    "_local_files_blocker",
    "_metadata_source_version_blocker",
    "_non_empty_string_blocker",
    "_presence_blocker",
    "_read_metadata_payload",
    "_required_fields_blocker",
]
