"""International peace vs aggression and war deterministic scorer
(requirement §9, §6).

Seventh per-category deterministic scorer. The rubric is a
transparent 2-group split (UCDP state-based + internationalized
conflict / SIPRI Military Expenditure). The
``minimum_viable_sources=2`` setting plus the
``SparseDataPolicy.INSUFFICIENT_DATA`` policy mirrors the
political-freedom / domestic-violence scorer's contract
end-to-end:

- :mod:`leaders_db.score.international_peace` (this file) — the
  public :func:`score_international_peace` facade and the
  formula / missingness / client-handling docstring.
- :mod:`leaders_db.score._international_peace_rubric` — group
  weights, variable-to-group map, sparse threshold (the rubric
  constants).
- :mod:`leaders_db.score._international_peace_components` —
  per-group component/ref computation, the 1..10 scale mapping,
  the leader-name fallback, the per-observation ref builder,
  and the client-source re-filter.
- :mod:`leaders_db.score._international_peace_flags` — the
  :class:`MissingnessSummary` builder, the proxy-count helper,
  the :class:`ReviewFlag` detector, and the rationale composer.

The split is documented at the module level so the next reviewer
can audit the rubric without re-walking the code; the public
import path
``leaders_db.score.international_peace.score_international_peace``
is stable.

This module exposes :func:`score_international_peace`, which
takes a :class:`~leaders_db.score.evidence.CategoryEvidenceBundle`
and returns a :class:`~leaders_db.score.results.ScoreResult`. The
client 2023 matrix is **not** an input — the client score is
applied downstream (after this function returns) to populate
:attr:`ScoreResult.score_delta_vs_client`; see
:mod:`docs.architecture` §"Client matrix invariants" and AGENTS.md
always-on rule #6.

The scorer is deliberately a **transparent prototype rubric**,
not a politically or scientifically overclaimed composite. The
weights and mapping are owned by this module; the underlying
source plans live in
:mod:`leaders_db.score.category_plans.international_peace`.

Formula
-------

Two-group weighted-average rubric; group weights sum to 1.0.
The 0.65 / 0.35 split reflects the strength of the direct
international-conflict signal each source carries: UCDP's
4-indicator state-based + internationalized events / fatalities
family is the direct event-based methodology (the strongest
direct signal of "international aggression / war"); SIPRI
Military Expenditure is the expenditure-based cross-validator
(4 share / scale indicators).

================== =================================================== ==================
Group              Variables                                           Group weight
================== =================================================== ==================
1. UCDP conflict   ``ucdp_state_based_events`` (PREFERRED),            0.65
   involvement     ``ucdp_state_based_fatalities`` (REQUIRED),
   group           ``ucdp_intl_events`` (PREFERRED),
                   ``ucdp_intl_fatalities`` (PREFERRED) — simple
                   mean of available UCDP state-based and
                   internationalized conflict indicators
2. SIPRI Military  ``sipri_milex_share_of_gdp`` (PREFERRED),          0.35
   Expenditure     ``sipri_milex_per_capita`` (FALLBACK),
   group           ``sipri_milex_constant_usd`` (FALLBACK),
                   ``sipri_milex_share_of_govt_spending``
                   (FALLBACK) — simple mean of available
                   SIPRI military-expenditure indicators
================== =================================================== ==================

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
them as effectively missing; we never invent values). Stage 6
normalization handles ``LOWER_IS_BETTER`` direction inversion
for all 8 indicators (all are LOWER_IS_BETTER in raw form:
more conflict / more military spending = worse peace signal)
so the scorer consumes a single 0..1 scale where 1 is "best"
(i.e. more peace / less military burden).

Score 1..10 mapping
-------------------

The prototype rubric speaks the customer scale as integer 1..10
even though the DB and the docs use 0..10. The mapping is
half-up and clamped:

    system_proposed_score_1_10 = clamp(1, 10, floor(1 + 9 * normalized + 0.5))

A normalized score of 0.0 maps to 1 (the "least-bad" floor);
1.0 maps to 10. The mapping is intentionally identical to the
social-wellbeing / integrity / effectiveness / economic
wellbeing / political-freedom / domestic-violence scorer's
mapping so a reviewer can compare scores across the matrix
without re-deriving per-category scaling.

Missingness handling
--------------------

- If the bundle falls below the plan's ``minimum_viable_sources``
  on **usable** observations (see
  :attr:`CategoryEvidenceBundle.has_minimum_viable_usable_evidence`)
  and the plan's :class:`SparseDataPolicy` is
  ``INSUFFICIENT_DATA``, the function returns an
  :attr:`ScoreResult.is_insufficient_data` result with both
  scores ``None`` and the :attr:`ReviewFlag.INSUFFICIENT_DATA`
  flag **plus** the same :attr:`ReviewFlag.MISSING_PRIMARY_SOURCE`
  / :attr:`ReviewFlag.SPARSE_DATA` /
  :attr:`ReviewFlag.LOW_CONFIDENCE` flags the score path
  derives (via
  :func:`leaders_db.score._international_peace_flags.detect_flags`).
  This is the :class:`INTERNATIONAL_PEACE_PLAN` setting.
- A missing REQUIRED (severity ``PRIMARY``) observation
  triggers :attr:`ReviewFlag.MISSING_PRIMARY_SOURCE` (only for
  non-client ``MissingObservation`` rows — the client 2023
  matrix is validation reference, never evidence).
- Substantial missingness (less than half of plan indicators
  observed) triggers :attr:`ReviewFlag.SPARSE_DATA`.
- Any observation whose :class:`TemporalKind` is not ``DIRECT``
  (``PROXY`` or ``STALE``) triggers
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
component refs.

Client score handling
---------------------

This scorer never consumes the client 2023 matrix as evidence.
The function strips any observations whose
:attr:`EvidenceObservation.source_key` is in
:data:`leaders_db.score.source_plans.EXCLUDED_SOURCE_KEYS`
(``client_existing`` / ``client_matrix``) before bucketing. The
Stage 5 bundle builder already excludes those source keys
upstream; this re-filter is the scorer's defence-in-depth
boundary. The filtered ``scoring_observations`` set is the
**single** observation basis for every downstream artefact —
components, refs, contributions, missingness, review_flags, and
human_review_required — so a contaminated client observation
cannot influence any artefact even if a contaminated bundle
reaches the scorer. See AGENTS.md always-on rule #6.

Style invariants (per ``docs/process/coding-guidelines.md``):

- ``from __future__ import annotations`` for forward-reference
  safety.
- Type hints on every public function parameter and return.
- No mutable defaults; no ``print()``, no ``TODO(debug)``, no
  scratch code.
"""

from __future__ import annotations

import math

from ._international_peace_components import (
    bucket_observations_by_group,
    compute_group_components,
    filter_excluded_observations,
    map_normalized_to_1_10,
    resolve_leader_name,
)
from ._international_peace_flags import (
    build_missingness_summary,
    build_rationale,
    count_proxy_observations,
    detect_flags,
)
from ._international_peace_rubric import _GROUP_WEIGHTS, CATEGORY_KEY
from .evidence import CategoryEvidenceBundle, SparseDataPolicy
from .results import ReviewFlag, ScoreResult

__all__ = ["CATEGORY_KEY", "score_international_peace"]


def score_international_peace(bundle: CategoryEvidenceBundle) -> ScoreResult:
    """Return a :class:`ScoreResult` for the international-peace category.

    The function is the deterministic entry point for one
    country-year. It does **not** consume the client 2023 matrix
    as evidence; ``score_delta_vs_client`` is left ``None`` and
    is populated downstream by the comparison stage.

    Parameters
    ----------
    bundle:
        The :class:`CategoryEvidenceBundle` for the
        country-year-category triple. The bundle's
        :attr:`source_plan` is expected to be
        :data:`INTERNATIONAL_PEACE_PLAN` (the function does not
        assert this; it inspects the plan fields it needs).

    Returns
    -------
    ScoreResult
        The deterministic scoring result. The shape is the shared
        :class:`ScoreResult` contract documented in
        :mod:`leaders_db.score.results`.

    Raises
    ------
    ValueError
        Re-raised from the :class:`ScoreResult` constructor when
        the computed payload violates the contract (e.g. an empty
        ``leader_name``). The function does not raise on missing
        data — missing data routes through the
        :attr:`ScoreResult.is_insufficient_data` /
        :attr:`ScoreResult.review_flags` channels instead.
    """
    plan = bundle.source_plan

    # Defence-in-depth client exclusion at the scorer boundary. The
    # Stage 5 bundle builder already filters out client sources
    # (``EXCLUDED_SOURCE_KEYS``); we re-filter here so a contaminated
    # bundle (hand-built or piped from a future stage that forgets
    # the upstream rule) cannot influence any downstream artefact.
    # See AGENTS.md always-on rule #6 and ``docs/architecture/overview.md``
    # §"Client matrix invariants".
    scoring_observations = filter_excluded_observations(bundle.observations)

    # Insufficient-data gate: distinct sources of **usable**
    # observations (normalized_value not None) below the plan's
    # threshold AND the plan's policy is INSUFFICIENT_DATA. The
    # INTERNATIONAL_PEACE_PLAN uses INSUFFICIENT_DATA so the gate is
    # "always on" when the bundle is below the threshold.
    #
    # The flag set here is the **same** set the score path would
    # derive via :func:`detect_flags` (MISSING_PRIMARY_SOURCE from
    # non-client PRIMARY missing rows, SPARSE_DATA from a
    # sub-threshold observed ratio, LOW_CONFIDENCE from any
    # PROXY/STALE observation), plus :attr:`ReviewFlag.INSUFFICIENT_DATA`
    # prepended so the manual-review queue can distinguish
    # "insufficient data, no score emitted" from the scored-path
    # flag set. The client-source filter is applied inside
    # :func:`detect_flags` (see :func:`_filter_excluded_missing`)
    # so a contaminated bundle carrying ``client_existing`` /
    # ``client_matrix`` PRIMARY missing rows cannot trigger
    # MISSING_PRIMARY_SOURCE through this branch either. See
    # AGENTS.md always-on rule #6.
    if (
        not bundle.has_minimum_viable_usable_evidence
        and plan.sparse_data_policy is SparseDataPolicy.INSUFFICIENT_DATA
    ):
        # Compute the missingness summary first so ``detect_flags``
        # can read the observed-ratio and decide whether
        # SPARSE_DATA applies. The summary already uses the
        # filtered ``scoring_observations`` (client sources
        # excluded) — see :func:`build_missingness_summary`.
        missingness = build_missingness_summary(bundle, scoring_observations)
        # Derive the same MISSING_PRIMARY_SOURCE / SPARSE_DATA /
        # LOW_CONFIDENCE triple the scored path derives, then add
        # :attr:`ReviewFlag.INSUFFICIENT_DATA` so the manual-review
        # queue can sort on "insufficient" as the strongest
        # signal. Order is deterministic: INSUFFICIENT_DATA first,
        # then the scored-path-derived flags in their canonical
        # ordering (primary → sparse → low_confidence).
        derived_flags = detect_flags(
            bundle,
            observations=list(scoring_observations),
            missingness=missingness,
        )
        flags: list[ReviewFlag] = [ReviewFlag.INSUFFICIENT_DATA]
        for derived in derived_flags:
            if derived not in flags:
                flags.append(derived)
        rationale = build_rationale(
            bundle=bundle,
            normalized=0.0,
            score_1_10=1,
            components=(),
            missingness=missingness,
            flags=flags,
            proxy_count=count_proxy_observations(scoring_observations),
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

    # Score path: bucket observations into groups and compute each
    # group's contribution. Sum across groups is the normalized
    # score in [0, 1].
    buckets = bucket_observations_by_group(scoring_observations)
    all_components = []
    all_refs = []
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
    missingness = build_missingness_summary(bundle, scoring_observations)
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
