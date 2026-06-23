"""Per-indicator collection helpers for the Stage 5 evidence-bundle builder.

Stage 5 produces a :class:`~leaders_db.score.evidence.CategoryEvidenceBundle`
per (country, year, category) tuple. For each expected indicator in
the category plan the orchestrator must:

1. Resolve the **owning** canonical source key (per
   :class:`~leaders_db.score.evidence_types.IndicatorSpec.source_key`,
   with a plan-level fallback for ad-hoc test plans).
2. Query ``source_observations`` joined to ``sources`` **scoped to that
   single owning source** so a wrong-source row (e.g. a WGI row
   carrying ``vdem_v2x_corr``) is silently dropped and the variable is
   reported missing with
   :attr:`~leaders_db.score.evidence.MissingReason.TARGET_YEAR_ABSENT`.
3. Classify the missingness reason
   (:attr:`~leaders_db.score.evidence.MissingReason.SOURCE_NOT_IMPLEMENTED`
   when the owning source is not registered,
   :attr:`~leaders_db.score.evidence.MissingReason.TARGET_YEAR_ABSENT`
   when it is registered but has no eligible row).
4. Convert the best-fit row (selected by
   :func:`leaders_db.resolve.indicators_selection.select_best_row`)
   into an :class:`~leaders_db.score.evidence.EvidenceObservation` with
   the per-observation authority / specificity defaults declared in
   :mod:`leaders_db.score.source_plans`.

The owning source key flows through to
:attr:`~leaders_db.score.evidence.MissingObservation.source_key` so
the manual-review queue and audit trail point at the source that
should have produced the row.

Style invariants (per ``docs/process/coding-guidelines.md``):

- ``from __future__ import annotations`` for forward-reference safety.
- Type hints on every public function parameter and return.
- No mutable defaults.
- No ``print()``, no ``TODO(debug)``, no scratch code.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Country, Source, SourceObservation
from ..score.evidence import (
    Direction,
    EvidenceObservation,
    MissingObservation,
    MissingReason,
)
from ..score.source_plans import (
    DEFAULT_AUTHORITY_SCORE,
    DEFAULT_SPECIFICITY_SCORE,
    CategorySourcePlan,
    IndicatorSpec,
    canonical_source_key,
)
from .indicators_selection import (
    coerce_float,
    coerce_numeric,
    select_best_row,
    severity_for_indicator,
    temporal_kind_for,
)

__all__ = [
    "collect_indicator_observations",
]


# ---------------------------------------------------------------------------
# Owning-source resolution
# ---------------------------------------------------------------------------


def _resolve_owning_source_key(
    spec: IndicatorSpec, plan: CategorySourcePlan
) -> str:
    """Return the owning canonical source key for ``spec``.

    Production plans declare :attr:`IndicatorSpec.source_key` on
    every spec; the function falls back to the plan's first
    ``expected_sources`` entry when ``spec.source_key`` is
    ``None`` (the only path that hits the fallback today is the
    Stage 5 contract tests under ``tests/_score_evidence_factories``,
    which construct ad-hoc plans without an owning-source rule).

    Raises :class:`ValueError` when neither the spec nor the plan
    declares an owning source: that would mean the indicator has
    nowhere to look, so the production builder must fail loudly
    instead of silently inventing a source key.
    """
    if spec.source_key:
        return spec.source_key
    if plan.expected_sources:
        return plan.expected_sources[0]
    raise ValueError(
        f"Cannot resolve owning source for indicator {spec.variable_name!r}: "
        "IndicatorSpec.source_key is unset and the plan has no "
        "expected_sources to fall back on."
    )


# ---------------------------------------------------------------------------
# Per-indicator collection
# ---------------------------------------------------------------------------


def collect_indicator_observations(
    session: Session,
    *,
    country: Country,
    target_year: int,
    spec: IndicatorSpec,
    plan: CategorySourcePlan,
    expected_source_ids: dict[str, int],
    observations: list[EvidenceObservation],
    missing: list[MissingObservation],
) -> None:
    """Populate ``observations`` / ``missing`` for one expected indicator.

    The owning source is resolved from ``spec.source_key`` (with
    a plan-level fallback for ad-hoc test plans). The query is
    then scoped to **that single source** so a wrong-source row is
    silently ignored.

    Missingness is reported with two distinct reasons:

    - :attr:`MissingReason.SOURCE_NOT_IMPLEMENTED` when the
      owning source key is not registered in the ``sources`` table
      at all (the plan's expected_sources are matched but the
      owning key is absent).
    - :attr:`MissingReason.TARGET_YEAR_ABSENT` when the owning
      source is registered but has no eligible row (no row at
      all, no row for ``target_year``, or every row is outside the
      ``allowed_proxy_years`` budget).

    In both cases the :attr:`MissingObservation.source_key` is the
    owning source key (never a "primary expected source" fallback)
    so the manual-review queue and audit trail point at the source
    that should have produced the row.
    """
    owning_source_key = _resolve_owning_source_key(spec, plan)
    severity = severity_for_indicator(spec, plan)

    owning_source_id = expected_source_ids.get(owning_source_key)
    if owning_source_id is None:
        # The owning source is in the plan's expected set but is
        # not registered in the DB. The owning source key flows
        # through to the MissingObservation so the audit trail
        # names the exact source that is missing (NOT a generic
        # "primary" source).
        missing.append(
            MissingObservation(
                source_key=owning_source_key,
                variable_name=spec.variable_name,
                reason=MissingReason.SOURCE_NOT_IMPLEMENTED,
                severity=severity,
            )
        )
        return

    rows = session.execute(
        select(SourceObservation, Source)
        .join(Source, Source.id == SourceObservation.source_id)
        .where(
            SourceObservation.country_id == country.id,
            SourceObservation.variable_name == spec.variable_name,
            SourceObservation.source_id == owning_source_id,
        )
        .order_by(SourceObservation.id)
    ).all()

    if not rows:
        missing.append(
            MissingObservation(
                source_key=owning_source_key,
                variable_name=spec.variable_name,
                reason=MissingReason.TARGET_YEAR_ABSENT,
                severity=severity,
            )
        )
        return

    best = select_best_row(rows, target_year, plan)
    if best is None:
        # Rows exist for the variable but every one is outside the
        # allowed proxy budget — treat as missing (task spec:
        # "missing is acceptable for this stage"; STALE selection
        # is deferred to a later stage).
        missing.append(
            MissingObservation(
                source_key=owning_source_key,
                variable_name=spec.variable_name,
                reason=MissingReason.TARGET_YEAR_ABSENT,
                severity=severity,
            )
        )
        return

    obs_row, source_row = best
    direction = plan.direction_of(spec.variable_name) or Direction.HIGHER_IS_BETTER
    source_key = canonical_source_key(source_row.source_name) or owning_source_key
    observations.append(
        EvidenceObservation(
            source_key=source_key,
            source_name=source_row.source_name or source_key,
            variable_name=spec.variable_name,
            raw_value=obs_row.raw_value,
            numeric_value=coerce_numeric(
                obs_row.normalized_value, obs_row.raw_value
            ),
            normalized_value=coerce_float(obs_row.normalized_value),
            unit=obs_row.unit,
            direction=direction,
            observation_year=obs_row.year,
            target_year=target_year,
            temporal_kind=temporal_kind_for(obs_row.year, target_year, plan),
            source_row_reference=obs_row.source_row_reference,
            authority_score=DEFAULT_AUTHORITY_SCORE,
            specificity_score=DEFAULT_SPECIFICITY_SCORE,
        )
    )
