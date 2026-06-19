"""Stage 5 evidence bundle — **contract** tests.

These tests pin the *positive* behavior of the typed contract
defined in :mod:`leaders_db.score.evidence`:

- enum membership and value strings (Direction, TemporalKind,
  MissingReason, MissingSeverity, IndicatorRole, SparseDataPolicy);
- the shape and properties of :class:`EvidenceObservation`
  (including :attr:`has_locator` and the per-row scalar fields);
- the shape and properties of :class:`MissingObservation`;
- the :class:`CategorySourcePlan` helpers
  (``expected_variables``, ``role_of`` / ``is_required_variable`` /
  ``is_preferred_variable`` / ``is_fallback_variable``,
  ``direction_of``, ``default_indicator_weight``,
  ``default_source_weight``, ``minimum_viable_met``);
- the :class:`CategoryEvidenceBundle` counts
  (:attr:`available_count`, :attr:`missing_count`,
  :attr:`has_minimum_viable_evidence`,
  :attr:`primary_missing_observations`);
- the bundle's read-only :attr:`~CategoryEvidenceBundle.category_metadata`
  slot — defaults, ``None`` handling, and content preservation.

Immutability and rejection tests live in
:mod:`tests.test_score_evidence_validation`.

These tests are deliberately DB-free: no SQLAlchemy session, no
``source_observations`` query, no filesystem writes. The bundle
models are pure data carriers; wiring them to the database is the
Stage 5 orchestrator's job (see ``leaders_db.resolve.indicators``).
"""

from __future__ import annotations

from leaders_db.score.evidence import (
    CategorySourcePlan,
    Direction,
    IndicatorRole,
    IndicatorSpec,
    MissingReason,
    MissingSeverity,
    SparseDataPolicy,
    TemporalKind,
)
from tests._score_evidence_factories import (
    make_bundle,
    make_missing,
    make_observation,
    make_plan,
)

# ---------------------------------------------------------------------------
# Locator preservation + has_locator
# ---------------------------------------------------------------------------


def test_observation_with_raw_locator_preserves_it_and_has_locator_true() -> None:
    locator = "country_text_id=MEX;year=2023;col=v2x_polyarchy"
    obs = make_observation(source_row_reference=locator)

    # The raw locator is preserved verbatim on the typed object.
    assert obs.source_row_reference == locator
    # has_locator is True when a non-empty locator is present (REQ-LAKE-004).
    assert obs.has_locator is True


def test_observation_without_locator_has_has_locator_false() -> None:
    obs = make_observation(source_row_reference=None)
    assert obs.has_locator is False


def test_observation_with_blank_locator_has_has_locator_false() -> None:
    # A whitespace-only locator is not a usable traceback (REQ-LAKE-004).
    obs = make_observation(source_row_reference="   ")
    assert obs.has_locator is False


# ---------------------------------------------------------------------------
# Missing observation: explicit, counted, and primary filterable
# ---------------------------------------------------------------------------


def test_missing_expected_primary_observation_is_explicit_and_counted() -> None:
    primary_missing = make_missing(
        source_key="ti_cpi",
        variable_name="cpi_score",
        reason=MissingReason.SOURCE_NOT_IMPLEMENTED,
        severity=MissingSeverity.PRIMARY,
    )
    bundle = make_bundle(missing=[primary_missing])

    # The missing observation is present on the bundle and counted.
    assert bundle.missing_count == 1
    assert bundle.missing[0] is primary_missing
    # And it shows up in the primary subset.
    assert primary_missing in bundle.primary_missing_observations
    assert len(bundle.primary_missing_observations) == 1


def test_bundle_available_count_and_missing_count_are_distinct() -> None:
    obs = make_observation()
    missing = make_missing(severity=MissingSeverity.PRIMARY)
    bundle = make_bundle(observations=[obs], missing=[missing])

    assert bundle.available_count == 1
    assert bundle.missing_count == 1
    # Empty default bundle reports zero on both counts.
    assert make_bundle().available_count == 0
    assert make_bundle().missing_count == 0


# ---------------------------------------------------------------------------
# Temporal kinds: proxy and stale are accepted and represented
# ---------------------------------------------------------------------------


def test_proxy_observation_is_accepted_and_represented() -> None:
    obs = make_observation(
        observation_year=2022,
        temporal_kind=TemporalKind.PROXY,
        notes="UNDP HDI 2022 used as 2023 proxy",
    )
    assert obs.temporal_kind is TemporalKind.PROXY
    assert obs.observation_year == 2022
    assert obs.notes is not None and "proxy" in obs.notes


def test_stale_observation_is_accepted_and_represented() -> None:
    obs = make_observation(
        source_key="polity_v",
        variable_name="polity2",
        observation_year=2018,
        temporal_kind=TemporalKind.STALE,
        notes="Polity V 2018 used as a stale political-freedom backstop",
    )
    assert obs.temporal_kind is TemporalKind.STALE
    assert obs.observation_year == 2018
    assert obs.notes is not None and "stale" in obs.notes


def test_temporal_kind_enum_lists_proxy_and_stale() -> None:
    # The contract explicitly enumerates these values (architecture §
    # "Evidence Bundle Contract"); pin them so a rename does not silently
    # break downstream scoring code.
    kinds = {k.value for k in TemporalKind}
    assert kinds == {"direct", "proxy", "stale", "not_available"}


def test_not_available_observation_may_omit_year() -> None:
    obs = make_observation(
        observation_year=None,
        temporal_kind=TemporalKind.NOT_AVAILABLE,
        source_row_reference=None,
        raw_value=None,
        numeric_value=None,
        normalized_value=None,
    )
    assert obs.temporal_kind is TemporalKind.NOT_AVAILABLE
    assert obs.observation_year is None
    assert obs.has_locator is False


# ---------------------------------------------------------------------------
# Minimum viable evidence
# ---------------------------------------------------------------------------


def test_minimum_viable_met_requires_distinct_sources() -> None:
    plan = make_plan(minimum_viable_sources=2)

    # One observation, one source -> below threshold.
    assert plan.minimum_viable_met([make_observation(source_key="vdem")]) is False

    # Two observations from the same source still count as one distinct source.
    same_source = [
        make_observation(source_key="vdem", variable_name="v2x_polyarchy"),
        make_observation(source_key="vdem", variable_name="v2x_libdem"),
    ]
    assert plan.minimum_viable_met(same_source) is False

    # Two observations from two distinct sources -> meets the threshold.
    mixed = [
        make_observation(source_key="vdem", variable_name="v2x_polyarchy"),
        make_observation(
            source_key="wgi",
            source_name="World Bank WGI",
            variable_name="wgi_control_of_corruption",
        ),
    ]
    assert plan.minimum_viable_met(mixed) is True


def test_minimum_viable_met_threshold_is_inclusive() -> None:
    plan = make_plan(minimum_viable_sources=2)
    two = [
        make_observation(source_key="vdem"),
        make_observation(
            source_key="wgi", variable_name="wgi_control_of_corruption"
        ),
    ]
    assert plan.minimum_viable_met(two) is True


def test_bundle_has_minimum_viable_evidence_uses_plan_helper() -> None:
    plan = make_plan(minimum_viable_sources=2)
    obs_vdem = make_observation(
        source_key="vdem", variable_name="v2x_polyarchy"
    )
    obs_wgi = make_observation(
        source_key="wgi",
        source_name="World Bank WGI",
        variable_name="wgi_control_of_corruption",
    )

    # Only one source -> not yet minimum-viable.
    partial = make_bundle(observations=[obs_vdem], plan=plan)
    assert partial.has_minimum_viable_evidence is False

    # Two sources -> meets the threshold.
    full = make_bundle(observations=[obs_vdem, obs_wgi], plan=plan)
    assert full.has_minimum_viable_evidence is True


def test_bundle_usable_observations_excludes_null_normalized_rows() -> None:
    """``usable_observations`` skips rows whose ``normalized_value`` is None.

    Per-category scorers that gate on the minimum-viable threshold
    to decide between a provisional score and
    :attr:`~leaders_db.score.results.ScoreResult.is_insufficient_data`
    use :attr:`CategoryEvidenceBundle.has_minimum_viable_usable_evidence`
    (which is built from :attr:`usable_observations`); the loose
    :attr:`has_minimum_viable_evidence` gate would otherwise count a
    source whose row arrived but whose ``normalized_value`` is
    ``None`` as viable evidence.
    """
    plan = make_plan(minimum_viable_sources=2)
    usable_vdem = make_observation(
        source_key="vdem",
        variable_name="v2x_polyarchy",
        normalized_value=0.7,
    )
    null_wgi = make_observation(
        source_key="wgi",
        source_name="World Bank WGI",
        variable_name="wgi_control_of_corruption",
        normalized_value=None,
    )

    bundle = make_bundle(
        observations=[usable_vdem, null_wgi], plan=plan
    )

    # Loose gate: distinct source count includes the null row.
    assert bundle.has_minimum_viable_evidence is True
    # Usable gate: only the vdem row is usable; the null wgi row
    # is filtered out, leaving only one distinct usable source.
    assert len(bundle.usable_observations) == 1
    assert bundle.has_minimum_viable_usable_evidence is False


def test_bundle_usable_observations_excludes_client_source_keys() -> None:
    """``usable_observations`` also strips client-matrix source keys.

    Defence-in-depth: the Stage 5 bundle builder already excludes
    :data:`~leaders_db.score.source_plans.EXCLUDED_SOURCE_KEYS`
    upstream; the bundle's :attr:`usable_observations` view
    re-applies the filter so the scorer cannot treat a contaminated
    bundle as carrying real evidence.
    """
    plan = make_plan(minimum_viable_sources=2)
    usable_vdem = make_observation(
        source_key="vdem",
        variable_name="v2x_polyarchy",
        normalized_value=0.7,
    )
    client_wgi = make_observation(
        source_key="client_existing",
        source_name="client_existing (test fixture)",
        variable_name="wgi_control_of_corruption",
        normalized_value=0.7,
    )

    bundle = make_bundle(
        observations=[usable_vdem, client_wgi], plan=plan
    )

    # Loose gate sees two distinct sources (vdem + client_existing).
    assert bundle.has_minimum_viable_evidence is True
    # Usable gate strips the client row; only vdem survives.
    assert len(bundle.usable_observations) == 1
    assert bundle.usable_observations[0].source_key == "vdem"
    assert bundle.has_minimum_viable_usable_evidence is False


# ---------------------------------------------------------------------------
# primary_missing_observations filters severity PRIMARY
# ---------------------------------------------------------------------------


def test_primary_missing_observations_filters_severity_primary() -> None:
    primary_a = make_missing(
        source_key="ti_cpi",
        variable_name="cpi_score",
        severity=MissingSeverity.PRIMARY,
    )
    primary_b = make_missing(
        source_key="freedom_house",
        variable_name="fh_total",
        severity=MissingSeverity.PRIMARY,
    )
    important = make_missing(
        source_key="rsf_press_freedom",
        variable_name="rsf_score",
        severity=MissingSeverity.IMPORTANT,
    )
    optional = make_missing(
        source_key="bti",
        variable_name="bti_status",
        severity=MissingSeverity.OPTIONAL,
    )
    bundle = make_bundle(missing=[primary_a, important, optional, primary_b])

    # All four are present on the bundle.
    assert bundle.missing_count == 4
    # Only the two PRIMARY severities make it into the primary subset, in
    # the original list order.
    assert bundle.primary_missing_observations == (primary_a, primary_b)


def test_primary_missing_observations_is_empty_when_no_primary() -> None:
    bundle = make_bundle(
        missing=[
            make_missing(severity=MissingSeverity.IMPORTANT),
            make_missing(severity=MissingSeverity.OPTIONAL),
        ]
    )
    assert bundle.primary_missing_observations == ()


# ---------------------------------------------------------------------------
# Plan: is_required_variable + role helpers
# ---------------------------------------------------------------------------


def test_is_required_variable_matches_required_role() -> None:
    # The default fixture sets both indicators as REQUIRED.
    plan = make_plan()
    assert plan.is_required_variable("v2x_polyarchy") is True
    assert plan.is_required_variable("wgi_control_of_corruption") is True
    assert plan.is_required_variable("not_in_plan") is False
    assert plan.is_required_variable("") is False


def test_role_helpers_distinguish_required_preferred_and_fallback() -> None:
    plan = make_plan(
        expected_indicators=(
            IndicatorSpec(
                "v_required", IndicatorRole.REQUIRED, Direction.HIGHER_IS_BETTER
            ),
            IndicatorSpec(
                "v_preferred",
                IndicatorRole.PREFERRED,
                Direction.HIGHER_IS_BETTER,
            ),
            IndicatorSpec(
                "v_fallback", IndicatorRole.FALLBACK, Direction.LOWER_IS_BETTER
            ),
        ),
    )

    # Each role helper returns True only for its own role.
    assert plan.is_required_variable("v_required") is True
    assert plan.is_preferred_variable("v_preferred") is True
    assert plan.is_fallback_variable("v_fallback") is True

    # Cross-checks: a REQUIRED indicator is not a PREFERRED or FALLBACK.
    assert plan.is_preferred_variable("v_required") is False
    assert plan.is_fallback_variable("v_required") is False
    # A PREFERRED indicator is not REQUIRED or FALLBACK.
    assert plan.is_required_variable("v_preferred") is False
    assert plan.is_fallback_variable("v_preferred") is False
    # A FALLBACK indicator is not REQUIRED or PREFERRED.
    assert plan.is_required_variable("v_fallback") is False
    assert plan.is_preferred_variable("v_fallback") is False

    # An unknown variable is not in any role.
    assert plan.is_required_variable("unknown") is False
    assert plan.is_preferred_variable("unknown") is False
    assert plan.is_fallback_variable("unknown") is False


def test_role_of_returns_role_or_none() -> None:
    plan = make_plan(
        expected_indicators=(
            IndicatorSpec(
                "v_required", IndicatorRole.REQUIRED, Direction.HIGHER_IS_BETTER
            ),
            IndicatorSpec(
                "v_fallback", IndicatorRole.FALLBACK, Direction.LOWER_IS_BETTER
            ),
        ),
    )
    assert plan.role_of("v_required") is IndicatorRole.REQUIRED
    assert plan.role_of("v_fallback") is IndicatorRole.FALLBACK
    assert plan.role_of("unknown") is None


def test_direction_of_returns_per_indicator_direction() -> None:
    plan = make_plan(
        expected_indicators=(
            IndicatorSpec(
                "v_higher", IndicatorRole.REQUIRED, Direction.HIGHER_IS_BETTER
            ),
            IndicatorSpec(
                "v_lower", IndicatorRole.PREFERRED, Direction.LOWER_IS_BETTER
            ),
        ),
    )
    assert plan.direction_of("v_higher") is Direction.HIGHER_IS_BETTER
    assert plan.direction_of("v_lower") is Direction.LOWER_IS_BETTER
    assert plan.direction_of("unknown") is None


def test_indicator_role_enum_lists_all_three_roles() -> None:
    # Pin the enum so a rename does not silently break the contract.
    assert {r.value for r in IndicatorRole} == {"required", "preferred", "fallback"}


def test_indicator_spec_default_weight_is_one() -> None:
    spec = IndicatorSpec(
        "v", IndicatorRole.REQUIRED, Direction.HIGHER_IS_BETTER
    )
    assert spec.weight == 1.0


# ---------------------------------------------------------------------------
# REQ-SCORE-004: default indicator / source weights
# ---------------------------------------------------------------------------


def test_expected_indicators_is_preserved_on_plan() -> None:
    indicators = (
        IndicatorSpec(
            "v_a",
            IndicatorRole.REQUIRED,
            Direction.HIGHER_IS_BETTER,
            weight=0.6,
        ),
        IndicatorSpec(
            "v_b",
            IndicatorRole.PREFERRED,
            Direction.LOWER_IS_BETTER,
            weight=0.4,
        ),
    )
    plan = make_plan(expected_indicators=indicators)

    # The per-indicator specs are stored and exposed in order.
    assert plan.expected_indicators == indicators
    # The derived expected_variables view stays in lockstep.
    assert plan.expected_variables == ("v_a", "v_b")


def test_default_indicator_weight_returns_spec_weight() -> None:
    plan = make_plan(
        expected_indicators=(
            IndicatorSpec(
                "v_a",
                IndicatorRole.REQUIRED,
                Direction.HIGHER_IS_BETTER,
                weight=0.6,
            ),
            IndicatorSpec(
                "v_b",
                IndicatorRole.PREFERRED,
                Direction.HIGHER_IS_BETTER,
                weight=0.4,
            ),
        ),
    )
    assert plan.default_indicator_weight("v_a") == 0.6
    assert plan.default_indicator_weight("v_b") == 0.4


def test_default_indicator_weight_for_unknown_variable_is_zero() -> None:
    # An indicator the plan does not know about must not contribute weight.
    plan = make_plan()
    assert plan.default_indicator_weight("not_in_plan") == 0.0


def test_default_source_weights_are_preserved() -> None:
    plan = make_plan(default_source_weights=(("vdem", 0.7), ("wgi", 0.3)))

    # The override list is stored in the order given.
    assert plan.default_source_weights == (("vdem", 0.7), ("wgi", 0.3))
    # And each lookup hits the configured weight.
    assert plan.default_source_weight("vdem") == 0.7
    assert plan.default_source_weight("wgi") == 0.3


def test_default_source_weight_for_unknown_source_is_one() -> None:
    # An unconfigured source defaults to equal weight (1.0).
    plan = make_plan()
    assert plan.default_source_weight("not_in_plan") == 1.0


# ---------------------------------------------------------------------------
# REQ-SCORE-004: sparse-data policy (provisional vs insufficient_data)
# ---------------------------------------------------------------------------


def test_sparse_data_policy_default_is_insufficient_data() -> None:
    plan = make_plan()
    assert plan.sparse_data_policy is SparseDataPolicy.INSUFFICIENT_DATA


def test_sparse_data_policy_can_be_set_to_provisional_score() -> None:
    plan = make_plan(sparse_data_policy=SparseDataPolicy.PROVISIONAL_SCORE)
    assert plan.sparse_data_policy is SparseDataPolicy.PROVISIONAL_SCORE


def test_sparse_data_policy_enum_lists_both_values() -> None:
    assert {p.value for p in SparseDataPolicy} == {
        "provisional_score",
        "insufficient_data",
    }


# ---------------------------------------------------------------------------
# REQ-SCORE-004: accepted proxy-year rules (retained)
# ---------------------------------------------------------------------------


def test_allowed_proxy_years_is_preserved() -> None:
    plan = make_plan(allowed_proxy_years=(1, 2))
    # Stored as a tuple; equality with a list is by value.
    assert plan.allowed_proxy_years == (1, 2)


def test_allowed_proxy_years_default_is_empty() -> None:
    plan = CategorySourcePlan(
        category_key="x",
        minimum_viable_sources=0,
        preferred_direct_year=2023,
    )
    assert plan.allowed_proxy_years == ()


# ---------------------------------------------------------------------------
# CategoryEvidenceBundle.category_metadata (category-specific metadata)
# ---------------------------------------------------------------------------


def test_bundle_category_metadata_is_preserved_when_provided() -> None:
    bundle = make_bundle(
        category_metadata={"rubric_year": "2023", "edition": "v1", "reviewer": "qa"},
    )
    assert bundle.category_metadata["rubric_year"] == "2023"
    assert bundle.category_metadata["edition"] == "v1"
    assert bundle.category_metadata["reviewer"] == "qa"


def test_bundle_category_metadata_default_is_empty() -> None:
    bundle = make_bundle()
    assert dict(bundle.category_metadata) == {}


def test_bundle_category_metadata_accepts_none() -> None:
    # None is treated as "no metadata" and stored as an empty mapping.
    bundle = make_bundle(category_metadata=None)
    assert dict(bundle.category_metadata) == {}


# ---------------------------------------------------------------------------
# Pin the remaining enum memberships
# ---------------------------------------------------------------------------


def test_direction_enum_lists_higher_and_lower_is_better() -> None:
    assert {d.value for d in Direction} == {"higher_is_better", "lower_is_better"}


def test_missing_reason_enum_lists_all_eight_values() -> None:
    # REQ-STAGE-007 enumerates eight missingness categories; the
    # EXCLUDED_BY_CONFIG value is the config-driven opt-out.
    expected = {
        "source_not_implemented",
        "raw_file_absent",
        "country_row_absent",
        "target_year_absent",
        "indicator_null",
        "not_applicable",
        "blocked_or_paywalled",
        "excluded_by_config",
    }
    assert {r.value for r in MissingReason} == expected
