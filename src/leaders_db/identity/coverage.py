"""Detailed D3-D5 ruler identity coverage and gap reporting."""

from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from leaders_db.db.models import (
    Country,
    CountryYear,
    NormalizedObservationRow,
    RulerSpell,
    RulerYear,
)
from leaders_db.identity.ruler_identity import (
    DEFAULT_LOW_CONFIDENCE_THRESHOLD,
    LIMITATIONS,
    NON_EVIDENCE_SOURCE_DATASETS,
    _country_by_iso3,
    _country_by_normalized_name,
    _identity_observation_rows,
    _loads_json,
    _resolve_country,
    _row_to_spell_input,
    assert_identity_database_ready,
)
from leaders_db.normalize.countries import normalize_country_name, normalize_iso3
from leaders_db.paths import outputs_dir

IdentityGapClassification = Literal[
    "resolved",
    "resolved_auto_single_candidate",
    "resolved_auto_role_priority",
    "resolved_auto_duration_majority",
    "resolved_auto_year_coverage_majority",
    "missing_no_identity_observation",
    "missing_unresolved_country_mapping",
    "missing_source_out_of_range",
    "missing_current_source_cache",
    "multiple_candidates",
    "multiple_candidates_manual_review",
    "disputed_rule",
    "low_confidence",
    "source_conflict",
    "source_conflict_manual_review",
    "out_of_scope",
]

CURRENT_IDENTITY_SOURCE = "wikidata_heads_of_state_government"
CURRENT_IDENTITY_START_YEAR = 2022

CLASSIFICATION_MEANINGS: dict[str, str] = {
    "resolved": (
        "Backward-compatible label for one evidence-backed ruler candidate. New runs emit "
        "resolved_auto_single_candidate instead."
    ),
    "resolved_auto_single_candidate": (
        "Exactly one evidence-backed ruler candidate covers the included country-year."
    ),
    "resolved_auto_role_priority": (
        "Multiple candidates are preserved, and a principal ruler was selected because source "
        "metadata distinguishes an actual/dominant executive from formal-only officeholders."
    ),
    "resolved_auto_duration_majority": (
        "Multiple candidates are preserved, and a principal ruler was selected because one "
        "candidate covers a unique majority/longest duration of the year."
    ),
    "resolved_auto_year_coverage_majority": (
        "A second adjudication pass selected the principal ruler because dated candidate "
        "intervals show one candidate covered more than half of the target year without "
        "hard conflict flags."
    ),
    "missing_no_identity_observation": (
        "The country-year has no usable persisted identity observation and no narrower "
        "source-range/cache diagnostic applies."
    ),
    "missing_unresolved_country_mapping": (
        "Persisted identity observations in the requested year could not be mapped into "
        "countries.iso3."
    ),
    "missing_source_out_of_range": "Loaded identity sources do not cover this year.",
    "missing_current_source_cache": (
        "A current-year identity row is expected from the Wikidata cache path, but no usable "
        "row is loaded for this country-year."
    ),
    "multiple_candidates": (
        "Backward-compatible label for multiple unresolved candidates. New runs emit "
        "multiple_candidates_manual_review or source_conflict_manual_review."
    ),
    "multiple_candidates_manual_review": (
        "More than one distinct evidence-backed leader candidate covers the same country-year, "
        "and deterministic adjudication did not safely select a principal ruler."
    ),
    "disputed_rule": (
        "At least one covering identity source marks the rule as disputed or the builder "
        "marked the pair disputed."
    ),
    "low_confidence": (
        "The selected identity evidence is below the configured confidence threshold."
    ),
    "source_conflict": (
        "Backward-compatible label for cross-source leader disagreement. New runs emit "
        "source_conflict_manual_review."
    ),
    "source_conflict_manual_review": (
        "Multiple identity sources cover the pair but identify different leaders after alias, "
        "role, and duration adjudication; manual review is required."
    ),
    "out_of_scope": (
        "The country-year exists for audit but is excluded from the scoring denominator."
    ),
}


@dataclass(frozen=True)
class IdentitySourceDiagnostic:
    """Loaded identity-source diagnostics from normalized observations."""

    source_slug: str
    loaded_row_count: int
    min_year: int | None
    max_year: int | None
    country_count: int
    usable_observation_count: int
    skipped_observation_count: int
    unresolved_country_count: int
    missing_leader_count: int
    missing_time_anchor_count: int


@dataclass(frozen=True)
class IdentityCoverageDetailRow:
    """One country-year identity coverage/gap classification."""

    iso3: str
    country_name: str
    year: int
    included_in_project: bool
    classification: IdentityGapClassification
    ruler_count: int
    source_count: int
    source_slugs: tuple[str, ...]
    leader_names: tuple[str, ...]
    confidence_min: int | None
    confidence_max: int | None
    next_action: str
    reason: str


@dataclass(frozen=True)
class IdentityCoverageSummary:
    """Aggregate counts for the detailed identity report."""

    total_country_years: int
    included_country_years: int
    excluded_country_years: int
    classification_counts: dict[str, int]


@dataclass(frozen=True)
class IdentityCoverageGapReport:
    """Complete machine-readable D3-D5 identity report."""

    year: int | None
    start_year: int | None
    end_year: int | None
    low_confidence_threshold: int
    summary: IdentityCoverageSummary
    source_diagnostics: tuple[IdentitySourceDiagnostic, ...]
    rows: tuple[IdentityCoverageDetailRow, ...]
    classification_meanings: dict[str, str]
    limitations: tuple[str, ...]


def build_identity_coverage_gap_report(
    engine: Engine,
    *,
    year: int | None = None,
    start_year: int | None = None,
    end_year: int | None = None,
    include_out_of_scope: bool = True,
    low_confidence_threshold: int = DEFAULT_LOW_CONFIDENCE_THRESHOLD,
) -> IdentityCoverageGapReport:
    """Build a reusable per-country-year identity coverage/gap report."""

    if year is not None:
        start_year = year
        end_year = year
    if start_year is not None and end_year is not None and start_year > end_year:
        raise ValueError("start_year must be less than or equal to end_year")

    assert_identity_database_ready(engine)
    with Session(engine) as session:
        country_by_iso3 = _country_by_iso3(session)
        country_by_name = _country_by_normalized_name(session)
        all_identity_rows = _identity_observation_rows(
            session,
            start_year=None,
            end_year=None,
        )
        identity_rows = _identity_observation_rows(
            session,
            start_year=start_year,
            end_year=end_year,
        )
        source_diagnostics = _source_diagnostics(session, all_identity_rows)
        usable_by_pair = _usable_observation_pairs(identity_rows, country_by_iso3, country_by_name)
        unresolved_keys = _unresolved_country_keys(
            identity_rows,
            country_by_iso3,
            country_by_name,
        )
        source_ranges = {
            diagnostic.source_slug: (diagnostic.min_year, diagnostic.max_year)
            for diagnostic in source_diagnostics
            if diagnostic.min_year is not None and diagnostic.max_year is not None
        }
        ruler_rows = _ruler_year_rows(session, start_year=start_year, end_year=end_year)
        ruler_rows_by_pair: dict[tuple[int, int], list[tuple[RulerYear, RulerSpell]]] = {}
        for ruler_year, spell in ruler_rows:
            ruler_rows_by_pair.setdefault((ruler_year.country_id, ruler_year.year), []).append(
                (ruler_year, spell)
            )
        detail_rows = tuple(
            _detail_row(
                country_year,
                ruler_rows_by_pair.get((country_year.country_id, country_year.year), []),
                usable_by_pair=usable_by_pair,
                unresolved_keys=unresolved_keys,
                source_ranges=source_ranges,
                include_out_of_scope=include_out_of_scope,
                low_confidence_threshold=low_confidence_threshold,
            )
            for country_year in _country_year_rows(
                session,
                start_year=start_year,
                end_year=end_year,
                include_out_of_scope=include_out_of_scope,
            )
        )

    return IdentityCoverageGapReport(
        year=year,
        start_year=start_year,
        end_year=end_year,
        low_confidence_threshold=low_confidence_threshold,
        summary=_summary(detail_rows),
        source_diagnostics=source_diagnostics,
        rows=detail_rows,
        classification_meanings=CLASSIFICATION_MEANINGS,
        limitations=LIMITATIONS,
    )


def identity_gap_report_to_json(
    report: IdentityCoverageGapReport, *, detail: bool
) -> dict[str, Any]:
    """Return a deterministic JSON-friendly report payload."""

    payload: dict[str, Any] = {
        "year": report.year,
        "start_year": report.start_year,
        "end_year": report.end_year,
        "low_confidence_threshold": report.low_confidence_threshold,
        "summary": asdict(report.summary),
        "source_diagnostics": [asdict(row) for row in report.source_diagnostics],
        "classification_meanings": report.classification_meanings,
        "limitations": list(report.limitations),
    }
    if detail:
        payload["rows"] = [_detail_row_to_json(row) for row in report.rows]
    return payload


def write_identity_gap_report_artifacts(
    report: IdentityCoverageGapReport,
    *,
    output_dir: Path | None = None,
) -> dict[str, Path]:
    """Write JSON, CSV, and Markdown artifacts under ``data/outputs`` by default."""

    directory = output_dir or outputs_dir()
    directory.mkdir(parents=True, exist_ok=True)
    stem = _artifact_stem(report)
    paths = {
        "json": directory / f"{stem}.json",
        "csv": directory / f"{stem}.csv",
        "markdown": directory / f"{stem}.md",
    }
    paths["json"].write_text(
        json.dumps(identity_gap_report_to_json(report, detail=True), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_csv(report, paths["csv"])
    paths["markdown"].write_text(identity_gap_report_to_markdown(report), encoding="utf-8")
    return paths


def identity_gap_report_to_markdown(report: IdentityCoverageGapReport) -> str:
    """Return a compact Markdown summary for human inspection."""

    lines = ["# Ruler identity coverage/gap report", ""]
    label = (
        str(report.year)
        if report.year is not None
        else f"{report.start_year or 'all'}-{report.end_year or 'all'}"
    )
    lines.append(f"Scope: `{label}`")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Total country-years: {report.summary.total_country_years}")
    lines.append(f"- Included country-years: {report.summary.included_country_years}")
    lines.append(f"- Excluded/out-of-scope country-years: {report.summary.excluded_country_years}")
    for key, count in sorted(report.summary.classification_counts.items()):
        lines.append(f"- `{key}`: {count}")
    lines.append("")
    lines.append("## Source diagnostics")
    lines.append("")
    lines.append("| Source | Rows | Years | Countries | Usable | Skipped | ")
    lines[-1] += "Unresolved country | Missing leader | Missing time |"
    lines.append("|---|---:|---|---:|---:|---:|---:|---:|---:|")
    for diagnostic in report.source_diagnostics:
        years = _year_range_label(diagnostic.min_year, diagnostic.max_year)
        lines.append(
            "| "
            f"{diagnostic.source_slug} | {diagnostic.loaded_row_count} | {years} | "
            f"{diagnostic.country_count} | {diagnostic.usable_observation_count} | "
            f"{diagnostic.skipped_observation_count} | {diagnostic.unresolved_country_count} | "
            f"{diagnostic.missing_leader_count} | {diagnostic.missing_time_anchor_count} |"
        )
    lines.append("")
    lines.append("## Classification meanings")
    lines.append("")
    for key, meaning in CLASSIFICATION_MEANINGS.items():
        lines.append(f"- `{key}` — {meaning}")
    return "\n".join(lines) + "\n"


def _country_year_rows(
    session: Session,
    *,
    start_year: int | None,
    end_year: int | None,
    include_out_of_scope: bool,
) -> tuple[CountryYear, ...]:
    statement = select(CountryYear).join(Country).order_by(CountryYear.year, Country.iso3)
    if start_year is not None:
        statement = statement.where(CountryYear.year >= start_year)
    if end_year is not None:
        statement = statement.where(CountryYear.year <= end_year)
    if not include_out_of_scope:
        statement = statement.where(CountryYear.included_in_project.is_(True))
    return tuple(session.scalars(statement).all())


def _ruler_year_rows(
    session: Session,
    *,
    start_year: int | None,
    end_year: int | None,
) -> tuple[tuple[RulerYear, RulerSpell], ...]:
    statement = (
        select(RulerYear, RulerSpell)
        .join(RulerSpell, RulerYear.ruler_spell_id == RulerSpell.id)
        .join(
            CountryYear,
            (CountryYear.country_id == RulerYear.country_id) & (CountryYear.year == RulerYear.year),
        )
        .where(
            RulerSpell.source_dataset.not_in(NON_EVIDENCE_SOURCE_DATASETS),
            CountryYear.included_in_project.is_(True),
        )
    )
    if start_year is not None:
        statement = statement.where(RulerYear.year >= start_year)
    if end_year is not None:
        statement = statement.where(RulerYear.year <= end_year)
    return tuple(session.execute(statement).all())


def _source_diagnostics(
    session: Session,
    rows: list[NormalizedObservationRow],
) -> tuple[IdentitySourceDiagnostic, ...]:
    by_source: dict[str, list[NormalizedObservationRow]] = {}
    country_by_iso3 = _country_by_iso3(session)
    country_by_name = _country_by_normalized_name(session)
    for row in rows:
        by_source.setdefault(row.source_slug, []).append(row)
    diagnostics = []
    for source_slug in sorted(by_source):
        source_rows = by_source[source_slug]
        years = [row.year for row in source_rows if row.year is not None]
        countries = {
            country.iso3
            for row in source_rows
            if (
                country := _resolve_country(
                    row, _loads_json(row.extension_json), country_by_iso3, country_by_name
                )
            )
            is not None
        }
        reason_counts = Counter(
            _skip_reason(row, country_by_iso3, country_by_name) for row in source_rows
        )
        usable = reason_counts.pop("usable", 0)
        diagnostics.append(
            IdentitySourceDiagnostic(
                source_slug=source_slug,
                loaded_row_count=len(source_rows),
                min_year=min(years) if years else None,
                max_year=max(years) if years else None,
                country_count=len(countries),
                usable_observation_count=usable,
                skipped_observation_count=len(source_rows) - usable,
                unresolved_country_count=reason_counts.get("unresolved_country", 0),
                missing_leader_count=reason_counts.get("missing_leader", 0),
                missing_time_anchor_count=reason_counts.get("missing_time_anchor", 0),
            )
        )
    return tuple(diagnostics)


def _skip_reason(
    row: NormalizedObservationRow,
    country_by_iso3: dict[str, Country],
    country_by_name: dict[str, Country],
) -> str:
    if _row_to_spell_input(row, country_by_iso3, country_by_name) is not None:
        return "usable"
    extension = _loads_json(row.extension_json)
    if _resolve_country(row, extension, country_by_iso3, country_by_name) is None:
        return "unresolved_country"
    leader_name = row.leader_name or extension.get("leader_name") or extension.get("person_label")
    if not str(leader_name or "").strip():
        return "missing_leader"
    return "missing_time_anchor"


def _usable_observation_pairs(
    rows: list[NormalizedObservationRow],
    country_by_iso3: dict[str, Country],
    country_by_name: dict[str, Country],
) -> set[tuple[int, int]]:
    pairs: set[tuple[int, int]] = set()
    for row in rows:
        candidate = _row_to_spell_input(row, country_by_iso3, country_by_name)
        if candidate is None:
            continue
        country = country_by_iso3[candidate.country_iso3]
        end_year = (
            candidate.end_date.year if candidate.end_date is not None else candidate.start_date.year
        )
        for obs_year in range(candidate.start_date.year, end_year + 1):
            pairs.add((country.id, obs_year))
    return pairs


def _unresolved_country_keys(
    rows: list[NormalizedObservationRow],
    country_by_iso3: dict[str, Country],
    country_by_name: dict[str, Country],
) -> set[tuple[int, str]]:
    keys: set[tuple[int, str]] = set()
    for row in rows:
        if row.year is None:
            continue
        if _skip_reason(row, country_by_iso3, country_by_name) != "unresolved_country":
            continue
        for key in _country_reference_keys(row):
            keys.add((int(row.year), key))
    return keys


def _country_reference_keys(row: NormalizedObservationRow) -> set[str]:
    extension = _loads_json(row.extension_json)
    keys: set[str] = set()
    for value in (
        row.country_code,
        extension.get("country_code"),
        extension.get("country_iso3"),
        extension.get("iso3"),
    ):
        if not value:
            continue
        try:
            keys.add(normalize_iso3(str(value)))
        except ValueError:
            keys.add(str(value).strip().upper())
    for value in (
        row.country_name,
        extension.get("country_name"),
        extension.get("country_label"),
    ):
        if value:
            keys.add(normalize_country_name(str(value)))
    return keys


def _detail_row(
    country_year: CountryYear,
    ruler_rows: list[tuple[RulerYear, RulerSpell]],
    *,
    usable_by_pair: set[tuple[int, int]],
    unresolved_keys: set[tuple[int, str]],
    source_ranges: dict[str, tuple[int | None, int | None]],
    include_out_of_scope: bool,
    low_confidence_threshold: int,
) -> IdentityCoverageDetailRow:
    if not include_out_of_scope and not country_year.included_in_project:
        raise ValueError("out-of-scope rows should have been filtered")
    country = country_year.country
    if not country_year.included_in_project:
        return _classified_row(
            country_year,
            "out_of_scope",
            [],
            "No scoring action; keep as audit-only scope row.",
            country_year.inclusion_reason or "excluded from project scope",
        )

    if ruler_rows:
        classification, reason, next_action = _covered_classification(
            ruler_rows,
            low_confidence_threshold=low_confidence_threshold,
        )
        return _classified_row(country_year, classification, ruler_rows, next_action, reason)

    pair = (country_year.country_id, country_year.year)
    if pair not in usable_by_pair and _has_unresolved_country_key(country_year, unresolved_keys):
        classification: IdentityGapClassification = "missing_unresolved_country_mapping"
        reason = "At least one identity observation for this year failed country mapping."
        next_action = "Improve source country-code/name mapping, then rebuild identity."
    elif (
        country_year.year >= CURRENT_IDENTITY_START_YEAR
        and CURRENT_IDENTITY_SOURCE in source_ranges
        and not _source_covers_year(source_ranges.get(CURRENT_IDENTITY_SOURCE), country_year.year)
    ):
        classification = "missing_current_source_cache"
        reason = "Current-year Wikidata identity observations are not loaded for this year."
        next_action = (
            "Ingest the local Wikidata HoS/HoG cache for this year, then rebuild identity."
        )
    elif not _any_source_covers_year(source_ranges, country_year.year):
        classification = "missing_source_out_of_range"
        reason = "Loaded identity source year ranges do not include this year."
        next_action = "Load an identity source whose coverage includes this year."
    else:
        classification = "missing_no_identity_observation"
        reason = "No usable identity observation produced a ruler_year for this country-year."
        next_action = "Inspect loaded identity observations and source-specific skipped counts."
    return IdentityCoverageDetailRow(
        iso3=country.iso3,
        country_name=country.country_name,
        year=country_year.year,
        included_in_project=True,
        classification=classification,
        ruler_count=0,
        source_count=0,
        source_slugs=(),
        leader_names=(),
        confidence_min=None,
        confidence_max=None,
        next_action=next_action,
        reason=reason,
    )


def _has_unresolved_country_key(
    country_year: CountryYear,
    unresolved_keys: set[tuple[int, str]],
) -> bool:
    country = country_year.country
    return (country_year.year, country.iso3) in unresolved_keys or (
        country_year.year,
        country.country_name_normalized,
    ) in unresolved_keys


def _covered_classification(  # noqa: PLR0911
    ruler_rows: list[tuple[RulerYear, RulerSpell]],
    *,
    low_confidence_threshold: int,
) -> tuple[IdentityGapClassification, str, str]:
    match_statuses = {ruler_year.match_status for ruler_year, _ in ruler_rows}
    for status in (
        "source_conflict_manual_review",
        "multiple_candidates_manual_review",
        "disputed_rule",
    ):
        if status in match_statuses:
            return _classification_from_adjudication(status)
    if any(
        spell.disputed_rule_flag or ruler_year.match_status == "disputed"
        for ruler_year, spell in ruler_rows
    ):
        return (
            "disputed_rule",
            "A source or builder status marks this rule as disputed.",
            "Manual review disputed-rule metadata.",
        )
    confidences = [
        row.confidence_score for row, _ in ruler_rows if row.confidence_score is not None
    ]
    if confidences and min(confidences) < low_confidence_threshold:
        return (
            "low_confidence",
            "Identity confidence is below threshold.",
            "Review or corroborate identity evidence.",
        )
    for status in (
        "resolved_auto_role_priority",
        "resolved_auto_duration_majority",
        "resolved_auto_single_candidate",
    ):
        if status in match_statuses:
            return _classification_from_adjudication(status)
    leader_ids = {ruler_year.leader_id for ruler_year, _ in ruler_rows}
    source_slugs = {spell.source_dataset for _, spell in ruler_rows}
    if len(source_slugs) > 1 and len(leader_ids) > 1:
        return (
            "source_conflict_manual_review",
            "Multiple sources identify different leaders.",
            "Manual adjudication required.",
        )
    if len(leader_ids) > 1:
        return (
            "multiple_candidates_manual_review",
            "More than one leader candidate covers this country-year.",
            "Manual adjudication required.",
        )
    return (
        "resolved_auto_single_candidate",
        "Exactly one evidence-backed ruler candidate covers this country-year.",
        "No identity action required.",
    )


def _classification_from_adjudication(
    status: str,
) -> tuple[IdentityGapClassification, str, str]:
    if status == "resolved_auto_role_priority":
        return (
            "resolved_auto_role_priority",
            "Adjudication selected a principal ruler using actual/formal role priority.",
            "No identity action required; inspect preserved competitor notes if needed.",
        )
    if status == "resolved_auto_duration_majority":
        return (
            "resolved_auto_duration_majority",
            "Adjudication selected a principal ruler using majority-year duration.",
            "No identity action required; inspect preserved transition candidates if needed.",
        )
    if status == "source_conflict_manual_review":
        return (
            "source_conflict_manual_review",
            "Multiple sources identify different leaders after deterministic adjudication.",
            "Manual adjudication required.",
        )
    if status == "multiple_candidates_manual_review":
        return (
            "multiple_candidates_manual_review",
            "Multiple candidates remain after deterministic adjudication.",
            "Manual adjudication required.",
        )
    if status == "disputed_rule":
        return (
            "disputed_rule",
            "A source or builder status marks this rule as disputed or hard conflict.",
            "Manual review disputed-rule metadata.",
        )
    return (
        "resolved_auto_single_candidate",
        "Exactly one evidence-backed ruler candidate covers this country-year.",
        "No identity action required.",
    )


def _classified_row(
    country_year: CountryYear,
    classification: IdentityGapClassification,
    ruler_rows: list[tuple[RulerYear, RulerSpell]],
    next_action: str,
    reason: str,
) -> IdentityCoverageDetailRow:
    confidences = [
        row.confidence_score for row, _ in ruler_rows if row.confidence_score is not None
    ]
    return IdentityCoverageDetailRow(
        iso3=country_year.country.iso3,
        country_name=country_year.country.country_name,
        year=country_year.year,
        included_in_project=country_year.included_in_project,
        classification=classification,
        ruler_count=len({row.leader_id for row, _ in ruler_rows}),
        source_count=len({spell.source_dataset for _, spell in ruler_rows}),
        source_slugs=tuple(sorted({spell.source_dataset for _, spell in ruler_rows})),
        leader_names=tuple(
            sorted({row.system_selected_leader_name or "" for row, _ in ruler_rows})
        ),
        confidence_min=min(confidences) if confidences else None,
        confidence_max=max(confidences) if confidences else None,
        next_action=next_action,
        reason=reason,
    )


def _summary(rows: tuple[IdentityCoverageDetailRow, ...]) -> IdentityCoverageSummary:
    counts = Counter(row.classification for row in rows)
    return IdentityCoverageSummary(
        total_country_years=len(rows),
        included_country_years=sum(1 for row in rows if row.included_in_project),
        excluded_country_years=sum(1 for row in rows if not row.included_in_project),
        classification_counts=dict(sorted(counts.items())),
    )


def _any_source_covers_year(
    source_ranges: dict[str, tuple[int | None, int | None]], year: int
) -> bool:
    return any(_source_covers_year(year_range, year) for year_range in source_ranges.values())


def _source_covers_year(year_range: tuple[int | None, int | None] | None, year: int) -> bool:
    if year_range is None:
        return False
    min_year, max_year = year_range
    return (min_year is None or min_year <= year) and (max_year is None or max_year >= year)


def _write_csv(report: IdentityCoverageGapReport, path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as file_obj:
        writer = csv.DictWriter(
            file_obj,
            fieldnames=list(_detail_row_to_json(report.rows[0]).keys()) if report.rows else [],
        )
        if not report.rows:
            return
        writer.writeheader()
        for row in report.rows:
            writer.writerow(_detail_row_to_json(row))


def _detail_row_to_json(row: IdentityCoverageDetailRow) -> dict[str, Any]:
    payload = asdict(row)
    payload["source_slugs"] = "|".join(row.source_slugs)
    payload["leader_names"] = "|".join(name for name in row.leader_names if name)
    return payload


def _artifact_stem(report: IdentityCoverageGapReport) -> str:
    if report.year is not None:
        return f"identity_ruler_coverage_{report.year}_gap_report"
    if report.start_year is not None or report.end_year is not None:
        start = report.start_year or "all"
        end = report.end_year or "all"
        return f"identity_ruler_coverage_{start}_{end}_gap_report"
    return "identity_ruler_coverage_all_gap_report"


def _year_range_label(min_year: int | None, max_year: int | None) -> str:
    if min_year is None and max_year is None:
        return "n/a"
    if min_year == max_year:
        return str(min_year)
    return f"{min_year or 'n/a'}-{max_year or 'n/a'}"


__all__ = [
    "CLASSIFICATION_MEANINGS",
    "IdentityCoverageDetailRow",
    "IdentityCoverageGapReport",
    "IdentityCoverageSummary",
    "IdentityGapClassification",
    "IdentitySourceDiagnostic",
    "build_identity_coverage_gap_report",
    "identity_gap_report_to_json",
    "identity_gap_report_to_markdown",
    "write_identity_gap_report_artifacts",
]
