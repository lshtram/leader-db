"""Stable loading of versioned chapter guides."""

from __future__ import annotations

import re
from pathlib import Path

_GUIDE_FILES = {
    "1B": "1b-nuclear-existential-risk.md",
    "2B": "2b-international-peace.md",
    "3B": "3b-domestic-safety.md",
    "4B": "4b-political-freedom.md",
    "5B": "5b-economic-wellbeing.md",
    "6B": "6b-social-wellbeing.md",
    "7B": "7b-integrity.md",
    "8B": "8b-effectiveness.md",
}


def load_chapter_guide(
    chapter_id: str, *, project_root: Path | None = None
) -> tuple[str, str]:
    """Return the complete guide text and its declared rubric version."""

    root = project_root or Path(__file__).resolve().parents[3]
    try:
        filename = _GUIDE_FILES[chapter_id]
    except KeyError as exc:
        raise ValueError(f"unsupported chapter_id: {chapter_id!r}") from exc
    text = (root / "docs/methodology/chapter-guides" / filename).read_text(
        encoding="utf-8"
    )
    match = re.search(r"Rubric version:\s*`([^`]+)`", text)
    if match is None:
        raise ValueError("chapter guide has no rubric version")
    return text, match.group(1)


__all__ = ["load_chapter_guide"]
