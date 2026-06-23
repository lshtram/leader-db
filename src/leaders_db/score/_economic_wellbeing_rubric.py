"""Economic wellbeing rubric constants.

This module is the **internal** rubric for the economic wellbeing
category scorer (:mod:`leaders_db.score.economic_wellbeing`). It
owns the variables-to-group mapping, the per-group weights, and
the sparse-data threshold so the per-component and per-flag
helpers can read the rubric without re-declaring it. The facade
(:func:`leaders_db.score.economic_wellbeing.score_economic_wellbeing`)
re-exports :data:`CATEGORY_KEY` and :data:`_GROUP_WEIGHTS` so the
rest of the package can refer to the category identifier and the
per-group weights without depending on this private module.

Rubric
------

Three-group weighted-average; group weights sum to 1.0. See
:mod:`leaders_db.score.economic_wellbeing` for the full docstring
that walks a reviewer through the formula end-to-end.

================== =================================================== ==================
Group              Variables                                           Group weight
================== =================================================== ==================
1. WDI per-capita   ``wdi_gdp_per_capita`` (REQUIRED),               0.45
   prosperity group ``wdi_gdp_per_capita_ppp_constant_2017``
                    (REQUIRED),
                    ``wdi_gni_per_capita_atlas`` (PREFERRED) —
                    simple mean of available per-capita prosperity
                    indicators
2. WDI scale /      ``wdi_gdp_current_usd`` (PREFERRED),             0.25
   openness /       ``wdi_gdp_constant_2015_usd`` (PREFERRED),
   investment       ``wdi_exports_pct_gdp`` (FALLBACK),
   group            ``wdi_imports_pct_gdp`` (FALLBACK),
                    ``wdi_fdi_inflows_current_usd`` (FALLBACK),
                    ``wdi_population`` (FALLBACK) — simple mean
                    of available normalized values
3. BTI economic     ``bti_q6_socioeconomic_development``             0.30
   transformation   (PREFERRED),
   group            ``bti_q7_market_competition`` (PREFERRED),
                    ``bti_q11_economic_performance`` (PREFERRED) —
                    simple mean of available BTI economic
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

#: Canonical category identifier for the economic wellbeing scorer. Matches
#: :data:`ECONOMIC_WELLBEING_PLAN.category_key` and one of the 8 categories
#: in requirement §4.
CATEGORY_KEY: str = "economic_wellbeing"


# ---------------------------------------------------------------------------
# Group weights — documented in the facade docstring; do not invent
# different weights in a one-off script.
# ---------------------------------------------------------------------------
#
# Rationale (per the source plan): per-capita prosperity carries the
# strongest direct signal of a country's economic wellbeing
# (GDP / GNI per capita are the canonical "how well-off is the average
# citizen" indicators). The WDI scale / openness / investment group
# captures market size, openness to trade, and foreign-investment
# attractiveness — supporting signals that complement the per-capita
# view. BTI is the expert-coded cross-validator (Q6 socioeconomic
# development, Q7 market competition, Q11 economic performance),
# at a slightly lower weight than the per-capita group because it is
# a biennial methodology with weaker temporal fit.

_GROUP_WEIGHT_PER_CAPITA: float = 0.45
_GROUP_WEIGHT_SCALE: float = 0.25
_GROUP_WEIGHT_BTI: float = 0.30


# ---------------------------------------------------------------------------
# Group keys — used as the ``component_key`` prefix on the emitted
# :class:`~leaders_db.score.results.ScoreComponent` rows.
# ---------------------------------------------------------------------------

_GROUP_KEY_PER_CAPITA: str = "wdi_per_capita_prosperity"
_GROUP_KEY_SCALE: str = "wdi_scale_openness_investment"
_GROUP_KEY_BTI: str = "bti_economic_transformation"


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
    # WDI per-capita prosperity group — the canonical economic
    # wellbeing signal. ``wdi_gdp_per_capita`` and
    # ``wdi_gdp_per_capita_ppp_constant_2017`` are REQUIRED;
    # ``wdi_gni_per_capita_atlas`` is PREFERRED.
    "wdi_gdp_per_capita": _GROUP_KEY_PER_CAPITA,
    "wdi_gdp_per_capita_ppp_constant_2017": _GROUP_KEY_PER_CAPITA,
    "wdi_gni_per_capita_atlas": _GROUP_KEY_PER_CAPITA,
    # WDI scale / openness / investment group — the supporting
    # market-size / trade / FDI signal. All entries are
    # PREFERRED or FALLBACK so a missing indicator drops
    # confidence but does not block a score.
    "wdi_gdp_current_usd": _GROUP_KEY_SCALE,
    "wdi_gdp_constant_2015_usd": _GROUP_KEY_SCALE,
    "wdi_exports_pct_gdp": _GROUP_KEY_SCALE,
    "wdi_imports_pct_gdp": _GROUP_KEY_SCALE,
    "wdi_fdi_inflows_current_usd": _GROUP_KEY_SCALE,
    "wdi_population": _GROUP_KEY_SCALE,
    # BTI economic transformation group — the biennial expert-coded
    # cross-validator. All three economic questions are PREFERRED.
    "bti_q6_socioeconomic_development": _GROUP_KEY_BTI,
    "bti_q7_market_competition": _GROUP_KEY_BTI,
    "bti_q11_economic_performance": _GROUP_KEY_BTI,
}


#: Map from group key to its weight. The lookup is by group string
#: so the scoring loop can pull the weight without an ``if/elif``
#: chain over the three groups. The values sum to 1.0.
_GROUP_WEIGHTS: dict[str, float] = {
    _GROUP_KEY_PER_CAPITA: _GROUP_WEIGHT_PER_CAPITA,
    _GROUP_KEY_SCALE: _GROUP_WEIGHT_SCALE,
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
    "_GROUP_KEY_PER_CAPITA",
    "_GROUP_KEY_SCALE",
    "_GROUP_WEIGHTS",
    "_GROUP_WEIGHT_BTI",
    "_GROUP_WEIGHT_PER_CAPITA",
    "_GROUP_WEIGHT_SCALE",
    "_SPARSE_OBSERVED_RATIO_THRESHOLD",
]
