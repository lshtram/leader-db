"""Stage 9 deterministic-scorer dispatch.

This module is the **single registry** that maps each
:class:`~leaders_db.score.evidence.CategorySourcePlan.category_key`
to its deterministic scoring function. The Stage 9 orchestration
seam (:func:`leaders_db.score.stage9.score_category_for_country`)
and any future caller ask the dispatcher for the scorer rather than
importing the per-category module directly, so adding a new
category is a two-step process:

1. implement the scorer function in
   ``src/leaders_db/score/<category>.py`` (one file per category per
   the AGENTS.md "future scoring formulas must live in separate files
   per rating category so each can be improved independently" rule);
2. register the function in :data:`_SCORERS` below.

The dispatcher deliberately does **not** discover scorers by
introspection / plugin-load. A literal registry keeps the wiring
auditable from one place and makes "removing a category" a single-
line edit (the boundary test
:func:`tests.test_score_dispatch.test_score_category_bundle_dispatches_social_wellbeing`
fails if the registry entry is removed).

Unsupported categories raise :class:`ValueError` with a message
that lists the supported categories and the extension point
(``_SCORERS`` in this module), so a Stage 9 caller gets a
self-explanatory failure rather than a bare ``KeyError``.

Style invariants (per ``docs/coding-guidelines.md``):

- ``from __future__ import annotations`` for forward-reference
  safety.
- Type hints on every public function parameter and return.
- No mutable defaults; no ``print()``, no ``TODO(debug)``, no
  scratch code.

Scope
-----

``social_wellbeing`` (Phase D.1), ``integrity`` (Phase D.5),
``effectiveness``, ``economic_wellbeing``,
``political_freedom`` (Phase D.6), ``domestic_violence``
(Phase D.7), ``international_peace`` (Phase D.8), and
``nuclear`` (Phase D.9) are registered today. Wiring
additional categories is a follow-on step that follows the
same two-step recipe.
"""

from __future__ import annotations

from collections.abc import Callable

from .domestic_violence import score_domestic_violence
from .economic_wellbeing import score_economic_wellbeing
from .effectiveness import score_effectiveness
from .evidence import CategoryEvidenceBundle
from .integrity import score_integrity
from .international_peace import score_international_peace
from .nuclear import score_nuclear
from .political_freedom import score_political_freedom
from .results import ScoreResult
from .social_wellbeing import score_social_wellbeing

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
#
# The single mapping from ``category_key`` to scorer function. Mirrors
# the per-category file convention used by ``score/social_wellbeing.py``
# (and the future per-category siblings). Keys are the canonical
# category keys; values are the deterministic scoring functions that
# accept a :class:`CategoryEvidenceBundle` and return a
# :class:`ScoreResult`.
#
# The literal ``dict`` (rather than a plugin-load / introspection
# mechanism) is intentional: a reviewer reading this module can see
# the entire registry in one place, and the
# ``test_score_category_bundle_dispatches_social_wellbeing`` boundary
# test fails if the entry is removed.
_SCORERS: dict[str, Callable[[CategoryEvidenceBundle], ScoreResult]] = {
    "social_wellbeing": score_social_wellbeing,
    "integrity": score_integrity,
    "effectiveness": score_effectiveness,
    "economic_wellbeing": score_economic_wellbeing,
    "political_freedom": score_political_freedom,
    "domestic_violence": score_domestic_violence,
    "international_peace": score_international_peace,
    "nuclear": score_nuclear,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def supported_score_categories() -> tuple[str, ...]:
    """Return the sorted tuple of registered category keys.

    The order is deterministic (lexicographic) so callers and tests
    can rely on the value. The returned tuple is a fresh copy — the
    registry's internal ordering is preserved but callers cannot
    mutate the underlying dict through it.
    """
    return tuple(sorted(_SCORERS))


def get_category_scorer(
    category_key: str,
) -> Callable[[CategoryEvidenceBundle], ScoreResult]:
    """Return the registered scorer for ``category_key``.

    Parameters
    ----------
    category_key:
        Canonical category identifier (e.g. ``"social_wellbeing"``).

    Returns
    -------
    Callable[[CategoryEvidenceBundle], ScoreResult]
        The deterministic scorer function. The caller is responsible
        for invoking it with a bundle whose ``category_key`` matches
        ``category_key``; the dispatcher does not validate the
        bundle's category_key against the lookup key (that
        consistency is the caller's contract).

    Raises
    ------
    ValueError
        If ``category_key`` is empty or not registered. The error
        message lists the supported categories and the extension
        point so a future contributor can wire a new category without
        reading the dispatcher source.
    """
    if not category_key:
        supported = ", ".join(repr(k) for k in supported_score_categories())
        raise ValueError(
            "category_key must be a non-empty string. Supported categories: "
            f"[{supported}]. Register a scorer in "
            "leaders_db.score.dispatch._SCORERS."
        )
    scorer = _SCORERS.get(category_key)
    if scorer is None:
        supported = ", ".join(repr(k) for k in supported_score_categories())
        raise ValueError(
            f"Unsupported category_key={category_key!r}. Supported categories: "
            f"[{supported}]. Register a scorer in "
            "leaders_db.score.dispatch._SCORERS."
        )
    return scorer


def score_category_bundle(bundle: CategoryEvidenceBundle) -> ScoreResult:
    """Dispatch ``bundle`` to the registered scorer for its category_key.

    The function is the single entry point every Stage 9 caller
    should use to turn an evidence bundle into a :class:`ScoreResult`
    — it lets the dispatcher own the registry and keeps the per-
    category scoring modules from importing each other.

    Parameters
    ----------
    bundle:
        A :class:`CategoryEvidenceBundle`. The function reads
        ``bundle.category_key`` and forwards the bundle to the
        matching registered scorer.

    Returns
    -------
    ScoreResult
        Whatever the registered scorer returns. The shape is the
        shared :class:`ScoreResult` contract documented in
        :mod:`leaders_db.score.results`.

    Raises
    ------
    ValueError
        Re-raised from :func:`get_category_scorer` when
        ``bundle.category_key`` is empty or not registered. The
        underlying scorer may also raise :class:`ValueError` if the
        bundle violates its contract (e.g. an empty ``leader_name``
        on the result); the dispatcher does not intercept those.
    """
    return get_category_scorer(bundle.category_key)(bundle)


__all__ = [
    "get_category_scorer",
    "score_category_bundle",
    "supported_score_categories",
]
