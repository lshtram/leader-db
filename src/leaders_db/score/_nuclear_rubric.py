"""Nuclear / global responsibility rubric constants.

This module is the **internal** rubric for the ``nuclear`` category
scorer (:mod:`leaders_db.score.nuclear`). It owns the
variables-to-group mapping, the per-group weights, and the
sparse-data threshold so the per-component and per-flag helpers
can read the rubric without re-declaring it. The facade
(:func:`leaders_db.score.nuclear.score_nuclear`) re-exports
:data:`CATEGORY_KEY` and :data:`_GROUP_WEIGHTS` so the rest of
the package can refer to the category identifier and the
per-group weights without depending on this private module.

Rubric
------

Two-group weighted-average; group weights sum to 1.0. See
:mod:`leaders_db.score.nuclear` for the full docstring that walks
a reviewer through the formula end-to-end.

================== =================================================== ==================
Group              Variables                                           Group weight
================== =================================================== ==================
1. FAS nuclear     ``fas_operational_strategic`` (PREFERRED),         0.60
   forces group     ``fas_operational_nonstrategic`` (FALLBACK),
                    ``fas_reserve_nondeployed`` (FALLBACK),
                    ``fas_military_stockpile`` (PREFERRED),
                    ``fas_total_inventory`` (REQUIRED) — simple
                    mean of available FAS indicators
2. SIPRI           ``sipri_yearbook_ch7_nuclear_warheads_             0.40
   Yearbook Ch.7    total_inventory`` (REQUIRED),
   nuclear forces   ``sipri_yearbook_ch7_nuclear_warheads_             deployed``
   group            (PREFERRED),
                    ``sipri_yearbook_ch7_nuclear_warheads_             retired``
                    (FALLBACK) — simple mean of available SIPRI
                    Yearbook Ch.7 indicators
================== =================================================== ==================

The 0.60 / 0.40 split reflects the strength of the direct
nuclear-arsenal signal each source carries: the FAS consolidated
"Status of World Nuclear Forces" snapshot is the canonical
nuclear-arsenal table for the ~9 nuclear-armed states (5
indicators: Operational Strategic, Operational Nonstrategic,
Reserve/Nondeployed, Military Stockpile, Total Inventory); SIPRI
Yearbook Chapter 7 Table 7.1 is the independent cross-validation
(3 indicators: Total Inventory, Deployed, Retired). Per
requirement §6 the nuclear module is a **lighter** module than
the 4-group / 3-group / 2-group categories because most countries
are non-nuclear and because global responsibility requires
judgment beyond raw data.

All 5 FAS indicators are LOWER_IS_BETTER in raw form (more
warheads = bigger arsenal = more nuclear capability / risk); SIPRI
Yearbook Ch.7's ``total_inventory`` and ``deployed`` are also
LOWER_IS_BETTER. The SIPRI ``retired`` indicator is
HIGHER_IS_BETTER (more retired warheads = more disarmament
activity = better peace signal per the SIPRI catalog header).
Stage 6 normalization handles ``LOWER_IS_BETTER`` direction
inversion so the scorer consumes a single 0..1 scale where 1 is
"best" (i.e. less nuclear capability / more disarmament progress).

Non-nuclear states
------------------

Most countries are non-nuclear and have no FAS / SIPRI Yearbook
Ch.7 row at all (the consolidated FAS snapshot and the SIPRI
Yearbook Ch.7 PDF cover the ~9 nuclear-armed states only). The
scorer therefore explicitly handles two population groups:

- **Nuclear-armed countries with usable observations** emit a
  numeric ``system_proposed_score_1_10`` via the
  group-weighted-average formula below. The result carries
  :attr:`ReviewFlag.NUCLEAR_CASE` so the manual-review queue
  can prioritize the row per REQ-REV-002 ("nuclear / global
  responsibility cases").
- **Non-nuclear states / no usable nuclear-source evidence**
  emit no numeric score; the result is
  ``is_insufficient_data=True`` with both scores ``None`` and
  the rationale saying no nuclear-source evidence was found
  (so a non-nuclear state never receives an invented numeric
  score). This is the requirement §13 / "no invented historical
  data" / REQ-HIST-002 spirit called out in the source-plan
  docstring.

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

#: Canonical category identifier for the nuclear scorer. Matches
#: :data:`NUCLEAR_PLAN.category_key` and one of the 8 categories in
#: requirement §4.
CATEGORY_KEY: str = "nuclear"


# ---------------------------------------------------------------------------
# Group weights — documented in the facade docstring; do not invent
# different weights in a one-off script.
# ---------------------------------------------------------------------------
#
# Rationale (per the source plan): the FAS consolidated "Status of
# World Nuclear Forces" snapshot is the canonical nuclear-arsenal
# table for the ~9 nuclear-armed states (5 indicators) so it carries
# the heaviest weight (0.60). SIPRI Yearbook Ch.7 Table 7.1 is the
# independent cross-validator (3 indicators) at 0.40.

_GROUP_WEIGHT_FAS: float = 0.60
_GROUP_WEIGHT_SIPRI: float = 0.40


# ---------------------------------------------------------------------------
# Group keys — used as the ``component_key`` prefix on the emitted
# :class:`~leaders_db.score.results.ScoreComponent` rows.
# ---------------------------------------------------------------------------

_GROUP_KEY_FAS: str = "fas_nuclear_forces"
_GROUP_KEY_SIPRI: str = "sipri_yearbook_ch7_nuclear_forces"


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
    # FAS nuclear forces group — the 5 consolidated-status-page
    # indicators (Operational Strategic, Operational Nonstrategic,
    # Reserve/Nondeployed, Military Stockpile, Total Inventory).
    # The REQUIRED ``fas_total_inventory`` anchors the group; the
    # 4 PREFERRED / FALLBACK indicators fill in the
    # strategic-vs-nonstrategic / stockpile-vs-reserve sub-
    # dimensions. All 5 are LOWER_IS_BETTER in raw form (more
    # warheads = bigger arsenal = more nuclear capability / risk);
    # Stage 6 inverts so the scorer sees 1 = best (less nuclear
    # capability). This group is the canonical nuclear-arsenal
    # signal (0.60).
    "fas_operational_strategic": _GROUP_KEY_FAS,
    "fas_operational_nonstrategic": _GROUP_KEY_FAS,
    "fas_reserve_nondeployed": _GROUP_KEY_FAS,
    "fas_military_stockpile": _GROUP_KEY_FAS,
    "fas_total_inventory": _GROUP_KEY_FAS,
    # SIPRI Yearbook Ch.7 nuclear forces group — the 3 Table-7.1
    # indicators (Total Inventory, Deployed, Retired). The
    # REQUIRED ``sipri_yearbook_ch7_nuclear_warheads_total_inventory``
    # anchors the group; the PREFERRED ``deployed`` and FALLBACK
    # ``retired`` indicators fill in the deployment and
    # disarmament-progress sub-dimensions. ``total_inventory``
    # and ``deployed`` are LOWER_IS_BETTER; ``retired`` is
    # HIGHER_IS_BETTER (more retired = more disarmament = better).
    # Stage 6 normalizes both directions so the scorer sees 1 =
    # best. This group is the cross-validation signal (0.40).
    "sipri_yearbook_ch7_nuclear_warheads_total_inventory": (
        _GROUP_KEY_SIPRI
    ),
    "sipri_yearbook_ch7_nuclear_warheads_deployed": _GROUP_KEY_SIPRI,
    "sipri_yearbook_ch7_nuclear_warheads_retired": _GROUP_KEY_SIPRI,
}


#: Map from plan ``variable_name`` to its **owning canonical source key**.
#: Per the Stage 5 "per-indicator ownership" rule (see
#: :mod:`leaders_db.score.source_plans` §"Per-indicator ownership"), each
#: :class:`~leaders_db.score.evidence_types.IndicatorSpec` declares the
#: canonical source key that owns its variable; the bundle builder scopes
#: every :class:`~leaders_db.score.evidence.EvidenceObservation` lookup to
#: that single source so cross-source contamination (e.g. a WGI row
#: carrying ``fas_total_inventory``) is silently dropped upstream. The
#: nuclear scorer's defence-in-depth scoring-basis filter uses this map
#: to drop any hand-built bundle observation whose
#: ``(variable_name, source_key)`` pair does not match the plan's declared
#: ownership — the no-invented-score invariant requires the scoring basis
#: to require BOTH the expected nuclear variable AND its owning nuclear
#: source before any viable-data gate, component, ref, score, flag,
#: :attr:`ReviewFlag.NUCLEAR_CASE` detection, or rationale is computed
#: (reviewer-blocker fix). See
#: :func:`leaders_db.score._nuclear_components.filter_scoring_basis` and
#: :func:`leaders_db.score.nuclear.score_nuclear`.
_OWNING_SOURCE_BY_VARIABLE: dict[str, str] = {
    # FAS-owned indicators.
    "fas_operational_strategic": "fas",
    "fas_operational_nonstrategic": "fas",
    "fas_reserve_nondeployed": "fas",
    "fas_military_stockpile": "fas",
    "fas_total_inventory": "fas",
    # SIPRI Yearbook Ch.7-owned indicators.
    "sipri_yearbook_ch7_nuclear_warheads_total_inventory": (
        "sipri_yearbook_ch7"
    ),
    "sipri_yearbook_ch7_nuclear_warheads_deployed": (
        "sipri_yearbook_ch7"
    ),
    "sipri_yearbook_ch7_nuclear_warheads_retired": (
        "sipri_yearbook_ch7"
    ),
}


#: Set of canonical source keys that own nuclear indicators in this rubric.
#: The set is the same as ``set(_OWNING_SOURCE_BY_VARIABLE.values())``
#: captured as a :class:`frozenset` for fast membership checks in the
#: scoring-basis filter. A hand-built bundle observation whose
#: ``source_key`` is not in this set cannot own a nuclear indicator and
#: must be ignored by the scoring basis. AGENTS.md always-on rule #6 +
#: requirement §6 ("most countries are non-nuclear") combine to require
#: this strict ownership gate: a non-nuclear source row (e.g. a WGI row
#: carrying ``fas_total_inventory``) carrying an expected nuclear variable
#: must NOT produce a numeric score. Without this filter the scorer would
#: happily invent one — the reviewer-blocker vulnerability the
#: :func:`leaders_db.score._nuclear_components.filter_scoring_basis` filter
#: closes.
_OWNING_SOURCE_KEYS: frozenset[str] = frozenset(
    {"fas", "sipri_yearbook_ch7"}
)


#: Map from group key to its weight. The lookup is by group string
#: so the scoring loop can pull the weight without an ``if/elif``
#: chain over the two groups. The values sum to 1.0.
_GROUP_WEIGHTS: dict[str, float] = {
    _GROUP_KEY_FAS: _GROUP_WEIGHT_FAS,
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
    "_GROUP_KEY_FAS",
    "_GROUP_KEY_SIPRI",
    "_GROUP_WEIGHTS",
    "_GROUP_WEIGHT_FAS",
    "_GROUP_WEIGHT_SIPRI",
    "_OWNING_SOURCE_BY_VARIABLE",
    "_OWNING_SOURCE_KEYS",
    "_SPARSE_OBSERVED_RATIO_THRESHOLD",
]
