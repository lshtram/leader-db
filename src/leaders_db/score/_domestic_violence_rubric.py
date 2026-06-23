"""Domestic violence / repression rubric constants.

This module is the **internal** rubric for the
``domestic_violence`` category scorer
(:mod:`leaders_db.score.domestic_violence`). It owns the
variables-to-group mapping, the per-group weights, and the
sparse-data threshold so the per-component and per-flag
helpers can read the rubric without re-declaring it. The facade
(:func:`leaders_db.score.domestic_violence.score_domestic_violence`)
re-exports :data:`CATEGORY_KEY` and :data:`_GROUP_WEIGHTS` so the
rest of the package can refer to the category identifier and the
per-group weights without depending on this private module.

Rubric
------

Four-group weighted-average; group weights sum to 1.0. See
:mod:`leaders_db.score.domestic_violence` for the full docstring
that walks a reviewer through the formula end-to-end.

================== =================================================== ==================
Group              Variables                                           Group weight
================== =================================================== ==================
1. PTS             ``pts_amnesty_score`` (REQUIRED),                   0.30
   state-terror     ``pts_human_rights_watch_score`` (PREFERRED),
   group            ``pts_state_dept_score`` (PREFERRED) — simple
                    mean of available PTS parallel scores
2. CIRIGHTS        ``cirights_physint`` (REQUIRED),                    0.35
   physical-        ``cirights_repression`` (PREFERRED),
   integrity /      ``cirights_civpol`` (FALLBACK),
   repression       ``cirights_disap`` (PREFERRED),
   group            ``cirights_kill`` (PREFERRED),
                    ``cirights_polpris`` (PREFERRED),
                    ``cirights_tort`` (PREFERRED) — simple mean
                    of available CIRIGHTS physical-integrity /
                    repression indicators
3. UCDP            ``ucdp_onesided_events`` (PREFERRED),              0.20
   one-sided        ``ucdp_onesided_fatalities`` (PREFERRED) —
   violence         simple mean of available UCDP one-sided
   group            violence indicators
4. V-Dem           ``vdem_v2x_clphy`` (PREFERRED),                     0.15
   civil-liberties  ``vdem_v2x_clpol`` (FALLBACK),
   / repression     ``vdem_v2x_clpriv`` (FALLBACK),
   cross-check      ``vdem_v2csreprss`` (FALLBACK),
   group            ``vdem_v2clkill`` (FALLBACK) — simple mean
                    of available V-Dem physical-violence /
                    civil-liberties / repression indicators
================== =================================================== ==================

The 0.30 / 0.35 / 0.20 / 0.15 split reflects the strength of the
direct domestic-violence signal each source carries: CIRIGHTS
physical-integrity indicators are the strongest single signal
(7 indicators covering disappearances, extrajudicial killings,
political imprisonment, torture, plus the additive PhysInt and
broader repression / civpol indices); PTS state-terror scores are
the expert-coded cross-validator (3 parallel scores from
Amnesty / HRW / US State Department); UCDP one-sided violence is
the event-based cross-validator (2 indicators: events +
fatalities); V-Dem civil-liberties / repression indicators are
the 4th-source cross-check (5 indicators: 3 liberties + 2
repression point estimates).

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

#: Canonical category identifier for the domestic-violence scorer.
#: Matches :data:`DOMESTIC_VIOLENCE_PLAN.category_key` and one of the
#: 8 categories in requirement §4.
CATEGORY_KEY: str = "domestic_violence"


# ---------------------------------------------------------------------------
# Group weights — documented in the facade docstring; do not invent
# different weights in a one-off script.
# ---------------------------------------------------------------------------
#
# Rationale (per the source plan): CIRIGHTS physical-integrity
# indices (PhysInt + the 4 component indices Disap / Kill /
# PolPris / Tort + the Repression and CivPol additive indices)
# are the strongest single direct signal of domestic violence /
# repression, so the group carries the heaviest weight (0.35).
# PTS state-terror scores (the 3 parallel Amnesty / HRW / US
# State Department scores) are the canonical expert-coded
# cross-validator (0.30). UCDP one-sided violence is the
# event-based cross-validator (0.20). V-Dem civil-liberties /
# repression indicators are the 4th-source cross-check (0.15).

_GROUP_WEIGHT_PTS: float = 0.30
_GROUP_WEIGHT_CIRIGHTS: float = 0.35
_GROUP_WEIGHT_UCDP: float = 0.20
_GROUP_WEIGHT_VDEM: float = 0.15


# ---------------------------------------------------------------------------
# Group keys — used as the ``component_key`` prefix on the emitted
# :class:`~leaders_db.score.results.ScoreComponent` rows.
# ---------------------------------------------------------------------------

_GROUP_KEY_PTS: str = "pts_state_terror"
_GROUP_KEY_CIRIGHTS: str = "cirights_physint_repression"
_GROUP_KEY_UCDP: str = "ucdp_one_sided_violence"
_GROUP_KEY_VDEM: str = "vdem_civil_liberties_repression"


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
    # PTS state-terror group — the 3 parallel expert-coded
    # scores from Amnesty / HRW / US State Department. The
    # REQUIRED is Amnesty (the longest-running); the 2
    # PREFERRED cross-validate.
    "pts_amnesty_score": _GROUP_KEY_PTS,
    "pts_human_rights_watch_score": _GROUP_KEY_PTS,
    "pts_state_dept_score": _GROUP_KEY_PTS,
    # CIRIGHTS physical-integrity / repression group — the 7
    # CIRIGHTS indicators: the REQUIRED Physical Integrity
    # Rights Index plus 3 PREFERRED components (Repression
    # Index, Disappearances, Extrajudicial Killings,
    # Political Imprisonment, Torture) and the FALLBACK
    # Civil and Political Rights Index. These are the
    # strongest single signal so they carry the heaviest
    # weight (0.35).
    "cirights_physint": _GROUP_KEY_CIRIGHTS,
    "cirights_repression": _GROUP_KEY_CIRIGHTS,
    "cirights_civpol": _GROUP_KEY_CIRIGHTS,
    "cirights_disap": _GROUP_KEY_CIRIGHTS,
    "cirights_kill": _GROUP_KEY_CIRIGHTS,
    "cirights_polpris": _GROUP_KEY_CIRIGHTS,
    "cirights_tort": _GROUP_KEY_CIRIGHTS,
    # UCDP one-sided violence group — the 2 PREFERRED
    # event-based indicators (event count + total deaths)
    # aggregating ``type_of_violence == 3`` rows from UCDP
    # GED. The group is the event-based cross-validator
    # (0.20).
    "ucdp_onesided_events": _GROUP_KEY_UCDP,
    "ucdp_onesided_fatalities": _GROUP_KEY_UCDP,
    # V-Dem civil-liberties / repression group — the 3
    # HIGHER_IS_BETTER liberties (Physical Violence,
    # Political Civil Liberties, Private Civil Liberties)
    # plus the 2 LOWER_IS_BETTER repression point estimates
    # (CSO Repression, Political Killings). The 4th-source
    # cross-check (0.15).
    "vdem_v2x_clphy": _GROUP_KEY_VDEM,
    "vdem_v2x_clpol": _GROUP_KEY_VDEM,
    "vdem_v2x_clpriv": _GROUP_KEY_VDEM,
    "vdem_v2csreprss": _GROUP_KEY_VDEM,
    "vdem_v2clkill": _GROUP_KEY_VDEM,
}


#: Map from group key to its weight. The lookup is by group string
#: so the scoring loop can pull the weight without an ``if/elif``
#: chain over the four groups. The values sum to 1.0.
_GROUP_WEIGHTS: dict[str, float] = {
    _GROUP_KEY_PTS: _GROUP_WEIGHT_PTS,
    _GROUP_KEY_CIRIGHTS: _GROUP_WEIGHT_CIRIGHTS,
    _GROUP_KEY_UCDP: _GROUP_WEIGHT_UCDP,
    _GROUP_KEY_VDEM: _GROUP_WEIGHT_VDEM,
}


#: Threshold below which the result is flagged ``SPARSE_DATA``.
#: "Less than half of the plan's expected indicators observed".
#: At or above the threshold, missingness is local (a few fallbacks)
#: and the result does not need an explicit sparse-data flag.
_SPARSE_OBSERVED_RATIO_THRESHOLD: float = 0.5


__all__ = [
    "CATEGORY_KEY",
    "_GROUP_BY_VARIABLE",
    "_GROUP_KEY_CIRIGHTS",
    "_GROUP_KEY_PTS",
    "_GROUP_KEY_UCDP",
    "_GROUP_KEY_VDEM",
    "_GROUP_WEIGHTS",
    "_GROUP_WEIGHT_CIRIGHTS",
    "_GROUP_WEIGHT_PTS",
    "_GROUP_WEIGHT_UCDP",
    "_GROUP_WEIGHT_VDEM",
    "_SPARSE_OBSERVED_RATIO_THRESHOLD",
]
