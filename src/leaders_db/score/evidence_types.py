"""Type vocabulary for the Stage 5 evidence bundle contract.

This module defines the **leaf** types used everywhere else in the
Stage 5 evidence bundle contract:

- The six contract enums (:class:`Direction`, :class:`TemporalKind`,
  :class:`MissingReason`, :class:`MissingSeverity`,
  :class:`IndicatorRole`, :class:`SparseDataPolicy`).
- The :class:`IndicatorSpec` dataclass — the per-indicator
  (variable, role, direction, weight) tuple that the
  :class:`~leaders_db.score.evidence_plan.CategorySourcePlan` groups
  into ``expected_indicators``.

These types are deliberately dependency-free: no imports from
``evidence_plan``, ``evidence_observation``, or ``evidence_bundle``.
That keeps the vocabulary reusable from the per-row observation types
and the plan type, and lets the bundle module own its imports of
this module without risking a cycle.

Style invariants (per ``docs/coding-guidelines.md``):

- Type hints on every public field and method.
- ``from __future__ import annotations`` for forward-reference safety.
- ``@dataclass(frozen=True)`` for the typed payload.
- No mutable defaults; no ``print()``, no ``TODO(debug)``, no scratch.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# ---------------------------------------------------------------------------
# Enums (the literal-like constants required by the contract)
# ---------------------------------------------------------------------------


class Direction(str, Enum):
    """Indicator directionality (Stage 6 normalization contract).

    ``HIGHER_IS_BETTER`` means larger raw values correspond to a better
    outcome on the category's rubric (e.g. higher V-Dem polyarchy score
    = more democracy). ``LOWER_IS_BETTER`` means the opposite (e.g.
    higher CPI corruption perception = more corrupt).
    """

    HIGHER_IS_BETTER = "higher_is_better"
    LOWER_IS_BETTER = "lower_is_better"


class TemporalKind(str, Enum):
    """How an observation's ``observation_year`` relates to ``target_year``.

    Per REQ-STAGE-007 and the temporal_fit component of the confidence
    formula (§11):

    - ``DIRECT``: the observation's year matches the target year.
    - ``PROXY``: the observation is for a recent adjacent year within the
      category's ``allowed_proxy_years`` budget.
    - ``STALE``: the observation is older than the proxy budget but still
      informative (e.g. Polity V 2018 used for a 2023 target).
    - ``NOT_AVAILABLE``: the observation cannot be placed on the timeline
      (no usable year); kept as a placeholder so the bundle still has a
      raw locator and a missingness reason.
    """

    DIRECT = "direct"
    PROXY = "proxy"
    STALE = "stale"
    NOT_AVAILABLE = "not_available"


class MissingReason(str, Enum):
    """Why an expected observation is missing from the bundle.

    The eight values enumerate the missingness cases called out in
    REQ-STAGE-007 and ``docs/architecture.md`` §"Confidence and
    Missingness". Distinguishing these is part of confidence — a
    ``not_applicable`` is not the same failure mode as ``blocked_or_paywalled``
    or ``source_not_implemented``.
    """

    SOURCE_NOT_IMPLEMENTED = "source_not_implemented"
    RAW_FILE_ABSENT = "raw_file_absent"
    COUNTRY_ROW_ABSENT = "country_row_absent"
    TARGET_YEAR_ABSENT = "target_year_absent"
    INDICATOR_NULL = "indicator_null"
    NOT_APPLICABLE = "not_applicable"
    BLOCKED_OR_PAYWALLED = "blocked_or_paywalled"
    EXCLUDED_BY_CONFIG = "excluded_by_config"


class MissingSeverity(str, Enum):
    """How much a missing observation hurts the category score.

    Per REQ-SCORE-004 ("category source plans shall define required,
    preferred, and fallback indicators; minimum viable source thresholds")
    and REQ-CONF-005 ("missing expected indicators shall affect confidence
    and review status according to the category source plan"):

    - ``PRIMARY``: the category plan cannot produce a confident score
      without this observation; manual review is likely.
    - ``IMPORTANT``: the observation is part of the rubric but a fallback
      exists; the scorer should emit a provisional score and a confidence
      penalty.
    - ``OPTIONAL``: nice-to-have; absence has minimal impact on score and
      confidence.
    """

    PRIMARY = "primary"
    IMPORTANT = "important"
    OPTIONAL = "optional"


class IndicatorRole(str, Enum):
    """Per-indicator role inside a category source plan (REQ-SCORE-004).

    The category source plan must classify every expected indicator into
    one of three roles so the scorer knows how to weight a missing
    observation:

    - ``REQUIRED``: the category rubric is not well-defined without this
      indicator. A missing REQUIRED indicator is a strong manual-review
      trigger and typically blocks a confident score.
    - ``PREFERRED``: the indicator strengthens the rubric but the plan
      has one or more fallbacks. A missing PREFERRED indicator drops
      confidence but does not block the score.
    - ``FALLBACK``: a substitute for a PREFERRED indicator. FALLBACKs
      are used when the PREFERRED source is missing; they are not
      themselves triggers for manual review.
    """

    REQUIRED = "required"
    PREFERRED = "preferred"
    FALLBACK = "fallback"


class SparseDataPolicy(str, Enum):
    """What the scorer should do when ``minimum_viable_sources`` is not met.

    Per REQ-SCORE-004 ("whether sparse data should produce a
    low-confidence provisional score or insufficient_data"):

    - ``PROVISIONAL_SCORE``: emit a low-confidence provisional score
      anyway, with a confidence penalty, and queue the bundle for
      manual review.
    - ``INSUFFICIENT_DATA``: do not emit a score; record
      ``insufficient_data`` and queue the bundle for manual review. This
      is the safe default for categories whose rubric depends on a
      critical mass of independent sources.
    """

    PROVISIONAL_SCORE = "provisional_score"
    INSUFFICIENT_DATA = "insufficient_data"


# ---------------------------------------------------------------------------
# Per-indicator spec
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IndicatorSpec:
    """One expected indicator inside a category source plan.

    Aligns with REQ-SCORE-004 ("default indicator weights, directionality
    per indicator, and indicator roles"). The plan groups these into
    :attr:`CategorySourcePlan.expected_indicators`; the role helpers on
    the plan (``is_required_variable`` / ``is_preferred_variable`` /
    ``is_fallback_variable``) look up the role, the per-indicator
    direction is exposed via :meth:`CategorySourcePlan.direction_of`,
    and the per-indicator default weight via
    :meth:`CategorySourcePlan.default_indicator_weight`.

    Attributes
    ----------
    variable_name:
        Canonical ``variable_name`` for the indicator (e.g.
        ``"v2x_polyarchy"``).
    role:
        :class:`IndicatorRole` for this indicator inside its category.
    direction:
        :class:`Direction` for this indicator (which way is "better").
    weight:
        Default 0..1 weight for this indicator. ``1.0`` is "equal
        weight with the other indicators in the plan"; ``0.0`` would
        drop the indicator from the score entirely. The score module
        may override this at runtime (e.g. when a source is stale), but
        ``weight`` is the plan-level default.
    source_key:
        Optional canonical source key that **owns** this indicator in
        the plan (e.g. ``"vdem"`` for ``"vdem_v2x_corr"``). When the
        Stage 5 evidence-bundle builder queries ``source_observations``
        it scopes the lookup to this single source (a wrong-source row
        is ignored and the indicator is reported missing). When
        ``None``, the builder falls back to the plan's first
        ``expected_sources`` entry — the production
        :mod:`leaders_db.score.source_plans` declarations always set
        the field explicitly so the fallback only fires for ad-hoc
        test fixtures. See the Stage 5 ``build_category_evidence_bundle``
        contract for the owning-source rule.
    """

    variable_name: str
    role: IndicatorRole
    direction: Direction
    weight: float = 1.0
    source_key: str | None = None

    def __post_init__(self) -> None:
        if not self.variable_name:
            raise ValueError("IndicatorSpec.variable_name must be non-empty")
        if not isinstance(self.role, IndicatorRole):
            raise ValueError(
                f"IndicatorSpec.role must be an IndicatorRole "
                f"(got {type(self.role).__name__})"
            )
        if not isinstance(self.direction, Direction):
            raise ValueError(
                f"IndicatorSpec.direction must be a Direction "
                f"(got {type(self.direction).__name__})"
            )
        if not (0.0 <= self.weight <= 1.0):
            raise ValueError(
                f"IndicatorSpec.weight must be in 0..1 "
                f"(got {self.weight} for {self.variable_name!r})"
            )
        if self.source_key is not None and not self.source_key:
            raise ValueError(
                "IndicatorSpec.source_key must be a non-empty string "
                "or None (got empty string for "
                f"{self.variable_name!r})"
            )


__all__ = [
    "Direction",
    "IndicatorRole",
    "IndicatorSpec",
    "MissingReason",
    "MissingSeverity",
    "SparseDataPolicy",
    "TemporalKind",
]
