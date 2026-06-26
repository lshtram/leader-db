"""Constants for the clean WHO Global Health Observatory (GHO) API adapter.

The WHO GHO API is a public OData 4.0 endpoint at
``https://ghoapi.azureedge.net/api/`` with ~2000 indicators. The
clean adapter narrows to the 5 in-scope ``social_wellbeing``
indicators defined in ``src/leaders_db/ingest/catalogs/who_gho_api.csv``
and reads them from the per-``(year, indicator)`` JSON cache
recorded under ``data/raw/who_gho_api/cache/``.

The constant block owns the canonical source metadata (source
key, default version, attribution text, homepage URL, observation
families, cache layout, coverage envelope) plus the structured
warning codes the readiness gate surfaces.
"""

from __future__ import annotations

WHO_GHO_API_SOURCE_KEY = "who_gho_api"
WHO_GHO_API_ATTRIBUTION_KEY = "who_gho_api"

# Canonical default version -- the exact string the existing staged
# ``data/raw/who_gho_api/metadata.json`` carries under ``version``.
# The metadata's top-level ``version`` field is the legacy alias
# the per-field validator probes first; the cleaner
# ``source_version`` field is also accepted for the new
# ``metadata.json`` shape. Mirrors the existing data-lake contract:
# the WHO GHO API is updated on a per-indicator basis, so the
# ``GHO OData v1`` label is the canonical API version stamp.
WHO_GHO_API_DEFAULT_VERSION = "GHO OData v1"

# WHO GHO OData API base. Public, no auth. The full per-(year,
# indicator) URL is built as
# ``WHO_GHO_API_BASE + IndicatorCode + ?$filter=...&$top=1000``.
WHO_GHO_API_HOMEPAGE_URL = "https://ghoapi.azureedge.net/api/"

# Cache layout constants. Mirrors the legacy
# ``data/raw/who_gho_api/cache/<year>/<IndicatorCode>.json``
# convention. The unified adapter reads ONLY this cache; the HTTP
# layer is not invoked by the unified read path.
WHO_GHO_API_METADATA_NAME = "metadata.json"
WHO_GHO_API_CACHE_DIR_NAME = "cache"

# Coverage envelope. WHO GHO API coverage is per-indicator and
# per-country; the descriptor uses a None end_year so the runner
# does not enforce an artificial cap. The earliest year with
# public OData coverage is 1990; the latest year varies by
# indicator.
WHO_GHO_API_COVERAGE_START_YEAR: int | None = 1990
WHO_GHO_API_COVERAGE_END_YEAR: int | None = None

# Single observation family -- all 5 catalog indicators are in the
# ``social_wellbeing`` category. The descriptor advertises the
# tuple ``("social_wellbeing_country_year",)`` so downstream query
# code can filter by family without consulting the per-source
# catalog.
WHO_GHO_API_OBSERVATION_FAMILY = "social_wellbeing_country_year"
WHO_GHO_API_SUPPORTED_FAMILIES = (WHO_GHO_API_OBSERVATION_FAMILY,)

# Canonical attribution text. The text is byte-identical to the
# ``WHO Global Health Observatory (World Health Organization).``
# line in ``docs/sources/attributions.md`` (lines 177-183 of the
# who_gho_api section + the citation-cheat-sheet row at line
# 263). The ``test_who_gho_api_attribution_text_matches_attributions_doc``
# drift guard enforces byte-identity. The legacy
# ``WHO_GHO_API_ATTRIBUTION`` constant in
# ``src/leaders_db/ingest/who_gho_api_io.py`` carries the longer
# ``World Health Organization. *Global Health Observatory*. ...``
# citation string; the unified adapter uses the SHORTER
# attribution block per the explicit user instruction (the
# ``docs/sources/attributions.md`` normative wording).
WHO_GHO_API_ATTRIBUTION_TEXT = (
    "WHO Global Health Observatory (World Health Organization)."
)

# Transform / readiness codes -- module-local so the readiness
# envelope surfaces them as structured :class:`SourceWarning`
# payloads with the canonical code strings.
WHO_GHO_API_TRANSFORM_NAME = "who_gho_api_country_year_v1"
WHO_GHO_API_LOCAL_FILES_INVALID = "who_gho_api_local_files_invalid"
WHO_GHO_API_METADATA_VERSION_MISMATCH = "who_gho_api_metadata_version_mismatch"
WHO_GHO_API_UNSUPPORTED_VERSION = "unsupported_version"
WHO_GHO_API_UNSUPPORTED_CACHE_POLICY = "unsupported_cache_policy"
WHO_GHO_API_NETWORK_CACHE_UNAVAILABLE = "network_cache_unavailable"
WHO_GHO_API_CHECKSUM_MISMATCH = "who_gho_api_checksum_mismatch"

# Default cache policy. ``offline_only`` is the documented safe
# default: the WHO GHO API is API-backed but the new runner must
# not surprise a test or production call with network I/O.
WHO_GHO_API_DEFAULT_CACHE_POLICY = "offline_only"

# The 5 in-scope indicator codes (WHO GHO API IndicatorCode
# values) defined in ``src/leaders_db/ingest/catalogs/who_gho_api.csv``.
# The clean adapter maps the canonical Stage 2 variable names to
# the IndicatorCode via the legacy catalog reader, but uses this
# tuple for the readiness-gate cache-file enumeration.
WHO_GHO_API_INDICATOR_CODES: tuple[str, ...] = (
    "WHOSIS_000001",
    "MDG_0000000007",
    "WHS4_100",
    "WHS4_117",
    "WHS4_543",
)

# Stable observation-family convention: the wide pivot
# (one row per (iso3, year), one column per variable name)
# produces the Stage 2 observation family name
# ``social_wellbeing_country_year``. The descriptor advertises
# it via :data:`WHO_GHO_API_OBSERVATION_FAMILY`.

__all__ = [
    "WHO_GHO_API_ATTRIBUTION_KEY",
    "WHO_GHO_API_ATTRIBUTION_TEXT",
    "WHO_GHO_API_CACHE_DIR_NAME",
    "WHO_GHO_API_CHECKSUM_MISMATCH",
    "WHO_GHO_API_COVERAGE_END_YEAR",
    "WHO_GHO_API_COVERAGE_START_YEAR",
    "WHO_GHO_API_DEFAULT_CACHE_POLICY",
    "WHO_GHO_API_DEFAULT_VERSION",
    "WHO_GHO_API_HOMEPAGE_URL",
    "WHO_GHO_API_INDICATOR_CODES",
    "WHO_GHO_API_LOCAL_FILES_INVALID",
    "WHO_GHO_API_METADATA_NAME",
    "WHO_GHO_API_METADATA_VERSION_MISMATCH",
    "WHO_GHO_API_NETWORK_CACHE_UNAVAILABLE",
    "WHO_GHO_API_OBSERVATION_FAMILY",
    "WHO_GHO_API_SOURCE_KEY",
    "WHO_GHO_API_SUPPORTED_FAMILIES",
    "WHO_GHO_API_TRANSFORM_NAME",
    "WHO_GHO_API_UNSUPPORTED_CACHE_POLICY",
    "WHO_GHO_API_UNSUPPORTED_VERSION",
]
