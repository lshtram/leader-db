"""Stage 14 — manual-review queue (requirement §14, REQ-REV-002).

Prioritized queue with the §14 priority order:

1. leader identity mismatch
2. category score delta > 2
3. confidence < 60
4. multiple possible rulers
5. missing primary sources
6. nuclear / global responsibility cases
7. war / aggression cases
8. severe human-rights / repression cases
9. strong disagreement with the client matrix

The output is a CSV with one row per review item and a stable
``priority_rank`` column. Reviewers update ``review_status`` directly
in the database; this queue is a snapshot.
"""

from __future__ import annotations

from pathlib import Path


def build_review_queue(year: int) -> Path:
    """Build the manual-review queue CSV for ``year``."""
    raise NotImplementedError("build_review_queue is not implemented yet. Phase E.")


__all__ = ["build_review_queue"]
