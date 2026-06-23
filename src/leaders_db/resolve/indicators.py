"""Stage 5 — indicator extraction (requirement §8, REQ-STAGE-006).

For each (country, year, category) tuple, the orchestrator (a later
phase) collects relevant country-year indicators from
``source_observations`` and arranges them into a per-category
:class:`~leaders_db.score.evidence.CategoryEvidenceBundle`. The
bundle is the single object the per-category scoring modules in
:mod:`leaders_db.score` consume.

The per-source indicator catalog lives at
``src/leaders_db/ingest/catalogs/<source>.csv`` (one CSV per Stage 2
adapter, sibling to the adapter module). The cross-source "which
indicator belongs to which rating category and which source owns it"
mapping is recorded in the per-source catalogs (the
``category_key`` / ``rating_category`` / ``source_key`` columns)
and in :mod:`leaders_db.score.source_plans` (this is the
authoritative per-category plan for Stage 5). Each
:class:`~leaders_db.score.evidence_types.IndicatorSpec` in a plan
declares its **owning canonical source key** via
``IndicatorSpec.source_key`` — the per-indicator ownership is the
authoritative Stage 5 rule for cross-source contamination.

Production seam
---------------

:func:`build_category_evidence_bundle` is the Phase E production
seam. It:

1. Resolves the country by ISO3 via the ``countries`` table
   (Stage 3 must run first — a missing country is a hard error).
2. Maps the plan's ``expected_sources`` to the persisted
   ``sources`` rows via the substring match in
   :func:`leaders_db.score.source_plans.canonical_source_key`.
   Client 2023 matrix sources are excluded at the name level and
   can never appear in the bundle (requirement §3, §9, §12;
   ``docs/architecture/overview.md`` §"Client matrix invariants").
3. For each expected indicator, queries
   ``source_observations`` joined to ``sources`` and
   ``countries`` (via the canonical ORM models) **scoped to the
   owning source** (the canonical key in ``spec.source_key``) and
   selects the best available year:

   - ``TemporalKind.DIRECT`` for an exact-year match,
   - ``TemporalKind.PROXY`` for a year within
     ``plan.allowed_proxy_years`` of the target (closest year
     wins; ties broken by later observation year, then
     ``source.id`` order, then ``SourceObservation.id`` order —
     see :mod:`leaders_db.resolve.indicators_selection` for the
     full deterministic tie-breaker contract),
   - :class:`MissingObservation` with
     :attr:`~leaders_db.score.evidence.MissingReason.SOURCE_NOT_IMPLEMENTED`
     when the **owning** source key is not registered in the DB
     (the owning key flows through to ``MissingObservation.source_key``),
   - :class:`MissingObservation` with
     :attr:`~leaders_db.score.evidence.MissingReason.TARGET_YEAR_ABSENT`
     when the owning source is registered but has no eligible
     row for the target year (or every row is outside the proxy
     budget).

   Stale observations (outside the proxy budget) are not selected
   in this stage; the task spec accepts "missing is acceptable for
   this stage".

4. Wraps the result in a
   :class:`~leaders_db.score.evidence.CategoryEvidenceBundle` with
   the per-observation authority / specificity defaults declared
   in :mod:`leaders_db.score.source_plans` and the read-only
   ``category_metadata`` slot populated with the target year.

Unknown ``category_key`` values raise :class:`ValueError`; the
error message lists the supported categories so a Stage 5 caller
gets a self-explanatory failure.

Private helpers live in:

- :mod:`leaders_db.resolve.indicators_sources` —
  :func:`normalize_iso3`, :func:`expected_source_ids`.
- :mod:`leaders_db.resolve.indicators_collection` —
  :func:`collect_indicator_observations` (queries
  ``source_observations`` and converts rows into
  :class:`EvidenceObservation` / :class:`MissingObservation`).
- :mod:`leaders_db.resolve.indicators_selection` —
  :func:`select_best_row`, :func:`temporal_kind_for`,
  :func:`severity_for_indicator`, :func:`coerce_float`,
  :func:`coerce_numeric`.

The public seam composes them.

Legacy materialization helper
-----------------------------

:func:`extract_indicators` is the older materializing seam that
writes a parquet / csv file under ``data/interim/``. Full-pipeline
materialization remains out of scope for the current Phase; the
helper stays as a stub and raises :class:`NotImplementedError`.
The legacy ``data/metadata/indicator_catalog.csv`` path mentioned
in earlier drafts is **not** the canonical location; it should be
re-derived from the per-source catalogs when Phase E lands.

Style invariants (per ``docs/process/coding-guidelines.md``):

- ``from __future__ import annotations`` for forward-reference safety.
- Type hints on every public function parameter and return.
- No mutable defaults.
- No ``print()``, no ``TODO(debug)``, no scratch code.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Country
from ..score.evidence import (
    CategoryEvidenceBundle,
    EvidenceObservation,
    MissingObservation,
)
from ..score.source_plans import get_category_source_plan
from .indicators_collection import collect_indicator_observations
from .indicators_sources import expected_source_ids, normalize_iso3

__all__ = [
    "build_category_evidence_bundle",
    "extract_indicators",
]


# ---------------------------------------------------------------------------
# Public production seam
# ---------------------------------------------------------------------------


def build_category_evidence_bundle(
    session: Session,
    *,
    country_iso3: str,
    year: int,
    category_key: str,
    leader_name: str | None = None,
) -> CategoryEvidenceBundle:
    """Build the Stage 5 evidence bundle for one (country, year, category).

    The function queries ``source_observations`` joined to
    ``countries`` and ``sources`` using the canonical ORM models
    (no raw SQL, no fake dict-only short-circuits). For each
    expected indicator in the category plan it picks the best
    available observation year (direct, then proxy) and emits
    :class:`EvidenceObservation` rows; missing indicators become
    :class:`MissingObservation` rows with the reason set to
    :attr:`MissingReason.TARGET_YEAR_ABSENT` (or
    :attr:`MissingReason.SOURCE_NOT_IMPLEMENTED` when no expected
    source is registered in the DB at all).

    Parameters
    ----------
    session:
        An open SQLAlchemy :class:`Session` bound to the canonical
        ``leaders_db.sqlite`` (or PostgreSQL via the same ORM).
        The session is read-only; nothing is written to the DB.
    country_iso3:
        Three-character ISO 3166-1 alpha-3 code (case-insensitive).
        The function normalises the value to upper case before the
        lookup. A missing country raises :class:`ValueError`.
    year:
        Target year (1900..2100) the bundle is being built for.
        Used as the anchor for direct / proxy / stale classification.
    category_key:
        Canonical category identifier (e.g. ``"social_wellbeing"``,
        ``"integrity"``). Unknown values raise :class:`ValueError`
        with a message that lists the supported categories.
    leader_name:
        Optional canonical leader name in office for ``year``. The
        bundle records the value on its ``leader_name`` field for
        downstream rationale / audit-trail use; this Stage 5
        builder does not filter observations by leader.

    Returns
    -------
    :class:`~leaders_db.score.evidence.CategoryEvidenceBundle`
        A frozen bundle carrying the plan, the available
        observations, the missing observations with their reasons
        and severities, and a small read-only ``category_metadata``
        slot populated with the target year and the plan's
        minimum-viable threshold.

    Raises
    ------
    ValueError
        If ``category_key`` is not in
        :data:`leaders_db.score.source_plans.CATEGORY_SOURCE_PLANS`,
        or if ``country_iso3`` does not match a row in the
        ``countries`` table.
    """
    plan = get_category_source_plan(category_key)
    iso3 = normalize_iso3(country_iso3)
    country = session.execute(
        select(Country).where(Country.iso3 == iso3)
    ).scalar_one_or_none()
    if country is None:
        raise ValueError(
            f"Country iso3={iso3!r} not found in the DB. "
            f"Run Stage 3 (country matching) before Stage 5."
        )
    if not (1900 <= year <= 2100):
        raise ValueError(f"year must be in 1900..2100 (got {year})")

    plan_source_ids = expected_source_ids(session, plan.expected_sources)
    observations: list[EvidenceObservation] = []
    missing: list[MissingObservation] = []
    for spec in plan.expected_indicators:
        collect_indicator_observations(
            session,
            country=country,
            target_year=year,
            spec=spec,
            plan=plan,
            expected_source_ids=plan_source_ids,
            observations=observations,
            missing=missing,
        )
    return CategoryEvidenceBundle(
        country_iso3=iso3,
        country_name=country.country_name,
        leader_name=leader_name,
        year=year,
        category_key=category_key,
        source_plan=plan,
        observations=observations,
        missing=missing,
        category_metadata={
            "target_year": str(year),
            "plan_minimum_viable_sources": str(plan.minimum_viable_sources),
        },
    )


# ---------------------------------------------------------------------------
# Legacy materialization helper (stub)
# ---------------------------------------------------------------------------


def extract_indicators(year: int) -> Path:
    """Extract per-ruler-year per-category indicator bundles for ``year``.

    Returns the absolute path to the indicator-bundles file (parquet
    or csv under ``data/interim/``).

    This materializing helper is **not implemented** in the current
    Phase. Stage 5 ships :func:`build_category_evidence_bundle`
    (the in-memory seam) and a future Phase will materialize the
    per-country-year bundles to disk here. The full-pipeline
    materialization remains out of scope per
    ``docs/workplan.md`` Phase D / E status; the stub is preserved
    so the CLI ``leaders-db extract-indicators --year <year>``
    surface stays callable.
    """
    raise NotImplementedError(
        "extract_indicators is not implemented yet. Phase E. "
        "Use build_category_evidence_bundle(session, *, "
        "country_iso3, year, category_key) for the in-memory seam."
    )
