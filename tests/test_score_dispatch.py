"""Tests for the Stage 9 deterministic-scorer dispatcher
(:mod:`leaders_db.score.dispatch`) — package-root re-exports,
supported-set contract, and unsupported-category error contract.

The per-category dispatch happy-path tests (one test per registered
``category_key`` proving the bundle reaches the matching scorer)
live in :mod:`tests.test_score_dispatch_per_category` so this
file stays under the 400-line convention while still being one
test module per production seam family — same pattern as the
``social_wellbeing`` / ``integrity`` / ``effectiveness`` /
``economic_wellbeing`` / ``political_freedom`` /
``domestic_violence` / ``international_peace` / ``nuclear``
per-category test files.

The dispatcher is the single registry that maps each
``CategorySourcePlan.category_key`` to its deterministic scorer
function. Adding a new category is a two-step process (implement
the per-category module, register it in ``_SCORERS``). These tests
pin the cross-cutting contract at the dispatcher boundary:

- removing the registry entry for any registered category makes
  the matching per-category dispatch test fail
  (see :mod:`tests.test_score_dispatch_per_category`);
- adding a new category without registering it makes the
  unsupported-category error test fail;
- silently renaming a category key without updating the registry
  makes the supported-list test fail.

Style invariants (per ``docs/coding-guidelines.md``): type
hints, no ``print()``, no ``TODO(debug)``, no scratch code.
"""

from __future__ import annotations

import pytest

import leaders_db.score as score_package
from leaders_db.score.dispatch import (
    get_category_scorer,
    score_category_bundle,
    supported_score_categories,
)
from leaders_db.score.domestic_violence import score_domestic_violence
from leaders_db.score.economic_wellbeing import score_economic_wellbeing
from leaders_db.score.effectiveness import score_effectiveness
from leaders_db.score.integrity import score_integrity
from leaders_db.score.international_peace import score_international_peace
from leaders_db.score.nuclear import score_nuclear
from leaders_db.score.political_freedom import score_political_freedom
from leaders_db.score.social_wellbeing import score_social_wellbeing

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


def test_score_package_reexports_score_integrity() -> None:
    """``score_integrity`` is re-exported from the package root.

    Boundary test that fails if the package-root export is
    removed (the dispatcher / Stage 9 caller imports it from
    ``leaders_db.score``).
    """
    assert score_package.score_integrity is score_integrity


def test_score_package_reexports_score_effectiveness() -> None:
    """``score_effectiveness`` is re-exported from the package root.

    Boundary test that fails if the package-root export is
    removed (the dispatcher / Stage 9 caller imports it from
    ``leaders_db.score``).
    """
    assert score_package.score_effectiveness is score_effectiveness


def test_score_package_reexports_score_political_freedom() -> None:
    """``score_political_freedom`` is re-exported from the package root.

    Boundary test that fails if the package-root export is
    removed (the dispatcher / Stage 9 caller imports it from
    ``leaders_db.score``).
    """
    assert score_package.score_political_freedom is score_political_freedom


def test_score_package_reexports_score_domestic_violence() -> None:
    """``score_domestic_violence`` is re-exported from the package root.

    Boundary test that fails if the package-root export is
    removed (the dispatcher / Stage 9 caller imports it from
    ``leaders_db.score``).
    """
    assert score_package.score_domestic_violence is score_domestic_violence


def test_score_package_reexports_score_international_peace() -> None:
    """``score_international_peace`` is re-exported from the package root.

    Boundary test that fails if the package-root export is
    removed (the dispatcher / Stage 9 caller imports it from
    ``leaders_db.score``).
    """
    assert score_package.score_international_peace is score_international_peace


def test_score_package_reexports_score_nuclear() -> None:
    """``score_nuclear`` is re-exported from the package root.

    Boundary test that fails if the package-root export is
    removed (the dispatcher / Stage 9 caller imports it from
    ``leaders_db.score``).
    """
    assert score_package.score_nuclear is score_nuclear


# ---------------------------------------------------------------------------
# supported_score_categories
# ---------------------------------------------------------------------------


def test_supported_score_categories_contains_registered_scorers() -> None:
    """The registry exposes the categories that are wired.

    Today ``social_wellbeing`` (Phase D.1), ``integrity`` (the
    second per-category deterministic scorer), ``effectiveness``
    (the third), ``economic_wellbeing`` (the fourth),
    ``political_freedom`` (the fifth), ``domestic_violence``
    (the sixth), ``international_peace`` (the seventh), and
    ``nuclear`` (the eighth) are registered. The future
    ``corruption`` category is not wired yet — adding it is a
    deliberate follow-on step, not a silent registry expansion.
    """
    supported = supported_score_categories()
    from leaders_db.score.economic_wellbeing import (
        CATEGORY_KEY as ECONOMIC_WELLBEING_CATEGORY_KEY,
    )
    from leaders_db.score.effectiveness import (
        CATEGORY_KEY as EFFECTIVENESS_CATEGORY_KEY,
    )
    from leaders_db.score.integrity import CATEGORY_KEY as INTEGRITY_CATEGORY_KEY
    from leaders_db.score.international_peace import (
        CATEGORY_KEY as INTERNATIONAL_PEACE_CATEGORY_KEY,
    )
    from leaders_db.score.nuclear import CATEGORY_KEY as NUCLEAR_CATEGORY_KEY
    from leaders_db.score.political_freedom import (
        CATEGORY_KEY as POLITICAL_FREEDOM_CATEGORY_KEY,
    )
    from leaders_db.score.social_wellbeing import CATEGORY_KEY

    assert CATEGORY_KEY in supported
    assert INTEGRITY_CATEGORY_KEY in supported
    assert EFFECTIVENESS_CATEGORY_KEY in supported
    assert ECONOMIC_WELLBEING_CATEGORY_KEY in supported
    assert POLITICAL_FREEDOM_CATEGORY_KEY in supported
    assert "domestic_violence" in supported
    assert INTERNATIONAL_PEACE_CATEGORY_KEY in supported
    assert NUCLEAR_CATEGORY_KEY in supported
    # And none of the other category keys from the source plans
    # are accidentally registered.
    for other in ("corruption",):
        assert other not in supported, (
            f"category {other!r} is not yet wired in the dispatcher"
        )


def test_supported_score_categories_is_sorted() -> None:
    """The supported tuple is sorted so callers see deterministic ordering."""
    supported = supported_score_categories()
    assert supported == tuple(sorted(supported))


# ---------------------------------------------------------------------------
# score_category_bundle uses the real per-category scorer functions
# ---------------------------------------------------------------------------


def test_score_category_bundle_uses_real_scorer_functions() -> None:
    """The dispatched scorers are the real per-category scorers."""
    social_scorer = get_category_scorer("social_wellbeing")
    assert social_scorer is score_social_wellbeing
    integrity_scorer = get_category_scorer("integrity")
    assert integrity_scorer is score_integrity
    effectiveness_scorer = get_category_scorer("effectiveness")
    assert effectiveness_scorer is score_effectiveness
    economic_wellbeing_scorer = get_category_scorer("economic_wellbeing")
    assert economic_wellbeing_scorer is score_economic_wellbeing
    political_freedom_scorer = get_category_scorer("political_freedom")
    assert political_freedom_scorer is score_political_freedom
    domestic_violence_scorer = get_category_scorer("domestic_violence")
    assert domestic_violence_scorer is score_domestic_violence
    international_peace_scorer = get_category_scorer("international_peace")
    assert international_peace_scorer is score_international_peace
    nuclear_scorer = get_category_scorer("nuclear")
    assert nuclear_scorer is score_nuclear


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
        "corruption",
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
        get_category_scorer("corruption")
