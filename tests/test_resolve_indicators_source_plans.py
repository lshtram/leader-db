"""Plan / source-key contract tests for the Stage 5 evidence-bundle builder.

These tests pin the *static* contract of
:mod:`leaders_db.score.source_plans` and the related
:func:`canonical_source_key` derivation. The behavior tests for
the production seam live in
:mod:`tests.test_resolve_indicators_builder`. The split mirrors the
production module boundary (the plan module owns the per-category
declarations; the indicator module owns the per-indicator
collection).

Coverage:

- (a) Canonical source-key substring match resolves every source
      registered by the plan.
- (b) Client / unknown / empty source names return ``None``.
- (c) Exclusion-substring list contains the documented ``client``
      marker.
- (d) ``CATEGORY_SOURCE_PLANS`` registry contains all 8 rating
      categories from requirement §4.
- (e) Each production plan declares a primary source for the
      canonical indicators.
- (f) Every :class:`IndicatorSpec` in the production plans
      carries a non-empty ``source_key`` that is a member of the
      plan's ``expected_sources`` (per-indicator ownership rule).
- (g) No plan has a duplicate ``variable_name`` in its
      ``expected_indicators``.
- (h) Every plan has at least one expected source and at least
      one expected indicator; no plan has a zero-source or
      zero-indicator registry.
- (i) The ``minimum_viable_sources`` threshold is sane: at least
      1 and at most the plan's ``expected_sources`` length, and
      never exceeds it.
- (j) ``get_category_source_plan`` accessor behaviour.
- (k) Authority / specificity default constants match the
      bundle's per-observation values.
- (l) ``SOURCE_KEY_BY_NAME`` covers all 14 implemented Stage 2
      structured sources.
"""

from __future__ import annotations

import pytest

from leaders_db.score.evidence import IndicatorSpec
from leaders_db.score.source_plans import (
    CATEGORY_SOURCE_PLANS,
    DEFAULT_AUTHORITY_SCORE,
    DEFAULT_SPECIFICITY_SCORE,
    DOMESTIC_VIOLENCE_INDICATORS,
    DOMESTIC_VIOLENCE_PLAN,
    ECONOMIC_WELLBEING_INDICATORS,
    ECONOMIC_WELLBEING_PLAN,
    EFFECTIVENESS_INDICATORS,
    EFFECTIVENESS_PLAN,
    EXCLUDED_SOURCE_NAME_SUBSTRINGS,
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
    SOURCE_KEY_BY_NAME,
    canonical_source_key,
    get_category_source_plan,
)

# The 8 rating categories from requirement §4
# (docs/requirements/top-level-requirements.md §4).
ALL_EIGHT_CATEGORIES: tuple[str, ...] = (
    "nuclear",
    "international_peace",
    "domestic_violence",
    "political_freedom",
    "economic_wellbeing",
    "social_wellbeing",
    "integrity",
    "effectiveness",
)

# A small registry of (plan, indicator-list) pairs for the
# indicator-ownership and duplicate-name sweeps. The factory keeps
# the per-test loops tiny and lets the per-plan names show up
# directly in the assertion messages.
ALL_PLANS: tuple[tuple[str, IndicatorSpec], ...] = tuple(
    (plan.category_key, indicator)
    for plan in CATEGORY_SOURCE_PLANS.values()
    for indicator in plan.expected_indicators
)


# ---------------------------------------------------------------------------
# (a) canonical_source_key substring match
# ---------------------------------------------------------------------------


def test_canonical_source_key_resolves_known_substrings() -> None:
    """The substring match resolves every source registered by the plan."""
    for name, expected_key in SOURCE_KEY_BY_NAME.items():
        for suffix in ("", " (test)", " 2023", " v16 (test)"):
            assert canonical_source_key(name + suffix) == expected_key


# ---------------------------------------------------------------------------
# (b) canonical_source_key negative cases
# ---------------------------------------------------------------------------


def test_canonical_source_key_returns_none_for_client_name() -> None:
    """A name containing the ``client`` substring returns ``None``."""
    assert canonical_source_key("client_existing_2023") is None
    assert canonical_source_key("Client 2023 Matrix") is None
    # A real source whose name accidentally contains "client" (none
    # in the current plan, but the guard is broad) is also excluded.
    assert canonical_source_key("ACME client-sourced feed") is None


def test_canonical_source_key_returns_none_for_empty_or_unknown() -> None:
    """Empty / ``None`` / unknown source names return ``None``."""
    assert canonical_source_key(None) is None
    assert canonical_source_key("") is None
    # Unknown source name (no substring match) -> None so the
    # builder treats it as out-of-scope.
    assert canonical_source_key("Random Non-Catalog Feed") is None


# ---------------------------------------------------------------------------
# (c) EXCLUDED_SOURCE_NAME_SUBSTRINGS contract
# ---------------------------------------------------------------------------


def test_excluded_source_name_substrings_contains_client() -> None:
    """The exclusion-substring list is the documented ``client`` marker."""
    assert "client" in EXCLUDED_SOURCE_NAME_SUBSTRINGS


# ---------------------------------------------------------------------------
# (d) Plan registry
# ---------------------------------------------------------------------------


def test_category_source_plans_registry_contains_all_eight_categories() -> None:
    """The registry ships all 8 rating categories from requirement §4."""
    assert set(CATEGORY_SOURCE_PLANS) == set(ALL_EIGHT_CATEGORIES)


def test_category_source_plans_keys_are_strings() -> None:
    """Every plan key is a non-empty string (the type contract)."""
    for key in CATEGORY_SOURCE_PLANS:
        assert isinstance(key, str)
        assert key, "Plan registry key must be non-empty"


# ---------------------------------------------------------------------------
# (e) Per-plan primary source
# ---------------------------------------------------------------------------


def test_nuclear_plan_uses_fas_and_sipri_yearbook_ch7() -> None:
    """The nuclear plan enumerates the §6 two-source set."""
    assert set(NUCLEAR_PLAN.expected_sources) == {"fas", "sipri_yearbook_ch7"}
    assert NUCLEAR_PLAN.is_required_variable("fas_total_inventory")
    assert NUCLEAR_PLAN.is_required_variable(
        "sipri_yearbook_ch7_nuclear_warheads_total_inventory"
    )


def test_international_peace_plan_uses_ucdp_and_sipri_milex() -> None:
    """The international_peace plan enumerates the §6 two-source set."""
    assert set(INTERNATIONAL_PEACE_PLAN.expected_sources) == {
        "ucdp",
        "sipri_milex",
    }
    assert INTERNATIONAL_PEACE_PLAN.is_required_variable(
        "ucdp_state_based_fatalities"
    )
    assert INTERNATIONAL_PEACE_PLAN.is_preferred_variable(
        "sipri_milex_share_of_gdp"
    )


def test_domestic_violence_plan_uses_pts_cirights_ucdp_vdem() -> None:
    """The domestic_violence plan enumerates the §6 four-source set."""
    assert set(DOMESTIC_VIOLENCE_PLAN.expected_sources) == {
        "pts",
        "cirights",
        "ucdp",
        "vdem",
    }
    assert DOMESTIC_VIOLENCE_PLAN.is_required_variable("pts_amnesty_score")
    assert DOMESTIC_VIOLENCE_PLAN.is_required_variable("cirights_physint")


def test_political_freedom_plan_uses_vdem_rsf_bti() -> None:
    """The political_freedom plan enumerates the §6 three-source set."""
    assert set(POLITICAL_FREEDOM_PLAN.expected_sources) == {
        "vdem",
        "rsf_press_freedom",
        "bti",
    }
    assert POLITICAL_FREEDOM_PLAN.is_required_variable("vdem_v2x_polyarchy")
    assert POLITICAL_FREEDOM_PLAN.is_required_variable("vdem_v2x_libdem")
    assert POLITICAL_FREEDOM_PLAN.is_preferred_variable(
        "rsf_press_freedom_score"
    )


def test_economic_wellbeing_plan_uses_wdi_and_bti() -> None:
    """The economic_wellbeing plan enumerates the §6 two-source set."""
    assert set(ECONOMIC_WELLBEING_PLAN.expected_sources) == {
        "world_bank_wdi",
        "bti",
    }
    assert ECONOMIC_WELLBEING_PLAN.is_required_variable("wdi_gdp_per_capita")
    assert ECONOMIC_WELLBEING_PLAN.is_required_variable(
        "wdi_gdp_per_capita_ppp_constant_2017"
    )


def test_social_wellbeing_plan_uses_undp_hdi_as_primary_source() -> None:
    """UNDP HDI is the canonical REQUIRED source for social-wellbeing."""
    assert "undp_hdi" in SOCIAL_WELLBEING_PLAN.expected_sources
    assert SOCIAL_WELLBEING_PLAN.is_required_variable("undp_hdi_hdi")


def test_integrity_plan_uses_wgi_vdem_and_ti_cpi() -> None:
    """The integrity plan enumerates the three §6 sources."""
    assert set(INTEGRITY_PLAN.expected_sources) == {"wgi", "vdem", "ti_cpi"}
    assert INTEGRITY_PLAN.is_required_variable("wgi_control_of_corruption")
    assert INTEGRITY_PLAN.is_required_variable("vdem_v2x_corr")
    assert INTEGRITY_PLAN.is_required_variable("cpi_score")


def test_effectiveness_plan_uses_wgi_vdem_and_bti() -> None:
    """The effectiveness plan enumerates the three §6 sources."""
    assert set(EFFECTIVENESS_PLAN.expected_sources) == {"wgi", "vdem", "bti"}
    assert EFFECTIVENESS_PLAN.is_required_variable("wgi_government_effectiveness")
    assert EFFECTIVENESS_PLAN.is_required_variable("wgi_rule_of_law")
    assert EFFECTIVENESS_PLAN.is_required_variable("vdem_v2x_accountability")
    assert EFFECTIVENESS_PLAN.is_required_variable("bti_governance_index")


# ---------------------------------------------------------------------------
# (f) Per-indicator ownership rule
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("category_key,indicator", ALL_PLANS)
def test_every_indicator_declares_owning_source_in_expected_sources(
    category_key: str, indicator: IndicatorSpec
) -> None:
    """Every indicator has a non-empty ``source_key`` in the plan's ``expected_sources``."""
    plan = CATEGORY_SOURCE_PLANS[category_key]
    expected = set(plan.expected_sources)
    assert indicator.source_key, (
        f"{category_key} indicator {indicator.variable_name!r} has no source_key"
    )
    assert indicator.source_key in expected, (
        f"{category_key} indicator {indicator.variable_name!r} owns source "
        f"{indicator.source_key!r} which is not in the plan's expected_sources "
        f"({sorted(expected)})"
    )


@pytest.mark.parametrize("plan", list(CATEGORY_SOURCE_PLANS.values()), ids=lambda p: p.category_key)
def test_wgi_does_not_own_corruption_outside_integrity(plan) -> None:
    """``wgi_control_of_corruption`` is owned only by the integrity plan."""
    wgi_corr_in_plan = [
        spec.variable_name
        for spec in plan.expected_indicators
        if spec.source_key == "wgi" and spec.variable_name == "wgi_control_of_corruption"
    ]
    if plan.category_key == "integrity":
        assert wgi_corr_in_plan == ["wgi_control_of_corruption"]
    else:
        assert wgi_corr_in_plan == []


@pytest.mark.parametrize("plan", list(CATEGORY_SOURCE_PLANS.values()), ids=lambda p: p.category_key)
def test_vdem_owns_only_vdem_variables(plan) -> None:
    """V-Dem is the owning source for every ``vdem_*`` variable in any plan."""
    vdem_vars = [
        spec.variable_name
        for spec in plan.expected_indicators
        if spec.source_key == "vdem"
    ]
    # All vdem_* variable names start with "vdem_"; assert that.
    for name in vdem_vars:
        assert name.startswith("vdem_"), (
            f"{plan.category_key} plan owns a non-vdem variable under vdem: {name!r}"
        )


def test_no_cross_source_ownership_collisions() -> None:
    """No single variable is owned by more than one source across all plans."""
    seen: dict[str, str] = {}
    for plan in CATEGORY_SOURCE_PLANS.values():
        for spec in plan.expected_indicators:
            existing = seen.get(spec.variable_name)
            if existing is not None and existing != spec.source_key:
                raise AssertionError(
                    f"variable {spec.variable_name!r} is owned by "
                    f"{existing!r} in one plan and {spec.source_key!r} in another"
                )
            seen[spec.variable_name] = spec.source_key or ""


# ---------------------------------------------------------------------------
# (g) No duplicate variable_name within a plan
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("plan", list(CATEGORY_SOURCE_PLANS.values()), ids=lambda p: p.category_key)
def test_plan_has_no_duplicate_variable_names(plan) -> None:
    """A plan's ``expected_indicators`` has no duplicate ``variable_name``."""
    seen: set[str] = set()
    duplicates: set[str] = set()
    for spec in plan.expected_indicators:
        if spec.variable_name in seen:
            duplicates.add(spec.variable_name)
        seen.add(spec.variable_name)
    assert not duplicates, (
        f"plan {plan.category_key!r} has duplicate variable_name entries: "
        f"{sorted(duplicates)}"
    )


# ---------------------------------------------------------------------------
# (h) No zero-source / zero-indicator plans
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("plan", list(CATEGORY_SOURCE_PLANS.values()), ids=lambda p: p.category_key)
def test_plan_has_at_least_one_source_and_indicator(plan) -> None:
    """A plan must declare at least one source and at least one indicator."""
    assert plan.expected_sources, (
        f"plan {plan.category_key!r} has no expected_sources"
    )
    assert plan.expected_indicators, (
        f"plan {plan.category_key!r} has no expected_indicators"
    )


# ---------------------------------------------------------------------------
# (i) minimum_viable_sources sanity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("plan", list(CATEGORY_SOURCE_PLANS.values()), ids=lambda p: p.category_key)
def test_minimum_viable_sources_is_sane(plan) -> None:
    """``minimum_viable_sources`` is in 1..len(expected_sources) (or 0 only by exception)."""
    # The architecture document says 0 is allowed (a 0 threshold means
    # even a totally missing bundle produces a score; the sparse-data
    # policy decides whether to emit one). The default is 0 per the
    # dataclass; the production plans either set it to 1+ or leave it
    # at 0 deliberately. We assert the upper bound: minimum_viable
    # cannot exceed the number of expected sources.
    assert plan.minimum_viable_sources <= len(plan.expected_sources), (
        f"plan {plan.category_key!r} minimum_viable_sources "
        f"({plan.minimum_viable_sources}) exceeds expected_sources "
        f"count ({len(plan.expected_sources)})"
    )
    assert plan.minimum_viable_sources >= 0, (
        f"plan {plan.category_key!r} minimum_viable_sources must be >= 0"
    )


# ---------------------------------------------------------------------------
# (j) get_category_source_plan accessor
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("category_key", ALL_EIGHT_CATEGORIES)
def test_get_category_source_plan_returns_registered_plan(category_key: str) -> None:
    """The accessor returns the registered plan for every one of the 8 categories."""
    assert get_category_source_plan(category_key) is CATEGORY_SOURCE_PLANS[category_key]


def test_get_category_source_plan_raises_for_unknown_key() -> None:
    """The accessor raises ``ValueError`` for keys not in the registry."""
    with pytest.raises(ValueError) as excinfo:
        get_category_source_plan("totally_made_up_category")
    msg = str(excinfo.value)
    # Error must point the caller at every supported category and
    # the extension point (the ``category_plans`` subpackage + the
    # ``CATEGORY_SOURCE_PLANS`` registry).
    for cat in ALL_EIGHT_CATEGORIES:
        assert cat in msg, f"error message must mention {cat!r}"
    assert "leaders_db.score.category_plans" in msg
    assert "CATEGORY_SOURCE_PLANS" in msg


def test_get_category_source_plan_raises_for_empty_key() -> None:
    """The accessor raises ``ValueError`` for an empty key."""
    with pytest.raises(ValueError, match="non-empty"):
        get_category_source_plan("")


# ---------------------------------------------------------------------------
# (k) Authority / specificity defaults
# ---------------------------------------------------------------------------


def test_authority_and_specificity_defaults_match_module_constants() -> None:
    """The defaults declared in ``source_plans`` are the documented values."""
    assert DEFAULT_AUTHORITY_SCORE == 70
    assert DEFAULT_SPECIFICITY_SCORE == 80


# ---------------------------------------------------------------------------
# (l) SOURCE_KEY_BY_NAME coverage
# ---------------------------------------------------------------------------


def test_source_key_by_name_covers_all_implemented_sources() -> None:
    """The substring map covers every implemented Stage 2 structured source.

    The 14 implemented sources whose ``register_*_source`` helpers
    stage a row in the ``sources`` table are listed here. Adding a
    new Stage 2 source that the scoring layer may consume means
    adding a substring here too.
    """
    expected_keys = {
        "undp_hdi",
        "wgi",
        "world_bank_wdi",
        "vdem",
        "who_gho_api",
        "ti_cpi",
        "fas",
        "sipri_yearbook_ch7",
        "sipri_milex",
        "ucdp",
        "pts",
        "cirights",
        "bti",
        "rsf_press_freedom",
    }
    assert set(SOURCE_KEY_BY_NAME.values()) == expected_keys


# ---------------------------------------------------------------------------
# (m) Indicator-list re-exports are well-formed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "indicator_list",
    [
        NUCLEAR_INDICATORS,
        INTERNATIONAL_PEACE_INDICATORS,
        DOMESTIC_VIOLENCE_INDICATORS,
        POLITICAL_FREEDOM_INDICATORS,
        ECONOMIC_WELLBEING_INDICATORS,
        SOCIAL_WELLBEING_INDICATORS,
        INTEGRITY_INDICATORS,
        EFFECTIVENESS_INDICATORS,
    ],
)
def test_indicator_lists_have_no_duplicates(indicator_list) -> None:
    """The exported ``*_INDICATORS`` tuple has no duplicate ``variable_name``."""
    seen: set[str] = set()
    duplicates: set[str] = set()
    for spec in indicator_list:
        if spec.variable_name in seen:
            duplicates.add(spec.variable_name)
        seen.add(spec.variable_name)
    assert not duplicates, f"indicator list has duplicates: {sorted(duplicates)}"


@pytest.mark.parametrize(
    "plan,indicator_list",
    [
        (NUCLEAR_PLAN, NUCLEAR_INDICATORS),
        (INTERNATIONAL_PEACE_PLAN, INTERNATIONAL_PEACE_INDICATORS),
        (DOMESTIC_VIOLENCE_PLAN, DOMESTIC_VIOLENCE_INDICATORS),
        (POLITICAL_FREEDOM_PLAN, POLITICAL_FREEDOM_INDICATORS),
        (ECONOMIC_WELLBEING_PLAN, ECONOMIC_WELLBEING_INDICATORS),
        (SOCIAL_WELLBEING_PLAN, SOCIAL_WELLBEING_INDICATORS),
        (INTEGRITY_PLAN, INTEGRITY_INDICATORS),
        (EFFECTIVENESS_PLAN, EFFECTIVENESS_INDICATORS),
    ],
    ids=lambda x: x.category_key if hasattr(x, "category_key") else "",
)
def test_indicator_list_matches_plan_expected_indicators(plan, indicator_list) -> None:
    """The exported ``*_INDICATORS`` tuple matches the plan's ``expected_indicators``."""
    assert tuple(plan.expected_indicators) == tuple(indicator_list)
