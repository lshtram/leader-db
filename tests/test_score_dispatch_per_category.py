"""Tests for the Stage 9 deterministic-scorer dispatcher
(:mod:`leaders_db.score.dispatch`) — per-category happy-path
dispatch tests.

The dispatcher is the single registry that maps each
``CategorySourcePlan.category_key`` to its deterministic scorer
function. Adding a new category is a two-step process (implement
the per-category module, register it in ``_SCORERS``). These
tests pin that contract at the dispatcher boundary so:

- removing the registry entry for ``social_wellbeing`` makes the
  ``score_category_bundle`` dispatch test for social_wellbeing
  fail;
- removing the registry entry for ``integrity`` makes the
  ``score_category_bundle`` dispatch test for integrity fail;
- removing the registry entry for ``effectiveness`` makes the
  ``score_category_bundle`` dispatch test for effectiveness fail;
- removing the registry entry for ``economic_wellbeing`` makes
  the ``score_category_bundle`` dispatch test for
  economic_wellbeing fail;
- removing the registry entry for ``political_freedom`` makes
  the ``score_category_bundle`` dispatch test for
  political_freedom fail;
- removing the registry entry for ``domestic_violence`` makes
  the ``score_category_bundle`` dispatch test for
  domestic_violence fail;
- removing the registry entry for ``international_peace`` makes
  the ``score_category_bundle`` dispatch test for
  international_peace fail;
- removing the registry entry for ``nuclear`` makes the
  ``score_category_bundle`` dispatch test for nuclear fail.

The tests use the canonical per-category scorers directly
rather than constructing fake ones — that keeps the dispatcher
contract grounded in the real per-category modules.

The dispatcher tests live in a sibling test file so this
per-category dispatch surface stays under the 400-line
convention while still being one test module per production
seam family. The companion file
:mod:`tests.test_score_dispatch` owns the cross-cutting
contract (package-root re-exports, supported-set shape,
unsupported-category error contract). The split mirrors the
per-category test files: facade + private-modules + focused
sibling tests, no ``__init__`` orchestrator.

Style invariants (per ``docs/process/coding-guidelines.md``): type
hints, no ``print()``, no ``TODO(debug)``, no scratch code.
"""

from __future__ import annotations

from leaders_db.score.dispatch import score_category_bundle
from leaders_db.score.results import ScoreResult
from tests._domestic_violence_factories import (
    domestic_violence_make_bundle,
    realistic_domestic_violence_observations,
)
from tests._economic_wellbeing_factories import (
    economic_wellbeing_make_bundle,
    realistic_economic_wellbeing_observations,
)
from tests._effectiveness_factories import (
    effectiveness_make_bundle,
    realistic_effectiveness_observations,
)
from tests._integrity_factories import (
    integrity_make_bundle,
    realistic_integrity_observations,
)
from tests._international_peace_factories import (
    international_peace_make_bundle,
    realistic_international_peace_observations,
)
from tests._nuclear_factories import (
    nuclear_make_bundle,
    realistic_nuclear_observations,
)
from tests._political_freedom_factories import (
    political_freedom_make_bundle,
    realistic_political_freedom_observations,
)
from tests._social_wellbeing_factories import (
    make_bundle,
    realistic_mexico_observations,
)

# ---------------------------------------------------------------------------
# score_category_bundle dispatch — per-category happy path
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


def test_score_category_bundle_dispatches_integrity() -> None:
    """An integrity bundle reaches the integrity scorer.

    Boundary test that fails if the ``integrity`` entry is
    removed from ``_SCORERS``.
    """
    bundle = integrity_make_bundle(observations=realistic_integrity_observations())
    result = score_category_bundle(bundle)

    assert isinstance(result, ScoreResult)
    assert result.category_key == "integrity"
    assert result.iso3 == "MEX"
    assert result.is_insufficient_data is False
    assert result.system_proposed_score_1_10 is not None
    assert 1 <= result.system_proposed_score_1_10 <= 10


def test_score_category_bundle_dispatches_effectiveness() -> None:
    """An effectiveness bundle reaches the effectiveness scorer.

    Boundary test that fails if the ``effectiveness`` entry is
    removed from ``_SCORERS``.
    """
    bundle = effectiveness_make_bundle(
        observations=realistic_effectiveness_observations()
    )
    result = score_category_bundle(bundle)

    assert isinstance(result, ScoreResult)
    assert result.category_key == "effectiveness"
    assert result.iso3 == "MEX"
    assert result.is_insufficient_data is False
    assert result.system_proposed_score_1_10 is not None
    assert 1 <= result.system_proposed_score_1_10 <= 10


def test_score_category_bundle_dispatches_economic_wellbeing() -> None:
    """An economic_wellbeing bundle reaches the economic_wellbeing scorer.

    Boundary test that fails if the ``economic_wellbeing`` entry
    is removed from ``_SCORERS``.
    """
    bundle = economic_wellbeing_make_bundle(
        observations=realistic_economic_wellbeing_observations()
    )
    result = score_category_bundle(bundle)

    assert isinstance(result, ScoreResult)
    assert result.category_key == "economic_wellbeing"
    assert result.iso3 == "MEX"
    assert result.is_insufficient_data is False
    assert result.system_proposed_score_1_10 is not None
    assert 1 <= result.system_proposed_score_1_10 <= 10


def test_score_category_bundle_dispatches_political_freedom() -> None:
    """A political_freedom bundle reaches the political_freedom scorer.

    Boundary test that fails if the ``political_freedom`` entry
    is removed from ``_SCORERS``.
    """
    bundle = political_freedom_make_bundle(
        observations=realistic_political_freedom_observations()
    )
    result = score_category_bundle(bundle)

    assert isinstance(result, ScoreResult)
    assert result.category_key == "political_freedom"
    assert result.iso3 == "MEX"
    assert result.is_insufficient_data is False
    assert result.system_proposed_score_1_10 is not None
    assert 1 <= result.system_proposed_score_1_10 <= 10


def test_score_category_bundle_dispatches_domestic_violence() -> None:
    """A domestic_violence bundle reaches the domestic_violence scorer.

    Boundary test that fails if the ``domestic_violence`` entry
    is removed from ``_SCORERS``.
    """
    bundle = domestic_violence_make_bundle(
        observations=realistic_domestic_violence_observations()
    )
    result = score_category_bundle(bundle)

    assert isinstance(result, ScoreResult)
    assert result.category_key == "domestic_violence"
    assert result.iso3 == "MEX"
    assert result.is_insufficient_data is False
    assert result.system_proposed_score_1_10 is not None
    assert 1 <= result.system_proposed_score_1_10 <= 10


def test_score_category_bundle_dispatches_international_peace() -> None:
    """An international_peace bundle reaches the international_peace scorer.

    Boundary test that fails if the ``international_peace`` entry
    is removed from ``_SCORERS``.
    """
    bundle = international_peace_make_bundle(
        observations=realistic_international_peace_observations()
    )
    result = score_category_bundle(bundle)

    assert isinstance(result, ScoreResult)
    assert result.category_key == "international_peace"
    assert result.iso3 == "MEX"
    assert result.is_insufficient_data is False
    assert result.system_proposed_score_1_10 is not None
    assert 1 <= result.system_proposed_score_1_10 <= 10


def test_score_category_bundle_dispatches_nuclear() -> None:
    """A nuclear bundle reaches the nuclear scorer.

    Boundary test that fails if the ``nuclear`` entry is removed
    from ``_SCORERS``. The realistic fixture populates all 8
    NUCLEAR_PLAN indicators across FAS + SIPRI Yearbook Ch.7
    so the bundle clears the minimum-viable threshold and the
    scorer emits a real (non-insufficient-data) result.
    """
    bundle = nuclear_make_bundle(observations=realistic_nuclear_observations())
    result = score_category_bundle(bundle)

    assert isinstance(result, ScoreResult)
    assert result.category_key == "nuclear"
    assert result.iso3 == "USA"
    assert result.is_insufficient_data is False
    assert result.system_proposed_score_1_10 is not None
    assert 1 <= result.system_proposed_score_1_10 <= 10
    # The nuclear-case population-split flag fires on the
    # scored path iff the bundle carries any usable
    # nuclear-source observation (the §14 manual-review-queue
    # hook per REQ-REV-002).
    from leaders_db.score.results import ReviewFlag

    assert ReviewFlag.NUCLEAR_CASE in result.review_flags
