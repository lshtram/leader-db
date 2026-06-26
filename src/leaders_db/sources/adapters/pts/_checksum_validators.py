"""Per-field ``sha256`` checksum validators for the
unified-source PTS adapter.

Split out of :mod:`._metadata_validators` so the
per-field validators module stays under the 400-line
module convention. The helpers handle:

- :func:`_checksum_shape_blocker` -- block if
  ``sha256`` is not a valid 64-char hex SHA-256.
- :func:`_checksum_match_blocker` -- verify the staged
  xlsx SHA-256 against the metadata ``sha256`` field.

The canonical PTS bundle metadata carries
``sha256="6f4d1ccd...88832"`` (verified live 2026-06-18
per ``docs/architecture/pts.md`` §2). The PTS bundle
ships ``sha256`` populated with the live xlsx SHA-256,
so the readiness gate's xlsx-checksum match is
exercised in the canonical shape.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from leaders_db.sources.warnings import MISSING_METADATA

# Module-local structured warning code used to surface
# an xlsx SHA-256 that is well-formed but does not
# match the metadata ``sha256`` field. Mirrors the CPI
# / UCDP / V-Dem ``*_checksum_mismatch`` pattern.
PTS_CHECKSUM_MISMATCH: str = "pts_checksum_mismatch"


def _checksum_shape_blocker(
    payload: dict[str, Any],
) -> tuple[str, str] | None:
    """Block if ``sha256`` is not a valid 64-char hex
    SHA-256.

    The canonical PTS bundle metadata carries
    ``sha256="6f4d1ccd...88832"`` (verified live
    2026-06-18 per ``docs/architecture/pts.md`` §2).
    """
    expected_sha = payload.get("sha256")
    if expected_sha is None:
        return (
            "PTS readiness gate: metadata.json 'sha256' "
            "must be a 64-character hex SHA-256 string "
            "for the staged PTS-2025.xlsx; got null.",
            MISSING_METADATA,
        )
    if not isinstance(expected_sha, str) or not expected_sha.strip():
        return (
            "PTS readiness gate: metadata.json 'sha256' "
            "must be a 64-character hex SHA-256 string; "
            "got empty value.",
            MISSING_METADATA,
        )
    stripped = expected_sha.strip().lower()
    if len(stripped) != 64 or any(
        ch not in "0123456789abcdef" for ch in stripped
    ):
        return (
            "PTS readiness gate: metadata.json 'sha256' "
            "must be a 64-character hex SHA-256 string; "
            f"got {expected_sha!r}.",
            MISSING_METADATA,
        )
    return None


def _checksum_match_blocker(
    payload: dict[str, Any],
    xlsx_path: Path,
    xlsx_name: str,
) -> tuple[str, str] | None:
    """Verify the staged xlsx SHA-256 against the
    metadata ``sha256`` field.

    Returns a structured ``pts_checksum_mismatch``
    blocker when the staged xlsx SHA-256 disagrees
    with the metadata field.
    """
    expected_sha = payload.get("sha256")
    if not isinstance(expected_sha, str) or not expected_sha.strip():
        return None
    if not xlsx_path.is_file():
        return None
    expected_sha = expected_sha.strip().lower()
    actual_sha = hashlib.sha256(xlsx_path.read_bytes()).hexdigest()
    if actual_sha != expected_sha:
        return (
            "PTS readiness gate: xlsx checksum "
            "mismatch. metadata.json says "
            f"sha256={expected_sha!r} but the staged "
            f"{xlsx_name} has sha256={actual_sha!r}.",
            PTS_CHECKSUM_MISMATCH,
        )
    return None


__all__ = [
    "PTS_CHECKSUM_MISMATCH",
    "_checksum_match_blocker",
    "_checksum_shape_blocker",
]
