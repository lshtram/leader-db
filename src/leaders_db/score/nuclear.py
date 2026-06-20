"""Nuclear / global responsibility deterministic scorer
(requirement §9, §6).

Eighth per-category deterministic scorer. The rubric is a
transparent 2-group split (FAS consolidated "Status of World
Nuclear Forces" snapshot + SIPRI Yearbook Chapter 7 Table 7.1).
The ``minimum_viable_sources=1`` setting plus the
``SparseDataPolicy.PROVISIONAL_SCORE`` policy mirrors the
nuclear-source-plan's specialization: non-nuclear states (the
~190 of the ~200 prototype countries that are not in the FAS
or SIPRI Yearbook Ch.7 population) are explicitly **not**
invented a numeric score; the scorer routes them through the
``is_insufficient_data=True`` path with both scores ``None``
and a "non-nuclear / no nuclear-source evidence" rationale. The
public import path
``leaders_db.score.nuclear.score_nuclear`` is stable.

- :mod:`leaders_db.score.nuclear` (this file) — the public
  :func:`score_nuclear` facade and the formula / missingness /
  client-handling docstring.
- :mod:`leaders_db.score._nuclear_rubric` — group weights,
  variable-to-group map, sparse threshold (the rubric
  constants).
- :mod:`leaders_db.score._nuclear_components` — per-group
  component/ref computation, the 1..10 scale mapping, the
  leader-name fallback, the per-observation ref builder, the
  client-source re-filter, and the nuclear-source-evidence
  helper.
- :mod:`leaders_db.score._nuclear_flags` — the
  :class:`MissingnessSummary` builder, the proxy-count helper,
  the :class:`ReviewFlag` detector (with the nuclear-specific
  :attr:`ReviewFlag.NUCLEAR_CASE` population split), and the
  rationale composer (with the "non-nuclear / no nuclear-source
  evidence" wording on the insufficient-data path).
- :mod:`leaders_db.score._nuclear_result` — the
  insufficient-data :class:`ScoreResult` assembler used by the
  facade (encapsulates the INSUFFICIENT_DATA-prepended flag
  set and the result shape so the facade stays under the
  400-line convention).

This module exposes :func:`score_nuclear`, which takes a
:class:`~leaders_db.score.evidence.CategoryEvidenceBundle` and
returns a :class:`~leaders_db.score.results.ScoreResult`. The
client 2023 matrix is **not** an input — the client score is
applied downstream (after this function returns) to populate
:attr:`ScoreResult.score_delta_vs_client`; see
:mod:`docs.architecture` §"Client matrix invariants" and
AGENTS.md always-on rule #6.

Formula
-------

Two-group weighted-average rubric; group weights sum to 1.0.
The 0.60 / 0.40 split reflects the strength of the direct
nuclear-arsenal signal each source carries: FAS's 5-indicator
consolidated-status-page snapshot is the canonical
nuclear-arsenal table for the ~9 nuclear-armed states; SIPRI
Yearbook Ch.7 Table 7.1 is the independent cross-validator
(3 indicators: total inventory, deployed, retired).

================== =================================================== ==================
Group              Variables                                           Group weight
================== =================================================== ==================
1. FAS nuclear     ``fas_operational_strategic`` (PREFERRED),         0.60
   forces group     ``fas_operational_nonstrategic`` (FALLBACK),
                    ``fas_reserve_nondeployed`` (FALLBACK),
                    ``fas_military_stockpile`` (PREFERRED),
                    ``fas_total_inventory`` (REQUIRED) — simple
                    mean of available FAS indicators
2. SIPRI           ``sipri_yearbook_ch7_nuclear_warheads_             0.40
   Yearbook Ch.7    total_inventory`` (REQUIRED),
   nuclear forces   ``sipri_yearbook_ch7_nuclear_warheads_             deployed``
   group            (PREFERRED),
                    ``sipri_yearbook_ch7_nuclear_warheads_             retired``
                    (FALLBACK) — simple mean of available SIPRI
                    Yearbook Ch.7 indicators
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
for all 5 FAS indicators and 2 of the 3 SIPRI indicators so the
scorer consumes a single 0..1 scale where 1 is "best" (i.e.
less nuclear capability / more disarmament progress).

Score 1..10 mapping
-------------------

The prototype rubric speaks the customer scale as integer 1..10
even though the DB and the docs use 0..10. The mapping is
half-up and clamped:

    system_proposed_score_1_10 = clamp(1, 10, floor(1 + 9 * normalized + 0.5))

A normalized score of 0.0 maps to 1 (the "least-bad" floor);
1.0 maps to 10. The mapping is intentionally identical to the
7 prior per-category scorers' mapping so a reviewer can
compare scores across the matrix without re-deriving
per-category scaling.

Missingness handling
--------------------

- If the bundle falls below the plan's
  ``minimum_viable_sources`` on **usable** observations (see
  :attr:`CategoryEvidenceBundle.has_minimum_viable_usable_evidence`)
  the function returns an :attr:`ScoreResult.is_insufficient_data`
  result with both scores ``None`` and the
  :attr:`ReviewFlag.INSUFFICIENT_DATA` flag **plus** the same
  :attr:`ReviewFlag.MISSING_PRIMARY_SOURCE` /
  :attr:`ReviewFlag.SPARSE_DATA` /
  :attr:`ReviewFlag.LOW_CONFIDENCE` flags the score path
  derives (via
  :func:`leaders_db.score._nuclear_flags.detect_flags`). The
  :class:`NUCLEAR_PLAN`'s ``sparse_data_policy`` is
  :attr:`SparseDataPolicy.PROVISIONAL_SCORE` but the nuclear
  specialization (per requirement §6 "most countries are
  non-nuclear") is to emit no numeric score for a non-nuclear
  state — so every below-threshold bundle is insufficient-
  data.
- A missing REQUIRED (severity ``PRIMARY``) observation
  triggers :attr:`ReviewFlag.MISSING_PRIMARY_SOURCE` (only for
  non-client ``MissingObservation`` rows — the client 2023
  matrix is validation reference, never evidence).
- Substantial missingness (less than half of plan indicators
  observed) triggers :attr:`ReviewFlag.SPARSE_DATA`.
- Any observation whose :class:`TemporalKind` is not ``DIRECT``
  (``PROXY`` / ``STALE``) triggers
  :attr:`ReviewFlag.LOW_CONFIDENCE` (the FAS snapshot is
  dated 2014-04-30 per the catalog header; the per-plan proxy
  budget accommodates the temporal-fit gap).
- :attr:`ReviewFlag.NUCLEAR_CASE` fires on the **scored** path
  iff the bundle has at least one usable FAS / SIPRI
  Yearbook Ch.7 observation (the §14 manual-review-queue hook
  per REQ-REV-002: "nuclear / global responsibility cases").
  The flag is deliberately **not** added on the insufficient-
  data path — a non-nuclear state with no observations is the
  absence of a nuclear case, not a "nuclear case" itself.
- ``human_review_required`` is set ``True`` iff any of the
  above flags fires; :class:`ScoreResult` forward-invariant
  in :meth:`ScoreResult.__post_init__` enforces consistency.

Observation refs / client handling
---------------------------------

Every component carries a single :class:`ScoreObservationRef`
that points back at its underlying :class:`EvidenceObservation`
(source, variable, observation year, target year). The result's
flat :attr:`ScoreResult.observation_refs` mirrors the per-
component refs.

This scorer never consumes the client 2023 matrix as evidence.
The function strips any observations whose
:attr:`EvidenceObservation.source_key` is in
:data:`leaders_db.score.source_plans.EXCLUDED_SOURCE_KEYS`
(``client_existing`` / ``client_matrix``) before bucketing.
The Stage 5 bundle builder already excludes those source keys
upstream; this re-filter is the scorer's defence-in-depth
boundary. The filtered ``scoring_observations`` set is the
**single** observation basis for every downstream artefact —
components, refs, contributions, missingness, review_flags,
and human_review_required — so a contaminated client
observation cannot influence any artefact even if a
contaminated bundle reaches the scorer. See AGENTS.md
always-on rule #6.

Style invariants (per ``docs/coding-guidelines.md``):

- ``from __future__ import annotations`` for forward-reference
  safety.
- Type hints on every public function parameter and return.
- No mutable defaults; no ``print()``, no ``TODO(debug)``, no
  scratch code.
"""

from __future__ import annotations

import math

from ._nuclear_components import (
    bucket_observations_by_group,
    compute_group_components,
    filter_scoring_basis,
    has_nuclear_source_evidence,
    map_normalized_to_1_10,
    resolve_leader_name,
)
from ._nuclear_flags import (
    build_missingness_summary,
    build_rationale,
    count_proxy_observations,
    detect_flags,
)
from ._nuclear_result import build_insufficient_data_result
from ._nuclear_rubric import _GROUP_WEIGHTS, CATEGORY_KEY
from .evidence import CategoryEvidenceBundle
from .results import ReviewFlag, ScoreResult

__all__ = ["CATEGORY_KEY", "score_nuclear"]


def score_nuclear(bundle: CategoryEvidenceBundle) -> ScoreResult:
    """Return a :class:`ScoreResult` for the nuclear category.

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
        :data:`NUCLEAR_PLAN` (the function does not assert this;
        it inspects the plan fields it needs).

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
    # Scoring-basis filter at the scorer boundary. The filtered
    # set is the **single** observation basis for every
    # downstream artefact: viable-data gate, components, refs,
    # score, flags, NUCLEAR_CASE detection, and rationale. See
    # :func:`filter_scoring_basis` for the three-rule contract
    # (client strip + variable strip + owning-source strip) and
    # AGENTS.md always-on rule #6.
    scoring_observations = filter_scoring_basis(
        bundle.observations, bundle.source_plan
    )

    # Population split: the bundle carries at least one usable
    # FAS / SIPRI Yearbook Ch.7 observation iff the country is
    # in the nuclear-armed population (~9 states). The flag
    # fires on the scored path only — a non-nuclear state with
    # no observations is the absence of a nuclear case, not a
    # "nuclear case" itself.
    has_nuclear_source_evidence_flag = has_nuclear_source_evidence(
        scoring_observations
    )

    # Insufficient-data gate: counts distinct sources of the
    # **scoring-basis usable** subset (additional
    # ``normalized_value is not None`` filter on top of the
    # scoring-basis contract). The gate deliberately uses the
    # scoring-basis set rather than the bundle's loose
    # ``has_minimum_viable_usable_evidence`` so a hand-built
    # bundle carrying a non-FAS / non-SIPRI row with an
    # expected nuclear variable cannot sneak through and emit
    # an invented numeric score. Per requirement §6 ("most
    # countries are non-nuclear") and the no-invented-score
    # invariant, every below-threshold bundle is treated as
    # insufficient-data. The flag set here is the **same** set
    # the score path derives via :func:`detect_flags`, plus
    # :attr:`ReviewFlag.INSUFFICIENT_DATA` prepended so the
    # manual-review queue can sort on "insufficient" as the
    # strongest signal. :attr:`ReviewFlag.NUCLEAR_CASE` is
    # **deliberately not** added on this branch: a non-nuclear
    # state is the absence of a nuclear case. See AGENTS.md
    # always-on rule #6.
    scoring_basis_usable = tuple(
        obs for obs in scoring_observations if obs.normalized_value is not None
    )
    if not bundle.source_plan.minimum_viable_met(scoring_basis_usable):
        return build_insufficient_data_result(
            bundle=bundle,
            scoring_observations=scoring_observations,
            has_nuclear_source_evidence=has_nuclear_source_evidence_flag,
        )

    # Score path: bucket observations into groups and compute
    # each group's contribution. Sum across groups is the
    # normalized score in [0, 1].
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
    # SPARSE_DATA flag (the gate the manual-review queue sorts
    # on).
    missingness = build_missingness_summary(bundle, scoring_observations)
    flags = detect_flags(
        bundle,
        observations=list(scoring_observations),
        missingness=missingness,
    )
    # The NUCLEAR_CASE population-split flag fires on the scored
    # path iff the bundle carries any usable nuclear-source
    # observation (the §14 manual-review-queue hook per
    # REQ-REV-002: "nuclear / global responsibility cases"). It
    # is appended after the scored-path-derived flags so the
    # ordering is deterministic and the manual-review queue can
    # still sort on the existing primary / sparse /
    # low-confidence signals first.
    if has_nuclear_source_evidence_flag:
        if ReviewFlag.NUCLEAR_CASE not in flags:
            flags.append(ReviewFlag.NUCLEAR_CASE)
    proxy_count = count_proxy_observations(scoring_observations)
    rationale = build_rationale(
        bundle=bundle,
        normalized=normalized,
        score_1_10=score_1_10,
        components=all_components,
        missingness=missingness,
        flags=flags,
        proxy_count=proxy_count,
        has_nuclear_source_evidence=has_nuclear_source_evidence_flag,
    )

    # The forward invariant: any review signal implies
    # human_review_required=True. The ScoreResult contract
    # enforces this; we set it explicitly here so the call site
    # is obvious.
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
