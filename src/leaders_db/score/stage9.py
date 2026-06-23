"""Stage 9 — single-country and all-countries deterministic scoring seams.

This module composes the Stage 5 evidence-bundle builder
(:func:`leaders_db.resolve.indicators.build_category_evidence_bundle`)
with the Stage 9 dispatcher (:func:`leaders_db.score.dispatch.score_category_bundle`)
so a single call turns ``(session, country, year, category_key)`` into
a :class:`~leaders_db.score.results.ScoreResult`.

Scope
-----

The seams are intentionally **narrow and read-only**:

- They do **not** persist a ``ruler_scores`` row. Persistence requires
  the Stage 4 leader resolver (a ``ruler_year_id`` + ``category_id``
  pair) and is out of scope for this step; the comparison and manual-
  review stages will wire persistence in a follow-on step.
- They do **not** consult the client matrix as evidence (AGENTS.md
  always-on rule #6 — the bundle builder excludes client sources
  upstream; the scorer applies a defence-in-depth re-filter).
- :func:`score_category_for_country` is the canonical one-country
  path. :func:`score_category_for_all_countries` is the canonical
  one-year/category all-countries batch path; it composes the
  per-country seam so a country with no eligible observations
  returns an ``is_insufficient_data=True`` :class:`ScoreResult`
  rather than dropping the row (per AGENTS.md always-on rule #13
  "no invented data" and the 2022 all-country social-wellbeing
  vertical slice).

The :func:`score_category_for_all_countries` seam is also the
**canonical reusable pattern** for the per-category vertical
slices that follow ``social_wellbeing``. Each new category
reuses the same call pattern; only the ``category_key`` value
changes once the next per-category scorer lands in
:data:`leaders_db.score.dispatch._SCORERS`.

CSV export
----------

The all-countries seam writes its results through
:func:`write_score_results_csv`, which is defined in
:mod:`leaders_db.score._stage9_csv` (the **focused** CSV
module) and re-exported from this module. The split keeps
:mod:`leaders_db.score.stage9` under the 400-line convention
while preserving the public import path
``from leaders_db.score.stage9 import write_score_results_csv``
(unchanged across the split).

Import-order note
-----------------

The :mod:`leaders_db.resolve.indicators` builder imports back from
``leaders_db.score.evidence``, so this module cannot import the
builder at module load time without creating a cycle (the package
root ``leaders_db.score`` eagerly imports this module, and the
test suite imports ``leaders_db.resolve.indicators`` first).
We therefore use a function-local deferred import per
:doc:`docs/process/coding-guidelines.md` §"Python Standards" ("keep imports
local only when they avoid optional dependency costs or isolate
CLI-only behavior") — the cycle-avoidance case is the documented
exception.

Style invariants (per ``docs/process/coding-guidelines.md``):

- ``from __future__ import annotations`` for forward-reference
  safety.
- Type hints on every public function parameter and return.
- No mutable defaults; no ``print()``, no ``TODO(debug)``, no
  scratch code.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

# Local imports: the CSV writer lives in a focused sibling module
# (``_stage9_csv.py``) so this module's line count stays under the
# 400-line convention. The public ``write_score_results_csv`` /
# ``SCORE_RESULTS_CSV_COLUMNS`` names are re-exported below so
# existing imports (CLI, tests, downstream callers) continue to
# work unchanged across the split.
from ._stage9_csv import SCORE_RESULTS_CSV_COLUMNS, write_score_results_csv
from .dispatch import score_category_bundle
from .results import ScoreResult

__all__ = [
    "SCORE_RESULTS_CSV_COLUMNS",
    "score_category_for_all_countries",
    "score_category_for_country",
    "write_score_results_csv",
]


# ---------------------------------------------------------------------------
# Per-country seam
# ---------------------------------------------------------------------------


def score_category_for_country(
    session: Session,
    *,
    country_iso3: str,
    year: int,
    category_key: str,
    leader_name: str | None = None,
) -> ScoreResult:
    """Score one (country, year, category) tuple end-to-end.

    The function is the Stage 9 production seam. It:

    1. Builds the Stage 5 evidence bundle via
       :func:`leaders_db.resolve.indicators.build_category_evidence_bundle`,
       which scopes the ``source_observations`` lookup to the
       category plan's expected indicator set (per-indicator
       ownership; client sources are excluded at the bundle level
       per AGENTS.md always-on rule #6).
    2. Dispatches the bundle to the registered scorer via
       :func:`leaders_db.score.dispatch.score_category_bundle`.

    The session is read-only — the function performs no DB writes
    (no ``ruler_scores`` persistence, no ``ruler_years`` upsert).
    The caller is responsible for any persistence the downstream
    comparison / manual-review stages require.

    Parameters
    ----------
    session:
        An open SQLAlchemy :class:`Session` bound to the canonical
        ``leaders_db.sqlite`` (or PostgreSQL via the same ORM).
    country_iso3:
        Three-character ISO 3166-1 alpha-3 code (case-insensitive).
    year:
        Target year the score is computed for (1900..2100 per the
        evidence-bundle contract).
    category_key:
        Canonical category identifier (e.g. ``"social_wellbeing"``).
        Must be registered in
        :data:`leaders_db.score.dispatch._SCORERS`; unsupported
        values raise :class:`ValueError` from the dispatcher.
    leader_name:
        Optional canonical leader name in office for ``year``. The
        bundle records the value on its ``leader_name`` field for
        downstream rationale / audit-trail use; this seam does not
        filter observations by leader. ``None`` (the default) lets
        the scorer fall back to the country name where appropriate.

    Returns
    -------
    ScoreResult
        The deterministic scoring result. The shape is the shared
        :class:`ScoreResult` contract documented in
        :mod:`leaders_db.score.results`. An empty bundle (no
        usable observations, below the plan's minimum-viable
        threshold) returns an ``is_insufficient_data=True`` result;
        the caller decides how to surface that.

    Raises
    ------
    ValueError
        Re-raised from the underlying seams:

        - from :func:`build_category_evidence_bundle` when
          ``category_key`` is unsupported or ``country_iso3`` is not
          in the ``countries`` table;
        - from :func:`score_category_bundle` when
          ``bundle.category_key`` is not registered in the
          dispatcher.

        The function does not catch these — the caller (CLI, test,
        future orchestrator) decides how to surface them.
    """
    # Deferred import: avoids a circular dependency on
    # ``leaders_db.resolve.indicators`` (which imports back from
    # ``leaders_db.score.evidence``). See the module docstring for
    # the full rationale.
    from ..resolve.indicators import build_category_evidence_bundle

    bundle = build_category_evidence_bundle(
        session,
        country_iso3=country_iso3,
        year=year,
        category_key=category_key,
        leader_name=leader_name,
    )
    return score_category_bundle(bundle)


# ---------------------------------------------------------------------------
# All-countries batch seam
# ---------------------------------------------------------------------------


def score_category_for_all_countries(
    session: Session,
    *,
    year: int,
    category_key: str,
) -> tuple[ScoreResult, ...]:
    """Score ``category_key`` for every country in the DB for one year.

    The function is the Stage 9 batch seam and the canonical
    reusable pattern for per-category vertical slices. It iterates
    over every :class:`~leaders_db.db.models.Country` row (ordered
    by ``iso3`` for a deterministic output) and delegates each
    (country, year, category) tuple to
    :func:`score_category_for_country`. Countries whose evidence
    bundle is empty or below the plan's minimum-viable threshold
    return an ``is_insufficient_data=True`` :class:`ScoreResult`
    rather than being dropped from the tuple — the contract is
    "one row per country" so the downstream CSV / report can
    quantify missingness per AGENTS.md always-on rule #13
    ("no invented data", "older years degrade gracefully: fewer
    indicators, more uncertainty, more manual review").

    A country that exists in the DB but has no eligible
    observations returns a clean :class:`ScoreResult` with
    ``is_insufficient_data=True`` and ``score=None`` — the
    bundle builder emits a missing-observations-only bundle for
    that case rather than raising, so no defensive try/except is
    needed here.

    The session is read-only (same contract as
    :func:`score_category_for_country`).

    Parameters
    ----------
    session:
        An open SQLAlchemy :class:`Session` bound to the canonical
        ``leaders_db.sqlite`` (or PostgreSQL via the same ORM).
    year:
        Target year the score is computed for (1900..2100 per the
        evidence-bundle contract).
    category_key:
        Canonical category identifier (e.g. ``"social_wellbeing"``).
        Must be registered in
        :data:`leaders_db.score.dispatch._SCORERS`; an unsupported
        category raises :class:`ValueError` on the first call into
        :func:`score_category_for_country`.

    Returns
    -------
    tuple[ScoreResult, ...]
        One :class:`ScoreResult` per :class:`~leaders_db.db.models.Country`
        row, ordered by ``iso3``. The tuple is a real
        :class:`tuple` (not a generator) so the caller can iterate
        it twice — for example to feed it to
        :func:`write_score_results_csv` and to compute a summary.
    """
    # Local import: Country is the only model we touch here. Keeping
    # the import local keeps the per-country seam's call path lean
    # and avoids forcing every Stage 9 caller to load the full
    # models module.
    from ..db.models import Country

    countries: Sequence[Country] = tuple(
        session.execute(
            select(Country).order_by(Country.iso3)
        ).scalars()
    )

    results: list[ScoreResult] = []
    for country in countries:
        # The bundle builder returns a missing-observations-only
        # bundle for countries that exist in the DB but have no
        # eligible observations, so the dispatcher emits a clean
        # insufficient-data ScoreResult rather than raising.
        result = score_category_for_country(
            session,
            country_iso3=country.iso3,
            year=year,
            category_key=category_key,
            leader_name=country.country_name,
        )
        results.append(result)
    return tuple(results)
