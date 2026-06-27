"""Canonical constants for the clean IAEA Safeguards status-list adapter.

The IAEA Safeguards Status List is the public legal/status evidence
the IAEA publishes at
``https://www.iaea.org/sites/default/files/20/01/sg-agreements-comprehensive-status.pdf``
("Conclusion of Safeguards Agreements, Additional Protocols and
Small Quantities Protocols"). The list is updated periodically;
the canonical stamp probed for this slice is the
2025-12-31 status date.

The clean adapter is offline / cache-first: it reads a single
cached PDF plus a runtime-local ``metadata.json`` (gitignored per
Always-On Rule #9). Live fetch is intentionally NOT supported --
the unified adapter never invokes the network; the
``cache_policy='refresh'`` / ``'no_cache'`` policies fail
readiness with a structured
``iaea_safeguards_unsupported_cache_policy`` error so the runner
refuses to dispatch ``read_raw`` / ``transform`` rather than
silently surfacing an HTTP-fetched payload. Per the task brief
this slice intentionally does NOT implement live download /
scraping of the canonical status list.

Scope of evidence
-----------------

This source captures safeguards legal / status observations -- the
country-level presence / status of a Comprehensive Safeguards
Agreement (CSA) cell (the source-native composite label such as
``In Force: 153`` / ``Not in Force: 66`` / ``N/A``), the status
of an Additional Protocol (AP) signed / approved / in force /
not in force / not signed, the status of a Small Quantities
Protocol (SQP) (modified / original / not applicable / not in
force), and the INFCIRC document identifier for the agreement.

This source is NOT a per-country nuclear-weapons score. The status
list captures legal/status evidence and is NOT direct proof of
safeguards compliance or non-compliance. Downstream scorers MUST
NOT silently treat a ``"not in force"`` AP cell as proof of
non-cooperation; the descriptor's ``coverage_hint.notes`` carries
the explicit caveat and the Stage 11 confidence formula penalises
the temporal-fit gap between the cached status date and the
prototype's target year.

Coverage envelope
-----------------

The IAEA Safeguards Status List is a single-point legal/status
snapshot (the canonical probed stamp is 2025-12-31). The adapter
treats the snapshot as a single ``status_date`` rather than a
multi-year envelope; ``CoverageHint.start_year`` /
``CoverageHint.end_year`` are both set to the snapshot year
``2025``. Per the status list's "as of 31 December 2025" stamp,
the descriptor advertises the canonical envelope so downstream
query code can refuse to dispatch out-of-coverage year requests.

Observation-family shape
------------------------

The descriptor advertises a single observation family
(``nuclear_safeguards_status_country``) so downstream query code
can filter by family without consulting the per-source catalog.
Each cached row in the status list produces one observation per
catalog indicator. The catalog carries 4 source-native
indicators (one per non-State column in the cached PDF table):

- ``iaea_safeguards_safeguards_agreement_status`` -- the
  safeguards-agreement status cell (verbatim source-native label
  preserved on ``extension["iaea_safeguards_safeguards_agreement_status_raw"]``).
- ``iaea_safeguards_infcirc_number`` -- the INFCIRC document
  identifier (text; preserved verbatim on
  ``extension["iaea_safeguards_infcirc_raw"]``).
- ``iaea_safeguards_additional_protocol_status`` -- the AP
  status cell (verbatim source-native label preserved on
  ``extension["iaea_safeguards_additional_protocol_status_raw"]``).
- ``iaea_safeguards_small_quantities_protocol_status`` -- the
  SQP status cell.

The catalog exactly mirrors the 4 non-State columns in the
source-native PDF table -- the adapter does NOT invent a
separate ``safeguards_agreement_type`` indicator (the canonical
IAEA table carries a single ``Safeguards Agreement`` column
that holds the composite status label, not a separate type
column).

The 4-indicator catalog is preserved on
:data:`IAEA_SAFEGUARDS_INDICATOR_CODES` so downstream query code
can filter by indicator without consulting the per-source catalog.

Attribution
-----------

The unified ``IAEA_SAFEGUARDS_ATTRIBUTION_TEXT`` constant is
byte-identical to the ``iaea_safeguards`` section in
``docs/sources/attributions.md`` (Always-On Rule #15). The
:func:`test_iaea_safeguards_attribution_text_matches_attributions_doc`
drift guard enforces byte-identity.

Source hygiene
--------------

- ``source_type="document"`` because the source is a public PDF
  status list. The unified adapter is offline / cache-only in
  this slice (``requires_network=False``); the readiness gate
  blocks ``cache_policy="refresh"`` / ``"no_cache"`` with a
  structured ``unsupported_cache_policy`` error.

- The clean adapter does NOT invent ISO3 country codes -- the
  cached status list uses IAEA's own country display names,
  which are NOT ISO3. ``country_code`` remains ``None`` until
  later matching / resolution stages introduce a canonical ISO3
  mapping.
"""

from __future__ import annotations

# Canonical slug. The data-lake folder is ``iaea_safeguards/``
# (the slug is the folder name; no source-key / folder-alias
# reconciliation is needed). The descriptor's ``source_id.slug``
# is ``"iaea_safeguards"``.
IAEA_SAFEGUARDS_SOURCE_KEY: str = "iaea_safeguards"

# Canonical metadata + raw file names. ``metadata.json`` is the
# runtime-local bundle metadata (gitignored per Always-On Rule #9).
# The canonical raw PDF name matches the IAEA public filename
# pattern (``sg-agreements-comprehensive-status.pdf``).
IAEA_SAFEGUARDS_METADATA_NAME: str = "metadata.json"
IAEA_SAFEGUARDS_PDF_NAME: str = "sg-agreements-comprehensive-status.pdf"

# Canonical default version stamp. The cached bundle metadata
# MUST carry this stamp byte-for-byte under ``source_version``.
# The version encodes the canonical status date (the IAEA status
# list is a single-point legal snapshot, not a multi-year time
# series), so the stamp includes the date in ISO form.
IAEA_SAFEGUARDS_DEFAULT_VERSION: str = (
    "IAEA Safeguards Status List, status as of 2025-12-31"
)

# Canonical status date. The IAEA safeguards status list carries
# a single "status as of" date (the canonical probed date is
# 2025-12-31). The descriptor advertises this date as both the
# coverage-envelope start and end year (the snapshot is a
# single-point legal observation, NOT a multi-year time series).
IAEA_SAFEGUARDS_STATUS_DATE: str = "2025-12-31"
IAEA_SAFEGUARDS_COVERAGE_YEAR: int = 2025

# Canonical coverage envelope -- a single-year legal/status
# snapshot. Per the IAEA status list's "as of 31 December 2025"
# stamp the descriptor advertises ``start_year == end_year ==
# 2025``. The readiness envelope surfaces a structured
# ``YEAR_ABSENT`` warning on out-of-coverage year requests so the
# runner never silently proxies an out-of-coverage year to the
# nearest in-coverage year (SRC-COV-002 / SRC-COV-003).
IAEA_SAFEGUARDS_COVERAGE_START_YEAR: int = IAEA_SAFEGUARDS_COVERAGE_YEAR
IAEA_SAFEGUARDS_COVERAGE_END_YEAR: int = IAEA_SAFEGUARDS_COVERAGE_YEAR

# Canonical homepage URL (the IAEA safeguards-agreements topic
# page -- the public landing page, NOT the direct PDF URL).
IAEA_SAFEGUARDS_HOMEPAGE_URL: str = (
    "https://www.iaea.org/topics/safeguards-agreements"
)

# Canonical direct PDF URL for provenance / attribution only --
# the clean adapter in this slice does NOT invoke the URL at
# runtime; it is preserved here as the canonical provenance
# reference so downstream operators / audits can locate the
# canonical IAEA status list. Live fetch is intentionally NOT
# supported in this slice.
IAEA_SAFEGUARDS_PDF_URL: str = (
    "https://www.iaea.org/sites/default/files/20/01/"
    "sg-agreements-comprehensive-status.pdf"
)

# Canonical attribution key + text. The text is byte-identical
# to the ``iaea_safeguards`` section in
# ``docs/sources/attributions.md`` (Always-On Rule #15). The
# IAEA permits download / copy / use of its published material
# with acknowledgement for research / private study / commercial
# / non-commercial use subject to restrictions; the pipeline
# does NOT redistribute the full PDF in public outputs.
IAEA_SAFEGUARDS_ATTRIBUTION_KEY: str = "iaea_safeguards"
IAEA_SAFEGUARDS_ATTRIBUTION_TEXT: str = (
    "IAEA Safeguards Status List, Conclusion of Safeguards "
    "Agreements, Additional Protocols and Small Quantities "
    "Protocols (International Atomic Energy Agency, status as "
    "of 31 December 2025)."
)

# Single observation family. The descriptor advertises this
# single family so downstream query code can filter by
# ``observation_family == "nuclear_safeguards_status_country"``
# without consulting the per-source catalog.
IAEA_SAFEGUARDS_OBSERVATION_FAMILY: str = (
    "nuclear_safeguards_status_country"
)
IAEA_SAFEGUARDS_SUPPORTED_FAMILIES: tuple[str, ...] = (
    IAEA_SAFEGUARDS_OBSERVATION_FAMILY,
)

# 4 catalog indicators -- one per non-State column in the
# canonical IAEA Safeguards Status List (safeguards-agreement
# status, INFCIRC number, additional-protocol status,
# small-quantities-protocol status). Per-row emission produces
# one observation per cached country row + indicator. The
# catalog deliberately does NOT carry a separate
# ``safeguards_agreement_type`` indicator -- the canonical
# IAEA table has a single ``Safeguards Agreement`` column
# holding the composite status label (e.g. ``In Force: 153``
# / ``Not in Force: 66`` / ``N/A``); there is no separate
# type column in the parsed fixture so the adapter never
# invents one.
IAEA_SAFEGUARDS_INDICATOR_SAFEGUARDS_AGREEMENT_STATUS: str = (
    "iaea_safeguards_safeguards_agreement_status"
)
IAEA_SAFEGUARDS_INDICATOR_ADDITIONAL_PROTOCOL_STATUS: str = (
    "iaea_safeguards_additional_protocol_status"
)
IAEA_SAFEGUARDS_INDICATOR_SMALL_QUANTITIES_PROTOCOL_STATUS: str = (
    "iaea_safeguards_small_quantities_protocol_status"
)
IAEA_SAFEGUARDS_INDICATOR_INFCIRC_NUMBER: str = (
    "iaea_safeguards_infcirc_number"
)
IAEA_SAFEGUARDS_INDICATOR_CODES: tuple[str, ...] = (
    IAEA_SAFEGUARDS_INDICATOR_SAFEGUARDS_AGREEMENT_STATUS,
    IAEA_SAFEGUARDS_INDICATOR_ADDITIONAL_PROTOCOL_STATUS,
    IAEA_SAFEGUARDS_INDICATOR_SMALL_QUANTITIES_PROTOCOL_STATUS,
    IAEA_SAFEGUARDS_INDICATOR_INFCIRC_NUMBER,
)

# Canonical required PDF table columns. The cached status-list
# PDF carries a documented set of columns; the reader validates
# the parsed header against this set and refuses to emit any
# observations when a required column is missing. The five
# canonical columns match the IAEA public status-list layout
# (verified 2026-06-27 against the published document).
IAEA_SAFEGUARDS_REQUIRED_COLUMNS: tuple[str, ...] = (
    "State",
    "Safeguards Agreement",
    "INFCIRC",
    "Additional Protocol",
    "Small Quantities Protocol",
)

# Asset id template for the canonical raw PDF bundle. The
# asset id follows the canonical
# ``<source_key>:<file_name>`` convention used by the
# SIPRI Yearbook Ch.7 / SIPRI Milex / Polity V / FAS /
# PWT adapters.
IAEA_SAFEGUARDS_PDF_ASSET_ID: str = (
    f"{IAEA_SAFEGUARDS_SOURCE_KEY}:{IAEA_SAFEGUARDS_PDF_NAME}"
)

# Structured readiness warning codes. The codes are surfaced
# as ``SourceWarning(severity='error')`` / ``'warning'``
# payloads so the runner / CLI can dispatch on the code.
IAEA_SAFEGUARDS_LOCAL_FILES_INVALID: str = (
    "iaea_safeguards_local_files_invalid"
)
IAEA_SAFEGUARDS_METADATA_VERSION_MISMATCH: str = (
    "iaea_safeguards_metadata_version_mismatch"
)
IAEA_SAFEGUARDS_CHECKSUM_MISMATCH: str = (
    "iaea_safeguards_checksum_mismatch"
)
IAEA_SAFEGUARDS_SCHEMA_ERROR: str = (
    "iaea_safeguards_schema_error"
)
IAEA_SAFEGUARDS_UNSUPPORTED_VERSION: str = "unsupported_version"
IAEA_SAFEGUARDS_UNSUPPORTED_CACHE_POLICY: str = (
    "unsupported_cache_policy"
)

# Transform name + scale + unit. The unified adapter preserves
# the source-native cell labels verbatim on the ``unit`` /
# ``scale`` fields so downstream scorers can read the raw
# source-native value without re-parsing the extension payload.
IAEA_SAFEGUARDS_TRANSFORM_NAME: str = (
    "iaea_safeguards_status_list_v1"
)
IAEA_SAFEGUARDS_TEXT_UNIT: str = "iaea_safeguards_status_label"
IAEA_SAFEGUARDS_TEXT_SCALE: str = "source_native_status_label"
IAEA_SAFEGUARDS_INFCIRC_UNIT: str = "iaea_safeguards_infcirc_id"
IAEA_SAFEGUARDS_INFCIRC_SCALE: str = "iaea_infcirc_number"

# The default cache policy for the unified adapter. The IAEA
# Safeguards adapter is offline / cache-only in this slice
# (the cached status-list PDF is the source of truth; live
# fetch is intentionally NOT supported). The readiness gate
# blocks unsupported policies (``"refresh"`` / ``"no_cache"``)
# with a structured ``unsupported_cache_policy`` error.
IAEA_SAFEGUARDS_DEFAULT_CACHE_POLICY: str = "offline_only"


__all__ = [
    "IAEA_SAFEGUARDS_ATTRIBUTION_KEY",
    "IAEA_SAFEGUARDS_ATTRIBUTION_TEXT",
    "IAEA_SAFEGUARDS_CHECKSUM_MISMATCH",
    "IAEA_SAFEGUARDS_COVERAGE_END_YEAR",
    "IAEA_SAFEGUARDS_COVERAGE_START_YEAR",
    "IAEA_SAFEGUARDS_COVERAGE_YEAR",
    "IAEA_SAFEGUARDS_DEFAULT_CACHE_POLICY",
    "IAEA_SAFEGUARDS_DEFAULT_VERSION",
    "IAEA_SAFEGUARDS_HOMEPAGE_URL",
    "IAEA_SAFEGUARDS_INDICATOR_ADDITIONAL_PROTOCOL_STATUS",
    "IAEA_SAFEGUARDS_INDICATOR_CODES",
    "IAEA_SAFEGUARDS_INDICATOR_INFCIRC_NUMBER",
    "IAEA_SAFEGUARDS_INDICATOR_SAFEGUARDS_AGREEMENT_STATUS",
    "IAEA_SAFEGUARDS_INDICATOR_SMALL_QUANTITIES_PROTOCOL_STATUS",
    "IAEA_SAFEGUARDS_INFCIRC_SCALE",
    "IAEA_SAFEGUARDS_INFCIRC_UNIT",
    "IAEA_SAFEGUARDS_LOCAL_FILES_INVALID",
    "IAEA_SAFEGUARDS_METADATA_NAME",
    "IAEA_SAFEGUARDS_METADATA_VERSION_MISMATCH",
    "IAEA_SAFEGUARDS_OBSERVATION_FAMILY",
    "IAEA_SAFEGUARDS_PDF_ASSET_ID",
    "IAEA_SAFEGUARDS_PDF_NAME",
    "IAEA_SAFEGUARDS_PDF_URL",
    "IAEA_SAFEGUARDS_REQUIRED_COLUMNS",
    "IAEA_SAFEGUARDS_SCHEMA_ERROR",
    "IAEA_SAFEGUARDS_SOURCE_KEY",
    "IAEA_SAFEGUARDS_STATUS_DATE",
    "IAEA_SAFEGUARDS_SUPPORTED_FAMILIES",
    "IAEA_SAFEGUARDS_TEXT_SCALE",
    "IAEA_SAFEGUARDS_TEXT_UNIT",
    "IAEA_SAFEGUARDS_TRANSFORM_NAME",
    "IAEA_SAFEGUARDS_UNSUPPORTED_CACHE_POLICY",
    "IAEA_SAFEGUARDS_UNSUPPORTED_VERSION",
]
