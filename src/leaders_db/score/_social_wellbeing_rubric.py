"""Social-wellbeing rubric constants.

This module is the **internal** rubric for the social-wellbeing
category scorer (:mod:`leaders_db.score.social_wellbeing`). It owns
the variables-to-group mapping, the per-group weights, and the
sparse-data threshold so the per-component and per-flag helpers can
read the rubric without re-declaring it.

The facade (:func:`leaders_db.score.social_wellbeing.score_social_wellbeing`)
re-exports :data:`CATEGORY_KEY` so the rest of the package can refer
to the category identifier without depending on this private module.

Rubric
------

Five-group weighted-average; group weights sum to 1.0. See
:mod:`leaders_db.score.social_wellbeing` for the full docstring
that walks a reviewer through the formula end-to-end.

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

#: Canonical category identifier for the social-wellbeing scorer.
#: Matches :data:`SOCIAL_WELLBEING_PLAN.category_key` and one of the 8
#: categories in requirement §4.
CATEGORY_KEY: str = "social_wellbeing"


# ---------------------------------------------------------------------------
# Group weights — documented in the facade docstring; do not invent different
# weights in a one-off script.
# ---------------------------------------------------------------------------

_GROUP_WEIGHT_HDI: float = 0.40
_GROUP_WEIGHT_HEALTH: float = 0.20
_GROUP_WEIGHT_EDUCATION: float = 0.15
_GROUP_WEIGHT_INCOME: float = 0.15
_GROUP_WEIGHT_INEQUALITY: float = 0.10


# ---------------------------------------------------------------------------
# Group keys — used as the ``component_key`` prefix on the emitted
# :class:`~leaders_db.score.results.ScoreComponent` rows.
# ---------------------------------------------------------------------------

_GROUP_KEY_HDI: str = "hdi_anchor"
_GROUP_KEY_HEALTH: str = "health_signal"
_GROUP_KEY_EDUCATION: str = "education_signal"
_GROUP_KEY_INCOME: str = "income_signal"
_GROUP_KEY_INEQUALITY: str = "inequality_signal"


# ---------------------------------------------------------------------------
# Map from plan ``variable_name`` to its group.
# ---------------------------------------------------------------------------

#: Map from plan ``variable_name`` to its rubric group. Used to
 #: bucket each :class:`~leaders_db.score.evidence.EvidenceObservation`
 #: into the right rubric group. A variable not in the map is treated
 #: as out-of-scope and skipped (the bundle builder scopes each row to
 #: the variable's owning source, so unknown variables should not
 #: appear; the skip is a defence-in-depth check rather than a happy-
 #: path branch).
_GROUP_BY_VARIABLE: dict[str, str] = {
    # HDI composite anchor
    "undp_hdi_hdi": _GROUP_KEY_HDI,
    # Health signal
    "undp_hdi_life_expectancy": _GROUP_KEY_HEALTH,
    "who_gho_life_expectancy": _GROUP_KEY_HEALTH,
    "wdi_life_expectancy_at_birth": _GROUP_KEY_HEALTH,
    "who_gho_under5_mortality": _GROUP_KEY_HEALTH,
    "wdi_under5_mortality_per_1000": _GROUP_KEY_HEALTH,
    "who_gho_dtp3_immunization": _GROUP_KEY_HEALTH,
    "who_gho_hepb3_immunization": _GROUP_KEY_HEALTH,
    "who_gho_bcg_immunization": _GROUP_KEY_HEALTH,
    # Education signal
    "undp_hdi_expected_years_schooling": _GROUP_KEY_EDUCATION,
    "undp_hdi_mean_years_schooling": _GROUP_KEY_EDUCATION,
    "wdi_literacy_rate_adult": _GROUP_KEY_EDUCATION,
    "wdi_secondary_school_enrollment": _GROUP_KEY_EDUCATION,
    # Income / standard-of-living signal
    "undp_hdi_gni_per_capita": _GROUP_KEY_INCOME,
    # Inequality / social protection
    "wdi_gini_index": _GROUP_KEY_INEQUALITY,
    "vdem_v2x_egal": _GROUP_KEY_INEQUALITY,
    "vdem_v2clsocgrp_ord": _GROUP_KEY_INEQUALITY,
}


#: Map from group key to its weight. The lookup is by group string so
 #: the scoring loop can pull the weight without an ``if/elif`` chain
 #: over the five groups.
_GROUP_WEIGHTS: dict[str, float] = {
    _GROUP_KEY_HDI: _GROUP_WEIGHT_HDI,
    _GROUP_KEY_HEALTH: _GROUP_WEIGHT_HEALTH,
    _GROUP_KEY_EDUCATION: _GROUP_WEIGHT_EDUCATION,
    _GROUP_KEY_INCOME: _GROUP_WEIGHT_INCOME,
    _GROUP_KEY_INEQUALITY: _GROUP_WEIGHT_INEQUALITY,
}


#: Threshold below which the result is flagged ``SPARSE_DATA``.
#: "Less than half of the plan's expected indicators observed".
#: At or above the threshold, missingness is local (a few fallbacks)
#: and the result does not need an explicit sparse-data flag.
_SPARSE_OBSERVED_RATIO_THRESHOLD: float = 0.5


__all__ = [
 "CATEGORY_KEY",
 "_GROUP_BY_VARIABLE",
 "_GROUP_KEY_EDUCATION",
 "_GROUP_KEY_HDI",
 "_GROUP_KEY_HEALTH",
 "_GROUP_KEY_INCOME",
 "_GROUP_KEY_INEQUALITY",
 "_GROUP_WEIGHTS",
 "_GROUP_WEIGHT_EDUCATION",
 "_GROUP_WEIGHT_HDI",
 "_GROUP_WEIGHT_HEALTH",
 "_GROUP_WEIGHT_INCOME",
 "_GROUP_WEIGHT_INEQUALITY",
 "_SPARSE_OBSERVED_RATIO_THRESHOLD",
]
