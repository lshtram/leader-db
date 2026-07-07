"""Source-native country-code mapping tests."""

from __future__ import annotations

import pytest

from leaders_db.sources.country_codes import (
    iso3_from_cow_code,
    iso3_from_source_country,
    iso3_from_ucdp_country_id,
    normalize_source_country_code,
)


@pytest.mark.parametrize(
    ("source_code", "project_iso3"),
    [
        ("ADO", "AND"),
        ("ROK", "KOR"),
        ("TAW", "TWN"),
        ("DRC", "COD"),
        ("CEN", "CAF"),
        ("CDI", "CIV"),
        ("CAP", "CPV"),
        ("CON", "COG"),
        ("MAC", "MKD"),
        ("BOS", "BIH"),
        ("CZR", "CZE"),
        ("OMA", "OMN"),
        ("ROM", "ROU"),
        ("SER", "SRB"),
        ("BHU", "BTN"),
        ("TMP", "TLS"),
        ("ZAR", "COD"),
        ("KSV", "XKX"),
    ],
)
def test_source_native_country_codes_map_to_project_iso3(
    source_code: str,
    project_iso3: str,
) -> None:
    assert normalize_source_country_code(source_code) == project_iso3


def test_source_native_country_codes_keep_supported_iso3_and_reject_unknowns() -> None:
    assert normalize_source_country_code("USA") == "USA"
    assert normalize_source_country_code("ZZZ") is None
    assert normalize_source_country_code("Korea") is None


@pytest.mark.parametrize(
    ("source_name", "ccode", "project_iso3"),
    [
        ("St Lucia", 56, "LCA"),
        ("St Kitts and Nevis", 60, "KNA"),
        ("St Vincent", 57, "VCT"),
        ("Andorra", 232, "AND"),
        ("Austria", 305, "AUT"),
        ("Micronesia", 987, "FSM"),
        ("Oman", 698, "OMN"),
        ("Somalia", 520, "SOM"),
        ("Korea South", 732, "KOR"),
        ("Turkey", 640, "TUR"),
        ("Dominican Rep", 42, "DOM"),
        ("Korea North", 731, "PRK"),
        ("Cen African Rep", 482, "CAF"),
        ("Congo/Zaire", 490, "COD"),
        ("Congo-Brz", 484, "COG"),
        ("Ivory Coast", 437, "CIV"),
        ("Brunei", 835, "BRN"),
        ("Swaziland", 572, "SWZ"),
        ("Cape Verde", 402, "CPV"),
        ("Bosnia", 346, "BIH"),
        ("Macedonia", 343, "MKD"),
        ("Czech Rep", 316, "CZE"),
        ("East Timor", 860, "TLS"),
        ("Australia", 900, "AUS"),
    ],
)
def test_reign_country_names_and_cow_codes_map_to_project_iso3(
    source_name: str,
    ccode: int,
    project_iso3: str,
) -> None:
    assert iso3_from_source_country(source_name, ccode=ccode, year=2020) == project_iso3
    assert iso3_from_cow_code(ccode) == project_iso3


@pytest.mark.parametrize(
    ("source_name", "project_iso3"),
    [
        ("German Democratic Republic", "DDR"),
        ("German Federal Republic", "DEU"),
        ("Germany, E.", "DDR"),
        ("Germany, W.", "DEU"),
        ("Czechoslovakia", "CSK"),
        ("Moldova, Republic of", "MDA"),
        ("Serbia and Montenegro", "SCG"),
        ("Yugoslavia", "YUG"),
        ("The Gambia", "GMB"),
        ("Tanzania, United Republic of", "TZA"),
        ("Kosovo", "XKX"),
        ("Congo (Kinshasa)", "COD"),
        ("Congo (Brazzaville)", "COG"),
        ("St. Vincent and the Grenadines", "VCT"),
        ("Yemen Arab Republic", "YEM"),
        ("Yemen People's Republic", "YEM"),
    ],
)
def test_non_cow_source_names_map_to_project_lifecycle_identities(
    source_name: str,
    project_iso3: str,
) -> None:
    assert iso3_from_source_country(source_name, year=2020) == project_iso3


def test_soviet_union_source_name_is_lifecycle_aware() -> None:
    assert iso3_from_source_country("Soviet Union", ccode=365, year=1991) == "SUN"
    assert iso3_from_source_country("Soviet Union", ccode=365, year=1992) == "RUS"
    assert iso3_from_source_country("USSR", year=1990) == "SUN"
    assert iso3_from_source_country("USSR", year=1992) == "RUS"
    assert iso3_from_source_country("Yemen, North", year=1989) == "YEM"


@pytest.mark.parametrize(
    ("ucdp_country_id", "project_iso3"),
    [
        (2, "USA"),
        (70, "MEX"),
        (100, "COL"),
        (530, "ETH"),
        (540, "AGO"),
        (645, "IRQ"),
        (630, "IRN"),
        (700, "AFG"),
        (770, "PAK"),
        (811, "KHM"),
    ],
)
def test_ucdp_country_ids_map_to_project_iso3(
    ucdp_country_id: int,
    project_iso3: str,
) -> None:
    assert iso3_from_ucdp_country_id(ucdp_country_id) == project_iso3


def test_ucdp_country_ids_do_not_fall_back_to_cow_when_unmapped() -> None:
    assert iso3_from_cow_code(987) == "FSM"
    assert iso3_from_ucdp_country_id(987) is None
    assert iso3_from_ucdp_country_id(365) is None
    assert iso3_from_ucdp_country_id(345) is None
    assert iso3_from_ucdp_country_id("not-a-code") is None


def test_ucdp_country_ids_dispatch_lifecycle_ambiguous_ids_by_year() -> None:
    assert iso3_from_ucdp_country_id(345, year=1991) == "YUG"
    assert iso3_from_ucdp_country_id(345, year=2001) == "YUG"
    assert iso3_from_ucdp_country_id(345, year=2006) is None
    assert iso3_from_ucdp_country_id(365, year=1991) == "SUN"
    assert iso3_from_ucdp_country_id(365, year=1992) == "RUS"
