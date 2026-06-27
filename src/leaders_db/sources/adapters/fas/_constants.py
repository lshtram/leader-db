"""Constants for the clean FAS Nuclear Notebook source adapter.

The FAS (Federation of American Scientists) Nuclear Notebook is the
second source for the ``nuclear`` rating category in the prototype,
complementing the SIPRI Yearbook Ch.7 PDF source. The FAS public
"Status of World Nuclear Forces" page
(``https://programs.fas.org/ssp/nukes/nuclearweapons/nukestatus.html``)
is a single parseable HTML table with the 9 nuclear-armed states and
5 numeric columns (Operational Strategic, Operational Nonstrategic,
Reserve/Nondeployed, Military Stockpile, Total Inventory). The page
is updated "continuously" per FAS but the consolidated snapshot is
dated 2014-04-30 per the page's ``<meta name="date">`` element and
the table footer "Current update: April 30, 2014".

The clean adapter reads the staged local HTML cache
(``<raw_root>/fas/fas_status.html``) through lazy legacy parser
imports inside the raw-read function. The legacy HTTP fetch path is
intentionally NEVER invoked by the unified adapter (the readiness
gate and the cache-only read path both refuse to fall through to the
network). The unified adapter is local-file only.

Snapshot-year semantics
-----------------------

The FAS consolidated status page is a single-snapshot source. The
clean adapter parses the snapshot year from the page's
``<meta name="date">`` element (falling back to the footer "Current
update" text and finally the conservative default). The snapshot year
is recorded on every observation's ``extension.snapshot_year`` field
plus the ``year`` field is set to the parsed snapshot year
(``2014`` for the live page as of probe 2026-06-19).

A requested 2023 with a 2014 snapshot is preserved by emitting the
2014 rows labeled with ``year=2014`` and an additional
``requested_year=2023`` / ``snapshot_year=2014`` /
``proxy_snapshot_semantics`` audit metadata on every observation. The
readiness gate surfaces a structured ``YEAR_ABSENT`` warning so the
caller can branch on the temporal-fit gap without relabeling rows as
2023 (no silent stale-proxy fill per SRC-COV-002 / SRC-COV-003).
"""

from __future__ import annotations

# Source identity
FAS_SOURCE_KEY = "fas"
FAS_ATTRIBUTION_KEY = "fas"
FAS_DEFAULT_VERSION = "consolidated status table"

# Canonical FAS consolidated status page URL (the URL the page was
# fetched from per the staged ``data/raw/fas/metadata.json`` /
# ``docs/sources/registry.md``). The HTML cache is named
# ``fas_status.html`` to mirror the legacy cache convention.
FAS_STATUS_PAGE_URL = (
    "https://programs.fas.org/ssp/nukes/nuclearweapons/nukestatus.html"
)
FAS_PUBLISHER_URL = "https://fas.org/issues/nuclear-weapons/"
FAS_HOMEPAGE_URL = FAS_PUBLISHER_URL

# Canonical local HTML cache filename. Mirrors the legacy
# ``fas_status.html`` cache convention under ``data/raw/fas/``.
FAS_HTML_NAME = "fas_status.html"
FAS_HTML_ASSET_ID = f"{FAS_SOURCE_KEY}:{FAS_HTML_NAME}"

# Bundle metadata filename (matches the legacy
# ``data/raw/<source>/metadata.json`` convention).
FAS_METADATA_NAME = "metadata.json"

# Single observation family for the 5 catalog indicators. Matches
# the SIPRI Yearbook Ch.7 ``nuclear_country_year`` family so the
# nuclear rating category can consume both sources through a single
# query. Per ``docs/architecture/sources.md`` §5.8 + §7.1 and
# ``docs/requirements/core.md``, the FAS observations are
# ``nuclear_country_year`` evidence, not leader-month / leader-spell
# or event-level.
FAS_OBSERVATION_FAMILY = "nuclear_country_year"
FAS_SUPPORTED_FAMILIES = (FAS_OBSERVATION_FAMILY,)

# Coverage envelope. The FAS consolidated status page is a single
# snapshot; the ``snapshot_year`` is parsed from the page's
# ``<meta name="date">`` element. The coverage hint advertises the
# snapshot year as both start and end year so downstream code can
# detect out-of-coverage year requests.
#
# The default snapshot year is the legacy ``_DEFAULT_SNAPSHOT_YEAR``
# constant (``2014``) which matches the live page as of probe
# 2026-06-19. The descriptor advertises this default; the actual
# snapshot year is parsed at read time and may differ if FAS updates
# the page in the future.
FAS_SNAPSHOT_YEAR = 2014
FAS_COVERAGE_START_YEAR = FAS_SNAPSHOT_YEAR
FAS_COVERAGE_END_YEAR = FAS_SNAPSHOT_YEAR

# Default cache policy. ``offline_only`` is the documented safe
# default: the FAS unified adapter never invokes the network. The
# HTML cache is the only source of data the unified adapter reads.
FAS_DEFAULT_CACHE_POLICY = "offline_only"

# Canonical FAS attribution text. Byte-identical to the legacy
# ``FAS_ATTRIBUTION`` constant in ``src/leaders_db/ingest/fas_io.py``
# and to the ``fas`` row in ``docs/sources/attributions.md``
# (Always-On Rule #15). The
# ``test_fas_attribution_text_matches_attributions_doc`` test pins
# the byte-identity drift guard.
FAS_ATTRIBUTION_TEXT = (
    "FAS Nuclear Notebook (Federation of American Scientists)."
)

# Transform / readiness codes -- module-local so the readiness
# envelope surfaces them as structured :class:`SourceWarning`
# payloads with the canonical code strings.
FAS_TRANSFORM_NAME = "fas_country_year_v1"
FAS_CHECKSUM_MISMATCH = "fas_checksum_mismatch"
FAS_LOCAL_FILES_INVALID = "fas_local_files_invalid"
FAS_METADATA_VERSION_MISMATCH = "fas_metadata_version_mismatch"
FAS_UNSUPPORTED_VERSION = "unsupported_version"
FAS_UNSUPPORTED_CACHE_POLICY = "unsupported_cache_policy"

# The 5 in-scope indicator variable names from the FAS catalog
# (``src/leaders_db/ingest/catalogs/fas.csv``). The clean adapter
# maps each catalog ``raw_column`` (the FAS HTML table column
# header) to the corresponding ``variable_name``; the raw column
# text is preserved verbatim on every observation's
# ``extension.fas_raw_column`` for the audit trail.
FAS_INDICATORS = (
    "fas_operational_strategic",
    "fas_operational_nonstrategic",
    "fas_reserve_nondeployed",
    "fas_military_stockpile",
    "fas_total_inventory",
)

# Raw column names from the FAS HTML table headers (the consolidated
# "Status of World Nuclear Forces" table). The header rows use
# ``<br>`` to wrap multi-line text; the legacy HTML reader strips
# tags + HTML entities, so the live column text is the post-strip
# string (e.g. ``"Operational Strategic"``).
FAS_RAW_COLUMNS = (
    "Operational Strategic",
    "Operational Nonstrategic",
    "Reserve/Nondeployed",
    "Military Stockpile",
    "Total Inventory",
)

__all__ = [
    "FAS_ATTRIBUTION_KEY",
    "FAS_ATTRIBUTION_TEXT",
    "FAS_CHECKSUM_MISMATCH",
    "FAS_COVERAGE_END_YEAR",
    "FAS_COVERAGE_START_YEAR",
    "FAS_DEFAULT_CACHE_POLICY",
    "FAS_DEFAULT_VERSION",
    "FAS_HOMEPAGE_URL",
    "FAS_HTML_ASSET_ID",
    "FAS_HTML_NAME",
    "FAS_INDICATORS",
    "FAS_LOCAL_FILES_INVALID",
    "FAS_METADATA_NAME",
    "FAS_METADATA_VERSION_MISMATCH",
    "FAS_OBSERVATION_FAMILY",
    "FAS_PUBLISHER_URL",
    "FAS_RAW_COLUMNS",
    "FAS_SNAPSHOT_YEAR",
    "FAS_SOURCE_KEY",
    "FAS_STATUS_PAGE_URL",
    "FAS_SUPPORTED_FAMILIES",
    "FAS_TRANSFORM_NAME",
    "FAS_UNSUPPORTED_CACHE_POLICY",
    "FAS_UNSUPPORTED_VERSION",
]
