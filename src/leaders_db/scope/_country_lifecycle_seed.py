"""Deterministic year-level country-lifecycle seed for scope building.

This seed is a compact packaged data table, not a runtime web fetch. It covers
the active 1950-2025 D1/D2/D3-D5 scope well enough to prevent current ISO3
countries from entering ruler-coverage denominators before modern independence,
restored sovereignty, or current-state succession. It also carries selected
ceased entities already useful to local predecessor handling.

Source basis: year-level anchors are taken from standard public chronology
references: the CIA World Factbook ``Independence`` field
(``https://factbook.wiki/fields/305.html``), the UN member-states chronology
(``https://www.un.org/en/about-us/member-states``), ISO 3166 transition history
for former codes (for example ISO 3166-3 Yugoslavia newsletter I-3 and the
Statoids ISO-change digest at ``https://statoids.com/w3166his.html``), and
official country/government historical summaries where those references are
clearer for state-successor cases. These are year-level scope anchors only; they
do not model month/day recognition, disputed recognition windows, occupation,
government-in-exile continuity, or predecessor polities in full.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CountryLifecycleRecord:
    """Year-level country lifecycle metadata for the country-year grid."""

    code: str
    name: str
    valid_from_year: int
    valid_to_year: int | None
    entity_type: str
    predecessor_codes: tuple[str, ...]
    successor_codes: tuple[str, ...]
    notes: str


def _current(
    code: str,
    name: str,
    year: int,
    *,
    predecessors: tuple[str, ...] = (),
    note: str | None = None,
) -> CountryLifecycleRecord:
    return CountryLifecycleRecord(
        code=code,
        name=name,
        valid_from_year=year,
        valid_to_year=None,
        entity_type="current_state_lifecycle",
        predecessor_codes=predecessors,
        successor_codes=(),
        notes=note
        or (
            f"Year-level lifecycle seed: modern {name} enters the active scope "
            f"from {year}; month/day recognition and predecessor-polity details "
            "are not modeled."
        ),
    )


def _historical(
    code: str,
    name: str,
    start: int,
    end: int,
    *,
    successors: tuple[str, ...] = (),
    note: str | None = None,
) -> CountryLifecycleRecord:
    return CountryLifecycleRecord(
        code=code,
        name=name,
        valid_from_year=start,
        valid_to_year=end,
        entity_type="historical_state",
        predecessor_codes=(),
        successor_codes=successors,
        notes=note
        or (
            f"Year-level lifecycle seed: {name} modeled for {start}-{end}; "
            "successor, recognition, and subperiod details are not fully modeled."
        ),
    )


POST_1950_CURRENT_STATE_LIFECYCLES: tuple[CountryLifecycleRecord, ...] = (
    # Africa and Middle East decolonization / modern state entries.
    _current("AGO", "Angola", 1975),
    _current("ARE", "United Arab Emirates", 1971),
    _current("BFA", "Burkina Faso", 1960),
    _current("BDI", "Burundi", 1962),
    _current("BEN", "Benin", 1960),
    _current("BHR", "Bahrain", 1971),
    _current("BWA", "Botswana", 1966),
    _current("CAF", "Central African Republic", 1960),
    _current("CIV", "Côte d'Ivoire", 1960),
    _current("CMR", "Cameroon", 1960),
    _current("COD", "Congo, The Democratic Republic of the", 1960),
    _current("COG", "Congo", 1960),
    _current("COM", "Comoros", 1975),
    _current("CPV", "Cabo Verde", 1975),
    _current("DJI", "Djibouti", 1977),
    _current("DZA", "Algeria", 1962),
    _current("ERI", "Eritrea", 1993),
    _current("GAB", "Gabon", 1960),
    _current("GHA", "Ghana", 1957),
    _current("GIN", "Guinea", 1958),
    _current("GMB", "Gambia", 1965),
    _current("GNB", "Guinea-Bissau", 1974),
    _current("GNQ", "Equatorial Guinea", 1968),
    _current("KEN", "Kenya", 1963),
    _current("KWT", "Kuwait", 1961),
    _current("LBN", "Lebanon", 1943),
    _current("LBY", "Libya", 1951),
    _current("LSO", "Lesotho", 1966),
    _current("MAR", "Morocco", 1956),
    _current("MDG", "Madagascar", 1960),
    _current("MLI", "Mali", 1960),
    _current("MOZ", "Mozambique", 1975),
    _current("MRT", "Mauritania", 1960),
    _current("MUS", "Mauritius", 1968),
    _current("MWI", "Malawi", 1964),
    _current("NAM", "Namibia", 1990),
    _current("NER", "Niger", 1960),
    _current("NGA", "Nigeria", 1960),
    _current(
        "PSE",
        "Palestine, State of",
        2012,
        note=(
            "Year-level lifecycle seed: PSE is retained as a polity-sensitive current "
            "ISO entry but only enters the active D3-D5 ruler-scoring denominator from "
            "the 2012 UN non-member observer State anchor; earlier rows stay audit-only."
        ),
    ),
    _current("QAT", "Qatar", 1971),
    _current("RWA", "Rwanda", 1962),
    _current("SDN", "Sudan", 1956),
    _current("SEN", "Senegal", 1960),
    _current("SLE", "Sierra Leone", 1961),
    _current("SOM", "Somalia", 1960),
    _current("SSD", "South Sudan", 2011, predecessors=("SDN",)),
    _current("STP", "Sao Tome and Principe", 1975),
    _current("SWZ", "Eswatini", 1968),
    _current("SYC", "Seychelles", 1976),
    _current("TCD", "Chad", 1960),
    _current("TGO", "Togo", 1960),
    _current("TUN", "Tunisia", 1956),
    _current("TZA", "Tanzania", 1961),
    _current("UGA", "Uganda", 1962),
    _current("ZMB", "Zambia", 1964),
    _current("ZWE", "Zimbabwe", 1980),
    # Asia-Pacific modern independence and successor entries.
    _current("BGD", "Bangladesh", 1971, predecessors=("PAK",)),
    _current("BRN", "Brunei Darussalam", 1984),
    _current("CYP", "Cyprus", 1960),
    _current("FJI", "Fiji", 1970),
    _current("FSM", "Micronesia, Federated States of", 1986),
    _current("KHM", "Cambodia", 1953),
    _current("KIR", "Kiribati", 1979),
    _current("LAO", "Lao People's Democratic Republic", 1953),
    _current("LKA", "Sri Lanka", 1948),
    _current("MDV", "Maldives", 1965),
    _current("MHL", "Marshall Islands", 1986),
    _current("MYS", "Malaysia", 1957),
    _current("NRU", "Nauru", 1968),
    _current("PLW", "Palau", 1994),
    _current("PNG", "Papua New Guinea", 1975),
    _current("SGP", "Singapore", 1965),
    _current("SLB", "Solomon Islands", 1978),
    _current("TLS", "Timor-Leste", 2002),
    _current("TON", "Tonga", 1970),
    _current("TUV", "Tuvalu", 1978),
    _current("VUT", "Vanuatu", 1980),
    _current("WSM", "Samoa", 1962),
    _current("YEM", "Yemen", 1990),
    # Europe, Eurasia, and Soviet/Czechoslovak/Yugoslav successor states.
    _current("ARM", "Armenia", 1991, predecessors=("SUN",)),
    _current("AZE", "Azerbaijan", 1991, predecessors=("SUN",)),
    _current("BIH", "Bosnia and Herzegovina", 1992, predecessors=("YUG",)),
    _current("BLR", "Belarus", 1991, predecessors=("SUN",)),
    _current("CZE", "Czechia", 1993, predecessors=("CSK",)),
    _current("EST", "Estonia", 1991, predecessors=("SUN",)),
    _current("GEO", "Georgia", 1991, predecessors=("SUN",)),
    _current("HRV", "Croatia", 1991, predecessors=("YUG",)),
    _current("KAZ", "Kazakhstan", 1991, predecessors=("SUN",)),
    _current("KGZ", "Kyrgyzstan", 1991, predecessors=("SUN",)),
    _current(
        "XKX",
        "Kosovo",
        2008,
        predecessors=("SCG", "SRB"),
        note=(
            "Year-level lifecycle seed: Kosovo is modeled as XKX from the 2008 "
            "declaration-of-independence anchor for source coverage; recognition "
            "status and month/day details are not modeled."
        ),
    ),
    _current("LTU", "Lithuania", 1991, predecessors=("SUN",)),
    _current("LVA", "Latvia", 1991, predecessors=("SUN",)),
    _current("MDA", "Moldova, Republic of", 1991, predecessors=("SUN",)),
    _current("MKD", "North Macedonia", 1991, predecessors=("YUG",)),
    _current("MLT", "Malta", 1964),
    _current("MNE", "Montenegro", 2006, predecessors=("YUG",)),
    _current("RUS", "Russian Federation", 1991, predecessors=("SUN",)),
    _current("SRB", "Serbia", 2006, predecessors=("YUG",)),
    _current("SVK", "Slovakia", 1993, predecessors=("CSK",)),
    _current("SVN", "Slovenia", 1991, predecessors=("YUG",)),
    _current("TJK", "Tajikistan", 1991, predecessors=("SUN",)),
    _current("TKM", "Turkmenistan", 1991, predecessors=("SUN",)),
    _current("UKR", "Ukraine", 1991, predecessors=("SUN",)),
    _current("UZB", "Uzbekistan", 1991, predecessors=("SUN",)),
    # Americas and Caribbean decolonization entries.
    _current("ATG", "Antigua and Barbuda", 1981),
    _current("BHS", "Bahamas", 1973),
    _current("BLZ", "Belize", 1981),
    _current("BRB", "Barbados", 1966),
    _current("DMA", "Dominica", 1978),
    _current("GRD", "Grenada", 1974),
    _current("GUY", "Guyana", 1966),
    _current("JAM", "Jamaica", 1962),
    _current("KNA", "Saint Kitts and Nevis", 1983),
    _current("LCA", "Saint Lucia", 1979),
    _current("SUR", "Suriname", 1975),
    _current("TTO", "Trinidad and Tobago", 1962),
    _current("VCT", "Saint Vincent and the Grenadines", 1979),
)


HISTORICAL_STATE_LIFECYCLES: tuple[CountryLifecycleRecord, ...] = (
    _historical(
        "CSK",
        "Czechoslovakia",
        1918,
        1992,
        successors=("CZE", "SVK"),
    ),
    _historical(
        "SUN",
        "Soviet Union",
        1922,
        1991,
        successors=(
            "ARM",
            "AZE",
            "BLR",
            "EST",
            "GEO",
            "KAZ",
            "KGZ",
            "LTU",
            "LVA",
            "MDA",
            "RUS",
            "TJK",
            "TKM",
            "UKR",
            "UZB",
        ),
    ),
    _historical(
        "DDR",
        "German Democratic Republic",
        1949,
        1990,
        successors=("DEU",),
        note=(
            "Year-level lifecycle seed: East Germany / German Democratic Republic "
            "modeled as DDR for 1949-1990; reunification subyear details are not modeled."
        ),
    ),
    _historical(
        "SCG",
        "Serbia and Montenegro",
        2003,
        2006,
        successors=("MNE", "SRB", "XKX"),
        note=(
            "Year-level lifecycle seed: Serbia and Montenegro modeled as SCG for "
            "2003-2006; successor and recognition subperiods are not split further."
        ),
    ),
    _historical(
        "YUG",
        "Yugoslavia",
        1918,
        2002,
        successors=("BIH", "HRV", "MKD", "MNE", "SCG", "SRB", "SVN"),
        note=(
            "Year-level lifecycle seed: Yugoslavia modeled as YUG for 1918-2002; "
            "successor-state, Federal Republic/State Union, and recognition subperiods "
            "are not split in this D1/D2 seed."
        ),
    ),
)


COUNTRY_LIFECYCLE_SEED: tuple[CountryLifecycleRecord, ...] = (
    *POST_1950_CURRENT_STATE_LIFECYCLES,
    *HISTORICAL_STATE_LIFECYCLES,
)


__all__ = ["COUNTRY_LIFECYCLE_SEED", "CountryLifecycleRecord"]
