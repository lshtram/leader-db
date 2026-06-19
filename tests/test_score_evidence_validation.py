"""Stage 5 evidence bundle — **validation** tests.

These tests pin the *rejection, immutability, and defensive-copy*
behavior of the typed contract defined in
:mod:`leaders_db.score.evidence`:

- ``__post_init__`` rejects bad input (out-of-range scores, empty
  identifier strings, bad ISO-3 codes, out-of-range years, bad
  metadata types);
- the bundle and the plan are coherently linked
  (``bundle.category_key == source_plan.category_key``);
- the frozen dataclass cannot be silently mutated after construction
  (REQ-NFR-AUDIT-001);
- collection fields are stored as tuples, not lists, and cannot be
  extended from the outside;
- the bundle's ``category_metadata`` mapping cannot be item-assigned
  (``MappingProxyType`` view);
- the bundle takes a **defensive copy** of every sequence/mapping
  the caller passes, so later mutation of the caller's container
  cannot leak into the bundle — including the
  ``MappingProxyType``-backed-by-mutable-dict case the second-pass
  review flagged.

Positive / happy-path coverage lives in
:mod:`tests.test_score_evidence_contract`.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from types import MappingProxyType

import pytest

from leaders_db.score.evidence import (
    CategoryEvidenceBundle,
    Direction,
    IndicatorRole,
    IndicatorSpec,
    TemporalKind,
)
from tests._score_evidence_factories import (
    make_bundle,
    make_missing,
    make_observation,
    make_plan,
)

# ---------------------------------------------------------------------------
# observation_year required for non-NOT_AVAILABLE temporal kinds
# ---------------------------------------------------------------------------


def test_observation_year_required_for_non_not_available_kinds() -> None:
    # observation_year=None is only valid for NOT_AVAILABLE; other kinds
    # must carry a concrete year.
    with pytest.raises(ValueError):
        make_observation(observation_year=None, temporal_kind=TemporalKind.DIRECT)
    with pytest.raises(ValueError):
        make_observation(observation_year=None, temporal_kind=TemporalKind.PROXY)
    with pytest.raises(ValueError):
        make_observation(observation_year=None, temporal_kind=TemporalKind.STALE)


# ---------------------------------------------------------------------------
# Plan: out-of-range rejection
# ---------------------------------------------------------------------------


def test_category_source_plan_rejects_negative_minimum_viable_sources() -> None:
    with pytest.raises(ValueError):
        make_plan(minimum_viable_sources=-1)


def test_category_source_plan_rejects_out_of_range_year() -> None:
    with pytest.raises(ValueError):
        make_plan(preferred_direct_year=1850)


# ---------------------------------------------------------------------------
# Frozen dataclass immutability
# ---------------------------------------------------------------------------


def test_bundles_and_observations_are_frozen() -> None:
    # The frozen dataclass guarantees the typed contract cannot be silently
    # mutated after construction; this is part of the audit-trail invariant
    # (REQ-NFR-AUDIT-001).
    bundle = make_bundle()
    plan = bundle.source_plan
    with pytest.raises(FrozenInstanceError):
        bundle.country_iso3 = "USA"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        plan.minimum_viable_sources = 999  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Bundle <-> plan coherence and identifier validation
# ---------------------------------------------------------------------------


def test_bundle_must_agree_with_plan_category_key() -> None:
    plan = make_plan(category_key="political_freedom")
    with pytest.raises(ValueError):
        CategoryEvidenceBundle(
            country_iso3="MEX",
            country_name="Mexico",
            leader_name=None,
            year=2023,
            category_key="integrity",  # mismatch with plan
            source_plan=plan,
        )


def test_bundle_rejects_bad_iso3() -> None:
    plan = make_plan()
    with pytest.raises(ValueError):
        CategoryEvidenceBundle(
            country_iso3="MEXICO",  # not a 3-char code
            country_name="Mexico",
            leader_name=None,
            year=2023,
            category_key=plan.category_key,
            source_plan=plan,
        )


# ---------------------------------------------------------------------------
# IndicatorSpec validation
# ---------------------------------------------------------------------------


def test_indicator_spec_rejects_empty_variable_name() -> None:
    with pytest.raises(ValueError):
        IndicatorSpec("", IndicatorRole.REQUIRED, Direction.HIGHER_IS_BETTER)


def test_indicator_spec_rejects_out_of_range_weight() -> None:
    with pytest.raises(ValueError):
        IndicatorSpec(
            "v", IndicatorRole.REQUIRED, Direction.HIGHER_IS_BETTER, weight=1.5
        )
    with pytest.raises(ValueError):
        IndicatorSpec(
            "v", IndicatorRole.REQUIRED, Direction.HIGHER_IS_BETTER, weight=-0.1
        )


# ---------------------------------------------------------------------------
# Plan source-weight rejection
# ---------------------------------------------------------------------------


def test_plan_rejects_source_weight_out_of_range() -> None:
    with pytest.raises(ValueError):
        make_plan(default_source_weights=(("vdem", 1.5),))
    with pytest.raises(ValueError):
        make_plan(default_source_weights=(("vdem", -0.1),))


# ---------------------------------------------------------------------------
# Plan sequence immutability (REQ-NFR-AUDIT-001)
# ---------------------------------------------------------------------------


def test_plan_expected_sources_is_a_tuple_and_cannot_be_appended() -> None:
    plan = make_plan()
    # The stored collection is a tuple, not a list.
    assert isinstance(plan.expected_sources, tuple)
    # Tuples do not expose .append, so a caller cannot extend the plan's
    # expected source set after construction.
    with pytest.raises(AttributeError):
        plan.expected_sources.append("new_source")  # type: ignore[attr-defined]


def test_plan_allowed_proxy_years_is_a_tuple_and_cannot_be_appended() -> None:
    plan = make_plan(allowed_proxy_years=[1, 2])
    assert isinstance(plan.allowed_proxy_years, tuple)
    with pytest.raises(AttributeError):
        plan.allowed_proxy_years.append(3)  # type: ignore[attr-defined]


def test_plan_default_source_weights_is_a_tuple_and_cannot_be_appended() -> None:
    plan = make_plan(default_source_weights=[("vdem", 0.7)])
    assert isinstance(plan.default_source_weights, tuple)
    with pytest.raises(AttributeError):
        plan.default_source_weights.append(("wgi", 0.3))  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Bundle sequence immutability (REQ-NFR-AUDIT-001)
# ---------------------------------------------------------------------------


def test_bundle_observations_is_a_tuple_and_cannot_be_appended() -> None:
    bundle = make_bundle(observations=[make_observation()])
    assert isinstance(bundle.observations, tuple)
    with pytest.raises(AttributeError):
        bundle.observations.append(make_observation())  # type: ignore[attr-defined]


def test_bundle_missing_is_a_tuple_and_cannot_be_appended() -> None:
    bundle = make_bundle(missing=[make_missing()])
    assert isinstance(bundle.missing, tuple)
    with pytest.raises(AttributeError):
        bundle.missing.append(make_missing())  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# category_metadata immutability (REQ-NFR-AUDIT-001)
# ---------------------------------------------------------------------------


def test_bundle_category_metadata_cannot_be_item_assigned() -> None:
    bundle = make_bundle(category_metadata={"k": "v"})
    # MappingProxyType raises TypeError on item assignment — the audit-
    # trail invariant for the bundle's metadata.
    with pytest.raises(TypeError):
        bundle.category_metadata["new"] = "x"  # type: ignore[index]


# ---------------------------------------------------------------------------
# Defensive copy from caller's container (REQ-NFR-AUDIT-001)
# ---------------------------------------------------------------------------


def test_plan_does_not_alias_caller_list() -> None:
    # If the caller mutates the list they passed in, the plan must not
    # reflect the change: the plan took a defensive tuple copy in
    # __post_init__.
    sources = ["vdem"]
    plan = make_plan(expected_sources=sources)
    sources.append("wgi")
    assert "wgi" not in plan.expected_sources
    # And the plan's own tuple cannot be mutated from outside either.
    assert isinstance(plan.expected_sources, tuple)


def test_bundle_does_not_alias_caller_observations_list() -> None:
    obs = make_observation()
    obs_extra = make_observation(
        source_key="wgi", variable_name="wgi_control_of_corruption"
    )
    caller_list = [obs]
    bundle = make_bundle(observations=caller_list)
    # Mutating the caller's list after construction must not leak in.
    caller_list.append(obs_extra)
    assert bundle.observations == (obs,)


def test_bundle_does_not_alias_caller_metadata_dict() -> None:
    caller_dict = {"rubric_year": "2023"}
    bundle = make_bundle(category_metadata=caller_dict)
    # Mutating the caller's dict must not leak into the bundle.
    caller_dict["new"] = "x"
    assert "new" not in bundle.category_metadata
    # And the bundle's own mapping cannot be mutated.
    with pytest.raises(TypeError):
        bundle.category_metadata["rubric_year"] = "2024"  # type: ignore[index]


def test_bundle_category_metadata_does_not_alias_mappingproxy_backing_dict() -> None:
    # Regression: the second-pass review flagged a hole where a caller
    # could pass a ``MappingProxyType`` wrapping a mutable dict, and the
    # bundle would store the same proxy through unchanged. Mutating the
    # backing dict afterwards would then leak into the bundle's
    # ``category_metadata`` view, breaking the audit-trail invariant
    # (REQ-NFR-AUDIT-001).
    backing: dict[str, str] = {"rubric_year": "2023"}
    proxy = MappingProxyType(backing)
    bundle = make_bundle(category_metadata=proxy)

    # The bundle's snapshot has the right content.
    assert bundle.category_metadata["rubric_year"] == "2023"

    # Mutate the caller's backing dict after construction.
    backing["new"] = "x"

    # The bundle's metadata view must NOT see the new key — the
    # constructor took a defensive copy of the proxy's contents into a
    # fresh dict, so the proxy and the bundle's view are now decoupled.
    assert "new" not in bundle.category_metadata
    assert "rubric_year" in bundle.category_metadata
    assert dict(bundle.category_metadata) == {"rubric_year": "2023"}

    # And the bundle's own mapping is still read-only.
    with pytest.raises(TypeError):
        bundle.category_metadata["rubric_year"] = "2024"  # type: ignore[index]
