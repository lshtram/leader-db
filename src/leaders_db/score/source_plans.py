"""Category source plans for the Stage 5 evidence-bundle builder
(public facade).

This module is the **focused facade** for the per-category
:class:`~leaders_db.score.evidence.CategorySourcePlan` instances.
It owns:

- the :data:`SOURCE_KEY_BY_NAME` substring map (the canonical
  source-key derivation from a Stage 2 ``Source.source_name``);
- the :data:`EXCLUDED_SOURCE_KEYS` / :data:`EXCLUDED_SOURCE_NAME_SUBSTRINGS`
  client-matrix guard;
- the conservative :data:`DEFAULT_AUTHORITY_SCORE` /
  :data:`DEFAULT_SPECIFICITY_SCORE` defaults for every Stage 5
  observation;
- :func:`canonical_source_key` (the substring matcher);
- the :data:`CATEGORY_SOURCE_PLANS` registry and
  :func:`get_category_source_plan` accessor.

The per-category plan instances live in
:mod:`leaders_db.score.category_plans` — one focused file per
category, mirroring the "future scoring formulas must live in
separate files per rating category" rule (AGENTS.md). The
subpackage re-exports the same names through
:mod:`leaders_db.score` (the package root) for backward
compatibility.

Scope
-----

The prototype ships plans for **all 8** categories from requirement
§4 (``docs/req/top-level-requirements.md`` §4):

1. ``nuclear`` — FAS nuclear forces + SIPRI Yearbook Ch.7.
2. ``international_peace`` — UCDP state-based events/fatalities +
   UCDP internationalized events/fatalities + SIPRI military
   expenditure.
3. ``domestic_violence`` — PTS (3 parallel scores) + CIRIGHTS (4
   physical-integrity components) + UCDP one-sided violence + V-Dem
   physical-violence indices.
4. ``political_freedom`` — V-Dem polyarchy / liberal democracy /
   civil liberties / rule of law / electoral components + RSF press
   freedom + BTI political-freedom composites.
5. ``economic_wellbeing`` — World Bank WDI (gdp / gni / trade / fdi)
   + BTI economic questions.
6. ``social_wellbeing`` — UNDP HDI (composite + components) + WHO
   GHO API + World Bank WDI social indicators + V-Dem egalitarian
   component.
7. ``integrity`` — WGI Control of Corruption + V-Dem political-
   corruption indices + Transparency International CPI.
8. ``effectiveness`` — WGI (5 governance indicators) + V-Dem
   judicial/legislative constraints + BTI governance indices.

Adding a new category is a two-step process: (1) declare the plan
constant in a new file under :mod:`leaders_db.score.category_plans`;
(2) register the new plan in
:attr:`leaders_db.score.category_plans.CATEGORY_SOURCE_PLANS`. The
builder raises :class:`ValueError` for an unknown category key.

Source-key derivation
---------------------

The plan's ``expected_sources`` lists canonical short keys (e.g.
``"undp_hdi"``). The persisted ``Source.source_name`` field is the
human-readable name (e.g. ``"UNDP Human Development Index
(HDR 2023-24)"``). :func:`canonical_source_key` translates one to
the other via a case-insensitive substring match against
:data:`SOURCE_KEY_BY_NAME`. The substring match is robust to minor
naming changes between versions and to the test fixtures' lighter
``"(test fixture)"`` suffixes.

Client-supplied sources — the 2023 matrix the client sent us, staged
under ``data/raw/client_existing/`` — are **explicitly excluded**:
the matrix is the reference for validation, not an independent
source of structured evidence (requirement §3, §9, §12;
``docs/architecture.md`` §"Client matrix invariants"). The
exclusion has two layers (defense in depth):

1. The source key is in :data:`EXCLUDED_SOURCE_KEYS`.
2. The source name contains one of
   :data:`EXCLUDED_SOURCE_NAME_SUBSTRINGS` (case-insensitive).

Authority / specificity defaults
-------------------------------

Per task spec, the per-observation ``authority_score`` and
``specificity_score`` use conservative defaults
(:data:`DEFAULT_AUTHORITY_SCORE` = 70,
:data:`DEFAULT_SPECIFICITY_SCORE` = 80) for every observation this
module's plans describe. The defaults are placeholders for the
per-source authority table the Phase D score module will fill in.
They are documented here so the values are auditable from one
location; a future phase may add a per-source override dict.

Per-indicator ownership
-----------------------

Each :class:`IndicatorSpec` declared in the per-category plan
files carries an owning canonical source key via
``IndicatorSpec.source_key``. The Stage 5 evidence-bundle builder
scopes its ``source_observations`` lookup to this single source
for that variable; rows from a non-owning source are ignored and
the indicator is reported missing. The rule prevents cross-source
contamination (e.g. a WGI row carrying ``vdem_v2x_corr`` is
silently dropped, and ``vdem_v2x_corr`` is flagged as
``TARGET_YEAR_ABSENT`` when no V-Dem row exists). The
:mod:`leaders_db.score.category_plans` subpackage is the
**single** place where the per-indicator ownership mapping is
declared; adding a new indicator means declaring both the
variable name and the owning source.

Style invariants (per ``docs/coding-guidelines.md``):

- ``from __future__ import annotations`` for forward-reference safety.
- Public functions carry type hints on every parameter and return.
- No mutable defaults.
- No ``print()``, no ``TODO(debug)``, no scratch code.
"""

from __future__ import annotations

from collections.abc import Mapping

from .category_plans import (
    CATEGORY_SOURCE_PLANS,
    DOMESTIC_VIOLENCE_INDICATORS,
    DOMESTIC_VIOLENCE_PLAN,
    ECONOMIC_WELLBEING_INDICATORS,
    ECONOMIC_WELLBEING_PLAN,
    EFFECTIVENESS_INDICATORS,
    EFFECTIVENESS_PLAN,
    INTEGRITY_INDICATORS,
    INTEGRITY_PLAN,
    INTERNATIONAL_PEACE_INDICATORS,
    INTERNATIONAL_PEACE_PLAN,
    NUCLEAR_INDICATORS,
    NUCLEAR_PLAN,
    POLITICAL_FREEDOM_INDICATORS,
    POLITICAL_FREEDOM_PLAN,
    SOCIAL_WELLBEING_INDICATORS,
    SOCIAL_WELLBEING_PLAN,
)
from .evidence import CategorySourcePlan, IndicatorSpec, SparseDataPolicy

# ---------------------------------------------------------------------------
# Source-key derivation
# ---------------------------------------------------------------------------

#: Map a case-insensitive substring of a Source row's ``source_name``
#: to the canonical short key used by the plan and the evidence
#: bundle. The needles are intentionally short and stable substrings;
#: they match what the Stage 2 adapter ``register_*_source`` calls
#: set as ``source_name`` plus a year / version suffix. The
#: substring match is robust to that suffix and to test-fixture
#: variants like ``"World Bank WGI (test fixture)"``.
#:
#: Coverage: the 14 implemented Stage 2 sources whose per-source
#: catalogs live under ``src/leaders_db/ingest/catalogs/`` and whose
#: ``register_*_source`` helpers stage a row in the ``sources`` table.
#: Leader-identity sources (Archigos, REIGN, Leader Survival,
#: Wikidata heads of state/government, Wikipedia search extract) are
#: NOT in this map — the scoring layer never consumes them; they
#: feed Stage 3/4 (leader resolution) and are out of scope for the
#: category source plans.
SOURCE_KEY_BY_NAME: Mapping[str, str] = {
    "UNDP": "undp_hdi",
    "World Bank WGI": "wgi",
    "World Bank WDI": "world_bank_wdi",
    "V-Dem": "vdem",
    "WHO Global Health Observatory": "who_gho_api",
    "Transparency International": "ti_cpi",
    "Federation of American Scientists": "fas",
    "SIPRI Yearbook Chapter 7": "sipri_yearbook_ch7",
    "SIPRI Military Expenditure Database": "sipri_milex",
    "UCDP": "ucdp",
    "Political Terror Scale": "pts",
    "CIRI Human Rights Data Project": "cirights",
    "Bertelsmann BTI": "bti",
    "Reporters Without Borders World Press Freedom Index": "rsf_press_freedom",
}

#: Source keys that must never be used as Stage 5 evidence. The
#: client 2023 matrix is the reference for validation, not an
#: independent source of structured evidence (requirement §3, §9,
#: §12).
EXCLUDED_SOURCE_KEYS: frozenset[str] = frozenset(
    {"client_existing", "client_matrix"}
)

#: Substrings in a ``Source.source_name`` that mark the row as a
#: client-supplied reference (case-insensitive). The matrix xlsx in
#: ``data/raw/client_existing/`` is the only such source the
#: prototype expects; any future "client" prefix lands here too.
EXCLUDED_SOURCE_NAME_SUBSTRINGS: tuple[str, ...] = ("client",)

#: Conservative default authority score (component 1 of the §11
#: confidence formula) for every observation in the bundle. The
#: score is on the closed interval [0, 100] and indicates "vetted
#: but not premium" — sources passed the source-vetting report but
#: we are not yet making a per-source claim. A future phase may
#: replace this with a per-source override dict derived from
#: ``docs/source-vetting-report.md``.
DEFAULT_AUTHORITY_SCORE: int = 70

#: Conservative default specificity score (component 3 of the §11
#: confidence formula) for every observation. The score is on the
#: closed interval [0, 100] and reflects "country-year specific,
#: not leader-specific" — the Stage 5 bundle is at country-year
#: granularity. Leader-specific scoring lives in a later stage.
DEFAULT_SPECIFICITY_SCORE: int = 80


def canonical_source_key(source_name: str | None) -> str | None:
    """Return the canonical short key for a Source row, or ``None`` if excluded.

    The lookup is a case-insensitive substring scan of
    :data:`SOURCE_KEY_BY_NAME`. A row whose ``source_name`` contains
    any of :data:`EXCLUDED_SOURCE_NAME_SUBSTRINGS` (e.g. ``"client"``)
    is excluded first, so the client 2023 matrix can never appear in
    an evidence bundle even if a :class:`SourceObservation` row
    points at it.

    Returns ``None`` when ``source_name`` is empty / ``None`` or when
    the row is excluded. Returns the canonical key (e.g. ``"wgi"``,
    ``"undp_hdi"``) on a hit. Returns ``None`` on a miss too — the
    builder treats unknown sources as out-of-scope and the
    per-source authority table is the place to extend coverage.
    """
    if not source_name:
        return None
    lowered = source_name.lower()
    if any(sub in lowered for sub in EXCLUDED_SOURCE_NAME_SUBSTRINGS):
        return None
    for needle, key in SOURCE_KEY_BY_NAME.items():
        if needle.lower() in lowered:
            return key
    return None


def get_category_source_plan(category_key: str) -> CategorySourcePlan:
    """Return the source plan for ``category_key`` or raise :class:`ValueError`.

    The error message lists the supported categories and points the
    caller at the right extension point (this module + the
    :data:`CATEGORY_SOURCE_PLANS` registry) so the next person to
    add a plan does not have to read the builder to find the place
    to register it.
    """
    if not category_key:
        raise ValueError(
            "category_key must be a non-empty string. Supported categories: "
            f"[{', '.join(sorted(CATEGORY_SOURCE_PLANS))}]."
        )
    if category_key not in CATEGORY_SOURCE_PLANS:
        supported = ", ".join(repr(k) for k in sorted(CATEGORY_SOURCE_PLANS))
        raise ValueError(
            f"Unsupported category_key={category_key!r}. Supported categories: "
            f"[{supported}]. Add a new plan in leaders_db.score.category_plans "
            f"and register it in CATEGORY_SOURCE_PLANS."
        )
    return CATEGORY_SOURCE_PLANS[category_key]


__all__ = [
    "CATEGORY_SOURCE_PLANS",
    "DEFAULT_AUTHORITY_SCORE",
    "DEFAULT_SPECIFICITY_SCORE",
    "DOMESTIC_VIOLENCE_INDICATORS",
    "DOMESTIC_VIOLENCE_PLAN",
    "ECONOMIC_WELLBEING_INDICATORS",
    "ECONOMIC_WELLBEING_PLAN",
    "EFFECTIVENESS_INDICATORS",
    "EFFECTIVENESS_PLAN",
    "EXCLUDED_SOURCE_KEYS",
    "EXCLUDED_SOURCE_NAME_SUBSTRINGS",
    "INTEGRITY_INDICATORS",
    "INTEGRITY_PLAN",
    "INTERNATIONAL_PEACE_INDICATORS",
    "INTERNATIONAL_PEACE_PLAN",
    "NUCLEAR_INDICATORS",
    "NUCLEAR_PLAN",
    "POLITICAL_FREEDOM_INDICATORS",
    "POLITICAL_FREEDOM_PLAN",
    "SOCIAL_WELLBEING_INDICATORS",
    "SOCIAL_WELLBEING_PLAN",
    "SOURCE_KEY_BY_NAME",
    "CategorySourcePlan",
    "IndicatorSpec",
    "SparseDataPolicy",
    "canonical_source_key",
    "get_category_source_plan",
]
