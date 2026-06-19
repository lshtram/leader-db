"""Social wellbeing deterministic scorer (requirement §9, §6).

First per-category deterministic scorer per the AGENTS.md rule
"future scoring formulas must live in separate files per rating
category so each can be improved independently". One file per
category keeps each rubric auditable from a single location and
removes the temptation to drift weights or formula pieces
between categories.

This module exposes the public function
:func:`score_social_wellbeing`, which takes a
:class:`~leaders_db.score.evidence.CategoryEvidenceBundle` and
returns a :class:`~leaders_db.score.results.ScoreResult`. The
client 2023 matrix is **not** an input — the client score is
applied downstream (after this function returns) to populate
:attr:`ScoreResult.score_delta_vs_client`; see
:mod:`docs.architecture` §"Client matrix invariants" and AGENTS.md
always-on rule #6.

The scorer is deliberately a **transparent prototype rubric**,
not a politically or scientifically overclaimed composite. The
formula below is documented in full in this docstring so a
reviewer reading the manual-review queue row can audit the
rubric without re-deriving it from the code. The weights and
mapping are owned by this module; the underlying source plans
live in :mod:`leaders_db.score.category_plans.social_wellbeing`.

Module layout
-------------

The implementation is split across focused modules so each file
stays close to the 400-line convention
(``docs/coding-guidelines.md`` §"Modularity") and the formula
pieces are independently auditable. See the private sibling
modules ``_social_wellbeing_{rubric,components,flags}.py``
in this package for the per-piece details; the public import
path
``leaders_db.score.social_wellbeing.score_social_wellbeing`` is
preserved unchanged across the split, and the same name is
re-exported from :mod:`leaders_db.score` (the package root) so
production wiring is a single import.

Formula
-------

Five-group weighted-average rubric; group weights sum to 1.0.

================== =================================== ==================
Group              Variables                            Group weight
================== =================================== ==================
1. HDI composite   ``undp_hdi_hdi`` (REQUIRED)         0.40
2. Health signal   life expectancy + under-5           0.20
                   mortality (inverted) + immunization
3. Education       expected / mean years of            0.15
                   schooling + literacy + secondary
                   enrollment
4. Income / living ``undp_hdi_gni_per_capita``         0.15
5. Inequality /    ``wdi_gini_index`` (inverted) +     0.10
   social protection V-Dem egalitarian indicators
================== =================================== ==================

Per-observation mechanics
-------------------------

Within each group, every available :class:`EvidenceObservation`
contributes one :class:`ScoreComponent` with
``weight = group_weight / count_in_group`` and
``contribution_0_1 = normalized_value * weight``. Sum of the
group's contributions equals
``group_weight * mean(group_normalized)``. Sum across groups is
the normalized score in ``[0, 1]``. Observations whose
``normalized_value`` is ``None`` are skipped (the bundle treats
them as effectively missing; we never invent values).

Indicator-to-group mapping
--------------------------

Each plan variable is assigned to one group via the
:data:`_GROUP_BY_VARIABLE` table in
:mod:`leaders_db.score._social_wellbeing_rubric`. The Stage 5
bundle builder scopes each observation to the variable's owning
source (the ``source_key`` field on :class:`IndicatorSpec`), so
the scorer can trust the bundle to contain one observation per
(variable, year) — never a foreign variable from a non-owning
source. Stage 6 normalization handles ``LOWER_IS_BETTER``
direction inversion, so the scorer consumes a single 0..1 scale
where 1 is "best".

Score 1..10 mapping
-------------------

Customer scores are effectively 0..10 in the DB and docs, but
the user often speaks the rubric as 1..10. This scorer emits
integer **1..10** for non-insufficient results to match the
spoken convention. The mapping is half-up and clamped:

    system_proposed_score_1_10 = clamp(1, 10, floor(1 + 9 * normalized + 0.5))

A normalized score of 0.0 maps to 1 (the "least-bad" floor);
1.0 maps to 10. The :class:`ScoreResult` contract validates
``0..10`` (``ScoreResult.__post_init__``), so 1..10 is in range.
The mapping is restated in :attr:`ScoreResult.rationale_short`
so a reviewer reading the manual-review queue row sees the
scale explicitly.

Missingness handling
--------------------

- If the bundle falls below the plan's ``minimum_viable_sources``
  on **usable** observations (see
  :attr:`CategoryEvidenceBundle.has_minimum_viable_usable_evidence`)
  and the plan's :class:`SparseDataPolicy` is
  ``INSUFFICIENT_DATA``, the function returns an
  :attr:`ScoreResult.is_insufficient_data` result with both
  scores ``None`` and the :attr:`ReviewFlag.INSUFFICIENT_DATA`
  flag. This is the :class:`SOCIAL_WELLBEING_PLAN` setting — the
  plan does not accept a low-confidence provisional score for
  this category. Counting "usable" observations (not all
  observations) ensures that a source whose row arrived but
  whose ``normalized_value`` is ``None`` does not by itself
  satisfy the threshold.
- A missing REQUIRED (severity ``PRIMARY``) observation
  triggers :attr:`ReviewFlag.MISSING_PRIMARY_SOURCE` and
  ``human_review_required=True``. The scorer reads this from the
  bundle's :attr:`CategoryEvidenceBundle.primary_missing_observations`.
- Substantial missingness (less than half of plan indicators
  observed) triggers :attr:`ReviewFlag.SPARSE_DATA`.
- Any observation whose :class:`TemporalKind` is not ``DIRECT``
  (``PROXY`` or ``STALE``) reduces temporal fit and therefore
  the §11 confidence; the scorer flags this with
  :attr:`ReviewFlag.LOW_CONFIDENCE`.
- ``human_review_required`` is set ``True`` iff any of the
  above flags fires; the :class:`ScoreResult` forward-invariant
  in :meth:`ScoreResult.__post_init__` enforces consistency.

Observation refs
----------------

Every component carries a single :class:`ScoreObservationRef`
that points back at its underlying :class:`EvidenceObservation`
(source, variable, observation year, target year). The result's
flat :attr:`ScoreResult.observation_refs` mirrors the per-
component refs so the manual-review queue can audit a row
without re-walking the components.

Client score handling
---------------------

This scorer never consumes the client 2023 matrix as evidence.
As a defence-in-depth check, the function strips any
observations whose :attr:`EvidenceObservation.source_key` is
in :data:`leaders_db.score.source_plans.EXCLUDED_SOURCE_KEYS`
(``client_existing`` / ``client_matrix``) before bucketing.
The Stage 5 bundle builder already excludes those source keys
upstream, but the scorer boundary is the last line of defence in
case a contaminated bundle reaches the function. The filtered
``scoring_observations`` set is the **single** observation
basis for every downstream artefact — components, refs,
contributions, :attr:`ScoreResult.missingness` (including
``total_observed``), :attr:`ScoreResult.review_flags`, and
:attr:`ScoreResult.human_review_required`. A contaminated
client observation cannot inflate ``total_observed`` and
silently suppress :attr:`~leaders_db.score.results.ReviewFlag.SPARSE_DATA`.
The client score is validation-only and is applied **after**
the deterministic scoring to populate
:attr:`ScoreResult.score_delta_vs_client` — see the comparison
stage and AGENTS.md always-on rule #6.

Style invariants (per ``docs/coding-guidelines.md``):

- ``from __future__ import annotations`` for forward-reference
  safety.
- Type hints on every public function and helper.
- No mutable defaults; no ``print()``, no ``TODO(debug)``, no
  scratch code.
"""

from __future__ import annotations

import math
from collections.abc import Iterable

from ._social_wellbeing_components import (
    bucket_observations_by_group,
    compute_group_components,
    map_normalized_to_1_10,
    resolve_leader_name,
)
from ._social_wellbeing_flags import (
    build_missingness_summary,
    build_rationale,
    count_proxy_observations,
    detect_flags,
)
from ._social_wellbeing_rubric import _GROUP_WEIGHTS, CATEGORY_KEY
from .evidence import (
    CategoryEvidenceBundle,
    EvidenceObservation,
    SparseDataPolicy,
)
from .results import ReviewFlag, ScoreResult
from .source_plans import EXCLUDED_SOURCE_KEYS

# ---------------------------------------------------------------------------
# Public scorer
# ---------------------------------------------------------------------------


def score_social_wellbeing(
    bundle: CategoryEvidenceBundle,
) -> ScoreResult:
    """Return a :class:`ScoreResult` for the social-wellbeing category.

    The function is the deterministic entry point for one
    country-year. It does **not** consume the client 2023 matrix as
    evidence; ``score_delta_vs_client`` is left ``None`` and is
    populated downstream by the comparison stage.

    Parameters
    ----------
    bundle:
        The :class:`CategoryEvidenceBundle` for the
        country-year-category triple. The bundle's
        :attr:`source_plan` is expected to be
        :data:`SOCIAL_WELLBEING_PLAN` (the function does not
        assert this; it inspects the plan fields it needs).

    Returns
    -------
    ScoreResult
        The deterministic scoring result. The shape is the shared
        :class:`ScoreResult` contract — see
        :mod:`leaders_db.score.results` for the per-field
        documentation.

    Raises
    ------
    ValueError
        Re-raised from the :class:`ScoreResult` constructor when the
        computed payload violates the contract (e.g. an empty
        ``leader_name``). The function does not raise on missing
        data — missing data routes through the
        :attr:`ScoreResult.is_insufficient_data` /
        :attr:`ScoreResult.review_flags` channels instead.
    """
    plan = bundle.source_plan

    # ------------------------------------------------------------------
    # Defence-in-depth client exclusion at the scorer boundary.
    #
    # The Stage 5 bundle builder already filters out client sources
    # (``EXCLUDED_SOURCE_KEYS``), so the production bundle cannot
    # carry them. We re-filter here as the last line of defence in
    # case a contaminated bundle is hand-built in a test or piped
    # from a future stage that forgets the upstream rule. We never
    # raise on a contaminated bundle — silently skipping client
    # observations is the review-safe behavior (the reviewer sees
    # the rest of the result and can audit the contamination
    # upstream). See AGENTS.md always-on rule #6 and
    # ``docs/architecture.md`` §"Client matrix invariants".
    # ------------------------------------------------------------------
    scoring_observations = _filter_excluded_observations(
        bundle.observations
    )

    # ------------------------------------------------------------------
    # Insufficient-data gate: distinct sources of **usable**
    # observations (normalized_value not None) below the plan's
    # threshold AND the plan's policy is INSUFFICIENT_DATA.
    # SOCIAL_WELLBEING_PLAN uses INSUFFICIENT_DATA, so the gate is
    # "always on" when the bundle is below the threshold. Counting
    # usable observations (not all observations) ensures that a
    # source whose row arrived but whose ``normalized_value`` is
    # ``None`` does not by itself satisfy the threshold.
    # ------------------------------------------------------------------
    if (
        not bundle.has_minimum_viable_usable_evidence
        and plan.sparse_data_policy is SparseDataPolicy.INSUFFICIENT_DATA
    ):
        flags = [
            ReviewFlag.INSUFFICIENT_DATA,
            ReviewFlag.SPARSE_DATA,
        ]
        proxy_count = count_proxy_observations(scoring_observations)
        # Use the filtered ``scoring_observations`` (client sources
        # excluded) so a contaminated bundle cannot inflate
        # ``missingness.total_observed`` and silently downgrade the
        # payload's SPARSE_DATA flag.
        missingness = build_missingness_summary(
            bundle, scoring_observations
        )
        rationale = build_rationale(
            bundle=bundle,
            normalized=0.0,
            score_1_10=1,  # placeholder for the rationale text only
            components=(),
            missingness=missingness,
            flags=flags,
            proxy_count=proxy_count,
        )
        return ScoreResult(
            category_key=CATEGORY_KEY,
            iso3=bundle.country_iso3,
            year=bundle.year,
            leader_name=resolve_leader_name(bundle),
            normalized_score_0_1=None,
            system_proposed_score_1_10=None,
            components=(),
            observation_refs=(),
            missingness=missingness,
            rationale_short=rationale,
            human_review_required=True,
            review_flags=tuple(flags),
            is_insufficient_data=True,
            score_delta_vs_client=None,
        )

    # ------------------------------------------------------------------
    # Score path: bucket observations into groups and compute each
    # group's contribution. Sum across groups is the normalized score
    # in [0, 1].
    # ------------------------------------------------------------------
    buckets = bucket_observations_by_group(scoring_observations)
    all_components: list = []
    all_refs: list = []
    group_contributions: list[float] = []
    for group_key, weight in _GROUP_WEIGHTS.items():
        contribution, components, refs = compute_group_components(
            buckets[group_key],
            group_key=group_key,
            group_weight=weight,
            target_year=bundle.year,
        )
        group_contributions.append(contribution)
        all_components.extend(components)
        all_refs.extend(refs)

    normalized = math.fsum(group_contributions)
    # Clamp to [0, 1] in case of arithmetic drift.
    if normalized < 0.0:
        normalized = 0.0
    elif normalized > 1.0:
        normalized = 1.0

    score_1_10 = map_normalized_to_1_10(normalized)
    # Use the filtered ``scoring_observations`` (client sources
    # excluded) so a contaminated bundle cannot inflate
    # ``missingness.total_observed`` and silently suppress the
    # SPARSE_DATA flag (the gate the manual-review queue sorts on).
    missingness = build_missingness_summary(
        bundle, scoring_observations
    )
    flags = detect_flags(
        bundle,
        observations=list(scoring_observations),
        missingness=missingness,
    )
    proxy_count = count_proxy_observations(scoring_observations)
    rationale = build_rationale(
        bundle=bundle,
        normalized=normalized,
        score_1_10=score_1_10,
        components=all_components,
        missingness=missingness,
        flags=flags,
        proxy_count=proxy_count,
    )

    # The forward invariant: any review signal implies
    # human_review_required=True. The ScoreResult contract enforces
    # this; we set it explicitly here so the call site is obvious.
    human_review_required = bool(flags)

    return ScoreResult(
        category_key=CATEGORY_KEY,
        iso3=bundle.country_iso3,
        year=bundle.year,
        leader_name=resolve_leader_name(bundle),
        normalized_score_0_1=normalized,
        system_proposed_score_1_10=score_1_10,
        components=tuple(all_components),
        observation_refs=tuple(all_refs),
        missingness=missingness,
        rationale_short=rationale,
        human_review_required=human_review_required,
        review_flags=tuple(flags),
        is_provisional=False,
        is_insufficient_data=False,
        score_delta_vs_client=None,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _filter_excluded_observations(
    observations: Iterable[EvidenceObservation],
) -> tuple[EvidenceObservation, ...]:
    """Strip observations whose source_key is in :data:`EXCLUDED_SOURCE_KEYS`.

    The bundle builder already filters client sources upstream; this
    helper is the scorer's defence-in-depth boundary. Returns a new
    tuple — the input is never mutated. Used by
    :func:`score_social_wellbeing` as the **single** observation
    basis for the result: components, refs, contributions,
    :attr:`ScoreResult.missingness`, :attr:`ScoreResult.review_flags`,
    and :attr:`ScoreResult.human_review_required` all derive from
    this filtered set so the client matrix can never influence any
    downstream artefact even if a contaminated bundle reaches the
    scorer.
    """
    return tuple(
        obs for obs in observations if obs.source_key not in EXCLUDED_SOURCE_KEYS
    )


__all__ = [
    "CATEGORY_KEY",
    "score_social_wellbeing",
]
