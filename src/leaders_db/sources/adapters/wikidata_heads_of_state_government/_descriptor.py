"""Descriptor factory for the clean Wikidata WikiProject heads-of-state adapter.

The Wikidata WikiProject heads-of-state-and-government source is
the **always-on leader-identity helper** for the prototype (per
``docs/requirements/top-level-requirements.md`` §3, §9, and §12).
The canonical Stage 2 access path is the public Wikidata SPARQL
endpoint (``https://query.wikidata.org/sparql``, CC0 1.0). The
unified adapter reads the per-``(office_qids, year, country_qids)``
JSON cache recorded under
``<raw_root>/wikidata_heads_of_state_government/cache/`` through
lazy legacy parser imports. The adapter NEVER falls through to
HTTP in this slice -- the readiness gate enforces
``cache_policy="offline_only"`` / ``"prefer_cache"`` and rejects
the unsupported ``"refresh"`` / ``"no_cache"`` policies with a
structured ``unsupported_cache_policy`` error.

The descriptor advertises the canonical Wikidata static metadata
(source_id ``wikidata_heads_of_state_government``, default version
``"SPARQL"``, ``source_type="knowledge_base"`` -- NOT
``"api"`` because the unified adapter is cache-only in this slice
and the network path is not exercised; ``requires_network=False``
because the unified adapter never invokes the network; coverage
hint ``None`` (Wikidata is global, all-years, all-countries);
single observation family ``leader_identity_country_year``; SPARQL
endpoint homepage URL; attribution text
``"Wikidata (CC0 1.0)."``).
"""

from __future__ import annotations

from leaders_db.sources.contracts import (
    CoverageHint,
    SourceDescriptor,
    SourceId,
)

from ._constants import (
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_ATTRIBUTION_KEY,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_COVERAGE_END_YEAR,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_COVERAGE_START_YEAR,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_DEFAULT_VERSION,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_HOMEPAGE_URL,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_OBSERVATION_FAMILY,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_PROJECT_URL,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_KEY,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SPARQL_ENDPOINT_URL,
    WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SUPPORTED_FAMILIES,
)


def build_wikidata_heads_of_state_government_descriptor() -> SourceDescriptor:
    """Build the canonical Wikidata HoS/HoG :class:`SourceDescriptor`.

    The descriptor is the static metadata the registry exposes for
    source discovery (SRC-ID-003). The values mirror the canonical
    catalog and citation block in ``docs/sources/attributions.md``
    (Rule #15).

    The descriptor advertises ``source_type="knowledge_base"``
    because the canonical Stage 2 access path is the Wikidata
    SPARQL endpoint -- a public, queryable, structured knowledge
    base, not a bulk dataset download. The descriptor advertises
    ``requires_network=False`` because the unified adapter is
    cache-only in this slice -- the readiness gate refuses
    ``cache_policy="refresh"`` / ``"no_cache"`` and the read path
    never falls through to HTTP.

    The coverage hint advertises ``None`` for both ``start_year``
    and ``end_year`` because Wikidata covers all years / all
    countries / all leaders; there is no temporal or geographic
    cap to encode. The notes carry the canonical SPARQL endpoint
    + WikiProject page URLs plus the cache layout (per-
    ``(office_qids, year, country_qids)`` JSON cache under
    ``<raw_root>/wikidata_heads_of_state_government/cache/``) plus
    the two indicator codes emitted by the clean adapter
    (``wikidata_head_of_state_held`` for Q30461, and
    ``wikidata_head_of_government_held`` for Q22857062).
    """
    return SourceDescriptor(
        source_id=SourceId(
            slug=WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SOURCE_KEY,
        ),
        display_name=(
            "Wikidata WikiProject Heads of state and government"
        ),
        source_type="knowledge_base",
        supported_observation_families=(
            WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SUPPORTED_FAMILIES
        ),
        default_version=WIKIDATA_HEADS_OF_STATE_GOVERNMENT_DEFAULT_VERSION,
        homepage_url=WIKIDATA_HEADS_OF_STATE_GOVERNMENT_HOMEPAGE_URL,
        attribution_key=(
            WIKIDATA_HEADS_OF_STATE_GOVERNMENT_ATTRIBUTION_KEY
        ),
        coverage_hint=CoverageHint(
            start_year=(
                WIKIDATA_HEADS_OF_STATE_GOVERNMENT_COVERAGE_START_YEAR
            ),
            end_year=(
                WIKIDATA_HEADS_OF_STATE_GOVERNMENT_COVERAGE_END_YEAR
            ),
            countries=None,
            leaders=None,
            notes=(
                "Knowledge-base leader-identity source (CC0 1.0). "
                "Public SPARQL endpoint at "
                f"{WIKIDATA_HEADS_OF_STATE_GOVERNMENT_SPARQL_ENDPOINT_URL}; "
                f"WikiProject page at "
                f"{WIKIDATA_HEADS_OF_STATE_GOVERNMENT_PROJECT_URL}. "
                "The clean adapter reads the per-"
                "(office_qids, year, country_qids) JSON cache under "
                "<raw_root>/wikidata_heads_of_state_government/cache/ "
                "through lazy legacy parser imports. The clean adapter "
                "is cache-only in this slice "
                "(requires_network=False); the readiness gate refuses "
                "cache_policy='refresh' / 'no_cache' and the read path "
                "never falls through to HTTP. The cache key is "
                "'wd_ALL_<year>_<country_hash>_<template_hash>.json' "
                "(year='YYYY' for explicit-year requests, 'current' "
                "for the all-current-holders run; country_hash='all' "
                "when country_qids=None, '<10-char-sha256>' "
                "otherwise). The adapter emits "
                f"{WIKIDATA_HEADS_OF_STATE_GOVERNMENT_OBSERVATION_FAMILY} "
                "observations for the two legacy catalog variables "
                "('wikidata_head_of_state_held' for office Q30461, "
                "'wikidata_head_of_government_held' for office "
                "Q22857062). Per-observation ``country_code=None`` "
                "(Wikidata QIDs are source-native, not ISO3; Stage 3 "
                "resolves QIDs via the canonical country mapping); "
                "``country_name`` carries the Wikidata English label "
                "verbatim; ``leader_id=None``; ``leader_name`` carries "
                "the Wikidata person English label verbatim. The "
                "verbatim SPARQL binding JSON is preserved on "
                "extension.raw_binding for the audit trail. "
                "Coverage: all years, all countries, all leaders "
                "(Wikidata is global)."
            ),
        ),
        requires_manual_approval=False,
        requires_network=False,
    )


__all__ = [
    "build_wikidata_heads_of_state_government_descriptor",
]
