"""The :class:`CategorySourcePlan` — the expected source set for one
rating category (Stage 5 input).

Aligns with ``docs/architecture.md`` §"Evidence Bundle Contract"
(``CategorySourcePlan`` block) and REQ-SCORE-004 ("category source
plans shall define required, preferred, and fallback indicators;
minimum viable source thresholds; default weights; directionality;
accepted proxy-year rules; and whether sparse data should produce a
low-confidence provisional score or insufficient_data").

The plan is the **input** to Stage 5; the
:class:`~leaders_db.score.evidence_bundle.CategoryEvidenceBundle` is
the **output** that wraps the plan together with the available
``EvidenceObservation`` rows and the ``MissingObservation`` records.
The plan module imports only from ``evidence_types`` and
``evidence_observation`` — never from ``evidence_bundle`` — so the
bundle module can import the plan without creating a cycle.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .evidence_observation import EvidenceObservation
from .evidence_types import (
    Direction,
    IndicatorRole,
    IndicatorSpec,
    SparseDataPolicy,
)

# ---------------------------------------------------------------------------
# Module-level empty sentinels for sequence fields
# ---------------------------------------------------------------------------
#
# These are immutable and safe to share across instances. The frozen
# dataclass uses them as defaults so empty plans do not allocate fresh
# containers per instance.

_EMPTY_STRINGS: tuple[str, ...] = ()
_EMPTY_INDICATORS: tuple[IndicatorSpec, ...] = ()
_EMPTY_YEARS: tuple[int, ...] = ()
_EMPTY_SOURCE_WEIGHTS: tuple[tuple[str, float], ...] = ()


# ---------------------------------------------------------------------------
# Category source plan
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CategorySourcePlan:
    """The expected source set for one rating category (Stage 5 input).

    Attributes
    ----------
    category_key:
        Canonical category identifier (e.g. ``"political_freedom"``).
    expected_sources:
        Source keys expected for this category (e.g.
        ``("vdem", "rsf_press_freedom", "polity_v")``). The constructor
        accepts any sequence; the stored value is a tuple.
    expected_indicators:
        Per-indicator specs (role, direction, default weight). The
        :attr:`expected_variables` view derives the simple variable-name
        list from these.
    minimum_viable_sources:
        Minimum number of distinct sources with an observation required
        for the scorer to emit a provisional score instead of
        ``insufficient_data``. See REQ-SCORE-004.
    preferred_direct_year:
        The target year the plan is written for. Direct-year observations
        for this year score highest on ``temporal_fit``.
    allowed_proxy_years:
        Acceptable year offsets for proxy-year observations. The plan
        treats year deltas within this set as ``TemporalKind.PROXY``;
        larger deltas are demoted to ``TemporalKind.STALE``. Per
        REQ-SCORE-004 ("accepted proxy-year rules").
    default_source_weights:
        Per-source default weights (0..1). ``default_source_weight(key)``
        returns the configured weight, or ``1.0`` for sources without
        an override. Per REQ-SCORE-004 ("default weights").
    sparse_data_policy:
        What the scorer should do when ``minimum_viable_sources`` is not
        met. Per REQ-SCORE-004 ("low-confidence provisional score vs
        insufficient_data").
    """

    category_key: str
    expected_sources: Sequence[str] = _EMPTY_STRINGS
    expected_indicators: Sequence[IndicatorSpec] = _EMPTY_INDICATORS
    minimum_viable_sources: int = 0
    preferred_direct_year: int = 2023
    allowed_proxy_years: Sequence[int] = _EMPTY_YEARS
    default_source_weights: Sequence[tuple[str, float]] = _EMPTY_SOURCE_WEIGHTS
    sparse_data_policy: SparseDataPolicy = SparseDataPolicy.INSUFFICIENT_DATA

    def __post_init__(self) -> None:
        # Defensive copy: convert any sequence to a tuple so external
        # mutation of the caller's input cannot leak into the plan.
        object.__setattr__(self, "expected_sources", tuple(self.expected_sources))
        object.__setattr__(self, "expected_indicators", tuple(self.expected_indicators))
        object.__setattr__(self, "allowed_proxy_years", tuple(self.allowed_proxy_years))
        object.__setattr__(
            self,
            "default_source_weights",
            tuple((str(k), float(v)) for k, v in self.default_source_weights),
        )

        if not self.category_key:
            raise ValueError("CategorySourcePlan.category_key must be non-empty")
        if self.minimum_viable_sources < 0:
            raise ValueError(
                f"minimum_viable_sources must be >= 0 "
                f"(got {self.minimum_viable_sources})"
            )
        if not (1900 <= self.preferred_direct_year <= 2100):
            raise ValueError(
                f"preferred_direct_year must be in 1900..2100 "
                f"(got {self.preferred_direct_year})"
            )
        # Re-validate per-indicator and per-source weights here as a
        # defence-in-depth check (IndicatorSpec.__post_init__ already
        # validates the per-indicator range, but a caller could pass
        # a raw tuple of pairs that bypassed that).
        for spec in self.expected_indicators:
            if not (0.0 <= spec.weight <= 1.0):
                raise ValueError(
                    f"indicator weight for {spec.variable_name!r} must be in "
                    f"0..1 (got {spec.weight})"
                )
        for key, weight in self.default_source_weights:
            if not (0.0 <= weight <= 1.0):
                raise ValueError(
                    f"source weight for {key!r} must be in 0..1 "
                    f"(got {weight})"
                )

    @property
    def expected_variables(self) -> tuple[str, ...]:
        """Return the canonical ``variable_name`` list for this plan.

        Derived from :attr:`expected_indicators`; preserved for back-
        compatibility with the Stage 5 contract and the architecture
        document's ``expected_variables`` field.
        """
        return tuple(spec.variable_name for spec in self.expected_indicators)

    # ----- role helpers (REQ-SCORE-004) -----

    def role_of(self, variable_name: str) -> IndicatorRole | None:
        """Return the :class:`IndicatorRole` for ``variable_name`` (or None)."""
        for spec in self.expected_indicators:
            if spec.variable_name == variable_name:
                return spec.role
        return None

    def is_required_variable(self, variable_name: str) -> bool:
        """Return True iff ``variable_name`` is a REQUIRED indicator in this plan."""
        return self.role_of(variable_name) is IndicatorRole.REQUIRED

    def is_preferred_variable(self, variable_name: str) -> bool:
        """Return True iff ``variable_name`` is a PREFERRED indicator in this plan."""
        return self.role_of(variable_name) is IndicatorRole.PREFERRED

    def is_fallback_variable(self, variable_name: str) -> bool:
        """Return True iff ``variable_name`` is a FALLBACK indicator in this plan."""
        return self.role_of(variable_name) is IndicatorRole.FALLBACK

    def direction_of(self, variable_name: str) -> Direction | None:
        """Return the :class:`Direction` for ``variable_name`` (or None)."""
        for spec in self.expected_indicators:
            if spec.variable_name == variable_name:
                return spec.direction
        return None

    # ----- weight helpers (REQ-SCORE-004 "default indicator/source weights") -----

    def default_indicator_weight(self, variable_name: str) -> float:
        """Return the plan-level default weight for ``variable_name``.

        Returns ``0.0`` for an unknown variable (the safe choice: do not
        contribute weight to an indicator the plan does not know about;
        the caller's role check decides whether to even reach this
        method).
        """
        for spec in self.expected_indicators:
            if spec.variable_name == variable_name:
                return spec.weight
        return 0.0

    def default_source_weight(self, source_key: str) -> float:
        """Return the plan-level default weight for ``source_key``.

        Returns ``1.0`` for a source without an explicit override in
        :attr:`default_source_weights` (i.e. equal weight with the
        other sources in the plan).
        """
        for key, weight in self.default_source_weights:
            if key == source_key:
                return weight
        return 1.0

    def minimum_viable_met(
        self, observations: Sequence[EvidenceObservation]
    ) -> bool:
        """Return True iff ``observations`` satisfies the minimum-viable threshold.

        The threshold counts **distinct source keys** in ``observations``
        (a single source contributing two variables counts once), then
        compares against :attr:`minimum_viable_sources`. This matches the
        architecture's "if fewer than the category's minimum viable
        sources are available" rule (REQ-SCORE-004).
        """
        distinct_sources = {obs.source_key for obs in observations}
        return len(distinct_sources) >= self.minimum_viable_sources


__all__ = ["CategorySourcePlan"]
