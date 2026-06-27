"""Constants for the clean Wikidata WikiProject heads-of-state-and-government adapter.

The Wikidata WikiProject heads-of-state-and-government source is the
**always-on leader-identity helper** for the prototype. The canonical
Stage 2 access path is the public Wikidata SPARQL endpoint
(``https://query.wikidata.org/sparql``, CC0 1.0). The clean adapter
reads the per-``(office_qids, year, country_qids)`` JSON cache
recorded under ``<raw_root>/wikidata_heads_of_state_government/cache/``
through lazy legacy parser imports. The adapter NEVER falls through
to HTTP in this slice -- the readiness gate enforces
``cache_policy="offline_only"`` / ``"prefer_cache"`` and rejects the
unsupported ``"refresh"`` / ``"no_cache"`` policies with a
structured ``unsupported_cache_policy`` error.

The Wikidata source is structurally distinct from every prior clean
migration: it is a **knowledge-base** source (per
``docs/architecture/sources.md`` §5.2) -- NOT a country-year
scoring source, NOT a leader-spell source. The Wikidata SPARQL
response carries per-binding leader-identity evidence: each binding
is one ``(country_qid, country_label, person_qid, person_label,
office_qid, office_label, start, end, statement)`` tuple for a
specific office held by a specific person in a specific country
during a specific date range. The clean adapter does NOT invent
ISO3 country codes, does NOT invent leader identifiers, and does
NOT relabel rows. ``country_code`` / ``leader_id`` are left
``None`` until Stage 3 / Stage 4 fill them via the canonical
country / leader mapping tables. ``country_name`` carries the
Wikidata English label (e.g. ``"United States"``) verbatim;
``leader_name`` carries the Wikidata person English label
(e.g. ``"Joe Biden"``) verbatim.

The constant block owns the canonical source metadata (source
key, default version, attribution text, homepage URL, observation
family, cache layout, coverage envelope) plus the structured
warning codes the readiness gate surfaces.

Cache key convention (mirrors the legacy
:func:`leaders_db.ingest.wikidata_heads_of_state_government_http.build_cache_key`):

- ``wd_ALL_<year>_<country_hash>_<template_hash>.json`` -- the
  per-``(year, country_qids)`` SPARQL response cache. The
  ``<year>`` slot is ``YYYY`` for explicit-year requests and
  ``current`` for the all-current-holders run; ``<country_hash>``
  is ``all`` when ``country_qids=None`` and ``<10-char-sha256>``
  otherwise; ``<template_hash>`` is the canonical SPARQL query
  template hash (a 10-character SHA-256 prefix of the sorted
  ``office_qids`` CSV).

The unified adapter reads from this cache structure exactly. It
does NOT auto-create cache files, does NOT overwrite cache files,
and does NOT invoke the SPARQL endpoint. HTTP writes belong to the
legacy orchestrator and to the dedicated cache-refresh command
(future work).
"""

from __future__ import annotations

# Source identity. ``wikidata_heads_of_state_government`` is the
# canonical slug used everywhere in the data lake, the CLI dispatch,
# and the legacy ``STAGE2_ADAPTERS`` table.
WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_KEY = (
    "wikidata_heads_of_state_government"
)
WIKIDATA_HEADS_OF_STATE_GOVERNMENT_ATTRIBUTION_KEY = (
    "wikidata_heads_of_state_government"
)

# Canonical default version. The clean adapter advertises
# ``"SPARQL"`` (the short, canonical stamp matching the
# ``source_type="knowledge_base"`` / ``source_type="api"`` access
# path). The legacy staged
# ``data/raw/wikidata_heads_of_state_government/metadata.json``
# carries ``version="SPARQL endpoint (no version)"`` -- the
# readiness gate accepts BOTH values so the existing staged bundle
# does not need to be rewritten as part of the migration.
WIKIDATA_HEADS_OF_STATE_GOVERNMENT_DEFAULT_VERSION = "SPARQL"
WIKIDATA_HEADS_OF_STATE_GOVERNMENT_LEGACY_VERSION_ALIAS = (
    "SPARQL endpoint (no version)"
)

# Canonical SPARQL endpoint URL. Public, no auth. The unified
# adapter NEVER calls this URL; it is the documented home of the
# data and the canonical source for the descriptor / attribution.
WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SPARQL_ENDPOINT_URL = (
    "https://query.wikidata.org/sparql"
)

# Canonical WikiProject page URL (the project's own documentation
# page; cited in the metadata + attributions.md + the descriptor
# notes alongside the SPARQL endpoint).
WIKIDATA_HEADS_OF_STATE_GOVERNMENT_PROJECT_URL = (
    "https://www.wikidata.org/wiki/Wikidata:WikiProject_Heads_of_state_and_government"
)

# The descriptor advertises the SPARQL endpoint as the
# ``homepage_url`` because it is the canonical access path; the
# WikiProject page is recorded in the coverage hint notes so a
# developer can navigate to the project documentation from the
# descriptor.
WIKIDATA_HEADS_OF_STATE_GOVERNMENT_HOMEPAGE_URL = (
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SPARQL_ENDPOINT_URL
)

# Cache layout constants. Mirrors the legacy
# ``data/raw/wikidata_heads_of_state_government/cache/<cache_key>.json``
# convention. The unified adapter reads ONLY this cache; the HTTP
# layer is not invoked by the unified read path.
WIKIDATA_HEADS_OF_STATE_GOVERNMENT_METADATA_NAME = "metadata.json"
WIKIDATA_HEADS_OF_STATE_GOVERNMENT_CACHE_DIR_NAME = "cache"

# Coverage envelope. Wikidata covers all years / all countries /
# all leaders -- there is no temporal / geographic cap. The
# descriptor advertises ``None`` for both start / end year so the
# runner does not enforce an artificial cap. The
# ``leader_identity`` rating category is the only consumer; the
# source is the **always-on leader-identity helper** for the
# prototype per ``docs/requirements/top-level-requirements.md`` §3
# + §9.
WIKIDATA_HEADS_OF_STATE_GOVERNMENT_COVERAGE_START_YEAR: int | None = None
WIKIDATA_HEADS_OF_STATE_GOVERNMENT_COVERAGE_END_YEAR: int | None = None

# Single observation family -- the adapter emits leader-identity
# reference observations for downstream Stage 4 (leader resolver)
# per the documented `leader_identity_country_year` family. The
# descriptor advertises the tuple
# ``("leader_identity_country_year",)`` so downstream query code
# can filter by family without consulting the per-source catalog.
WIKIDATA_HEADS_OF_STATE_GOVERNMENT_OBSERVATION_FAMILY = (
    "leader_identity_country_year"
)
WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SUPPORTED_FAMILIES = (
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_OBSERVATION_FAMILY,
)

# Canonical attribution text. The text is byte-identical to the
# ``Wikidata (CC0 1.0).`` line in ``docs/sources/attributions.md``
# (the wikidata_heads_of_state_government section + the citation
# cheat-sheet row). The
# ``test_wikidata_heads_of_state_government_attribution_text_matches_attributions_doc``
# drift guard enforces byte-identity. The legacy
# ``WIKIDATA_HEADS_OF_STATE_GOVERNMENT_ATTRIBUTION`` constant in
# ``src/leaders_db/ingest/wikidata_heads_of_state_government_io.py``
# carries the same text -- both constants must remain in sync
# (Rule #15).
WIKIDATA_HEADS_OF_STATE_GOVERNMENT_ATTRIBUTION_TEXT = (
    "Wikidata (CC0 1.0)."
)

# The two in-scope indicator codes from the legacy indicator
# catalog (``src/leaders_db/ingest/catalogs/wikidata_heads_of_state_government.csv``):
# the Wikidata office QIDs are ``Q30461`` (head of state) and
# ``Q22857062`` (head of government). The unified adapter maps the
# legacy Stage 2 ``variable_name`` -> ``raw_column`` (office QID)
# via the legacy catalog reader. These two variable names are the
# canonical Stage 2 / Stage 9 names exposed by the clean adapter.
WIKIDATA_HEADS_OF_STATE_GOVERNMENT_INDICATORS: tuple[str, ...] = (
    "wikidata_head_of_state_held",
    "wikidata_head_of_government_held",
)

# Default cache policy. ``offline_only`` is the documented safe
# default: the unified adapter never invokes the network in this
# slice; the SPARQL endpoint is consulted only by the legacy HTTP
# orchestrator and by future cache-refresh tooling.
WIKIDATA_HEADS_OF_STATE_GOVERNMENT_DEFAULT_CACHE_POLICY = (
    "offline_only"
)

# Transform / readiness codes -- module-local so the readiness
# envelope surfaces them as structured :class:`SourceWarning`
# payloads with the canonical code strings.
WIKIDATA_HEADS_OF_STATE_GOVERNMENT_TRANSFORM_NAME = (
    "wikidata_heads_of_state_government_country_year_v1"
)
WIKIDATA_HEADS_OF_STATE_GOVERNMENT_LOCAL_FILES_INVALID = (
    "wikidata_heads_of_state_government_local_files_invalid"
)
WIKIDATA_HEADS_OF_STATE_GOVERNMENT_METADATA_VERSION_MISMATCH = (
    "wikidata_heads_of_state_government_metadata_version_mismatch"
)
WIKIDATA_HEADS_OF_STATE_GOVERNMENT_UNSUPPORTED_VERSION = (
    "unsupported_version"
)
WIKIDATA_HEADS_OF_STATE_GOVERNMENT_UNSUPPORTED_CACHE_POLICY = (
    "unsupported_cache_policy"
)
WIKIDATA_HEADS_OF_STATE_GOVERNMENT_CHECKSUM_MISMATCH = (
    "wikidata_heads_of_state_government_checksum_mismatch"
)
WIKIDATA_HEADS_OF_STATE_GOVERNMENT_NON_QID_COUNTRY = (
    "wikidata_non_qid_country_filter"
)
WIKIDATA_HEADS_OF_STATE_GOVERNMENT_UNSUPPORTED_MULTI_YEAR = (
    "wikidata_multi_year_request_unsupported"
)

__all__ = [
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
]
