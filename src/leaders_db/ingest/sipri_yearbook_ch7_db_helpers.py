"""Stage 2 -- SIPRI Yearbook Ch.7 DB helpers: coercion + bundle metadata.

This module holds the pure helper functions used by
:mod:`sipri_yearbook_ch7_db`. It is split out of
:mod:`sipri_yearbook_ch7_db` so the DB module stays focused on
the DB-write contract (sources, source_observations, run
manifest) and the helper module stays focused on the
value-coercion and bundle-metadata parsing rules. Splitting was
triggered by the 400-line convention; the helpers total ~100
lines and warrant their own file (the WGI / UCDP / SIPRI milex
precedent).

Owns:

- :func:`_coerce_int` -- turn a wide-frame cell (post-pivot) into
  ``int | None`` for the ``source_observations.normalized_value``
  column. Handles the SIPRI-Yearbook-Ch.7-specific sentinels
  (``"-"`` -> 0, ``".."`` -> None, ``"c. <num> [letter]"`` -> the
  parsed int) plus the V-Dem / WDI / WGI / UCDP / SIPRI milex
  sentinels as defense in depth.
- :func:`_coerce_int_from_string` -- string variant.
- :func:`_raw_value_to_string` -- render a raw cell for the
  ``source_observations.raw_value`` audit field, preserving the
  SIPRI-Yearbook-Ch.7-specific literal ``"-"`` / ``".."`` / ``"c.
  24 j"`` for missing/annotated cells.
- :func:`_read_sipri_yearbook_ch7_bundle_metadata` -- read
  ``data/raw/sipri_yearbook_ch7/metadata.json`` if present.
- :func:`_parse_download_date` -- parse an ISO date from the bundle
  metadata; return ``None`` on failure.
- :func:`_parse_year_range` -- parse a ``"YYYY-YYYY"`` year range;
  return ``(None, None)`` on failure.

The DB-write functions (:func:`register_sipri_yearbook_ch7_source`,
:func:`write_sipri_yearbook_ch7_observations`,
:func:`write_sipri_yearbook_ch7_run_manifest`) live in
:mod:`sipri_yearbook_ch7_db`. The PDF read + parquet write live
in :mod:`sipri_yearbook_ch7_io` and
:mod:`sipri_yearbook_ch7_pdf`. The orchestrator lives in
:mod:`sipri_yearbook_ch7`.
"""

from __future__ import annotations

import json
import re
from datetime import date

import pandas as pd

from ..paths import raw_dir
from .sipri_yearbook_ch7_io import SIPRI_YEARBOOK_CH7_SOURCE_KEY
from .sipri_yearbook_ch7_pdf import DOTS_SENTINEL, EN_DASH_SENTINEL

# ---------------------------------------------------------------------------
# Sentinels (defense in depth)
# ---------------------------------------------------------------------------

#: SIPRI-Yearbook-Ch.7-specific missing-value / annotation tokens,
#: unioned with the V-Dem / WDI / WGI / UCDP / SIPRI milex sentinels
#: as defense in depth. The PDF parser already coerces the SIPRI
#: sentinels (``"-"`` -> 0, ``".."`` -> None, ``"c. <num> [letter]"``
#: -> parsed int), so these strings will not appear in the wide
#: frame. The defense-in-depth set is here so a future Stage 2
#: read that bypasses the PDF parser (e.g. a CSV export) still
#: produces the right ``normalized_value``.
_SIPRI_YEARBOOK_CH7_MISSING_STRINGS: frozenset[str] = frozenset(
    {EN_DASH_SENTINEL, DOTS_SENTINEL, "N/A", "NA", "NaN", "nan",
     "null", "None", "-999", "-999.0", ""}
)

#: Numeric missing sentinel (defense in depth; the PDF data does
#: not use ``-999`` but the V-Dem-style helper still recognizes
#: it). The PDF parser's coercion already maps ``"-"`` -> 0 (not
#: None), so ``_SIPRI_YEARBOOK_CH7_MISSING_SENTINEL`` is only
#: hit for cells that somehow bypass the parser.
_SIPRI_YEARBOOK_CH7_MISSING_SENTINEL: float = -999.0

#: Footnote-letter regex for the ``"c. <num> [letter]"`` annotation.
#: Mirrors the parser's regex in :mod:`sipri_yearbook_ch7_pdf`.
#: The ``_coerce_int_from_string`` helper uses this regex to parse
#: annotated cells if they ever reach the DB layer without
#: passing through the PDF parser.
_FOOTNOTE_LETTER_RE = re.compile(
    r"^\s*(?:[cC]\.\s*)?(\d[\d\s]*?)\s*([a-z])?\s*$",
)


# ---------------------------------------------------------------------------
# Bundle metadata helpers
# ---------------------------------------------------------------------------


def _read_sipri_yearbook_ch7_bundle_metadata() -> dict[str, object]:
    """Read ``data/raw/sipri_yearbook_ch7/metadata.json`` if present,
    else empty dict.

    The bundle's ``metadata.json`` carries the source provenance
    (``source_url``, ``download_date``, ``license_note``,
    ``year_range``). The :func:`register_sipri_yearbook_ch7_source`
    DB function consumes this for the ``sources`` row's
    provenance columns.
    """
    bundle_meta_path = raw_dir(SIPRI_YEARBOOK_CH7_SOURCE_KEY) / "metadata.json"
    if not bundle_meta_path.is_file():
        return {}
    try:
        result: dict[str, object] = json.loads(
            bundle_meta_path.read_text(encoding="utf-8"),
        )
        return result
    except json.JSONDecodeError:
        return {}


def _parse_download_date(raw: object) -> date | None:
    """Parse an ISO date from the bundle metadata; return
    ``None`` on failure.
    """
    if not isinstance(raw, str):
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _parse_year_range(
    raw: object,
) -> tuple[int | None, int | None]:
    """Parse a ``"YYYY-YYYY"`` year range; return ``(None, None)``
    on failure.
    """
    if not isinstance(raw, str) or "-" not in raw:
        return (None, None)
    start_str, end_str = raw.split("-", 1)
    try:
        return (int(start_str.strip()), int(end_str.strip()))
    except ValueError:
        return (None, None)


# ---------------------------------------------------------------------------
# Missing-value coercion
# ---------------------------------------------------------------------------


def _coerce_int(value: object) -> int | None:
    """Coerce a wide-frame cell to ``int`` or return ``None``.

    The SIPRI Yearbook Ch.7 PDF parser already maps the
    sentinels:

    - ``"-"`` (U+2013 en-dash) -> ``0`` (per the legend, "nil
      or a negligible value")
    - ``".."`` (two ASCII dots) -> ``None`` (per the legend,
      "not applicable or not available")
    - ``"c. <num> [letter]"`` -> the parsed ``int`` (the ``"c. "``
      prefix and footnote letter are stripped)

    By the time the cell reaches the DB layer, the value is
    already a Python ``int`` (0 for the en-dash, the parsed
    integer for normal/annotated cells) or ``pd.NA`` / ``None``
    (for the two-dot). This helper handles the post-parse
    values: ``pd.NA`` / ``None`` -> ``None``; ``int`` -> the
    same ``int``; ``str`` -> re-coerced via
    :func:`_coerce_int_from_string` (defense in depth).
    """
    if value is None:
        return None
    if isinstance(value, float):
        return _coerce_int_from_float(value)
    if isinstance(value, bool):
        # bool is a subclass of ``int`` in Python; reject it
        # explicitly (a bool is not a warhead count).
        return None
    if isinstance(value, int):
        return _coerce_int_from_int(value)
    if isinstance(value, str):
        return _coerce_int_from_string(value)
    # Unknown type (list, dict, etc.) -- be safe and return None.
    return None


def _coerce_int_from_float(value: float) -> int | None:
    """Float variant of :func:`_coerce_int`."""
    if pd.isna(value):
        return None
    if value <= _SIPRI_YEARBOOK_CH7_MISSING_SENTINEL:
        return None
    return int(value)


def _coerce_int_from_int(value: int) -> int | None:
    """Int variant of :func:`_coerce_int`.

    Handles the pandas ``Int64`` nullable extension type. A
    missing ``Int64`` cell is ``pd.NA``; the ``pd.isna`` check
    catches that. Plain Python ``int`` values that are at or
    below the missing sentinel return ``None`` (defense in
    depth).
    """
    if pd.isna(value):
        return None
    if value <= int(_SIPRI_YEARBOOK_CH7_MISSING_SENTINEL):
        return None
    return value


def _coerce_int_from_string(raw: str) -> int | None:
    """String variant of :func:`_coerce_int`.

    Handles the SIPRI-Yearbook-Ch.7-specific sentinels (``"-"``,
    ``".."``, the ``"c. <num> [letter]"`` annotation) plus the
    V-Dem / WDI / WGI / UCDP sentinels as defense in depth. The
    en-dash is mapped to ``0`` (per the legend); the two-dot is
    mapped to ``None``; the ``"c. <num> [letter]"`` annotation is
    parsed to the integer; plain numeric cells are parsed
    directly.
    """
    stripped = raw.strip()
    # Sentinel checks (combined).
    if not stripped or stripped in _SIPRI_YEARBOOK_CH7_MISSING_STRINGS:
        return None
    if stripped == EN_DASH_SENTINEL:
        return 0
    # The "c. <num> [letter]" annotation. The leading "c. " prefix
    # is optional; the footnote letter is optional. The
    # ``_FOOTNOTE_LETTER_RE`` regex extracts the digit group.
    match = _FOOTNOTE_LETTER_RE.match(stripped)
    if match is not None:
        return _coerce_int_from_footnote_match(match)
    # Plain numeric cell.
    return _coerce_int_from_plain_string(stripped)


def _coerce_int_from_footnote_match(
    match: re.Match[str],
) -> int | None:
    """Parse the digit group of a ``_FOOTNOTE_LETTER_RE`` match.

    The regex extracts the digit group (with optional spaces as
    thousands separators); this helper strips the spaces and
    parses the int.
    """
    digit_str = match.group(1) or ""
    digit_str_clean = (
        digit_str.replace(" ", "").replace("\u00a0", "")
    )
    try:
        return int(digit_str_clean)
    except ValueError:
        return None


def _coerce_int_from_plain_string(stripped: str) -> int | None:
    """Parse a plain numeric string (no ``c.`` prefix, no
    footnote letter).
    """
    try:
        numeric = int(stripped)
    except ValueError:
        return None
    if numeric <= _SIPRI_YEARBOOK_CH7_MISSING_SENTINEL:
        return None
    return numeric


def _raw_value_to_string(cell: object) -> str:
    """Render a raw cell for the ``source_observations.raw_value``
    audit field.

    Rules:

    - ``None`` -> ``""`` (no audit trail for missing cells).
    - pandas ``NaN`` / ``pd.NA`` -> ``""`` (no audit trail;
      pandas' internal missing is the same as None for our
      purposes; the wide frame's ``_sipri_yearbook_ch7_raw_lookup``
      attr is the source of truth for the original PDF cell).
    - All other values -> ``str(cell)`` (preserves the SIPRI
      literal ``"-"`` / ``".."`` / ``"c. 24 j"`` so the audit
      trail shows what the source file actually said).

    Note: in normal Stage 2 flow, the
    :func:`sipri_yearbook_ch7_db._build_observation_rows` helper
    does NOT call this function for SIPRI Yearbook Ch.7 -- it
    looks up the original PDF cell text from
    ``df.attrs["_sipri_yearbook_ch7_raw_lookup"]`` (the
    long-format raw-cell map built by
    :func:`sipri_yearbook_ch7_io.read_sipri_yearbook_ch7`).
    This function is exported for defense in depth and for
    tests that build cells by hand.
    """
    if cell is None:
        return ""
    if isinstance(cell, float) and pd.isna(cell):
        return ""
    return str(cell)


__all__ = [
    "_SIPRI_YEARBOOK_CH7_MISSING_SENTINEL",
    "_SIPRI_YEARBOOK_CH7_MISSING_STRINGS",
    "_coerce_int",
    "_coerce_int_from_string",
    "_parse_download_date",
    "_parse_year_range",
    "_raw_value_to_string",
    "_read_sipri_yearbook_ch7_bundle_metadata",
]
