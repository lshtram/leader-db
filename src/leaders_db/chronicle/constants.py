"""Constants and attribution strings for the Country-Year Chronicle slice.

This module owns the slice-specific constants that the workplan
labels as "stable domain schema values" — column names, source
attribution text, the V-Dem regime mapping table, and the
country-period mapping for the conservative system-type classifier.

Per :file:`docs/coding-guidelines.md` § "Hard-Coded Values", domain
schema values are acceptable constants when documented and owned by
the relevant module. Research-changing values (target years, country
lists, scoring weights) are NOT defined here; they come from the
caller's CLI/config.

Attribution text is intentionally duplicated from
:file:`docs/source-attributions.md` because that doc is the
normative source — the test
``test_chronicle_attribution_matches_attributions_doc`` enforces that
the strings here are byte-for-byte substrings of the doc.
"""

from __future__ import annotations

from typing import Final

# ---------------------------------------------------------------------------
# Output layout
# ---------------------------------------------------------------------------

#: Output directory name under ``data/outputs/`` for this slice.
CHRONICLE_OUTPUT_DIR_NAME: Final[str] = "country-year-chronicle"

#: Default output CSV file name; the CLI writes to
#: ``<output_dir>/<output_basename>`` and the directory is auto-created.
DEFAULT_OUTPUT_BASENAME: Final[str] = "country_year_chronicle.csv"

#: Default start year for the pilot (per Increment 0 §4).
DEFAULT_START_YEAR: Final[int] = 1900

#: Default end year for the pilot (per Increment 0 §4).
DEFAULT_END_YEAR: Final[int] = 2026

#: Default comma-separated ISO3 list for the pilot (per Increment 0 §4).
DEFAULT_COUNTRIES: Final[tuple[str, ...]] = (
    "USA",
    "GBR",
    "FRA",
    "IND",
    "RUS",
    "SUN",
    "CHN",
)

#: Proxy year used when the requested year is one beyond V-Dem's coverage.
#: V-Dem v16 covers 1789-2025; ``DEFAULT_PROXY_YEAR`` is the year we copy
#: from when the user asks for 2026. The flag ``proxy_year_used`` is added
#: to any row whose regime value came from a proxy year.
DEFAULT_PROXY_YEAR: Final[int] = 2025

#: V-Dem's maximum covered year (per V-Dem v16 metadata).
VDEM_MAX_COVERED_YEAR: Final[int] = 2025

# ---------------------------------------------------------------------------
# V-Dem regime mapping
# ---------------------------------------------------------------------------

#: Native V-Dem ``v2x_regime`` integer to CYC political-regime bucket.
#: Per docs/country-year-chronicle-increment-0.md §5.1.
VDEM_REGIME_TO_BUCKET: Final[dict[int, str]] = {
    0: "Authoritarian",
    1: "Hybrid regime",
    2: "Flawed democracy",
    3: "Full democracy",
}

#: Conservative fallback thresholds used when ``v2x_regime`` is missing
#: but ``v2x_polyarchy`` (V-Dem's Electoral Democracy Index, 0-1) is present.
#: The thresholds are intentionally coarse; if they fire we add the
#: ``regime_source_gap`` flag so a reader can see the bucket was derived.
VDEM_POLYARCHY_FALLBACK_THRESHOLDS: Final[dict[str, tuple[float, float]]] = {
    "Full democracy": (0.70, 1.01),
    "Flawed democracy": (0.50, 0.70),
    "Hybrid regime": (0.30, 0.50),
    "Authoritarian": (-0.01, 0.30),
}

# ---------------------------------------------------------------------------
# Country-period mapping for the system-type classifier
# ---------------------------------------------------------------------------

#: A small curated mapping of ``(iso3, start_year, end_year) -> primary
#: system_type``. Used by the conservative system-type classifier; if no
#: mapping applies, the classifier falls back to a regime-bucket default.
#: Per Increment 0 §5.2 the pilot uses these explicit mappings:
#:
#: - USSR/SUN during the Soviet period (1922-1991) -> Communist one-party state.
#: - PRC/CHN after 1949 -> Communist one-party state.
#: - India before 1947 -> Colonial administration.
#:
#: Note: Russia / Russian Federation is intentionally NOT in this
#: curated list. There is no documented conservative rule that
#: pins RUS to a specific system-type label for the full 1992-2026
#: window. Without a curated mapping, RUS rows fall through to the
#: regime-bucket fallback (Hybrid/Authoritarian -> Mixed / unclear;
#: Full/Flawed democracy -> Liberal capitalist democracy), which is
#: the conservative behavior Increment 1 documents. Adding a curated
#: RUS mapping requires a documented rule, not an assumed one.
SYSTEM_TYPE_COUNTRY_PERIODS: Final[tuple[tuple[str, int, int, str], ...]] = (
    # Soviet period (1922-1991, Russian SFSR before that). Russia proper
    # transitioned through multiple systems; we mark 1922-1991 SUN history
    # as Communist one-party state.
    ("SUN", 1922, 1991, "Communist one-party state"),
    # PRC from 1949 onward.
    ("CHN", 1949, 2026, "Communist one-party state"),
    # India pre-independence (under direct British Crown rule). 1858-1947.
    ("IND", 1858, 1946, "Colonial administration"),
    # No curated mapping for RUS post-1991: see the note above.
)

#: Regime bucket -> default system_type when no curated mapping applies.
#: Per Increment 0 §5.2: "For democratic market economies, use 'Liberal
#: capitalist democracy' by default." We split:
#:
#: - Full democracy    -> "Liberal capitalist democracy"
#: - Flawed democracy  -> "Liberal capitalist democracy"
#: - Hybrid regime     -> "Mixed / unclear"
#: - Authoritarian     -> "Mixed / unclear"
#: - Unknown           -> "Unknown"
REGIME_BUCKET_DEFAULT_SYSTEM_TYPE: Final[dict[str, str]] = {
    "Full democracy": "Liberal capitalist democracy",
    "Flawed democracy": "Liberal capitalist democracy",
    "Hybrid regime": "Mixed / unclear",
    "Authoritarian": "Mixed / unclear",
    "Unknown": "Unknown",
}

#: Conservative confidence value (0-100) used for the curated
#: country-period classifier matches.
CURATED_SYSTEM_TYPE_CONFIDENCE: Final[int] = 70

#: Conservative confidence value for regime-bucket fallback matches.
FALLBACK_SYSTEM_TYPE_CONFIDENCE: Final[int] = 40

# ---------------------------------------------------------------------------
# Output column order (Increment 0 §4 final CSV contract)
# ---------------------------------------------------------------------------

#: The fixed, ordered list of CSV column names. The CSV writer is REQUIRED
#: to use this exact order. Adding a column is a contract change.
CHRONICLE_CSV_COLUMNS: Final[tuple[str, ...]] = (
    "year",
    "iso3",
    "country_name",
    "country_status",
    "region",
    "subregion",
    "ruler_name",
    "ruler_title",
    "ruler_type",
    "ruler_source",
    "ruler_source_year_used",
    "ruler_confidence",
    "shared_rule_flag",
    "disputed_rule_flag",
    "political_regime_bucket",
    "political_regime_raw_score",
    "political_regime_source",
    "political_regime_source_year_used",
    "political_regime_confidence",
    "system_type_primary",
    "system_type_secondary",
    "system_type_source",
    "system_type_confidence",
    "system_type_notes",
    "population",
    "population_source",
    "population_source_year_used",
    "gdp",
    "gdp_unit",
    "gdp_source",
    "gdp_source_year_used",
    "gdp_per_capita",
    "gdp_per_capita_unit",
    "gdp_per_capita_method",
    "military_spend",
    "military_spend_unit",
    "military_spend_source",
    "military_spend_source_year_used",
    "country_area_km2",
    "controlled_area_km2",
    "area_source",
    "area_source_year_used",
    "controlled_area_note",
    "data_quality_flags",
    "row_confidence",
    "provenance_summary",
)

# ---------------------------------------------------------------------------
# Canonical data-quality flag values (Increment 0 §6).
# ---------------------------------------------------------------------------

FLAG_MISSING_RULER: Final[str] = "missing_ruler"
FLAG_MULTIPLE_RULERS: Final[str] = "multiple_rulers"
FLAG_SHARED_RULE: Final[str] = "shared_rule"
FLAG_DISPUTED_RULE: Final[str] = "disputed_rule"
FLAG_PROXY_YEAR_USED: Final[str] = "proxy_year_used"
FLAG_MISSING_POPULATION: Final[str] = "missing_population"
FLAG_MISSING_GDP: Final[str] = "missing_gdp"
FLAG_MISSING_MILITARY_SPEND: Final[str] = "missing_military_spend"
FLAG_MISSING_AREA: Final[str] = "missing_area"
FLAG_REGIME_SOURCE_GAP: Final[str] = "regime_source_gap"
FLAG_SYSTEM_TYPE_LOW_CONFIDENCE: Final[str] = "system_type_low_confidence"
FLAG_SUCCESSOR_STATE_ISSUE: Final[str] = "successor_state_issue"
FLAG_COLONIAL_STATUS_ISSUE: Final[str] = "colonial_status_issue"
FLAG_CONTROLLED_AREA_NOT_MODELED: Final[str] = "controlled_area_not_modeled"
FLAG_SOURCE_CONFLICT: Final[str] = "source_conflict"

#: Additional slice-owned flags that are not in the canonical Increment 0
#: list. These are intentionally narrow and documented.
FLAG_PRE_EXISTENCE_GAP: Final[str] = "pre_existence_gap"
FLAG_POST_EXISTENCE_GAP: Final[str] = "post_existence_gap"

# ---------------------------------------------------------------------------
# Source attribution strings (per docs/source-attributions.md).
# These are byte-identical substrings of the doc; the test
# test_chronicle_attribution_matches_attributions_doc enforces it.
# ---------------------------------------------------------------------------

VDEM_ATTRIBUTION: Final[str] = (
    "V-Dem v16 (Coppedge et al. 2026)."
)

WDI_ATTRIBUTION: Final[str] = (
    "World Bank WDI (World Bank 2024)."
)

SIPRI_MILEX_ATTRIBUTION: Final[str] = (
    "SIPRI milex (Stockholm International Peace Research Institute 2026)."
)

#: Canonical source key tags used in the per-field source columns.
SOURCE_TAG_VDEM: Final[str] = "vdem"
SOURCE_TAG_WDI: Final[str] = "wdi"
SOURCE_TAG_SIPRI: Final[str] = "sipri_milex"
SOURCE_TAG_CURATED: Final[str] = "cyc_curated"
SOURCE_TAG_NONE: Final[str] = ""

#: When a field cannot be populated from any vetted source we emit the
#: sentinel below in the ``*_source`` column. The ``data_quality_flags``
#: column carries the specific reason.
SOURCE_NA: Final[str] = ""

# ---------------------------------------------------------------------------
# Source precedence (per Increment 0 §5).
# ---------------------------------------------------------------------------

#: V-Dem regime values are scored at this confidence when they come
#: directly from the raw V-Dem CSV for the exact requested year.
VDEM_DIRECT_CONFIDENCE: Final[int] = 80

#: V-Dem regime values copied from ``DEFAULT_PROXY_YEAR`` because the
#: requested year is beyond V-Dem coverage are scored at this lower
#: confidence.
VDEM_PROXY_CONFIDENCE: Final[int] = 60

#: WDI values copied from the processed parquet for the exact year are
#: scored at this confidence.
WDI_DIRECT_CONFIDENCE: Final[int] = 80

#: SIPRI milex values from the processed parquet for the exact year are
#: scored at this confidence.
SIPRI_DIRECT_CONFIDENCE: Final[int] = 80

#: Conservative confidence for placeholder ruler / area fields. They are
#: always empty in Increment 1 so the confidence floor does not matter
#: for the row builder, but we keep the constant so the CSV writes a
#: non-empty ``ruler_confidence`` string for a downstream consumer that
#: wants to filter on it.
PLACEHOLDER_RULER_CONFIDENCE: Final[int] = 0

# ---------------------------------------------------------------------------
# Country display / status
# ---------------------------------------------------------------------------

#: Display name + status + region metadata for the pilot ISO3 list.
#: This is intentionally minimal; we do not pretend to be a country
#: reference table. The ``country_status`` values are limited to the
#: four documented values from Increment 0 §3.1.
COUNTRY_METADATA: Final[dict[str, dict[str, str]]] = {
    "USA": {
        "country_name": "United States",
        "country_status": "independent",
        "region": "Americas",
        "subregion": "Northern America",
        # The United States existed as a recognized polity for the entire
        # 1776-onward span. The pilot starts at 1900 so we do not need a
        # ``start_year``. We add 1776 here for completeness; the row builder
        # uses ``start_year`` only when set.
        "start_year": "1776",
        "end_year": "",
    },
    "GBR": {
        "country_name": "United Kingdom",
        "country_status": "independent",
        "region": "Europe",
        "subregion": "Northern Europe",
        # United Kingdom of Great Britain and Ireland from 1801; United
        # Kingdom of Great Britain and Northern Ireland from 1922. We
        # represent it as one row stream for the pilot.
        "start_year": "1801",
        "end_year": "",
    },
    "FRA": {
        "country_name": "France",
        "country_status": "independent",
        "region": "Europe",
        "subregion": "Western Europe",
        # French Third Republic from 1870, including the Vichy period.
        # Multiple regime transitions in the 20th century; the regime
        # bucket captures them.
        "start_year": "1870",
        "end_year": "",
    },
    "IND": {
        "country_name": "India",
        "country_status": "independent",
        "region": "Asia",
        "subregion": "Southern Asia",
        # Pre-1947 the country_status flips to ``colonial/dependent``.
        # We do not duplicate the row in the pilot output; the row
        # builder emits one row per (iso3, year) regardless and tags
        # pre-1947 with the colonial flag.
        "start_year": "1947",
        "end_year": "",
        # We document that pre-1947 is British India via a curated
        # country_status override; the row builder handles the rest.
        "colonial_status_until": "1946",
    },
    "RUS": {
        "country_name": "Russian Federation",
        "country_status": "independent",
        "region": "Europe",
        "subregion": "Eastern Europe",
        # Russian Federation from 1991-12-25 onward. Pre-1991 RUS in V-Dem
        # is the merged RUS+SUN record.
        "start_year": "1991",
        "end_year": "",
    },
    "SUN": {
        "country_name": "Soviet Union",
        "country_status": "successor_state",
        "region": "Europe",
        "subregion": "Eastern Europe",
        # Soviet Union 1922-1991. V-Dem v16 does not have a separate
        # ``SUN`` country_text_id; the merged RUS record covers the
        # same years. We emit SUN rows with the conservative
        # system-type classifier and a successor_state flag.
        "start_year": "1922",
        "end_year": "1991",
    },
    "CHN": {
        "country_name": "China",
        "country_status": "independent",
        "region": "Asia",
        "subregion": "Eastern Asia",
        # People's Republic of China from 1949-10-01. ROC history prior
        # to that is not represented as a separate row stream in this
        # slice; the curated classifier tags pre-1949 as unknown.
        "start_year": "1949",
        "end_year": "",
    },
}


__all__ = [
    "CHRONICLE_CSV_COLUMNS",
    "CHRONICLE_OUTPUT_DIR_NAME",
    "COUNTRY_METADATA",
    "CURATED_SYSTEM_TYPE_CONFIDENCE",
    "DEFAULT_COUNTRIES",
    "DEFAULT_END_YEAR",
    "DEFAULT_OUTPUT_BASENAME",
    "DEFAULT_PROXY_YEAR",
    "DEFAULT_START_YEAR",
    "FALLBACK_SYSTEM_TYPE_CONFIDENCE",
    "FLAG_COLONIAL_STATUS_ISSUE",
    "FLAG_CONTROLLED_AREA_NOT_MODELED",
    "FLAG_DISPUTED_RULE",
    "FLAG_MISSING_AREA",
    "FLAG_MISSING_GDP",
    "FLAG_MISSING_MILITARY_SPEND",
    "FLAG_MISSING_POPULATION",
    "FLAG_MISSING_RULER",
    "FLAG_MULTIPLE_RULERS",
    "FLAG_POST_EXISTENCE_GAP",
    "FLAG_PRE_EXISTENCE_GAP",
    "FLAG_PROXY_YEAR_USED",
    "FLAG_REGIME_SOURCE_GAP",
    "FLAG_SHARED_RULE",
    "FLAG_SOURCE_CONFLICT",
    "FLAG_SUCCESSOR_STATE_ISSUE",
    "FLAG_SYSTEM_TYPE_LOW_CONFIDENCE",
    "PLACEHOLDER_RULER_CONFIDENCE",
    "REGIME_BUCKET_DEFAULT_SYSTEM_TYPE",
    "SIPRI_DIRECT_CONFIDENCE",
    "SIPRI_MILEX_ATTRIBUTION",
    "SOURCE_NA",
    "SOURCE_TAG_CURATED",
    "SOURCE_TAG_NONE",
    "SOURCE_TAG_SIPRI",
    "SOURCE_TAG_VDEM",
    "SOURCE_TAG_WDI",
    "SYSTEM_TYPE_COUNTRY_PERIODS",
    "VDEM_ATTRIBUTION",
    "VDEM_DIRECT_CONFIDENCE",
    "VDEM_MAX_COVERED_YEAR",
    "VDEM_POLYARCHY_FALLBACK_THRESHOLDS",
    "VDEM_PROXY_CONFIDENCE",
    "VDEM_REGIME_TO_BUCKET",
    "WDI_ATTRIBUTION",
    "WDI_DIRECT_CONFIDENCE",
]
