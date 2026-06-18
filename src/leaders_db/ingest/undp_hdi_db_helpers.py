"""Stage 2 -- UNDP HDI DB helpers: coercion + bundle metadata.

This module holds the pure helper functions used by
:mod:`undp_hdi_db`. It is split out of :mod:`undp_hdi_db` so the
DB module stays focused on the DB-write contract (sources,
source_observations, run manifest) and the helper module stays
focused on the value-coercion and bundle-metadata parsing rules.

The split is mandated by architecture §5: "no separate `_helpers.py`
unless the module grows past 350 lines." :mod:`undp_hdi_db` reached
449 lines (the trigger fired at 351), so the helpers were extracted
-- mirroring the WGI / UCDP / SIPRI milex / SIPRI Yearbook Ch.7 /
PTS split pattern.

Owns:

- :func:`_read_undp_hdi_bundle_metadata` -- read
  ``data/raw/undp_hdi/metadata.json`` if present.
- :func:`_parse_download_date` -- parse an ISO date from the bundle
  metadata; return ``None`` on failure.
- :func:`_parse_year_range` -- parse a ``"YYYY-YYYY"`` year range;
  return ``(None, None)`` on failure.
- :func:`_coerce_float` / :func:`_coerce_float_from_string` -- turn
  a raw cell into ``float | None`` for the
  ``source_observations.normalized_value`` column.
- :func:`_build_observation_rows` -- in-memory builder for
  :class:`SourceObservation` rows from a narrow-format pandas
  frame.

The DB-write functions (:func:`undp_hdi_db.register_undp_hdi_source`,
:func:`undp_hdi_db.write_undp_hdi_observations`,
:func:`undp_hdi_db.write_undp_hdi_run_manifest`) live in
:mod:`leaders_db.ingest.undp_hdi_db`. The CSV read + UNPIVOT
lives in :mod:`leaders_db.ingest.undp_hdi_csv`. The orchestrator
that ties everything together lives in
:mod:`leaders_db.ingest.undp_hdi`.
"""

from __future__ import annotations

import json
import logging
from datetime import date

import pandas as pd

from ..db.models import SourceObservation
from ..paths import raw_dir
from .undp_hdi_io import UNDP_HDI_SOURCE_KEY, IndicatorSpec

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Bundle metadata helpers
# ---------------------------------------------------------------------------


def _read_undp_hdi_bundle_metadata() -> dict[str, object]:
    """Read ``data/raw/undp_hdi/metadata.json`` if present, else empty dict."""
    bundle_meta_path = raw_dir(UNDP_HDI_SOURCE_KEY) / "metadata.json"
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
    """Parse an ISO date from the bundle metadata; return ``None`` on failure."""
    if not isinstance(raw, str):
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _parse_year_range(
    raw: object,
) -> tuple[int | None, int | None]:
    """Parse a ``"YYYY-YYYY"`` year range; return ``(None, None)`` on failure.

    UNDP HDI's bundle metadata uses the integer fields
    ``coverage_start_year`` / ``coverage_end_year`` directly; this
    helper is here for parity with the other Stage 2 adapters and
    for any future bundle that uses a range string.
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


def _coerce_float(value: object) -> float | None:
    """Coerce a raw cell to ``float`` for ``normalized_value``.

    Handles the pandas NaN / string-NaN edge cases + the empty
    string. Returns ``None`` for missing cells.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, float):
        return None if pd.isna(value) else value
    if isinstance(value, int):
        return float(value)
    if isinstance(value, str):
        return _coerce_float_from_string(value)
    return None


def _coerce_float_from_string(raw: str) -> float | None:
    """String variant of :func:`_coerce_float`.

    Centralizes the empty / NaN string handling + the float
    parse. Returns ``None`` for missing cells, otherwise the
    parsed float.
    """
    stripped = raw.strip()
    if not stripped or stripped.lower() in {"nan", "na", "null"}:
        return None
    try:
        return float(stripped)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Observation-row builder
# ---------------------------------------------------------------------------


def _build_observation_rows(
    source_id: int,
    df: pd.DataFrame,
    specs: list[IndicatorSpec],
) -> list[SourceObservation]:
    """Build the ``source_observations`` rows in memory.

    The ``df`` is the narrow-format frame from
    :func:`undp_hdi_csv.build_undp_hdi_observations`. One
    :class:`SourceObservation` row per narrow-frame row.
    ``raw_value`` preserves the original cell text (string
    coercion via ``str(value)``); ``normalized_value`` is the
    float-coerced cell or ``None`` for missing.

    Iteration order: the frame is pre-sorted by
    ``(year, iso3, variable_name)`` by
    :func:`undp_hdi_csv.build_undp_hdi_observations`; the order
    here is therefore deterministic without a re-sort.
    """
    rows: list[SourceObservation] = []
    spec_by_var = {s.variable_name: s for s in specs}
    for _, raw_row in df.iterrows():
        iso3 = str(raw_row["iso3"])
        year = int(raw_row["year"])
        variable_name = str(raw_row["variable_name"])
        raw_value_cell = raw_row["raw_value"]
        spec = spec_by_var.get(variable_name)
        if spec is None:
            # Defensive: the narrow frame should only carry
            # catalog-driven variable names, but a malformed
            # frame would otherwise write a row with a missing
            # spec. Skip.
            _logger.warning(
                "UNDP HDI DB write: no spec for variable_name=%s "
                "(iso3=%s, year=%d). Skipping.",
                variable_name, iso3, year,
            )
            continue
        value = _coerce_float(raw_value_cell)
        raw_value_str = (
            str(raw_value_cell)
            if raw_value_cell is not None
            and not (
                isinstance(raw_value_cell, float) and pd.isna(raw_value_cell)
            )
            else ""
        )
        rows.append(
            SourceObservation(
                source_id=source_id,
                country_id=None,  # Stage 3 fills this in
                leader_id=None,
                year=year,
                variable_name=variable_name,
                raw_value=raw_value_str,
                normalized_value=value,
                unit=spec.unit,
                source_row_reference=f"undp_hdi:{iso3}",
                confidence=None,  # set by Stage 11
                notes=(
                    f"raw_scale={spec.raw_scale}; "
                    f"higher_is_better={1 if spec.higher_is_better else 0}"
                ),
            )
        )
    return rows


__all__ = [
    "_build_observation_rows",
    "_coerce_float",
    "_coerce_float_from_string",
    "_parse_download_date",
    "_parse_year_range",
    "_read_undp_hdi_bundle_metadata",
]
