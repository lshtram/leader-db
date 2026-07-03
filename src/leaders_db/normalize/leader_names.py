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
_PARENTHETICAL_PATTERN = re.compile(r"\([^)]*\)")
_LEADING_TITLES = {
    "acting",
    "chairman",
    "chancellor",
    "deputy",
    "dr",
    "general",
    "hon",
    "king",
    "minister",
    "president",
    "prime",
    "prof",
    "queen",
    "sir",
    "state",
}
_TRAILING_SUFFIXES = {"jr", "sr", "ii", "iii", "iv"}


def normalize_leader_name(value: str) -> str:
    """Lowercase, accent-strip, drop punctuation, collapse whitespace.

    Used to compare leader strings across sources. No language detection
    or transliteration is attempted — that lives in the resolver layer.
    """
    if value is None:
        raise ValueError("leader name is None")
    text = _PARENTHETICAL_PATTERN.sub(" ", str(value))
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = _DROP_PATTERN.sub(" ", text)
    tokens = re.sub(r"\s+", " ", text).strip().split()
    while tokens and tokens[0] in _LEADING_TITLES:
        tokens.pop(0)
    while tokens and tokens[-1] in _TRAILING_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def name_match_key(value: str) -> str:
    """Return a stable key suitable for equality checks across sources.

    Equivalent to :func:`normalize_leader_name` today; kept as a separate
    function so the matching strategy can evolve (e.g. dropping patronymic
    prefixes, swapping roman/cyrillic transliterations) without changing
    the public normalize interface.
    """
    return normalize_leader_name(value)
