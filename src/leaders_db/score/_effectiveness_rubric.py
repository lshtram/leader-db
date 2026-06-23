"""Effectiveness rubric constants.

This module is the **internal** rubric for the effectiveness
category scorer (:mod:`leaders_db.score.effectiveness`). It owns
the variables-to-group mapping, the per-group weights, and the
sparse-data threshold so the per-component and per-flag helpers
can read the rubric without re-declaring it. The facade
(:func:`leaders_db.score.effectiveness.score_effectiveness`)
re-exports :data:`CATEGORY_KEY` and :data:`_GROUP_WEIGHTS` so the
rest of the package can refer to the category identifier and the
per-group weights without depending on this private module.

Rubric
------

Three-group weighted-average; group weights sum to 1.0. See
:mod:`leaders_db.score.effectiveness` for the full docstring
that walks a reviewer through the formula end-to-end.

================== =================================================== ==================
Group              Variables                                           Group weight
================== =================================================== ==================
1. WGI governance  ``wgi_voice_and_accountability`` (PREFERRED),      0.45
   group           ``wgi_political_stability`` (PREFERRED),
                   ``wgi_government_effectiveness`` (REQUIRED),
                   ``wgi_regulatory_quality`` (PREFERRED),
                   ``wgi_rule_of_law`` (REQUIRED) — simple mean
                   of available WGI governance indicators
2. V-Dem           ``vdem_v2x_jucon`` (PREFERRED),                    0.35
   governance /    ``vdem_v2xlg_legcon`` (PREFERRED),
   accountability  ``vdem_v2x_accountability`` (REQUIRED),
   group           ``vdem_v2x_mpi`` (PREFERRED),
                   ``vdem_v2x_regime`` (FALLBACK) — simple mean
                   of available V-Dem indicators
3. BTI governance  ``bti_governance_index`` (REQUIRED),              0.20
   group           ``bti_governance_performance`` (PREFERRED) —
                   simple mean of available BTI governance
                   composites
================== =================================================== ==================

Style invariants (per ``docs/process/coding-guidelines.md``):

- ``from __future__ import annotations`` for forward-reference
  safety.
- No mutable defaults; no ``print()``, no ``TODO(debug)``, no
  scratch code.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Public constant — exposed so the facade can re-export it without depending
# on this private module.
# ---------------------------------------------------------------------------

#: Canonical category identifier for the effectiveness scorer. Matches
#: :data:`EFFECTIVENESS_PLAN.category_key` and one of the 8 categories
#: in requirement §4.
CATEGORY_KEY: str = "effectiveness"


# ---------------------------------------------------------------------------
# Group weights — documented in the facade docstring; do not invent
# different weights in a one-off script.
# ---------------------------------------------------------------------------
#
# Rationale (per the source plan): WGI has the strongest direct
# governance/effectiveness signal (the 5 indicators are explicitly the
# World Bank's Worldwide Governance Indicators, mapped to the same
# construct). V-Dem cross-validates with expert-coded judicial /
# legislative constraints and accountability. BTI is a biennial
# supporting methodology with weaker temporal fit (it covers a
# two-year window), so it carries the lowest weight.

_GROUP_WEIGHT_WGI: float = 0.45
_GROUP_WEIGHT_VDEM: float = 0.35
_GROUP_WEIGHT_BTI: float = 0.20


# ---------------------------------------------------------------------------
# Group keys — used as the ``component_key`` prefix on the emitted
# :class:`~leaders_db.score.results.ScoreComponent` rows.
# ---------------------------------------------------------------------------

_GROUP_KEY_WGI: str = "wgi_governance"
_GROUP_KEY_VDEM: str = "vdem_governance_accountability"
_GROUP_KEY_BTI: str = "bti_governance"


# ---------------------------------------------------------------------------
# Map from plan ``variable_name`` to its rubric group.
# ---------------------------------------------------------------------------

#: Map from plan ``variable_name`` to its rubric group. Used to
#: bucket each :class:`~leaders_db.score.evidence.EvidenceObservation`
#: into the right rubric group. A variable not in the map is treated
#: as out-of-scope and skipped (the bundle builder scopes each row to
#: the variable's owning source, so unknown variables should not
#: appear; the skip is a defence-in-depth check rather than a happy-
#: path branch).
_GROUP_BY_VARIABLE: dict[str, str] = {
    # WGI governance group — the canonical effectiveness signal.
    # ``government_effectiveness`` and ``rule_of_law`` are REQUIRED;
    # the other 3 are PREFERRED so a missing preferred indicator
    # drops confidence but does not block a score.
    "wgi_voice_and_accountability": _GROUP_KEY_WGI,
    "wgi_political_stability": _GROUP_KEY_WGI,
    "wgi_government_effectiveness": _GROUP_KEY_WGI,
    "wgi_regulatory_quality": _GROUP_KEY_WGI,
    "wgi_rule_of_law": _GROUP_KEY_WGI,
    # V-Dem governance / accountability group — the expert-coded
    # cross-validator. ``v2x_accountability`` is REQUIRED; the
    # other PREFERRED indicators are the legislative / judicial
    # constraints and the multiplicative polyarchy index. The
    # FALLBACK ``vdem_v2x_regime`` keeps the group usable when only
    # the regime classifier is present.
    "vdem_v2x_jucon": _GROUP_KEY_VDEM,
    "vdem_v2xlg_legcon": _GROUP_KEY_VDEM,
    "vdem_v2x_accountability": _GROUP_KEY_VDEM,
    "vdem_v2x_mpi": _GROUP_KEY_VDEM,
    "vdem_v2x_regime": _GROUP_KEY_VDEM,
    # BTI governance group — the biennial supporting methodology.
    # ``bti_governance_index`` is REQUIRED; the PREFERRED
    # ``bti_governance_performance`` is the difficulty-adjusted
    # twin that refines the G composite.
    "bti_governance_index": _GROUP_KEY_BTI,
    "bti_governance_performance": _GROUP_KEY_BTI,
}


#: Map from group key to its weight. The lookup is by group string
#: so the scoring loop can pull the weight without an ``if/elif``
#: chain over the three groups. The values sum to 1.0.
_GROUP_WEIGHTS: dict[str, float] = {
    _GROUP_KEY_WGI: _GROUP_WEIGHT_WGI,
    _GROUP_KEY_VDEM: _GROUP_WEIGHT_VDEM,
    _GROUP_KEY_BTI: _GROUP_WEIGHT_BTI,
}


#: Threshold below which the result is flagged ``SPARSE_DATA``.
#: "Less than half of the plan's expected indicators observed".
#: At or above the threshold, missingness is local (a few fallbacks)
#: and the result does not need an explicit sparse-data flag.
_SPARSE_OBSERVED_RATIO_THRESHOLD: float = 0.5


__all__ = [
    "CATEGORY_KEY",
    "_GROUP_BY_VARIABLE",
    "_GROUP_KEY_BTI",
    "_GROUP_KEY_VDEM",
    "_GROUP_KEY_WGI",
    "_GROUP_WEIGHTS",
    "_GROUP_WEIGHT_BTI",
    "_GROUP_WEIGHT_VDEM",
    "_GROUP_WEIGHT_WGI",
    "_SPARSE_OBSERVED_RATIO_THRESHOLD",
]
