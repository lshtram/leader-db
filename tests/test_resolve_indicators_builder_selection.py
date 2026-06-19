"""Deterministic tie-breaker tests for the Stage 5 evidence-bundle builder.

These tests pin the contract that
:func:`leaders_db.resolve.indicators_selection.select_best_row`
always picks the same row regardless of insertion order. The
deterministic contract is documented in
:mod:`leaders_db.resolve.indicators_selection` and exercised at
two layers:

- **End-to-end** through ``build_category_evidence_bundle`` with
  candidate rows inserted in different orders and asserted on the
  selected row.
- **Unit** through ``select_best_row`` itself with hand-built
  in-memory ORM objects so the (tier, delta, year, source_id,
  obs_id) tie-breaker is locked at the helper layer.

Coverage pinned here (the (g) tier):

- (g.1) Two tied proxy candidates inserted in different orders
       select the later year (T3).
- (g.2) Two direct-year (target-year) candidates tied on every
       criterion except ``SourceObservation.id`` select the lower
       id (T5).
- (g.3) Two ``Source`` rows substring-matching V-Dem dedupe to
       the lower ``source.id`` (T4).
- (g.4) A STALE row (delta outside the proxy budget) is skipped.
- (g.5) Every row outside the proxy budget → ``None``.
- (g.6) Empty candidate list → ``None``.

Wrong-source / missingness tests live in
:mod:`tests.test_resolve_indicators_builder_missing`; the happy
path and the error contract live in
:mod:`tests.test_resolve_indicators_builder_core`.

The shared fixtures live in :mod:`tests._resolve_indicators_factories`.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from leaders_db.db.engine import init_database
from leaders_db.db.models import Source, SourceObservation
from leaders_db.db.session import session_scope
from leaders_db.resolve.indicators import build_category_evidence_bundle
from leaders_db.resolve.indicators_selection import select_best_row
from leaders_db.score.evidence import TemporalKind
from leaders_db.score.source_plans import (
    INTEGRITY_PLAN,
    CategorySourcePlan,
    SparseDataPolicy,
)

from ._resolve_indicators_factories import (
    COUNTRY_ISO3,
    TARGET_YEAR,
    VDEM_SOURCE_NAME,
    add_observation,
    seed_country,
    upsert_source,
)

# ---------------------------------------------------------------------------
# Local helpers
# ---------------------------------------------------------------------------


def _insert_direct_year_row_for_vdem(
    session: Session,
    *,
    vdem_id: int,
    country_id: int,
    year: int,
) -> None:
    add_observation(
        session,
        source_id=vdem_id,
        country_id=country_id,
        year=year,
        variable_name="vdem_v2x_corr",
        raw_value=f"0.{year - 2020}",
        normalized_value=float(year - 2020) / 100.0,
        source_row_reference=f"vdem:MEX:{year}:v2x_corr",
    )


def _build_integrity_plan_with_one_year_budget() -> CategorySourcePlan:
    """Return an integrity-shaped plan with ``allowed_proxy_years=(1,)``."""
    return CategorySourcePlan(
        category_key=INTEGRITY_PLAN.category_key,
        expected_sources=INTEGRITY_PLAN.expected_sources,
        expected_indicators=INTEGRITY_PLAN.expected_indicators,
        minimum_viable_sources=INTEGRITY_PLAN.minimum_viable_sources,
        preferred_direct_year=2023,
        allowed_proxy_years=(1,),
        default_source_weights=INTEGRITY_PLAN.default_source_weights,
        sparse_data_policy=SparseDataPolicy.INSUFFICIENT_DATA,
    )


# ---------------------------------------------------------------------------
# (g.1) Two tied proxy candidates inserted in different orders → same row
# ---------------------------------------------------------------------------


def test_deterministic_proxy_selection_independent_of_insertion_order(
    database_url: str,
) -> None:
    """Two tied proxy candidates inserted in different orders select the same row.

    Inserts a 2022 row and a 2024 row for the same indicator
    (``vdem_v2x_corr``) in two passes: one pass inserts the 2022
    row first then the 2024 row; the other pass inserts them in
    the opposite order. Both passes must surface the **2024** row
    — it is the later publication year and the deterministic
    tie-breaker prefers the most recent data point on tied delta.
    """
    for order in ((2022, 2024), (2024, 2022)):
        init_database(database_url)
        with session_scope(database_url) as session:
            country = seed_country(session)
            vdem = upsert_source(session, source_name=VDEM_SOURCE_NAME)
            for year in order:
                _insert_direct_year_row_for_vdem(
                    session,
                    vdem_id=vdem.id,
                    country_id=country.id,
                    year=year,
                )

        with session_scope(database_url) as session:
            bundle = build_category_evidence_bundle(
                session,
                country_iso3=COUNTRY_ISO3,
                year=TARGET_YEAR,
                category_key="integrity",
            )

        vdem_obs = [
            obs
            for obs in bundle.observations
            if obs.variable_name == "vdem_v2x_corr"
        ]
        assert len(vdem_obs) == 1, f"order={order}"
        assert vdem_obs[0].observation_year == 2024, (
            f"order={order}: expected 2024 (later year wins on tied delta), "
            f"got {vdem_obs[0].observation_year}"
        )
        assert vdem_obs[0].temporal_kind is TemporalKind.PROXY


# ---------------------------------------------------------------------------
# (g.2) Two direct-year (target-year) candidates tied on every criterion
#       except SourceObservation.id → lower id wins
# ---------------------------------------------------------------------------


def test_deterministic_direct_year_selection_prefers_latest_year(
    database_url: str,
) -> None:
    """Multiple direct-year (target-year) candidates pick the latest year.

    Both 2023 rows are DIRECT (year delta == 0); the tie-breaker
    prefers the later ``observation_year`` (T3). Wait — both are
    exactly 2023, so they tie on every criterion except
    ``SourceObservation.id`` (T5): the lower id wins (stable DB
    insertion order).
    """
    init_database(database_url)
    with session_scope(database_url) as session:
        country = seed_country(session)
        vdem = upsert_source(session, source_name=VDEM_SOURCE_NAME)
        first = add_observation(
            session,
            source_id=vdem.id,
            country_id=country.id,
            year=2023,
            variable_name="vdem_v2x_corr",
            raw_value="0.10",
            normalized_value=0.10,
            source_row_reference="vdem:MEX:2023:v2x_corr:first",
        )
        second = add_observation(
            session,
            source_id=vdem.id,
            country_id=country.id,
            year=2023,
            variable_name="vdem_v2x_corr",
            raw_value="0.20",
            normalized_value=0.20,
            source_row_reference="vdem:MEX:2023:v2x_corr:second",
        )

    with session_scope(database_url) as session:
        bundle = build_category_evidence_bundle(
            session,
            country_iso3=COUNTRY_ISO3,
            year=TARGET_YEAR,
            category_key="integrity",
        )

    vdem_obs = [
        obs
        for obs in bundle.observations
        if obs.variable_name == "vdem_v2x_corr"
    ]
    assert len(vdem_obs) == 1
    # The first-inserted row wins (lower SourceObservation.id).
    assert vdem_obs[0].source_row_reference == first.source_row_reference
    assert second.id > first.id


# ---------------------------------------------------------------------------
# (g.3) Two Source rows substring-matching V-Dem → lower source.id wins
# ---------------------------------------------------------------------------


def test_deterministic_source_id_tiebreak_when_multiple_source_rows_share_key(
    database_url: str,
) -> None:
    """Two ``Source`` rows substring-matching V-Dem → lower ``source.id`` wins.

    The deterministic tie-breaker documents that the lower
    ``source.id`` wins when multiple ``Source`` rows map to the
    same canonical key (e.g. two registered versions of V-Dem).
    The production registration is unique per ``(source_name,
    version)`` so this only fires in tests.
    """
    init_database(database_url)
    with session_scope(database_url) as session:
        country = seed_country(session)
        legacy = upsert_source(session, source_name="V-Dem v15 (legacy)")
        modern = upsert_source(session, source_name=VDEM_SOURCE_NAME)
        # Modern source inserted second → higher source.id.
        add_observation(
            session,
            source_id=legacy.id,
            country_id=country.id,
            year=2023,
            variable_name="vdem_v2x_corr",
            raw_value="0.05",
            normalized_value=0.05,
            source_row_reference="vdem_legacy:MEX:2023:v2x_corr",
        )
        add_observation(
            session,
            source_id=modern.id,
            country_id=country.id,
            year=2023,
            variable_name="vdem_v2x_corr",
            raw_value="0.20",
            normalized_value=0.20,
            source_row_reference="vdem:MEX:2023:v2x_corr",
        )

    with session_scope(database_url) as session:
        bundle = build_category_evidence_bundle(
            session,
            country_iso3=COUNTRY_ISO3,
            year=TARGET_YEAR,
            category_key="integrity",
        )

    vdem_obs = [
        obs
        for obs in bundle.observations
        if obs.variable_name == "vdem_v2x_corr"
    ]
    # Only one V-Dem observation can exist on the bundle because
    # the bundle builder dedupes by canonical key in
    # ``expected_source_ids`` (first match wins). The bundle still
    # has exactly one vdem observation.
    assert len(vdem_obs) == 1
    # And the dedup chose the lower source.id (the legacy row).
    assert vdem_obs[0].source_name == "V-Dem v15 (legacy)"


# ---------------------------------------------------------------------------
# (g.4–g.6) Direct unit tests of ``select_best_row``
# ---------------------------------------------------------------------------


def test_select_best_row_unit_picks_later_year_on_tied_delta() -> None:
    """Direct unit test of ``select_best_row`` for the T3 tie-breaker."""
    plan = _build_integrity_plan_with_one_year_budget()
    obs_a = SourceObservation(
        id=1,
        source_id=1,
        country_id=1,
        year=2022,
        variable_name="vdem_v2x_corr",
        raw_value="0.10",
    )
    obs_b = SourceObservation(
        id=2,
        source_id=1,
        country_id=1,
        year=2024,
        variable_name="vdem_v2x_corr",
        raw_value="0.30",
    )
    src = Source(id=1, source_name=VDEM_SOURCE_NAME, source_type="official")
    # Both rows are tied at delta=1; 2024 is the later year.
    best = select_best_row([(obs_a, src), (obs_b, src)], 2023, plan)
    assert best is not None
    assert best[0].year == 2024
    # Reverse insertion order: same selection.
    best_rev = select_best_row([(obs_b, src), (obs_a, src)], 2023, plan)
    assert best_rev is not None
    assert best_rev[0].year == 2024


def test_select_best_row_unit_skips_stale_rows() -> None:
    """A STALE row (delta outside proxy budget) is skipped."""
    plan = _build_integrity_plan_with_one_year_budget()
    stale = SourceObservation(
        id=1,
        source_id=1,
        country_id=1,
        year=2020,
        variable_name="vdem_v2x_corr",
        raw_value="0.10",
    )
    proxy = SourceObservation(
        id=2,
        source_id=1,
        country_id=1,
        year=2022,
        variable_name="vdem_v2x_corr",
        raw_value="0.20",
    )
    src = Source(id=1, source_name=VDEM_SOURCE_NAME, source_type="official")
    # Only the proxy row (delta=1) is eligible; the 2020 row is
    # STALE (delta=3) and must be skipped.
    best = select_best_row([(stale, src), (proxy, src)], 2023, plan)
    assert best is not None
    assert best[0].year == 2022


def test_select_best_row_unit_returns_none_when_all_stale() -> None:
    """Every row outside the proxy budget → ``None``."""
    plan = _build_integrity_plan_with_one_year_budget()
    stale_a = SourceObservation(
        id=1,
        source_id=1,
        country_id=1,
        year=2019,
        variable_name="vdem_v2x_corr",
        raw_value="0.10",
    )
    stale_b = SourceObservation(
        id=2,
        source_id=1,
        country_id=1,
        year=2018,
        variable_name="vdem_v2x_corr",
        raw_value="0.20",
    )
    src = Source(id=1, source_name=VDEM_SOURCE_NAME, source_type="official")
    assert select_best_row([(stale_a, src), (stale_b, src)], 2023, plan) is None


def test_select_best_row_unit_returns_none_for_empty_input() -> None:
    """An empty candidate list returns ``None``."""
    plan = _build_integrity_plan_with_one_year_budget()
    assert select_best_row([], 2023, plan) is None
