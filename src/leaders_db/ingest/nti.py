"""Stage 2 — NTI (Nuclear Threat Initiative) country profiles (REQ-SRC-008).

NTI publishes country profiles covering nuclear materials, sites, and
proliferation-relevant facts. Mostly web pages; the adapter fetches a
curated whitelist of country pages and stores structured data with the
page URL captured in ``source_row_reference``.
"""

from __future__ import annotations

from pathlib import Path


def download_nti() -> Path:
    """Download NTI country profiles into ``data/raw/nti/``."""
    raise NotImplementedError(
        "download_nti is not implemented yet. Phase C; gated on Phase B."
    )


def ingest_nti() -> int:
    """Ingest NTI data into ``source_observations`` + processed."""
    raise NotImplementedError(
        "ingest_nti is not implemented yet. Phase C; gated on Phase B."
    )


__all__ = ["download_nti", "ingest_nti"]
