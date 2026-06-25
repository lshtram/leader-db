"""Static catalog data: stable concept keys, indicator codes, descriptors, and mappings.

This module owns the immutable registry of concept metadata. It
exposes:

- Stable concept key constants (``CONCEPT_GDP_PER_CAPITA`` etc.).
- Source-slug constants (``WDI_SOURCE_KEY`` etc.) re-used by the
  caller-facing helpers.
- The :data:`KNOWN_CONCEPT_KEYS` ordered tuple used by
  :func:`leaders_db.sources.concepts.list_concepts`.
- The :func:`build_concept_descriptors` /
  :func:`build_concept_mappings` factories that produce the canonical
  descriptor / mapping lists. The lists are immutable tuples so
  downstream code can rely on iteration order across runs.

The catalog covers the three migrated sources (WDI, Maddison, PWT)
for the three stable concepts (gdp_per_capita, population,
gdp_total). Future slices may add more sources per concept; this
module is the single point of registration. Indicator code strings
mirror the canonical source catalogs:

- ``src/leaders_db/ingest/catalogs/wdi.csv``
- ``src/leaders_db/ingest/catalogs/maddison_project.csv``
- ``src/leaders_db/ingest/sources/pwt/catalog.csv``
"""

from __future__ import annotations

from ..contracts import SourceId
from ._dataclasses import ConceptDescriptor, ConceptMapping

# ---------------------------------------------------------------------------
# Stable concept keys
# ---------------------------------------------------------------------------

CONCEPT_GDP_PER_CAPITA: str = "gdp_per_capita"
CONCEPT_POPULATION: str = "population"
CONCEPT_GDP_TOTAL: str = "gdp_total"

# Canonical ordered list of stable concept keys. The order is the
# canonical iteration order for ``list_concepts()``; downstream code
# that needs a deterministic sequence relies on this order.
KNOWN_CONCEPT_KEYS: tuple[str, ...] = (
    CONCEPT_GDP_PER_CAPITA,
    CONCEPT_POPULATION,
    CONCEPT_GDP_TOTAL,
)


# ---------------------------------------------------------------------------
# Source-slug constants
# ---------------------------------------------------------------------------

WDI_SOURCE_KEY: str = "world_bank_wdi"
MADDISON_PROJECT_SOURCE_KEY: str = "maddison_project"
PWT_SOURCE_KEY: str = "pwt"
CLIENT_EXISTING_SOURCE_KEY: str = "client_existing"


# ---------------------------------------------------------------------------
# Indicator-code constants
# ---------------------------------------------------------------------------

# WDI catalog (src/leaders_db/ingest/catalogs/wdi.csv).
WDI_GDP_PER_CAPITA_INDICATOR_CODE: str = "wdi_gdp_per_capita"
WDI_GDP_PER_CAPITA_PPP_CONSTANT_2017_INDICATOR_CODE: str = (
    "wdi_gdp_per_capita_ppp_constant_2017"
)
WDI_POPULATION_INDICATOR_CODE: str = "wdi_population"
WDI_GDP_CURRENT_USD_INDICATOR_CODE: str = "wdi_gdp_current_usd"
WDI_GDP_CONSTANT_2015_USD_INDICATOR_CODE: str = "wdi_gdp_constant_2015_usd"

# Maddison catalog (src/leaders_db/ingest/catalogs/maddison_project.csv).
MADDISON_PROJECT_GDP_PER_CAPITA_INDICATOR_CODE: str = (
    "maddison_project_gdp_per_capita_2011_intl"
)
MADDISON_PROJECT_POPULATION_INDICATOR_CODE: str = (
    "maddison_project_population_thousands"
)
# The Maddison total real GDP indicator is already a derived
# value (gdppc * pop * 1000) computed by the Stage 2 reader;
# the concept catalog treats it as a direct mapping.
MADDISON_PROJECT_GDP_TOTAL_DERIVED_INDICATOR_CODE: str = (
    "maddison_project_gdp_total_2011_intl_derived"
)

# PWT catalog (src/leaders_db/ingest/sources/pwt/catalog.csv).
PWT_POPULATION_INDICATOR_CODE: str = "pwt_population"
PWT_REAL_GDP_OUTPUT_SIDE_INDICATOR_CODE: str = "pwt_real_gdp_output_side"
PWT_REAL_GDP_EXPENDITURE_SIDE_INDICATOR_CODE: str = (
    "pwt_real_gdp_expenditure_side"
)

# Derived-recipe key (stable string) for the PWT
# ``gdp_per_capita = real_gdp_output_side / population`` recipe.
PWT_GDP_PER_CAPITA_RECIPE_KEY: str = "pwt_gdp_per_capita_via_rgdpo_over_pop"

# Quality-flag string surfaced on every derived ConceptObservation.
DERIVED_CONCEPT_QUALITY_FLAG: str = "derived_concept"

# Warning codes surfaced by ``extract_concept_result`` when a derivation
# cannot produce a value for a scope. The codes mirror SRC-CONCEPT-009
# and the per-scope failure modes the catalog handles. The "missing
# numerator / denominator" codes fire when the scope lacks one side of
# the pair; the "ambiguous_pair" code fires when the scope has more
# than one numerator or denominator and the slice refuses to guess;
# the "non_numeric_*" codes fire when the value is not a finite
# number (None / NaN / inf / non-numeric); the "zero_denominator"
# code fires when division would be undefined; the
# "missing_source_version" code fires when one or both inputs lack a
# non-empty source_version stamp (kept narrow to preserve
# provenance); the "pair_year_mismatch" code is a defensive safety
# net -- with year-scoped grouping it is normally unreachable, but
# the catalog keeps the check so a future refactor that loosens the
# scope key still produces a structured diagnostic rather than a
# silent row.
CONCEPT_WARNING_MISSING_NUMERATOR: str = "concept_missing_numerator"
CONCEPT_WARNING_MISSING_DENOMINATOR: str = "concept_missing_denominator"
CONCEPT_WARNING_AMBIGUOUS_PAIR: str = "concept_ambiguous_pair"
CONCEPT_WARNING_NON_NUMERIC_NUMERATOR: str = "concept_non_numeric_numerator"
CONCEPT_WARNING_NON_NUMERIC_DENOMINATOR: str = "concept_non_numeric_denominator"
CONCEPT_WARNING_ZERO_DENOMINATOR: str = "concept_zero_denominator"
CONCEPT_WARNING_MISSING_SOURCE_VERSION: str = "concept_missing_source_version"
CONCEPT_WARNING_PAIR_YEAR_MISMATCH: str = "concept_pair_year_mismatch"


# ---------------------------------------------------------------------------
# Catalog factories
# ---------------------------------------------------------------------------


def build_concept_descriptors() -> tuple[ConceptDescriptor, ...]:
    """Return the canonical ordered list of :class:`ConceptDescriptor` records.

    The first slice supports three concepts per SRC-CONCEPT-001:
    ``gdp_per_capita``, ``population``, ``gdp_total``. Future slices
    may add more; this function is the single point of registration.
    """
    return (
        ConceptDescriptor(
            concept_key=CONCEPT_GDP_PER_CAPITA,
            display_name="Real GDP per capita",
            description=(
                "Country-year GDP per capita. Source-specific "
                "scales (USD, PPP constant 2017 intl $, 2011 intl "
                "$, 2017 USD, etc.) are preserved on each emitted "
                "ConceptObservation."
            ),
            unit=None,
            scale=None,
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_POPULATION,
            display_name="Country population",
            description=(
                "Country-year population. Source-specific scales "
                "(persons, thousands of persons) are preserved on "
                "each emitted ConceptObservation."
            ),
            unit=None,
            scale=None,
        ),
        ConceptDescriptor(
            concept_key=CONCEPT_GDP_TOTAL,
            display_name="Country GDP (total)",
            description=(
                "Country-year total GDP. Source-specific scales "
                "(current USD, constant 2015 USD, 2011 intl $, "
                "2017 USD millions, etc.) are preserved on each "
                "emitted ConceptObservation."
            ),
            unit=None,
            scale=None,
        ),
    )


def build_concept_mappings() -> tuple[ConceptMapping, ...]:
    """Return the canonical ordered list of :class:`ConceptMapping` records.

    The mappings cover the three migrated sources (WDI, Maddison,
    PWT) for the three concepts above. Future slices may add more
    sources per concept; this function is the single point of
    registration.
    """
    return (
        # --- WDI direct mappings -------------------------------------
        ConceptMapping(
            concept_key=CONCEPT_GDP_PER_CAPITA,
            source_id=SourceId(slug=WDI_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(
                WDI_GDP_PER_CAPITA_INDICATOR_CODE,
                WDI_GDP_PER_CAPITA_PPP_CONSTANT_2017_INDICATOR_CODE,
            ),
            notes=(
                "WDI publishes GDP per capita in two scales: "
                "current USD (NY.GDP.PCAP.CD) and constant 2017 "
                "international dollars at PPP (NY.GDP.PCAP.PP.KD). "
                "Both alias the concept; extraction produces one "
                "ConceptObservation per matching observation."
            ),
        ),
        ConceptMapping(
            concept_key=CONCEPT_POPULATION,
            source_id=SourceId(slug=WDI_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(WDI_POPULATION_INDICATOR_CODE,),
        ),
        ConceptMapping(
            concept_key=CONCEPT_GDP_TOTAL,
            source_id=SourceId(slug=WDI_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(
                WDI_GDP_CURRENT_USD_INDICATOR_CODE,
                WDI_GDP_CONSTANT_2015_USD_INDICATOR_CODE,
            ),
            notes=(
                "WDI publishes total GDP in current USD "
                "(NY.GDP.MKTP.CD) and constant 2015 USD "
                "(NY.GDP.MKTP.KD). Both alias the concept."
            ),
        ),
        # --- Maddison direct mappings ---------------------------------
        ConceptMapping(
            concept_key=CONCEPT_GDP_PER_CAPITA,
            source_id=SourceId(slug=MADDISON_PROJECT_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(
                MADDISON_PROJECT_GDP_PER_CAPITA_INDICATOR_CODE,
            ),
            output_unit="2011_international_dollars",
        ),
        ConceptMapping(
            concept_key=CONCEPT_POPULATION,
            source_id=SourceId(slug=MADDISON_PROJECT_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(MADDISON_PROJECT_POPULATION_INDICATOR_CODE,),
            output_unit="thousands_of_persons",
        ),
        # The Maddison GDP-total indicator is itself a derived value
        # (``gdppc * pop * 1000``) computed by the Stage 2 reader;
        # the concept catalog treats it as a direct mapping onto the
        # already-derived observation.
        ConceptMapping(
            concept_key=CONCEPT_GDP_TOTAL,
            source_id=SourceId(slug=MADDISON_PROJECT_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(
                MADDISON_PROJECT_GDP_TOTAL_DERIVED_INDICATOR_CODE,
            ),
            output_unit="2011_international_dollars",
        ),
        # --- PWT direct mappings --------------------------------------
        ConceptMapping(
            concept_key=CONCEPT_POPULATION,
            source_id=SourceId(slug=PWT_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(PWT_POPULATION_INDICATOR_CODE,),
            output_unit="thousands_of_persons",
        ),
        # PWT publishes real GDP under two sides (output + expenditure);
        # both alias the concept; extraction produces one
        # ConceptObservation per matching observation.
        ConceptMapping(
            concept_key=CONCEPT_GDP_TOTAL,
            source_id=SourceId(slug=PWT_SOURCE_KEY),
            mapping_type="direct",
            indicator_codes=(
                PWT_REAL_GDP_OUTPUT_SIDE_INDICATOR_CODE,
                PWT_REAL_GDP_EXPENDITURE_SIDE_INDICATOR_CODE,
            ),
            output_unit="million_2017_USD",
        ),
        # --- PWT derived mapping --------------------------------------
        # ``gdp_per_capita = pwt_real_gdp_output_side / pwt_population``.
        # Numerator is in million_2017_USD, denominator in thousands of
        # persons; the ratio is therefore in "1000 USD per person".
        # The recipe key is carried on every emitted ConceptObservation
        # so audit code can reproduce the exact derivation.
        ConceptMapping(
            concept_key=CONCEPT_GDP_PER_CAPITA,
            source_id=SourceId(slug=PWT_SOURCE_KEY),
            mapping_type="derived",
            indicator_codes=(
                PWT_REAL_GDP_OUTPUT_SIDE_INDICATOR_CODE,
                PWT_POPULATION_INDICATOR_CODE,
            ),
            output_unit="thousand_2017_USD_per_person",
            output_scale="ratio",
            recipe_key=PWT_GDP_PER_CAPITA_RECIPE_KEY,
            notes=(
                "Per-capita GDP derived from PWT real GDP output "
                "side (rgdpo, million_2017_USD) divided by PWT "
                "population (pop, thousands of persons). Output "
                "unit is therefore 1000 USD per person. Missing, "
                "non-numeric, zero, or ambiguous inputs produce "
                "no derived row for the affected (country, year, "
                "source_version) scope."
            ),
        ),
    )


__all__ = [
    "CLIENT_EXISTING_SOURCE_KEY",
    "CONCEPT_GDP_PER_CAPITA",
    "CONCEPT_GDP_TOTAL",
    "CONCEPT_POPULATION",
    "CONCEPT_WARNING_AMBIGUOUS_PAIR",
    "CONCEPT_WARNING_MISSING_DENOMINATOR",
    "CONCEPT_WARNING_MISSING_NUMERATOR",
    "CONCEPT_WARNING_MISSING_SOURCE_VERSION",
    "CONCEPT_WARNING_NON_NUMERIC_DENOMINATOR",
    "CONCEPT_WARNING_NON_NUMERIC_NUMERATOR",
    "CONCEPT_WARNING_PAIR_YEAR_MISMATCH",
    "CONCEPT_WARNING_ZERO_DENOMINATOR",
    "DERIVED_CONCEPT_QUALITY_FLAG",
    "KNOWN_CONCEPT_KEYS",
    "MADDISON_PROJECT_GDP_PER_CAPITA_INDICATOR_CODE",
    "MADDISON_PROJECT_GDP_TOTAL_DERIVED_INDICATOR_CODE",
    "MADDISON_PROJECT_POPULATION_INDICATOR_CODE",
    "MADDISON_PROJECT_SOURCE_KEY",
    "PWT_GDP_PER_CAPITA_RECIPE_KEY",
    "PWT_POPULATION_INDICATOR_CODE",
    "PWT_REAL_GDP_EXPENDITURE_SIDE_INDICATOR_CODE",
    "PWT_REAL_GDP_OUTPUT_SIDE_INDICATOR_CODE",
    "PWT_SOURCE_KEY",
    "WDI_GDP_CONSTANT_2015_USD_INDICATOR_CODE",
    "WDI_GDP_CURRENT_USD_INDICATOR_CODE",
    "WDI_GDP_PER_CAPITA_INDICATOR_CODE",
    "WDI_GDP_PER_CAPITA_PPP_CONSTANT_2017_INDICATOR_CODE",
    "WDI_POPULATION_INDICATOR_CODE",
    "WDI_SOURCE_KEY",
    "build_concept_descriptors",
    "build_concept_mappings",
]
