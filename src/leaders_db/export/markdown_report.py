"""Markdown report writer.

Used by the validation layer to emit the ``validation_<year>_summary.md``
file. The writer is intentionally tiny — the layout is owned by the
caller (Stage 15 ``summary_report``).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def write_markdown_report(content: str, path: Path | str) -> Path:
    """Atomically write a markdown report to ``path``.

    Writes UTF-8 and preserves trailing newlines so downstream formatters
    (Markdown renderers, GitHub, pandoc) behave consistently.
    """
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = content if content.endswith("\n") else content + "\n"
    with tempfile.NamedTemporaryFile(
        "w",
        delete=False,
        dir=target.parent,
        prefix=f".{target.name}.",
        encoding="utf-8",
    ) as tmp:
        tmp.write(payload)
        tmp_path = Path(tmp.name)
    try:
        os.replace(tmp_path, target)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
    return target


__all__ = ["write_markdown_report"]
