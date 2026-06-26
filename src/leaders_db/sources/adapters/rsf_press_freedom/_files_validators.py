"""Per-file ``files`` array + per-file SHA-256
validators for the unified-source RSF adapter.

Split out of :mod:`._metadata_validators` so the
per-field validators module stays under the 400-line
module convention. The helpers handle:

- :func:`_find_files_entry` -- find the ``files``
  array entry matching ``year``.
- :func:`_check_year_files_entry` -- block when a
  staged per-year CSV has no matching ``files``
  metadata entry (malformed metadata, NOT
  runner-ready).
- :func:`_checksum_match_blocker` -- verify the
  staged per-year CSV SHA-256 against the metadata
  ``files`` entry for ``year``.

The canonical RSF bundle metadata carries a
``files`` array with one record per year file
(``year`` / ``file`` / ``bytes`` / ``sha256`` /
``encoding_used_for_metadata_parse`` /
``columns``). The unified adapter's readiness gate
requires a well-formed ``files`` entry for every
staged per-year CSV; a missing entry is malformed
metadata (the canonical bundle uses ``files`` as
the per-file checksum + audit source of truth). A
null / absent per-file ``sha256`` is treated as
"no checksum declared" and passes the
SHA-256-match branch.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from leaders_db.sources.warnings import MISSING_METADATA

from ._constants import (
    RSF_PRESS_FREEDOM_CHECKSUM_MISMATCH,
)


def _find_files_entry(
    payload: dict[str, Any],
    year: int,
) -> dict[str, Any] | None:
    """Find the ``files`` array entry matching ``year``.

    Returns ``None`` when no entry exists (e.g. a
    metadata-only bundle or a year outside the staged
    metadata's coverage). The well-formed-entry
    requirement is enforced by
    :func:`_check_year_files_entry` so the readiness
    orchestrator surfaces the missing-entry failure
    as a structured ``missing_metadata`` blocker
    BEFORE the runner dispatches ``read_raw`` /
    ``transform``.
    """
    files_field = payload.get("files")
    if not isinstance(files_field, list):
        return None
    for entry in files_field:
        if not isinstance(entry, dict):
            continue
        if entry.get("year") == year:
            return entry
    return None


def _check_year_files_entry(
    payload: dict[str, Any],
    year: int,
) -> tuple[str, str] | None:
    """Return a blocker tuple when the staged per-year
    CSV has no matching well-formed ``files`` metadata
    entry for ``year``.

    The canonical RSF bundle metadata carries a
    ``files`` array with one record per year file;
    every staged per-year CSV MUST have a matching
    entry. A staged per-year CSV without a matching
    ``files`` entry is malformed metadata (the
    canonical bundle uses ``files`` as the per-file
    checksum + audit source of truth) and the
    readiness gate returns ``ready=False`` with a
    structured ``missing_metadata`` blocker BEFORE
    the runner dispatches ``read_raw`` /
    ``transform``.
    """
    entry = _find_files_entry(payload, year)
    if entry is None:
        return (
            f"RSF readiness gate: metadata.json 'files' "
            f"array is missing an entry for year={year}; "
            f"the canonical RSF bundle requires a "
            f"well-formed 'files' entry (year / file / "
            f"sha256 / bytes) for every staged "
            f"per-year CSV. Update metadata.json 'files' "
            f"to include a record for year={year}.",
            MISSING_METADATA,
        )
    return None


def _checksum_match_blocker(
    payload: dict[str, Any],
    csv_path: Path,
    csv_name: str,
    year: int,
) -> tuple[str, str] | None:
    """Verify the staged per-year CSV SHA-256 against
    the metadata ``files`` entry for ``year``.

    Returns a structured
    ``rsf_press_freedom_checksum_mismatch`` blocker
    when the staged per-year CSV SHA-256 disagrees
    with the metadata field. A null / absent
    per-file ``sha256`` is treated as "no checksum
    declared" and passes the gate.

    The well-formed-entry requirement is enforced
    upstream by :func:`_check_year_files_entry` so
    this helper only runs when a ``files`` entry
    exists for ``year``.
    """
    entry = _find_files_entry(payload, year)
    if entry is None:
        return None
    expected_sha = entry.get("sha256")
    if not isinstance(expected_sha, str) or not expected_sha.strip():
        return None
    if not csv_path.is_file():
        return None
    expected_sha = expected_sha.strip().lower()
    actual_sha = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    if actual_sha != expected_sha:
        return (
            "RSF readiness gate: per-year CSV checksum "
            f"mismatch for year={year}. metadata.json "
            f"files[{year!r}].sha256="
            f"{expected_sha!r} but the staged "
            f"{csv_name} has sha256={actual_sha!r}.",
            RSF_PRESS_FREEDOM_CHECKSUM_MISMATCH,
        )
    return None


__all__ = [
    "_check_year_files_entry",
    "_checksum_match_blocker",
    "_find_files_entry",
]
