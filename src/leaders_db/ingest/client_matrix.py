"""Stage 1 — ingest the client's existing matrix (requirement §8, REQ-STAGE-002).

Loads the xlsx bundle staged under ``data/raw/client_existing/`` and
extracts:

- ``countries`` + ``country_years`` (with the population-threshold logic
  from REQ-SCOPE-003).
- ``leaders`` + ``leader_aliases`` + ``ruler_spells`` + ``ruler_years``.
- ``score_categories`` (the ten canonical categories from §4).
- ``ruler_scores`` (one row per ruler-year-category, with
  ``client_score`` populated and ``system_proposed_score``/``final_score``
  left NULL — the latter two are filled by Stage 9+ and the manual-review
  workflow respectively).

Output: ``data/processed/client_2023_matrix_normalized.csv`` (and a
matching SQLite copy after the next ``init-db`` run).

The full implementation lands in Phase C (data acquisition). Reading the
``metadata.json`` in ``data/raw/client_existing/`` and listing the
candidate xlsx files is a useful smoke test for the data lake bootstrap.
"""

from __future__ import annotations

from pathlib import Path

from ..paths import raw_dir


def list_client_bundle_files() -> list[Path]:
    """List the xlsx/docx files staged under ``data/raw/client_existing/``.

    Phase A helper used by tests and the Phase B source-vetting probe to
    confirm the client bundle is in place before any Stage 1 work.
    """
    client_dir = raw_dir("client_existing")
    if not client_dir.is_dir():
        return []
    return sorted(
        p
        for p in client_dir.iterdir()
        if p.is_file() and p.suffix.lower() in {".xlsx", ".docx"}
    )


def read_client_metadata() -> dict[str, object]:
    """Return the parsed ``metadata.json`` from ``data/raw/client_existing/``.

    Raises :class:`FileNotFoundError` if the file is absent. The returned
    dict is the raw JSON; call sites should validate it against the
    ``SourceMetadata`` shape described in ``docs/sources/registry.md``.
    """
    import json

    meta = raw_dir("client_existing") / "metadata.json"
    if not meta.is_file():
        raise FileNotFoundError(f"client metadata not found: {meta}")
    return json.loads(meta.read_text(encoding="utf-8"))


def ingest_client_matrix(year: int) -> int:
    """Run Stage 1 for the given year.

    Returns the number of ``ruler_years`` rows written.

    Implemented during Phase C (data acquisition).
    """
    raise NotImplementedError(
        "ingest_client_matrix is not implemented yet. Phase C; see docs/workplan.md."
    )


__all__ = ["ingest_client_matrix", "list_client_bundle_files", "read_client_metadata"]
