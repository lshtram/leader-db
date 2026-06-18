"""Stage 2 — Transparency International CPI (REQ-SRC-005).

Annual xlsx download from Transparency International. The adapter
normalizes CPI scores (0–100, higher = cleaner) into 0–1 and pushes one
row per country-year into ``source_observations``.
"""

from __future__ import annotations

from pathlib import Path


def download_transparency_cpi() -> Path:
    """Download Transparency International CPI into ``data/raw/transparency_cpi/``."""
    raise NotImplementedError(
        "download_transparency_cpi is not implemented yet. Phase C; gated on Phase B."
    )


def ingest_transparency_cpi() -> int:
    """Ingest CPI into ``source_observations`` + processed."""
    raise NotImplementedError(
        "ingest_transparency_cpi is not implemented yet. Phase C; gated on Phase B."
    )


__all__ = ["download_transparency_cpi", "ingest_transparency_cpi"]
