"""Legacy ``peace.py`` stub — superseded by ``international_peace``.

The deterministic scorer for the ``international_peace`` category
lives at :mod:`leaders_db.score.international_peace`. This module
remains so any historical import path
(``from leaders_db.score.peace import score_peace``) keeps a
``DeprecationWarning``-friendly surface instead of failing at
import time; the new facade is the canonical implementation
(:func:`leaders_db.score.international_peace.score_international_peace`)
and is registered in :data:`leaders_db.score.dispatch._SCORERS`.

Style invariants (per ``docs/process/coding-guidelines.md``):

- ``from __future__ import annotations`` for forward-reference
  safety.
- The legacy function is preserved for back-compat but raises
  :class:`NotImplementedError` so a stale caller sees a clear
  "use the new module" message rather than a silent wrong
  score.
- No mutable defaults; no ``print()``, no ``TODO(debug)``, no
  scratch code.
"""

from __future__ import annotations

import warnings


def score_peace(
    *,
    iso3: str,
    year: int,
    leader_name: str,
    indicators: dict[str, float | None],
    client_score: int | None = None,
) -> int:
    """Legacy stub — superseded by the new international_peace module.

    Per the requirements, the international-peace category is one
    of the categories the manual-review queue must prioritize
    (REQ-REV-002: war / aggression cases). The deterministic
    scorer is now implemented; import from the new module
    instead. This stub raises :class:`NotImplementedError` on
    call so a stale caller fails fast with an actionable
    message rather than silently producing a wrong score.
    """
    warnings.warn(
        "score_peace is deprecated; use "
        "leaders_db.score.international_peace.score_international_peace "
        "instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    raise NotImplementedError(
        "score_peace is superseded by leaders_db.score.international_peace."
    )


__all__ = ["score_peace"]
