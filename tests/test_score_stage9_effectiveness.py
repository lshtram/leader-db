"""Stage 9 production seam tests for the ``effectiveness`` category.

Closes the reviewer blocker "production Stage 9 proof gap" for
the effectiveness scorer. The single-category seam
(:func:`leaders_db.score.stage9.score_category_for_country`) is
the social-wellbeing happy path in :mod:`tests.test_score_stage9`;
this file is the sibling that covers the same end-to-end
production path for the ``effectiveness`` category — seeding an
isolated SQLite DB with WGI / V-Dem / BTI ``source_observations``
rows, then calling ``score_category_for_country`` and
``score_category_for_all_countries`` with
``category_key='effectiveness'`` to prove the
``build_category_evidence_bundle`` → ``score_category_bundle`` →
``score_effectiveness`` chain returns a
:class:`~leaders_db.score.results.ScoreResult`. Brazil (``BRA``)
is seeded with no observations so the batch path proves the
insufficient-data branch end-to-end against the real DB + real
bundle builder.
"""

from __future__ import annotations

from leaders_db.db.engine import init_database
from leaders_db.db.models import Country
from leaders_db.db.session import session_scope
from leaders_db.score.results import ReviewFlag, ScoreResult
from leaders_db.score.stage9 import (
    score_category_for_all_countries,
    score_category_for_country,
)

from ._resolve_indicators_factories import (
    COUNTRY_ISO3,
    TARGET_YEAR,
    add_observation,
    seed_country,
    upsert_source,
)

# Source names match the production ``register_*_source`` calls in
# ``src/leaders_db/ingest/*_db.py`` so the substring match in
# :func:`leaders_db.score.source_plans.canonical_source_key` resolves
# them to the right canonical short keys (``wgi`` / ``vdem`` /
# ``bti``).
WGI_SOURCE_NAME: str = "World Bank WGI (test)"
VDEM_SOURCE_NAME: str = "V-Dem (Varieties of Democracy) (test)"
BTI_SOURCE_NAME: str = "Bertelsmann BTI (test)"

# ``BRA`` is inserted *after* ``MEX`` so the iso3 ordering of the
# batch result is exercised, not just the insertion order
# (``BRA < MEX`` lexicographically).
SECOND_COUNTRY_ISO3: str = "BRA"
SECOND_COUNTRY_NAME: str = "Brazil"
SECOND_COUNTRY_REGION: str = "LAC"

# Per-source ``(variable_name, normalized_value)`` pairs to seed
# for the dense Mexico bundle. Mirrors
# :func:`tests._effectiveness_factories.realistic_effectiveness_observations`
# — all 12 EFFECTIVENESS_PLAN indicators populated across 3 sources.
EFFECTIVENESS_SEED: tuple[tuple[str, str, tuple[tuple[str, float], ...]], ...] = (
    (
        WGI_SOURCE_NAME, "wgi",
        (
            ("wgi_voice_and_accountability", 0.60),
            ("wgi_political_stability", 0.55),
            ("wgi_government_effectiveness", 0.65),
            ("wgi_regulatory_quality", 0.60),
            ("wgi_rule_of_law", 0.50),
        ),
    ),
    (
        VDEM_SOURCE_NAME, "vdem",
        (
            ("vdem_v2x_jucon", 0.60),
            ("vdem_v2xlg_legcon", 0.55),
            ("vdem_v2x_accountability", 0.65),
            ("vdem_v2x_mpi", 0.55),
            ("vdem_v2x_regime", 0.70),
        ),
    ),
    (
        BTI_SOURCE_NAME, "bti",
        (
            ("bti_governance_index", 0.50),
            ("bti_governance_performance", 0.55),
        ),
    ),
)


def _seed_mexico_effectiveness_bundle(database_url: str) -> None:
    """Seed Mexico 2023 with WGI + V-Dem + BTI observations.

    Three distinct sources — well above the plan's
    ``minimum_viable_sources = 2``. All 12 EFFECTIVENESS_PLAN
    indicators populated so the bundle builder emits a usable
    bundle and the dispatcher routes it to
    :func:`score_effectiveness` for a real (non-insufficient-data)
    result.
    """
    init_database(database_url)
    with session_scope(database_url) as session:
        country = seed_country(session)
        for source_name, source_short, rows in EFFECTIVENESS_SEED:
            source_row = upsert_source(session, source_name=source_name)
            for variable_name, normalized in rows:
                add_observation(
                    session,
                    source_id=source_row.id,
                    country_id=country.id,
                    year=TARGET_YEAR,
                    variable_name=variable_name,
                    raw_value=f"{normalized:.4f}",
                    normalized_value=normalized,
                    unit="index",
                    source_row_reference=(
                        f"{source_short}:{COUNTRY_ISO3}:"
                        f"{TARGET_YEAR}:{variable_name}"
                    ),
                )


def _seed_mexico_and_brazil(database_url: str) -> None:
    """Seed MEX (dense effectiveness bundle) + BRA (no observations)."""
    _seed_mexico_effectiveness_bundle(database_url)
    with session_scope(database_url) as session:
        brazil = Country(
            iso3=SECOND_COUNTRY_ISO3,
            country_name=SECOND_COUNTRY_NAME,
            country_name_normalized="brazil",
            region=SECOND_COUNTRY_REGION,
        )
        session.add(brazil)
        session.flush()


# ---------------------------------------------------------------------------
# Single-country seam
# ---------------------------------------------------------------------------


def test_score_category_for_country_effectiveness_returns_score_result(
    database_url: str,
) -> None:
    """The seam composes bundle-builder + dispatcher and returns a ScoreResult.

    Boundary test: fails if either
    :func:`build_category_evidence_bundle` or
    :func:`score_category_bundle` is removed/replaced with a stub,
    or if the ``effectiveness`` entry is dropped from
    :data:`leaders_db.score.dispatch._SCORERS`.
    """
    _seed_mexico_effectiveness_bundle(database_url)

    with session_scope(database_url) as session:
        result = score_category_for_country(
            session,
            country_iso3=COUNTRY_ISO3,
            year=TARGET_YEAR,
            category_key="effectiveness",
        )

    assert isinstance(result, ScoreResult)
    assert result.category_key == "effectiveness"
    assert result.iso3 == COUNTRY_ISO3
    assert result.year == TARGET_YEAR


def test_score_category_for_country_effectiveness_emits_observation_refs(
    database_url: str,
) -> None:
    """The seam produces a result with one observation ref per indicator.

    All 12 EFFECTIVENESS_PLAN indicators are present across the
    three seeded sources, so the bundle builder emits 12
    :class:`EvidenceObservation` rows and the scorer carries 12
    refs in the flat :attr:`ScoreResult.observation_refs`.
    """
    _seed_mexico_effectiveness_bundle(database_url)

    with session_scope(database_url) as session:
        result = score_category_for_country(
            session,
            country_iso3=COUNTRY_ISO3,
            year=TARGET_YEAR,
            category_key="effectiveness",
        )

    assert result.is_insufficient_data is False
    assert len(result.observation_refs) == 12
    assert {ref.source_key for ref in result.observation_refs} == {
        "wgi", "vdem", "bti"
    }


def test_score_category_for_country_effectiveness_emits_concrete_score(
    database_url: str,
) -> None:
    """The seam emits a 1..10 score for the dense Mexico seed."""
    _seed_mexico_effectiveness_bundle(database_url)

    with session_scope(database_url) as session:
        result = score_category_for_country(
            session,
            country_iso3=COUNTRY_ISO3,
            year=TARGET_YEAR,
            category_key="effectiveness",
        )

    assert result.system_proposed_score_1_10 is not None
    assert 1 <= result.system_proposed_score_1_10 <= 10
    assert result.normalized_score_0_1 is not None
    assert 0.0 <= result.normalized_score_0_1 <= 1.0
    # No review flag fires on the dense seed — every REQUIRED
    # indicator is observed DIRECT.
    assert result.review_flags == ()
    assert result.human_review_required is False


def test_score_category_for_country_effectiveness_components_cover_groups(
    database_url: str,
) -> None:
    """The seam emits one :class:`ScoreComponent` per rubric group.

    The realistic Mexico seed populates all 12 indicators, so the
    scorer emits a 3-group breakdown: 5 WGI + 5 V-Dem + 2 BTI
    components. Each component carries a single observation ref
    pointing at its underlying row.
    """
    _seed_mexico_effectiveness_bundle(database_url)

    with session_scope(database_url) as session:
        result = score_category_for_country(
            session,
            country_iso3=COUNTRY_ISO3,
            year=TARGET_YEAR,
            category_key="effectiveness",
        )

    by_group: dict[str, int] = {}
    for component in result.components:
        _, _, group_key = component.component_key.partition("__")
        by_group[group_key] = by_group.get(group_key, 0) + 1
    assert by_group == {
        "wgi_governance": 5,
        "vdem_governance_accountability": 5,
        "bti_governance": 2,
    }


# ---------------------------------------------------------------------------
# Sparse / insufficient-data paths
# ---------------------------------------------------------------------------


def test_score_category_for_country_effectiveness_handles_sparse_bundle(
    database_url: str,
) -> None:
    """A bundle below the minimum-viable threshold emits an insufficient-data result.

    Seed exactly ONE source with a usable observation. The
    effectiveness plan requires ``minimum_viable_sources = 2`` so
    a single-source bundle must come back as
    ``is_insufficient_data = True`` with no score.
    """
    init_database(database_url)
    with session_scope(database_url) as session:
        country = seed_country(session)
        wgi = upsert_source(session, source_name=WGI_SOURCE_NAME)
        add_observation(
            session,
            source_id=wgi.id,
            country_id=country.id,
            year=TARGET_YEAR,
            variable_name="wgi_government_effectiveness",
            raw_value="0.6500",
            normalized_value=0.65,
            unit="index",
            source_row_reference=(
                f"wgi:{COUNTRY_ISO3}:{TARGET_YEAR}:"
                f"government_effectiveness"
            ),
        )

    with session_scope(database_url) as session:
        result = score_category_for_country(
            session,
            country_iso3=COUNTRY_ISO3,
            year=TARGET_YEAR,
            category_key="effectiveness",
        )

    assert result.is_insufficient_data is True
    assert result.system_proposed_score_1_10 is None
    assert result.normalized_score_0_1 is None
    assert result.human_review_required is True
    assert result.observation_refs == ()
    assert result.components == ()


# ---------------------------------------------------------------------------
# All-countries batch seam
# ---------------------------------------------------------------------------


def test_score_category_for_all_countries_effectiveness_returns_one_per_country(
    database_url: str,
) -> None:
    """The batch seam returns one :class:`ScoreResult` per ``Country`` row."""
    _seed_mexico_and_brazil(database_url)

    with session_scope(database_url) as session:
        results = score_category_for_all_countries(
            session,
            year=TARGET_YEAR,
            category_key="effectiveness",
        )

    iso3s = tuple(r.iso3 for r in results)
    # Ordered by iso3 — BRA < MEX lexicographically — so the
    # deterministic order is independent of insertion order.
    assert iso3s == (SECOND_COUNTRY_ISO3, COUNTRY_ISO3)
    for r in results:
        assert isinstance(r, ScoreResult)
        assert r.category_key == "effectiveness"
        assert r.year == TARGET_YEAR


def test_score_category_for_all_countries_effectiveness_scored_country_has_score(
    database_url: str,
) -> None:
    """The dense MEX row in the batch gets a real (non-insufficient) score."""
    _seed_mexico_and_brazil(database_url)

    with session_scope(database_url) as session:
        results = score_category_for_all_countries(
            session,
            year=TARGET_YEAR,
            category_key="effectiveness",
        )

    mex = next(r for r in results if r.iso3 == COUNTRY_ISO3)
    assert mex.is_insufficient_data is False
    assert mex.system_proposed_score_1_10 is not None
    assert 1 <= mex.system_proposed_score_1_10 <= 10
    assert 0.0 <= (mex.normalized_score_0_1 or 0.0) <= 1.0
    # 12 indicators × 1 ref each = 12 refs total.
    assert len(mex.observation_refs) == 12
    assert mex.review_flags == ()
    assert mex.human_review_required is False


def test_score_category_for_all_countries_effectiveness_missing_country_has_insufficient(
    database_url: str,
) -> None:
    """A Country row with no observations emits ``is_insufficient_data=True``.

    End-to-end proof that the insufficient-data branch — including
    the BLOCKER-1 fix that derives ``MISSING_PRIMARY_SOURCE`` /
    ``SPARSE_DATA`` / ``LOW_CONFIDENCE`` from the bundle on top of
    the ``INSUFFICIENT_DATA`` gate — fires correctly through the
    batch seam + bundle builder + dispatcher + scorer chain.
    """
    _seed_mexico_and_brazil(database_url)

    with session_scope(database_url) as session:
        results = score_category_for_all_countries(
            session,
            year=TARGET_YEAR,
            category_key="effectiveness",
        )

    bra = next(r for r in results if r.iso3 == SECOND_COUNTRY_ISO3)
    assert bra.is_insufficient_data is True
    assert bra.system_proposed_score_1_10 is None
    assert bra.normalized_score_0_1 is None
    assert bra.human_review_required is True
    # INSUFFICIENT_DATA is the gate signal; SPARSE_DATA rides along
    # because observed_ratio (0/12) is below the 0.5 threshold.
    assert ReviewFlag.INSUFFICIENT_DATA in bra.review_flags
    assert ReviewFlag.SPARSE_DATA in bra.review_flags
    assert bra.observation_refs == ()
    # Missingness summary is the missingness-investigation artifact;
    # the batch seam relies on the dispatcher to populate it even
    # for the empty-bundle path.
    assert bra.missingness is not None
    assert bra.missingness.total_expected == 12
    assert bra.missingness.total_observed == 0


__all__ = [
    "BTI_SOURCE_NAME",
    "SECOND_COUNTRY_ISO3",
    "SECOND_COUNTRY_NAME",
    "SECOND_COUNTRY_REGION",
    "VDEM_SOURCE_NAME",
    "WGI_SOURCE_NAME",
]
