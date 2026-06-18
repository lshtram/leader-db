"""Stage 2 -- UNDP HDI wide-to-long UNPIVOT helper.

This module is the UNPIVOT half of the UNDP HDI CSV read. It
owns the wide-to-long transformation that produces a narrow
observation frame (one row per ``(iso3, year, variable_name)``
triple).

The CSV-read orchestrator (:func:`undp_hdi_csv.read_undp_hdi_csv`)
reads the wide-format latin-1 CSV; this module handles the
``pd.melt`` + ``{prefix}_{year}`` parsing + empty-cell drop +
``source_row_reference`` attachment.

The split follows the WGI / UCDP / SIPRI milex / SIPRI Yearbook
Ch.7 / PTS pattern. The wide-to-long UNPIVOT is a distinct
concern from the CSV-read (which is a file I/O concern), and the
split keeps the read module under the 400-line convention cap.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from .undp_hdi_csv import _parse_col_year
from .undp_hdi_io import UNDP_HDI_STATIC_COLUMNS, load_undp_hdi_catalog

_logger = logging.getLogger(__name__)

__all__ = ["build_undp_hdi_observations"]


def build_undp_hdi_observations(
    wide_df: pd.DataFrame,
    *,
    catalog_path: Path | None = None,
    year: int | None = None,
) -> pd.DataFrame:
    """UNPIVOT the wide frame to a narrow observation frame.

    Produces one row per ``(iso3, year, variable_name)`` triple:

    - ``id_vars`` (preserved from the wide frame): ``iso3``,
      ``country``, ``region``, ``hdicode``.
    - ``variable_name``: the catalog ``variable_name`` resolved
      from the ``{prefix}_{year}`` column name via the catalog.
    - ``year``: int, parsed from the ``_{year}`` suffix.
    - ``raw_value``: the original cell text (string; ``""`` for
      empty cells -- the caller is expected to drop these).
    - ``source_row_reference``: ``"undp_hdi:<iso3>"`` (e.g.
      ``"undp_hdi:USA"``) per architecture §7.

    The catalog's ``raw_column`` set is the filter: any
    ``{prefix}_{year}`` column whose prefix is NOT in the catalog
    is dropped (rank fields, year-2022-only metadata, non-social-
    wellbeing prefixes). Empty cells are dropped at DEBUG level
    per architecture §6 (debug-level events, not WARNING spam).

    Args:
        wide_df: the wide-format DataFrame from
            :func:`undp_hdi_csv.read_undp_hdi_csv`.
        catalog_path: override the indicator catalog. Default:
            checked-in.
        year: if set, filter the narrow frame to this year only.
            The default (``None``) keeps all years.

    Returns:
        A narrow DataFrame with the columns ``iso3``, ``country``,
        ``region``, ``hdicode``, ``variable_name``, ``year``,
        ``raw_value``, ``source_row_reference``. ``year`` is int.
    """
    # The catalog's ``raw_column`` set is the filter: any
    # ``{prefix}_{year}`` column whose prefix is NOT in the
    # catalog is dropped (rank fields, year-2022-only metadata,
    # non-social-wellbeing prefixes).
    specs = load_undp_hdi_catalog(catalog_path=catalog_path)
    prefix_to_variable: dict[str, str] = {
        spec.raw_column: spec.variable_name for spec in specs
    }
    in_scope_prefixes = set(prefix_to_variable.keys())

    # Find the in-scope ``{prefix}_{year}`` columns.
    parseable_cols: list[str] = []
    for col in wide_df.columns:
        if col in UNDP_HDI_STATIC_COLUMNS:
            continue
        parsed = _parse_col_year(col)
        if parsed is None:
            continue
        prefix, _year = parsed
        if prefix in in_scope_prefixes:
            parseable_cols.append(col)
    if not parseable_cols:
        return pd.DataFrame(
            columns=(
                "iso3", "country", "region", "hdicode",
                "variable_name", "year", "raw_value",
                "source_row_reference",
            ),
        )

    # ``pd.melt`` UNPIVOT.
    long_df = wide_df.melt(
        id_vars=list(UNDP_HDI_STATIC_COLUMNS),
        value_vars=parseable_cols,
        var_name="col_year",
        value_name="raw_value",
    )

    # Parse ``{prefix}_{year}`` -> ``(prefix, year)``. Drop
    # rows whose ``col_year`` does not parse (defensive).
    parsed_series = long_df["col_year"].map(_parse_col_year)
    long_df = long_df.assign(
        prefix=parsed_series.map(
            lambda p: p[0] if p is not None else None,
        ),
        year=parsed_series.map(
            lambda p: p[1] if p is not None else None,
        ),
    )
    long_df = long_df.dropna(subset=["prefix", "year"]).copy()
    long_df["year"] = long_df["year"].astype(int)
    long_df["variable_name"] = long_df["prefix"].map(prefix_to_variable)

    if year is not None:
        long_df = long_df.loc[long_df["year"] == int(year)].copy()

    # Drop empty cells at DEBUG level (per architecture §6).
    raw_str = long_df["raw_value"].astype(str)
    is_empty = (
        raw_str.str.strip().eq("") | raw_str.str.lower().eq("nan")
    )
    empty_count = int(is_empty.sum())
    if empty_count:
        _logger.debug(
            "UNDP HDI dropping %d empty cell(s) during UNPIVOT "
            "(debug-level per architecture §6).",
            empty_count,
        )
    long_df = long_df.loc[~is_empty].copy()

    # Audit-trail ``source_row_reference`` per architecture §7.
    long_df["source_row_reference"] = (
        "undp_hdi:" + long_df["iso3"].astype(str)
    )

    # Sort for deterministic output. (year ASC, iso3 ASC,
    # variable_name ASC) -- matches the WGI / UCDP / SIPRI
    # pattern.
    long_df = long_df.sort_values(
        by=["year", "iso3", "variable_name"],
        ascending=[True, True, True],
        kind="mergesort",
    ).reset_index(drop=True)

    return long_df[
        [
            "iso3", "country", "region", "hdicode",
            "variable_name", "year", "raw_value",
            "source_row_reference",
        ]
    ]
