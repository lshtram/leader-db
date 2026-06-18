"""Stage 2 — World Bank WDI (REQ-SRC-003).

Free API (no key required). Provides population, GDP, GDP per capita,
and many social/economic indicators. The adapter uses the ``wbgapi`` or
direct REST client to materialize the indicator bundle needed by Stage 5.
"""

from __future__ import annotations

from pathlib import Path


def download_world_bank_wdi() -> Path:
    """Download WDI indicators into ``data/raw/world_bank_wdi/``."""
    raise NotImplementedError(
        "download_world_bank_wdi is not implemented yet. Phase C; gated on Phase B."
    )


def ingest_world_bank_wdi() -> int:
    """Ingest WDI into ``source_observations`` + processed."""
    raise NotImplementedError(
        "ingest_world_bank_wdi is not implemented yet. Phase C; gated on Phase B."
    )


__all__ = ["download_world_bank_wdi", "ingest_world_bank_wdi"]
