"""Source-native country-code helpers for identity observations.

The mapping below is intentionally small and auditable. It only bridges source
codes already used by the local leader-identity sources into project ISO3 keys;
it is not a general COW-code ontology.
"""

from __future__ import annotations

from leaders_db.normalize.countries import normalize_iso3
from leaders_db.scope._country_seed import ISO3_COUNTRY_SEED

# Correlates of War numeric state codes used by Archigos and REIGN. The initial
# set mirrors the project Chronicle pilot mapping and adds Yugoslavia, which is
# present in the lifecycle seed as historical ISO3-like code ``YUG``.
COW_NUMERIC_TO_ISO3: dict[int, str] = {
    2: "USA",
    42: "DOM",
    56: "LCA",
    57: "VCT",
    60: "KNA",
    200: "GBR",
    220: "FRA",
    232: "AND",
    305: "AUT",
    316: "CZE",
    343: "MKD",
    345: "YUG",
    346: "BIH",
    365: "RUS",
    402: "CPV",
    437: "CIV",
    482: "CAF",
    484: "COG",
    490: "COD",
    520: "SOM",
    572: "SWZ",
    640: "TUR",
    698: "OMN",
    710: "CHN",
    731: "PRK",
    732: "KOR",
    750: "IND",
    835: "BRN",
    860: "TLS",
    900: "AUS",
    987: "FSM",
}

SOURCE_COUNTRY_NAME_TO_ISO3: dict[str, str] = {
    "andorra": "AND",
    "bosnia": "BIH",
    "brunei": "BRN",
    "cape verde": "CPV",
    "cen african rep": "CAF",
    "congo brz": "COG",
    "congo/zaire": "COD",
    "czech rep": "CZE",
    "dominican rep": "DOM",
    "east timor": "TLS",
    "ivory coast": "CIV",
    "korea north": "PRK",
    "korea south": "KOR",
    "micronesia": "FSM",
    "oman": "OMN",
    "macedonia": "MKD",
    "soviet union": "SUN",
    "somalia": "SOM",
    "st kitts and nevis": "KNA",
    "st lucia": "LCA",
    "st vincent": "VCT",
    "swaziland": "SWZ",
    "turkey": "TUR",
}

# Source-native three-letter country codes observed in local identity sources.
# These are not valid ISO 3166-1 alpha-3 codes, but they point to current project
# ISO3 keys in ``countries.iso3``. Keep this list small and evidence-driven.
SOURCE_NATIVE_TO_ISO3: dict[str, str] = {
    "BHU": "BTN",
    "BOS": "BIH",
    "CAP": "CPV",
    "CDI": "CIV",
    "CEN": "CAF",
    "CON": "COG",
    "CZR": "CZE",
    "DRC": "COD",
    "MAC": "MKD",
    "OMA": "OMN",
    "ROK": "KOR",
    "SER": "SRB",
    "TAW": "TWN",
}
PROJECT_ISO3_CODES: frozenset[str] = frozenset(
    {iso3 for iso3, _name in ISO3_COUNTRY_SEED} | {"CSK", "SUN", "YUG"}
)


def iso3_from_cow_code(value: object) -> str | None:
    """Return project ISO3 for a supported COW numeric code, if known."""

    code = _int_value(value)
    if code is None:
        return None
    return COW_NUMERIC_TO_ISO3.get(code)


def iso3_from_source_country(
    value: object,
    *,
    ccode: object | None = None,
    year: object | None = None,
) -> str | None:
    """Return project ISO3 from source-native country fields.

    This helper handles the source's own country token/name first, then falls
    back to the small COW numeric bridge. Historical Soviet Union rows are
    deliberately lifecycle-aware: source rows saying ``Soviet Union`` through
    1991 map to historical ``SUN`` rather than modern Russia.
    """

    text = str(value).strip() if value is not None else ""
    normalized_text = " ".join(
        text.casefold().replace(".", "").replace("-", " ").replace("_", " ").split()
    )
    source_year = _int_value(year)
    if normalized_text == "soviet union":
        return "SUN" if source_year is None or source_year <= 1991 else "RUS"
    if normalized_text in SOURCE_COUNTRY_NAME_TO_ISO3:
        return SOURCE_COUNTRY_NAME_TO_ISO3[normalized_text]
    return normalize_source_country_code(text) or iso3_from_cow_code(ccode)


def normalize_source_country_code(value: object) -> str | None:
    """Return project ISO3 for a supported 3-letter source-native country token."""

    if value is None:
        return None
    text = str(value).strip()
    if len(text) != 3 or not text.isalpha():
        return None
    code = text.upper()
    if code in SOURCE_NATIVE_TO_ISO3:
        return SOURCE_NATIVE_TO_ISO3[code]
    try:
        iso3 = normalize_iso3(code)
    except ValueError:
        return None
    if iso3 in PROJECT_ISO3_CODES:
        return iso3
    return None


def _int_value(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


__all__ = [
    "COW_NUMERIC_TO_ISO3",
    "PROJECT_ISO3_CODES",
    "SOURCE_COUNTRY_NAME_TO_ISO3",
    "SOURCE_NATIVE_TO_ISO3",
    "iso3_from_cow_code",
    "iso3_from_source_country",
    "normalize_source_country_code",
]
