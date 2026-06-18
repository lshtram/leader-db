"""Stage 2 — SIPRI (Stockholm International Peace Research Institute).

Three sub-datasets are relevant (requirement §6):

- ``sipri_milex`` — military expenditure as share of GDP / govt expenditure
  (REQ-SRC-006).
- ``sipri_atrx``  — arms transfers (REQ-SRC-006).
- ``sipri_nuclear`` — nuclear forces (REQ-SRC-008).

The adapter downloads whichever subsets are required by the run config
and pushes one ``source_observations`` row per indicator.
"""

from __future__ import annotations

from pathlib import Path


def download_sipri() -> Path:
    """Download SIPRI subsets into ``data/raw/sipri/``."""
    raise NotImplementedError(
        "download_sipri is not implemented yet. Phase C; gated on Phase B."
    )


def ingest_sipri() -> int:
    """Ingest SIPRI subsets into ``source_observations`` + processed."""
    raise NotImplementedError(
        "ingest_sipri is not implemented yet. Phase C; gated on Phase B."
    )


__all__ = ["download_sipri", "ingest_sipri"]
