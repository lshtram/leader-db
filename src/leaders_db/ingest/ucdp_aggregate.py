"""Stage 2 -- UCDP event-level to country-year aggregation.

This module holds the long-to-wide aggregation that turns the UCDP
event-level frame into the country-year x 6-indicator wide frame the
score modules need. It is split out of :mod:`ucdp_io` to keep the IO
module focused on catalog + zip + parquet, and to keep this
aggregation logic isolated and testable on its own.

The aggregation is a 3-groupby long-to-wide pivot on
``(country_id, year)``:

- ``ucdp_state_based_*`` (events + fatalities): type_of_violence == 1
- ``ucdp_onesided_*`` (events + fatalities):    type_of_violence == 3
- ``ucdp_intl_*`` (events + fatalities):        type_of_violence == 1
                                                 AND gwnob.notna()

The cross-border / internationalized filter uses the ``gwnob`` column
(Gleditsch-Ward state number for side_b). Live probe of the real
UCDP GED 23.1 shows ``gwnob`` is non-null for 6,150 / 227,509
state-based events (2.7%) -- the genuine internationalized subset.
See :file:`docs/architecture/ucdp.md` §2.6 for the rationale.

The wide frame is dense: every (country, year) combination that
appears in the input becomes a row, even if the country had no
type=1 or type=3 events in that year (the row has 0 / 0.0 for the
absent indicators). This matches the architect's design §2.2
step 6 ("the wide frame is dense").
"""

from __future__ import annotations

import pandas as pd


def aggregate_events_to_country_year(
    df_long: pd.DataFrame,
    indicator_variables: list[str],
    *,
    grid: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Aggregate the UCDP long frame to a country-year wide frame.

    Args:
        df_long: the long-format frame loaded by
            :func:`ucdp_io.read_ucdp` (after year filter, types
            coerced). Must have the columns ``id``, ``year``,
            ``country_id``, ``type_of_violence``, ``best``, ``gwnob``.
        indicator_variables: the catalog ``variable_name`` list
            (used to guarantee every catalog column appears in the
            output, even if a future catalog extension adds an
            indicator that no aggregation produced).
        grid: optional pre-computed cross-product grid of
            ``(country_id, year)`` pairs. When supplied, the helper
            left-merges the aggregated frames onto this grid. When
            omitted, the helper computes its own grid from the
            unique ``country_id`` and ``year`` values in
            ``df_long``. The orchestrator pre-computes the grid
            from the unfiltered long frame so a year filter does
            not drop country-years that have no events in the
            requested year (e.g., Germany 2021 in the test
            fixture).

    Returns:
        A wide DataFrame with columns ``country_id``, ``year``,
        then one column per catalog ``variable_name``:
        ``ucdp_state_based_events``, ``ucdp_state_based_fatalities``,
        ``ucdp_intl_events``, ``ucdp_intl_fatalities``,
        ``ucdp_onesided_events``, ``ucdp_onesided_fatalities``.
        The frame is dense: every (country, year) pair from the
        grid is present. Counts are ``Int64`` (nullable; filled
        with 0 for present country-year groups with no events of
        the corresponding type). Fatalities are ``float`` (filled
        with 0.0).
    """
    # Build the dense (country_id, year) grid: cross-product of
    # every unique country in the input and every unique year in the
    # input. The architect's design §2.2 step 6 says the wide frame
    # is dense; the test fixture's 5 countries x 2 years = 10 rows
    # only holds if Germany 2021 (which has no events) is a row.
    if grid is None:
        unique_countries = sorted(
            df_long["country_id"].drop_duplicates().tolist()
        )
        unique_years = sorted(df_long["year"].drop_duplicates().tolist())
        grid = pd.MultiIndex.from_product(
            [unique_countries, unique_years],
            names=["country_id", "year"],
        ).to_frame(index=False)

    # Events filtered: type=1 OR type=3. Type=2 (non-state) is not on
    # the catalog; the intl subset is inside the type=1 group.
    type_filter_mask = df_long["type_of_violence"].isin([1, 3])
    events_filtered = int(type_filter_mask.sum())

    # Aggregate: 3 groupby's, one per indicator category.
    # ``ucdp_state_based_*``: type_of_violence == 1.
    # ``ucdp_onesided_*``:    type_of_violence == 3.
    # ``ucdp_intl_*``:         type_of_violence == 1 AND gwnob.notna().
    sb_mask = df_long["type_of_violence"] == 1
    os_mask = df_long["type_of_violence"] == 3
    intl_mask = sb_mask & df_long["gwnob"].notna()

    sb = (
        df_long.loc[sb_mask]
        .groupby(["country_id", "year"], as_index=False)
        .agg(
            ucdp_state_based_events=("id", "count"),
            ucdp_state_based_fatalities=("best", "sum"),
        )
    )
    intl = (
        df_long.loc[intl_mask]
        .groupby(["country_id", "year"], as_index=False)
        .agg(
            ucdp_intl_events=("id", "count"),
            ucdp_intl_fatalities=("best", "sum"),
        )
    )
    os_agg = (
        df_long.loc[os_mask]
        .groupby(["country_id", "year"], as_index=False)
        .agg(
            ucdp_onesided_events=("id", "count"),
            ucdp_onesided_fatalities=("best", "sum"),
        )
    )

    # Left-merge the aggregated frames onto the dense grid. Every
    # grid row is preserved; missing indicator columns are filled
    # with 0 / 0.0 below.
    wide = grid.merge(sb, on=["country_id", "year"], how="left")
    wide = wide.merge(intl, on=["country_id", "year"], how="left")
    wide = wide.merge(os_agg, on=["country_id", "year"], how="left")

    # Defensive: ensure every catalog indicator column is present.
    # The merges above produce all 6 columns because all three
    # frames carry the 6 columns (2 across the three frames: sb has
    # 2, intl has 2, os has 2). But if a future catalog added an
    # indicator that no aggregation produced, this guard ensures
    # we materialize the column with 0 / 0.0 rather than crashing
    # in the orchestrator.
    for var in indicator_variables:
        if var not in wide.columns:
            wide[var] = 0 if var.endswith("_events") else 0.0

    # Fill NaN values from the left merge:
    #   - event counts: 0 (the country-year had no events of that type)
    #   - fatalities:   0.0 (the country-year had no events of that
    #     type with a ``best`` value)
    count_cols = (
        "ucdp_state_based_events",
        "ucdp_intl_events",
        "ucdp_onesided_events",
    )
    sum_cols = (
        "ucdp_state_based_fatalities",
        "ucdp_intl_fatalities",
        "ucdp_onesided_fatalities",
    )
    for col in count_cols:
        if col in wide.columns:
            wide[col] = wide[col].fillna(0).astype("Int64")
    for col in sum_cols:
        if col in wide.columns:
            wide[col] = wide[col].fillna(0.0).astype(float)

    # Coerce ids / year to plain int (pandas Int64 is fine, but plain
    # int reads more cleanly in the orchestrator and parquet).
    wide["country_id"] = wide["country_id"].astype(int)
    wide["year"] = wide["year"].astype(int)

    # Sort for determinism (tests rely on stable order).
    wide = wide.sort_values(
        by=["country_id", "year"], ascending=[True, True], kind="mergesort"
    ).reset_index(drop=True)

    # Attach the events_filtered count so the orchestrator can
    # surface it on the IngestResult. The events_total count is set
    # by the caller (it is the pre-aggregation event count).
    wide.attrs["events_filtered"] = events_filtered
    return wide


__all__ = ["aggregate_events_to_country_year"]
