"""Per-component helpers for the nuclear scorer.

This module is the **internal** per-component logic of the
``nuclear`` deterministic scorer. The facade in
:mod:`leaders_db.score.nuclear` calls
:func:`bucket_observations_by_group` and
:func:`compute_group_components` to turn the bundle's
observations into a flat list of
:class:`~leaders_db.score.results.ScoreComponent` rows; the
rationale and flag helpers live in
:mod:`leaders_db.score._nuclear_flags`.

It also owns the helpers that are shared between the score path
and the insufficient-data path:

- :func:`map_normalized_to_1_10` — the half-up rounding to the
  integer 1..10 scale (intentionally identical to the
  social-wellbeing / integrity / effectiveness / economic
  wellbeing / political-freedom / domestic-violence /
  international-peace scorer's mapping so cross-category
  comparisons stay on one scale);
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

from ._nuclear_rubric import (
    _GROUP_BY_VARIABLE,
    _GROUP_WEIGHTS,
    _OWNING_SOURCE_BY_VARIABLE,
    CATEGORY_KEY,
)
from .evidence import CategoryEvidenceBundle, EvidenceObservation
from .evidence_plan import CategorySourcePlan
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

    The mapping is restated in the result's ``rationale_short``
    so a reviewer reading the manual-review queue row sees the
    scale explicitly. Intentionally identical to the
    social-wellbeing / integrity / effectiveness / economic
    wellbeing / political-freedom / domestic-violence /
    international-peace scorer's mapping so a reviewer can
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
    could not place a ruler; for the nuclear rubric the leader
    identity is secondary to the country-year indicators (the
    9 nuclear-armed states each have a single identified ruler
    for the year, but the scorer treats leader identity as
    secondary to the country-year nuclear-arsenal signal), so
    we fall back to the country name in that case.
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
    this helper is the scorer's defence-in-depth boundary.
    Returns a new tuple — the input is never mutated. Used by
    :func:`score_nuclear` as the **single** observation basis
    for the result: components, refs, contributions, missingness,
    review_flags, and ``human_review_required`` all derive from
    this filtered set so the client matrix can never influence
    any downstream artefact even if a contaminated bundle
    reaches the scorer. See AGENTS.md always-on rule #6.

    Note: this is the **client-only** filter. The stricter
    scoring-basis filter that also enforces
    ``(variable_name, source_key)`` ownership lives in
    :func:`filter_scoring_basis` — that is what
    :func:`leaders_db.score.nuclear.score_nuclear` actually calls
    (this lighter helper is kept for the missingness rollup paths
    in :mod:`leaders_db.score._nuclear_flags`).
    """
    return tuple(
        obs for obs in observations if obs.source_key not in EXCLUDED_SOURCE_KEYS
    )


def filter_scoring_basis(
    observations: Iterable[EvidenceObservation],
    plan: CategorySourcePlan,
) -> tuple[EvidenceObservation, ...]:
    """Return the **scoring basis** for the nuclear scorer.

    This is the defence-in-depth scoring-basis filter that closes
    the reviewer blocker: the nuclear scorer's viable-data gate,
    per-component bookkeeping, observation refs, normalized score,
    flag derivation, :attr:`ReviewFlag.NUCLEAR_CASE` detection,
    and rationale **all** consume this single filtered set, so a
    non-FAS / non-SIPRI observation cannot influence any
    downstream artefact even if a hand-built or otherwise
    contaminated bundle reaches the scorer.

    The filter applies three rules in turn:

    1. **Client-source strip** — drop observations whose
       ``source_key`` is in :data:`EXCLUDED_SOURCE_KEYS`
       (``client_existing`` / ``client_matrix``). The bundle
       builder already filters client sources upstream; this is
       the scorer's boundary against a hand-built bundle that
       forgets the upstream rule. See AGENTS.md always-on rule #6.
    2. **Nuclear-variable strip** — drop observations whose
       ``variable_name`` is not in the rubric's
       :data:`_OWNING_SOURCE_BY_VARIABLE` map. Non-nuclear
       variables (e.g. ``vdem_v2x_polyarchy``,
       ``wgi_control_of_corruption``) must never reach the
       nuclear scoring basis regardless of their source.
    3. **Owning-source strip** — drop observations whose
       ``source_key`` does not equal the rubric-declared owning
       source for that variable (e.g. ``source_key="wgi"`` with
       ``variable_name="fas_total_inventory"``). This is the
       ownership gate the per-category ownership rule from
       :mod:`leaders_db.score.source_plans` §"Per-indicator
       ownership" requires: a wrong-source row carrying an
       expected nuclear variable must be silently dropped so it
       cannot inflate the missingness summary, contribute a
       component, or invent a numeric score.

    Non-FAS / non-SIPRI observations are ignored — they are not
    "evidence" for the nuclear category. When no valid
    nuclear-source evidence remains, the bundle routes to the
    insufficient-data path (``is_insufficient_data=True`` with
    both scores ``None`` and the "non-nuclear / no
    nuclear-source evidence" rationale) per requirement §6
    ("most countries are non-nuclear") and the
    reviewer-blocker no-invented-score invariant.

    The helper also rejects rows whose ``variable_name`` IS in
    the ownership map but whose ``source_key`` is something else
    (e.g. an observation carrying the nuclear variable name but
    attributed to a wrong source). The bundle builder scopes
    every lookup to the owning source upstream, so this should
    not happen in production; the strict ownership check is
    defence-in-depth for hand-built bundles.

    Returns a fresh tuple — the input is never mutated.
    """
    del plan  # The rubric constant is the authoritative ownership
    # map; ``plan`` is accepted for symmetry with the bundle's
    # other scoring helpers so the signature is the right shape
    # for a future per-plan ownership override. Kept explicit so
    # ``ruff`` does not flag the unused parameter under future
    # configuration.
    return tuple(
        obs
        for obs in observations
        if obs.source_key not in EXCLUDED_SOURCE_KEYS
        and _OWNING_SOURCE_BY_VARIABLE.get(obs.variable_name)
        == obs.source_key
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


def has_nuclear_source_evidence(
    observations: Iterable[EvidenceObservation],
) -> bool:
    """Return ``True`` iff any observation is a FAS or SIPRI Yearbook Ch.7 row.

    Used by the facade to decide whether the
    :attr:`ReviewFlag.NUCLEAR_CASE` population-split flag fires
    on the scored path and to choose the "no nuclear-source
    evidence found (non-nuclear state)" vs. "nuclear-source
    evidence was present but insufficient" rationale wording on
    the insufficient-data path. The function deliberately
    ignores non-nuclear-source observations (e.g. a contaminated
    ``client_existing`` row that somehow leaked past the
    upstream filter) so the population split reflects the real
    evidence base, not contamination. Returns ``False`` for an
    empty input.
    """
    return any(
        obs.source_key in {"fas", "sipri_yearbook_ch7"}
        for obs in observations
    )


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
    "filter_scoring_basis",
    "has_nuclear_source_evidence",
    "map_normalized_to_1_10",
    "resolve_leader_name",
]
