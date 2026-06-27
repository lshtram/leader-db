"""Wikidata WikiProject heads-of-state-and-government clean source adapter.

The :class:`WikidataHeadsOfStateGovernmentAdapter` is the twentieth
source rebuilt under the clean ``leaders_db.sources`` interface
(after PWT, Maddison Project, World Bank WDI, World Bank WGI,
V-Dem, UCDP, Transparency CPI, PTS, RSF, BTI, Freedom House,
Archigos, REIGN, SIPRI Milex, SIPRI Yearbook Ch.7, CIRIGHTS,
UNDP HDI, WHO GHO API, and FAS). See
``docs/architecture/sources.md`` §7.1 for the priority list and
``docs/requirements/sources.md`` §12 for the migration plan.

The clean adapter reads the per-``(year, country_qids)`` JSON
cache recorded under ``<raw_root>/wikidata_heads_of_state_government/cache/``
through lazy legacy parser imports. The adapter NEVER falls
through to HTTP in this slice -- the readiness gate enforces
``cache_policy="offline_only"`` / ``"prefer_cache"`` and rejects
the unsupported ``"refresh"`` / ``"no_cache"`` policies with a
structured ``unsupported_cache_policy`` error.

The Wikidata source is structurally distinct from every prior
clean migration: it is a **knowledge-base** source (per
``docs/architecture/sources.md`` §5.2) carrying per-binding
leader-identity evidence (one SPARQL binding per
``(country_qid, person_qid, office_qid, start_date, end_date)``
tuple). The clean adapter emits
``leader_identity_country_year`` observations for the two
legacy catalog variables (``wikidata_head_of_state_held`` for
Q30461 and ``wikidata_head_of_government_held`` for Q22857062),
preserves the Wikidata English labels verbatim, does NOT invent
ISO3 codes / leader IDs, and exposes the verbatim SPARQL
binding JSON on ``extension.raw_binding`` for the audit trail.
"""

from __future__ import annotations

from ._constants import (
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_ATTRIBUTION_KEY,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_ATTRIBUTION_TEXT,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_CACHE_DIR_NAME,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_CHECKSUM_MISMATCH,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_COVERAGE_END_YEAR,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_COVERAGE_START_YEAR,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_DEFAULT_CACHE_POLICY,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_DEFAULT_VERSION,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_HOMEPAGE_URL,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_INDICATORS,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_LEGACY_VERSION_ALIAS,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_LOCAL_FILES_INVALID,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_METADATA_NAME,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_METADATA_VERSION_MISMATCH,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_NON_QID_COUNTRY,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_OBSERVATION_FAMILY,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_PROJECT_URL,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_KEY,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SPARQL_ENDPOINT_URL,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SUPPORTED_FAMILIES,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_TRANSFORM_NAME,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_UNSUPPORTED_CACHE_POLICY,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_UNSUPPORTED_MULTI_YEAR,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_UNSUPPORTED_VERSION,
)
from ._descriptor import (
    build_wikidata_heads_of_state_government_descriptor,
)
from .adapter import (
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_ADAPTER_FACTORY,
    WikidataHeadsOfStateGovernmentAdapter,
    create_wikidata_heads_of_state_government_adapter,
    register_wikidata_heads_of_state_government,
)

__all__ = [
    "WIKIDATA_HEADS_OF_STATE_GOVERNMENT_ADAPTER_FACTORY",
    "WIKIDATA_HEADS_OF_STATE_GOVERNMENT_ATTRIBUTION_KEY",
    "WIKIDATA_HEADS_OF_STATE_GOVERNMENT_ATTRIBUTION_TEXT",
    "WIKIDATA_HEADS_OF_STATE_GOVERNMENT_CACHE_DIR_NAME",
    "WIKIDATA_HEADS_OF_STATE_GOVERNMENT_CHECKSUM_MISMATCH",
    "WIKIDATA_HEADS_OF_STATE_GOVERNMENT_COVERAGE_END_YEAR",
    "WIKIDATA_HEADS_OF_STATE_GOVERNMENT_COVERAGE_START_YEAR",
    "WIKIDATA_HEADS_OF_STATE_GOVERNMENT_DEFAULT_CACHE_POLICY",
    "WIKIDATA_HEADS_OF_STATE_GOVERNMENT_DEFAULT_VERSION",
    "WIKIDATA_HEADS_OF_STATE_GOVERNMENT_HOMEPAGE_URL",
    "WIKIDATA_HEADS_OF_STATE_GOVERNMENT_INDICATORS",
    "WIKIDATA_HEADS_OF_STATE_GOVERNMENT_LEGACY_VERSION_ALIAS",
    "WIKIDATA_HEADS_OF_STATE_GOVERNMENT_LOCAL_FILES_INVALID",
    "WIKIDATA_HEADS_OF_STATE_GOVERNMENT_METADATA_NAME",
    "WIKIDATA_HEADS_OF_STATE_GOVERNMENT_METADATA_VERSION_MISMATCH",
    "WIKIDATA_HEADS_OF_STATE_GOVERNMENT_NON_QID_COUNTRY",
    "WIKIDATA_HEADS_OF_STATE_GOVERNMENT_OBSERVATION_FAMILY",
    "WIKIDATA_HEADS_OF_STATE_GOVERNMENT_PROJECT_URL",
    "WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_KEY",
    "WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SPARQL_ENDPOINT_URL",
    "WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SUPPORTED_FAMILIES",
    "WIKIDATA_HEADS_OF_STATE_GOVERNMENT_TRANSFORM_NAME",
    "WIKIDATA_HEADS_OF_STATE_GOVERNMENT_UNSUPPORTED_CACHE_POLICY",
    "WIKIDATA_HEADS_OF_STATE_GOVERNMENT_UNSUPPORTED_MULTI_YEAR",
    "WIKIDATA_HEADS_OF_STATE_GOVERNMENT_UNSUPPORTED_VERSION",
    "WikidataHeadsOfStateGovernmentAdapter",
    "build_wikidata_heads_of_state_government_descriptor",
    "create_wikidata_heads_of_state_government_adapter",
    "register_wikidata_heads_of_state_government",
]
