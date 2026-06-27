"""Descriptor factory for the clean Wikipedia Action API adapter.

The Wikipedia Action API (English Wikipedia) at
``https://en.wikipedia.org/w/api.php`` is the **always-on
narrative-context helper** for the prototype (per
``docs/requirements/top-level-requirements.md`` §3 + §9 + §12). The
canonical Stage 2 access path is the public Action API, but the
unified adapter reads the per-``(query, action)`` JSON cache
recorded under ``<raw_root>/wikipedia_search_extract/cache/`` through
lazy legacy parser imports. The adapter NEVER falls through to HTTP
in this slice -- the readiness gate enforces
``cache_policy="offline_only"`` / ``"prefer_cache"`` and rejects the
unsupported ``"refresh"`` / ``"no_cache"`` policies with a structured
``unsupported_cache_policy`` error.

The descriptor advertises the canonical Wikipedia static metadata
(source_id ``wikipedia_search_extract``, default version ``"Action
API"``, ``source_type="api"`` with ``requires_network=False`` because
the unified adapter is cache-only in this slice and the network path
is not exercised; coverage hint ``None`` (Wikipedia is global, not
temporally scoped); single observation family
``leader_identity_context``; Action API base URL; attribution text
``"Wikipedia (CC BY-SA 4.0)."``).
"""

from __future__ import annotations

from leaders_db.sources.contracts import (
    CoverageHint,
    SourceDescriptor,
    SourceId,
)

from ._constants import (
    WIKIPEDIA_SEARCH_EXTRACT_ATTRIBUTION_KEY,
    WIKIPEDIA_SEARCH_EXTRACT_COVERAGE_END_YEAR,
    WIKIPEDIA_SEARCH_EXTRACT_COVERAGE_START_YEAR,
    WIKIPEDIA_SEARCH_EXTRACT_DEFAULT_VERSION,
    WIKIPEDIA_SEARCH_EXTRACT_HOMEPAGE_URL,
    WIKIPEDIA_SEARCH_EXTRACT_OBSERVATION_FAMILY,
    WIKIPEDIA_SEARCH_EXTRACT_SOURCE_KEY,
    WIKIPEDIA_SEARCH_EXTRACT_SUPPORTED_FAMILIES,
)


def build_wikipedia_search_extract_descriptor() -> SourceDescriptor:
    """Build the canonical Wikipedia Action API :class:`SourceDescriptor`.

    The descriptor is the static metadata the registry exposes for
    source discovery (SRC-ID-003). The values mirror the canonical
    catalog and citation block in ``docs/sources/attributions.md``
    (Rule #15).

    The descriptor advertises ``source_type="api"`` because the
    canonical Stage 2 access path is the Wikipedia Action API -- a
    public, queryable, structured API, not a bulk dataset download.
    The descriptor advertises ``requires_network=False`` because the
    unified adapter is cache-only in this slice -- the readiness gate
    refuses ``cache_policy="refresh"`` / ``"no_cache"`` and the read
    path never falls through to HTTP.

    The coverage hint advertises ``None`` for both ``start_year`` and
    ``end_year`` because Wikipedia is not temporally scoped (the API
    returns the live page revision for a given title). The notes carry
    the canonical Action API base URL plus the cache layout (per-
    ``(query, action)`` JSON cache under
    ``<raw_root>/wikipedia_search_extract/cache/``) plus the two
    indicator codes emitted by the clean adapter
    (``wikipedia_extract_lead`` for the ``extracts`` Action API
    action; ``wikipedia_search_results`` for the ``search`` Action
    API action) and the request-input contract
    (``request.leaders=`` carries the explicit query / title strings).
    """
    return SourceDescriptor(
        source_id=SourceId(
            slug=WIKIPEDIA_SEARCH_EXTRACT_SOURCE_KEY,
        ),
        display_name=(
            "Wikipedia Action API (search + extract)"
        ),
        source_type="api",
        supported_observation_families=(
            WIKIPEDIA_SEARCH_EXTRACT_SUPPORTED_FAMILIES
        ),
        default_version=WIKIPEDIA_SEARCH_EXTRACT_DEFAULT_VERSION,
        homepage_url=WIKIPEDIA_SEARCH_EXTRACT_HOMEPAGE_URL,
        attribution_key=(
            WIKIPEDIA_SEARCH_EXTRACT_ATTRIBUTION_KEY
        ),
        coverage_hint=CoverageHint(
            start_year=(
                WIKIPEDIA_SEARCH_EXTRACT_COVERAGE_START_YEAR
            ),
            end_year=(
                WIKIPEDIA_SEARCH_EXTRACT_COVERAGE_END_YEAR
            ),
            countries=None,
            leaders=None,
            notes=(
                "Wikipedia Action API narrative-context source (CC "
                "BY-SA 4.0). Canonical access path is the public "
                f"Action API at {WIKIPEDIA_SEARCH_EXTRACT_HOMEPAGE_URL}. "
                "The clean adapter reads the per-(query, action) "
                "JSON cache under "
                "<raw_root>/wikipedia_search_extract/cache/ through "
                "lazy legacy parser imports. The clean adapter is "
                "cache-only in this slice (requires_network=False); "
                "the readiness gate refuses cache_policy='refresh' / "
                "'no_cache' and the read path never falls through to "
                "HTTP. The cache key is "
                "'wikipedia_<action>_<query_hash>_<params_hash>.json' "
                "(action in {'extracts', 'search'}; query_hash is a "
                "10-char SHA-256 prefix of the lower-cased query; "
                "params_hash is 'default' for extracts and a 10-char "
                "SHA-256 prefix of {'limit': 10} for search). The "
                "adapter emits "
                f"{WIKIPEDIA_SEARCH_EXTRACT_OBSERVATION_FAMILY} "
                "observations for the two legacy catalog variables "
                "('wikipedia_extract_lead' for action=extracts; "
                "'wikipedia_search_results' for action=search). "
                "Per-observation year=None, country_code=None, "
                "leader_id=None, leader_name=None (the Action API "
                "responses are not temporally scoped, not "
                "country-coded, and not leader-resolved; Stage 3 / "
                "Stage 4 resolve from the verbatim raw_value audit "
                "trail). The request.leaders= list carries the "
                "explicit query / title strings (the clean-slice "
                "input contract -- the helper does NOT browse / "
                "discover); missing or empty leaders= fails readiness "
                "before read/transform. years= and countries= are "
                "unsupported filters (the readiness envelope surfaces "
                "a structured unsupported_filter warning); the "
                "unified adapter never invents year / country / "
                "leader values."
            ),
        ),
        requires_manual_approval=False,
        requires_network=False,
    )


__all__ = [
    "build_wikipedia_search_extract_descriptor",
]
