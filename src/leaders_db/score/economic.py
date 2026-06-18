"""Economic well-being scoring module (requirement §9, REQ-SCORE-002).

Indicator bundle (from Stage 5):

- GDP growth
- GDP per capita
- Inflation
- Unemployment
- Poverty rate where available

The module projects each indicator onto 0–1 (using the
``score/normalization`` helpers), weights per the economic rubric, and
emits a 0–10 ``system_proposed_score``. For older years (per REQ-HIST-001)
the module degrades gracefully — fewer indicators → wider uncertainty →
manual-review priority.
"""

from __future__ import annotations


def score_economic(
    *,
    iso3: str,
    year: int,
    leader_name: str,
    indicators: dict[str, float | None],
    client_score: int | None = None,
) -> int:
    """Return a 0–10 ``system_proposed_score`` for economic well-being."""
    raise NotImplementedError("score_economic is not implemented yet. Phase E.")


__all__ = ["score_economic"]
