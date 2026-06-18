"""Atomic CSV writer.

Wraps :func:`pandas.DataFrame.to_csv` so every CSV export uses the same
atomic-rename pattern as :func:`leaders_db.ingest.external.atomic_write_csv`.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any


def write_csv(df: Any, path: Path | str) -> Path:
    """Atomically write ``df`` to ``path`` (CSV).

    The file is written to a temp file in the same directory and then
    renamed, so partial files never appear in ``data/outputs/``.
    """
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
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


__all__ = ["write_csv"]
