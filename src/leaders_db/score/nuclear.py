"""Nuclear / global responsibility scoring module (requirement §9).

Per requirement §6: *"For the first prototype, nuclear/global
responsibility may be a lighter module, because most countries are
non-nuclear and because responsibility requires judgment beyond raw
data."*

The module uses FAS + SIPRI nuclear + NTI inputs to identify nuclear-armed
rulers and apply a small, narrow rubric. Non-nuclear states receive a
"not applicable" status that is preserved as ``null`` rather than an
invented score (REQ-HIST-002 spirit).
"""

from __future__ import annotations


def score_nuclear(
    *,
    iso3: str,
    year: int,
    leader_name: str,
    indicators: dict[str, float | None],
    client_score: int | None = None,
) -> int | None:
    """Return a 0–10 ``system_proposed_score`` for nuclear responsibility.

    Returns ``None`` for non-nuclear states (no score invented).
    """
    raise NotImplementedError("score_nuclear is not implemented yet. Phase E.")


__all__ = ["score_nuclear"]
