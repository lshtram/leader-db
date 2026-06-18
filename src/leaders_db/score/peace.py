"""International peace vs aggression scoring module (requirement §9).

Indicator bundle (from Stage 5):

- UCDP conflict involvement
- COW/MID dispute involvement
- SIPRI military expenditure as share of GDP / govt expenditure

The module is implemented in Phase E. Per the requirements, this is one
of the categories the manual-review queue must prioritize (REQ-REV-002).
"""

from __future__ import annotations


def score_peace(
    *,
    iso3: str,
    year: int,
    leader_name: str,
    indicators: dict[str, float | None],
    client_score: int | None = None,
) -> int:
    """Return a 0–10 ``system_proposed_score`` for international peace/aggression."""
    raise NotImplementedError("score_peace is not implemented yet. Phase E.")


__all__ = ["score_peace"]
