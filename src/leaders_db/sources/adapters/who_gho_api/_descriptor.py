"""Descriptor factory for the WHO Global Health Observatory (GHO) API adapter.

This module owns the static metadata that does not change between
adapter instances: the canonical source constants (source key,
default version, attribution text, homepage URL, observation
families, coverage envelope), and the
:func:`build_who_gho_api_descriptor` factory.

The constants are re-exported from :mod:`._constants`; this
module only assembles them into a :class:`SourceDescriptor`.

Source-type semantics
---------------------

The descriptor advertises ``source_type="api"`` per
``docs/architecture/sources.md`` §5.2 and
``docs/sources/registry.md``: WHO GHO's canonical access path is
the OData API, augmented by a per-``(year, indicator)`` JSON
cache the adapter consults first. The staged
``data/raw/who_gho_api/metadata.json`` carries
``source_url="https://ghoapi.azureedge.net/api/"`` so the
API/cache-backed provenance is explicit.

The descriptor advertises ``requires_network=True`` because the
API is the canonical access path; the unified adapter is still
cache-only in this slice (the readiness gate enforces
``cache_policy="offline_only"`` / ``"prefer_cache"`` and the read
path never falls through to HTTP).
"""

from __future__ import annotations

from leaders_db.sources.contracts import (
    CoverageHint,
    SourceDescriptor,
    SourceId,
)

from ._constants import (
    WHO_GHO_API_ATTRIBUTION_KEY,
    WHO_GHO_API_COVERAGE_END_YEAR,
    WHO_GHO_API_COVERAGE_START_YEAR,
    WHO_GHO_API_DEFAULT_VERSION,
    WHO_GHO_API_HOMEPAGE_URL,
    WHO_GHO_API_OBSERVATION_FAMILY,
    WHO_GHO_API_SOURCE_KEY,
    WHO_GHO_API_SUPPORTED_FAMILIES,
)


def build_who_gho_api_descriptor() -> SourceDescriptor:
    """Build the canonical WHO GHO API :class:`SourceDescriptor`.

    The descriptor is the static metadata the registry exposes for
    source discovery (SRC-ID-003). The values mirror the canonical
    catalog and citation block in ``docs/sources/attributions.md``
    (Rule #15).

    The descriptor advertises ``source_type="api"`` and
    ``requires_network=True`` so downstream query code and the
    runner can refuse to dispatch network I/O unless
    ``cache_policy`` explicitly allows it.
    """
    return SourceDescriptor(
        source_id=SourceId(slug=WHO_GHO_API_SOURCE_KEY),
        display_name="WHO Global Health Observatory (OData API)",
        source_type="api",
        supported_observation_families=WHO_GHO_API_SUPPORTED_FAMILIES,
        default_version=WHO_GHO_API_DEFAULT_VERSION,
        homepage_url=WHO_GHO_API_HOMEPAGE_URL,
        attribution_key=WHO_GHO_API_ATTRIBUTION_KEY,
        coverage_hint=CoverageHint(
            start_year=WHO_GHO_API_COVERAGE_START_YEAR,
            end_year=WHO_GHO_API_COVERAGE_END_YEAR,
            countries=None,
            leaders=None,
            notes=(
                "API/cache-backed country-year health indicators; 5 in-scope "
                f"{WHO_GHO_API_OBSERVATION_FAMILY} records for life "
                "expectancy, under-5 mortality, and DTP3 / HepB3 / BCG "
                "immunization coverage. Coverage 1990-present, varies by "
                "indicator and country. Public OData API at "
                "https://ghoapi.azureedge.net/api/."
            ),
        ),
        requires_manual_approval=False,
        requires_network=True,
    )


__all__ = ["build_who_gho_api_descriptor"]
