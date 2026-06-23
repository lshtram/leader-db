"""Insufficient-data result assembler for the nuclear scorer.

This module owns the insufficient-data :class:`ScoreResult`
construction for the ``nuclear`` deterministic scorer. The
facade (:func:`leaders_db.score.nuclear.score_nuclear`) calls
:func:`build_insufficient_data_result` once the
``minimum_viable_sources`` gate fires; the helper encapsulates
the derived-flag set, rationale wording, and result shape so
the facade stays under the 400-line convention while the
nuclear specialization's insufficient-data contract stays in a
single focused module.

The nuclear specialization (per requirement §6 "most countries
are non-nuclear") is **non-nuclear states must never receive
an invented numeric score**. The helper encodes three
behaviours that distinguish the nuclear insufficient-data
contract from the social-wellbeing / integrity /
effectiveness / economic-wellbeing / political-freedom /
domestic-violence / international-peace scorers':

- :attr:`ReviewFlag.INSUFFICIENT_DATA` is **prepended** to the
  derived flag set (the ``MISSING_PRIMARY_SOURCE`` /
  ``SPARSE_DATA`` / ``LOW_CONFIDENCE`` triple
  :func:`~leaders_db.score._nuclear_flags.detect_flags`
  returns) so the manual-review queue can sort on "insufficient"
  as the strongest signal. This is the reviewer-blocker fix the
  :mod:`tests.test_score_nuclear_insufficient_flags` test
  module pins.
- :attr:`ReviewFlag.NUCLEAR_CASE` is **deliberately not** added
  here. A non-nuclear state with no observations is the
  absence of a nuclear case, not "a nuclear case" itself; the
  facade adds the flag only on the scored path (see
  :func:`leaders_db.score.nuclear.score_nuclear`).
- The rationale carries the "no nuclear-source evidence found"
  wording so a manual-review reader can tell a non-nuclear
  state from a sparse-bundle pathology (see
  :func:`~leaders_db.score._nuclear_flags.build_rationale`).
  The rationale **must not** state or imply a numeric score
  on this path (the contract requires
  ``system_proposed_score_1_10 is None``).

The caller passes the filtered ``scoring_observations`` (client
sources already excluded via
:func:`~leaders_db.score._nuclear_components.filter_scoring_basis`)
so a contaminated bundle cannot inflate
``missingness.total_observed`` and silently suppress
:attr:`ReviewFlag.SPARSE_DATA`. The caller must have already
decided the insufficient-data gate fires — this helper does
not re-evaluate the gate.

Style invariants (per ``docs/process/coding-guidelines.md``):

- ``from __future__ import annotations`` for forward-reference
  safety.
- Type hints on every public function.
- No mutable defaults; no ``print()``, no ``TODO(debug)``, no
  scratch.
"""

from __future__ import annotations

from collections.abc import Iterable

from ._nuclear_components import resolve_leader_name
from ._nuclear_flags import (
    build_missingness_summary,
    build_rationale,
    count_proxy_observations,
    detect_flags,
)
from ._nuclear_rubric import CATEGORY_KEY
from .evidence import CategoryEvidenceBundle, EvidenceObservation
from .results import ReviewFlag, ScoreResult


def build_insufficient_data_result(
    *,
    bundle: CategoryEvidenceBundle,
    scoring_observations: Iterable[EvidenceObservation],
    has_nuclear_source_evidence: bool,
) -> ScoreResult:
    """Assemble the insufficient-data :class:`ScoreResult` for the facade.

    The caller passes the filtered ``scoring_observations``
    (client sources excluded). :attr:`ReviewFlag.INSUFFICIENT_DATA`
    is **prepended** to the derived-flag set so the manual-
    review queue can sort on "insufficient" as the strongest
    signal. :attr:`ReviewFlag.NUCLEAR_CASE` is deliberately not
    added here (a non-nuclear state is the absence of a
    nuclear case). Both scores are ``None``; the rationale
    carries the "no nuclear-source evidence found" wording so
    a manual-review reader can tell a non-nuclear state from
    a sparse-bundle pathology. See the module docstring for
    the full contract.
    """
    scoring_observations_list = list(scoring_observations)
    missingness = build_missingness_summary(
        bundle, scoring_observations_list
    )
    derived_flags = detect_flags(
        bundle,
        observations=scoring_observations_list,
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
        proxy_count=count_proxy_observations(scoring_observations_list),
        has_nuclear_source_evidence=has_nuclear_source_evidence,
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


__all__ = ["build_insufficient_data_result"]
