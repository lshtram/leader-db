"""Wikipedia Action API (search + extract) clean source adapter.

The :class:`WikipediaSearchExtractAdapter` is the next source rebuilt
under the clean ``leaders_db.sources`` interface (after PWT,
Maddison Project, World Bank WDI, World Bank WGI, V-Dem, UCDP,
Transparency CPI, PTS, RSF, BTI, Freedom House, Archigos, REIGN,
SIPRI Milex, SIPRI Yearbook Ch.7, CIRIGHTS, UNDP HDI, WHO GHO API,
FAS, and Wikidata WikiProject heads-of-state-and-government). See
``docs/architecture/sources.md`` §7.1 for the priority list and
``docs/requirements/sources.md`` §12 for the migration plan.

The clean adapter reads the per-``(query, action)`` JSON cache
recorded under ``<raw_root>/wikipedia_search_extract/cache/`` through
lazy legacy parser imports. The adapter NEVER falls through to HTTP
in this slice -- the readiness gate enforces
``cache_policy="offline_only"`` / ``"prefer_cache"`` and rejects the
unsupported ``"refresh"`` / ``"no_cache"`` policies with a structured
``unsupported_cache_policy`` error.

The Wikipedia source is structurally distinct from every prior clean
migration: it is an **API-backed** source (per
``docs/architecture/sources.md`` §5.2) carrying per-(query, action)
web/knowledge context (one ``NormalizedObservation`` per parsed
``extracts`` page or per parsed ``search`` hit). The clean adapter
emits ``leader_identity_context`` observations for the two legacy
catalog variables (``wikipedia_extract_lead`` for the ``extracts``
Action API action; ``wikipedia_search_results`` for the ``search``
Action API action), preserves the Wikipedia action / title / pageid
/ extract text verbatim, does NOT invent ISO3 codes / leader IDs /
year scopes, and exposes the verbatim per-row payload JSON on
``extension.raw_row_payload`` for the audit trail.

The clean-slice request-input contract maps the Action API query
list to ``request.leaders`` (this source is a cached web/knowledge
snippet helper, ``leaders=`` here means query strings, NOT resolved
leader IDs). Missing / empty ``leaders=`` fails readiness with a
structured ``wikipedia_search_extract_missing_queries`` error
BEFORE the reader opens the cache -- the helper does NOT browse /
discover. ``years=`` and ``countries=`` are unsupported filters --
the readiness envelope surfaces a structured ``UNSUPPORTED_FILTER``
warning per request filter when set (the runner ignores the filters
and still emits the cached rows; the unified adapter never invents
year / country / leader values).
"""

from __future__ import annotations

from ._constants import (
    WIKIPEDIA_SEARCH_EXTRACT_ACTION_TO_INDICATOR,
    WIKIPEDIA_SEARCH_EXTRACT_ATTRIBUTION_KEY,
    WIKIPEDIA_SEARCH_EXTRACT_ATTRIBUTION_TEXT,
    WIKIPEDIA_SEARCH_EXTRACT_CACHE_DIR_NAME,
    WIKIPEDIA_SEARCH_EXTRACT_COVERAGE_END_YEAR,
    WIKIPEDIA_SEARCH_EXTRACT_COVERAGE_START_YEAR,
    WIKIPEDIA_SEARCH_EXTRACT_DEFAULT_CACHE_POLICY,
    WIKIPEDIA_SEARCH_EXTRACT_DEFAULT_VERSION,
    WIKIPEDIA_SEARCH_EXTRACT_HOMEPAGE_URL,
    WIKIPEDIA_SEARCH_EXTRACT_INDICATOR_TO_ACTION,
    WIKIPEDIA_SEARCH_EXTRACT_INDICATORS,
    WIKIPEDIA_SEARCH_EXTRACT_LEGACY_VERSION_ALIAS,
    WIKIPEDIA_SEARCH_EXTRACT_LOCAL_FILES_INVALID,
    WIKIPEDIA_SEARCH_EXTRACT_METADATA_NAME,
    WIKIPEDIA_SEARCH_EXTRACT_METADATA_VERSION_MISMATCH,
    WIKIPEDIA_SEARCH_EXTRACT_MISSING_QUERIES,
    WIKIPEDIA_SEARCH_EXTRACT_MISSING_RAW,
    WIKIPEDIA_SEARCH_EXTRACT_OBSERVATION_FAMILY,
    WIKIPEDIA_SEARCH_EXTRACT_SOURCE_KEY,
    WIKIPEDIA_SEARCH_EXTRACT_SUPPORTED_FAMILIES,
    WIKIPEDIA_SEARCH_EXTRACT_TRANSFORM_NAME,
    WIKIPEDIA_SEARCH_EXTRACT_UNSUPPORTED_CACHE_POLICY,
    WIKIPEDIA_SEARCH_EXTRACT_UNSUPPORTED_FILTER,
    WIKIPEDIA_SEARCH_EXTRACT_UNSUPPORTED_REQUEST,
    WIKIPEDIA_SEARCH_EXTRACT_UNSUPPORTED_VERSION,
)
from ._descriptor import (
    build_wikipedia_search_extract_descriptor,
)
from ._paths import build_cache_key
from .adapter import (
    WIKIPEDIA_SEARCH_EXTRACT_ADAPTER_FACTORY,
    WikipediaSearchExtractAdapter,
    create_wikipedia_search_extract_adapter,
    register_wikipedia_search_extract,
)

__all__ = [
    "WIKIPEDIA_SEARCH_EXTRACT_ACTION_TO_INDICATOR",
    "WIKIPEDIA_SEARCH_EXTRACT_ADAPTER_FACTORY",
    "WIKIPEDIA_SEARCH_EXTRACT_ATTRIBUTION_KEY",
    "WIKIPEDIA_SEARCH_EXTRACT_ATTRIBUTION_TEXT",
    "WIKIPEDIA_SEARCH_EXTRACT_CACHE_DIR_NAME",
    "WIKIPEDIA_SEARCH_EXTRACT_COVERAGE_END_YEAR",
    "WIKIPEDIA_SEARCH_EXTRACT_COVERAGE_START_YEAR",
    "WIKIPEDIA_SEARCH_EXTRACT_DEFAULT_CACHE_POLICY",
    "WIKIPEDIA_SEARCH_EXTRACT_DEFAULT_VERSION",
    "WIKIPEDIA_SEARCH_EXTRACT_HOMEPAGE_URL",
    "WIKIPEDIA_SEARCH_EXTRACT_INDICATORS",
    "WIKIPEDIA_SEARCH_EXTRACT_INDICATOR_TO_ACTION",
    "WIKIPEDIA_SEARCH_EXTRACT_LEGACY_VERSION_ALIAS",
    "WIKIPEDIA_SEARCH_EXTRACT_LOCAL_FILES_INVALID",
    "WIKIPEDIA_SEARCH_EXTRACT_METADATA_NAME",
    "WIKIPEDIA_SEARCH_EXTRACT_METADATA_VERSION_MISMATCH",
    "WIKIPEDIA_SEARCH_EXTRACT_MISSING_QUERIES",
    "WIKIPEDIA_SEARCH_EXTRACT_MISSING_RAW",
    "WIKIPEDIA_SEARCH_EXTRACT_OBSERVATION_FAMILY",
    "WIKIPEDIA_SEARCH_EXTRACT_SOURCE_KEY",
    "WIKIPEDIA_SEARCH_EXTRACT_SUPPORTED_FAMILIES",
    "WIKIPEDIA_SEARCH_EXTRACT_TRANSFORM_NAME",
    "WIKIPEDIA_SEARCH_EXTRACT_UNSUPPORTED_CACHE_POLICY",
    "WIKIPEDIA_SEARCH_EXTRACT_UNSUPPORTED_FILTER",
    "WIKIPEDIA_SEARCH_EXTRACT_UNSUPPORTED_REQUEST",
    "WIKIPEDIA_SEARCH_EXTRACT_UNSUPPORTED_VERSION",
    "WikipediaSearchExtractAdapter",
    "build_cache_key",
    "build_wikipedia_search_extract_descriptor",
    "create_wikipedia_search_extract_adapter",
    "register_wikipedia_search_extract",
]
