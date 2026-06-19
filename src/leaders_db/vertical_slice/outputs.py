"""Output writers for the 2023 vertical slice (architecture doc §9).

Produces three files under ``data/outputs/vertical_slice_2023/``:

- ``vertical_slice_scores.csv``
- ``vertical_slice_comparison.csv``
- ``vertical_slice_summary.md``

When the caller passes a ``years=`` sequence, a fourth source-only file
is also written:

- ``vertical_slice_timeseries.csv``

All four carry the source attribution for UNDP HDI and WGI (per
Always-On Rule #15) and an explicit "provisional / not final scoring"
caveat (architecture doc §1 + §9). The summary explicitly states that
the client comparison is 2023-only when multi-year output is requested.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ..paths import outputs_dir
from .constants import (
    CLIENT_ATTRIBUTION,
    OUTPUT_COMPARISON_CSV,
    OUTPUT_DIR_NAME,
    OUTPUT_SCORES_CSV,
    OUTPUT_SUMMARY_MD,
    OUTPUT_TIMESERIES_CSV,
    SLICE_NOTE_PREFIX,
    UNDP_HDI_ATTRIBUTION,
    WGI_ATTRIBUTION,
)


@dataclass(frozen=True)
class ScoreRow:
    """One row in ``vertical_slice_scores.csv`` (architecture doc §9.1)."""

    iso3: str
    country: str
    leader: str
    year: int
    category_key: str
    client_score: int | None
    system_proposed_score: int | None
    final_score: int | None
    score_delta_vs_client: int | None
    confidence_score: int | None
    source_variable: str
    source_year: int | None
    source_raw_value: str | None
    review_status: str
    rationale_short: str


@dataclass(frozen=True)
class ComparisonRow:
    """One row in ``vertical_slice_comparison.csv`` (architecture doc §9.2)."""

    iso3: str
    country: str
    year: int
    category_key: str
    client_score: int | None
    system_proposed_score: int | None
    score_delta_vs_client: int | None
    confidence_score: int | None
    validation_status: str
    missing_reason: str
    manual_review_required: bool
    rationale_short: str


@dataclass(frozen=True)
class TimeseriesRow:
    """One row in ``vertical_slice_timeseries.csv`` (multi-year source-only).

    Source-only output: there is no client comparison column. The DB
    rows (``ruler_years`` / ``ruler_scores`` / ``validation_results``)
    remain 2023-only; this file is the source-of-truth for the
    multi-year extension and never writes to the DB.
    """

    iso3: str
    country: str
    year: int
    category_key: str
    system_proposed_score: int | None
    source_variable: str
    source_year: int | None
    source_raw_value: str | None
    source_kind: str  # "direct" or "proxy"
    confidence_score: int | None
    note: str


def output_dir(root: Path | None = None) -> Path:
    """Return the absolute path to the slice's output directory.

    Pass ``root`` to override the data-lake root (tests use it via the
    ``LEADERSDB_PROJECT_ROOT`` env var). The directory layout follows
    the conventional data-lake rule:
    ``<project_root>/data/outputs/vertical_slice_2023/``.

    When ``root`` is ``None`` (the default), the function uses
    :func:`leaders_db.paths.outputs_dir` to avoid double-appending
    ``data/`` (which would otherwise produce ``data/data/outputs``).
    """
    if root is None:
        target = outputs_dir() / OUTPUT_DIR_NAME
    else:
        target = root / "data" / "outputs" / OUTPUT_DIR_NAME
    target.mkdir(parents=True, exist_ok=True)
    return target


def output_paths(root: Path | None = None) -> tuple[Path, Path, Path, Path]:
    """Return the absolute paths of the four output files.

    The fourth path is the multi-year time-series CSV. It is only
    written by the orchestrator when ``years=`` is provided; this
    helper always returns the canonical path so callers can detect the
    file's existence or absence.
    """
    out_dir = output_dir(root)
    return (
        out_dir / OUTPUT_SCORES_CSV,
        out_dir / OUTPUT_COMPARISON_CSV,
        out_dir / OUTPUT_SUMMARY_MD,
        out_dir / OUTPUT_TIMESERIES_CSV,
    )


def write_scores_csv(rows: Iterable[ScoreRow], *, root: Path | None = None) -> Path:
    """Persist the per-score CSV. Returns the absolute path."""
    path, _, _, _ = output_paths(root)
    fieldnames = [
        "iso3", "country", "leader", "year", "category_key",
        "client_score", "system_proposed_score", "final_score",
        "score_delta_vs_client", "confidence_score", "source_variable",
        "source_year", "source_raw_value", "review_status", "rationale_short",
    ]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(_score_row_to_dict(row))
    return path


def write_comparison_csv(
    rows: Iterable[ComparisonRow], *, root: Path | None = None
) -> Path:
    """Persist the per-(country, category) comparison CSV."""
    _, path, _, _ = output_paths(root)
    fieldnames = [
        "iso3", "country", "year", "category_key",
        "client_score", "system_proposed_score", "score_delta_vs_client",
        "confidence_score", "validation_status", "missing_reason",
        "manual_review_required", "rationale_short",
    ]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(_comparison_row_to_dict(row))
    return path


def write_timeseries_csv(
    rows: Iterable[TimeseriesRow], *, root: Path | None = None
) -> Path:
    """Persist the multi-year source-only time-series CSV.

    One row per ``(year, country, category)`` tuple for which a source
    observation was available. The file is the only place
    multi-year ``system_proposed_score`` rows live; the DB remains
    2023-only.
    """
    _, _, _, path = output_paths(root)
    fieldnames = [
        "iso3", "country", "year", "category_key",
        "system_proposed_score", "source_variable",
        "source_year", "source_raw_value", "source_kind",
        "confidence_score", "note",
    ]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(_timeseries_row_to_dict(row))
    return path


def write_summary_md(
    *,
    score_rows: list[ScoreRow],
    comparison_rows: list[ComparisonRow],
    countries: tuple[str, ...],
    categories: tuple[str, ...],
    target_year: int,
    sources_used: tuple[str, ...],
    direct_year_count: int,
    proxy_year_count: int,
    skipped: list[tuple[str, str, str]],
    root: Path | None = None,
    timeseries_years: tuple[int, ...] | None = None,
) -> Path:
    """Persist the human-readable summary markdown.

    When ``timeseries_years`` is non-empty, the summary names every
    requested year and states that the client comparison is 2023-only
    (the multi-year extension is source-only and lives in
    ``vertical_slice_timeseries.csv``).
    """
    _, _, path, _ = output_paths(root)
    timestamp = datetime.now(tz=UTC).isoformat(timespec="seconds")
    body = _render_summary(
        score_rows=score_rows,
        comparison_rows=comparison_rows,
        countries=countries,
        categories=categories,
        target_year=target_year,
        sources_used=sources_used,
        direct_year_count=direct_year_count,
        proxy_year_count=proxy_year_count,
        skipped=skipped,
        timestamp=timestamp,
        timeseries_years=timeseries_years,
    )
    path.write_text(body, encoding="utf-8")
    return path


def _render_summary(
    *,
    score_rows: list[ScoreRow],
    comparison_rows: list[ComparisonRow],
    countries: tuple[str, ...],
    categories: tuple[str, ...],
    target_year: int,
    sources_used: tuple[str, ...],
    direct_year_count: int,
    proxy_year_count: int,
    skipped: list[tuple[str, str, str]],
    timestamp: str,
    timeseries_years: tuple[int, ...] | None,
) -> str:
    deltas: list[str] = []
    for row in score_rows:
        kind = (
            "proxy" if row.source_year is not None and row.source_year != target_year
            else "direct"
        )
        deltas.append(
            f"| {row.iso3} | {row.country} | {row.category_key} | "
            f"{row.client_score if row.client_score is not None else '—'} | "
            f"{row.system_proposed_score if row.system_proposed_score is not None else '—'} | "
            f"{row.score_delta_vs_client if row.score_delta_vs_client is not None else '—'} | "
            f"{row.confidence_score if row.confidence_score is not None else '—'} | "
            f"{row.source_year if row.source_year is not None else '—'} ({kind}) |"
        )

    attribution_blocks: list[str] = []
    if "undp_hdi" in sources_used:
        attribution_blocks.append(f"- **UNDP HDR 2023-24** — {UNDP_HDI_ATTRIBUTION}")
    if "world_bank_wgi" in sources_used:
        attribution_blocks.append(f"- **World Bank WGI** — {WGI_ATTRIBUTION}")
    attribution_blocks.append(
        f"- **Client-supplied 2023 matrix** — {CLIENT_ATTRIBUTION}"
    )
    attribution_text = "\n".join(attribution_blocks)

    skipped_lines = (
        "\n".join(f"- {iso3} / {category}: {reason}" for iso3, category, reason in skipped)
        or "- (none)"
    )

    timeseries_block = ""
    if timeseries_years:
        years_label = ", ".join(str(year) for year in timeseries_years)
        timeseries_block = f"""- Time-series years requested: **{years_label}**
- Caveat: client comparison is 2023-only — the multi-year extension is
  source-only and is written to `vertical_slice_timeseries.csv`. The DB
  (`ruler_years`, `ruler_scores`, `validation_results`) stays scoped to
  the target year {target_year}.
"""

    return f"""# Vertical slice 2023 — summary

> **Provisional, experimental, not final scoring.** This output is a named
> vertical slice used to discover integration gaps in the Stage 3-15
> pipeline. The scoring formulas are deliberately simple (single-source,
> HDI for social_wellbeing and WGI Control of Corruption for integrity)
> and do **not** reflect the production rubric. Use only for testing and
> methodological review; not for redistribution.

- Generated at: `{timestamp}`
- Target year: **{target_year}**
- Countries: `{", ".join(countries)}`
- Categories: `{", ".join(categories)}`
- Sources used: `{", ".join(sources_used) if sources_used else "(none — all categories skipped)"}`
- Direct-year observations: **{direct_year_count}**
- Proxy-year observations (2022 -> {target_year}): **{proxy_year_count}**
{timeseries_block}

## Country x category delta table

| ISO3 | Country | Category | Client | System | Δ | Confidence | Source year (kind) |
|---|---|---|---|---|---|---|---|
{chr(10).join(deltas) if deltas else "| _no score rows_ | | | | | | | |"}

## Skipped inputs

{skipped_lines}

## Notes

- Every slice-owned row carries the `{SLICE_NOTE_PREFIX}` marker.
- `final_score` remains NULL — the slice proposes scores but does not
  override the client matrix.
- Leader identities are seeded from the client matrix with
  `match_status="client_only"`; the real Stage 4 leader resolver is not
  invoked by this slice.

## Sources & attribution

This report draws on:

{attribution_text}
"""


def _score_row_to_dict(row: ScoreRow) -> dict[str, object]:
    return {
        "iso3": row.iso3,
        "country": row.country,
        "leader": row.leader,
        "year": row.year,
        "category_key": row.category_key,
        "client_score": "" if row.client_score is None else row.client_score,
        "system_proposed_score": (
            "" if row.system_proposed_score is None else row.system_proposed_score
        ),
        "final_score": "" if row.final_score is None else row.final_score,
        "score_delta_vs_client": (
            "" if row.score_delta_vs_client is None else row.score_delta_vs_client
        ),
        "confidence_score": (
            "" if row.confidence_score is None else row.confidence_score
        ),
        "source_variable": row.source_variable,
        "source_year": "" if row.source_year is None else row.source_year,
        "source_raw_value": (
            "" if row.source_raw_value is None else row.source_raw_value
        ),
        "review_status": row.review_status,
        "rationale_short": row.rationale_short,
    }


def _comparison_row_to_dict(row: ComparisonRow) -> dict[str, object]:
    return {
        "iso3": row.iso3,
        "country": row.country,
        "year": row.year,
        "category_key": row.category_key,
        "client_score": "" if row.client_score is None else row.client_score,
        "system_proposed_score": (
            "" if row.system_proposed_score is None else row.system_proposed_score
        ),
        "score_delta_vs_client": (
            "" if row.score_delta_vs_client is None else row.score_delta_vs_client
        ),
        "confidence_score": (
            "" if row.confidence_score is None else row.confidence_score
        ),
        "validation_status": row.validation_status,
        "missing_reason": row.missing_reason,
        "manual_review_required": "true" if row.manual_review_required else "false",
        "rationale_short": row.rationale_short,
    }


def _timeseries_row_to_dict(row: TimeseriesRow) -> dict[str, object]:
    return {
        "iso3": row.iso3,
        "country": row.country,
        "year": row.year,
        "category_key": row.category_key,
        "system_proposed_score": (
            "" if row.system_proposed_score is None else row.system_proposed_score
        ),
        "source_variable": row.source_variable,
        "source_year": "" if row.source_year is None else row.source_year,
        "source_raw_value": (
            "" if row.source_raw_value is None else row.source_raw_value
        ),
        "source_kind": row.source_kind,
        "confidence_score": (
            "" if row.confidence_score is None else row.confidence_score
        ),
        "note": row.note,
    }


__all__ = [
    "ComparisonRow",
    "ScoreRow",
    "TimeseriesRow",
    "output_dir",
    "output_paths",
    "write_comparison_csv",
    "write_scores_csv",
    "write_summary_md",
    "write_timeseries_csv",
]
