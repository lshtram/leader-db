"""Shared scoring result contract for the per-category deterministic scorers.

This module is the **typed output** of the per-category deterministic scoring
modules that will live under :mod:`leaders_db.score.<category>` (one file
per rating category per the AGENTS.md §"Future scoring formulas must live
in separate files per rating category so each can be improved
independently" rule). It is **deliberately not a scoring formula** — it
defines the shape every category scorer will emit so the downstream
comparison / manual-review / summary-report stages can consume a uniform
payload regardless of which category produced it.

The contract is intentionally narrow:

- :class:`ScoreResult` — the per-country/year/leader/category result.
- :class:`ScoreComponent` — one weighted component feeding the result
  (e.g. "V-Dem polyarchy sub-score, weight 0.35, contribution 0.20").
- :class:`ScoreObservationRef` — a pointer to the underlying
  :class:`~leaders_db.score.evidence.EvidenceObservation` so a reviewer
  can audit the row that produced the component.
- :class:`MissingnessSummary` — the roll-up of missing observations the
  scorer saw (count by reason/severity) so the manual-review queue can
  reason about data-quality without re-walking the bundle.
- :class:`ReviewFlag` — the typed reasons a result can be flagged for
  human review (mirrors the §14 manual-review queue priorities).

What this module **does not** do:

- It does not score anything (no formula, no weighting, no normalization).
- It does not depend on Stage 2 ingestion, on the database, on the
  evidence bundle, or on the LLM adapter — it is a pure typed payload.
- It does not carry ``client_score``; the client matrix is the
  validation reference (requirement §3, §9, §12) and stays in
  ``ruler_scores`` / ``validation_results`` — never in the deterministic
  scorer's output (always-on rule #6).

Immutability contract (mirrors ``evidence_plan.py``):

- All dataclasses are ``frozen=True``.
- Sequence fields accept any sequence in ``__init__``, are defensively
  copied to a ``tuple`` in ``__post_init__`` via ``object.__setattr__``,
  and stored only as the tuple. The same pattern the evidence-bundle
  contract uses (``CategoryEvidenceBundle``).
- No mutable defaults. Module-level ``_EMPTY_*`` sentinels are immutable
  tuples shared across instances.

Style invariants (per ``docs/process/coding-guidelines.md``):

- ``from __future__ import annotations`` for forward-reference safety.
- Type hints on every public field and method.
- Light ``__post_init__`` validation matching the evidence-contract style.
- No ``print()``, no ``TODO(debug)``, no scratch code.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum

# ---------------------------------------------------------------------------
# Module-level empty sentinels for sequence fields
# ---------------------------------------------------------------------------
#
# These are immutable and safe to share across instances. The frozen
# dataclass uses them as defaults so empty results do not allocate fresh
# containers per instance. Mirrors ``evidence_plan._EMPTY_*``. The
# type is annotated as a generic tuple so the forward references to
# ``ScoreComponent`` / ``ScoreObservationRef`` resolve cleanly under
# ``from __future__ import annotations`` (annotations are strings at
# runtime, so the sentinel definitions do not need the real types).

_EMPTY_COMPONENTS: tuple = ()
_EMPTY_OBSERVATION_REFS: tuple = ()
_EMPTY_REVIEW_FLAGS: tuple = ()


# ---------------------------------------------------------------------------
# Review flag (the typed reasons a result is queued for human review)
# ---------------------------------------------------------------------------


class ReviewFlag(str, Enum):
    """Typed reasons a :class:`ScoreResult` is flagged for human review.

    The set mirrors the §14 manual-review queue priorities (REQ-REV-002):
    leader identity mismatch, category score delta > 2 vs client,
    confidence < 60, multiple possible rulers, missing primary sources,
    nuclear / global responsibility cases, war / aggression cases, severe
    human-rights / repression cases, and strong disagreement with the
    client matrix. Flags are not mutually exclusive — a single result
    can carry several.

    The deterministic scorer sets these flags from the bundle's
    missingness and the category plan's
    :class:`~leaders_db.score.evidence.SparseDataPolicy`. The client-side
    comparison (the ``score_delta_vs_client`` value) is a *separate* field
    on :class:`ScoreResult`; it does **not** set
    :attr:`ScoreResult.review_flags` directly because the LLM may later
    override the comparison-derived flag.
    """

    MISSING_PRIMARY_SOURCE = "missing_primary_source"
    SPARSE_DATA = "sparse_data"
    LOW_CONFIDENCE = "low_confidence"
    PROVISIONAL_SCORE = "provisional_score"
    INSUFFICIENT_DATA = "insufficient_data"
    NUCLEAR_CASE = "nuclear_case"
    WAR_AGGRESSION_CASE = "war_aggression_case"
    SEVERE_REPRESSION_CASE = "severe_repression_case"
    CATEGORY_OUTLIER = "category_outlier"


# ---------------------------------------------------------------------------
# Score observation ref
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScoreObservationRef:
    """A pointer to the underlying :class:`EvidenceObservation` row.

    The deterministic scorer does **not** embed the full
    :class:`~leaders_db.score.evidence.EvidenceObservation` in the
    result — that is the bundle's job. The result instead carries a
    thin reference (source key + variable name + observation year +
    target year) so a reviewer can find the row in the bundle and from
    there the row in ``source_observations``.

    Attributes
    ----------
    source_key:
        Canonical source identifier (e.g. ``"vdem"``).
    variable_name:
        Canonical indicator name as it appears in the bundle and the
        per-source catalog (e.g. ``"vdem_v2x_polyarchy"``).
    observation_year:
        Year the source reported the value for (``None`` for
        ``TemporalKind.NOT_AVAILABLE`` rows).
    target_year:
        Year the result is being computed for.
    """

    source_key: str
    variable_name: str
    observation_year: int | None
    target_year: int

    def __post_init__(self) -> None:
        if not self.source_key:
            raise ValueError("ScoreObservationRef.source_key must be non-empty")
        if not self.variable_name:
            raise ValueError(
                "ScoreObservationRef.variable_name must be non-empty"
            )
        if not (1900 <= self.target_year <= 2100):
            raise ValueError(
                f"ScoreObservationRef.target_year must be in 1900..2100 "
                f"(got {self.target_year} for {self.variable_name!r})"
            )


# ---------------------------------------------------------------------------
# Score component
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScoreComponent:
    """One weighted component feeding a :class:`ScoreResult`.

    A component is one bullet in the rubric: e.g. "V-Dem polyarchy
    contributed 0.20 to the political-freedom normalized score with
    weight 0.35". The component is the per-source / per-indicator
    contribution; the result sums the contributions to land on the
    ``normalized_score_0_1`` and ``system_proposed_score_1_10`` pair.

    Attributes
    ----------
    component_key:
        Stable identifier for the component (e.g. ``"vdem_polyarchy"``,
        ``"wgi_rule_of_law"``). Must be non-empty so the manual-review
        report can label the contribution.
    source_key:
        Owning source for the component (``"vdem"``, ``"wgi"``, ...).
    variable_name:
        Canonical indicator name for the underlying observation
        (``"vdem_v2x_polyarchy"``, ``"wgi_rule_of_law"``, ...).
    direction:
        Per-component direction (``HIGHER_IS_BETTER`` / ``LOWER_IS_BETTER``).
        Stored here (not just on the plan) so the rationale report does
        not have to walk the plan for every component.
    raw_value:
        The pre-normalization value the scorer saw (``None`` for
        ``MissingObservation`` placeholders).
    normalized_value_0_1:
        The 0..1 normalized value the scorer used in the contribution.
        ``None`` when the component could not be normalized (e.g. the
        source row is missing or the value is out of range).
    weight:
        The plan-level default weight (0..1) for this component. The
        scorer may have re-weighted at runtime (e.g. for stale
        sources); ``weight`` is the actual weight the scorer used.
    contribution_0_1:
        ``normalized_value_0_1 * weight`` if the value is not ``None``,
        else ``0.0``. Stored explicitly so the rationale report does
        not have to re-derive the contribution and so the manual-review
        queue can reason about it.
    observation_refs:
        Tuple of :class:`ScoreObservationRef` rows that fed this
        component. Most components have a single ref; composites built
        from multiple indicators (e.g. ``"wgi_governance_average"``)
        have one ref per contributing indicator.
    """

    component_key: str
    source_key: str
    variable_name: str
    direction: str  # Direction enum value; see evidence_types.Direction
    raw_value: float | None
    normalized_value_0_1: float | None
    weight: float
    contribution_0_1: float
    observation_refs: Sequence[ScoreObservationRef] = _EMPTY_OBSERVATION_REFS

    def __post_init__(self) -> None:
        if not self.component_key:
            raise ValueError("ScoreComponent.component_key must be non-empty")
        if not self.source_key:
            raise ValueError(
                f"ScoreComponent.source_key must be non-empty "
                f"(got {self.source_key!r} for {self.component_key!r})"
            )
        if not self.variable_name:
            raise ValueError(
                f"ScoreComponent.variable_name must be non-empty "
                f"(got {self.variable_name!r} for {self.component_key!r})"
            )
        if not (0.0 <= self.weight <= 1.0):
            raise ValueError(
                f"ScoreComponent.weight must be in 0..1 "
                f"(got {self.weight} for {self.component_key!r})"
            )
        if self.normalized_value_0_1 is not None and not (
            0.0 <= self.normalized_value_0_1 <= 1.0
        ):
            raise ValueError(
                f"ScoreComponent.normalized_value_0_1 must be in 0..1 "
                f"or None (got {self.normalized_value_0_1} for "
                f"{self.component_key!r})"
            )
        if not (0.0 <= self.contribution_0_1 <= 1.0):
            raise ValueError(
                f"ScoreComponent.contribution_0_1 must be in 0..1 "
                f"(got {self.contribution_0_1} for {self.component_key!r})"
            )
        # Defensive copy: tuple storage so external mutation cannot leak
        # in. Mirrors CategorySourcePlan / CategoryEvidenceBundle.
        object.__setattr__(
            self, "observation_refs", tuple(self.observation_refs)
        )


# ---------------------------------------------------------------------------
# Missingness summary
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MissingnessSummary:
    """Roll-up of the bundle's missing observations the scorer saw.

    The deterministic scorer summarises the bundle's
    :class:`~leaders_db.score.evidence.MissingObservation` rows by
    :class:`~leaders_db.score.evidence.MissingReason` and
    :class:`~leaders_db.score.evidence.MissingSeverity`. The summary is
    small (counts only) so the manual-review queue can sort and filter
    without re-walking the bundle, and so the Stage 15 summary report
    can report "12 indicators were missing; 4 of those are
    ``TARGET_YEAR_ABSENT`` and 2 are ``SOURCE_NOT_IMPLEMENTED``"
    without hitting the database.

    Attributes
    ----------
    total_expected:
        Total number of expected indicators the plan declares.
    total_observed:
        Total number of expected indicators the bundle actually carries.
    total_missing:
        ``total_expected - total_observed`` (clipped at zero so a
        plan-over-report scenario never reports a negative count).
    by_reason:
        Map of :class:`MissingReason` value (string) to count. Frozen
        dataclass holds the dict as an immutable view; ``__post_init__``
        copies to a fresh dict and stores a tuple-of-pairs so item
        assignment raises ``AttributeError`` (frozen) and external
        mutation of the caller's dict cannot leak in.
    by_severity:
        Map of :class:`MissingSeverity` value (string) to count. Same
        defensive-copy contract as :attr:`by_reason`.
    """

    total_expected: int
    total_observed: int
    by_reason: Sequence[tuple[str, int]] = field(default_factory=tuple)
    by_severity: Sequence[tuple[str, int]] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.total_expected < 0:
            raise ValueError(
                f"MissingnessSummary.total_expected must be >= 0 "
                f"(got {self.total_expected})"
            )
        if self.total_observed < 0:
            raise ValueError(
                f"MissingnessSummary.total_observed must be >= 0 "
                f"(got {self.total_observed})"
            )
        if self.total_observed > self.total_expected:
            raise ValueError(
                f"MissingnessSummary.total_observed ({self.total_observed}) "
                f"cannot exceed total_expected ({self.total_expected})"
            )
        # Defensive copies + value validation.
        reason_pairs = tuple((str(k), int(v)) for k, v in self.by_reason)
        for key, value in reason_pairs:
            if value < 0:
                raise ValueError(
                    f"MissingnessSummary.by_reason count must be >= 0 "
                    f"(got {value!r} for {key!r})"
                )
        object.__setattr__(self, "by_reason", reason_pairs)
        severity_pairs = tuple((str(k), int(v)) for k, v in self.by_severity)
        for key, value in severity_pairs:
            if value < 0:
                raise ValueError(
                    f"MissingnessSummary.by_severity count must be >= 0 "
                    f"(got {value!r} for {key!r})"
                )
        object.__setattr__(self, "by_severity", severity_pairs)

    @property
    def total_missing(self) -> int:
        """Return ``total_expected - total_observed`` clipped at zero."""
        return max(0, self.total_expected - self.total_observed)


# ---------------------------------------------------------------------------
# Score result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScoreResult:
    """The deterministic scorer's per-country/year/leader/category result.

    This is the uniform payload every per-category deterministic scorer
    emits (Stage 9-10 in the §8 pipeline). Downstream stages
    (comparison, manual-review queue, summary report) consume this
    shape regardless of which category produced it. The scorer is
    owned by a per-category file (``src/leaders_db/score/<category>.py``)
    per the AGENTS.md rule "future scoring formulas must live in
    separate files per rating category so each can be improved
    independently" — but the result shape is shared here.

    The result deliberately does **not** carry ``client_score`` or
    ``score_delta_vs_client``. The client matrix is validation
    reference only (requirement §3, §9, §12; always-on rule #6);
    those values live in ``ruler_scores.client_score`` and
    ``validation_results.score_delta`` (per the database schema).
    The result carries ``score_delta_vs_client`` as a typed
    convenience for the comparison / manual-review stages so they
    do not have to join ``ruler_scores`` and ``validation_results``
    on every read — but the value is a copy, not the source of
    truth, and the contract is explicit that the scorer never
    uses the client score as input.

    Attributes
    ----------
    category_key:
        Canonical category identifier (e.g. ``"political_freedom"``).
        Must match the source plan's ``category_key`` and one of the 8
        category keys in requirement §4.
    iso3:
        Country ISO3 code (the canonical country key per
        ``docs/process/coding-guidelines.md``).
    year:
        Target year the result is computed for (e.g. ``2023``).
        Must be in 1900..2100 to match the evidence contract.
    leader_name:
        System-selected leader display name. The deterministic scorer
        receives the resolved leader from the Stage 4 resolver; this
        is a copy used in the rationale.
    normalized_score_0_1:
        The 0..1 normalized score (closed interval; the scorer clamps
        to 0..1 in ``__post_init__`` to catch arithmetic drift).
        ``None`` for :attr:`is_insufficient_data` results — the
        scorer explicitly declined to emit a score.
    system_proposed_score_1_10:
        The 0..10 integer score the scorer proposes (the canonical
        scoring scale the client matrix uses). ``None`` for
        :attr:`is_insufficient_data` results.
    components:
        Tuple of :class:`ScoreComponent` rows that fed the result.
        The sum of :attr:`ScoreComponent.contribution_0_1` is the
        numerator of :attr:`normalized_score_0_1`; the components are
        preserved for the rationale report.
    observation_refs:
        Flat tuple of every :class:`ScoreObservationRef` the scorer
        saw. Same data is reachable via ``components[i].observation_refs``
        but the flat list lets the manual-review queue iterate without
        walking components.
    missingness:
        The :class:`MissingnessSummary` the scorer computed.
    rationale_short:
        Short human-readable rationale (1-3 sentences). The detailed
        per-component rationale lives in the LLM ``LLMScoreOutput``
        payload (when the LLM is enabled) and in the Stage 15 summary
        report; this short field is for the comparison / manual-review
        queue row preview.
    human_review_required:
        Scorer-set high-level "needs manual attention" signal. The
        forward direction of the invariant is **enforced** in
        :meth:`__post_init__`: if any of :attr:`review_flags`,
        :attr:`is_provisional`, or :attr:`is_insufficient_data` is
        set, then ``human_review_required`` must be ``True`` —
        otherwise construction raises :class:`ValueError`. The
        reverse direction is intentionally not constrained: a
        result may carry ``human_review_required=True`` with empty
        ``review_flags`` when the rationale flags a reason outside
        the typed enum (see :attr:`review_flags`). The comparison
        stage and the manual-review queue treat this field as the
        high-level "needs attention" signal — it is the join key
        they sort on, so a flagged / provisional / insufficient
        result silently landing with ``human_review_required=False``
        would skip the queue.
    review_flags:
        Tuple of :class:`ReviewFlag` values describing *why* a result
        needs review. May be empty even when ``human_review_required``
        is True (the rationale may set the flag from a free-form
        reason; future per-component flags will use this enum).
    is_provisional:
        True iff the result is a low-confidence provisional score (the
        :class:`~leaders_db.score.evidence.SparseDataPolicy` was
        ``PROVISIONAL_SCORE`` and the bundle fell below the
        ``minimum_viable_sources`` threshold). Provisional results
        always set :attr:`review_flags` to include
        :attr:`ReviewFlag.PROVISIONAL_SCORE`.
    is_insufficient_data:
        True iff the bundle fell below ``minimum_viable_sources`` and
        the plan's policy was :attr:`SparseDataPolicy.INSUFFICIENT_DATA`.
        In that case :attr:`normalized_score_0_1` and
        :attr:`system_proposed_score_1_10` are ``None``.
    score_delta_vs_client:
        ``system_proposed_score_1_10 - client_score`` when both are
        not ``None``; ``None`` otherwise. Convenience for the
        comparison stage; the source of truth lives in
        ``validation_results.score_delta``.
    """

    category_key: str
    iso3: str
    year: int
    leader_name: str
    normalized_score_0_1: float | None
    system_proposed_score_1_10: int | None
    components: Sequence[ScoreComponent] = _EMPTY_COMPONENTS
    observation_refs: Sequence[ScoreObservationRef] = _EMPTY_OBSERVATION_REFS
    missingness: MissingnessSummary | None = None
    rationale_short: str = ""
    human_review_required: bool = False
    review_flags: Sequence[ReviewFlag] = _EMPTY_REVIEW_FLAGS
    is_provisional: bool = False
    is_insufficient_data: bool = False
    score_delta_vs_client: int | None = None

    def __post_init__(self) -> None:
        if not self.category_key:
            raise ValueError("ScoreResult.category_key must be non-empty")
        if not self.iso3 or len(self.iso3) != 3:
            raise ValueError(
                f"ScoreResult.iso3 must be a 3-letter ISO3 code "
                f"(got {self.iso3!r} for category {self.category_key!r})"
            )
        if not (1900 <= self.year <= 2100):
            raise ValueError(
                f"ScoreResult.year must be in 1900..2100 "
                f"(got {self.year} for category {self.category_key!r})"
            )
        if not self.leader_name:
            raise ValueError("ScoreResult.leader_name must be non-empty")
        # Score range validation. ``None`` is the explicit "no score"
        # signal for insufficient-data results; the scorer does not
        # have to lie about the score.
        if self.normalized_score_0_1 is not None and not (
            0.0 <= self.normalized_score_0_1 <= 1.0
        ):
            raise ValueError(
                f"ScoreResult.normalized_score_0_1 must be in 0..1 "
                f"or None (got {self.normalized_score_0_1} for "
                f"{self.category_key!r} / {self.iso3} / {self.year})"
            )
        if self.system_proposed_score_1_10 is not None and not (
            0 <= self.system_proposed_score_1_10 <= 10
        ):
            raise ValueError(
                f"ScoreResult.system_proposed_score_1_10 must be in 0..10 "
                f"or None (got {self.system_proposed_score_1_10} for "
                f"{self.category_key!r} / {self.iso3} / {self.year})"
            )
        # Cross-field validation: a score pair is either both
        # populated (provisional or normal result) or both ``None``
        # (insufficient-data result). A half-populated result is
        # always a bug — the manual-review queue and the comparison
        # stage sort on the explicit pair.
        if self.is_insufficient_data and (
            self.normalized_score_0_1 is not None
            or self.system_proposed_score_1_10 is not None
        ):
            raise ValueError(
                "ScoreResult.is_insufficient_data=True requires "
                "normalized_score_0_1 and system_proposed_score_1_10 "
                f"to be None (got category {self.category_key!r} / "
                f"{self.iso3} / {self.year})"
            )
        if not self.is_insufficient_data and (
            self.normalized_score_0_1 is None
            or self.system_proposed_score_1_10 is None
        ):
            raise ValueError(
                "ScoreResult with is_insufficient_data=False requires "
                "both normalized_score_0_1 and system_proposed_score_1_10 "
                f"to be set (got category {self.category_key!r} / "
                f"{self.iso3} / {self.year})"
            )
        # Defensive copies.
        object.__setattr__(self, "components", tuple(self.components))
        object.__setattr__(
            self, "observation_refs", tuple(self.observation_refs)
        )
        object.__setattr__(self, "review_flags", tuple(self.review_flags))
        # Cross-field invariant: any review signal (a typed
        # :attr:`review_flags` entry, :attr:`is_provisional`, or
        # :attr:`is_insufficient_data`) must imply
        # ``human_review_required=True``. The reverse is allowed —
        # ``human_review_required=True`` with empty ``review_flags``
        # is a valid "rationale-level" reason that has not yet been
        # encoded as a typed flag. We reject the inconsistent
        # combination rather than silently overwriting the caller's
        # value so scorer bugs surface immediately at construction
        # instead of producing a downstream row that silently skips
        # the manual-review queue.
        has_review_signal = (
            bool(self.review_flags)
            or self.is_provisional
            or self.is_insufficient_data
        )
        if has_review_signal and not self.human_review_required:
            raise ValueError(
                "ScoreResult.human_review_required must be True when "
                "any of review_flags, is_provisional, or "
                f"is_insufficient_data is set (got category "
                f"{self.category_key!r} / {self.iso3} / {self.year}; "
                f"review_flags={list(self.review_flags)!r}, "
                f"is_provisional={self.is_provisional}, "
                f"is_insufficient_data={self.is_insufficient_data})"
            )

    @property
    def observed_component_count(self) -> int:
        """Return the number of components with a non-None normalized value.

        The manual-review queue and the summary report use this to
        answer "how many of the plan's expected indicators did the
        scorer actually see?" without re-walking the components.
        """
        return sum(
            1 for c in self.components if c.normalized_value_0_1 is not None
        )


__all__ = [
    "MissingnessSummary",
    "ReviewFlag",
    "ScoreComponent",
    "ScoreObservationRef",
    "ScoreResult",
]
