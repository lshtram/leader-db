"""Source-native country-code helpers for identity observations.

The mapping below is intentionally small and auditable. It only bridges source
codes already used by the local leader-identity sources into project ISO3 keys;
it is not a general COW-code ontology.
"""

from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

from leaders_db.normalize.countries import normalize_country_name, normalize_iso3
from leaders_db.paths import metadata_dir
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
    "congo brazzaville": "COG",
    "congo kinshasa": "COD",
    "congo/zaire": "COD",
    "czech rep": "CZE",
    "czechoslovakia": "CSK",
    "dominican rep": "DOM",
    "east timor": "TLS",
    "german democratic republic": "DDR",
    "german federal republic": "DEU",
    "germany e": "DDR",
    "germany w": "DEU",
    "ivory coast": "CIV",
    "kosovo": "XKX",
    "korea north": "PRK",
    "korea south": "KOR",
    "micronesia": "FSM",
    "oman": "OMN",
    "macedonia": "MKD",
    "soviet union": "SUN",
    "serbia and montenegro": "SCG",
    "yugoslavia": "YUG",
    "somalia": "SOM",
    "st kitts and nevis": "KNA",
    "st lucia": "LCA",
    "st vincent": "VCT",
    "st vincent and the grenadines": "VCT",
    "swaziland": "SWZ",
    "turkey": "TUR",
    "tanzania united republic of": "TZA",
    "the gambia": "GMB",
    "moldova republic of": "MDA",
    "yemen arab republic": "YEM",
    "yemen north": "YEM",
    "yemen people's republic": "YEM",
}

# Source-native three-letter country codes observed in local identity sources.
# These are not valid ISO 3166-1 alpha-3 codes, but they point to current project
# ISO3 keys in ``countries.iso3``. Keep this list small and evidence-driven.
SOURCE_NATIVE_TO_ISO3: dict[str, str] = {
    "ADO": "AND",
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
    "ROM": "ROU",
    "ROK": "KOR",
    "SER": "SRB",
    "TAW": "TWN",
    "TMP": "TLS",
    "ZAR": "COD",
    "KSV": "XKX",
}
PROJECT_ISO3_CODES: frozenset[str] = frozenset(
    {iso3 for iso3, _name in ISO3_COUNTRY_SEED} | {"CSK", "DDR", "SCG", "SUN", "XKX", "YUG"}
)
UCDP_COUNTRY_ISO3_CSV_NAME: str = "ucdp_country_iso3.csv"
UCDP_COUNTRY_YEAR_TO_ISO3: tuple[tuple[int, int, int, str], ...] = (
    # UCDP 345 is labelled "Serbia (Yugoslavia)" in GED 23.1. Local GED rows
    # for this id are 1991-2001; project lifecycle coverage uses YUG through 2002.
    (345, 1991, 2002, "YUG"),
    # UCDP 365 is labelled "Russia (Soviet Union)" and spans both identities.
    (365, 1989, 1991, "SUN"),
    (365, 1992, 9999, "RUS"),
)


def iso3_from_cow_code(value: object) -> str | None:
    """Return project ISO3 for a supported COW numeric code, if known."""

    code = _int_value(value)
    if code is None:
        return None
    return COW_NUMERIC_TO_ISO3.get(code)


def iso3_from_ucdp_country_id(
    value: object,
    *,
    year: object | None = None,
    mapping_path: Path | None = None,
) -> str | None:
    """Return project ISO3 for a supported UCDP numeric country id.

    UCDP GED ``country_id`` values are source-native identifiers, not a general
    COW/GW ontology. The committed CSV is intentionally small and evidence-driven;
    unknown ids return ``None`` so callers skip rather than guess.
    """

    code = _int_value(value)
    if code is None:
        return None
    source_year = _int_value(year)
    if source_year is not None:
        for row_code, start_year, end_year, iso3 in UCDP_COUNTRY_YEAR_TO_ISO3:
            if code == row_code and start_year <= source_year <= end_year:
                return iso3
    mapping = (
        _load_ucdp_country_iso3_mapping(mapping_path)
        if mapping_path is not None
        else _load_default_ucdp_country_iso3_mapping()
    )
    return mapping.get(code)


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
    normalized_text = normalize_country_name(text) if text else ""
    source_year = _int_value(year)
    if normalized_text in {"soviet union", "ussr"}:
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


@lru_cache(maxsize=1)
def _load_default_ucdp_country_iso3_mapping() -> dict[int, str]:
    return _load_ucdp_country_iso3_mapping(metadata_dir() / UCDP_COUNTRY_ISO3_CSV_NAME)


def _load_ucdp_country_iso3_mapping(path: Path) -> dict[int, str]:
    if not path.is_file():
        return {}
    mapping: dict[int, str] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            code = _int_value(row.get("ucdp_country_id"))
            iso3 = normalize_source_country_code(row.get("iso3"))
            if code is not None and iso3 is not None:
                mapping[code] = iso3
    return mapping


__all__ = [
    "COW_NUMERIC_TO_ISO3",
    "PROJECT_ISO3_CODES",
    "SOURCE_COUNTRY_NAME_TO_ISO3",
    "SOURCE_NATIVE_TO_ISO3",
    "UCDP_COUNTRY_ISO3_CSV_NAME",
    "UCDP_COUNTRY_YEAR_TO_ISO3",
    "iso3_from_cow_code",
    "iso3_from_source_country",
    "iso3_from_ucdp_country_id",
    "normalize_source_country_code",
]
