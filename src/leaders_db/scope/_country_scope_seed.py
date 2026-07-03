"""Deterministic country-scope exclusions for ruler scoring.

This seed is intentionally conservative. It only excludes clear ISO 3166-1
territory, dependency, uninhabited/special, or observer/non-state entries from
the D3-D5 ruler-scoring denominator. It is not a complete sovereignty ontology.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CountryScopeRecord:
    """Year-level project-scope metadata for a country code."""

    code: str
    included_in_project: bool
    reason: str


NON_SOVEREIGN_OR_SPECIAL_EXCLUSION_REASON = (
    "excluded from D3-D5 ruler-scoring scope by conservative ISO scope policy: "
    "clear territory/dependency/special or non-sovereign entry; not treated as "
    "a sovereign country-year target for ruler scoring"
)


COUNTRY_SCOPE_SEED: tuple[CountryScopeRecord, ...] = tuple(
    CountryScopeRecord(code=code, included_in_project=False, reason=reason)
    for code, reason in {
        "ABW": (
            "Aruba is a constituent country within the Kingdom of the Netherlands, "
            "not a separate sovereign target."
        ),
        "AIA": "Anguilla is a British Overseas Territory.",
        "ALA": "Åland Islands is an autonomous region of Finland.",
        "ASM": "American Samoa is an unincorporated territory of the United States.",
        "ATA": "Antarctica is a special treaty area, not a sovereign country target.",
        "ATF": "French Southern Territories is a French overseas territory.",
        "BES": "Bonaire, Sint Eustatius and Saba are special municipalities of the Netherlands.",
        "BLM": "Saint Barthélemy is an overseas collectivity of France.",
        "BMU": "Bermuda is a British Overseas Territory.",
        "BVT": "Bouvet Island is an uninhabited Norwegian dependency.",
        "CCK": "Cocos (Keeling) Islands is an external territory of Australia.",
        "COK": (
            "Cook Islands has a special free-association status and is excluded "
            "pending explicit opt-in policy."
        ),
        "CUW": (
            "Curaçao is a constituent country within the Kingdom of the Netherlands, "
            "not a separate sovereign target."
        ),
        "CXR": "Christmas Island is an external territory of Australia.",
        "CYM": "Cayman Islands is a British Overseas Territory.",
        "ESH": (
            "Western Sahara is a disputed/non-self-governing territory for this "
            "prototype scope."
        ),
        "FLK": "Falkland Islands is a British Overseas Territory.",
        "FRO": "Faroe Islands is an autonomous territory within the Kingdom of Denmark.",
        "GGY": "Guernsey is a Crown Dependency.",
        "GIB": "Gibraltar is a British Overseas Territory.",
        "GLP": "Guadeloupe is an overseas department/region of France.",
        "GRL": "Greenland is an autonomous territory within the Kingdom of Denmark.",
        "GUF": "French Guiana is an overseas department/region of France.",
        "GUM": "Guam is an unincorporated territory of the United States.",
        "HKG": "Hong Kong is a special administrative region of China.",
        "HMD": (
            "Heard Island and McDonald Islands is an uninhabited external territory "
            "of Australia."
        ),
        "IMN": "Isle of Man is a Crown Dependency.",
        "IOT": "British Indian Ocean Territory is a British Overseas Territory.",
        "JEY": "Jersey is a Crown Dependency.",
        "MAC": "Macao is a special administrative region of China.",
        "MAF": "Saint Martin (French part) is an overseas collectivity of France.",
        "MNP": (
            "Northern Mariana Islands is a commonwealth in political union with the "
            "United States."
        ),
        "MSR": "Montserrat is a British Overseas Territory.",
        "MTQ": "Martinique is an overseas department/region of France.",
        "MYT": "Mayotte is an overseas department/region of France.",
        "NCL": "New Caledonia is a French sui generis collectivity.",
        "NFK": "Norfolk Island is an external territory of Australia.",
        "NIU": (
            "Niue has a special free-association status and is excluded pending "
            "explicit opt-in policy."
        ),
        "PCN": "Pitcairn is a British Overseas Territory.",
        "PRI": "Puerto Rico is an unincorporated territory of the United States.",
        "PYF": "French Polynesia is an overseas collectivity of France.",
        "REU": "Réunion is an overseas department/region of France.",
        "SGS": "South Georgia and the South Sandwich Islands is a British Overseas Territory.",
        "SHN": "Saint Helena, Ascension and Tristan da Cunha is a British Overseas Territory.",
        "SJM": "Svalbard and Jan Mayen is a special Norwegian territory entry.",
        "SPM": "Saint Pierre and Miquelon is an overseas collectivity of France.",
        "SXM": (
            "Sint Maarten is a constituent country within the Kingdom of the "
            "Netherlands, not a separate sovereign target."
        ),
        "TCA": "Turks and Caicos Islands is a British Overseas Territory.",
        "TKL": "Tokelau is a dependent territory of New Zealand.",
        "UMI": (
            "United States Minor Outlying Islands is a special "
            "uninhabited/minor-outlying territory entry."
        ),
        "VAT": (
            "Holy See/Vatican City is an observer/special micro-entity excluded "
            "pending explicit scorer policy."
        ),
        "VGB": "British Virgin Islands is a British Overseas Territory.",
        "VIR": "U.S. Virgin Islands is an unincorporated territory of the United States.",
        "WLF": "Wallis and Futuna is an overseas collectivity of France.",
    }.items()
)


__all__ = ["COUNTRY_SCOPE_SEED", "CountryScopeRecord"]
