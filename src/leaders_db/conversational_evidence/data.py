"""Load collector-owned data files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).with_name("data")


def load(name: str) -> dict[str, Any]:
    """Load one JSON data file."""

    value = json.loads((DATA_DIR / name).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{name} must contain a JSON object")
    return value


def questions() -> list[dict[str, str]]:
    """Return all questions in their configured order."""

    return [q for chapter in load("questions.json")["chapters"] for q in chapter["questions"]]
