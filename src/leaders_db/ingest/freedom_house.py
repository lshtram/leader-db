"""Stage 2 — Freedom House Freedom in the World (REQ-SRC-002).

Annual freedom ratings (political rights + civil liberties, plus a
combined status). Downloaded as an xlsx from the Freedom House website.
"""

from __future__ import annotations

from pathlib import Path


def download_freedom_house() -> Path:
    """Download Freedom House into ``data/raw/freedom_house/``."""
    raise NotImplementedError(
        "download_freedom_house is not implemented yet. Phase C; gated on Phase B."
    )


def ingest_freedom_house() -> int:
    """Ingest Freedom House into ``source_observations`` + processed."""
    raise NotImplementedError(
        "ingest_freedom_house is not implemented yet. Phase C; gated on Phase B."
    )


__all__ = ["download_freedom_house", "ingest_freedom_house"]
