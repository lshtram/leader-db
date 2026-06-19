"""Shared test factories for the Stage 5 evidence bundle contract.

These factories are intentionally not :func:`pytest.fixture` s — they
take keyword arguments and return a constructed instance, so the
test body reads naturally:

    plan = make_plan(minimum_viable_sources=3)
    bundle = make_bundle(observations=[obs], plan=plan)

The contract tests (``test_score_evidence_contract.py``) and the
validation tests (``test_score_evidence_validation.py``) both depend
on these factories. The leading underscore in the module name keeps
pytest from collecting it as a test file.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from leaders_db.score.evidence import (
    CategoryEvidenceBundle,
    CategorySourcePlan,
    Direction,
    EvidenceObservation,
    IndicatorRole,
    IndicatorSpec,
    MissingObservation,
    MissingReason,
    MissingSeverity,
    SparseDataPolicy,
    TemporalKind,
)

_DEFAULT_INDICATORS: tuple[IndicatorSpec, ...] = (
    IndicatorSpec(
        variable_name="v2x_polyarchy",
        role=IndicatorRole.REQUIRED,
        direction=Direction.HIGHER_IS_BETTER,
    ),
    IndicatorSpec(
        variable_name="wgi_control_of_corruption",
        role=IndicatorRole.REQUIRED,
        direction=Direction.HIGHER_IS_BETTER,
    ),
)


def make_plan(
    *,
    category_key: str = "political_freedom",
    expected_sources: Sequence[str] | None = None,
    expected_indicators: Sequence[IndicatorSpec] | None = None,
    minimum_viable_sources: int = 2,
    preferred_direct_year: int = 2023,
    allowed_proxy_years: Sequence[int] | None = None,
    default_source_weights: Sequence[tuple[str, float]] | None = None,
    sparse_data_policy: SparseDataPolicy = SparseDataPolicy.INSUFFICIENT_DATA,
) -> CategorySourcePlan:
    """Construct a :class:`CategorySourcePlan` with sensible defaults."""
    return CategorySourcePlan(
        category_key=category_key,
        expected_sources=(
            expected_sources if expected_sources is not None else ("vdem", "wgi")
        ),
        expected_indicators=(
            expected_indicators
            if expected_indicators is not None
            else _DEFAULT_INDICATORS
        ),
        minimum_viable_sources=minimum_viable_sources,
        preferred_direct_year=preferred_direct_year,
        allowed_proxy_years=(
            allowed_proxy_years if allowed_proxy_years is not None else (1,)
        ),
        default_source_weights=(
            default_source_weights if default_source_weights is not None else ()
        ),
        sparse_data_policy=sparse_data_policy,
    )


def make_observation(
    *,
    source_key: str = "vdem",
    source_name: str = "V-Dem v16",
    variable_name: str = "v2x_polyarchy",
    raw_value: str | None = "0.45",
    numeric_value: float | None = 0.45,
    normalized_value: float | None = 0.45,
    unit: str | None = "index",
    direction: Direction = Direction.HIGHER_IS_BETTER,
    observation_year: int | None = 2023,
    target_year: int = 2023,
    temporal_kind: TemporalKind = TemporalKind.DIRECT,
    source_row_reference: str | None = (
        "country_text_id=MEX;year=2023;col=v2x_polyarchy"
    ),
    authority_score: int = 90,
    specificity_score: int = 90,
    notes: str | None = None,
) -> EvidenceObservation:
    """Construct an :class:`EvidenceObservation` with sensible defaults."""
    return EvidenceObservation(
        source_key=source_key,
        source_name=source_name,
        variable_name=variable_name,
        raw_value=raw_value,
        numeric_value=numeric_value,
        normalized_value=normalized_value,
        unit=unit,
        direction=direction,
        observation_year=observation_year,
        target_year=target_year,
        temporal_kind=temporal_kind,
        source_row_reference=source_row_reference,
        authority_score=authority_score,
        specificity_score=specificity_score,
        notes=notes,
    )


def make_missing(
    *,
    source_key: str = "ti_cpi",
    variable_name: str = "cpi_score",
    reason: MissingReason = MissingReason.SOURCE_NOT_IMPLEMENTED,
    severity: MissingSeverity = MissingSeverity.PRIMARY,
) -> MissingObservation:
    """Construct a :class:`MissingObservation` with sensible defaults."""
    return MissingObservation(
        source_key=source_key,
        variable_name=variable_name,
        reason=reason,
        severity=severity,
    )


def make_bundle(
    *,
    observations: Sequence[EvidenceObservation] | None = None,
    missing: Sequence[MissingObservation] | None = None,
    plan: CategorySourcePlan | None = None,
    category_metadata: Mapping[str, str] | None = None,
) -> CategoryEvidenceBundle:
    """Construct a :class:`CategoryEvidenceBundle` with sensible defaults."""
    plan = plan or make_plan()
    return CategoryEvidenceBundle(
        country_iso3="MEX",
        country_name="Mexico",
        leader_name="Andrés Manuel López Obrador",
        year=2023,
        category_key=plan.category_key,
        source_plan=plan,
        observations=observations if observations is not None else (),
        missing=missing if missing is not None else (),
        category_metadata=category_metadata,
    )


__all__ = [
    "make_bundle",
    "make_missing",
    "make_observation",
    "make_plan",
]
