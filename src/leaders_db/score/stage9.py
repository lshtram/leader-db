"""Stage 9 — single-country deterministic scoring seam.

This module composes the Stage 5 evidence-bundle builder
(:func:`leaders_db.resolve.indicators.build_category_evidence_bundle`)
with the Stage 9 dispatcher (:func:`leaders_db.score.dispatch.score_category_bundle`)
so a single call turns ``(session, country, year, category_key)`` into
a :class:`~leaders_db.score.results.ScoreResult`.

Scope
-----

The seam is intentionally **narrow and read-only**:

- It does **not** persist a ``ruler_scores`` row. Persistence requires
  the Stage 4 leader resolver (a ``ruler_year_id`` + ``category_id``
  pair) and is out of scope for this step; the comparison and manual-
  review stages will wire persistence in a follow-on step.
- It does **not** consult the client matrix as evidence (AGENTS.md
  always-on rule #6 — the bundle builder excludes client sources
  upstream; the scorer applies a defence-in-depth re-filter).
- It does **not** batch over multiple countries or years. The
  batch / ``score-all`` orchestration remains a Phase E item per
  ``docs/workplan.md``.

The seam is the **canonical Stage 9 production path** for one
country-year-category tuple. The CLI ``leaders-db score-category
--country <ISO3>`` uses it directly; future programmatic callers
(notebooks, pipelines) can do the same.

Import-order note
-----------------

The :mod:`leaders_db.resolve.indicators` builder imports back from
``leaders_db.score.evidence``, so this module cannot import the
builder at module load time without creating a cycle (the package
root ``leaders_db.score`` eagerly imports this module, and the
test suite imports ``leaders_db.resolve.indicators`` first).
We therefore use a function-local deferred import per
:doc:`docs/coding-guidelines.md` §"Python Standards" ("keep imports
local only when they avoid optional dependency costs or isolate
CLI-only behavior") — the cycle-avoidance case is the documented
exception.

Style invariants (per ``docs/coding-guidelines.md``):

- ``from __future__ import annotations`` for forward-reference
  safety.
- Type hints on every public function parameter and return.
- No mutable defaults; no ``print()``, no ``TODO(debug)``, no
  scratch code.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from .dispatch import score_category_bundle
from .results import ScoreResult

__all__ = ["score_category_for_country"]


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
