"""World Bank WDI bundle-metadata readiness validators.

This module owns the per-field ``metadata.json`` validation that
runs BEFORE the unified adapter's cache reader opens staged
per-(year, indicator) cache payloads. The readiness gate's
:func:`leaders_db.sources.adapters.world_bank_wdi._readiness.check_metadata_well_formed`
orchestrator composes these helpers in the documented phase
order (file presence → JSON parse → per-field validation).

Split out of
:mod:`leaders_db.sources.adapters.world_bank_wdi._readiness` so
the cache-availability gate can live in a sibling
:mod:`_cache_readiness` module and the orchestrator module
stays focused on lifecycle wiring. The split keeps each
module under the 400-line convention.

Why a separate metadata module
------------------------------

The metadata gate enforces four orthogonal concerns:

1. File presence + JSON parse (defensive: malformed JSON must
   never silently fall through to cache loading).
2. Required-field presence (mirrors the Maddison / PWT
   readiness contract: the union of fields the unified gate
   inspects).
3. Per-field value shape (string non-empty, ``local_files``
   includes ``cache/``, ``ingestion_status == 'downloaded'``,
   ``source_version`` is the canonical stamp).
4. Checksum contract (WDI is API/cache-backed; the staged
   ``metadata.json`` carries ``checksum_sha256: null`` with
   a documented ``checksum_note``, OR a flat 64-char hex
   SHA-256, OR a per-file dict -- three canonical shapes
   per the unified source-bundle contract).

Splitting these from the cache-availability gate keeps each
helper single-purpose and testable in isolation. The gate
orchestrator composes them in one place.
"""

from __future__ import annotations

import json
import re
from typing import Any

from leaders_db.sources.warnings import MISSING_METADATA

# Module-local structured warning code used by
# :func:`_metadata_source_version_blocker` to reject an
# unsupported metadata ``source_version`` per SRC-REQ-009.
# Mirrors the PWT / Maddison ``UNSUPPORTED_VERSION`` code so
# the WDI readiness envelope stays consistent with the rest of
# the unified source subsystem. Re-exported from
# :mod:`._readiness` for backward compatibility with callers
# that import ``UNSUPPORTED_VERSION`` from the umbrella module.
UNSUPPORTED_VERSION: str = "unsupported_version"

# Required metadata fields. Mirrors the Maddison / PWT
# readiness contract: the union of fields the unified gate
# inspects before loading cached payloads. ``checksum_sha256``
# is in this tuple so the gate refuses a bundle whose checksum
# field is missing entirely; when it is present as ``null`` the
# gate then demands an actionable ``checksum_note`` (see
# :func:`_checksum_blocker`).
REQUIRED_METADATA_FIELDS: tuple[str, ...] = (
    "source_version",
    "source_url",
    "license_note",
    "local_files",
    "ingestion_status",
    "coverage",
    "checksum_sha256",
)

# SHA-256 hex shape: exactly 64 lowercase-or-uppercase
# hexadecimal characters. Used to validate the
# ``checksum_sha256`` flat-string and per-file dict shapes.
_SHA256_HEX_PATTERN: re.Pattern[str] = re.compile(r"^[0-9a-fA-F]{64}$")

# Keywords the ``checksum_note`` must mention when
# ``checksum_sha256`` is ``null``. The canonical WDI bundle
# notes that checksums are managed per cached response / per
# API request; the gate requires at least one of the
# documented tokens (case-insensitive) so a developer can
# tell that the null is deliberate, not an oversight.
_CHECKSUM_NOTE_RATIONALE_KEYWORDS: tuple[str, ...] = (
    "api",
    "cache",
    "per-response",
    "per response",
    "checksum",
)


def _is_actionable_checksum_note(value: Any) -> bool:
    """Return True iff ``value`` is a non-empty string mentioning
    at least one documented API/cache/per-response/checksum
    rationale token.

    The keyword check is intentionally permissive (any of
    ``api``, ``cache``, ``per-response`` / ``per response``,
    or ``checksum``) so a developer has multiple natural ways
    to document the per-response checksum omission; the gate
    refuses a vague or empty note because a null checksum with
    no rationale is indistinguishable from a missing checksum.
    """
    if not isinstance(value, str):
        return False
    lowered = value.strip().lower()
    if not lowered:
        return False
    return any(
        keyword in lowered
        for keyword in _CHECKSUM_NOTE_RATIONALE_KEYWORDS
    )


def _validate_checksum_dict(
    checksum: dict[Any, Any],
) -> tuple[str, str] | None:
    """Validate the per-file ``checksum_sha256`` dict shape.

    Returns a ``(blocker_message, MISSING_METADATA)`` tuple
    when the dict is empty, carries a non-string key, or
    carries a non-hex value. Returns ``None`` when every
    key / value pair validates. Extracted from
    :func:`_checksum_blocker` to keep the latter under the
    documented 6-return-statement ceiling (PLR0911).
    """
    if not checksum:
        return (
            "World Bank WDI readiness gate: metadata.json "
            "'checksum_sha256' is a dict but is empty; "
            "either set the dict to a non-empty per-file "
            "mapping or remove 'checksum_sha256' and "
            "document the per-response checksum contract in "
            "'checksum_note'.",
            MISSING_METADATA,
        )
    for file_name, value in checksum.items():
        if not isinstance(file_name, str) or not file_name.strip():
            return (
                "World Bank WDI readiness gate: metadata.json "
                "'checksum_sha256' dict keys must be non-empty "
                "file-name strings; got "
                f"{type(file_name).__name__}.",
                MISSING_METADATA,
            )
        if (
            not isinstance(value, str)
            or not _SHA256_HEX_PATTERN.match(value.strip())
        ):
            return (
                "World Bank WDI readiness gate: metadata.json "
                f"'checksum_sha256' value for {file_name!r} "
                "must be a 64-character hexadecimal SHA-256; "
                f"got {type(value).__name__}.",
                MISSING_METADATA,
            )
    return None


def _read_metadata_payload(metadata_path: Any) -> dict[str, Any]:
    """Return the parsed ``metadata.json`` payload, or ``{}`` on any error.

    The function is defensive: a missing file, ``OSError`` on
    read, or ``json.JSONDecodeError`` all return ``{}`` so the
    readiness gate's required-field check can surface a single
    actionable blocker (parse failed / missing field) instead
    of letting an exception bubble up through the runner.
    """
    from pathlib import Path  # local import keeps module surface small

    if not isinstance(metadata_path, Path):
        return {}
    if not metadata_path.is_file():
        return {}
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _presence_blocker(
    metadata_path: Any,
) -> tuple[str, str] | None:
    """Block if ``metadata.json`` is missing from the bundle."""
    from pathlib import Path

    if not isinstance(metadata_path, Path) or not metadata_path.is_file():
        return (
            "World Bank WDI readiness gate: metadata.json missing "
            f"at {metadata_path}; place the canonical "
            "data/raw/world_bank_wdi/metadata.json before running "
            "Stage 2.",
            MISSING_METADATA,
        )
    return None


def _required_fields_blocker(
    payload: dict[str, Any],
) -> tuple[str, str] | None:
    """Block if any canonical required metadata field is absent."""
    for field in REQUIRED_METADATA_FIELDS:
        if field not in payload:
            return (
                f"World Bank WDI readiness gate: metadata.json is "
                f"missing required field '{field}'.",
                MISSING_METADATA,
            )
    return None


def _local_files_blocker(
    payload: dict[str, Any],
) -> tuple[str, str] | None:
    """Block if ``local_files`` does not include the canonical cache marker.

    The WDI bundle's ``local_files`` field is documented as
    ``["cache/"]`` in the staged metadata. We accept the
    trailing-slash cache directory name; we ALSO accept the
    bare ``"cache"`` (without slash) for forward compatibility.
    """
    from ._descriptor import WORLD_BANK_WDI_CACHE_DIR_NAME

    local_files = payload.get("local_files")
    if not isinstance(local_files, list):
        return (
            "World Bank WDI readiness gate: metadata.json "
            "'local_files' must be a list; got "
            f"{type(local_files).__name__}.",
            MISSING_METADATA,
        )
    accepted = {WORLD_BANK_WDI_CACHE_DIR_NAME, f"{WORLD_BANK_WDI_CACHE_DIR_NAME}/"}
    if not any(item in accepted for item in local_files if isinstance(item, str)):
        return (
            f"World Bank WDI readiness gate: metadata.json "
            f"'local_files' must include {WORLD_BANK_WDI_CACHE_DIR_NAME!r}; "
            f"got {local_files!r}",
            MISSING_METADATA,
        )
    return None


def _ingestion_status_blocker(
    payload: dict[str, Any],
) -> tuple[str, str] | None:
    """Block if ``ingestion_status`` is not ``'downloaded'``."""
    if payload.get("ingestion_status") != "downloaded":
        return (
            "World Bank WDI readiness gate: metadata.json "
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
            f"World Bank WDI readiness gate: metadata.json '{field}' "
            f"must be a non-empty string naming {expected}.",
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
            "World Bank WDI readiness gate: metadata.json "
            f"'source_version' must be the canonical version "
            f"{canonical_version!r}.",
            UNSUPPORTED_VERSION,
        )
    if metadata_version.strip() != canonical_version:
        return (
            f"World Bank WDI readiness gate: metadata.json "
            f"'source_version' is {metadata_version.strip()!r}, "
            f"but the unified World Bank WDI adapter supports only "
            f"canonical version {canonical_version!r}. Re-stage a "
            f"WDI bundle with the canonical source_version or "
            f"correct metadata.json before running ingestion.",
            UNSUPPORTED_VERSION,
        )
    return None


def _checksum_blocker(
    payload: dict[str, Any],
) -> tuple[str, str] | None:
    """Block if ``checksum_sha256`` is missing or invalid.

    Three canonical shapes are accepted for the unified
    source-bundle contract:

    - ``checksum_sha256: null`` together with a non-empty
      ``checksum_note`` that mentions the API / cache /
      per-response / checksum contract. The canonical WDI
      bundle carries this shape because each cached response
      is independently checksummed; an empty or vague
      ``checksum_note`` would leave the omission
      indistinguishable from a forgotten checksum, so the
      gate refuses it.
    - ``checksum_sha256: "<64-char hex>"`` -- a flat
      bundle-level SHA-256. Matches the PWT / Maddison
      hex-string shape.
    - ``checksum_sha256: {"<file>": "<64-char hex>"}`` -- a
      per-file dict. Matches the Maddison multi-file shape.
      Every value must be a 64-char hex string; non-string
      values fail the gate.
    """
    checksum = payload.get("checksum_sha256")
    # None / hex string / dict each have their own
    # validation path. The branches stay under the
    # 6-return-statement ceiling (PLR0911) by sharing
    # helper validations for the dict path.
    if checksum is None:
        note = payload.get("checksum_note")
        if _is_actionable_checksum_note(note):
            return None
        return (
            "World Bank WDI readiness gate: metadata.json "
            "'checksum_sha256' is null and 'checksum_note' "
            "is missing or does not document the per-response "
            "API/cache checksum contract; for API/cache-backed "
            "bundles a null checksum MUST be paired with a "
            "non-empty checksum_note mentioning API, cache, "
            "per-response, or checksum. Either provide a "
            "valid 64-char hex SHA-256 in 'checksum_sha256' "
            "or document the per-response checksum contract "
            "in 'checksum_note'.",
            MISSING_METADATA,
        )
    if isinstance(checksum, str):
        if _SHA256_HEX_PATTERN.match(checksum.strip()):
            return None
        return (
            "World Bank WDI readiness gate: metadata.json "
            "'checksum_sha256' must be a 64-character "
            "hexadecimal SHA-256 when set to a string; "
            f"got {len(checksum)} chars.",
            MISSING_METADATA,
        )
    if isinstance(checksum, dict):
        return _validate_checksum_dict(checksum)
    return (
        "World Bank WDI readiness gate: metadata.json "
        "'checksum_sha256' must be null, a 64-character "
        "hexadecimal SHA-256 string, or a non-empty dict "
        "mapping file names to 64-char hex SHA-256 strings; "
        f"got {type(checksum).__name__}.",
        MISSING_METADATA,
    )


__all__ = [
    "MISSING_METADATA",
    "REQUIRED_METADATA_FIELDS",
    "UNSUPPORTED_VERSION",
    "_checksum_blocker",
    "_ingestion_status_blocker",
    "_is_actionable_checksum_note",
    "_local_files_blocker",
    "_metadata_source_version_blocker",
    "_non_empty_string_blocker",
    "_presence_blocker",
    "_read_metadata_payload",
    "_required_fields_blocker",
    "_validate_checksum_dict",
]
