"""Political freedom rubric constants.

This module is the **internal** rubric for the political
freedom category scorer (:mod:`leaders_db.score.political_freedom`).
It owns the variables-to-group mapping, the per-group weights,
and the sparse-data threshold so the per-component and per-flag
helpers can read the rubric without re-declaring it. The facade
(:func:`leaders_db.score.political_freedom.score_political_freedom`)
re-exports :data:`CATEGORY_KEY` and :data:`_GROUP_WEIGHTS` so the
rest of the package can refer to the category identifier and the
per-group weights without depending on this private module.

Rubric
------

Three-group weighted-average; group weights sum to 1.0. See
:mod:`leaders_db.score.political_freedom` for the full docstring
that walks a reviewer through the formula end-to-end.

================== =================================================== ==================
Group              Variables                                           Group weight
================== =================================================== ==================
1. V-Dem           ``vdem_v2x_polyarchy`` (REQUIRED),                 0.50
   democratic /    ``vdem_v2x_libdem`` (REQUIRED),
   liberal /       ``vdem_v2x_freexp`` (PREFERRED),
   civil-liberties ``vdem_v2x_frassoc_thick`` (PREFERRED),
   group           ``vdem_v2x_suffr`` (PREFERRED),
                   ``vdem_v2x_rule`` (PREFERRED),
                   ``vdem_v2x_civlib`` (PREFERRED) — simple
                   mean of available V-Dem polyarchy / liberal /
                   civil-liberties indicators
2. BTI political   ``bti_status_index`` (PREFERRED),                  0.30
   transformation  ``bti_democracy_status`` (PREFERRED),
   group           ``bti_q1_stateness`` (FALLBACK),
                   ``bti_q2_political_participation`` (FALLBACK),
                   ``bti_q3_rule_of_law`` (FALLBACK),
                   ``bti_q4_democratic_institutions`` (FALLBACK),
                   ``bti_q5_political_social_integration``
                   (FALLBACK) — simple mean of available BTI
                   political-transformation composites
3. RSF press-      ``rsf_press_freedom_score`` (PREFERRED),           0.20
   freedom group   ``rsf_press_freedom_political_context``
                   (FALLBACK) — simple mean of available RSF
                   press-freedom indicators
================== =================================================== ==================

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

#: Canonical category identifier for the political freedom scorer. Matches
#: :data:`POLITICAL_FREEDOM_PLAN.category_key` and one of the 8 categories
#: in requirement §4.
CATEGORY_KEY: str = "political_freedom"


# ---------------------------------------------------------------------------
# Group weights — documented in the facade docstring; do not invent
# different weights in a one-off script.
# ---------------------------------------------------------------------------
#
# Rationale (per the source plan): the V-Dem polyarchy / liberal
# democracy / civil-liberties family is the strongest direct
# signal of "political freedom vs authoritarian rule" — the
# 7-indicator family is the V-Dem v16 canonical multi-dimensional
# democracy composite, so it carries the heaviest weight (0.50).
# BTI 2026 political-transformation composites cross-validate
# with the biennial expert-coded methodology (0.30). RSF
# press-freedom is the press / media-freedom sub-signal — a
# important but narrower dimension of political freedom (0.20).

_GROUP_WEIGHT_VDEM: float = 0.50
_GROUP_WEIGHT_BTI: float = 0.30
_GROUP_WEIGHT_RSF: float = 0.20


# ---------------------------------------------------------------------------
# Group keys — used as the ``component_key`` prefix on the emitted
# :class:`~leaders_db.score.results.ScoreComponent` rows.
# ---------------------------------------------------------------------------

_GROUP_KEY_VDEM: str = "vdem_democracy_liberty"
_GROUP_KEY_BTI: str = "bti_political_transformation"
_GROUP_KEY_RSF: str = "rsf_press_freedom"


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
    # V-Dem democratic / liberal / civil-liberties group — the
    # canonical political-freedom signal. ``vdem_v2x_polyarchy``
    # and ``vdem_v2x_libdem`` are REQUIRED; the other 5
    # PREFERRED indicators fill in the electoral / associational
    # / suffrage / rule-of-law / civil-liberties subdimensions.
    "vdem_v2x_polyarchy": _GROUP_KEY_VDEM,
    "vdem_v2x_libdem": _GROUP_KEY_VDEM,
    "vdem_v2x_freexp": _GROUP_KEY_VDEM,
    "vdem_v2x_frassoc_thick": _GROUP_KEY_VDEM,
    "vdem_v2x_suffr": _GROUP_KEY_VDEM,
    "vdem_v2x_rule": _GROUP_KEY_VDEM,
    "vdem_v2x_civlib": _GROUP_KEY_VDEM,
    # BTI political-transformation group — the biennial expert-
    # coded cross-validator. The two PREFERRED composites
    # (status_index, democracy_status) plus the five FALLBACK
    # political-transformation questions (Q1 stateness through
    # Q5 political/social integration).
    "bti_status_index": _GROUP_KEY_BTI,
    "bti_democracy_status": _GROUP_KEY_BTI,
    "bti_q1_stateness": _GROUP_KEY_BTI,
    "bti_q2_political_participation": _GROUP_KEY_BTI,
    "bti_q3_rule_of_law": _GROUP_KEY_BTI,
    "bti_q4_democratic_institutions": _GROUP_KEY_BTI,
    "bti_q5_political_social_integration": _GROUP_KEY_BTI,
    # RSF press-freedom group — the press / media-freedom
    # sub-signal. The PREFERRED headline score plus the FALLBACK
    # political-context component.
    "rsf_press_freedom_score": _GROUP_KEY_RSF,
    "rsf_press_freedom_political_context": _GROUP_KEY_RSF,
}


#: Map from group key to its weight. The lookup is by group string
#: so the scoring loop can pull the weight without an ``if/elif``
#: chain over the three groups. The values sum to 1.0.
_GROUP_WEIGHTS: dict[str, float] = {
    _GROUP_KEY_VDEM: _GROUP_WEIGHT_VDEM,
    _GROUP_KEY_BTI: _GROUP_WEIGHT_BTI,
    _GROUP_KEY_RSF: _GROUP_WEIGHT_RSF,
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
    "_GROUP_KEY_RSF",
    "_GROUP_KEY_VDEM",
    "_GROUP_WEIGHTS",
    "_GROUP_WEIGHT_BTI",
    "_GROUP_WEIGHT_RSF",
    "_GROUP_WEIGHT_VDEM",
    "_SPARSE_OBSERVED_RATIO_THRESHOLD",
]
