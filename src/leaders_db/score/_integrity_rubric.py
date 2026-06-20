"""Integrity rubric constants.

This module is the **internal** rubric for the integrity category
scorer (:mod:`leaders_db.score.integrity`). It owns the
variables-to-group mapping, the per-group weights, and the
sparse-data threshold so the per-component and per-flag helpers
can read the rubric without re-declaring it. The facade
(:func:`leaders_db.score.integrity.score_integrity`) re-exports
:data:`CATEGORY_KEY` and :data:`_GROUP_WEIGHTS` so the rest of the
package can refer to the category identifier and the per-group
weights without depending on this private module.

Rubric
------

Three-group weighted-average; group weights sum to 1.0. See
:mod:`leaders_db.score.integrity` for the full docstring that
walks a reviewer through the formula end-to-end.

================== =================================================== ==================
Group              Variables                                           Group weight
================== =================================================== ==================
1. WGI control of  ``wgi_control_of_corruption`` (REQUIRED)            0.35
   corruption
2. V-Dem           ``vdem_v2x_corr`` (REQUIRED), ``vdem_v2x_execorr``   0.35
   corruption      (PREFERRED), ``vdem_v2x_pubcorr`` (PREFERRED) —
   composite        simple mean of available indicators
3. Transparency    ``cpi_score`` (REQUIRED)                            0.30
   International
   CPI
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

#: Canonical category identifier for the integrity scorer. Matches
#: :data:`INTEGRITY_PLAN.category_key` and one of the 8 categories
#: in requirement §4.
CATEGORY_KEY: str = "integrity"


# ---------------------------------------------------------------------------
# Group weights — documented in the facade docstring; do not invent
# different weights in a one-off script.
# ---------------------------------------------------------------------------

_GROUP_WEIGHT_WGI: float = 0.35
_GROUP_WEIGHT_VDEM: float = 0.35
_GROUP_WEIGHT_CPI: float = 0.30


# ---------------------------------------------------------------------------
# Group keys — used as the ``component_key`` prefix on the emitted
# :class:`~leaders_db.score.results.ScoreComponent` rows.
# ---------------------------------------------------------------------------

_GROUP_KEY_WGI: str = "wgi_control_of_corruption"
_GROUP_KEY_VDEM: str = "vdem_corruption_composite"
_GROUP_KEY_CPI: str = "ti_cpi"


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
    # WGI Control of Corruption — the canonical integrity signal.
    "wgi_control_of_corruption": _GROUP_KEY_WGI,
    # V-Dem political-corruption indices — the expert-coded
    # cross-validator. ``v2x_corr`` is REQUIRED; ``v2x_execorr`` and
    # ``v2x_pubcorr`` are PREFERRED so a missing preferred indicator
    # drops confidence but does not block a score.
    "vdem_v2x_corr": _GROUP_KEY_VDEM,
    "vdem_v2x_execorr": _GROUP_KEY_VDEM,
    "vdem_v2x_pubcorr": _GROUP_KEY_VDEM,
    # Transparency International CPI — the perception-based
    # cross-validator.
    "cpi_score": _GROUP_KEY_CPI,
}


#: Map from group key to its weight. The lookup is by group string
#: so the scoring loop can pull the weight without an ``if/elif``
#: chain over the three groups. The values sum to 1.0.
_GROUP_WEIGHTS: dict[str, float] = {
    _GROUP_KEY_WGI: _GROUP_WEIGHT_WGI,
    _GROUP_KEY_VDEM: _GROUP_WEIGHT_VDEM,
    _GROUP_KEY_CPI: _GROUP_WEIGHT_CPI,
}


#: Threshold below which the result is flagged ``SPARSE_DATA``.
#: "Less than half of the plan's expected indicators observed".
#: At or above the threshold, missingness is local (a few fallbacks)
#: and the result does not need an explicit sparse-data flag.
_SPARSE_OBSERVED_RATIO_THRESHOLD: float = 0.5


__all__ = [
    "CATEGORY_KEY",
    "_GROUP_BY_VARIABLE",
    "_GROUP_KEY_CPI",
    "_GROUP_KEY_VDEM",
    "_GROUP_KEY_WGI",
    "_GROUP_WEIGHTS",
    "_GROUP_WEIGHT_CPI",
    "_GROUP_WEIGHT_VDEM",
    "_GROUP_WEIGHT_WGI",
    "_SPARSE_OBSERVED_RATIO_THRESHOLD",
]
