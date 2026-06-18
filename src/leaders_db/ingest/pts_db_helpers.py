"""Stage 2 -- Political Terror Scale (PTS) DB helpers: coercion + bundle metadata.

This module holds the pure helper functions used by :mod:`pts_db`. It
is split out of :mod:`pts_db` so the DB module stays focused on the
DB-write contract (sources, source_observations, run manifest) and
the helper module stays focused on the observation-row builder and
the bundle-metadata parsing rules.

The split is mandated by architecture §5: "no separate `_helpers.py`
unless the module grows past 350 lines." :mod:`pts_db` reached 431
lines (the trigger fired at 351), so the helpers are extracted into
this module -- mirroring the WGI 5-module split (``wgi_db.py`` +
``wgi_db_helpers.py``).

Owns:

- :func:`_read_pts_bundle_metadata` -- read
  ``data/raw/political_terror_scale/metadata.json`` if present;
  checks both the ``pts`` and ``political_terror_scale`` folder
  conventions.
- :func:`_parse_download_date` -- parse an ISO date from the bundle
  metadata; return ``None`` on failure.
- :func:`_parse_year_range` -- parse a ``"YYYY-YYYY"`` year range;
  return ``(None, None)`` on failure.
- :func:`_build_observation_rows` -- in-memory builder for
  ``SourceObservation`` rows from the wide-format pandas frame.

The DB-write functions (:func:`pts_db.register_pts_source`,
:func:`pts_db.write_pts_observations`, :func:`pts_db.write_pts_run_manifest`)
live in :mod:`leaders_db.ingest.pts_db`. The orchestrator that ties
everything together lives in :mod:`leaders_db.ingest.pts`.
"""

from __future__ import annotations

import json
import logging
from datetime import date

import pandas as pd

from ..db.models import SourceObservation
from ..paths import raw_dir
from .pts_io import PTS_SOURCE_KEY, IndicatorSpec

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Bundle metadata helpers
# ---------------------------------------------------------------------------


def _read_pts_bundle_metadata() -> dict[str, object]:
    """Read ``data/raw/political_terror_scale/metadata.json`` if present."""
    # The data-lake folder is ``political_terror_scale`` (the
    # human-readable bundle name), not ``pts`` (the source key).
    # Resolve both candidates so the helper works regardless of
    # which folder convention the operator used.
    for candidate in (PTS_SOURCE_KEY, "political_terror_scale"):
        path = raw_dir(candidate) / "metadata.json"
        if path.is_file():
            try:
                return dict(json.loads(path.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                return {}
    return {}


def _parse_download_date(raw: object) -> date | None:
    """Parse an ISO date from the bundle metadata; return ``None`` on failure."""
    if not isinstance(raw, str):
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _parse_year_range(raw: object) -> tuple[int | None, int | None]:
    """Parse a ``"YYYY-YYYY"`` year range; return ``(None, None)`` on failure."""
    if not isinstance(raw, str) or "-" not in raw:
        return (None, None)
    start_str, end_str = raw.split("-", 1)
    try:
        return (int(start_str.strip()), int(end_str.strip()))
    except ValueError:
        return (None, None)


# ---------------------------------------------------------------------------
# Observation-row builder
# ---------------------------------------------------------------------------


def _build_observation_rows(
    source_id: int,
    df: pd.DataFrame,
    specs: list[IndicatorSpec],
) -> list[SourceObservation]:
    """Build the ``source_observations`` rows in memory (no DB session needed).

    Iterates the wide frame row-by-row; for each spec, writes one
    :class:`SourceObservation` row. ``raw_value`` is recovered from
    ``df.attrs["_pts_raw_lookup"]`` (the pre-coercion cell-text
    lookup built by :func:`pts_xlsx.read_pts_from_dataframe`); this
    is the source of truth for the original xlsx cell text (the
    literal ``"NA"`` for case-3/4 cells; the stringified int for
    case-1/2 cells). For dropped cells (any of cases 2, 3, 4),
    ``raw_value`` is ``None`` and ``normalized_value`` is ``None``.

    Iteration order: ``(year ASC, cow_code ASC)`` via stable mergesort.
    """
    rows: list[SourceObservation] = []
    # Sort: stable mergesort breaks ties by cow_code so insertion
    # order is fully deterministic. The sort key matches the WGI /
    # UCDP / SIPRI milex / SIPRI Yearbook Ch.7 pattern.
    sorted_df = df.sort_values(
        by=["year", "cow_code"], ascending=[True, True], kind="mergesort",
    )
    # (country, year, variable_name) -> raw cell text lookup from
    # the read orchestrator's _pts_raw_lookup attr. The key uses the
    # canonical ``variable_name`` (not the raw column name) so the
    # DB writer can find it by the same key it iterates over.
    raw_lookup: dict[tuple[str, int, str], str] = (
        df.attrs.get("_pts_raw_lookup", {}) or {}
    )

    for _, raw_row in sorted_df.iterrows():
        country = str(raw_row.get("country") or "")
        cow_code = str(raw_row.get("cow_code") or "")
        year = int(raw_row["year"])
        # The source_row_reference carries the COW code per §7.3
        # (e.g. ``pts:USA``). The country display name is kept on
        # the wide frame for audit but is NOT used as the primary
        # key -- the COW code is the Stage 3 join target.
        source_row_reference = f"pts:{cow_code}" if cow_code else "pts:"
        for spec in specs:
            if spec.variable_name not in raw_row.index:
                # No data column for this spec (e.g. the wide frame
                # was empty for some reason). Skip -- no observation
                # to record.
                continue
            cell = raw_row[spec.variable_name]
            # Coerce the post-pivot cell to int 1-5 or None. The
            # wide frame holds ``pd.NA`` for dropped cells (per the
            # §6 sentinel matrix). Per the test-builder's contract
            # (full fixture: 11 valid observations; year=2023: only
            # the country-year pairs with valid cells produce
            # observations), we SKIP dropped cells here rather than
            # writing a NULL ``normalized_value`` row. The §6.3
            # audit-trail matrix still records the raw cell text in
            # ``df.attrs["_pts_raw_lookup"]`` so a future iteration
            # can write the dropped rows with NULL ``normalized_value``
            # if the cross-source comparison needs them.
            if cell is None or pd.isna(cell):
                # Skip dropped cells (any flavor of NA: Python None,
                # ``float('nan')``, or ``pd.NA``). Do not write a row.
                continue
            if isinstance(cell, int) and not isinstance(cell, bool):
                value: int = int(cell)
            else:
                # Defensive: unexpected type after the wide pivot.
                # The reader should only emit int or NA; if we see
                # something else, log and skip (treat as missing --
                # don't crash the run).
                _logger.warning(
                    "PTS DB write: unexpected cell type %r for "
                    "(country=%s, year=%d, indicator=%s). Skipping.",
                    type(cell).__name__, country, year, spec.variable_name,
                )
                continue
            # Recover the pre-coercion raw cell for the audit trail.
            # If the lookup misses (e.g. the caller passed a DataFrame
            # without the raw_lookup attr), fall back to the
            # stringified cell value as a defense in depth.
            raw_cell = raw_lookup.get(
                (country, year, spec.variable_name),
            )
            raw_value_str: str
            if raw_cell is not None:
                raw_value_str = str(raw_cell)
            else:
                # Defense in depth: stringify the int value.
                raw_value_str = str(int(value))

            rows.append(
                SourceObservation(
                    source_id=source_id,
                    country_id=None,  # Stage 3 fills this in
                    leader_id=None,
                    year=year,
                    variable_name=spec.variable_name,
                    raw_value=raw_value_str,
                    normalized_value=value,
                    unit=spec.unit,
                    source_row_reference=source_row_reference,
                    confidence=None,  # set by Stage 11
                    notes=(
                        f"raw_scale={spec.raw_scale}; "
                        f"higher_is_better={1 if spec.higher_is_better else 0}"
                    ),
                )
            )
    return rows


# Re-export so the orchestrator can call the helper without touching
# the private ``_`` prefix when accessed from outside the module
# (e.g., for tests that want to verify the builder directly).
__all__ = [
    "_build_observation_rows",
    "_parse_download_date",
    "_parse_year_range",
    "_read_pts_bundle_metadata",
]
