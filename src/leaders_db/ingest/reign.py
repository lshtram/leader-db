"""Stage 2 — REIGN (Rulers, Elections, and Irregular Governance) (REQ-SRC-001).

Free academic dataset; country-month coverage of leadership and election
events. The adapter handles monthly grain by rolling up to country-year
for the leader resolver.
"""

from __future__ import annotations

from pathlib import Path


def download_reign() -> Path:
    """Download REIGN into ``data/raw/reign/``."""
    raise NotImplementedError(
        "download_reign is not implemented yet. Phase C; gated on Phase B."
    )


def ingest_reign() -> int:
    """Ingest REIGN into ``source_observations`` + processed."""
    raise NotImplementedError(
        "ingest_reign is not implemented yet. Phase C; gated on Phase B."
    )


__all__ = ["download_reign", "ingest_reign"]
