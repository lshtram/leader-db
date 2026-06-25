"""Semantic indicator concept catalog over :class:`NormalizedObservation`.

This sub-package provides a small query/analysis-time normalization
layer above :class:`NormalizedObservation` and below scoring /
research code. Analysts and scorers can ask for stable cross-source
concepts such as ``gdp_per_capita``, ``population``, or ``gdp_total``
without memorizing source-specific indicator strings such as
``wdi_gdp_per_capita_ppp_constant_2017`` or
``maddison_project_gdp_per_capita_2011_intl``.

The concept layer is **aliases or recipes over observations**, never
new evidence. Source-specific ``NormalizedObservation.indicator_code``
values remain preserved on every emitted :class:`ConceptObservation`
so audit, provenance, cataloging, and source-specific analysis can
keep using the canonical source keys without consulting the concept
catalog.

Design rules (mirrors ``docs/architecture/sources.md`` §5.8 and
``docs/requirements/sources.md`` §10A SRC-CONCEPT-001..013):

- Concept mappings are either ``direct`` aliases or ``derived``
  recipes over same-source, same-entity, same-year observations.
- The concept catalog never reads raw files, calls source adapters,
  reruns ingestion, or writes processed/DB output. It only consumes
  the provided :class:`NormalizedObservation` records.
- Unknown concept keys and unsupported concept/source pairs raise
  actionable :class:`UnknownConceptError` /
  :class:`UnsupportedConceptSourceError` exceptions -- never silent
  empty mappings or guessed values.
- Derived concept outputs carry provenance to every input observation
  id, both raw locators, both source indicator codes, the source id
  and source version, an explicit ``derived_concept`` quality flag,
  and the recipe key in the extension payload.
- The PWT derivation scope key includes ``year`` so multi-year valid
  same-country inputs produce one derived row per country-year,
  never an ambiguous multi-year aggregate (SRC-CONCEPT-011).
- Missing, non-numeric, zero (where division would be undefined),
  ambiguous, missing / mismatched ``source_version``, or
  mismatched-year inputs for a derivation produce no derived row
  for that scope -- the slice does not silently guess values. Each
  drop reason is surfaced as a structured :class:`SourceWarning`
  via the diagnostic helper :func:`extract_concept_result`
  (SRC-CONCEPT-009, SRC-CONCEPT-012).
- Direct mappings surface a structured ``missing_value`` warning on
  the row's ``warnings`` tuple when the input value is missing /
  non-numeric; the row is emitted with ``value=None`` and
  ``value_type="missing"`` so the observation id / locator is not
  lost.

The sub-package does NOT import ``leaders_db.ingest``. The legacy
Stage 2 subsystem stays isolated; only the unified
:class:`NormalizedObservation` contract is consumed here. The
``tests/sources/test_concepts.py::test_concepts_module_does_not_import_legacy_ingest_at_import``
test enforces this boundary by AST inspection of every submodule.

Sub-package layout (each module stays close to the 400-line
convention):

- :mod:`._direct` -- direct (alias) mapping extraction.
- :mod:`._derived` -- derived (recipe) entry points and dispatch.
- :mod:`._derived_reasons` -- per-scope drop-reason construction
  (split from :mod:`._derived` to keep module sizes focused).
- :mod:`._catalog` -- stable concept keys, indicator codes, and
  catalog factories.
- :mod:`._dataclasses` -- public dataclasses + exceptions.
- :mod:`._api` -- public functions (``list_concepts``,
  ``resolve_concept``, ``extract_concept``,
  ``extract_concept_result``).
- :mod:`.__init__` -- public re-exports.
"""

from __future__ import annotations

from ._api import (
    extract_concept,
    extract_concept_result,
    list_concepts,
    resolve_concept,
)
from ._catalog import (
    CLIENT_EXISTING_SOURCE_KEY,
    CONCEPT_GDP_PER_CAPITA,
    CONCEPT_GDP_TOTAL,
    CONCEPT_POPULATION,
    CONCEPT_WARNING_AMBIGUOUS_PAIR,
    CONCEPT_WARNING_MISSING_DENOMINATOR,
    CONCEPT_WARNING_MISSING_NUMERATOR,
    CONCEPT_WARNING_MISSING_SOURCE_VERSION,
    CONCEPT_WARNING_NON_NUMERIC_DENOMINATOR,
    CONCEPT_WARNING_NON_NUMERIC_NUMERATOR,
    CONCEPT_WARNING_PAIR_YEAR_MISMATCH,
    CONCEPT_WARNING_ZERO_DENOMINATOR,
    DERIVED_CONCEPT_QUALITY_FLAG,
    KNOWN_CONCEPT_KEYS,
    MADDISON_PROJECT_GDP_PER_CAPITA_INDICATOR_CODE,
    MADDISON_PROJECT_GDP_TOTAL_DERIVED_INDICATOR_CODE,
    MADDISON_PROJECT_POPULATION_INDICATOR_CODE,
    MADDISON_PROJECT_SOURCE_KEY,
    PWT_GDP_PER_CAPITA_RECIPE_KEY,
    PWT_POPULATION_INDICATOR_CODE,
    PWT_REAL_GDP_EXPENDITURE_SIDE_INDICATOR_CODE,
    PWT_REAL_GDP_OUTPUT_SIDE_INDICATOR_CODE,
    PWT_SOURCE_KEY,
    WDI_GDP_CONSTANT_2015_USD_INDICATOR_CODE,
    WDI_GDP_CURRENT_USD_INDICATOR_CODE,
    WDI_GDP_PER_CAPITA_INDICATOR_CODE,
    WDI_GDP_PER_CAPITA_PPP_CONSTANT_2017_INDICATOR_CODE,
    WDI_POPULATION_INDICATOR_CODE,
    WDI_SOURCE_KEY,
)
from ._dataclasses import (
    ConceptCatalogError,
    ConceptDescriptor,
    ConceptExtractionResult,
    ConceptMapping,
    ConceptMappingType,
    ConceptObservation,
    UnknownConceptError,
    UnsupportedConceptSourceError,
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
    "ConceptCatalogError",
    "ConceptDescriptor",
    "ConceptExtractionResult",
    "ConceptMapping",
    "ConceptMappingType",
    "ConceptObservation",
    "UnknownConceptError",
    "UnsupportedConceptSourceError",
    "extract_concept",
    "extract_concept_result",
    "list_concepts",
    "resolve_concept",
]
