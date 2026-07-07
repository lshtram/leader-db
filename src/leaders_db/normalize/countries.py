"""Country-name and ISO3 normalization helpers (Stage 3 building blocks).

The country-matching layer (Stage 3) uses ISO3 as the primary key. Each
ingestion step normalizes the raw country string from a source into:

1. An ISO3 code (canonical).
2. A lowercased, accent-stripped, whitespace-collapsed name used for
   alias matching and human-readable fallback.

This module ships a deterministic ``normalize_country_name`` helper and a
strict ``normalize_iso3`` validator. The full alias table grows over time
into ``data/metadata/country_aliases.csv``; a small in-code seed handles
common historical / variant names so the package is usable before the
alias file exists.

REQ-STAGE-004 enumerates the rules the country matcher must enforce.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Final

# A small in-code seed of common alias -> ISO3 mappings. The full alias
# table lives in data/metadata/country_aliases.csv and is loaded at runtime
# by the country matcher; this seed covers common historical names that
# show up in source datasets before the alias file is built.
COUNTRY_NAME_NORMALIZATION: Final[dict[str, str]] = {
    # historical / variant spellings -> canonical ISO3
    "russia": "RUS",
    "russian federation": "RUS",
    "ussr": "RUS",
    "soviet union": "RUS",
    "united states": "USA",
    "united states of america": "USA",
    "us": "USA",
    "u.s.": "USA",
    "u.s.a.": "USA",
    "america": "USA",
    "uk": "GBR",
    "u.k.": "GBR",
    "united kingdom": "GBR",
    "great britain": "GBR",
    "britain": "GBR",
    "south korea": "KOR",
    "korea, republic of": "KOR",
    "republic of korea": "KOR",
    "north korea": "PRK",
    "korea, democratic people's republic of": "PRK",
    "democratic people's republic of korea": "PRK",
    "iran": "IRN",
    "iran (islamic republic of)": "IRN",
    "islamic republic of iran": "IRN",
    "syria": "SYR",
    "syrian arab republic": "SYR",
    "serbia and montenegro": "SCG",
    "yugoslavia": "YUG",
    "laos": "LAO",
    "lao people's democratic republic": "LAO",
    "bolivia": "BOL",
    "bolivia (plurinational state of)": "BOL",
    "plurinational state of bolivia": "BOL",
    "venezuela": "VEN",
    "venezuela (bolivarian republic of)": "VEN",
    "bolivarian republic of venezuela": "VEN",
    "tanzania": "TZA",
    "united republic of tanzania": "TZA",
    "czechia": "CZE",
    "czech republic": "CZE",
    "czechoslovakia": "CSK",
    "german democratic republic": "DDR",
    "east germany": "DDR",
    "germany e": "DDR",
    "germany w": "DEU",
    "kosovo": "XKX",
    "slovak republic": "SVK",
    "slovak republic slovakia": "SVK",
    "macedonia fyr": "MKD",
    "bosnia herzegovina": "BIH",
    "bosnia herzegovenia": "BIH",
    "ivory coast": "CIV",
    "cote d ivoire": "CIV",
    "cote d'ivoire": "CIV",
    "côte d'ivoire": "CIV",
    "dr congo zaire": "COD",
    "macedonia": "MKD",
    "north macedonia": "MKD",
    "republic of north macedonia": "MKD",
    "the former yugoslav republic of macedonia": "MKD",
    "zimbabwe rhodesia": "ZWE",
    "kingdom of eswatini swaziland": "SWZ",
    "madagascar malagasy": "MDG",
    "yemen north yemen": "YEM",
    "burma": "MMR",
    "burma myanmar": "MMR",
    "myanmar": "MMR",
    "myanmar burma": "MMR",
    "cambodia kampuchea": "KHM",
    "east timor timor leste": "TLS",
    "brunei": "BRN",
    "cape verde": "CPV",
    "congo dr": "COD",
    "congo democratic republic of": "COD",
    "congo kinshasa": "COD",
    "congo republic": "COG",
    "congo rep": "COG",
    "congo republic of": "COG",
    "congo brazzaville": "COG",
    "gambia the": "GMB",
    "the gambia": "GMB",
    "korea north": "PRK",
    "korea democratic people's republic of north korea": "PRK",
    "korea democratic peoples republic of north korea": "PRK",
    "korea south": "KOR",
    "korea republic of south korea": "KOR",
    "kyrgyz republic": "KGZ",
    "swaziland": "SWZ",
    "eswatini": "SWZ",
    "kingdom of eswatini": "SWZ",
    "vatican": "VAT",
    "holy see": "VAT",
    "palestine": "PSE",
    "state of palestine": "PSE",
    "st vincent and the grenadines": "VCT",
    "turkey": "TUR",
    "turkiye": "TUR",
    "türkiye": "TUR",
    "republic of turkiye": "TUR",
    "republic of türkiye": "TUR",
    "viet nam": "VNM",
}


def normalize_iso3(value: str) -> str:
    """Validate and uppercase a 3-letter ISO 3166-1 alpha-3 code.

    Raises :class:`ValueError` when ``value`` is not a 3-letter ASCII
    string. Use :func:`normalize_country_name` first when the input is a
    human-readable country name.
    """
    if value is None:
        raise ValueError("iso3 is None")
    code = str(value).strip().upper()
    if len(code) != 3 or not code.isalpha() or not code.isascii():
        raise ValueError(f"invalid ISO3 code: {value!r}")
    return code


def normalize_country_name(value: str) -> str:
    """Lowercase, accent-strip, and collapse whitespace in a country name.

    The result is used for alias matching against the canonical
    ``country_name_normalized`` column. No ISO3 mapping happens here —
    use the alias table for that.
    """
    if value is None:
        raise ValueError("country name is None")
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s']", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def alias_to_iso3(normalized_name: str) -> str | None:
    """Look up a normalized country name in the in-code alias seed.

    Returns ``None`` when the name is not in the seed; the runtime alias
    table (``data/metadata/country_aliases.csv``) is consulted by the
    Stage 3 country matcher for unknown names.
    """
    return COUNTRY_NAME_NORMALIZATION.get(normalized_name)
