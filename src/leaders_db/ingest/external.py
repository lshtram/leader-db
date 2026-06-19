"""Generic Stage 2 ingestion helpers.

Shared by per-source adapters in :mod:`leaders_db.ingest.<source>`. Each
adapter should:

1. Call :func:`ensure_source_metadata` to read/write the per-source
   ``metadata.json``.
2. Call :func:`atomic_write_parquet` (or ``atomic_write_csv``) to land
   normalized output under ``data/processed/<source>/``.
3. Use :func:`write_observations` to push raw + normalized values into
   the ``source_observations`` table.

Helpers are deliberately tiny — the bulk of the per-source work lives in
the per-source adapter modules and is implemented during Phase C (data
acquisition), only after Phase B (source vetting) approves the source.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

from ..paths import processed_dir, raw_dir


def ensure_source_metadata(source_key: str) -> dict[str, Any]:
    """Read the ``metadata.json`` for a source, creating a placeholder if absent.

    The placeholder is intentionally minimal; a real ingestion run fills
    in ``download_date``, ``local_files``, ``checksum_sha256``, and
    transitions ``ingestion_status`` from ``pending`` → ``downloaded`` →
    ``ingested``.
    """
    meta_path = raw_dir(source_key) / "metadata.json"
    if meta_path.is_file():
        return json.loads(meta_path.read_text(encoding="utf-8"))

    placeholder = {
        "source_name": source_key,
        "source_version": "",
        "download_date": None,
        "coverage": "",
        "years_available": "",
        "license_note": "",
        "local_files": [],
        "ingestion_status": "pending",
        "source_url": "",
        "checksum_sha256": "",
    }
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(placeholder, indent=2, sort_keys=True), encoding="utf-8")
    return placeholder


def update_source_metadata(source_key: str, **changes: Any) -> dict[str, Any]:
    """Update and rewrite the source's ``metadata.json``.

    Records ``download_date`` automatically when ``ingestion_status`` is
    set to ``downloaded`` and no explicit ``download_date`` is given.
    """
    meta = ensure_source_metadata(source_key)
    if (
        changes.get("ingestion_status") == "downloaded"
        and "download_date" not in changes
    ):
        changes["download_date"] = date.today().isoformat()
    meta.update(changes)
    meta_path = raw_dir(source_key) / "metadata.json"
    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8")
    return meta


def atomic_write_parquet(source_key: str, table_name: str, df: Any) -> Path:
    """Atomically write a DataFrame to ``data/processed/<source>/<table>.parquet``.

    The write happens to a temp file in the same directory and is renamed
    into place, so partial files never appear in the data lake.
    """
    processed_dir(source_key).mkdir(parents=True, exist_ok=True)
    target = processed_dir(source_key) / f"{table_name}.parquet"
    with tempfile.NamedTemporaryFile(
        "wb", delete=False, dir=target.parent, prefix=f".{target.name}."
    ) as tmp:
        tmp_path = Path(tmp.name)
    try:
        df.to_parquet(tmp_path, index=False)
        os.replace(tmp_path, target)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
    return target


def atomic_write_csv(source_key: str, table_name: str, df: Any) -> Path:
    """Atomically write a DataFrame to ``data/processed/<source>/<table>.csv``."""
    processed_dir(source_key).mkdir(parents=True, exist_ok=True)
    target = processed_dir(source_key) / f"{table_name}.csv"
    with tempfile.NamedTemporaryFile(
        "w",
        delete=False,
        dir=target.parent,
        prefix=f".{target.name}.",
        encoding="utf-8",
        newline="",
    ) as tmp:
        tmp_path = Path(tmp.name)
    try:
        df.to_csv(tmp_path, index=False)
        os.replace(tmp_path, target)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
    return target


__all__ = [
    "atomic_write_csv",
    "atomic_write_parquet",
    "ensure_source_metadata",
    "update_source_metadata",
]
