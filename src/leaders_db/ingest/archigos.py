"""Stage 2 — Archigos dataset ingestion (requirement §6, REQ-SRC-001).

Archigos is a leader-identity academic dataset covering country-years from
~1875 to the present. It is a free academic download. The adapter:

1. Downloads the latest Archigos CSV into ``data/raw/archigos/``.
2. Writes a per-source ``metadata.json`` (download date, version,
   checksum, coverage).
3. Normalizes country names to ISO3, normalizes leader names, and writes
   the result to ``data/processed/archigos/`` (parquet + CSV).
4. Pushes one row per ``(leader, country, year)`` into
   ``source_observations`` via the Stage 4 resolver.

Source URL and version land here once Phase B (source vetting) confirms
the dataset is reachable, license-compatible, and covers 2023.
"""

from __future__ import annotations

from pathlib import Path

from .external import ensure_source_metadata


def download_archigos() -> Path:
    """Download Archigos to ``data/raw/archigos/`` and update metadata.

    Implemented during Phase C; gated on Phase B vetting verdict.
    """
    raise NotImplementedError(
        "download_archigos is not implemented yet. Phase C; gated on Phase B vetting."
    )


def ingest_archigos() -> int:
    """Ingest Archigos into ``source_observations`` + ``data/processed/archigos/``.

    Returns the number of rows written.
    """
    raise NotImplementedError(
        "ingest_archigos is not implemented yet. Phase C; gated on Phase B vetting."
    )


__all__ = ["download_archigos", "ingest_archigos", "ensure_source_metadata"]
