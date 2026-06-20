"""Stage 9 production seam tests for the ``domestic_violence`` category.

Closes the reviewer blocker "production Stage 9 proof gap" for
the domestic-violence scorer. The single-category seam
(:func:`leaders_db.score.stage9.score_category_for_country`) is
the social-wellbeing happy path in :mod:`tests.test_score_stage9`;
this file is the sibling that covers the same end-to-end
production path for the ``domestic_violence`` category —
seeding an isolated SQLite DB with PTS / CIRIGHTS / UCDP / V-Dem
``source_observations`` rows, then calling
``score_category_for_country`` with
``category_key='domestic_violence'`` to prove the
``build_category_evidence_bundle`` → ``score_category_bundle`` →
``score_domestic_violence`` chain returns a
:class:`~leaders_db.score.results.ScoreResult`.

The all-countries batch seam
(:func:`leaders_db.score.stage9.score_category_for_all_countries`)
plus the CSV-facing proof for the insufficient-data rationale
contract live in the focused sibling
:mod:`tests.test_score_stage9_domestic_violence_batch` so this
file stays under the 400-line convention.
"""

from __future__ import annotations

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
# them to the right canonical short keys (``pts`` / ``cirights`` /
# ``ucdp`` / ``vdem``).
PTS_SOURCE_NAME: str = "Political Terror Scale (PTS) (test)"
CIRIGHTS_SOURCE_NAME: str = "CIRI Human Rights Data Project (test)"
UCDP_SOURCE_NAME: str = "UCDP (Uppsala Conflict Data Program) (test)"
VDEM_SOURCE_NAME: str = "V-Dem (Varieties of Democracy) (test)"

# Per-source ``(variable_name, normalized_value)`` pairs to seed
# for the dense Mexico bundle. Mirrors
# :func:`tests._domestic_violence_factories.realistic_domestic_violence_observations`
# — all 17 DOMESTIC_VIOLENCE_PLAN indicators populated across 4
# sources.
DOMESTIC_VIOLENCE_SEED: tuple[
    tuple[str, str, tuple[tuple[str, float], ...]], ...
] = (
    (
        PTS_SOURCE_NAME, "pts",
        (
            ("pts_amnesty_score", 0.65),
            ("pts_human_rights_watch_score", 0.60),
            ("pts_state_dept_score", 0.55),
        ),
    ),
    (
        CIRIGHTS_SOURCE_NAME, "cirights",
        (
            ("cirights_physint", 0.65),
            ("cirights_repression", 0.70),
            ("cirights_civpol", 0.60),
            ("cirights_disap", 0.55),
            ("cirights_kill", 0.50),
            ("cirights_polpris", 0.55),
            ("cirights_tort", 0.60),
        ),
    ),
    (
        UCDP_SOURCE_NAME, "ucdp",
        (
            ("ucdp_onesided_events", 0.65),
            ("ucdp_onesided_fatalities", 0.70),
        ),
    ),
    (
        VDEM_SOURCE_NAME, "vdem",
        (
            ("vdem_v2x_clphy", 0.65),
            ("vdem_v2x_clpol", 0.55),
            ("vdem_v2x_clpriv", 0.60),
            ("vdem_v2csreprss", 0.45),
            ("vdem_v2clkill", 0.50),
        ),
    ),
)


def _seed_mexico_domestic_violence_bundle(database_url: str) -> None:
    """Seed Mexico 2023 with PTS + CIRIGHTS + UCDP + V-Dem observations.

    Four distinct sources — well above the plan's
    ``minimum_viable_sources = 2``. All 17
    DOMESTIC_VIOLENCE_PLAN indicators populated so the bundle
    builder emits a usable bundle and the dispatcher routes it
    to :func:`score_domestic_violence` for a real
    (non-insufficient-data) result.

    Also reused by the batch-seam sibling
    (:mod:`tests.test_score_stage9_domestic_violence_batch`) which
    imports this helper.
    """
    from leaders_db.db.engine import init_database

    init_database(database_url)
    with session_scope(database_url) as session:
        country = seed_country(session)
        for source_name, source_short, rows in DOMESTIC_VIOLENCE_SEED:
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


# ---------------------------------------------------------------------------
# Single-country seam
# ---------------------------------------------------------------------------


def test_score_category_for_country_domestic_violence_returns_score_result(
    database_url: str,
) -> None:
    """The seam composes bundle-builder + dispatcher and returns a ScoreResult.

    Boundary test: fails if either
    :func:`build_category_evidence_bundle` or
    :func:`score_category_bundle` is removed/replaced with a stub,
    or if the ``domestic_violence`` entry is dropped from
    :data:`leaders_db.score.dispatch._SCORERS`.
    """
    _seed_mexico_domestic_violence_bundle(database_url)

    with session_scope(database_url) as session:
        result = score_category_for_country(
            session,
            country_iso3=COUNTRY_ISO3,
            year=TARGET_YEAR,
            category_key="domestic_violence",
        )

    assert isinstance(result, ScoreResult)
    assert result.category_key == "domestic_violence"
    assert result.iso3 == COUNTRY_ISO3
    assert result.year == TARGET_YEAR


def test_score_category_for_country_domestic_violence_emits_observation_refs(
    database_url: str,
) -> None:
    """The seam produces a result with one observation ref per indicator.

    All 17 DOMESTIC_VIOLENCE_PLAN indicators are present across
    the four seeded sources, so the bundle builder emits 17
    :class:`EvidenceObservation` rows and the scorer carries 17
    refs in the flat :attr:`ScoreResult.observation_refs`.
    """
    _seed_mexico_domestic_violence_bundle(database_url)

    with session_scope(database_url) as session:
        result = score_category_for_country(
            session,
            country_iso3=COUNTRY_ISO3,
            year=TARGET_YEAR,
            category_key="domestic_violence",
        )

    assert result.is_insufficient_data is False
    assert len(result.observation_refs) == 17
    assert {ref.source_key for ref in result.observation_refs} == {
        "pts", "cirights", "ucdp", "vdem"
    }


def test_score_category_for_country_domestic_violence_emits_concrete_score(
    database_url: str,
) -> None:
    """The seam emits a 1..10 score for the dense Mexico seed."""
    _seed_mexico_domestic_violence_bundle(database_url)

    with session_scope(database_url) as session:
        result = score_category_for_country(
            session,
            country_iso3=COUNTRY_ISO3,
            year=TARGET_YEAR,
            category_key="domestic_violence",
        )

    assert result.system_proposed_score_1_10 is not None
    assert 1 <= result.system_proposed_score_1_10 <= 10
    assert result.normalized_score_0_1 is not None
    assert 0.0 <= result.normalized_score_0_1 <= 1.0
    # No review flag fires on the dense seed — every REQUIRED
    # indicator is observed DIRECT.
    assert result.review_flags == ()
    assert result.human_review_required is False


def test_score_category_for_country_domestic_violence_components_cover_groups(
    database_url: str,
) -> None:
    """The seam emits one :class:`ScoreComponent` per rubric group.

    The realistic Mexico seed populates all 17 indicators, so
    the scorer emits a 4-group breakdown: 3 PTS + 7 CIRIGHTS + 2
    UCDP + 5 V-Dem components. Each component carries a single
    observation ref pointing at its underlying row.
    """
    _seed_mexico_domestic_violence_bundle(database_url)

    with session_scope(database_url) as session:
        result = score_category_for_country(
            session,
            country_iso3=COUNTRY_ISO3,
            year=TARGET_YEAR,
            category_key="domestic_violence",
        )

    by_group: dict[str, int] = {}
    for component in result.components:
        _, _, group_key = component.component_key.partition("__")
        by_group[group_key] = by_group.get(group_key, 0) + 1
    assert by_group == {
        "pts_state_terror": 3,
        "cirights_physint_repression": 7,
        "ucdp_one_sided_violence": 2,
        "vdem_civil_liberties_repression": 5,
    }


# ---------------------------------------------------------------------------
# Sparse / insufficient-data paths
# ---------------------------------------------------------------------------


def test_score_category_for_country_domestic_violence_handles_sparse_bundle(
    database_url: str,
) -> None:
    """A bundle below the minimum-viable threshold emits an insufficient-data result.

    Seed exactly ONE source with a usable observation. The
    domestic-violence plan requires
    ``minimum_viable_sources = 2`` so a single-source bundle
    must come back as ``is_insufficient_data = True`` with no
    score.
    """
    from leaders_db.db.engine import init_database

    init_database(database_url)
    with session_scope(database_url) as session:
        country = seed_country(session)
        pts = upsert_source(session, source_name=PTS_SOURCE_NAME)
        add_observation(
            session,
            source_id=pts.id,
            country_id=country.id,
            year=TARGET_YEAR,
            variable_name="pts_amnesty_score",
            raw_value="0.6500",
            normalized_value=0.65,
            unit="index",
            source_row_reference=(
                f"pts:{COUNTRY_ISO3}:{TARGET_YEAR}:pts_amnesty_score"
            ),
        )

    with session_scope(database_url) as session:
        result = score_category_for_country(
            session,
            country_iso3=COUNTRY_ISO3,
            year=TARGET_YEAR,
            category_key="domestic_violence",
        )

    assert result.is_insufficient_data is True
    assert result.system_proposed_score_1_10 is None
    assert result.normalized_score_0_1 is None
    assert result.human_review_required is True
    assert result.observation_refs == ()
    assert result.components == ()


__all__ = [
    "CIRIGHTS_SOURCE_NAME",
    "PTS_SOURCE_NAME",
    "UCDP_SOURCE_NAME",
    "VDEM_SOURCE_NAME",
    "_seed_mexico_domestic_violence_bundle",
]
