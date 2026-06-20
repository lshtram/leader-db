"""Per-component helpers for the economic wellbeing scorer.

This module is the **internal** per-component logic of the
economic wellbeing deterministic scorer. The facade in
:mod:`leaders_db.score.economic_wellbeing` calls
:func:`bucket_observations_by_group` and
:func:`compute_group_components` to turn the bundle's
observations into a flat list of :class:`~leaders_db.score.results.ScoreComponent`
rows; the rationale and flag helpers live in
:mod:`leaders_db.score._economic_wellbeing_flags`.

It also owns the helpers that are shared between the score path
and the insufficient-data path:

- :func:`map_normalized_to_1_10` — the half-up rounding to the
  integer 1..10 scale (intentionally identical to the
  social-wellbeing / integrity / effectiveness scorer's mapping
  so cross-category comparisons stay on one scale);
- :func:`resolve_leader_name` — the bundle leader-name →
  country-name fallback;
- :func:`build_observation_ref` — the per-observation
  :class:`~leaders_db.score.results.ScoreObservationRef`;
- :func:`filter_excluded_observations` — the defence-in-depth
  client-source re-filter at the scorer boundary.

Style invariants (per ``docs/coding-guidelines.md``):

- ``from __future__ import annotations`` for forward-reference
  safety.
- Type hints on every public function and helper.
- No mutable defaults; no ``print()``, no ``TODO(debug)``, no scratch.
"""

from __future__ import annotations

import math
from collections.abc import Iterable

from ._economic_wellbeing_rubric import (
    _GROUP_BY_VARIABLE,
    _GROUP_WEIGHTS,
    CATEGORY_KEY,
)
from .evidence import CategoryEvidenceBundle, EvidenceObservation
from .results import ScoreComponent, ScoreObservationRef
from .source_plans import EXCLUDED_SOURCE_KEYS


def map_normalized_to_1_10(normalized: float) -> int:
    """Map a normalized 0..1 score onto the integer 1..10 scale.

    Half-up rounding with clamping:

    - 0.0 → 1 (the "least-bad" floor; the contract validates
      ``0..10`` so 1 is in range)
    - 1.0 → 10
    - any value below 0 (defence in depth) → 1
    - any value above 1 (defence in depth) → 10

    The mapping is restated in the result's ``rationale_short`` so
    a reviewer reading the manual-review queue row sees the scale
    explicitly. Intentionally identical to the social-wellbeing /
    integrity / effectiveness scorer's mapping so a reviewer can
    compare scores across the matrix without re-deriving
    per-category scaling.
    """
    if normalized <= 0.0:
        return 1
    if normalized >= 1.0:
        return 10
    score = math.floor(1.0 + 9.0 * normalized + 0.5)
    if score < 1:
        return 1
    if score > 10:
        return 10
    return score


def resolve_leader_name(bundle: CategoryEvidenceBundle) -> str:
    """Return the leader name to record on the result.

    The :class:`~leaders_db.score.results.ScoreResult` contract
    requires ``leader_name`` to be non-empty. The bundle's
    ``leader_name`` may be ``None`` when the Stage 4 resolver
    could not place a ruler; for the economic wellbeing rubric
    the leader identity is secondary to the country-year
    indicators, so we fall back to the country name in that case.
    """
    leader = bundle.leader_name
    if isinstance(leader, str) and leader.strip():
        return leader.strip()
    # Fall back to the country name (the rubric is country-year
    # anchored; a missing leader does not block the score).
    return bundle.country_name


def build_observation_ref(
    obs: EvidenceObservation, target_year: int
) -> ScoreObservationRef:
    """Build a :class:`ScoreObservationRef` for one observation.

    ``observation_year`` falls back to ``target_year`` for
    ``TemporalKind.NOT_AVAILABLE`` observations so the ref points
    at the bundle's target year.
    """
    obs_year = (
        target_year if obs.observation_year is None else obs.observation_year
    )
    return ScoreObservationRef(
        source_key=obs.source_key,
        variable_name=obs.variable_name,
        observation_year=obs_year,
        target_year=target_year,
    )


def filter_excluded_observations(
    observations: Iterable[EvidenceObservation],
) -> tuple[EvidenceObservation, ...]:
    """Strip observations whose source_key is in :data:`EXCLUDED_SOURCE_KEYS`.

    The bundle builder already filters client sources upstream;
    this helper is the scorer's defence-in-depth boundary. Returns
    a new tuple — the input is never mutated. Used by
    :func:`score_economic_wellbeing` as the **single** observation
    basis for the result: components, refs, contributions,
    missingness, review_flags, and human_review_required all
    derive from this filtered set so the client matrix can never
    influence any downstream artefact even if a contaminated
    bundle reaches the scorer.
    """
    return tuple(
        obs for obs in observations if obs.source_key not in EXCLUDED_SOURCE_KEYS
    )


def bucket_observations_by_group(
    observations: Iterable[EvidenceObservation],
) -> dict[str, list[EvidenceObservation]]:
    """Bucket each observation by its rubric group.

    Observations whose variable is not in the group map are
    skipped (defence in depth; the bundle builder scopes rows to
    the variable's owning source so this should not happen in
    production).
    """
    buckets: dict[str, list[EvidenceObservation]] = {
        key: [] for key in _GROUP_WEIGHTS
    }
    for obs in observations:
        group = _GROUP_BY_VARIABLE.get(obs.variable_name)
        if group is None:
            continue
        buckets[group].append(obs)
    return buckets


def compute_group_components(
    observations: list[EvidenceObservation],
    *,
    group_key: str,
    group_weight: float,
    target_year: int,
) -> tuple[float, list[ScoreComponent], list[ScoreObservationRef]]:
    """Compute one group's contribution, components, and refs.

    Returns ``(group_contribution, components, refs)``. The
    ``group_contribution`` is
    ``group_weight * mean(group_normalized)`` where
    ``group_normalized`` is the list of per-observation
    ``normalized_value`` (skips observations with
    ``normalized_value`` of ``None``). When the group has no
    usable observations, the contribution is 0.0 and the
    component/ref lists are empty.

    Each non-empty group emits one :class:`ScoreComponent` per
    observation with ``weight = group_weight / count_in_group``
    and ``contribution_0_1 = normalized_value * weight``. Sum of
    the group-level contributions equals the returned
    ``group_contribution`` within float tolerance; the per-
    component breakdown is the audit trail for reviewers.
    """
    valid = [obs for obs in observations if obs.normalized_value is not None]
    if not valid:
        return 0.0, [], []

    count = len(valid)
    per_obs_weight = group_weight / count
    group_average = sum(obs.normalized_value for obs in valid) / count
    group_contribution = group_weight * group_average

    components: list[ScoreComponent] = []
    refs: list[ScoreObservationRef] = []
    for obs in valid:
        ref = build_observation_ref(obs, target_year)
        component = ScoreComponent(
            component_key=f"{CATEGORY_KEY}__{group_key}",
            source_key=obs.source_key,
            variable_name=obs.variable_name,
            direction=obs.direction.value,
            raw_value=obs.numeric_value,
            normalized_value_0_1=obs.normalized_value,
            weight=per_obs_weight,
            contribution_0_1=obs.normalized_value * per_obs_weight,
            observation_refs=(ref,),
        )
        components.append(component)
        refs.append(ref)

    return group_contribution, components, refs


__all__ = [
    "bucket_observations_by_group",
    "build_observation_ref",
    "compute_group_components",
    "filter_excluded_observations",
    "map_normalized_to_1_10",
    "resolve_leader_name",
]
