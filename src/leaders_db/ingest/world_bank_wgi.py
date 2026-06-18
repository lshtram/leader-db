"""Stage 2 — World Bank WGI (REQ-SRC-004, REQ-SRC-005).

Free API. Provides six aggregate governance indicators, including
``Control of Corruption``, ``Government Effectiveness``, and ``Rule of Law``.
The adapter splits corruption vs governance indicators into separate
normalized outputs because they feed different scoring categories.
"""

from __future__ import annotations

from pathlib import Path


def download_world_bank_wgi() -> Path:
    """Download WGI into ``data/raw/world_bank_wgi/``."""
    raise NotImplementedError(
        "download_world_bank_wgi is not implemented yet. Phase C; gated on Phase B."
    )


def ingest_world_bank_wgi() -> int:
    """Ingest WGI into ``source_observations`` + processed."""
    raise NotImplementedError(
        "ingest_world_bank_wgi is not implemented yet. Phase C; gated on Phase B."
    )


__all__ = ["download_world_bank_wgi", "ingest_world_bank_wgi"]
