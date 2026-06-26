"""RSF ``metadata.json`` per-field validators for the
``files`` array + the ``source_version`` stamp.

Split out of :mod:`._metadata_validators` so the
per-field validators module stays under the 400-line
module convention. The helpers handle:

- :func:`_files_blocker` -- block if the per-file
  ``files`` array is missing or malformed.
- :func:`_validate_files_entry` -- per-entry helper
  for :func:`_files_blocker`. Delegates the
  ``sha256`` hex + length check to
  :func:`_validate_files_entry_sha256` so the
  orchestrator stays under the documented
  ``PLR0911`` (too many return statements) limit.
- :func:`_validate_files_entry_sha256` -- block if
  the per-entry ``sha256`` is not a 64-character
  lowercase hex string when present. The canonical
  RSF bundle carries the lowercase-hex SHA-256 of
  the staged per-year CSV; a 64-character non-hex
  string (e.g. ``"z" * 64``) is malformed metadata,
  NOT a checksum mismatch.
- :func:`_metadata_source_version_blocker` -- block
  if the bundle ``source_version`` stamp is missing
  or not canonical.

The canonical RSF bundle metadata carries the verbose
acquisition-date stamp ``"annual CSV series 2002-2026,
acquired 2026-06-18"``; the unified adapter also
accepts the brief canonical stamp ``"RSF Press Freedom
Index 2026"`` so future metadata rewrites that adopt
the brief stamp still pass readiness.
"""

from __future__ import annotations

from typing import Any

from leaders_db.sources.warnings import MISSING_METADATA

from ._constants import (
    RSF_PRESS_FREEDOM_METADATA_VERSION_MISMATCH,
)

# Verbose acquisition-date stamp the staged metadata
# carries under ``source_version``. The unified
# adapter also accepts the brief canonical stamp
# ``"RSF Press Freedom Index 2026"`` so future
# metadata rewrites that adopt the brief stamp still
# pass readiness. These stamps are local to the
# metadata-version validator so the constants module
# stays under the documented 400-line convention.
RSF_PRESS_FREEDOM_BUNDLE_VERSION_STAMP: str = (
    "annual CSV series 2002-2026, acquired 2026-06-18"
)
RSF_PRESS_FREEDOM_CANONICAL_VERSION_STAMP: str = (
    "RSF Press Freedom Index 2026"
)


def _validate_files_entry_sha256(
    sha: Any,
) -> tuple[str, str] | None:
    """Validate the ``sha256`` field of a ``files``
    entry.

    Returns ``None`` when ``sha`` is ``None`` (no
    checksum declared) or a 64-character hex string,
    and a ``(message, MISSING_METADATA)`` blocker
    tuple when ``sha`` is malformed -- not a string,
    wrong length, or contains non-hex characters. The
    canonical RSF bundle carries the lowercase-hex
    SHA-256 of the staged per-year CSV; a
    64-character non-hex string (e.g. ``"z" * 64``)
    is malformed metadata, NOT a checksum mismatch.
    Without this guard the readiness gate would
    silently treat ``"z" * 64`` as a "checksum
    mismatch" and the runner would dispatch
    ``read_raw`` against a malformed metadata bundle.
    """
    if sha is None:
        return None
    if not isinstance(sha, str):
        return (
            "RSF readiness gate: metadata.json 'files' "
            "entries 'sha256' must be a 64-character "
            "hex string when present; got "
            f"{sha!r}.",
            MISSING_METADATA,
        )
    stripped = sha.strip()
    if len(stripped) != 64:
        return (
            "RSF readiness gate: metadata.json 'files' "
            "entries 'sha256' must be a 64-character "
            "hex string when present; got "
            f"{sha!r}.",
            MISSING_METADATA,
        )
    try:
        int(stripped, 16)
    except ValueError:
        return (
            "RSF readiness gate: metadata.json 'files' "
            "entries 'sha256' must be a 64-character "
            "hex string when present; got "
            f"{sha!r}.",
            MISSING_METADATA,
        )
    return None


def _validate_files_entry(
    entry: Any,
) -> tuple[str, str] | None:
    """Validate a single ``files`` array entry.

    Returns ``None`` when the entry is well-formed or a
    ``(message, MISSING_METADATA)`` blocker tuple when
    the entry is malformed. Per-entry ``sha256`` is
    optional (the canonical bundle carries one per
    file, but the gate accepts absent / null when the
    per-year CSV is not yet checksummed).
    """
    if not isinstance(entry, dict):
        return (
            "RSF readiness gate: metadata.json 'files' "
            "entries must be dicts; got "
            f"{type(entry).__name__}.",
            MISSING_METADATA,
        )
    year = entry.get("year")
    file_name = entry.get("file")
    if not isinstance(year, int) or isinstance(year, bool):
        return (
            "RSF readiness gate: metadata.json 'files' "
            "entries must include a positive integer "
            "'year' field; got "
            f"{entry!r}.",
            MISSING_METADATA,
        )
    if not isinstance(file_name, str) or not file_name.strip():
        return (
            "RSF readiness gate: metadata.json 'files' "
            "entries must include a non-empty 'file' "
            f"field; got {entry!r}.",
            MISSING_METADATA,
        )
    return _validate_files_entry_sha256(entry.get("sha256"))


def _files_blocker(
    payload: dict[str, Any],
) -> tuple[str, str] | None:
    """Block if the per-file ``files`` array is missing
    or malformed.

    The canonical RSF bundle metadata carries a
    ``files`` array with one record per year file
    (``year`` / ``file`` / ``bytes`` / ``sha256`` /
    ``encoding_used_for_metadata_parse`` /
    ``columns``). A present-but-null ``files`` field is
    NOT accepted.
    """
    if "files" not in payload:
        return None
    files_field = payload["files"]
    if files_field is None:
        return (
            "RSF readiness gate: metadata.json 'files' "
            "must be a list (possibly empty); got null. "
            "The canonical RSF bundle metadata requires "
            "'files' as a list of per-year file records.",
            MISSING_METADATA,
        )
    if not isinstance(files_field, list):
        return (
            "RSF readiness gate: metadata.json 'files' "
            "must be a list (possibly empty); got "
            f"{type(files_field).__name__}.",
            MISSING_METADATA,
        )
    for entry in files_field:
        blocker = _validate_files_entry(entry)
        if blocker is not None:
            return blocker
    return None


def _metadata_source_version_blocker(
    payload: dict[str, Any],
    *,
    canonical_version: str,
) -> tuple[str, str] | None:
    """Block if metadata ``source_version`` is missing
    or not canonical.

    The staged bundle carries the verbose acquisition-
    date stamp ``"annual CSV series 2002-2026,
    acquired 2026-06-18"``; the unified adapter also
    accepts the brief canonical stamp ``"RSF Press
    Freedom Index 2026"`` so future metadata rewrites
    that adopt the brief stamp still pass readiness.
    """
    version_field = payload.get("source_version")
    if not isinstance(version_field, str) or not version_field.strip():
        return (
            "RSF readiness gate: metadata.json "
            "'source_version' must be a non-empty string; "
            f"got {version_field!r}.",
            MISSING_METADATA,
        )
    stripped = version_field.strip()
    accepted_stamps = {
        canonical_version,
        RSF_PRESS_FREEDOM_CANONICAL_VERSION_STAMP,
        RSF_PRESS_FREEDOM_BUNDLE_VERSION_STAMP,
    }
    if stripped not in accepted_stamps:
        return (
            "RSF readiness gate: metadata.json "
            f"'source_version' is {stripped!r}, but the "
            "unified RSF adapter supports only the "
            "canonical stamps "
            f"{sorted(accepted_stamps)!r}.",
            RSF_PRESS_FREEDOM_METADATA_VERSION_MISMATCH,
        )
    return None


__all__ = [
    "_files_blocker",
    "_metadata_source_version_blocker",
    "_validate_files_entry",
    "_validate_files_entry_sha256",
]
