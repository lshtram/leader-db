"""Stage 12 — compare system output against the client matrix (REQ-CMP-001).

For each country, produce:

- Client leader vs system leader
- Client leader start year vs external tenure data
- Per-category score comparison and delta
- Average delta
- Per-item confidence
- Missing / disputed data
- Manual-review flag

Outputs:

- ``data/outputs/validation_<year>_leader_identity.csv``
- ``data/outputs/validation_<year>_scores.csv``
- ``data/outputs/validation_<year>_summary.md``
- ``data/outputs/validation_<year>_high_delta_cases.csv``
- ``data/outputs/validation_<year>_manual_review_queue.csv``

Phase E implementation.
"""

from __future__ import annotations

from pathlib import Path


def compare_vs_client(year: int) -> list[Path]:
    """Run Stage 12 for ``year``.

    Returns the absolute paths of every file written.
    """
    raise NotImplementedError("compare_vs_client is not implemented yet. Phase E.")


__all__ = ["compare_vs_client"]
