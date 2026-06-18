"""Stage 2 — FAS nuclear notebook (REQ-SRC-008).

Federation of American Scientists publishes the canonical reference on
each nuclear-armed state's arsenal. Mostly web pages rather than a bulk
download; the adapter scrapes a small whitelist of pages and stores a
structured table under ``data/raw/fas/`` with per-page source URLs in
``source_row_reference``.
"""

from __future__ import annotations

from pathlib import Path


def download_fas() -> Path:
    """Download FAS nuclear pages into ``data/raw/fas/``."""
    raise NotImplementedError(
        "download_fas is not implemented yet. Phase C; gated on Phase B."
    )


def ingest_fas() -> int:
    """Ingest FAS data into ``source_observations`` + processed."""
    raise NotImplementedError(
        "ingest_fas is not implemented yet. Phase C; gated on Phase B."
    )


__all__ = ["download_fas", "ingest_fas"]
