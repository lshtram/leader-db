"""Canonical constants for the clean World Bank Poverty and Inequality
Platform (PIP) adapter.

The World Bank Poverty and Inequality Platform (PIP) is the
World-Bank-maintained public database of poverty, inequality, and
distribution indicators, served through the documented PIP API at
``https://pip.worldbank.org/api`` (CSV / JSON endpoints) and the
PIP home page at ``https://pip.worldbank.org/``. PIP delivers
per-(country, year, reporting_level, welfare_type, poverty_line)
indicators such as the poverty headcount ratio, the poverty gap,
and the Gini index, all of which are PPP / survey / consumption-
or-income specific and version-stamped by the World Bank.

This module owns the static source metadata the adapter exposes:
the canonical slug, default version (a PIP version-id stamp such
as ``20260324_2021`` or ``20260324_2017``), attribution text,
homepage URL, observation family, coverage envelope, the
supported raw file names (cached CSV / JSON exports), the
schema-contract column names, the indicator codes the adapter
emits, and the structured readiness warning codes.

Source hygiene
--------------

- ``source_type="api"`` because PIP delivers results through a
  documented backend API (the canonical PIP API at
  ``https://pip.worldbank.org/api``), even though the unified
  adapter in this slice is offline / cache-only.
- ``requires_network=False`` -- the unified adapter never invokes
  the network; live fetch is intentionally NOT supported in this
  slice (the task brief: "Build an offline/cache-first adapter.
  Do NOT implement live HTTP fetching"). The cache-policy gate
  blocks ``"refresh"`` / ``"no_cache"`` with a structured
  ``world_bank_poverty_inequality_platform_unsupported_cache_policy``
  error so the runner refuses to dispatch ``read_raw`` /
  ``transform`` rather than silently surfacing an HTTP-fetched
  payload.

Coverage envelope
-----------------

PIP coverage is version-stamped and PPP / survey / welfare-type
specific. The descriptor advertises a conservative broad envelope
(``start_year`` / ``end_year``) and the canonical PIP version
stamp so downstream query code can refuse to dispatch
out-of-coverage year requests. The readiness gate surfaces a
structured ``YEAR_ABSENT`` warning on out-of-coverage year
requests so the runner never silently proxies an out-of-coverage
year to the nearest in-coverage year (SRC-COV-002 / SRC-COV-003).
Estimates are survey / model / PPP specific and SHOULD NOT be
mixed across PIP version stamps or PPP bases without explicit
metadata propagation -- the descriptor's ``coverage_hint.notes``
carries the explicit caveat.

Observation-family shape
------------------------

The unified adapter emits ONE observation family
(``poverty_inequality_country_year``) so downstream query code
can filter by family without consulting the per-source catalog.
The catalog carries the 3 source-native indicators the canonical
PIP CSV typically exposes:

- ``world_bank_poverty_inequality_platform_poverty_headcount_ratio``
  -- the poverty headcount ratio at the cached row's poverty
  line (preserved verbatim on ``extension[..._poverty_line]``).
- ``world_bank_poverty_inequality_platform_poverty_gap`` -- the
  poverty gap at the cached row's poverty line (preserved
  verbatim).
- ``world_bank_poverty_inequality_platform_gini_index`` -- the
  Gini index of the cached row's distribution.

The catalog deliberately does NOT include a default
``world_bank_poverty_inequality_platform_ppp_factor`` /
``world_bank_poverty_inequality_platform_survey_year`` indicator
beyond what the source-native CSV / JSON explicitly exposes.
The transform never invents a poverty / inequality value from
missing source-native data; blank / non-numeric cells are
emitted as ``value=None`` / ``value_type="missing"`` plus the
verbatim raw cell text on ``extension.raw_value``.

Source-native preservation
--------------------------

PIP source-native cells carry the World-Bank-maintained reporting
country display name + the source-native country code (typically
a 3-character code that LOOKS LIKE ISO3 but is the World Bank's
own reporting identifier -- not a canonical ISO3 mapping). The
unified adapter preserves the source-native country code + display
name verbatim on every emitted observation; ``country_code`` is
left as ``None`` (the adapter does NOT assume the PIP source
identifier is a canonical ISO3 even when it resembles one) and
the source-native identifier is preserved on
``extension["world_bank_poverty_inequality_platform_country_code_raw"]``
so audit code can recover the original cell. Per-row PPP version
+ reporting level + welfare type + poverty line are preserved on
the audit-trail extension payload so downstream code can recover
the source-native provenance without inventing values.

Attribution
-----------

The World Bank PIP dataset citation block in
``docs/sources/attributions.md`` (``world_bank_poverty_inequality_platform``
section) is byte-identical to the
:data:`WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_ATTRIBUTION_TEXT`
constant (Always-On Rule #15). The drift guard enforces
byte-identity between the code constant and the docs.

Caveat
------

PIP poverty / inequality estimates are SURVEY- and
PPP-specific and SHOULD NOT be silently mixed across PIP version
stamps (e.g. ``20260324_2021`` vs ``20260324_2017``) or PPP
bases (2021 PPP vs 2017 PPP) without explicit metadata
propagation. The adapter propagates the PIP version stamp +
PPP version (when present) onto every emitted observation's
audit-trail extension payload so downstream scorers can apply
the canonical "version / PPP basis" treatment explicitly. The
descriptor's ``coverage_hint.notes`` carries the explicit caveat.
"""

from __future__ import annotations

# Canonical slug. The data-lake folder is
# ``world_bank_poverty_inequality_platform/`` (the slug is the
# folder name; no source-key / folder-alias reconciliation is
# needed). The descriptor's ``source_id.slug`` is
# ``"world_bank_poverty_inequality_platform"``.
WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_SOURCE_KEY: str = (
    "world_bank_poverty_inequality_platform"
)

# Canonical metadata + raw file names. ``metadata.json`` is the
# runtime-local bundle metadata (gitignored per Always-On Rule
# #9). The canonical raw CSV name is ``pip_stats.csv``; the
# canonical raw JSON name is ``pip_stats.json``. The adapter
# prefers the CSV shape when both are staged.
WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_METADATA_NAME: str = (
    "metadata.json"
)
WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_CSV_NAME: str = "pip_stats.csv"
WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_JSON_NAME: str = "pip_stats.json"
WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_LOCAL_FILE_NAMES: tuple[str, ...] = (
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_CSV_NAME,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_JSON_NAME,
)

# Canonical default version stamp. The PIP dataset is
# version-stamped by the World Bank with a version_id such as
# ``20260324_2021`` (PIP 2021 PPP base) or ``20260324_2017``
# (PIP 2017 PPP base) -- the version ID encodes the PIP release
# date + the PPP base year. The descriptor advertises the
# canonical default stamp; the staged metadata's ``source_version``
# field must match this stamp byte-for-byte for readiness to
# pass.
WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_VERSION: str = (
    "World Bank PIP, version 20260324_2021"
)

# Canonical coverage envelope -- a broad PPP / survey envelope
# that the canonical PIP dataset covers. PIP records typically
# begin in the early 1960s (when the first survey-based poverty
# estimates become available for low / lower-middle income
# countries) and end in the most recent PIP release (the
# canonical probe stamp is 2021 for the ``20260324_2021`` PIP
# version, with a few extrapolation cells into 2024 for a
# handful of countries). The descriptor advertises the canonical
# envelope so downstream query code can refuse to dispatch
# out-of-coverage year requests (SRC-COV-002 / SRC-COV-003).
WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_COVERAGE_START_YEAR: int = 1960
WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_COVERAGE_END_YEAR: int = 2024

# Canonical homepage + API URLs. The homepage is the
# user-facing citation landing page; the API URL is the
# canonical PIP backend (the unified adapter in this slice
# does NOT invoke the API at runtime -- it is preserved here
# only as the canonical provenance reference so downstream
# operators / audits can locate the canonical PIP source).
# Live fetch is intentionally NOT supported in this slice; the
# readiness gate blocks ``cache_policy="refresh"`` /
# ``"no_cache"`` with a structured
# ``world_bank_poverty_inequality_platform_unsupported_cache_policy``
# error.
WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_HOMEPAGE_URL: str = (
    "https://pip.worldbank.org/"
)
WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_API_URL: str = (
    "https://pip.worldbank.org/api"
)

# Canonical attribution key + text. The text is byte-identical
# to the ``world_bank_poverty_inequality_platform`` section in
# ``docs/sources/attributions.md`` (Always-On Rule #15). The
# World Bank permits use of its published material subject to
# the World Bank Terms of Use for Datasets; attribution
# required.
WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_ATTRIBUTION_KEY: str = (
    "world_bank_poverty_inequality_platform"
)
WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_ATTRIBUTION_TEXT: str = (
    "World Bank (2025) Poverty and Inequality Platform "
    "(version {version_ID}) [Data set] World Bank Group, "
    "www.pip.worldbank.org."
)

# Default version-id placeholder string for the
# ``{version_ID}`` interpolation slot. The descriptor
# substitutes the canonical version stamp at observation
# emission time so downstream readers can recover the exact
# PIP version the cached bundle carries without consulting
# the bundle's ``metadata.json``.
WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_VERSION_ID: str = (
    "20260324_2021"
)
WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_PPP_VERSION: str = "2021"

# Single observation family. The descriptor advertises this
# single family so downstream query code can filter by
# ``observation_family == "poverty_inequality_country_year"``
# without consulting the per-source catalog.
WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_OBSERVATION_FAMILY: str = (
    "poverty_inequality_country_year"
)
WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_SUPPORTED_FAMILIES: tuple[str, ...] = (
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_OBSERVATION_FAMILY,
)

# 3 catalog indicators -- one per source-native numeric
# indicator typically exposed by the canonical PIP CSV /
# JSON export:
# - poverty headcount ratio (the proportion of the population
#   living below the row's poverty line);
# - poverty gap (the depth of poverty below the row's poverty
#   line);
# - Gini index (the row's distribution Gini).
WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_INDICATOR_HEADCOUNT: str = (
    "world_bank_poverty_inequality_platform_poverty_headcount_ratio"
)
WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_INDICATOR_GAP: str = (
    "world_bank_poverty_inequality_platform_poverty_gap"
)
WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_INDICATOR_GINI: str = (
    "world_bank_poverty_inequality_platform_gini_index"
)
WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_INDICATOR_CODES: tuple[str, ...] = (
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_INDICATOR_HEADCOUNT,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_INDICATOR_GAP,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_INDICATOR_GINI,
)

# Canonical required CSV / JSON columns. The cached PIP CSV /
# JSON export carries a documented set of columns; the
# clean adapter validates the parsed header against this set
# and refuses to emit any observations when a required column
# is missing. The 11 canonical required columns cover the
# minimum identity + indicator schema:
# - ``country_code`` -- the source-native reporting country
#   identifier (a 3-character code that LOOKS LIKE ISO3 but is
#   the World Bank's own reporting identifier -- the adapter
#   does NOT assume it is a canonical ISO3 even when it
#   resembles one);
# - ``country_name`` -- the source-native reporting country
#   display name (preserved verbatim);
# - ``year`` -- the year of the indicator observation;
# - ``reporting_level`` -- the survey reporting level
#   (e.g. ``"national"`` / ``"rural"`` / ``"urban"``; preserved
#   verbatim as a string);
# - ``welfare_type`` -- the welfare type (e.g.
#   ``"income"`` / ``"consumption"``; preserved verbatim as a
#   string);
# - ``poverty_line`` -- the poverty line value (preserved
#   verbatim as a string; may carry a numeric value such as
#   ``"1.9"`` for the international $1.90/day line);
# - ``headcount`` -- the poverty headcount ratio (numeric;
#   may be blank / non-numeric for some rows);
# - ``poverty_gap`` -- the poverty gap (numeric; may be blank
#   / non-numeric for some rows);
# - ``gini`` -- the Gini index (numeric; may be blank /
#   non-numeric for some rows).
# Column names are matched case-sensitively against the parsed
# header; canonical CSV / JSON exports carry exactly these
# column names.
WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_REQUIRED_COLUMNS: tuple[str, ...] = (
    "country_code",
    "country_name",
    "year",
    "reporting_level",
    "welfare_type",
    "poverty_line",
    "headcount",
    "poverty_gap",
    "gini",
    "version_id",
    "ppp_version",
)

# Canonical 11-column PIP header row. Re-exported as a separate
# constant so the raw-read JSON parser can compute the canonical
# header (the union of every object's keys, in the order they
# first appear) WITHOUT mutating the required-columns tuple.
WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_COV_HEADER_ROW: tuple[str, ...] = (
    "country_code",
    "country_name",
    "year",
    "reporting_level",
    "welfare_type",
    "poverty_line",
    "headcount",
    "poverty_gap",
    "gini",
    "version_id",
    "ppp_version",
)

# Optional CSV / JSON columns beyond the 11 required schema
# columns. These are preserved on the parsed row payload and
# propagated onto the observation's ``extension`` field so audit
# code can recover the original cell, but their absence is NOT a
# schema contract violation (the cached bundle may legitimately
# omit these optional extras without breaking per-row emission).
# ``version_id`` and ``ppp_version`` are intentionally NOT listed
# here: they are required audit columns and every row must match
# the bundle metadata before transform.
WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_OPTIONAL_COLUMNS: tuple[str, ...] = (
    "ppp_base_year",
    "survey_year",
    "survey_comparability",
    "notes",
)

# Asset id templates for the canonical raw CSV / JSON cached
# bundle. The asset id follows the canonical
# ``<source_key>:<file_name>`` convention used by the SIPRI
# Arms Transfers / CTBTO Treaty Status / IAEA Safeguards /
# Polity V / SIPRI Milex / WGI / WDI / V-Dem / UCDP / CPI /
# PWT adapters.
WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_CSV_ASSET_ID: str = (
    f"{WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_SOURCE_KEY}:"
    f"{WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_CSV_NAME}"
)
WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_JSON_ASSET_ID: str = (
    f"{WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_SOURCE_KEY}:"
    f"{WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_JSON_NAME}"
)

# Structured readiness warning codes. The codes are surfaced as
# ``SourceWarning(severity='error')`` / ``'warning'`` payloads
# so the runner / CLI can dispatch on the code.
WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_LOCAL_FILES_INVALID: str = (
    "world_bank_poverty_inequality_platform_local_files_invalid"
)
WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_METADATA_VERSION_MISMATCH: str = (
    "world_bank_poverty_inequality_platform_metadata_version_mismatch"
)
WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_CHECKSUM_MISMATCH: str = (
    "world_bank_poverty_inequality_platform_checksum_mismatch"
)
WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_SCHEMA_ERROR: str = (
    "world_bank_poverty_inequality_platform_schema_error"
)
WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_UNSUPPORTED_VERSION: str = (
    "unsupported_version"
)
WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_UNSUPPORTED_CACHE_POLICY: str = (
    "unsupported_cache_policy"
)

# Transform name + scale + unit. The unified PIP values are
# preserved on the ``unit`` / ``scale`` fields so downstream
# scorers can read the raw numeric value without re-parsing
# the extension payload.
WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_TRANSFORM_NAME: str = (
    "world_bank_poverty_inequality_platform_pip_stats_v1"
)
WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_RATIO_UNIT: str = (
    "world_bank_pip_poverty_headcount_ratio"
)
WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_RATIO_SCALE: str = "ratio_0_1"
WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_GAP_UNIT: str = (
    "world_bank_pip_poverty_gap"
)
WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_GAP_SCALE: str = "ratio_0_1"
WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_GINI_UNIT: str = (
    "world_bank_pip_gini_index"
)
WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_GINI_SCALE: str = "gini_0_100"


# The default cache policy for the unified adapter. ``offline_only``
# is the documented safe default: the PIP API is documented and
# public, but the unified adapter in this slice is offline-only --
# the readiness gate blocks unsupported policies with a structured
# ``unsupported_cache_policy`` error.
WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_CACHE_POLICY: str = (
    "offline_only"
)


__all__ = [
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_API_URL",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_ATTRIBUTION_KEY",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_ATTRIBUTION_TEXT",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_CHECKSUM_MISMATCH",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_COVERAGE_END_YEAR",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_COVERAGE_START_YEAR",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_COV_HEADER_ROW",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_CSV_ASSET_ID",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_CSV_NAME",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_CACHE_POLICY",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_VERSION",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_VERSION_ID",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_GAP_SCALE",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_GAP_UNIT",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_GINI_SCALE",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_GINI_UNIT",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_HOMEPAGE_URL",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_INDICATOR_CODES",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_INDICATOR_GAP",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_INDICATOR_GINI",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_INDICATOR_HEADCOUNT",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_JSON_ASSET_ID",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_JSON_NAME",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_LOCAL_FILES_INVALID",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_LOCAL_FILE_NAMES",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_METADATA_NAME",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_METADATA_VERSION_MISMATCH",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_OBSERVATION_FAMILY",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_OPTIONAL_COLUMNS",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_RATIO_SCALE",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_RATIO_UNIT",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_REQUIRED_COLUMNS",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_SCHEMA_ERROR",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_SOURCE_KEY",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_SUPPORTED_FAMILIES",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_TRANSFORM_NAME",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_UNSUPPORTED_CACHE_POLICY",
    "WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_UNSUPPORTED_VERSION",
]
