"""Small transform helpers for Wikidata HoS/HoG observations."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def statement_hash(statement_uri: str) -> str:
    """Return the legacy 10-character SHA-256 statement prefix."""
    if not statement_uri:
        return "-"
    return hashlib.sha256(statement_uri.encode("utf-8")).hexdigest()[:10]


def parse_raw_binding(raw_value_text: str) -> dict[str, Any] | None:
    """Return the parsed SPARQL binding JSON, or ``None`` on failure."""
    if not raw_value_text:
        return None
    try:
        parsed = json.loads(raw_value_text)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def text(value: Any) -> str:
    """Return stripped text, treating pandas nulls as absent."""
    if value is None:
        return ""
    try:
        import pandas as pd

        if pd.isna(value):
            return ""
    except (ImportError, TypeError, ValueError):
        pass
    return str(value).strip()


def text_or_none(value: Any) -> str | None:
    """Return the trimmed text, ``None`` when absent or null."""
    output = text(value)
    if not output or output.lower() == "none":
        return None
    return output


def coerce_int(value: Any) -> int | None:
    """Return ``value`` coerced to ``int`` when possible."""
    if value is None:
        return None
    try:
        import pandas as pd

        if pd.isna(value):
            return None
    except (ImportError, TypeError, ValueError):
        pass
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "coerce_int",
    "parse_raw_binding",
    "statement_hash",
    "text",
    "text_or_none",
]
