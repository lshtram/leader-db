"""Stage 2 -- Transparency International CPI CSV reader: long->wide pivot.

This module owns the Transparency International CPI CSV reader:
turn the HDX per-year CSV (or any cached HDX-format CSV) into a
wide-format ``pandas.DataFrame`` with columns ``[iso3, year,
cpi_score, cpi_score_raw_value, ...]``. The reader narrows the
catalog to a single ``cpi_score`` column (the 0-100 CPI score per
country-year); the score modules in Stage 9-10 normalize the
score from 0-100 to 0-10 by dividing by 10.

Owns:

- :func:`read_transparency_cpi_csv` -- the public reader (one
  year per call; returns a wide-format DataFrame).
- :func:`_coerce_int_score` -- turn an HDX CSV cell into an
  ``int | None`` (the score is an integer 0-100 per the TI
  methodology since 2012; missing values are empty / ``NA`` /
  ``nan``).
- :func:`_normalize_iso3` -- uppercase + strip; the HDX CSV uses
  uppercase ISO3 already, but defensive normalization keeps the
  Stage 2 frame consistent with the WHO GHO API / WDI /
  UNDP HDI adapter shape.

The HTTP + cache I/O lives in :mod:`transparency_cpi_http`. The
catalog + paths + parquet write live in
:mod:`transparency_cpi_io`. The DB writes live in
:mod:`transparency_cpi_db`. The orchestrator lives in
:mod:`transparency_cpi`.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path

import pandas as pd

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: String sentinels the HDX CSV may emit on missing values. Treated
#: as missing. The HDX CSV uses empty cells; defensively handle
#: ``NA`` / ``NaN`` / ``nan`` / ``null`` / ``None`` strings too.
_MISSING_STRINGS: frozenset[str] = frozenset(
    {"NA", "NaN", "nan", "null", "None", ""}
)

#: The required column set in the HDX CSV. The reader raises
#: :class:`ValueError` if any of these are missing.
_REQUIRED_CSV_COLUMNS: tuple[str, ...] = (
    "country",
    "iso3",
    "region",
    "year",
    "score",
    "rank",
    "sources",
    "standardError",
    "lowerCi",
    "upperCi",
)

#: Default location of the per-year cached CSV.
_DEFAULT_CSV_NAME_TEMPLATE: str = "global_cpi_{year}.csv"


# ---------------------------------------------------------------------------
# Cell coercion
# ---------------------------------------------------------------------------


def _coerce_int_score(cell: object) -> int | None:
    """Coerce an HDX CSV ``score`` cell to ``int | None``.

    The CPI score is an integer 0-100 per the TI methodology since
    2012 (whole-number scores, no decimals). The HDX CSV uses
    empty cells for missing values. Defensive: handle the
    standard string sentinels (``NA``, ``NaN``, ``nan``, ``null``,
    ``None``, ``""``) and pandas NaN.
    """
    if cell is None:
        return None
    if isinstance(cell, bool):
        return None
    if isinstance(cell, float):
        if math.isnan(cell):
            return None
        return int(cell)
    if isinstance(cell, int):
        return cell
    if isinstance(cell, str):
        stripped = cell.strip()
        if stripped in _MISSING_STRINGS:
            return None
        try:
            return int(float(stripped))
        except ValueError:
            return None
    return None


def _normalize_iso3(cell: object) -> str:
    """Normalize an HDX CSV ``iso3`` cell to a 3-letter uppercase string.

    The HDX CSV already uses uppercase ISO3 (verified at probe
    time); defensive normalization keeps the Stage 2 frame
    consistent with the WDI / WHO GHO API / UNDP HDI shape.
    Returns ``""`` for empty / missing cells.
    """
    if cell is None:
        return ""
    if isinstance(cell, str):
        return cell.strip().upper()
    return str(cell).strip().upper()


# ---------------------------------------------------------------------------
# Public reader
# ---------------------------------------------------------------------------


def read_transparency_cpi_csv(
    records: list[dict[str, str]],
    *,
    year: int,
    cache_path: Path | None = None,
) -> pd.DataFrame:
    """Read the Transparency International CPI CSV records and pivot to wide format.

    Args:
        records: a list of dicts (one per country row) from
            :func:`transparency_cpi_http.fetch_transparency_cpi_csv`
            (either cache or HTTP). Each dict has the HDX CSV
            columns: ``country``, ``iso3``, ``region``, ``year``,
            ``score``, ``rank``, ``sources``, ``standardError``,
            ``lowerCi``, ``upperCi``.
        year: the year the records were fetched for (used as the
            ``year`` column value; the ``year`` field on the
            record is preserved as a sanity check but the
            caller's year wins if they conflict).
        cache_path: reserved for future per-call logging; not
            consumed.

    Returns:
        A pandas DataFrame with columns ``iso3``, ``year``,
        ``cpi_score`` (the integer 0-100 CPI score),
        ``cpi_score_raw_value`` (the verbatim original cell as a
        string), and ``country``, ``region``, ``rank``,
        ``sources``, ``standard_error``, ``lower_ci``,
        ``upper_ci`` (the audit-trail fields preserved verbatim).
        One row per country. The frame is sorted by ``iso3``
        ascending for deterministic idempotency.

    Raises:
        ValueError: if any required HDX CSV column is missing.
    """
    if not records:
        return pd.DataFrame(
            columns=[
                "iso3",
                "year",
                "country",
                "region",
                "cpi_score",
                "cpi_score_raw_value",
                "rank",
                "sources",
                "standard_error",
                "lower_ci",
                "upper_ci",
            ]
        )

    sample = records[0]
    missing = set(_REQUIRED_CSV_COLUMNS) - set(sample.keys())
    if missing:
        raise ValueError(
            "Transparency International CPI CSV is missing required "
            f"columns: {sorted(missing)}"
        )

    rows: list[dict[str, object]] = []
    for rec in records:
        iso3 = _normalize_iso3(rec.get("iso3"))
        if not iso3 or len(iso3) != 3:
            # Defensive: empty / non-3-letter ISO3 codes are
            # skipped. The HDX CSV uses uppercase ISO3 already.
            continue
        raw_score = rec.get("score")
        score = _coerce_int_score(raw_score)
        rows.append(
            {
                "iso3": iso3,
                "year": int(year),
                "country": str(rec.get("country") or "").strip(),
                "region": str(rec.get("region") or "").strip(),
                "cpi_score": score,
                "cpi_score_raw_value": (
                    "" if raw_score is None else str(raw_score).strip()
                ),
                "rank": (
                    _coerce_int_score(rec.get("rank"))
                ),
                "sources": (
                    _coerce_int_score(rec.get("sources"))
                ),
                "standard_error": (
                    _coerce_float_or_none(rec.get("standardError"))
                ),
                "lower_ci": (
                    _coerce_float_or_none(rec.get("lowerCi"))
                ),
                "upper_ci": (
                    _coerce_float_or_none(rec.get("upperCi"))
                ),
            }
        )

    df = pd.DataFrame(
        rows,
        columns=[
            "iso3",
            "year",
            "country",
            "region",
            "cpi_score",
            "cpi_score_raw_value",
            "rank",
            "sources",
            "standard_error",
            "lower_ci",
            "upper_ci",
        ],
    )
    # Sort by iso3 for deterministic idempotency. The HDX CSV
    # rows are already sorted alphabetically by country name
    # (not by ISO3); sorting here guarantees the Stage 2 frame is
    # identical across re-runs.
    if not df.empty:
        df = df.sort_values("iso3", kind="mergesort").reset_index(
            drop=True
        )
    # Type coercion: year to int, indicator columns to
    # float (NaN for missing).
    df["year"] = df["year"].astype(int)
    df["cpi_score"] = pd.to_numeric(
        df["cpi_score"], errors="coerce"
    ).astype(float)
    return df


def _coerce_float_or_none(cell: object) -> float | None:
    """Coerce an HDX CSV numeric cell to ``float | None``.

    Used for the audit-trail columns (``standard_error``,
    ``lower_ci``, ``upper_ci``) which are floats in the HDX CSV.
    Returns ``None`` for empty / missing / non-parseable cells.
    """
    if cell is None:
        return None
    if isinstance(cell, bool):
        return None
    if isinstance(cell, float):
        if math.isnan(cell):
            return None
        return cell
    if isinstance(cell, int):
        return float(cell)
    if isinstance(cell, str):
        stripped = cell.strip()
        if stripped in _MISSING_STRINGS:
            return None
        try:
            return float(stripped)
        except ValueError:
            return None
    return None


__all__ = ["read_transparency_cpi_csv"]
