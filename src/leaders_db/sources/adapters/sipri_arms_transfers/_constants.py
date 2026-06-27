"""Canonical constants for the clean SIPRI Arms Transfers adapter.

The SIPRI Arms Transfers Database is the SIPRI-maintained public
record of international transfers of major conventional arms
(see ``docs/sources/attributions.md`` ``sipri_arms_transfers``
section). The data is delivered as a CSV (the public app returns
a JSON envelope wrapping base64 CSV bytes). The unified adapter
treats the canonical bundle as a single local CSV file with a
runtime-local ``metadata.json`` and parses the SIPRI preamble /
citation lines safely.

This module owns the static source metadata the adapter exposes:
the canonical slug, default version, attribution text, homepage
URL, observation families, coverage envelope, the supported raw
file extensions, the schema-contract column names, the
indicator codes the adapter emits, and the structured readiness
warning codes.

Source hygiene
--------------

- ``source_type="api"`` because the SIPRI Arms Transfers data is
  delivered through a backend API + web app, even though the
  clean adapter in this slice is cache-only / offline-only.
- ``requires_network=False`` -- the unified adapter never invokes
  the network; live fetch is intentionally NOT supported in this
  slice (the task brief: "If implementing live fetch would be
  ambiguous, leave live fetch unsupported with structured
  readiness error and implement cached JSON/CSV ingestion only").
  The cache-policy gate blocks ``"refresh"`` / ``"no_cache"``
  with a structured ``unsupported_cache_policy`` error so the
  runner refuses to dispatch ``read_raw`` / ``transform`` rather
  than silently surfacing an HTTP-fetched payload.

Coverage envelope
-----------------

The SIPRI Arms Transfers Database covers transfers of major
conventional arms from 1950 to the most recent full calendar
year. As of probe (2026-03-09 SIPRI page snapshot), the database
covers 1950-2025. The descriptor advertises the canonical
envelope; the readiness gate surfaces a structured ``YEAR_ABSENT``
warning on out-of-coverage year requests so the runner never
silently proxies an out-of-coverage year to the nearest
in-coverage year (SRC-COV-002 / SRC-COV-003).

Observation-family shape
------------------------

The unified adapter emits TWO observation families so downstream
query code can filter by family without consulting the
per-source catalog:

1. ``arms_transfer_register_row`` -- one observation per cached
   transfer row (per supplier, recipient, order year, delivery
   year, designation, status). The 3 per-row indicators are
   ``sipri_arms_transfers_tiv_delivered``,
   ``sipri_arms_transfers_tiv_ordered``, and
   ``sipri_arms_transfers_number_delivered``. These preserve
   the per-transfer provenance for audit code and are the
   canonical raw evidence unit.

2. ``arms_transfer_country_year_aggregate`` -- one observation
   per ``(role, country, year)`` triple where ``role`` is
   ``"supplier"`` or ``"recipient"``. The aggregate is the
   deterministic sum of TIV (Trend Indicator Value) delivered
   over all transfers in the cached bundle where the country
   appears as supplier (resp. recipient) and the delivery year
   matches the year. Aggregates are computed on the transform
   side from the parsed row-level frame; the adapter does NOT
   fetch a separate aggregate cache and does NOT double-count
   supplier-side + recipient-side aggregates for the same
   country-year (the per-``(role, country, year)`` scope key
   keeps them separate).

The descriptor advertises BOTH families via
:data:`SIPRI_ARMS_TRANSFERS_SUPPORTED_FAMILIES`.

Attribution
-----------

The SIPRI Arms Transfers Database is SIPRI copyright; database
use must be non-commercial and in line with SIPRI fair-use
policy; commercial use requires licence / permission; attribution
required. The unified ``SIPRI_ARMS_TRANSFERS_ATTRIBUTION_TEXT``
constant is byte-identical to the ``sipri_arms_transfers``
section in ``docs/sources/attributions.md`` (Always-On Rule
#15). The
:func:`test_sipri_arms_transfers_attribution_text_matches_attributions_doc`
drift guard enforces byte-identity. The attribution text is
distinct from the ``sipri_milex`` and ``sipri_yearbook_ch7``
attribution strings -- SIPRI Arms Transfers is a separate
SIPRI sub-dataset with its own citation block.
"""

from __future__ import annotations

# Canonical slug. The data-lake folder is ``sipri_arms_transfers/``
# (the slug is the folder name; no source-key / folder-alias
# reconciliation is needed). The descriptor's ``source_id.slug``
# is ``"sipri_arms_transfers"``.
SIPRI_ARMS_TRANSFERS_SOURCE_KEY: str = "sipri_arms_transfers"

# Canonical metadata + raw file names. ``metadata.json`` is the
# runtime-local bundle metadata (gitignored per Always-On Rule #9).
# The canonical raw CSV name is ``trade_register.csv``; the
# canonical base64-JSON wrapper name is ``trade_register.json``
# (the SIPRI app returns a JSON envelope containing base64 CSV
# bytes -- the unified adapter supports BOTH cached shapes per
# the task brief: "either a CSV file directly or JSON containing
# base64 CSV bytes"). When the cache holds the base64-JSON
# wrapper, the metadata's ``local_files`` must list the JSON
# file name; the canonical CSV shape lists ``trade_register.csv``.
SIPRI_ARMS_TRANSFERS_METADATA_NAME: str = "metadata.json"
SIPRI_ARMS_TRANSFERS_CSV_NAME: str = "trade_register.csv"
SIPRI_ARMS_TRANSFERS_JSON_NAME: str = "trade_register.json"
SIPRI_ARMS_TRANSFERS_LOCAL_FILE_NAMES: tuple[str, ...] = (
    SIPRI_ARMS_TRANSFERS_CSV_NAME,
    SIPRI_ARMS_TRANSFERS_JSON_NAME,
)

# Canonical default version stamp. The canonical SIPRI Arms
# Transfers Trade Register export is the "Trade Register"
# snapshot in the SIPRI Arms Transfers Database; the SIPRI page
# (probed 2026-03-09) labels the latest update as "updated 9
# March 2026, includes transfers 1950-2025". The descriptor
# advertises the canonical stamp; the staged metadata's
# ``source_version`` field must match this stamp byte-for-byte
# for readiness to pass.
SIPRI_ARMS_TRANSFERS_DEFAULT_VERSION: str = (
    "SIPRI Arms Transfers Trade Register 2026-03-09 (data 1950-2025)"
)

# Canonical coverage envelope. The SIPRI Arms Transfers Database
# covers 1950-2025 as of the latest 2026-03-09 update.
SIPRI_ARMS_TRANSFERS_COVERAGE_START_YEAR: int = 1950
SIPRI_ARMS_TRANSFERS_COVERAGE_END_YEAR: int = 2025

# Canonical homepage + public app URLs. ``SIPRI_ARMS_TRANSFERS_HOMEPAGE_URL``
# is the user-facing citation landing page; the clean adapter
# in this slice does NOT invoke the public app endpoint
# (``SIPRI_ARMS_TRANSFERS_PUBLIC_APP_URL``) at runtime -- it is
# preserved here only as the canonical provenance reference so
# downstream operators / audits can locate the canonical SIPRI
# source. Live fetch is intentionally NOT supported in this
# slice; the readiness gate blocks ``cache_policy="refresh"`` /
# ``"no_cache"`` with a structured ``unsupported_cache_policy``
# error (see :data:`SIPRI_ARMS_TRANSFERS_UNSUPPORTED_CACHE_POLICY`).
SIPRI_ARMS_TRANSFERS_HOMEPAGE_URL: str = (
    "https://www.sipri.org/databases/armstransfers"
)
SIPRI_ARMS_TRANSFERS_PUBLIC_APP_URL: str = (
    "https://armstransfers.sipri.org/ArmsTransfer"
)

# Canonical attribution key + text. The text is byte-identical to
# the ``sipri_arms_transfers`` section in
# ``docs/sources/attributions.md`` (Always-On Rule #15). The
# text is intentionally distinct from the ``sipri_milex`` and
# ``sipri_yearbook_ch7`` attribution strings -- SIPRI Arms
# Transfers is a separate SIPRI sub-dataset.
SIPRI_ARMS_TRANSFERS_ATTRIBUTION_KEY: str = "sipri_arms_transfers"
SIPRI_ARMS_TRANSFERS_ATTRIBUTION_TEXT: str = (
    "SIPRI Arms Transfers Database "
    "(Stockholm International Peace Research Institute 2026)."
)

# Two observation families. The descriptor advertises BOTH so
# downstream query code can filter by family without consulting
# the per-source catalog. ``arms_transfer_register_row`` is the
# canonical per-transfer raw evidence unit;
# ``arms_transfer_country_year_aggregate`` is the deterministic
# per-``(role, country, year)`` aggregate (sum of TIV delivered
# over the cached bundle).
SIPRI_ARMS_TRANSFERS_OBSERVATION_FAMILY_REGISTER: str = (
    "arms_transfer_register_row"
)
SIPRI_ARMS_TRANSFERS_OBSERVATION_FAMILY_AGGREGATE: str = (
    "arms_transfer_country_year_aggregate"
)
SIPRI_ARMS_TRANSFERS_SUPPORTED_FAMILIES: tuple[str, ...] = (
    SIPRI_ARMS_TRANSFERS_OBSERVATION_FAMILY_REGISTER,
    SIPRI_ARMS_TRANSFERS_OBSERVATION_FAMILY_AGGREGATE,
)

# Per-transfer indicator codes (3) + per-country-year aggregate
# indicator codes (2) for the canonical 5-indicator catalog.
# The descriptor advertises the per-source catalog via the
# ``SIPRI_ARMS_TRANSFERS_INDICATOR_CODES`` tuple so downstream
# query code can filter by indicator without consulting a
# separate catalog file.
SIPRI_ARMS_TRANSFERS_INDICATOR_TIV_DELIVERED: str = (
    "sipri_arms_transfers_tiv_delivered"
)
SIPRI_ARMS_TRANSFERS_INDICATOR_TIV_ORDERED: str = (
    "sipri_arms_transfers_tiv_ordered"
)
SIPRI_ARMS_TRANSFERS_INDICATOR_NUMBER_DELIVERED: str = (
    "sipri_arms_transfers_number_delivered"
)
SIPRI_ARMS_TRANSFERS_INDICATOR_SUPPLIER_YEAR_TIV_DELIVERED: str = (
    "sipri_arms_transfers_supplier_year_tiv_delivered"
)
SIPRI_ARMS_TRANSFERS_INDICATOR_RECIPIENT_YEAR_TIV_DELIVERED: str = (
    "sipri_arms_transfers_recipient_year_tiv_delivered"
)
SIPRI_ARMS_TRANSFERS_INDICATOR_CODES: tuple[str, ...] = (
    SIPRI_ARMS_TRANSFERS_INDICATOR_TIV_DELIVERED,
    SIPRI_ARMS_TRANSFERS_INDICATOR_TIV_ORDERED,
    SIPRI_ARMS_TRANSFERS_INDICATOR_NUMBER_DELIVERED,
    SIPRI_ARMS_TRANSFERS_INDICATOR_SUPPLIER_YEAR_TIV_DELIVERED,
    SIPRI_ARMS_TRANSFERS_INDICATOR_RECIPIENT_YEAR_TIV_DELIVERED,
)

# Canonical required CSV columns. The cached SIPRI Trade Register
# CSV carries a documented set of columns; the clean adapter
# validates the header against this set and refuses to emit any
# observations when a required column is missing (a missing
# required column is a schema contract violation -- the transform
# layer MUST NOT silently emit partial output on a schema
# violation). Column names match the canonical SIPRI Trade
# Register header (verified 2026-06-27 against the documented
# SIPRI app export shape).
SIPRI_ARMS_TRANSFERS_REQUIRED_COLUMNS: tuple[str, ...] = (
    "Supplier",
    "Recipient",
    "Order year",
    "Delivery year",
    "Designation",
    "Status",
    "Numbers delivered",
    "TIV (delivered)",
)

# Optional CSV columns. These are preserved on the parsed row
# payload and propagated onto the observation's ``extension``
# field so audit code can recover the original cell, but their
# absence is NOT a schema contract violation (the cached bundle
# may legitimately omit the optional columns without breaking
# per-row emission).
SIPRI_ARMS_TRANSFERS_OPTIONAL_COLUMNS: tuple[str, ...] = (
    "Order date",
    "Delivery date",
    "Description",
    "Weapon category",
    "Numbers ordered",
    "TIV (ordered)",
    "Comments",
)

# Asset id template for the canonical raw CSV / JSON cached
# bundle. The asset id is ``<source_key>:<file_name>`` per the
# convention used by the SIPRI Milex / SIPRI Yearbook Ch.7 /
# WGI / WDI / V-Dem / UCDP / CPI / PWT adapters.
SIPRI_ARMS_TRANSFERS_CSV_ASSET_ID: str = (
    f"{SIPRI_ARMS_TRANSFERS_SOURCE_KEY}:{SIPRI_ARMS_TRANSFERS_CSV_NAME}"
)
SIPRI_ARMS_TRANSFERS_JSON_ASSET_ID: str = (
    f"{SIPRI_ARMS_TRANSFERS_SOURCE_KEY}:{SIPRI_ARMS_TRANSFERS_JSON_NAME}"
)

# Structured readiness warning codes. The codes are surfaced as
# ``SourceWarning(severity='error')`` / ``'warning'`` payloads
# so the runner / CLI can dispatch on the code.
SIPRI_ARMS_TRANSFERS_LOCAL_FILES_INVALID: str = (
    "sipri_arms_transfers_local_files_invalid"
)
SIPRI_ARMS_TRANSFERS_METADATA_VERSION_MISMATCH: str = (
    "sipri_arms_transfers_metadata_version_mismatch"
)
SIPRI_ARMS_TRANSFERS_CHECKSUM_MISMATCH: str = (
    "sipri_arms_transfers_checksum_mismatch"
)
SIPRI_ARMS_TRANSFERS_SCHEMA_ERROR: str = (
    "sipri_arms_transfers_schema_error"
)
SIPRI_ARMS_TRANSFERS_PREAMBLE_NOT_FOUND: str = (
    "sipri_arms_transfers_preamble_not_found"
)
SIPRI_ARMS_TRANSFERS_UNSUPPORTED_VERSION: str = "unsupported_version"
SIPRI_ARMS_TRANSFERS_UNSUPPORTED_CACHE_POLICY: str = (
    "unsupported_cache_policy"
)

# Transform name + scale + unit. The unified TIV values are
# preserved on the ``unit`` / ``scale`` fields so downstream
# scorers can read the raw numeric value without re-parsing
# the extension payload.
SIPRI_ARMS_TRANSFERS_TRANSFORM_NAME: str = (
    "sipri_arms_transfers_trade_register_v1"
)
SIPRI_ARMS_TRANSFERS_TIV_UNIT: str = "TIV (SIPRI Trend Indicator Value)"
SIPRI_ARMS_TRANSFERS_TIV_SCALE: str = "sipri_tiv_units"
SIPRI_ARMS_TRANSFERS_NUMBER_UNIT: str = "weapons_delivered"
SIPRI_ARMS_TRANSFERS_NUMBER_SCALE: str = "count"


__all__ = [
    "SIPRI_ARMS_TRANSFERS_ATTRIBUTION_KEY",
    "SIPRI_ARMS_TRANSFERS_ATTRIBUTION_TEXT",
    "SIPRI_ARMS_TRANSFERS_CHECKSUM_MISMATCH",
    "SIPRI_ARMS_TRANSFERS_COVERAGE_END_YEAR",
    "SIPRI_ARMS_TRANSFERS_COVERAGE_START_YEAR",
    "SIPRI_ARMS_TRANSFERS_CSV_ASSET_ID",
    "SIPRI_ARMS_TRANSFERS_CSV_NAME",
    "SIPRI_ARMS_TRANSFERS_DEFAULT_CACHE_POLICY",
    "SIPRI_ARMS_TRANSFERS_DEFAULT_VERSION",
    "SIPRI_ARMS_TRANSFERS_HOMEPAGE_URL",
    "SIPRI_ARMS_TRANSFERS_INDICATOR_CODES",
    "SIPRI_ARMS_TRANSFERS_INDICATOR_NUMBER_DELIVERED",
    "SIPRI_ARMS_TRANSFERS_INDICATOR_RECIPIENT_YEAR_TIV_DELIVERED",
    "SIPRI_ARMS_TRANSFERS_INDICATOR_SUPPLIER_YEAR_TIV_DELIVERED",
    "SIPRI_ARMS_TRANSFERS_INDICATOR_TIV_DELIVERED",
    "SIPRI_ARMS_TRANSFERS_INDICATOR_TIV_ORDERED",
    "SIPRI_ARMS_TRANSFERS_JSON_ASSET_ID",
    "SIPRI_ARMS_TRANSFERS_JSON_NAME",
    "SIPRI_ARMS_TRANSFERS_LOCAL_FILES_INVALID",
    "SIPRI_ARMS_TRANSFERS_LOCAL_FILE_NAMES",
    "SIPRI_ARMS_TRANSFERS_METADATA_NAME",
    "SIPRI_ARMS_TRANSFERS_METADATA_VERSION_MISMATCH",
    "SIPRI_ARMS_TRANSFERS_NUMBER_SCALE",
    "SIPRI_ARMS_TRANSFERS_NUMBER_UNIT",
    "SIPRI_ARMS_TRANSFERS_OBSERVATION_FAMILY_AGGREGATE",
    "SIPRI_ARMS_TRANSFERS_OBSERVATION_FAMILY_REGISTER",
    "SIPRI_ARMS_TRANSFERS_OPTIONAL_COLUMNS",
    "SIPRI_ARMS_TRANSFERS_PREAMBLE_NOT_FOUND",
    "SIPRI_ARMS_TRANSFERS_PUBLIC_APP_URL",
    "SIPRI_ARMS_TRANSFERS_REQUIRED_COLUMNS",
    "SIPRI_ARMS_TRANSFERS_SCHEMA_ERROR",
    "SIPRI_ARMS_TRANSFERS_SOURCE_KEY",
    "SIPRI_ARMS_TRANSFERS_SUPPORTED_FAMILIES",
    "SIPRI_ARMS_TRANSFERS_TIV_SCALE",
    "SIPRI_ARMS_TRANSFERS_TIV_UNIT",
    "SIPRI_ARMS_TRANSFERS_TRANSFORM_NAME",
    "SIPRI_ARMS_TRANSFERS_UNSUPPORTED_CACHE_POLICY",
    "SIPRI_ARMS_TRANSFERS_UNSUPPORTED_VERSION",
]


# The default cache policy for the unified adapter. ``offline_only``
# is the documented safe default: the SIPRI Arms Transfers
# adapter is API-backed (the SIPRI public app returns the Trade
# Register export) but the unified adapter in this slice is
# offline-only -- the readiness gate blocks unsupported cache
# policies with a structured ``unsupported_cache_policy`` error.
SIPRI_ARMS_TRANSFERS_DEFAULT_CACHE_POLICY: str = "offline_only"
