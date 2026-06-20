"""International peace rubric constants.

This module is the **internal** rubric for the
``international_peace`` category scorer
(:mod:`leaders_db.score.international_peace`). It owns the
variables-to-group mapping, the per-group weights, and the
sparse-data threshold so the per-component and per-flag helpers
can read the rubric without re-declaring it. The facade
(:func:`leaders_db.score.international_peace.score_international_peace`)
re-exports :data:`CATEGORY_KEY` and :data:`_GROUP_WEIGHTS` so
the rest of the package can refer to the category identifier
and the per-group weights without depending on this private
module.

Rubric
------

Two-group weighted-average; group weights sum to 1.0. See
:mod:`leaders_db.score.international_peace` for the full
docstring that walks a reviewer through the formula end-to-end.

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

The 0.65 / 0.35 split reflects the strength of the direct
international-conflict signal each source carries: UCDP
state-based + internationalized events / fatalities is the
direct event-based methodology (the strongest single signal of
"international aggression / war" — 4 indicators aggregating
the UCDP GED dataset); SIPRI Military Expenditure is the
expenditure-based cross-validator (4 share / scale indicators
that catch the "military build-up" signal even in years where
no event-based conflict is observed).

All 8 ``INTERNATIONAL_PEACE_PLAN`` indicators are
``LOWER_IS_BETTER`` in raw form: more conflict / more military
spending = worse peace signal. Stage 6 normalization inverts
the raw values to the 0..1 high-is-better scale so the scorer
consumes a single 0..1 scale where 1 is "best" (i.e. more
peace / less military burden).

Style invariants (per ``docs/coding-guidelines.md``):

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

#: Canonical category identifier for the international-peace scorer.
#: Matches :data:`INTERNATIONAL_PEACE_PLAN.category_key` and one of the
#: 8 categories in requirement §4.
CATEGORY_KEY: str = "international_peace"


# ---------------------------------------------------------------------------
# Group weights — documented in the facade docstring; do not invent
# different weights in a one-off script.
# ---------------------------------------------------------------------------
#
# Rationale (per the source plan): UCDP state-based + UCDP
# internationalized events / fatalities is the direct event-based
# methodology (the strongest single signal of "international
# aggression / war"), so it carries the heaviest weight (0.65).
# SIPRI Military Expenditure is the expenditure-based
# cross-validator (0.35).

_GROUP_WEIGHT_UCDP: float = 0.65
_GROUP_WEIGHT_SIPRI: float = 0.35


# ---------------------------------------------------------------------------
# Group keys — used as the ``component_key`` prefix on the emitted
# :class:`~leaders_db.score.results.ScoreComponent` rows.
# ---------------------------------------------------------------------------

_GROUP_KEY_UCDP: str = "ucdp_conflict_involvement"
_GROUP_KEY_SIPRI: str = "sipri_military_expenditure"


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
    # UCDP conflict involvement group — the 4 event-based
    # indicators (state-based events + fatalities plus the
    # internationalized cross-border subset). The REQUIRED
    # ``ucdp_state_based_fatalities`` anchors the group; the 3
    # PREFERRED indicators (``ucdp_state_based_events``,
    # ``ucdp_intl_events``, ``ucdp_intl_fatalities``) fill in the
    # event-count and cross-border subdimensions. All 4 are
    # LOWER_IS_BETTER in raw form (more deaths = worse); Stage 6
    # inverts so the scorer sees 1 = best. This group is the
    # event-based cross-validator (0.65).
    "ucdp_state_based_events": _GROUP_KEY_UCDP,
    "ucdp_state_based_fatalities": _GROUP_KEY_UCDP,
    "ucdp_intl_events": _GROUP_KEY_UCDP,
    "ucdp_intl_fatalities": _GROUP_KEY_UCDP,
    # SIPRI Military Expenditure group — the 4 share / scale
    # indicators (share of GDP, per capita, constant USD, share
    # of govt spending). The PREFERRED ``sipri_milex_share_of_gdp``
    # is the canonical "military burden" metric; the 3 FALLBACK
    # indicators fill in the per-capita / scale / share-of-budget
    # subdimensions. All 4 are LOWER_IS_BETTER in raw form (more
    # spending = worse); Stage 6 inverts so the scorer sees
    # 1 = best. This group is the expenditure-based
    # cross-validator (0.35).
    "sipri_milex_share_of_gdp": _GROUP_KEY_SIPRI,
    "sipri_milex_per_capita": _GROUP_KEY_SIPRI,
    "sipri_milex_constant_usd": _GROUP_KEY_SIPRI,
    "sipri_milex_share_of_govt_spending": _GROUP_KEY_SIPRI,
}


#: Map from group key to its weight. The lookup is by group string
#: so the scoring loop can pull the weight without an ``if/elif``
#: chain over the two groups. The values sum to 1.0.
_GROUP_WEIGHTS: dict[str, float] = {
    _GROUP_KEY_UCDP: _GROUP_WEIGHT_UCDP,
    _GROUP_KEY_SIPRI: _GROUP_WEIGHT_SIPRI,
}


#: Threshold below which the result is flagged ``SPARSE_DATA``.
#: "Less than half of the plan's expected indicators observed".
#: At or above the threshold, missingness is local (a few fallbacks)
#: and the result does not need an explicit sparse-data flag.
_SPARSE_OBSERVED_RATIO_THRESHOLD: float = 0.5


__all__ = [
    "CATEGORY_KEY",
    "_GROUP_BY_VARIABLE",
    "_GROUP_KEY_SIPRI",
    "_GROUP_KEY_UCDP",
    "_GROUP_WEIGHTS",
    "_GROUP_WEIGHT_SIPRI",
    "_GROUP_WEIGHT_UCDP",
    "_SPARSE_OBSERVED_RATIO_THRESHOLD",
]
