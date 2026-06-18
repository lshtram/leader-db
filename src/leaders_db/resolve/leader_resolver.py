"""Stage 4 — leader resolver (requirement §8, REQ-STAGE-005).

For each country-year:

1. Pull candidate leaders from Archigos, Leader Survival, REIGN, and the
   client matrix.
2. Normalize leader names (see :mod:`leaders_db.normalize.leader_names`).
3. Compare names, dates, and office titles.
4. Select the likely actual ruler.
5. Mark confidence and disagreement via the
   ``ruler_years.match_status`` enum (exact_match, name_variant_match,
   different_formal_same_actual, multiple_possible_rulers, client_only,
   external_only, conflict_between_sources, manual_review_required).

Output: ``data/outputs/leader_resolution_<year>.csv``.

Phase E implementation.
"""

from __future__ import annotations

from pathlib import Path


def resolve_leaders(year: int) -> Path:
    """Resolve the actual ruler per country-year for ``year``.

    Returns the absolute path to the ``leader_resolution_<year>.csv`` file.
    """
    raise NotImplementedError("resolve_leaders is not implemented yet. Phase E.")


__all__ = ["resolve_leaders"]
