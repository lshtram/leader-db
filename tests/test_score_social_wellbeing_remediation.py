"""Regression tests for the reviewer blockers flagged against the
social-wellbeing scorer.

These tests pin the **defence-in-depth** behaviours that the
reviewer required in addition to the happy-path contract:

1. ``has_minimum_viable_usable_evidence`` gate: a source whose
   observations all carry ``normalized_value=None`` does **not**
   count as viable evidence. The previous loose
   ``has_minimum_viable_evidence`` gate counted such a source as
   viable, so the scorer could clear the minimum-viable threshold
   on null-only observations.
2. Client-matrix exclusion at the scorer boundary: a contaminated
   bundle carrying ``client_existing`` / ``client_matrix``
   observations must not propagate those observations into the
   result's components, refs, or contributions. The scorer is the
   last line of defence in case the Stage 5 bundle builder forgets
   the upstream exclusion rule.
3. Production wiring: ``score_social_wellbeing`` is exposed from the
   package root (:mod:`leaders_db.score`), not only from the
   sub-module path. The boundary test fails if the export is
   removed — that catches "we forgot to wire the scorer" regressions
   before they reach the pipeline.

The happy-path tests live in
:mod:`tests.test_score_social_wellbeing`. The original
flag-detection tests live in
:mod:`tests.test_score_social_wellbeing_flags`.

Style invariants (per ``docs/coding-guidelines.md``):

- ``from __future__ import annotations`` for forward-reference
  safety.
- Type hints on test parameters.
- No ``print()``, no ``TODO(debug)``, no scratch code.
"""

from __future__ import annotations

import pytest

from leaders_db.score.evidence import (
    Direction,
    EvidenceObservation,
    TemporalKind,
)
from leaders_db.score.results import ScoreResult
from leaders_db.score.social_wellbeing import score_social_wellbeing
from tests._social_wellbeing_factories import (
    make_bundle,
    make_obs,
)

# ---------------------------------------------------------------------------
# (1) Insufficient-data gate counts only usable observations
# ---------------------------------------------------------------------------


def test_insufficient_data_when_one_source_has_only_null_normalized() -> None:
    """A source whose only observation is ``normalized_value=None`` is not viable.

    Regression test for reviewer blocker #1 ("insufficient-data
    gate counts unusable observations as viable evidence"). The
    bundle has two distinct source keys (``undp_hdi`` and ``vdem``)
    so the loose ``has_minimum_viable_evidence`` gate would clear
    the threshold — but ``undp_hdi`` only contributes a
    ``normalized_value=None`` row, so the usable-evidence gate must
    route the bundle to the insufficient-data path.
    """
    null_obs = EvidenceObservation(
        source_key="undp_hdi",
        source_name="undp_hdi (test fixture)",
        variable_name="undp_hdi_hdi",
        raw_value="",
        numeric_value=None,
        normalized_value=None,
        unit="index",
        direction=Direction.HIGHER_IS_BETTER,
        observation_year=2023,
        target_year=2023,
        temporal_kind=TemporalKind.DIRECT,
        source_row_reference=None,
        authority_score=70,
        specificity_score=80,
    )
    # vdem contributes one usable observation. The bundle's
    # distinct source count is 2 (undp_hdi + vdem) but the distinct
    # usable source count is 1 (vdem only).
    bundle = make_bundle(
        observations=[null_obs, make_obs("vdem_v2x_egal", "vdem", 0.55)]
    )
    result = score_social_wellbeing(bundle)

    assert isinstance(result, ScoreResult)
    assert result.is_insufficient_data is True
    assert result.normalized_score_0_1 is None
    assert result.system_proposed_score_1_10 is None
    assert result.components == ()
    assert result.observation_refs == ()
    # Both insufficient-data and sparse-data flags fire — this is
    # the standard insufficient-data payload per the scorer
    # contract.
    assert result.human_review_required is True


def test_has_minimum_viable_usable_evidence_property_distinguishes() -> None:
    """The bundle property exposes the loose-vs-usable gate distinction.

    Companion test for the regression above: the bundle's
    :attr:`CategoryEvidenceBundle.has_minimum_viable_evidence` is
    ``True`` (two distinct source keys), but
    :attr:`CategoryEvidenceBundle.has_minimum_viable_usable_evidence`
    is ``False`` (only one distinct usable source). The scorer uses
    the latter; this test pins both for documentation.
    """
    null_obs = EvidenceObservation(
        source_key="undp_hdi",
        source_name="undp_hdi (test fixture)",
        variable_name="undp_hdi_hdi",
        raw_value="",
        numeric_value=None,
        normalized_value=None,
        unit="index",
        direction=Direction.HIGHER_IS_BETTER,
        observation_year=2023,
        target_year=2023,
        temporal_kind=TemporalKind.DIRECT,
        source_row_reference=None,
        authority_score=70,
        specificity_score=80,
    )
    bundle = make_bundle(
        observations=[null_obs, make_obs("vdem_v2x_egal", "vdem", 0.55)]
    )
    # Loose gate: distinct source count ≥ plan's minimum_viable_sources.
    assert bundle.has_minimum_viable_evidence is True
    # Usable gate: distinct source count of *usable* observations.
    assert bundle.has_minimum_viable_usable_evidence is False


# ---------------------------------------------------------------------------
# (2) Client matrix exclusion at the scorer boundary
# ---------------------------------------------------------------------------


def test_score_social_wellbeing_strips_client_observations_at_boundary() -> None:
    """A contaminated bundle never produces a client-derived component.

    Regression test for reviewer blocker #2 ("client matrix exclusion
    not enforced at scorer boundary"). The Stage 5 bundle builder
    already excludes ``client_existing`` / ``client_matrix`` upstream
    (see ``EXCLUDED_SOURCE_KEYS`` in
    :mod:`leaders_db.score.source_plans`), but the scorer is the last
    line of defence in case a contaminated bundle is hand-built in a
    test or piped from a future stage. The function must silently
    skip client observations (review-safe behaviour: the rest of the
    result is still auditable, and the reviewer can spot the
    contamination upstream).
    """
    client_obs = EvidenceObservation(
        source_key="client_existing",
        source_name="client_existing (test fixture)",
        variable_name="undp_hdi_hdi",
        raw_value="9",
        numeric_value=9.0,
        normalized_value=0.9,  # would dominate the score if consumed
        unit="score_0_10",
        direction=Direction.HIGHER_IS_BETTER,
        observation_year=2023,
        target_year=2023,
        temporal_kind=TemporalKind.DIRECT,
        source_row_reference="client_existing:undp_hdi_hdi:MEX",
        authority_score=100,
        specificity_score=100,
    )
    clean_obs = (
        make_obs("undp_hdi_hdi", "undp_hdi", 0.78),
        make_obs("vdem_v2x_egal", "vdem", 0.55),
    )
    # Build a bundle that includes a client observation alongside
    # the two clean observations from two distinct sources.
    bundle = make_bundle(observations=[client_obs, *clean_obs])

    result = score_social_wellbeing(bundle)

    assert isinstance(result, ScoreResult)
    # No client source key appears in components, refs, or
    # contributions.
    for component in result.components:
        assert component.source_key not in {"client_existing", "client_matrix"}
    for ref in result.observation_refs:
        assert ref.source_key not in {"client_existing", "client_matrix"}
    # The variable that the client observation would have supplied
    # (undp_hdi_hdi) is still observed via the clean undp_hdi row —
    # but that component's source_key must be undp_hdi, not
    # client_existing.
    hdi_components = [
        c for c in result.components if c.variable_name == "undp_hdi_hdi"
    ]
    assert hdi_components, "undp_hdi_hdi should be observed via undp_hdi"
    for component in hdi_components:
        assert component.source_key == "undp_hdi"
    # The result is a real score (not insufficient-data) and the
    # client observation did not silently flip the result.
    assert result.is_insufficient_data is False
    assert result.normalized_score_0_1 is not None
    assert result.system_proposed_score_1_10 is not None


def test_score_social_wellbeing_only_client_observations_means_insufficient_data() -> (
    None
):
    """If every observation is a client row, the bundle has no usable evidence.

    Companion test for the boundary exclusion: stripping the only
    two distinct sources of evidence yields zero usable observations
    and routes the bundle to insufficient-data. This is the
    "review-safe" behaviour — the scorer does not raise on a
    contaminated bundle, it just doesn't trust the client rows as
    evidence and reports insufficient_data.
    """
    client_obs_hdi = EvidenceObservation(
        source_key="client_existing",
        source_name="client_existing (test fixture)",
        variable_name="undp_hdi_hdi",
        raw_value="9",
        numeric_value=9.0,
        normalized_value=0.9,
        unit="score_0_10",
        direction=Direction.HIGHER_IS_BETTER,
        observation_year=2023,
        target_year=2023,
        temporal_kind=TemporalKind.DIRECT,
        source_row_reference="client_existing:undp_hdi_hdi:MEX",
        authority_score=100,
        specificity_score=100,
    )
    client_obs_vdem = EvidenceObservation(
        source_key="client_matrix",
        source_name="client_matrix (test fixture)",
        variable_name="vdem_v2x_egal",
        raw_value="0.5",
        numeric_value=0.5,
        normalized_value=0.5,
        unit="index",
        direction=Direction.HIGHER_IS_BETTER,
        observation_year=2023,
        target_year=2023,
        temporal_kind=TemporalKind.DIRECT,
        source_row_reference="client_matrix:vdem_v2x_egal:MEX",
        authority_score=100,
        specificity_score=100,
    )
    bundle = make_bundle(
        observations=[client_obs_hdi, client_obs_vdem]
    )
    result = score_social_wellbeing(bundle)

    assert result.is_insufficient_data is True
    assert result.normalized_score_0_1 is None
    assert result.system_proposed_score_1_10 is None
    # No client-derived component or ref survived the boundary filter.
    assert result.components == ()
    assert result.observation_refs == ()


# ---------------------------------------------------------------------------
# (3) Production wiring — the scorer must be importable from the package root
# ---------------------------------------------------------------------------


def test_score_social_wellbeing_exported_from_package_root() -> None:
    """``score_social_wellbeing`` is exposed from ``leaders_db.score``.

    Regression test for reviewer blocker #3 ("test coverage does not
    prove production scorer wiring"). The scorer is registered as
    the production seam at the package root
    (:mod:`leaders_db.score`) — not only at the sub-module path
    (``leaders_db.score.social_wellbeing``). The Stage 9 pipeline
    imports the scorer from the package root, so removing the
    re-export silently breaks the wiring. This test fails if the
    export is removed.

    We import via the package root and verify the symbol resolves
    to the same callable that the sub-module exposes.
    """
    import leaders_db.score as score_pkg

    assert hasattr(score_pkg, "score_social_wellbeing"), (
        "leaders_db.score must re-export score_social_wellbeing "
        "so the production wiring is a single import"
    )
    assert score_pkg.score_social_wellbeing is score_social_wellbeing, (
        "leaders_db.score.score_social_wellbeing must be the same "
        "object as leaders_db.score.social_wellbeing.score_social_wellbeing "
        "— re-exported, not shadowed"
    )


def test_score_social_wellbeing_category_key_exported_from_package_root() -> (
    None
):
    """``CATEGORY_KEY`` is exposed from ``leaders_db.score``.

    Companion wiring test for the category identifier — the
    registry / dispatch layer reads ``CATEGORY_KEY`` from the
    package root, so removing the re-export breaks the dispatcher.
    """
    import leaders_db.score as score_pkg
    from leaders_db.score.social_wellbeing import CATEGORY_KEY

    assert hasattr(score_pkg, "CATEGORY_KEY"), (
        "leaders_db.score must re-export CATEGORY_KEY "
        "so the registry can read it from the package root"
    )
    assert score_pkg.CATEGORY_KEY == CATEGORY_KEY == "social_wellbeing"


# ---------------------------------------------------------------------------
# (4) Client contamination cannot inflate missingness or suppress SPARSE_DATA
# ---------------------------------------------------------------------------


def test_client_observation_cannot_suppress_sparse_data_flag() -> None:
    """A client observation must not flip ``total_observed`` over the sparse threshold.

    Regression test for reviewer blocker #4 ("missingness still
    counts ``bundle.observations`` directly"). The social-wellbeing
    plan declares 17 expected variables; the sparse-data threshold
    is ``observed_ratio < 0.5`` (less than half observed). This
    test pins two adjacent totals:

    - **Clean bundle** — 8 non-client observations covering 8
      distinct plan variables across 2 sources (so the
      minimum-viable gate clears). 8/17 ≈ 0.47 < 0.5 → the
      ``SPARSE_DATA`` flag fires. ``total_observed == 8``.
    - **Contaminated bundle** — same 8 non-client observations plus
      1 client observation covering a 9th plan variable. Without the
      fix the missingness summary counts the client row, so
      ``total_observed == 9`` and the 9/17 ≈ 0.529 ratio suppresses
      ``SPARSE_DATA``. With the fix the client observation is
      stripped before ``missingness`` is computed, so the result is
      identical to the clean bundle (same ``total_observed``, same
      ``SPARSE_DATA`` flag, same ``human_review_required``, no
      client-derived component / ref / contribution).

    The two ``ScoreResult`` payloads must be **identical** in
    missingness / review_flags / human_review_required, and the
    contaminated result must contain zero client source keys in
    its ``components`` / ``observation_refs``.
    """
    from leaders_db.score.results import ReviewFlag

    # 8 non-client observations covering 8 distinct plan variables
    # across 3 sources (undp_hdi + vdem + world_bank_wdi). All
    # DIRECT, all normalized — well-formed usable evidence.
    clean_obs = [
        # undp_hdi (5 distinct variables)
        make_obs("undp_hdi_hdi", "undp_hdi", 0.78),
        make_obs("undp_hdi_life_expectancy", "undp_hdi", 0.70),
        make_obs(
            "undp_hdi_expected_years_schooling", "undp_hdi", 0.75
        ),
        make_obs("undp_hdi_mean_years_schooling", "undp_hdi", 0.65),
        make_obs("undp_hdi_gni_per_capita", "undp_hdi", 0.70),
        # vdem (2 distinct variables)
        make_obs("vdem_v2x_egal", "vdem", 0.55),
        make_obs("vdem_v2clsocgrp_ord", "vdem", 0.50),
        # world_bank_wdi (1 distinct variable)
        make_obs("wdi_gini_index", "world_bank_wdi", 0.60),
    ]

    # Sanity: the clean bundle is below the 0.5 sparse threshold
    # (8/17 ≈ 0.47) AND clears the minimum-viable-sources gate
    # (3 distinct sources).
    clean_bundle = make_bundle(observations=clean_obs)
    assert clean_bundle.has_minimum_viable_usable_evidence is True

    # Build the contaminated bundle: identical 8 non-client
    # observations + 1 client observation covering a NEW 9th plan
    # variable (``who_gho_under5_mortality``). The client observation
    # is well-formed (DIRECT, normalized_value=0.85) — without the
    # fix it would be counted as "observed" and flip
    # ``total_observed`` from 8 → 9 (ratio 0.47 → 0.529), suppressing
    # ``SPARSE_DATA``.
    client_obs = EvidenceObservation(
        source_key="client_existing",
        source_name="client_existing (test fixture)",
        variable_name="who_gho_under5_mortality",
        raw_value="0.85",
        numeric_value=0.85,
        normalized_value=0.85,
        unit="index",
        direction=Direction.LOWER_IS_BETTER,
        observation_year=2023,
        target_year=2023,
        temporal_kind=TemporalKind.DIRECT,
        source_row_reference=(
            "client_existing:who_gho_under5_mortality:MEX"
        ),
        authority_score=100,
        specificity_score=100,
    )
    contaminated_bundle = make_bundle(
        observations=[*clean_obs, client_obs]
    )

    # Run the scorer on both bundles.
    clean_result = score_social_wellbeing(clean_bundle)
    contaminated_result = score_social_wellbeing(contaminated_bundle)

    # 1. Missingness is identical — the client observation cannot
    #    inflate ``total_observed`` (or change ``by_reason`` /
    #    ``by_severity``, which both bundles leave empty here).
    assert clean_result.missingness is not None
    assert contaminated_result.missingness is not None
    assert (
        clean_result.missingness.total_observed
        == contaminated_result.missingness.total_observed
        == 8
    ), (
        "client_existing/client_matrix observations must not "
        "inflate missingness.total_observed (got "
        f"clean={clean_result.missingness.total_observed}, "
        f"contaminated={contaminated_result.missingness.total_observed})"
    )
    assert (
        clean_result.missingness.total_expected
        == contaminated_result.missingness.total_expected
    )
    assert (
        clean_result.missingness.by_reason
        == contaminated_result.missingness.by_reason
    )
    assert (
        clean_result.missingness.by_severity
        == contaminated_result.missingness.by_severity
    )

    # 2. Review flags are identical — the client observation must
    #    not flip SPARSE_DATA off.
    assert ReviewFlag.SPARSE_DATA in clean_result.review_flags, (
        "precondition: 8/17 < 0.5 must fire SPARSE_DATA on the "
        "clean bundle so the regression test is meaningful"
    )
    assert (
        clean_result.review_flags
        == contaminated_result.review_flags
    ), (
        "review_flags must be identical between the clean and "
        "contaminated bundles — a client observation cannot "
        "suppress SPARSE_DATA"
    )
    assert ReviewFlag.SPARSE_DATA in contaminated_result.review_flags, (
        "client observation must not suppress SPARSE_DATA — the "
        "filtered scoring_observations set is the single source of "
        "truth for missingness"
    )

    # 3. human_review_required is identical.
    assert (
        clean_result.human_review_required
        == contaminated_result.human_review_required
    )

    # 4. No client source key appears in components, refs, or
    #    contributions of the contaminated result.
    for component in contaminated_result.components:
        assert component.source_key not in {
            "client_existing",
            "client_matrix",
        }
    for ref in contaminated_result.observation_refs:
        assert ref.source_key not in {
            "client_existing",
            "client_matrix",
        }
    # The contamination contributed 0.0 to the normalized score —
    # the client's contribution never entered the result.
    clean_total_contribution = sum(
        c.contribution_0_1 for c in clean_result.components
    )
    contaminated_total_contribution = sum(
        c.contribution_0_1 for c in contaminated_result.components
    )
    assert clean_total_contribution == pytest.approx(
        contaminated_total_contribution
    ), (
        "client observation must not change the normalized score — "
        f"clean={clean_total_contribution}, "
        f"contaminated={contaminated_total_contribution}"
    )

    # 5. The contaminated result has the SAME score pair (normalized
    #    + 1..10) as the clean result.
    assert contaminated_result.normalized_score_0_1 == pytest.approx(
        clean_result.normalized_score_0_1
    )
    assert (
        contaminated_result.system_proposed_score_1_10
        == clean_result.system_proposed_score_1_10
    )


def test_client_observation_cannot_change_missingness_in_insufficient_path() -> (
    None
):
    """A client observation cannot change missingness in the insufficient-data path.

    Companion test for the insufficient-data path of the scorer:
    even when the bundle fails the minimum-viable-sources gate and
    routes to ``is_insufficient_data=True``, the missingness summary
    must still be computed from the filtered scoring observation
    set. A client observation in the bundle cannot inflate
    ``total_observed`` and change the ratio the rationale reports
    ("{total_observed}/{total_expected} plan indicator(s)
    observed").
    """
    from leaders_db.score.results import ReviewFlag

    # Clean bundle: 1 non-client observation from 1 source —
    # below the plan's minimum_viable_sources=2, so the bundle
    # routes to insufficient-data.
    clean_obs = make_obs("undp_hdi_hdi", "undp_hdi", 0.78)
    clean_bundle = make_bundle(observations=[clean_obs])

    # Contaminated bundle: same 1 non-client observation + 1 client
    # observation for a different variable. Without the fix the
    # missingness summary would count the client row, flipping
    # ``total_observed`` from 1 → 2.
    client_obs = EvidenceObservation(
        source_key="client_matrix",
        source_name="client_matrix (test fixture)",
        variable_name="vdem_v2x_egal",
        raw_value="0.5",
        numeric_value=0.5,
        normalized_value=0.5,
        unit="index",
        direction=Direction.HIGHER_IS_BETTER,
        observation_year=2023,
        target_year=2023,
        temporal_kind=TemporalKind.DIRECT,
        source_row_reference="client_matrix:vdem_v2x_egal:MEX",
        authority_score=100,
        specificity_score=100,
    )
    contaminated_bundle = make_bundle(
        observations=[clean_obs, client_obs]
    )

    clean_result = score_social_wellbeing(clean_bundle)
    contaminated_result = score_social_wellbeing(contaminated_bundle)

    # Both routes land on insufficient-data.
    assert clean_result.is_insufficient_data is True
    assert contaminated_result.is_insufficient_data is True

    # Missingness is identical — the client observation cannot
    # inflate ``total_observed`` even on the insufficient-data
    # branch.
    assert clean_result.missingness is not None
    assert contaminated_result.missingness is not None
    assert (
        clean_result.missingness.total_observed
        == contaminated_result.missingness.total_observed
        == 1
    ), (
        "client_existing/client_matrix observations must not "
        "inflate missingness.total_observed on the "
        "insufficient-data path either"
    )

    # The flags are identical (both insufficient-data + sparse-data).
    assert clean_result.review_flags == contaminated_result.review_flags
    assert ReviewFlag.INSUFFICIENT_DATA in contaminated_result.review_flags
    assert ReviewFlag.SPARSE_DATA in contaminated_result.review_flags
