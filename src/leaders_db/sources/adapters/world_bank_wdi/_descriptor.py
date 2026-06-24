"""World Bank WDI constants + canonical :class:`SourceDescriptor`.

This module owns the static metadata that does not change between
adapter instances: the canonical source constants (source key,
default version, attribution text, homepage URL, observation
families, coverage envelope), and the
:func:`build_world_bank_wdi_descriptor` factory.

Split out of
:mod:`leaders_db.sources.adapters.world_bank_wdi.adapter` so the
adapter class module stays focused on the lifecycle methods. The
constants are also re-exported from
:mod:`leaders_db.sources.adapters.world_bank_wdi` (the package
root) so callers can
``from leaders_db.sources.adapters.world_bank_wdi import
WORLD_BANK_WDI_SOURCE_KEY`` without knowing which submodule the
symbol lives in.

Source-type semantics
---------------------

The descriptor advertises ``source_type="api"`` per
``docs/architecture/sources.md`` §5.2: WDI's canonical access path
is the World Bank API v2 endpoint, augmented by a per-(year,
indicator) JSON cache the adapter consults first. The legacy
``data/raw/world_bank_wdi/metadata.json`` carries
``source_version="World Bank API v2; cached indicator responses"``
to make the API/cache-backed provenance explicit. The unified
adapter carries the same string as the canonical default version
so readiness can validate it byte-for-byte against the staged
bundle's ``metadata.json``.

Observation-family shape
------------------------

WDI covers both economic and social indicators (see the catalog at
``src/leaders_db/ingest/catalogs/wdi.csv``: ``economic_wellbeing``
+ ``social_wellbeing``). The descriptor advertises the tuple
``("economic_country_year", "social_country_year")`` so downstream
query code can filter by either family without consulting a
per-source catalog.
"""

from __future__ import annotations

from leaders_db.sources.contracts import (
    CoverageHint,
    SourceDescriptor,
    SourceId,
)

# ---------------------------------------------------------------------------
# Canonical World Bank WDI constants
# ---------------------------------------------------------------------------

WORLD_BANK_WDI_SOURCE_KEY: str = "world_bank_wdi"

# Canonical metadata + cache file names. ``metadata.json`` is
# always at the bundle root; the cache root lives at
# ``cache/`` (per ``data/raw/world_bank_wdi/metadata.json``). The
# legacy ``local_files`` field is ``["cache/"]`` to record the
# presence of the cache directory.
WORLD_BANK_WDI_METADATA_NAME: str = "metadata.json"
WORLD_BANK_WDI_CACHE_DIR_NAME: str = "cache"

# Canonical default version -- the exact string the staged
# ``data/raw/world_bank_wdi/metadata.json`` carries under
# ``source_version``. API/cache-backed; per-cached-response
# SHA-256 is optional. The unified adapter uses this string as
# the canonical version stamp; the bundle's
# ``metadata.json['source_version']`` must match it byte-for-byte
# for readiness to pass.
WORLD_BANK_WDI_DEFAULT_VERSION: str = (
    "World Bank API v2; cached indicator responses"
)

# Coverage envelope. WDI's full availability window starts at
# 1960 and reaches 2023+; the precise upper bound is per-country
# and per-indicator (the docs explicitly note
# "1960-2023+ (varies by indicator and country)"). The
# descriptor uses an open-ended end_year (None) so the runner
# does not enforce an artificial cap.
WORLD_BANK_WDI_COVERAGE_START_YEAR: int = 1960
WORLD_BANK_WDI_COVERAGE_END_YEAR: int | None = None

# WDI v2 API endpoint base. Public, no auth. The full per-(year,
# indicator) URL is built as
# ``WDI_API_BASE + country/all/indicator/{code}?date={year}&format=json&per_page=...``.
# We use the API root (not the data.worldbank.org homepage) in
# the descriptor because the API is the canonical access path;
# the user-facing data portal is recorded separately in the
# legacy ``WDI_ATTRIBUTION`` citation.
WORLD_BANK_WDI_HOMEPAGE_URL: str = "https://api.worldbank.org/v2/"

# Attribution key + canonical text. The text is byte-identical to
# the legacy ``WDI_ATTRIBUTION`` constant in
# ``src/leaders_db/ingest/wdi_io.py`` and to the
# ``world_bank_wdi`` section in
# ``docs/sources/attributions.md`` (Always-On Rule #15). The
# ``test_world_bank_wdi_attribution_text_matches_attributions_doc``
# drift guard enforces byte-identity.
WORLD_BANK_WDI_ATTRIBUTION_KEY: str = "world_bank_wdi"
WORLD_BANK_WDI_ATTRIBUTION_TEXT: str = (
    "World Bank. 2024. World Development Indicators. "
    "Washington, D.C.: The World Bank. https://data.worldbank.org/ "
    "Licensed under CC BY 4.0 "
    "(https://creativecommons.org/licenses/by/4.0/)."
)

# Two observation families: WDI covers both economic and social
# indicators. The catalog at
# ``src/leaders_db/ingest/catalogs/wdi.csv`` partitions its 14
# indicators into ``economic_wellbeing`` (10 indicators) and
# ``social_wellbeing`` (4 indicators). The unified descriptor
# exposes both families so downstream query code can filter by
# either without consulting the per-source catalog.
WORLD_BANK_WDI_OBSERVATION_FAMILY_ECONOMIC: str = "economic_country_year"
WORLD_BANK_WDI_OBSERVATION_FAMILY_SOCIAL: str = "social_country_year"
WORLD_BANK_WDI_SUPPORTED_FAMILIES: tuple[str, ...] = (
    WORLD_BANK_WDI_OBSERVATION_FAMILY_ECONOMIC,
    WORLD_BANK_WDI_OBSERVATION_FAMILY_SOCIAL,
)

# Default cache policy for WDI in the new runner. ``offline_only``
# is the documented safe default: WDI is API-backed but the new
# runner must not surprise a test or production call with network
# I/O. ``cache_policy="refresh"`` / ``"no_cache"`` is NOT
# supported by the unified WDI adapter in this slice -- the
# readiness gate refuses both with a structured
# ``unsupported_cache_policy`` error.
WORLD_BANK_WDI_DEFAULT_CACHE_POLICY: str = "offline_only"

# JSON pointer prefix for entries inside the WDI v2 2-element
# response array. The response shape is
# ``[metadata, data]``; ``data`` is a list whose i-th entry is
# the ``i``-th country record for the requested (indicator,
# year) tuple. Each ``NormalizedObservation`` carries the
# matching ``/1/{i}`` json_pointer so downstream audit code can
# resolve the per-row source location without re-reading the
# cache file.
WORLD_BANK_WDI_JSON_POINTER_DATA_PREFIX: str = "/1/"


def build_world_bank_wdi_descriptor() -> SourceDescriptor:
    """Build the canonical World Bank WDI :class:`SourceDescriptor`.

    The descriptor is the static metadata the registry exposes for
    source discovery (SRC-ID-003). The values mirror the legacy
    Stage 2 constants + the canonical citation block in
    ``docs/sources/attributions.md`` (Rule #15).

    The descriptor advertises ``source_type="api"`` and
    ``requires_network=True`` so downstream query code and the
    runner can refuse to dispatch network I/O unless
    ``cache_policy`` explicitly allows it.
    """
    return SourceDescriptor(
        source_id=SourceId(slug=WORLD_BANK_WDI_SOURCE_KEY),
        display_name="World Bank World Development Indicators",
        source_type="api",
        supported_observation_families=WORLD_BANK_WDI_SUPPORTED_FAMILIES,
        default_version=WORLD_BANK_WDI_DEFAULT_VERSION,
        homepage_url=WORLD_BANK_WDI_HOMEPAGE_URL,
        attribution_key=WORLD_BANK_WDI_ATTRIBUTION_KEY,
        coverage_hint=CoverageHint(
            start_year=WORLD_BANK_WDI_COVERAGE_START_YEAR,
            end_year=WORLD_BANK_WDI_COVERAGE_END_YEAR,
            countries=None,
            leaders=None,
            notes=(
                "Country-year economic + social indicators; "
                "~217 real countries; coverage 1960-present, "
                "varies by indicator and country. API-backed "
                "with per-(year, indicator) JSON cache; "
                "CC BY 4.0."
            ),
        ),
        requires_manual_approval=False,
        requires_network=True,
    )


__all__ = [
    "WORLD_BANK_WDI_ATTRIBUTION_KEY",
    "WORLD_BANK_WDI_ATTRIBUTION_TEXT",
    "WORLD_BANK_WDI_CACHE_DIR_NAME",
    "WORLD_BANK_WDI_COVERAGE_END_YEAR",
    "WORLD_BANK_WDI_COVERAGE_START_YEAR",
    "WORLD_BANK_WDI_DEFAULT_CACHE_POLICY",
    "WORLD_BANK_WDI_DEFAULT_VERSION",
    "WORLD_BANK_WDI_HOMEPAGE_URL",
    "WORLD_BANK_WDI_JSON_POINTER_DATA_PREFIX",
    "WORLD_BANK_WDI_METADATA_NAME",
    "WORLD_BANK_WDI_OBSERVATION_FAMILY_ECONOMIC",
    "WORLD_BANK_WDI_OBSERVATION_FAMILY_SOCIAL",
    "WORLD_BANK_WDI_SOURCE_KEY",
    "WORLD_BANK_WDI_SUPPORTED_FAMILIES",
    "build_world_bank_wdi_descriptor",
]
