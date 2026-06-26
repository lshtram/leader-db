"""Per-field SHA-256 checksum validators for the
unified-source BTI adapter.

Validates the bundle ``checksum_sha256`` field shape
and verifies the staged xlsx's actual SHA-256
matches. The canonical BTI bundle metadata carries
``checksum_sha256`` as a ``{filename: sha256}`` dict
per ``data/raw/bti/metadata.json``; the unified
adapter accepts either a top-level 64-char hex
string (the single-file convention; mirrors the PTS
bundle) OR a ``{filename: sha256}`` dict (the
canonical BTI bundle shape). When the staged xlsx
is present and the metadata carries a matching
checksum, the gate fires ``bti_checksum_mismatch``
if they disagree; when the metadata is malformed
or missing required fields, the gate fires
``missing_metadata`` instead.

Split out of :mod:`._metadata_validators` so the
per-field validators stay under the 400-line
convention. The single 64-char hex validator lives
in :func:`_checksum_shape_blocker`; the
``{filename: sha256}`` dict validator lives in
:func:`_checksum_match_blocker` together with the
actual staged xlsx SHA-256 verification.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from leaders_db.sources.warnings import (
    MISSING_METADATA,
)

# Module-local structured warning code used to
# surface a per-file SHA-256 that is well-formed
# but does not match the staged file. Mirrors the
# WGI / WDI / V-Dem / UCDP / CPI / PTS / RSF
# ``*_checksum_mismatch`` pattern.
BTI_CHECKSUM_MISMATCH: str = "bti_checksum_mismatch"

# Length of a SHA-256 hex digest (256 bits / 4 bits
# per hex char).
_SHA256_HEX_LEN: int = 64


def _is_hex_64(value: Any) -> bool:
    """Return ``True`` when ``value`` is a 64-char
    lower- or upper-case hex string.

    Defense in depth: a non-hex 64-char string (e.g.
    ``"z" * 64``) is malformed metadata, NOT a
    checksum mismatch. The validator routes such
    cases to ``MISSING_METADATA`` (per the
    documented "no silent errors" contract) instead
    of the wrong code.
    """
    if not isinstance(value, str) or len(value) != _SHA256_HEX_LEN:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def _checksum_shape_string_blocker(
    raw_checksum: str,
) -> tuple[str, str] | None:
    """Block if the staged ``checksum_sha256`` is a
    present-but-malformed string."""
    if _is_hex_64(raw_checksum):
        return None
    return (
        "BTI readiness gate: metadata.json "
        "'checksum_sha256' must be a 64-char "
        "hex string when present as a string; "
        f"got {raw_checksum!r}.",
        MISSING_METADATA,
    )


def _checksum_shape_dict_blocker(
    raw_checksum: dict[str, Any],
) -> tuple[str, str] | None:
    """Block if the staged ``checksum_sha256`` is a
    present-but-malformed dict (keys or values are
    not 64-char hex strings)."""
    for filename, value in raw_checksum.items():
        if not isinstance(filename, str) or not filename.strip():
            return (
                "BTI readiness gate: metadata.json "
                "'checksum_sha256' dict keys must "
                "be non-empty filenames.",
                MISSING_METADATA,
            )
        if not _is_hex_64(value):
            return (
                "BTI readiness gate: metadata.json "
                "'checksum_sha256' dict values must "
                "be 64-char hex strings; got "
                f"{filename!r}={value!r}.",
                MISSING_METADATA,
            )
    return None


def _checksum_shape_blocker(
    payload: dict[str, Any],
) -> tuple[str, str] | None:
    """Block if ``checksum_sha256`` is present but
    malformed.

    Accepts:

    - A single 64-char hex string (the single-file
      convention; mirrors the PTS bundle).
    - A ``{filename: sha256}`` dict where every
      value is a 64-char hex string.
    - The field being absent (the metadata is
      malformed in a different way; this validator
      only handles the shape branch).

    A present-but-malformed value (non-hex 64-char
    string, or a dict whose values are not 64-char
    hex strings) fires ``MISSING_METADATA`` (not
    ``bti_checksum_mismatch`` -- mismatch is reserved
    for well-formed values that disagree with the
    staged file).

    The validator delegates the per-shape error
    construction to two helpers
    (:func:`_checksum_shape_string_blocker` +
    :func:`_checksum_shape_dict_blocker`) so the
    ``PLR0911`` "too many return statements"
    lint rule is satisfied.
    """
    raw_checksum = payload.get("checksum_sha256")
    if raw_checksum is None:
        # The field is allowed to be absent (the
        # canonical bundle ships per-file SHA-256
        # values, but the readiness gate tolerates a
        # missing field for backward compatibility).
        return None
    if isinstance(raw_checksum, str):
        return _checksum_shape_string_blocker(raw_checksum)
    if isinstance(raw_checksum, dict):
        return _checksum_shape_dict_blocker(raw_checksum)
    return (
        "BTI readiness gate: metadata.json "
        "'checksum_sha256' must be a 64-char hex "
        "string or a {filename: sha256} dict; got "
        f"{type(raw_checksum).__name__}.",
        MISSING_METADATA,
    )


def _resolve_xlsx_sha_from_metadata(
    payload: dict[str, Any],
    xlsx_name: str,
) -> str | None:
    """Return the bundle's expected SHA-256 for the
    staged xlsx, or ``None`` when the metadata does
    not carry a per-file checksum for ``xlsx_name``.

    Handles both the single 64-char hex string
    convention and the ``{filename: sha256}`` dict
    convention. Returns ``None`` for an absent or
    unknown filename so the matcher can short-circuit
    cleanly.
    """
    raw_checksum = payload.get("checksum_sha256")
    if isinstance(raw_checksum, str):
        if _is_hex_64(raw_checksum):
            return raw_checksum.strip()
        return None
    if isinstance(raw_checksum, dict):
        per_file = raw_checksum.get(xlsx_name)
        if isinstance(per_file, str) and _is_hex_64(per_file):
            return per_file.strip()
    return None


def _checksum_match_blocker(
    payload: dict[str, Any],
    xlsx_path: Path,
    xlsx_name: str,
) -> tuple[str, str] | None:
    """Block if the staged xlsx's SHA-256 disagrees
    with the bundle ``checksum_sha256`` field.

    Returns ``None`` when:

    - The bundle does not carry a per-file checksum
      for ``xlsx_name`` (the canonical BTI bundle
      ships per-file SHA-256 values; an absent
      checksum means the metadata is silent and the
      readiness gate tolerates it).
    - The staged xlsx's actual SHA-256 matches the
      bundle's expected checksum.

    Returns a ``(message, BTI_CHECKSUM_MISMATCH)``
    blocker tuple when the well-formed bundle
    checksum disagrees with the staged file's
    actual SHA-256.

    Returns a ``(message, MISSING_METADATA)``
    blocker tuple when the staged xlsx is missing or
    unreadable (defensive guard for an out-of-band
    bundle mutation between the readiness gate's
    presence check and the checksum match).
    """
    expected_sha = _resolve_xlsx_sha_from_metadata(
        payload, xlsx_name,
    )
    if expected_sha is None:
        # No per-file checksum in the metadata;
        # silently allow the readiness gate to
        # pass (the canonical BTI bundle ships
        # per-file SHA-256 values, but the
        # readiness gate tolerates a missing field
        # for backward compatibility with the
        # legacy ``bti`` Stage 2 adapter).
        return None
    if not xlsx_path.is_file():
        return (
            "BTI readiness gate: cannot verify "
            f"checksum_sha256 because the staged xlsx "
            f"is missing at {xlsx_path}.",
            MISSING_METADATA,
        )
    try:
        actual_sha = hashlib.sha256(
            xlsx_path.read_bytes(),
        ).hexdigest()
    except OSError:
        return (
            "BTI readiness gate: cannot verify "
            f"checksum_sha256 because the staged xlsx "
            f"at {xlsx_path} is unreadable.",
            MISSING_METADATA,
        )
    if actual_sha == expected_sha:
        return None
    return (
        "BTI readiness gate: checksum_sha256 "
        f"mismatch for {xlsx_name}; bundle metadata "
        f"declares {expected_sha!r}, but the staged "
        f"file's actual SHA-256 is {actual_sha!r}. "
        "Re-stage the canonical xlsx or update the "
        "metadata to match.",
        BTI_CHECKSUM_MISMATCH,
    )


__all__ = [
    "BTI_CHECKSUM_MISMATCH",
    "_checksum_match_blocker",
    "_checksum_shape_blocker",
]
