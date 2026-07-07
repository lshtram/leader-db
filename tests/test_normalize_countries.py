"""Country-name and ISO3 normalization tests (Stage 3 building blocks)."""

from __future__ import annotations

import pytest

from leaders_db.normalize import (
    COUNTRY_NAME_NORMALIZATION,
    normalize_country_name,
    normalize_iso3,
)
from leaders_db.normalize.countries import alias_to_iso3


@pytest.mark.parametrize(
    "raw, normalized",
    [
        ("United States", "united states"),
        ("  Côte d'Ivoire ", "cote d'ivoire"),
        ("Türkiye", "turkiye"),
        ("Vatican", "vatican"),
        ("South Korea", "south korea"),
    ],
)
def test_normalize_country_name(raw: str, normalized: str) -> None:
    assert normalize_country_name(raw) == normalized


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("usa", "USA"),
        ("gbr", "GBR"),
        (" deU ", "DEU"),
    ],
)
def test_normalize_iso3_accepts_3_letter_codes(raw: str, expected: str) -> None:
    assert normalize_iso3(raw) == expected


@pytest.mark.parametrize("bad", ["", "USA1", "US", "U2A", None])
def test_normalize_iso3_rejects_invalid(bad) -> None:
    with pytest.raises(ValueError):
        normalize_iso3(bad)


def test_alias_seed_contains_common_variants() -> None:
    # The seed must cover the historical / variant names that show up in
    # source datasets before the alias file is built.
    expected_keys = {
        "united states",
        "united kingdom",
        "south korea",
        "north korea",
        "russia",
        "iran",
        "syria",
        "laos",
        "bolivia",
        "venezuela",
        "tanzania",
        "czechia",
        "ivory coast",
        "myanmar",
        "eswatini",
        "vatican",
        "palestine",
        "turkey",
        "the gambia",
    }
    assert expected_keys.issubset(set(COUNTRY_NAME_NORMALIZATION.keys()))


def test_alias_to_iso3_returns_iso3_for_known_alias() -> None:
    assert alias_to_iso3(normalize_country_name("United States")) == "USA"
    assert alias_to_iso3(normalize_country_name("UK")) == "GBR"
    assert alias_to_iso3(normalize_country_name("Burma")) == "MMR"


@pytest.mark.parametrize(
    ("source_name", "iso3"),
    [
        ("Brunei", "BRN"),
        ("Cape Verde", "CPV"),
        ("Congo, DR", "COD"),
        ("Congo, Republic", "COG"),
        ("Congo, Rep.", "COG"),
        ("Gambia, The", "GMB"),
        ("Korea, North", "PRK"),
        ("Korea, South", "KOR"),
        ("Kyrgyz Republic", "KGZ"),
        ("Viet Nam", "VNM"),
        ("Macedonia, FYR", "MKD"),
        ("Bosnia-Herzegovina", "BIH"),
        ("Czechoslovakia", "CSK"),
        ("Bosnia Herzegovenia", "BIH"),
        ("German Democratic Republic", "DDR"),
        ("East Germany", "DDR"),
        ("Germany, E.", "DDR"),
        ("Germany, W.", "DEU"),
        ("Kosovo", "XKX"),
        ("Serbia and Montenegro", "SCG"),
        ("Yugoslavia", "YUG"),
        ("Côte d’Ivoire", "CIV"),
        ("DR Congo (Zaire)", "COD"),
        ("Congo, Democratic Republic of", "COD"),
        ("Congo (Kinshasa)", "COD"),
        ("Congo, Republic of", "COG"),
        ("Congo (Brazzaville)", "COG"),
        ("The Gambia", "GMB"),
        ("St. Vincent and the Grenadines", "VCT"),
        ("Türkiye", "TUR"),
        ("Republic of Türkiye", "TUR"),
        ("Zimbabwe (Rhodesia)", "ZWE"),
        ("Kingdom of eSwatini (Swaziland)", "SWZ"),
        ("Madagascar (Malagasy)", "MDG"),
        ("Yemen (North Yemen)", "YEM"),
        ("Myanmar (Burma)", "MMR"),
        ("Burma (Myanmar)", "MMR"),
        ("Cambodia (Kampuchea)", "KHM"),
        ("East Timor (Timor-Leste)", "TLS"),
        ("Slovak Republic", "SVK"),
        ("Slovak Republic/ Slovakia", "SVK"),
        ("Korea, Democratic People's Republic of (North Korea)", "PRK"),
        ("Korea, Republic of (South Korea)", "KOR"),
    ],
)
def test_alias_to_iso3_resolves_sipri_display_names(
    source_name: str,
    iso3: str,
) -> None:
    assert alias_to_iso3(normalize_country_name(source_name)) == iso3


def test_alias_to_iso3_returns_none_for_unknown_name() -> None:
    assert alias_to_iso3("atlantis") is None
