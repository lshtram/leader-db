"""Stage 2 — CIRIGHTS Physical Integrity Rights (REQ-SRC-007).

Annual country-year indicators on physical-integrity rights abuse
(disappearance, killing, political imprisonment, torture). Free
academic download. Feeds the domestic-violence scoring category.
"""

from __future__ import annotations

from pathlib import Path


def download_cirights() -> Path:
    """Download CIRIGHTS into ``data/raw/cirights/``."""
    raise NotImplementedError(
        "download_cirights is not implemented yet. Phase C; gated on Phase B."
    )


def ingest_cirights() -> int:
    """Ingest CIRIGHTS into ``source_observations`` + processed."""
    raise NotImplementedError(
        "ingest_cirights is not implemented yet. Phase C; gated on Phase B."
    )


__all__ = ["download_cirights", "ingest_cirights"]
