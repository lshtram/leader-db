"""Political freedom scoring module (requirement §9, REQ-SCORE-002).

Indicator bundle (from Stage 5):

- V-Dem liberal democracy index
- V-Dem electoral democracy index
- Freedom House total score
- Freedom House status (Free / Partly Free / Not Free)
- EIU / Polity / BMR (auxiliary)

The module projects each indicator onto 0–1, weights them per the
political-freedom rubric, and emits a 0–10 ``system_proposed_score`` plus
a short rationale. Phase E implementation; the module docstring pins the
contract so the stub can be referenced from tests and from the LLM prompt.
"""

from __future__ import annotations

from ..llm.schemas import LLMScoreOutput


def score_political_freedom(
    *,
    iso3: str,
    year: int,
    leader_name: str,
    indicators: dict[str, float | None],
    client_score: int | None = None,
) -> int:
    """Return a 0–10 ``system_proposed_score`` for political freedom.

    Parameters
    ----------
    iso3:
        Country ISO3 code.
    year:
        Target year (e.g. 2023).
    leader_name:
        System-selected leader name (used in the rationale only).
    indicators:
        Map of indicator name → 0–1 normalized value, or ``None`` if
        missing. Keys used: ``vdem_liberal_democracy``,
        ``vdem_electoral_democracy``, ``freedom_house_total``,
        ``freedom_house_status_numeric``, and the EIU/Polity/BMR
        auxiliary indicators when present.
    client_score:
        Optional client matrix score for the same ruler-year-category;
        carried for the rationale only — the module never overwrites
        ``client_score`` (REQ-REF-003).
    """
    raise NotImplementedError(
        "score_political_freedom is not implemented yet. Phase E."
    )


def rationale_for(
    *, indicators: dict[str, float | None], leader_name: str
) -> LLMScoreOutput | None:
    """Optional LLM-assisted rationale builder; returns ``None`` if LLM is disabled."""
    return None


__all__ = ["rationale_for", "score_political_freedom"]
