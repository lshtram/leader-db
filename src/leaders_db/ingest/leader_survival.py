"""Stage 2 — Leader Survival / Political Leaders through Time (REQ-SRC-001).

Free academic dataset; country-year coverage of leaders and survival
outcomes. The adapter mirrors :mod:`leaders_db.ingest.archigos` in shape.
"""

from __future__ import annotations

from pathlib import Path


def download_leader_survival() -> Path:
    """Download Leader Survival into ``data/raw/leader_survival/``."""
    raise NotImplementedError(
        "download_leader_survival is not implemented yet. Phase C; gated on Phase B."
    )


def ingest_leader_survival() -> int:
    """Ingest Leader Survival into ``source_observations`` + processed."""
    raise NotImplementedError(
        "ingest_leader_survival is not implemented yet. Phase C; gated on Phase B."
    )


__all__ = ["download_leader_survival", "ingest_leader_survival"]
