"""Canonical constants for the clean CTBTO Treaty Status adapter.

The CTBTO signature / ratification page
(``https://www.ctbto.org/our-mission/states-signatories``) is the
CTBTO-maintained public record of which States have signed and
ratified the Comprehensive Nuclear-Test-Ban Treaty (CTBT). The
public page exposes a table with documented columns ``Region`` /
``State`` / ``Signature Date`` / ``Ratification Date`` and reports
cumulative totals (e.g. 196 total States, 187 signed, 178 ratified
on the canonical 2024-03-13 probe -- latest signatory Somalia
2023-09-08; latest ratifying state Papua New Guinea 2024-03-13).

This module owns the static source metadata the adapter exposes:
the canonical slug, default version, attribution text, homepage
URL, observation family, coverage envelope, the supported raw
file names (cached CSV / HTML exports), the schema-contract
column names, the indicator codes the adapter emits, and the
structured readiness warning codes.

Source hygiene
--------------

- ``source_type="document"`` because the CTBTO States Signatories
  page is delivered as a public HTML table (the canonical source)
  AND because users typically stage a cached CSV export derived
  from that table for offline ingestion. The descriptor's
  ``coverage_hint.notes`` documents BOTH the canonical HTML page
  and the cached CSV export; the canonical raw file name is
  ``states-signatories.csv`` and the optional HTML fallback is
  ``states-signatories.html``.
- ``requires_network=False`` -- the unified adapter never invokes
  the network; live fetch is intentionally NOT supported in this
  slice (the task brief: "Do NOT implement live
  download/scraping. Build an offline/cache-first adapter"). The
  cache-policy gate blocks ``"refresh"`` / ``"no_cache"`` with a
  structured ``ctbto_treaty_status_unsupported_cache_policy``
  error so the runner refuses to dispatch ``read_raw`` /
  ``transform`` rather than silently surfacing an HTTP-fetched
  payload.

Coverage envelope
-----------------

The CTBTO treaty-status table is a **single-point status
snapshot** -- it reports the signature / ratification status of
each State as of the snapshot date the canonical HTML page
reports. The descriptor advertises a single-year envelope
(``start_year == end_year == CTBTO_TREATY_STATUS_COVERAGE_YEAR``,
the canonical snapshot year). The readiness gate surfaces a
structured ``YEAR_ABSENT`` warning on out-of-coverage year
requests so the runner never silently proxies an out-of-coverage
year to the nearest in-coverage year (SRC-COV-002 / SRC-COV-003).

Observation-family shape
------------------------

The descriptor advertises a single observation family
(``nuclear_treaty_status_country``) so downstream query code
can filter by family without consulting the per-source catalog.
Each cached row in the CTBTO table produces one observation per
catalog indicator. The default catalog carries 2 source-native
indicators, one per date-bearing column of the canonical CTBTO
table:

- ``ctbto_treaty_status_signature_status`` -- the source-derived
  signature status: ``"signed"`` iff a signature date is present
  in the cached row, ``"not_signed"`` otherwise. The adapter
  NEVER invents a signature status from empty / blank date
  cells -- an empty signature date cell is treated as
  ``"not_signed"`` per the canonical CTBTO page semantics.
- ``ctbto_treaty_status_ratification_status`` -- the source-
  derived ratification status: ``"ratified"`` iff a ratification
  date is present in the cached row, ``"not_ratified"``
  otherwise. The adapter NEVER invents a ratification status
  from empty / blank date cells.
- ``ctbto_treaty_status_annex_2_status`` -- NOT part of the
  default indicator tuple. It is ONLY emitted when the
  cached fixture / source-native data carries an explicit Annex 2
  flag; the canonical CTBTO States Signatories page does NOT
  carry an Annex 2 flag column, so the indicator is omitted
  from the default catalog. The adapter NEVER invents an Annex 2
  flag from missing source-native data.

The catalog deliberately carries ONLY source-native status
indicators derived from the 2 date-bearing columns (signature /
ratification) plus the optional Annex 2 indicator when the
source-native data carries it. The adapter does NOT carry
indicators like ``ctbto_treaty_status_signed_year`` /
``ctbto_treaty_status_ratified_year`` (the signature / ratification
date strings are preserved verbatim on the audit-trail extension
payload instead, so downstream code can recover them without
inventing numeric-year coercion that could mislead Stage 11
confidence calculations).

The 2-indicator default catalog is preserved on
:data:`CTBTO_TREATY_STATUS_INDICATOR_CODES` so downstream query
code can filter by indicator without consulting the per-source
catalog; Annex 2 remains a dynamic observation path only when an
explicit source-native column exists.

Attribution
-----------

The CTBTO terms-of-use
(``https://www.ctbto.org/terms-of-use``) permit users to visit,
download and copy CTBTO materials subject to terms; personal,
non-commercial, research / teaching use is permitted with
acknowledgement; no resale, redistribution, or derivative
compilation without permission; the "designations" caveat
preserves the CTBTO's neutral diplomatic nomenclature. The
unified ``CTBTO_TREATY_STATUS_ATTRIBUTION_TEXT`` constant is
byte-identical to the ``ctbto_treaty_status`` section in
``docs/sources/attributions.md`` (Always-On Rule #15). The
:func:`test_ctbto_treaty_status_attribution_text_matches_attributions_doc`
drift guard enforces byte-identity.

Legal caveat
------------

CTBTO signature / ratification status is a TREATY-STATUS
observation, NOT direct proof of nuclear behaviour, compliance,
or non-compliance. The descriptor's ``coverage_hint.notes``
carries the explicit caveat. Downstream scorers MUST NOT
silently treat an unsigned / unratified status cell as proof
of nuclear activity or non-cooperation; the Stage 11 confidence
formula penalises the temporal-fit gap between the cached
snapshot date and the prototype's target year (2023). The
adapter does NOT infer compliance, nuclear behaviour, or
weaponisation from the signature / ratification status.
"""

from __future__ import annotations

# Canonical slug. The data-lake folder is ``ctbto_treaty_status/``
# (the slug is the folder name; no source-key / folder-alias
# reconciliation is needed). The descriptor's ``source_id.slug``
# is ``"ctbto_treaty_status"``.
CTBTO_TREATY_STATUS_SOURCE_KEY: str = "ctbto_treaty_status"

# Canonical metadata + raw file names. ``metadata.json`` is the
# runtime-local bundle metadata (gitignored per Always-On Rule
# #9). The canonical raw CSV name is ``states-signatories.csv``
# (matches the canonical CTBTO page slug); the optional HTML
# fallback name is ``states-signatories.html``.
CTBTO_TREATY_STATUS_METADATA_NAME: str = "metadata.json"
CTBTO_TREATY_STATUS_CSV_NAME: str = "states-signatories.csv"
CTBTO_TREATY_STATUS_HTML_NAME: str = "states-signatories.html"
CTBTO_TREATY_STATUS_LOCAL_FILE_NAMES: tuple[str, ...] = (
    CTBTO_TREATY_STATUS_CSV_NAME,
    CTBTO_TREATY_STATUS_HTML_NAME,
)

# Canonical default version stamp. The CTBTO States Signatories
# page is a single-point status snapshot; the canonical probed
# stamp is "as of 13 March 2024" (the date of the latest
# ratifying state Papua New Guinea). The descriptor advertises
# the canonical stamp; the staged metadata's ``source_version``
# field must match this stamp byte-for-byte for readiness to
# pass. The descriptor's default version propagates consistently
# to ``RawAsset.version`` and every emitted
# ``NormalizedObservation.source_version``.
CTBTO_TREATY_STATUS_DEFAULT_VERSION: str = (
    "CTBTO States Signatories, status as of 2024-03-13"
)

# Canonical snapshot year. The CTBTO States Signatories page is
# a single-point treaty-status snapshot; the canonical probed
# stamp is 2024-03-13 (the date of the latest ratifying state
# Papua New Guinea). The descriptor advertises a single-year
# envelope (``start_year == end_year == 2024``) so downstream
# query code can refuse to dispatch out-of-coverage year
# requests. The readiness envelope surfaces a structured
# ``YEAR_ABSENT`` warning on out-of-coverage year requests
# (e.g. ``years=(2023,)`` -- the prototype's target year --
# falls outside the envelope) so the runner never silently
# proxies an out-of-coverage year to the nearest in-coverage
# year (SRC-COV-002 / SRC-COV-003).
CTBTO_TREATY_STATUS_COVERAGE_YEAR: int = 2024

# Canonical coverage envelope -- a single-year treaty-status
# snapshot. Per the canonical probed stamp
# ("status as of 13 March 2024") the descriptor advertises
# ``start_year == end_year == 2024``. The readiness envelope
# surfaces a structured ``YEAR_ABSENT`` warning on
# out-of-coverage year requests so the runner never silently
# proxies an out-of-coverage year to the nearest in-coverage
# year (SRC-COV-002 / SRC-COV-003).
CTBTO_TREATY_STATUS_COVERAGE_START_YEAR: int = (
    CTBTO_TREATY_STATUS_COVERAGE_YEAR
)
CTBTO_TREATY_STATUS_COVERAGE_END_YEAR: int = (
    CTBTO_TREATY_STATUS_COVERAGE_YEAR
)

# Canonical snapshot date. The CTBTO States Signatories page
# carries a single "status as of" date; the canonical probed
# stamp is 2024-03-13 (the date of the latest ratifying state
# Papua New Guinea). The descriptor's coverage_hint.notes
# advertises this date as the canonical coverage-envelope
# snapshot stamp.
CTBTO_TREATY_STATUS_SNAPSHOT_DATE: str = "2024-03-13"

# Canonical homepage URL -- the CTBTO States Signatories
# landing page (the public source-of-truth page).
CTBTO_TREATY_STATUS_HOMEPAGE_URL: str = (
    "https://www.ctbto.org/our-mission/states-signatories"
)

# Canonical terms-of-use URL -- the CTBTO terms-of-use page that
# governs how the unified adapter may use the cached CTBTO
# material. The terms permit personal, non-commercial, research
# / teaching use with acknowledgement; do not redistribute
# copied full table in outputs.
CTBTO_TREATY_STATUS_TERMS_URL: str = "https://www.ctbto.org/terms-of-use"

# Canonical attribution key + text. The text is byte-identical
# to the ``ctbto_treaty_status`` section in
# ``docs/sources/attributions.md`` (Always-On Rule #15). The
# CTBTO terms-of-use permit download / copy / use with
# acknowledgement for personal, non-commercial, research /
# teaching use; do not redistribute copied full table in
# outputs; attribution required.
CTBTO_TREATY_STATUS_ATTRIBUTION_KEY: str = "ctbto_treaty_status"
CTBTO_TREATY_STATUS_ATTRIBUTION_TEXT: str = (
    "CTBTO States Signatories, Comprehensive Nuclear-Test-Ban "
    "Treaty signature and ratification status (Comprehensive "
    "Nuclear-Test-Ban Treaty Organization, status as of "
    "13 March 2024)."
)

# Single observation family. The descriptor advertises this
# single family so downstream query code can filter by
# ``observation_family == "nuclear_treaty_status_country"``
# without consulting the per-source catalog.
CTBTO_TREATY_STATUS_OBSERVATION_FAMILY: str = (
    "nuclear_treaty_status_country"
)
CTBTO_TREATY_STATUS_SUPPORTED_FAMILIES: tuple[str, ...] = (
    CTBTO_TREATY_STATUS_OBSERVATION_FAMILY,
)

# 2 catalog indicators (default) -- the source-derived signature
# and ratification status flags. The signature status is
# ``"signed"`` iff a signature date is present in the cached
# row, ``"not_signed"`` otherwise. The ratification status is
# ``"ratified"`` iff a ratification date is present in the cached
# row, ``"not_ratified"`` otherwise. The adapter NEVER invents a
# signature / ratification status from empty / blank date cells.
# Per-row emission produces one observation per cached State row
# + indicator (2 observations per row for the default 2-
# indicator catalog).
CTBTO_TREATY_STATUS_INDICATOR_SIGNATURE_STATUS: str = (
    "ctbto_treaty_status_signature_status"
)
CTBTO_TREATY_STATUS_INDICATOR_RATIFICATION_STATUS: str = (
    "ctbto_treaty_status_ratification_status"
)
CTBTO_TREATY_STATUS_INDICATOR_CODES: tuple[str, ...] = (
    CTBTO_TREATY_STATUS_INDICATOR_SIGNATURE_STATUS,
    CTBTO_TREATY_STATUS_INDICATOR_RATIFICATION_STATUS,
)

# Optional Annex 2 indicator. The canonical CTBTO States
# Signatories page does NOT carry an Annex 2 flag column --
# Annex 2 refers to the 44 States that the CTBTO PrepCom
# identified as needing to ratify the CTBT for the Treaty to
# enter into force, but the public table does NOT surface an
# Annex 2 status column. The adapter therefore does NOT emit a
# default ``ctbto_treaty_status_annex_2_status`` indicator in
# the canonical catalog. When the cached fixture / source-native
# data carries an explicit Annex 2 flag column the adapter emits
# one extra observation per row, but the catalog deliberately
# does NOT include the Annex 2 indicator in the default 2-
# indicator catalog so the adapter NEVER invents an Annex 2
# flag from missing source-native data. The constant is preserved
# here for documentation / future-source-data-compatibility
# purposes only.
CTBTO_TREATY_STATUS_INDICATOR_ANNEX_2_STATUS: str = (
    "ctbto_treaty_status_annex_2_status"
)

# Canonical status sentinels emitted by the transform layer.
# ``"signed"`` and ``"ratified"`` are emitted when the
# corresponding date cell is non-empty in the cached row;
# ``"not_signed"`` and ``"not_ratified"`` are emitted when the
# date cell is empty / blank. The transform layer NEVER emits
# the literal string ``""`` or the SQL ``NULL`` value -- the
# explicit sentinel preserves the source-native semantics on
# the audit trail.
CTBTO_TREATY_STATUS_STATUS_SIGNED: str = "signed"
CTBTO_TREATY_STATUS_STATUS_NOT_SIGNED: str = "not_signed"
CTBTO_TREATY_STATUS_STATUS_RATIFIED: str = "ratified"
CTBTO_TREATY_STATUS_STATUS_NOT_RATIFIED: str = "not_ratified"

# Canonical required CSV / HTML columns. The cached CTBTO
# States Signatories CSV (derived from the canonical public
# HTML table) carries a documented set of columns; the clean
# adapter validates the parsed header against this set and
# refuses to emit any observations when a required column is
# missing. Column names match the canonical CTBTO public table
# layout (verified 2026-06-28 against the documented public
# page header). The 4 canonical columns mirror the canonical
# CTBTO page: ``Region`` / ``State`` / ``Signature Date`` /
# ``Ratification Date``. The 5th column ``Annex 2`` is OPTIONAL
# -- the canonical CTBTO page does NOT carry an Annex 2 flag,
# but the parser tolerates it when present in the cached
# fixture (the transform layer then emits a per-row
# ``ctbto_treaty_status_annex_2_status`` observation in
# addition to the default 2-indicator catalog).
CTBTO_TREATY_STATUS_REQUIRED_COLUMNS: tuple[str, ...] = (
    "Region",
    "State",
    "Signature Date",
    "Ratification Date",
)

# Optional Annex 2 column. The canonical CTBTO public page
# does NOT carry an Annex 2 flag column; when a cached fixture
# (or future user-staged export) carries an Annex 2 column the
# transform layer treats the column as a source-native optional
# indicator and emits a per-row
# ``ctbto_treaty_status_annex_2_status`` observation in
# addition to the default 2-indicator catalog. The column name
# is preserved as a constant so future fixture authors can
# reference the canonical Annex 2 column name.
CTBTO_TREATY_STATUS_OPTIONAL_ANNEX_2_COLUMN: str = "Annex 2"

# Asset id templates for the canonical raw CSV / HTML cached
# bundle. The asset id follows the canonical
# ``<source_key>:<file_name>`` convention used by the IAEA
# Safeguards / SIPRI Arms Transfers / Polity V / FAS / PWT /
# SIPRI Milex adapters.
CTBTO_TREATY_STATUS_CSV_ASSET_ID: str = (
    f"{CTBTO_TREATY_STATUS_SOURCE_KEY}:{CTBTO_TREATY_STATUS_CSV_NAME}"
)
CTBTO_TREATY_STATUS_HTML_ASSET_ID: str = (
    f"{CTBTO_TREATY_STATUS_SOURCE_KEY}:{CTBTO_TREATY_STATUS_HTML_NAME}"
)

# Structured readiness warning codes. The codes are surfaced as
# ``SourceWarning(severity='error')`` / ``'warning'`` payloads
# so the runner / CLI can dispatch on the code.
CTBTO_TREATY_STATUS_LOCAL_FILES_INVALID: str = (
    "ctbto_treaty_status_local_files_invalid"
)
CTBTO_TREATY_STATUS_METADATA_VERSION_MISMATCH: str = (
    "ctbto_treaty_status_metadata_version_mismatch"
)
CTBTO_TREATY_STATUS_CHECKSUM_MISMATCH: str = (
    "ctbto_treaty_status_checksum_mismatch"
)
CTBTO_TREATY_STATUS_SCHEMA_ERROR: str = (
    "ctbto_treaty_status_schema_error"
)
CTBTO_TREATY_STATUS_UNSUPPORTED_VERSION: str = "unsupported_version"
CTBTO_TREATY_STATUS_UNSUPPORTED_CACHE_POLICY: str = (
    "ctbto_treaty_status_unsupported_cache_policy"
)

# Transform name + scale + unit. The unified status-flag values
# are preserved on the ``unit`` / ``scale`` fields so downstream
# scorers can read the source-derived status sentinel without
# re-parsing the extension payload.
CTBTO_TREATY_STATUS_TRANSFORM_NAME: str = (
    "ctbto_treaty_status_signature_ratification_v1"
)
CTBTO_TREATY_STATUS_STATUS_UNIT: str = "ctbto_treaty_status_label"
CTBTO_TREATY_STATUS_STATUS_SCALE: str = "source_derived_status_label"


# The default cache policy for the unified adapter. The CTBTO
# treaty status adapter is offline / cache-only in this slice
# (the cached CTBTO States Signatories export is the source of
# truth; live fetch is intentionally NOT supported). The
# readiness gate blocks unsupported policies (``"refresh"`` /
# ``"no_cache"``) with a structured
# ``ctbto_treaty_status_unsupported_cache_policy`` error
# (``CTBTO_TREATY_STATUS_UNSUPPORTED_CACHE_POLICY`` constant).
CTBTO_TREATY_STATUS_DEFAULT_CACHE_POLICY: str = "offline_only"


__all__ = [
    "CTBTO_TREATY_STATUS_ATTRIBUTION_KEY",
    "CTBTO_TREATY_STATUS_ATTRIBUTION_TEXT",
    "CTBTO_TREATY_STATUS_CHECKSUM_MISMATCH",
    "CTBTO_TREATY_STATUS_COVERAGE_END_YEAR",
    "CTBTO_TREATY_STATUS_COVERAGE_START_YEAR",
    "CTBTO_TREATY_STATUS_COVERAGE_YEAR",
    "CTBTO_TREATY_STATUS_CSV_ASSET_ID",
    "CTBTO_TREATY_STATUS_CSV_NAME",
    "CTBTO_TREATY_STATUS_DEFAULT_CACHE_POLICY",
    "CTBTO_TREATY_STATUS_DEFAULT_VERSION",
    "CTBTO_TREATY_STATUS_HOMEPAGE_URL",
    "CTBTO_TREATY_STATUS_HTML_ASSET_ID",
    "CTBTO_TREATY_STATUS_HTML_NAME",
    "CTBTO_TREATY_STATUS_INDICATOR_ANNEX_2_STATUS",
    "CTBTO_TREATY_STATUS_INDICATOR_CODES",
    "CTBTO_TREATY_STATUS_INDICATOR_RATIFICATION_STATUS",
    "CTBTO_TREATY_STATUS_INDICATOR_SIGNATURE_STATUS",
    "CTBTO_TREATY_STATUS_LOCAL_FILES_INVALID",
    "CTBTO_TREATY_STATUS_LOCAL_FILE_NAMES",
    "CTBTO_TREATY_STATUS_METADATA_NAME",
    "CTBTO_TREATY_STATUS_METADATA_VERSION_MISMATCH",
    "CTBTO_TREATY_STATUS_OBSERVATION_FAMILY",
    "CTBTO_TREATY_STATUS_OPTIONAL_ANNEX_2_COLUMN",
    "CTBTO_TREATY_STATUS_REQUIRED_COLUMNS",
    "CTBTO_TREATY_STATUS_SCHEMA_ERROR",
    "CTBTO_TREATY_STATUS_SNAPSHOT_DATE",
    "CTBTO_TREATY_STATUS_SOURCE_KEY",
    "CTBTO_TREATY_STATUS_STATUS_NOT_RATIFIED",
    "CTBTO_TREATY_STATUS_STATUS_NOT_SIGNED",
    "CTBTO_TREATY_STATUS_STATUS_RATIFIED",
    "CTBTO_TREATY_STATUS_STATUS_SCALE",
    "CTBTO_TREATY_STATUS_STATUS_SIGNED",
    "CTBTO_TREATY_STATUS_STATUS_UNIT",
    "CTBTO_TREATY_STATUS_SUPPORTED_FAMILIES",
    "CTBTO_TREATY_STATUS_TERMS_URL",
    "CTBTO_TREATY_STATUS_TRANSFORM_NAME",
    "CTBTO_TREATY_STATUS_UNSUPPORTED_CACHE_POLICY",
    "CTBTO_TREATY_STATUS_UNSUPPORTED_VERSION",
]
