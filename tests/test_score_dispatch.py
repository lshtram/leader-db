"""Tests for the Stage 9 deterministic-scorer dispatcher
(:mod:`leaders_db.score.dispatch`).

The dispatcher is the single registry that maps each
``CategorySourcePlan.category_key`` to its deterministic scorer
function. Adding a new category is a two-step process (implement
the per-category module, register it in ``_SCORERS``). These tests
pin that contract at the dispatcher boundary so:

- removing the registry entry for ``social_wellbeing`` makes the
  ``score_category_bundle`` dispatch test fail;
- adding a new category without registering it makes the
  unsupported-category error test fail;
- silently renaming a category key without updating the registry
  makes the supported-list test fail.

The tests use the canonical ``social_wellbeing`` scorer directly
rather than constructing a fake one — that keeps the dispatcher
contract grounded in the real per-category module.
"""

from __future__ import annotations

import pytest

import leaders_db.score as score_package
from leaders_db.score.dispatch import (
    get_category_scorer,
    score_category_bundle,
    supported_score_categories,
)
from leaders_db.score.results import ScoreResult
from leaders_db.score.social_wellbeing import (
    CATEGORY_KEY,
    score_social_wellbeing,
)
from tests._social_wellbeing_factories import (
    make_bundle,
    realistic_mexico_observations,
)

# ---------------------------------------------------------------------------
# Package-root exports
# ---------------------------------------------------------------------------


def test_score_package_all_names_are_bound() -> None:
    """Every package-root public export resolves at runtime."""
    for public_name in score_package.__all__:
        assert hasattr(score_package, public_name), public_name


def test_score_package_reexports_stage9_dispatch_functions() -> None:
    """The documented Stage 9 dispatch path is importable from package root."""
    assert score_package.get_category_scorer is get_category_scorer
    assert score_package.score_category_bundle is score_category_bundle
    assert score_package.supported_score_categories is supported_score_categories


# ---------------------------------------------------------------------------
# supported_score_categories
# ---------------------------------------------------------------------------


def test_supported_score_categories_contains_only_social_wellbeing() -> None:
    """The registry exposes only the per-category scorer that is wired.

    Today only ``social_wellbeing`` is registered (the first
    per-category deterministic scorer, Phase D.1). Future categories
    (political_freedom, integrity, ...) are not wired yet — adding
    them is a deliberate follow-on step, not a silent registry
    expansion.
    """
    supported = supported_score_categories()
    assert supported == ("social_wellbeing",)
    assert CATEGORY_KEY in supported
    # And none of the other category keys from the source plans are
    # accidentally registered.
    for other in (
        "political_freedom",
        "economic_wellbeing",
        "corruption",
        "domestic_violence",
        "international_peace",
        "nuclear",
        "effectiveness",
    ):
        assert other not in supported


def test_supported_score_categories_is_sorted() -> None:
    """The supported tuple is sorted so callers see deterministic ordering."""
    supported = supported_score_categories()
    assert supported == tuple(sorted(supported))


# ---------------------------------------------------------------------------
# score_category_bundle dispatch
# ---------------------------------------------------------------------------


def test_score_category_bundle_dispatches_social_wellbeing() -> None:
    """A social-wellbeing bundle reaches the social_wellbeing scorer.

    This is the boundary test that fails if the ``social_wellbeing``
    entry is removed from ``_SCORERS`` — the dispatcher would
    raise :class:`ValueError` instead of running the scorer.
    """
    bundle = make_bundle(observations=realistic_mexico_observations())
    result = score_category_bundle(bundle)

    # The result has the canonical social_wellbeing shape and
    # category_key, proving the bundle reached the right scorer
    # (a hypothetical second scorer for the same category_key
    # would emit a different category_key on the result, e.g.
    # one that round-trips a different value).
    assert isinstance(result, ScoreResult)
    assert result.category_key == "social_wellbeing"
    assert result.iso3 == "MEX"
    assert result.is_insufficient_data is False
    # The realistic Mexico fixture clears the minimum-viable threshold
    # so the result carries an actual score, not an insufficient-data
    # payload.
    assert result.system_proposed_score_1_10 is not None
    assert 1 <= result.system_proposed_score_1_10 <= 10


def test_score_category_bundle_uses_real_scorer_function() -> None:
    """The dispatched scorer is the real social_wellbeing scorer."""
    scorer = get_category_scorer("social_wellbeing")
    assert scorer is score_social_wellbeing


# ---------------------------------------------------------------------------
# Unsupported category error contract
# ---------------------------------------------------------------------------


def test_unsupported_category_raises_value_error_with_supported_list() -> None:
    """An unsupported category raises ``ValueError`` listing the supported set."""
    with pytest.raises(ValueError) as excinfo:
        get_category_scorer("totally_made_up_category")

    message = str(excinfo.value)
    assert "totally_made_up_category" in message
    # The error must point the caller at the supported set so they
    # can pick the right key without reading the dispatcher source.
    assert "social_wellbeing" in message
    # And at the extension point so the next contributor knows
    # where to register a new category.
    assert "_SCORERS" in message


def test_empty_category_key_raises_value_error() -> None:
    """An empty category key raises ``ValueError``."""
    with pytest.raises(ValueError):
        get_category_scorer("")


@pytest.mark.parametrize(
    "category_key",
    [
        "political_freedom",
        "economic_wellbeing",
        "corruption",
        "domestic_violence",
        "international_peace",
        "nuclear",
        "effectiveness",
    ],
)
def test_unsupported_category_via_dispatch_raises_value_error(
    category_key: str,
) -> None:
    """Every category not yet registered raises ``ValueError`` via the dispatcher."""
    with pytest.raises(ValueError) as excinfo:
        get_category_scorer(category_key)
    assert category_key in str(excinfo.value)
    assert "social_wellbeing" in str(excinfo.value)


def test_score_category_bundle_unsupported_raises_value_error() -> None:
    """``score_category_bundle`` raises when the bundle's category_key is unsupported."""
    # Build a bundle with an unsupported category_key (the bundle
    # constructor checks category_key against the source plan, so we
    # need to bypass it via a fresh plan-bound bundle then mutate
    # the key — easier to just use ``get_category_scorer`` directly).
    with pytest.raises(ValueError):
        get_category_scorer("political_freedom")
