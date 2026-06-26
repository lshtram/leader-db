"""WHO Global Health Observatory (GHO) API clean source adapter.

The :class:`WhoGhoApiAdapter` is the seventeenth source rebuilt
under the clean ``leaders_db.sources`` interface (after PWT,
Maddison, WDI, WGI, V-Dem, UCDP, Transparency CPI, PTS, RSF,
BTI, Freedom House, Archigos, REIGN, SIPRI Milex, SIPRI
Yearbook Ch.7, CIRIGHTS, and UNDP HDI). See
``docs/architecture/sources.md`` §7.1 for the priority list and
``docs/requirements/sources.md`` §12 for the migration plan.

The clean adapter reads the per-``(year, IndicatorCode)`` JSON
cache recorded under ``data/raw/who_gho_api/cache/`` through
lazy legacy catalog + parser imports. The adapter NEVER falls
through to HTTP in this slice -- the readiness gate enforces
``cache_policy="offline_only"`` / ``"prefer_cache"`` and rejects
the unsupported ``"refresh"`` / ``"no_cache"`` policies with a
structured ``unsupported_cache_policy`` error.
"""

from __future__ import annotations

from ._constants import (
    WHO_GHO_API_ATTRIBUTION_KEY,
    WHO_GHO_API_ATTRIBUTION_TEXT,
    WHO_GHO_API_CACHE_DIR_NAME,
    WHO_GHO_API_COVERAGE_END_YEAR,
    WHO_GHO_API_COVERAGE_START_YEAR,
    WHO_GHO_API_DEFAULT_CACHE_POLICY,
    WHO_GHO_API_DEFAULT_VERSION,
    WHO_GHO_API_HOMEPAGE_URL,
    WHO_GHO_API_INDICATOR_CODES,
    WHO_GHO_API_METADATA_NAME,
    WHO_GHO_API_OBSERVATION_FAMILY,
    WHO_GHO_API_SOURCE_KEY,
    WHO_GHO_API_SUPPORTED_FAMILIES,
    WHO_GHO_API_TRANSFORM_NAME,
    WHO_GHO_API_UNSUPPORTED_CACHE_POLICY,
)
from ._descriptor import build_who_gho_api_descriptor
from .adapter import (
    WHO_GHO_API_ADAPTER_FACTORY,
    WhoGhoApiAdapter,
    create_who_gho_api_adapter,
    register_who_gho_api,
)

__all__ = [
    "WHO_GHO_API_ADAPTER_FACTORY",
    "WHO_GHO_API_ATTRIBUTION_KEY",
    "WHO_GHO_API_ATTRIBUTION_TEXT",
    "WHO_GHO_API_CACHE_DIR_NAME",
    "WHO_GHO_API_COVERAGE_END_YEAR",
    "WHO_GHO_API_COVERAGE_START_YEAR",
    "WHO_GHO_API_DEFAULT_CACHE_POLICY",
    "WHO_GHO_API_DEFAULT_VERSION",
    "WHO_GHO_API_HOMEPAGE_URL",
    "WHO_GHO_API_INDICATOR_CODES",
    "WHO_GHO_API_METADATA_NAME",
    "WHO_GHO_API_OBSERVATION_FAMILY",
    "WHO_GHO_API_SOURCE_KEY",
    "WHO_GHO_API_SUPPORTED_FAMILIES",
    "WHO_GHO_API_TRANSFORM_NAME",
    "WHO_GHO_API_UNSUPPORTED_CACHE_POLICY",
    "WhoGhoApiAdapter",
    "build_who_gho_api_descriptor",
    "create_who_gho_api_adapter",
    "register_who_gho_api",
]
