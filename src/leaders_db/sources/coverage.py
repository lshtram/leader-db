"""Coverage reporting for persisted normalized source observations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import Engine

from .registry import SourceRegistry


@dataclass(frozen=True)
class ObservationCoverageRow:
    """DB-backed coverage aggregate for one source/family/indicator group."""

    source_slug: str
    observation_family: str
    indicator_code: str
    row_count: int
    min_year: int | None
    max_year: int | None
    country_count: int
    missing_raw_locator_count: int


@dataclass(frozen=True)
class SourceCoverageStatus:
    """Per-source load status derived from DB rows and registry metadata."""

    source_slug: str
    status: str
    row_count: int
    requires_manual_approval: bool


@dataclass(frozen=True)
class SourceCoverageReport:
    """Complete source coverage report payload."""

    rows: tuple[ObservationCoverageRow, ...]
    source_statuses: tuple[SourceCoverageStatus, ...]


def build_source_coverage_report(
    engine: Engine,
    *,
    registry: SourceRegistry | None = None,
) -> SourceCoverageReport:
    """Return deterministic coverage aggregates from ``normalized_observations``.

    This function reads only the persisted database table. When a registry is
    provided, zero-row sources are included in the status section so
    user-managed/blocked sources are distinct from ordinary not-yet-loaded rows.
    """

    rows = _coverage_rows(engine)
    statuses = _source_statuses(rows, registry=registry)
    return SourceCoverageReport(rows=rows, source_statuses=statuses)


def _coverage_rows(engine: Engine) -> tuple[ObservationCoverageRow, ...]:
    statement = text(
        """
        SELECT
            source_slug,
            observation_family,
            indicator_code,
            COUNT(*) AS row_count,
            MIN(year) AS min_year,
            MAX(year) AS max_year,
            COUNT(DISTINCT COALESCE(country_code, country_name)) AS country_count,
            SUM(
                CASE
                    WHEN raw_locator_json IS NULL
                      OR raw_locator_json = ''
                      OR raw_locator_json = 'null'
                      OR raw_locator_json = '{}'
                    THEN 1
                    ELSE 0
                END
            ) AS missing_raw_locator_count
        FROM normalized_observations
        GROUP BY source_slug, observation_family, indicator_code
        ORDER BY source_slug, observation_family, indicator_code
        """
    )
    with engine.connect() as conn:
        result = conn.execute(statement).mappings().all()
    return tuple(
        ObservationCoverageRow(
            source_slug=str(row["source_slug"]),
            observation_family=str(row["observation_family"]),
            indicator_code=str(row["indicator_code"]),
            row_count=int(row["row_count"]),
            min_year=_optional_int(row["min_year"]),
            max_year=_optional_int(row["max_year"]),
            country_count=int(row["country_count"]),
            missing_raw_locator_count=int(row["missing_raw_locator_count"] or 0),
        )
        for row in result
    )


def _source_statuses(
    rows: Sequence[ObservationCoverageRow],
    *,
    registry: SourceRegistry | None,
) -> tuple[SourceCoverageStatus, ...]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.source_slug] = counts.get(row.source_slug, 0) + row.row_count

    manual_flags: dict[str, bool] = {}
    if registry is not None:
        for descriptor in registry.list_descriptors():
            slug = descriptor.source_id.slug
            manual_flags[slug] = descriptor.requires_manual_approval
            counts.setdefault(slug, 0)

    statuses = []
    for slug in sorted(counts):
        row_count = counts[slug]
        requires_manual_approval = manual_flags.get(slug, False)
        if row_count > 0:
            status = "loaded"
        elif requires_manual_approval:
            status = "blocked_user_managed"
        else:
            status = "no_rows"
        statuses.append(
            SourceCoverageStatus(
                source_slug=slug,
                status=status,
                row_count=row_count,
                requires_manual_approval=requires_manual_approval,
            )
        )
    return tuple(statuses)


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return int(value)


def coverage_report_to_json(report: SourceCoverageReport) -> Mapping[str, object]:
    """Return a deterministic JSON-friendly report payload."""

    return {
        "rows": [row.__dict__ for row in report.rows],
        "source_statuses": [status.__dict__ for status in report.source_statuses],
    }


__all__ = [
    "ObservationCoverageRow",
    "SourceCoverageReport",
    "SourceCoverageStatus",
    "build_source_coverage_report",
    "coverage_report_to_json",
]
