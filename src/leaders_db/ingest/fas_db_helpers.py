"""Stage 2 -- FAS Nuclear Notebook DB helpers: coercion + bundle metadata.

This module holds the pure helper functions used by
:mod:`fas_db`. It is split out of :mod:`fas_db` so the DB module
stays focused on the DB-write contract (sources,
source_observations, run manifest) and the helper module stays
focused on the value-coercion and bundle-metadata parsing rules.

The split mirrors the WHO GHO API / WDI / WGI / UCDP / SIPRI
milex / SIPRI Yearbook Ch.7 / PTS / UNDP HDI / CIRIGHTS /
Transparency International CPI / RSF Press Freedom pattern.

Owns:

- :func:`_read_fas_bundle_metadata` -- read
  ``data/raw/fas/metadata.json`` if present.
- :func:`_parse_download_date` -- parse an ISO date from the
  bundle metadata; return ``None`` on failure.
- :func:`_coerce_float` / :func:`_coerce_float_from_string` --
  turn a raw cell into ``float | None`` for the
  ``source_observations.normalized_value`` column. Mirrors the
  WHO GHO API / Transparency International CPI helpers.
- :func:`_raw_value_to_string` -- render a raw cell for the
  ``source_observations.raw_value`` audit field.
- :func:`_build_observation_rows` -- in-memory builder for
  :class:`SourceObservation` rows from the wide-format pandas
  frame produced by the reader.

Country handling for FAS:

- The FAS table uses country names (``Russia``, ``United States``,
  etc.), not ISO3 codes. The Stage 2 reader preserves the
  country name in the frame; Stage 3 (country match) fills
  ``country_id`` via the canonical country aliases table.
- ``source_row_reference`` carries the catalog ``raw_column`` +
  country name (e.g. ``fas:Operational Strategic:Russia``) so
  Stage 3 can resolve it and the audit trail identifies both
  the indicator and the country.
"""

from __future__ import annotations

import json
import logging
from datetime import date

import pandas as pd

from ..db.models import SourceObservation
from ..paths import raw_dir
from .fas_io import FAS_SOURCE_KEY, IndicatorSpec

_logger = logging.getLogger(__name__)

#: String sentinels pandas / HTML may emit on re-reads. Treated
#: as missing. The FAS HTML uses empty cells; the standard string
#: sentinels (``NA``, ``NaN``, ``nan``, ``null``, ``None``,
#: ``""``) are handled defensively.
_FAS_MISSING_STRINGS: frozenset[str] = frozenset(
    {"NA", "NaN", "nan", "null", "None", ""}
)


# ---------------------------------------------------------------------------
# Bundle metadata helpers
# ---------------------------------------------------------------------------


def _read_fas_bundle_metadata() -> dict[str, object]:
    """Read ``data/raw/fas/metadata.json`` if present."""
    bundle_meta_path = raw_dir(FAS_SOURCE_KEY) / "metadata.json"
    if not bundle_meta_path.is_file():
        return {}
    try:
        result: dict[str, object] = json.loads(
            bundle_meta_path.read_text(encoding="utf-8")
        )
        return result
    except json.JSONDecodeError:
        return {}


def _parse_download_date(raw: object) -> date | None:
    """Parse an ISO date from the bundle metadata; return ``None`` on failure."""
    if not isinstance(raw, str):
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Missing-value coercion
# ---------------------------------------------------------------------------


def _coerce_float(value: object) -> float | None:
    """Coerce a FAS / pandas cell to ``float`` or ``None``.

    The FAS values are integer warhead counts; after JSON /
    parquet re-reads pandas may surface them as float (with NaN
    for missing). This helper handles both, plus the common
    string sentinels (``""``, ``"NA"``, ``"NaN"``, ``"nan"``,
    ``"null"``, ``"None"``).
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, float):
        if pd.isna(value):
            return None
        return value
    if isinstance(value, int):
        return float(value)
    if isinstance(value, str):
        return _coerce_float_from_string(value)
    return None


def _coerce_float_from_string(raw: str) -> float | None:
    """String variant of :func:`_coerce_float`."""
    stripped = raw.strip()
    if stripped in _FAS_MISSING_STRINGS:
        return None
    try:
        return float(stripped)
    except ValueError:
        return None


def _raw_value_to_string(cell: object) -> str:
    """Render a raw cell for the ``source_observations.raw_value`` audit field."""
    if cell is None:
        return ""
    if isinstance(cell, float) and pd.isna(cell):
        return "nan"
    return str(cell)


# ---------------------------------------------------------------------------
# Observation-row builder
# ---------------------------------------------------------------------------


def _build_observation_rows(
    source_id: int,
    df: pd.DataFrame,
    specs: list[IndicatorSpec],
) -> list[SourceObservation]:
    """Build the ``source_observations`` rows in memory (no DB session needed).

    Iterates the wide-format DataFrame row-by-row. For each
    ``(country, year)`` pair, writes one ``SourceObservation``
    row per catalog spec whose ``variable_name`` is a column in
    the frame. ``country_id`` and ``leader_id`` are intentionally
    left ``NULL`` -- Stage 3 fills them (the FAS table uses
    country names, not ISO3; Stage 3 resolves them).
    ``source_row_reference`` carries the catalog ``raw_column``
    + country name (e.g. ``"fas:Operational Strategic:Russia"``)
    so Stage 3 can resolve the observation and the audit trail
    identifies both the indicator and the country.

    The wide frame's columns are the catalog ``variable_name``s
    (the reader renames the FAS HTML column headers to canonical
    ``fas_<col>`` slugs during the long-to-wide pivot).
    """
    rows: list[SourceObservation] = []
    for _, raw_row in df.iterrows():
        country = str(raw_row["country"])
        year = int(raw_row["year"])
        for spec in specs:
            if spec.variable_name not in raw_row.index:
                continue
            cell = raw_row[spec.variable_name]
            value = _coerce_float(cell)
            # The verbatim FAS cell (e.g. ``"1,600a"`` for
            # Russia operational strategic with the footnote
            # letter) is preserved in the sibling
            # ``<variable>_raw_value`` column emitted by the
            # reader. When that column is absent (e.g. a future
            # caller constructs the wide frame by hand) fall
            # back to the cell stringification.
            raw_value_col = f"{spec.variable_name}_raw_value"
            if raw_value_col in raw_row.index:
                raw_value_audit = _raw_value_to_string(
                    raw_row[raw_value_col]
                )
            else:
                raw_value_audit = _raw_value_to_string(cell)
            rows.append(
                SourceObservation(
                    source_id=source_id,
                    country_id=None,  # Stage 3 fills this in
                    leader_id=None,
                    year=year,
                    variable_name=spec.variable_name,
                    raw_value=raw_value_audit,
                    normalized_value=value,
                    unit=spec.unit,
                    source_row_reference=(
                        f"fas:{spec.raw_column}:{country}"
                    ),
                    confidence=None,  # set by Stage 11
                    notes=(
                        f"raw_scale={spec.raw_scale}; "
                        f"higher_is_better="
                        f"{1 if spec.higher_is_better else 0}"
                    ),
                )
            )
    return rows


__all__ = [
    "_build_observation_rows",
    "_coerce_float",
    "_coerce_float_from_string",
    "_parse_download_date",
    "_raw_value_to_string",
    "_read_fas_bundle_metadata",
]
