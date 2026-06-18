"""Stage 2 -- Political Terror Scale (PTS) long-to-wide pivot helper.

This module is the pivot half of the PTS xlsx read. It owns:

- :func:`pivot_long_to_wide` -- turn the per-row ``(country, cow_code,
  year, region, variable_name, value)`` long records into the dense
  wide-format frame (one row per ``(COW_Code_A, Year)``, one column per
  catalog ``variable_name``).
- :func:`_attach_raw_lookup` -- attach the pre-coercion
  ``(country, year, variable_name) -> raw_cell_text`` audit lookup to
  ``df.attrs["_pts_raw_lookup"]`` so the DB writer can recover the
  literal xlsx cell text (the ``"NA"`` sentinel or the stringified
  int) for the ``source_observations.raw_value`` audit trail.
- :func:`_empty_wide_frame` -- helper that emits the canonical empty
  wide frame with the expected columns + the required ``df.attrs``
  (raw_lookup, regions_covered, year_window).

The sentinel matrix (:func:`_coerce_pts_value`, the §6 4-case
precedence rule) and the raw-cell-text audit helper
(:func:`_raw_cell_text`) live in :mod:`leaders_db.ingest.pts_xlsx`
alongside the read orchestrator and the xlsx-reader
(:func:`read_xlsx_to_long_dataframe`). The xlsx-reader produces the
long-format frame; the caller (:func:`pts_xlsx.read_pts_from_dataframe`)
iterates that frame, applies the sentinel matrix per indicator, builds
the long records + raw_lookup, and delegates to
:func:`pivot_long_to_wide` for the wide-frame construction.

The §6 wide-frame contract (the "dense" requirement):

- One row per ``(COW_Code_A, Year)`` present in the long frame (even
  when all 3 indicator cells are missing).
- Every catalog ``variable_name`` has a column; if ``pivot_table``
  drops a column because all values are NaN, we re-add it as an
  all-``pd.NA`` ``Int64`` column so downstream code does not have to
  special-case missing columns.
- ``year`` is ``int``; indicator columns are ``Int64`` (nullable).
- The display columns (``country``, ``cow_code``, ``region``) are
  ``object`` dtype (plain Python strings), not the pandas StringDtype
  extension type.

The wide frame also carries three audit attrs:

- ``df.attrs["_pts_raw_lookup"]`` -- the pre-coercion raw cell text
  lookup (stripped by :func:`pts_io.write_pts_parquet` before the
  parquet write because pyarrow cannot JSON-serialize the tuple keys).
- ``df.attrs["regions_covered"]`` -- a sorted list of the unique
  ``region`` values found in the wide frame, preserved verbatim (the
  ``'mena, ssa'`` data anomaly per §6.4 is preserved as a literal).
- ``df.attrs["year_window"]`` -- a ``(start_year, end_year)`` tuple
  representing the min/max year in the wide frame (or ``(0, 0)`` for
  the empty-frame case).

The :class:`IndicatorSpec` dataclass, the catalog loader, and the path
helpers live in :mod:`leaders_db.ingest.pts_io` to break the import
cycle. The DB helpers live in
:mod:`leaders_db.ingest.pts_db` and
:mod:`leaders_db.ingest.pts_db_helpers`. The orchestrator that ties
everything together lives in :mod:`leaders_db.ingest.pts`.
"""

from __future__ import annotations

import logging

import pandas as pd

_logger = logging.getLogger(__name__)

__all__ = ["pivot_long_to_wide"]


# Canonical 3-indicator metadata. Mirrored as module-level constants
# in :mod:`pts_xlsx` so the test seam can construct a valid wide frame
# without instantiating IndicatorSpec objects. We re-import the same
# tuple here to keep this module self-contained for the pivot logic.
_PTS_INDICATOR_COLS: tuple[tuple[str, str], ...] = (
    ("PTS_A", "pts_amnesty_score"),
    ("PTS_H", "pts_human_rights_watch_score"),
    ("PTS_S", "pts_state_dept_score"),
)


# ---------------------------------------------------------------------------
# Wide frame construction (the §6 "dense" contract)
# ---------------------------------------------------------------------------


def _empty_wide_frame(
    raw_lookup: dict[tuple[str, int, str], str] | None = None,
    *,
    regions_covered: list[str] | None = None,
    year_window: tuple[int, int] = (0, 0),
) -> pd.DataFrame:
    """Build the canonical empty wide frame with all required ``df.attrs``.

    Used for the empty-input short-circuit and the
    empty-long-records short-circuit so downstream code does not have
    to special-case the empty case (the wide frame is always emitted
    with the expected columns + the three audit attrs).
    """
    wide = pd.DataFrame(
        columns=(
            "country", "cow_code", "year", "region",
            *[vn for _rc, vn in _PTS_INDICATOR_COLS],
        )
    )
    wide.attrs["_pts_raw_lookup"] = dict(raw_lookup or {})
    wide.attrs["regions_covered"] = sorted(regions_covered or [])
    wide.attrs["year_window"] = year_window
    return wide


def _attach_raw_lookup(
    df_wide: pd.DataFrame,
    raw_lookup: dict[tuple[str, int, str], str],
) -> pd.DataFrame:
    """Attach the pre-coercion raw-cell-text lookup to ``df.attrs``.

    The lookup uses ``(country, year, variable_name)`` as the key (the
    canonical variable_name, not the raw xlsx column name) so the DB
    writer can find the raw text by the same key it iterates over.

    The lookup is attached in-place and returned for caller convenience
    (so the pivot orchestrator can chain ``df = _attach_raw_lookup(df,
    raw_lookup)``).
    """
    df_wide.attrs["_pts_raw_lookup"] = raw_lookup
    return df_wide


def pivot_long_to_wide(
    long_records: list[dict[str, object]],
    raw_lookup: dict[tuple[str, int, str], str],
    *,
    year: int | None = None,
) -> pd.DataFrame:
    """Pivot the per-row long records into the §6 wide-format frame.

    The wide frame is **dense**: every ``(COW_Code_A, Year)`` pair from
    the long records is present in the output, even when all 3
    indicator cells are missing. Every catalog ``variable_name`` has
    a column; if ``pivot_table`` drops one because all values are NaN,
    we re-add it as an all-``pd.NA`` ``Int64`` column.

    Steps:

    1. Build the long DataFrame from the records (one row per
       ``(country, cow_code, year, region, variable_name)``).
    2. Pivot to wide: ``(country, cow_code, year, region)`` index,
       ``variable_name`` columns, ``value`` as values,
       ``aggfunc="first"``.
    3. Re-add any catalog ``variable_name`` column that ``pivot_table``
       dropped (the all-NaN case).
    4. Coerce ``year`` to ``int``; coerce the display columns
       (``country``, ``cow_code``, ``region``) to ``object``; coerce
       indicator columns to ``Int64``.
    5. Apply the defensive ``year=`` post-pivot filter (the long-step
       filter in :func:`pts_xlsx.read_xlsx_to_long_dataframe` is the
       primary path for xlsx-driven runs; this handles the case where
       a caller passes a pre-loaded DataFrame that was not filtered).
    6. Attach the three audit attrs (``_pts_raw_lookup``,
       ``regions_covered``, ``year_window``) and return.

    Args:
        long_records: the per-row records built by
            :func:`pts_xlsx.read_pts_from_dataframe`. Each record is
            ``{"country": str, "cow_code": str, "year": int,
            "region": str, "variable_name": str, "value": int | None}``.
        raw_lookup: the pre-coercion ``(country, year, variable_name)
            -> raw_cell_text`` audit lookup, attached to the wide
            frame's ``df.attrs["_pts_raw_lookup"]``.
        year: filter to a single year after the pivot. Default: keep
            all years.

    Returns:
        A pandas DataFrame with columns ``country``, ``cow_code``,
        ``year``, ``region``, then one column per catalog
        ``variable_name``. ``year`` is ``int``. Indicator columns are
        ``Int64`` (nullable; ``pd.NA`` = missing per §6). The wide
        frame carries ``_pts_raw_lookup``, ``regions_covered``, and
        ``year_window`` in ``df.attrs``.
    """
    if not long_records:
        # Nothing to pivot -- emit the canonical empty frame so the
        # downstream code does not have to special-case the empty case.
        return _empty_wide_frame(raw_lookup)

    long_df = pd.DataFrame.from_records(long_records)
    if long_df.empty:
        return _empty_wide_frame(raw_lookup)

    # Pivot to wide format: one row per (country, cow_code, year,
    # region), one column per variable_name. We include cow_code
    # and region in the index so they survive the pivot (the long
    # frame's identity columns are repeated for each of the 3
    # indicators).
    wide = long_df.pivot_table(
        index=["country", "cow_code", "year", "region"],
        columns="variable_name",
        values="value",
        aggfunc="first",
    )
    wide = wide.reset_index()
    # ``pivot_table`` drops a column if ALL its values are NaN
    # (e.g. a country-year where all 3 indicators were dropped by
    # the §6 sentinel matrix, like Bahamas 2017 case-4 across all
    # 3 indicators). The wide frame contract requires every
    # catalog indicator to have a column -- re-add the missing ones
    # as all-NaN ``Int64`` columns so downstream code does not have
    # to special-case missing columns.
    for _raw_col, var_name in _PTS_INDICATOR_COLS:
        if var_name not in wide.columns:
            wide[var_name] = pd.array([pd.NA] * len(wide), dtype="Int64")

    # Coerce types. ``year`` is already int from the construction
    # above; cast explicitly for paranoia. Indicator columns are
    # ``Int64`` (nullable; ``pd.NA`` for the §6 dropped cells).
    wide["year"] = wide["year"].astype(int)
    # pandas may convert string columns to StringDtype after the
    # pivot (because the index column was promoted to object and
    # then back to string). Force the display columns (``country``,
    # ``cow_code``, ``region``) to ``object`` dtype so downstream
    # consumers (the DB writer, the tests) see plain Python strings,
    # not the pandas StringDtype extension type.
    for col_name in ("country", "cow_code", "region"):
        if col_name in wide.columns:
            wide[col_name] = wide[col_name].astype(object)
    for _raw_col, var_name in _PTS_INDICATOR_COLS:
        if var_name in wide.columns:
            wide[var_name] = wide[var_name].astype("Int64")

    # Defensive year filter at the post-pivot step (the long-step
    # filter in ``read_xlsx_to_long_dataframe`` is the primary path
    # for xlsx-driven runs; this handles the case where a caller
    # passes a pre-loaded DataFrame that was not filtered).
    if year is not None:
        wide = wide.loc[wide["year"] == int(year)].reset_index(drop=True)

    # Attach the raw_lookup attr for the DB writer's audit trail.
    _attach_raw_lookup(wide, raw_lookup)

    # Surface the source-specific extras as additional attrs so the
    # orchestrator can carry them into the PtsIngestResult. Sorted
    # list of region codes present in the wide frame (including
    # the ``"mena, ssa"`` anomaly per §6.4).
    wide.attrs["regions_covered"] = sorted(
        {str(r) for r in wide["region"].dropna().unique().tolist() if str(r)},
    )
    if not wide.empty:
        wide.attrs["year_window"] = (
            int(wide["year"].min()), int(wide["year"].max()),
        )
    else:
        wide.attrs["year_window"] = (0, 0)

    return wide
