"""Derived analytic tables for the Superset-facing SQLite artifact.

This module produces the additional CSVs that the local Superset dashboards
read on top of the canonical ``viz_country_year_metrics`` fact table:

- ``viz_country_year_growth`` — country-year observations with year-over-year
  growth columns. Same grain as the source fact table plus
  ``prev_value``, ``yoy_abs_change``, ``yoy_pct_growth`` and ``decade``.
- ``viz_regime_year_aggregates`` — aggregate metrics rolled up by
  ``(year, metric_id, political_regime_bucket)`` and by
  ``(year, metric_id, political_regime)`` for regime-comparison charts.
- ``viz_country_latest_metrics`` — one row per country with the latest
  available observation for each metric plus decade-growth CAGR and
  rank fields for leaderboard charts.

All generators are pure functions that read the source CSV from disk and
return a ``pandas.DataFrame``. The CLI orchestrator is responsible for
writing the CSVs and rebuilding the SQLite DB; see
:mod:`leaders_db.viz.superset_db`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

GROWTH_CSV_FILENAME = "viz_country_year_growth.csv"
REGIME_AGGREGATES_CSV_FILENAME = "viz_regime_year_aggregates.csv"
COUNTRY_LATEST_CSV_FILENAME = "viz_country_latest_metrics.csv"

SOURCE_FACT_FILENAME = "viz_country_year_metrics.csv"

GROWTH_COLUMNS: tuple[str, ...] = (
    "metric_id",
    "year_date",
    "year",
    "country_iso3",
    "country_name",
    "political_regime",
    "political_regime_bucket",
    "existence_status",
    "value",
    "prev_value",
    "yoy_abs_change",
    "yoy_pct_growth",
    "decade",
)

REGIME_AGGREGATES_COLUMNS: tuple[str, ...] = (
    "year",
    "metric_id",
    "political_regime_bucket",
    "political_regime",
    "n_countries",
    "mean_value",
    "sum_value",
    "pop_weighted_mean_value",
    "prev_mean_value",
    "mean_yoy_pct_growth",
)

COUNTRY_LATEST_COLUMNS: tuple[str, ...] = (
    "country_iso3",
    "country_name",
    "latest_year",
    "latest_population",
    "latest_gdp",
    "latest_gdp_per_capita",
    "political_regime",
    "political_regime_bucket",
    "existence_status",
    "population_rank",
    "gdp_rank",
    "gdp_per_capita_rank",
    "population_10yr_cagr_pct",
    "gdp_10yr_cagr_pct",
    "gdp_per_capita_10yr_cagr_pct",
)


@dataclass(frozen=True)
class GrowthTableBuildResult:
    """Summary of a derived-tables build."""

    output_dir: Path
    growth_csv: Path
    regime_aggregates_csv: Path
    country_latest_csv: Path
    growth_rows: int
    regime_aggregates_rows: int
    country_latest_rows: int


def build_growth_tables(
    *,
    data_dir: Path,
    source_filename: str = SOURCE_FACT_FILENAME,
    growth_filename: str = GROWTH_CSV_FILENAME,
    regime_aggregates_filename: str = REGIME_AGGREGATES_CSV_FILENAME,
    country_latest_filename: str = COUNTRY_LATEST_CSV_FILENAME,
) -> GrowthTableBuildResult:
    """Build the derived visualization CSVs under ``data_dir``.

    Reads ``source_filename`` from ``data_dir`` and writes the three
    derived CSVs next to it. Idempotent: an existing file is overwritten.
    """
    source_path = data_dir / source_filename
    if not source_path.is_file():
        raise FileNotFoundError(
            f"Required source fact CSV is missing: {source_path}. "
            "Run the country-year Chronicle analytic export first."
        )

    fact = _read_fact_csv(source_path)
    growth = build_country_year_growth(fact)
    regime_aggregates = build_regime_year_aggregates(fact, growth=growth)
    country_latest = build_country_latest_metrics(fact)

    growth_path = data_dir / growth_filename
    regime_path = data_dir / regime_aggregates_filename
    latest_path = data_dir / country_latest_filename

    growth.to_csv(growth_path, index=False)
    regime_aggregates.to_csv(regime_path, index=False)
    country_latest.to_csv(latest_path, index=False)

    return GrowthTableBuildResult(
        output_dir=data_dir,
        growth_csv=growth_path,
        regime_aggregates_csv=regime_path,
        country_latest_csv=latest_path,
        growth_rows=len(growth),
        regime_aggregates_rows=len(regime_aggregates),
        country_latest_rows=len(country_latest),
    )


def build_country_year_growth(fact: pd.DataFrame) -> pd.DataFrame:
    """Return a per-(country, metric, year) frame with YoY growth columns.

    The output is sorted by ``(country_iso3, metric_id, year)`` so the
    Superset ``year_date`` axis lines up with the source fact table.
    """
    required = {
        "metric_id",
        "year",
        "country_iso3",
        "value",
        "year_date",
        "country_name",
        "political_regime",
        "political_regime_bucket",
        "existence_status",
    }
    missing = required - set(fact.columns)
    if missing:
        raise ValueError(f"Fact frame is missing required columns: {sorted(missing)}.")

    work = fact[list(required)].copy()
    work = work.sort_values(["country_iso3", "metric_id", "year"]).reset_index(drop=True)

    grouped = work.groupby(["country_iso3", "metric_id"], sort=False)
    work["prev_value"] = grouped["value"].shift(1)
    work["yoy_abs_change"] = work["value"] - work["prev_value"]
    work["yoy_pct_growth"] = _safe_pct_growth(work["value"], work["prev_value"])
    work["decade"] = (work["year"] // 10) * 10
    return work[list(GROWTH_COLUMNS)]


def build_regime_year_aggregates(
    fact: pd.DataFrame, *, growth: pd.DataFrame | None = None
) -> pd.DataFrame:
    """Aggregate metrics by year, metric, regime bucket, and 5-regime label.

    Produces rows at two granularities:

    - bucket-level rows (``political_regime_bucket`` filled,
      ``political_regime`` empty) — for democracy-vs-non-democracy charts.
    - 5-regime rows (``political_regime_bucket`` empty,
      ``political_regime`` filled) — for Authoritarian / Flawed / Full /
      Hybrid / Unknown charts.

    ``growth`` is the country-level growth frame produced by
    :func:`build_country_year_growth`; if omitted it is computed internally.
    """
    if growth is None:
        growth = build_country_year_growth(fact)
    work = fact.dropna(subset=["value"]).copy()
    work["_pop"] = (
        work["metric_id"].eq("chronicle.population").astype(float) * work["value"]
    )
    pop_lookup = (
        work[work["metric_id"] == "chronicle.population"][
            ["country_iso3", "year", "_pop"]
        ].rename(columns={"_pop": "_country_pop"})
    )
    work = work.merge(pop_lookup, on=["country_iso3", "year"], how="left")

    bucket_agg = _aggregate_by(work, group_col="political_regime_bucket", bucket=True)
    regime_agg = _aggregate_by(work, group_col="political_regime", bucket=False)

    country_yoy = growth.dropna(subset=["yoy_pct_growth"])[
        [
            "metric_id",
            "year",
            "country_iso3",
            "political_regime",
            "political_regime_bucket",
            "yoy_pct_growth",
        ]
    ]

    def attach_yoy(df: pd.DataFrame, group_col: str) -> pd.DataFrame:
        yoy_group_key = (
            "political_regime_bucket"
            if group_col == "political_regime_bucket"
            else "political_regime"
        )
        yoy_mean = (
            country_yoy.groupby(["year", "metric_id", yoy_group_key], sort=False)["yoy_pct_growth"]
            .mean()
            .reset_index()
            .rename(columns={"yoy_pct_growth": "mean_yoy_pct_growth"})
        )
        return df.merge(
            yoy_mean,
            on=["year", "metric_id", yoy_group_key],
            how="left",
        )

    bucket_agg = attach_yoy(bucket_agg, "political_regime_bucket")
    regime_agg = attach_yoy(regime_agg, "political_regime")

    combined = pd.concat([bucket_agg, regime_agg], ignore_index=True, sort=False)
    combined = combined.sort_values(
        ["year", "metric_id", "political_regime_bucket", "political_regime"]
    ).reset_index(drop=True)
    for col in REGIME_AGGREGATES_COLUMNS:
        if col not in combined.columns:
            combined[col] = float("nan")
    return combined[list(REGIME_AGGREGATES_COLUMNS)]


def _aggregate_by(
    work: pd.DataFrame, *, group_col: str, bucket: bool
) -> pd.DataFrame:
    """Aggregate a (year, metric, regime-group) frame.

    When ``bucket`` is True the group column is ``political_regime_bucket``
    and ``political_regime`` is left empty. When ``bucket`` is False the
    group column is ``political_regime`` and ``political_regime_bucket`` is
    left empty. The population-weighted mean uses each country's
    population in the same year as the weight.
    """
    work = work.assign(
        _weighted_value=work["value"] * work["_country_pop"].fillna(0)
    )
    groups = work.groupby(["year", "metric_id", group_col], sort=False, dropna=False)
    agg = groups.agg(
        n_countries=("country_iso3", "nunique"),
        mean_value=("value", "mean"),
        sum_value=("value", "sum"),
        _weighted_sum=("_weighted_value", "sum"),
        _pop_sum=("_country_pop", "sum"),
    ).reset_index()

    agg["pop_weighted_mean_value"] = agg.apply(
        lambda r: (r["_weighted_sum"] / r["_pop_sum"])
        if pd.notna(r["_pop_sum"]) and r["_pop_sum"] > 0
        else float("nan"),
        axis=1,
    )

    if bucket:
        agg = agg.rename(columns={"political_regime_bucket": "political_regime_bucket"})
        agg["political_regime"] = ""
    else:
        agg = agg.rename(columns={"political_regime": "political_regime"})
        agg["political_regime_bucket"] = ""

    agg["prev_mean_value"] = agg.groupby(
        ["metric_id", group_col], sort=False
    )["mean_value"].shift(1)

    agg = agg.drop(columns=["_weighted_sum", "_pop_sum"])
    return agg[
        [
            "year",
            "metric_id",
            "political_regime_bucket",
            "political_regime",
            "n_countries",
            "mean_value",
            "sum_value",
            "pop_weighted_mean_value",
            "prev_mean_value",
        ]
    ]


def build_country_latest_metrics(fact: pd.DataFrame) -> pd.DataFrame:
    """One row per country with the latest observation per metric + CAGR.

    Each metric's latest observation year is taken independently (so GDP
    may be 2023 while population may be 2025); the country-level
    ``latest_year`` column reports the most recent year across all
    metrics. Ranking and CAGR columns use the latest available value per
    metric, with NaN for missing metrics.
    """
    required = {
        "metric_id",
        "year",
        "country_iso3",
        "country_name",
        "political_regime",
        "political_regime_bucket",
        "existence_status",
        "value",
    }
    missing = required - set(fact.columns)
    if missing:
        raise ValueError(f"Fact frame is missing required columns: {sorted(missing)}.")

    work = fact.dropna(subset=["value"]).copy()
    work = work.sort_values(["country_iso3", "metric_id", "year"])
    latest_idx = work.groupby(["country_iso3", "metric_id"])["year"].idxmax()
    latest = work.loc[
        latest_idx,
        [
            "country_iso3",
            "country_name",
            "political_regime",
            "political_regime_bucket",
            "existence_status",
            "year",
            "metric_id",
            "value",
        ],
    ]

    pivot = latest.pivot_table(
        index="country_iso3",
        columns="metric_id",
        values=["year", "value"],
        aggfunc="first",
    )
    pivot.columns = [f"{measure}_{metric}" for measure, metric in pivot.columns]
    pivot = pivot.reset_index()

    metric_lookup = {
        "chronicle.population": "latest_population",
        "chronicle.gdp": "latest_gdp",
        "chronicle.gdp_per_capita": "latest_gdp_per_capita",
    }
    rename_map: dict[str, str] = {}
    for metric_col, alias in metric_lookup.items():
        if f"value_{metric_col}" in pivot.columns:
            rename_map[f"value_{metric_col}"] = alias
        if f"year_{metric_col}" in pivot.columns:
            rename_map[f"year_{metric_col}"] = f"{alias.replace('latest_', '')}_latest_year"
    pivot = pivot.rename(columns=rename_map)

    for alias in metric_lookup.values():
        if alias not in pivot.columns:
            pivot[alias] = float("nan")

    year_cols = [c for c in pivot.columns if c.endswith("_latest_year")]
    if year_cols:
        pivot["latest_year"] = pivot[year_cols].max(axis=1)
    else:
        pivot["latest_year"] = float("nan")

    profile = (
        work.sort_values(["country_iso3", "year"])
        .groupby("country_iso3", as_index=False)
        .agg(
            country_name=("country_name", "last"),
            political_regime=("political_regime", "last"),
            political_regime_bucket=("political_regime_bucket", "last"),
            existence_status=("existence_status", "last"),
        )
    )
    pivot = pivot.merge(profile, on="country_iso3", how="left")

    pivot["population_rank"] = pivot["latest_population"].rank(
        ascending=False, method="min"
    )
    pivot["gdp_rank"] = pivot["latest_gdp"].rank(ascending=False, method="min")
    pivot["gdp_per_capita_rank"] = pivot["latest_gdp_per_capita"].rank(
        ascending=False, method="min"
    )

    cagr = _country_cagr(fact, window_years=10)
    pivot = pivot.merge(cagr, on="country_iso3", how="left")

    for col in (
        "population_10yr_cagr_pct",
        "gdp_10yr_cagr_pct",
        "gdp_per_capita_10yr_cagr_pct",
    ):
        if col not in pivot.columns:
            pivot[col] = float("nan")

    pivot = pivot.sort_values("country_iso3").reset_index(drop=True)
    keep = [c for c in COUNTRY_LATEST_COLUMNS if c in pivot.columns]
    return pivot[keep]


def _country_cagr(fact: pd.DataFrame, *, window_years: int) -> pd.DataFrame:
    """Compute decade CAGR per country per metric.

    CAGR is ``(end/start) ** (1/n) - 1``; if the country does not have a
    matching observation ``window_years`` years before its latest year
    the CAGR is NaN.
    """
    work = fact.dropna(subset=["value"]).copy()
    work = work.sort_values(["country_iso3", "metric_id", "year"])
    latest_idx = work.groupby(["country_iso3", "metric_id"])["year"].idxmax()
    latest = work.loc[
        latest_idx, ["country_iso3", "metric_id", "year", "value"]
    ].rename(columns={"year": "end_year", "value": "end_value"})

    targets = latest[["country_iso3", "metric_id"]].copy()
    targets["target_year"] = latest["end_year"] - window_years

    lookup = work.merge(targets, on=["country_iso3", "metric_id"])
    lookup = lookup[lookup["year"] == lookup["target_year"]].rename(
        columns={"value": "start_value"}
    )[["country_iso3", "metric_id", "start_value", "target_year"]]
    merged = latest.merge(lookup, on=["country_iso3", "metric_id"], how="left")

    years_diff = (merged["end_year"] - merged["target_year"]).astype(float)
    safe_start = merged["start_value"].replace({0: float("nan")})
    ratio = merged["end_value"] / safe_start
    cagr_pct = (ratio ** (1.0 / years_diff) - 1.0) * 100.0
    cagr_pct = cagr_pct.where(years_diff > 0)
    cagr_pct = cagr_pct.where(safe_start.notna() & (safe_start > 0))
    cagr_pct = cagr_pct.where(ratio.notna())

    pivot_cagr = pd.DataFrame(
        {
            "country_iso3": merged["country_iso3"],
            "metric_id": merged["metric_id"],
            "cagr_pct": cagr_pct,
        }
    ).pivot_table(
        index="country_iso3", columns="metric_id", values="cagr_pct", aggfunc="first"
    ).reset_index()

    rename_map = {
        "chronicle.population": "population_10yr_cagr_pct",
        "chronicle.gdp": "gdp_10yr_cagr_pct",
        "chronicle.gdp_per_capita": "gdp_per_capita_10yr_cagr_pct",
    }
    pivot_cagr = pivot_cagr.rename(
        columns={k: v for k, v in rename_map.items() if k in pivot_cagr.columns}
    )
    return pivot_cagr


def _safe_pct_growth(value: pd.Series, prev_value: pd.Series) -> pd.Series:
    """Return ``value / prev_value - 1`` with NaN/zero guards."""
    out = value.astype(float) / prev_value.astype(float) - 1.0
    out = out.where(prev_value.notna() & (prev_value != 0))
    out = out.where(value.notna())
    return out


def _read_fact_csv(path: Path) -> pd.DataFrame:
    """Read the source fact CSV with stable types."""
    frame = pd.read_csv(path)
    if "year_date" in frame.columns:
        frame["year_date"] = pd.to_datetime(frame["year_date"])
    else:
        frame["year_date"] = pd.to_datetime(frame["year"], format="%Y")
    return frame


__all__ = [
    "COUNTRY_LATEST_COLUMNS",
    "COUNTRY_LATEST_CSV_FILENAME",
    "GROWTH_COLUMNS",
    "GROWTH_CSV_FILENAME",
    "REGIME_AGGREGATES_COLUMNS",
    "REGIME_AGGREGATES_CSV_FILENAME",
    "SOURCE_FACT_FILENAME",
    "GrowthTableBuildResult",
    "build_country_latest_metrics",
    "build_country_year_growth",
    "build_growth_tables",
    "build_regime_year_aggregates",
]
