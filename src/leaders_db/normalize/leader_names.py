"""Leader-name normalization helpers.

The Stage 4 leader resolver needs a deterministic way to compare leader
strings across sources. This module ships the small building blocks
(:func:`normalize_leader_name`, :func:`name_match_key`); the full
matching strategy (alias table, fuzzy thresholds, decision rules per
§4) lands in :mod:`leaders_db.resolve.leader_resolver` during Phase E.
"""

from __future__ import annotations

import re
import unicodedata


_DROP_PATTERN = re.compile(r"[^a-z0-9\s]")


def normalize_leader_name(value: str) -> str:
    """Lowercase, accent-strip, drop punctuation, collapse whitespace.

    Used to compare leader strings across sources. No language detection
    or transliteration is attempted — that lives in the resolver layer.
    """
    if value is None:
        raise ValueError("leader name is None")
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = _DROP_PATTERN.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def name_match_key(value: str) -> str:
    """Return a stable key suitable for equality checks across sources.

    Equivalent to :func:`normalize_leader_name` today; kept as a separate
    function so the matching strategy can evolve (e.g. dropping patronymic
    prefixes, swapping roman/cyrillic transliterations) without changing
    the public normalize interface.
    """
    return normalize_leader_name(value)
