"""Constants for the clean Wikipedia Action API (search + extract) adapter.

The Wikipedia Action API (English Wikipedia) at
``https://en.wikipedia.org/w/api.php`` is the **always-on narrative-context
helper** for the prototype (per
``docs/requirements/top-level-requirements.md`` §3 + §9 + §12). The two
in-scope indicator codes (per the legacy catalog
``src/leaders_db/ingest/catalogs/wikipedia_search_extract.csv``) are:

- ``wikipedia_extract_lead`` -- the article lead / intro paragraph for
  a given title (``action=query&prop=extracts&exintro=1&explaintext=1``).
- ``wikipedia_search_results`` -- the search hit list for a given query
  (``action=query&list=search``).

The clean adapter reads the per-``(query, action)`` JSON cache recorded
under ``<raw_root>/wikipedia_search_extract/cache/`` through lazy legacy
``build_cache_key`` / parser imports. The adapter NEVER falls through to
HTTP in this slice -- the readiness gate enforces
``cache_policy="offline_only"`` / ``"prefer_cache"`` and rejects the
unsupported ``"refresh"`` / ``"no_cache"`` policies with a structured
``unsupported_cache_policy`` error.

The Wikipedia source is structurally distinct from every prior clean
migration:

- It is **API-backed** (public Wikipedia Action API, CC BY-SA 4.0) but
  the unified runner is offline / cache-first by default and the
  unified adapter is offline / cache-only in this slice.
- The unified adapter accepts an **explicit ``queries=`` list** through
  ``request.leaders`` (the clean-slice contract: this source is a
  cached web/knowledge snippet helper, ``leaders=`` here means query
  strings, NOT resolved leader IDs). Missing / empty ``leaders=`` fails
  readiness with a structured error before ``read_raw`` / ``transform``
  are called -- the adapter does NOT browse / discover.
- ``years=`` and ``countries=`` are **unsupported** request filters for
  this source: the Wikipedia Action API responses are not temporally
  scoped and not country-coded (the adapter surfaces a structured
  warning rather than silently dropping or filtering).

The constant block owns the canonical source metadata (source key,
default version, attribution text, homepage / API URL, observation
family, cache layout, indicator codes) plus the structured warning
codes the readiness gate surfaces.

Cache key convention (mirrors the legacy
:func:`leaders_db.ingest.wikipedia_search_extract_http.build_cache_key`):

- ``wikipedia_<action>_<query_hash>_<params_hash>.json`` -- the per-
  ``(action, query, extra_params)`` cache filename. ``<query_hash>`` is
  a 10-character SHA-256 prefix of the lower-cased, stripped query
  string; ``<params_hash>`` is a 10-character SHA-256 prefix of the
  JSON-serialised extra params (or ``"default"`` when no extra params
  are set). The canonical fixture filenames are
  ``wikipedia_extracts_62f100bfa4_default.json`` (Joe Biden, extracts),
  ``wikipedia_search_62f100bfa4_7d0587b5ac.json`` (Joe Biden, search),
  and ``wikipedia_extracts_6f47c90e93_default.json`` (AMLO, extracts).

The unified adapter reads from this cache structure exactly. It does
NOT auto-create cache files, does NOT overwrite cache files, and does
NOT invoke the Action API endpoint. HTTP writes belong to the legacy
orchestrator and to the dedicated cache-refresh command (future work).
"""

from __future__ import annotations

# Source identity. ``wikipedia_search_extract`` is the canonical slug
# used everywhere in the data lake, the CLI dispatch, and the legacy
# ``STAGE2_ADAPTERS`` table.
WIKIPEDIA_SEARCH_EXTRACT_SOURCE_KEY = "wikipedia_search_extract"
WIKIPEDIA_SEARCH_EXTRACT_ATTRIBUTION_KEY = "wikipedia_search_extract"

# Canonical default version. The clean adapter advertises the canonical
# short stamp ``"Action API"`` matching the ``source_type="api"`` /
# ``source_type="knowledge_base"`` access path. The legacy staged
# ``data/raw/wikipedia_search_extract/metadata.json`` carries the alias
# ``"Action API (no version)"`` -- the readiness gate accepts BOTH
# values so the existing staged bundle does not need to be rewritten as
# part of the migration.
WIKIPEDIA_SEARCH_EXTRACT_DEFAULT_VERSION = "Action API"
WIKIPEDIA_SEARCH_EXTRACT_LEGACY_VERSION_ALIAS = "Action API (no version)"

# Canonical Wikipedia Action API base URL (English Wikipedia). Public,
# no auth. The unified adapter NEVER calls this URL; it is the
# documented home of the data and the canonical source for the
# descriptor / attribution.
WIKIPEDIA_SEARCH_EXTRACT_HOMEPAGE_URL = "https://en.wikipedia.org/w/api.php"

# Cache layout constants. Mirrors the legacy
# ``data/raw/wikipedia_search_extract/cache/<cache_key>.json``
# convention. The unified adapter reads ONLY this cache; the HTTP layer
# is not invoked by the unified read path.
WIKIPEDIA_SEARCH_EXTRACT_METADATA_NAME = "metadata.json"
WIKIPEDIA_SEARCH_EXTRACT_CACHE_DIR_NAME = "cache"

# Wikipedia Action API responses are not temporally scoped (the API
# returns the live page revision for a given title); the prototype
# does not encode a coverage envelope for this source. ``None`` advertises
# the open envelope in the descriptor.
WIKIPEDIA_SEARCH_EXTRACT_COVERAGE_START_YEAR: int | None = None
WIKIPEDIA_SEARCH_EXTRACT_COVERAGE_END_YEAR: int | None = None

# Single observation family -- the adapter emits leader-identity-context
# observations for downstream Stage 4 (leader resolver). The descriptor
# advertises the tuple ``("leader_identity_context",)`` so downstream
# query code can filter by family without consulting the per-source
# catalog. ``leader_identity_context`` is distinguished from the
# Wikidata ``leader_identity_country_year`` family so the two
# leader-context source can co-exist in the registry without collision.
WIKIPEDIA_SEARCH_EXTRACT_OBSERVATION_FAMILY = "leader_identity_context"
WIKIPEDIA_SEARCH_EXTRACT_SUPPORTED_FAMILIES = (
    WIKIPEDIA_SEARCH_EXTRACT_OBSERVATION_FAMILY,
)

# Canonical attribution text. The text is byte-identical to the
# ``Wikipedia (CC BY-SA 4.0).`` line in ``docs/sources/attributions.md``
# (the wikipedia_search_extract section + the citation cheat-sheet row).
# The
# ``test_wikipedia_search_extract_attribution_text_matches_attributions_doc``
# drift guard enforces byte-identity. The legacy
# ``WIKIPEDIA_SEARCH_EXTRACT_ATTRIBUTION`` constant in
# ``src/leaders_db/ingest/wikipedia_search_extract_io.py`` carries the
# same text -- both constants must remain in sync (Rule #15).
WIKIPEDIA_SEARCH_EXTRACT_ATTRIBUTION_TEXT = "Wikipedia (CC BY-SA 4.0)."

# The two in-scope indicator codes from the legacy catalog
# (``src/leaders_db/ingest/catalogs/wikipedia_search_extract.csv``).
# ``wikipedia_extract_lead`` maps to the ``extracts`` Action API
# request (``prop=extracts&exintro=1&explaintext=1``);
# ``wikipedia_search_results`` maps to the ``search`` Action API
# request (``list=search``). The unified transform uses these
# variable names per the legacy Stage 2 / Stage 9 contract.
WIKIPEDIA_SEARCH_EXTRACT_INDICATORS: tuple[str, ...] = (
    "wikipedia_extract_lead",
    "wikipedia_search_results",
)

# Map of indicator code -> Action API action name. The clean adapter
# iterates the requested queries and the catalog actions; for each
# ``(query, action)`` pair it locates the matching cache file via
# :func:`leaders_db.ingest.wikipedia_search_extract_http.build_cache_key`
# (lazy import).
WIKIPEDIA_SEARCH_EXTRACT_INDICATOR_TO_ACTION: dict[str, str] = {
    "wikipedia_extract_lead": "extracts",
    "wikipedia_search_results": "search",
}
WIKIPEDIA_SEARCH_EXTRACT_ACTION_TO_INDICATOR: dict[str, str] = {
    "extracts": "wikipedia_extract_lead",
    "search": "wikipedia_search_results",
}

# Default cache policy. ``offline_only`` is the documented safe
# default: the unified adapter never invokes the network in this slice.
WIKIPEDIA_SEARCH_EXTRACT_DEFAULT_CACHE_POLICY = "offline_only"

# Transform / readiness codes -- module-local so the readiness
# envelope surfaces them as structured :class:`SourceWarning`
# payloads with the canonical code strings.
WIKIPEDIA_SEARCH_EXTRACT_TRANSFORM_NAME = "wikipedia_search_extract_query_v1"
WIKIPEDIA_SEARCH_EXTRACT_LOCAL_FILES_INVALID = (
    "wikipedia_search_extract_local_files_invalid"
)
WIKIPEDIA_SEARCH_EXTRACT_METADATA_VERSION_MISMATCH = (
    "wikipedia_search_extract_metadata_version_mismatch"
)
WIKIPEDIA_SEARCH_EXTRACT_UNSUPPORTED_VERSION = "unsupported_version"
WIKIPEDIA_SEARCH_EXTRACT_UNSUPPORTED_CACHE_POLICY = (
    "unsupported_cache_policy"
)
WIKIPEDIA_SEARCH_EXTRACT_UNSUPPORTED_FILTER = "unsupported_filter"
WIKIPEDIA_SEARCH_EXTRACT_MISSING_QUERIES = "wikipedia_search_extract_missing_queries"
WIKIPEDIA_SEARCH_EXTRACT_MISSING_RAW = "wikipedia_search_extract_missing_raw"
WIKIPEDIA_SEARCH_EXTRACT_UNSUPPORTED_REQUEST = (
    "wikipedia_search_extract_unsupported_request"
)

__all__ = [
    "WIKIPEDIA_SEARCH_EXTRACT_ACTION_TO_INDICATOR",
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
]
