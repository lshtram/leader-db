"""Stage 9 production seam tests for the ``political_freedom`` category.

Single-country seam + sparse-bundle insufficient-data proof for
the political freedom scorer. The batch-seam sibling lives in
:mod:`tests.test_score_stage9_political_freedom_batch` (same
split pattern as the nuclear / domestic-violence / international-
peace per-category siblings).

Seeds an isolated SQLite DB with V-Dem / BTI / RSF
``source_observations`` rows and calls
:func:`leaders_db.score.stage9.score_category_for_country` with
``category_key='political_freedom'`` to prove the
``build_category_evidence_bundle`` → ``score_category_bundle`` →
``score_political_freedom`` chain returns a
:class:`~leaders_db.score.results.ScoreResult`.
"""

from __future__ import annotations

from leaders_db.db.engine import init_database
from leaders_db.db.models import Country
from leaders_db.db.session import session_scope
from leaders_db.score.results import ScoreResult
from leaders_db.score.stage9 import score_category_for_country

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
# them to the right canonical short keys (``vdem`` / ``bti`` / ``rsf_press_freedom``).
VDEM_SOURCE_NAME: str = "V-Dem (Varieties of Democracy) (test)"
BTI_SOURCE_NAME: str = "Bertelsmann BTI (test)"
RSF_SOURCE_NAME: str = "Reporters Without Borders World Press Freedom Index (test)"

# ``BRA`` is inserted *after* ``MEX`` so the iso3 ordering of the
# batch result is exercised, not just the insertion order
# (``BRA < MEX`` lexicographically).
SECOND_COUNTRY_ISO3: str = "BRA"
SECOND_COUNTRY_NAME: str = "Brazil"
SECOND_COUNTRY_REGION: str = "LAC"

# Per-source ``(variable_name, normalized_value)`` pairs to seed
# for the dense Mexico bundle. Mirrors
# :func:`tests._political_freedom_factories.realistic_political_freedom_observations`
# — all 16 POLITICAL_FREEDOM_PLAN indicators populated across 3 sources.
POLITICAL_FREEDOM_SEED: tuple[tuple[str, str, tuple[tuple[str, float], ...]], ...] = (
    (
        VDEM_SOURCE_NAME, "vdem",
        (
            ("vdem_v2x_polyarchy", 0.50),
            ("vdem_v2x_libdem", 0.45),
            ("vdem_v2x_freexp", 0.55),
            ("vdem_v2x_frassoc_thick", 0.50),
            ("vdem_v2x_suffr", 0.65),
            ("vdem_v2x_rule", 0.50),
            ("vdem_v2x_civlib", 0.55),
        ),
    ),
    (
        BTI_SOURCE_NAME, "bti",
        (
            ("bti_status_index", 0.50),
            ("bti_democracy_status", 0.55),
            ("bti_q1_stateness", 0.60),
            ("bti_q2_political_participation", 0.45),
            ("bti_q3_rule_of_law", 0.50),
            ("bti_q4_democratic_institutions", 0.55),
            ("bti_q5_political_social_integration", 0.50),
        ),
    ),
    (
        RSF_SOURCE_NAME, "rsf_press_freedom",
        (
            ("rsf_press_freedom_score", 0.50),
            ("rsf_press_freedom_political_context", 0.55),
        ),
    ),
)


def _seed_mexico_political_freedom_bundle(database_url: str) -> None:
    """Seed Mexico 2023 with V-Dem + BTI + RSF observations.

    Three distinct sources — well above the plan's
    ``minimum_viable_sources = 2``. All 16
    POLITICAL_FREEDOM_PLAN indicators populated so the bundle
    builder emits a usable bundle and the dispatcher routes it
    to :func:`score_political_freedom` for a real
    (non-insufficient-data) result.
    """
    init_database(database_url)
    with session_scope(database_url) as session:
        country = seed_country(session)
        for source_name, source_short, rows in POLITICAL_FREEDOM_SEED:
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
    """Seed MEX (dense political_freedom bundle) + BRA (no observations)."""
    _seed_mexico_political_freedom_bundle(database_url)
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


def test_score_category_for_country_political_freedom_returns_score_result(
    database_url: str,
) -> None:
    """The seam composes bundle-builder + dispatcher and returns a ScoreResult.

    Boundary test: fails if either
    :func:`build_category_evidence_bundle` or
    :func:`score_category_bundle` is removed/replaced with a stub,
    or if the ``political_freedom`` entry is dropped from
    :data:`leaders_db.score.dispatch._SCORERS`.
    """
    _seed_mexico_political_freedom_bundle(database_url)

    with session_scope(database_url) as session:
        result = score_category_for_country(
            session,
            country_iso3=COUNTRY_ISO3,
            year=TARGET_YEAR,
            category_key="political_freedom",
        )

    assert isinstance(result, ScoreResult)
    assert result.category_key == "political_freedom"
    assert result.iso3 == COUNTRY_ISO3
    assert result.year == TARGET_YEAR


def test_score_category_for_country_political_freedom_emits_observation_refs(
    database_url: str,
) -> None:
    """The seam produces a result with one observation ref per indicator.

    All 16 POLITICAL_FREEDOM_PLAN indicators are present across
    the three seeded sources, so the bundle builder emits 16
    :class:`EvidenceObservation` rows and the scorer carries 16
    refs in the flat :attr:`ScoreResult.observation_refs`.
    """
    _seed_mexico_political_freedom_bundle(database_url)

    with session_scope(database_url) as session:
        result = score_category_for_country(
            session,
            country_iso3=COUNTRY_ISO3,
            year=TARGET_YEAR,
            category_key="political_freedom",
        )

    assert result.is_insufficient_data is False
    assert len(result.observation_refs) == 16
    assert {ref.source_key for ref in result.observation_refs} == {
        "vdem", "bti", "rsf_press_freedom"
    }


def test_score_category_for_country_political_freedom_emits_concrete_score(
    database_url: str,
) -> None:
    """The seam emits a 1..10 score for the dense Mexico seed."""
    _seed_mexico_political_freedom_bundle(database_url)

    with session_scope(database_url) as session:
        result = score_category_for_country(
            session,
            country_iso3=COUNTRY_ISO3,
            year=TARGET_YEAR,
            category_key="political_freedom",
        )

    assert result.system_proposed_score_1_10 is not None
    assert 1 <= result.system_proposed_score_1_10 <= 10
    assert result.normalized_score_0_1 is not None
    assert 0.0 <= result.normalized_score_0_1 <= 1.0
    # No review flag fires on the dense seed — every REQUIRED
    # indicator is observed DIRECT.
    assert result.review_flags == ()
    assert result.human_review_required is False


def test_score_category_for_country_political_freedom_components_cover_groups(
    database_url: str,
) -> None:
    """The seam emits one :class:`ScoreComponent` per rubric group.

    The realistic Mexico seed populates all 16 indicators, so the
    scorer emits a 3-group breakdown: 7 V-Dem + 7 BTI + 2 RSF
    components. Each component carries a single observation ref
    pointing at its underlying row.
    """
    _seed_mexico_political_freedom_bundle(database_url)

    with session_scope(database_url) as session:
        result = score_category_for_country(
            session,
            country_iso3=COUNTRY_ISO3,
            year=TARGET_YEAR,
            category_key="political_freedom",
        )

    by_group: dict[str, int] = {}
    for component in result.components:
        _, _, group_key = component.component_key.partition("__")
        by_group[group_key] = by_group.get(group_key, 0) + 1
    assert by_group == {
        "vdem_democracy_liberty": 7,
        "bti_political_transformation": 7,
        "rsf_press_freedom": 2,
    }


# ---------------------------------------------------------------------------
# Sparse / insufficient-data paths
# ---------------------------------------------------------------------------


def test_score_category_for_country_political_freedom_handles_sparse_bundle(
    database_url: str,
) -> None:
    """A bundle below the minimum-viable threshold emits an insufficient-data result.

    Seed exactly ONE source with a usable observation. The
    political_freedom plan requires
    ``minimum_viable_sources = 2`` so a single-source bundle
    must come back as ``is_insufficient_data = True`` with no
    score.
    """
    init_database(database_url)
    with session_scope(database_url) as session:
        country = seed_country(session)
        vdem = upsert_source(session, source_name=VDEM_SOURCE_NAME)
        add_observation(
            session,
            source_id=vdem.id,
            country_id=country.id,
            year=TARGET_YEAR,
            variable_name="vdem_v2x_polyarchy",
            raw_value="0.5000",
            normalized_value=0.50,
            unit="index",
            source_row_reference=(
                f"vdem:{COUNTRY_ISO3}:{TARGET_YEAR}:v2x_polyarchy"
            ),
        )

    with session_scope(database_url) as session:
        result = score_category_for_country(
            session,
            country_iso3=COUNTRY_ISO3,
            year=TARGET_YEAR,
            category_key="political_freedom",
        )

    assert result.is_insufficient_data is True
    assert result.system_proposed_score_1_10 is None
    assert result.normalized_score_0_1 is None
    assert result.human_review_required is True
    assert result.observation_refs == ()
    assert result.components == ()


__all__ = [
    "BTI_SOURCE_NAME",
    "RSF_SOURCE_NAME",
    "SECOND_COUNTRY_ISO3",
    "SECOND_COUNTRY_NAME",
    "SECOND_COUNTRY_REGION",
    "VDEM_SOURCE_NAME",
]
