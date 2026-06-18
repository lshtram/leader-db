"""Domestic violence / repression scoring module (requirement §9, REQ-SCORE-002).

Indicator bundle (from Stage 5):

- Political Terror Scale (PTS)
- CIRIGHTS physical-integrity variables
- UCDP one-sided violence (or ACLED when available)

The module projects each indicator onto 0–1, weights per the rubric, and
emits a 0–10 ``system_proposed_score``. High values (more repression) →
low score; low values → high score. The score sign convention is
documented here so the LLM prompt and any downstream report agree.
"""

from __future__ import annotations


def score_domestic_violence(
    *,
    iso3: str,
    year: int,
    leader_name: str,
    indicators: dict[str, float | None],
    client_score: int | None = None,
) -> int:
    """Return a 0–10 ``system_proposed_score`` for domestic violence/repression.

    Convention: high score = low repression. The module inverts any
    "more violence = higher" indicators before scoring so the per-category
    0–10 axis is consistent with the other categories.
    """
    raise NotImplementedError(
        "score_domestic_violence is not implemented yet. Phase E."
    )


__all__ = ["score_domestic_violence"]
