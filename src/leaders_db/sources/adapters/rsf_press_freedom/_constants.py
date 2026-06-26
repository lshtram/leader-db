"""Unified-source Reporters Without Borders (RSF) World
Press Freedom Index constants.

This module owns the static metadata that does not
change between adapter instances. Split out of
:mod:`._descriptor` so the descriptor module stays
focused on the
:func:`build_rsf_press_freedom_descriptor` factory
and respects the documented 400-line convention.

The constants are also re-exported from
:mod:`._descriptor` (and from
:mod:`leaders_db.sources.adapters.rsf_press_freedom`,
the package root) so callers can ``from
leaders_db.sources.adapters.rsf_press_freedom import
RSF_PRESS_FREEDOM_SOURCE_KEY`` without knowing which
submodule the symbol lives in.

Source-type semantics
---------------------

The descriptor advertises ``source_type="dataset"`` per
``docs/architecture/sources.md`` §5.2: the canonical
RSF access path is 24 local annual CSVs staged at
``data/raw/rsf_press_freedom/rsf_press_freedom_<year>.csv``
(2002-2010 + 2012-2026; the direct ``2011.csv`` is
intentionally absent and the 2012 file represents RSF's
combined 2011/2012 edition per
``data/raw/rsf_press_freedom/metadata.json`` +
``docs/sources/vetting/report.md`` §3.2). There is no
HTTP layer in the unified adapter;
``requires_network=False``.

The canonical default version ``"RSF Press Freedom Index
2026"`` matches the staged bundle's
``data/raw/rsf_press_freedom/metadata.json``
``source_version`` field byte-for-byte so the readiness
gate can validate the staged metadata against the
canonical version stamp. The descriptor advertises the
``coverage_hint`` envelope 2002-2026 (the documented RSF
annual coverage envelope; the 2011 direct CSV is absent
so the effective per-year file list is
``AVAILABLE_YEARS = (2002..2010, 2012..2026)``) so the
runner can refuse to dispatch out-of-coverage year
requests (SRC-COV-002 / SRC-COV-003) and surface a
structured 2011 missing/direct-CSV caveat when a caller
asks for the missing year.

Observation-family shape
------------------------

RSF is a press/media-freedom sub-signal for the
``political_freedom`` rating category per
``docs/architecture/sources.md`` §7.1 priority 7 +
``docs/sources/vetting/report.md`` §3.2 -- the canonical
RSF catalog at
``src/leaders_db/ingest/catalogs/rsf_press_freedom.csv``
declares ``category=political_freedom`` for all 7
catalog indicators. The unified descriptor maps that
single category to a single observation family:

- ``political_freedom`` -> ``political_freedom_country_year``

The 7 catalog indicators (per
``src/leaders_db/ingest/catalogs/rsf_press_freedom.csv``)
are the canonical pre/post-2022 schema set:

- ``rsf_press_freedom_score`` (2002-2026; 2002-2021
  uses ``Score N``; 2022-2024 uses ``Score``; 2025+ uses
  ``Score 2025`` / ``Score 2026``).
- ``rsf_press_freedom_rank`` (2002-2026; 2002-2021 uses
  ``Rank N``; 2022+ uses ``Rank``).
- 5 component-context indicators
  (``rsf_press_freedom_political_context``,
  ``rsf_press_freedom_economic_context``,
  ``rsf_press_freedom_legal_context``,
  ``rsf_press_freedom_social_context``,
  ``rsf_press_freedom_safety``) -- 2022+ files ONLY.
  Pre-2022 files do not carry these columns; the unified
  transform emits zero observations for those years per
  the documented pre/post-2022 methodology/schema
  distinction.

The descriptor advertises the single observation
family so downstream query code can filter by
``observation_family == "political_freedom_country_year"``
without consulting the per-source catalog. RSF is
explicitly NOT a full political-freedom replacement --
it is a press/media-freedom sub-signal, complementing
V-Dem / Polity V / Freedom House (per the canonical
attribution block in ``docs/sources/attributions.md``).

Attribution
-----------

The unified ``RSF_PRESS_FREEDOM_ATTRIBUTION_TEXT``
constant is byte-identical to the legacy
``RSF_PRESS_FREEDOM_ATTRIBUTION`` constant in
``src/leaders_db/ingest/rsf_press_freedom_io.py`` and to
the ``rsf_press_freedom`` section in
``docs/sources/attributions.md``. The
:func:`test_rsf_press_freedom_attribution_text_matches_attributions_doc`
drift guard enforces byte-identity between the code
constant and the docs (Always-On Rule #15).

Direction hint
--------------

RSF is the first source where the score direction is
``higher_is_better=True`` (higher RSF score = better
situation for press freedom -- the RSF methodology
inverts the natural "freedom" framing). The rank
direction is ``higher_is_better=False`` (rank 1 = best
country; rank ~180 = worst). Per-observation
``extension`` carries the canonical
``higher_is_better`` / ``raw_scale`` /
``normalized_scale_target`` direction hints so
downstream Stage 5/6 score modules can normalize
without re-reading the legacy catalog.
"""

from __future__ import annotations

# Re-export the indicator-name + raw_column constants
# from :mod:`._indicator_constants` so callers can
# ``from leaders_db.sources.adapters.rsf_press_freedom
# ._constants import RSF_PRESS_FREEDOM_INDICATOR_NAMES``
# (the canonical module-level re-export contract;
# see :mod:`._indicator_constants` for the per-symbol
# docstring + provenance).
from ._indicator_constants import (
    RSF_PRESS_FREEDOM_BASE_RAW_COLUMNS,
    RSF_PRESS_FREEDOM_INDICATOR_ECONOMIC_CONTEXT,
    RSF_PRESS_FREEDOM_INDICATOR_LEGAL_CONTEXT,
    RSF_PRESS_FREEDOM_INDICATOR_NAMES,
    RSF_PRESS_FREEDOM_INDICATOR_POLITICAL_CONTEXT,
    RSF_PRESS_FREEDOM_INDICATOR_RANK,
    RSF_PRESS_FREEDOM_INDICATOR_SAFETY,
    RSF_PRESS_FREEDOM_INDICATOR_SCORE,
    RSF_PRESS_FREEDOM_INDICATOR_SOCIAL_CONTEXT,
    RSF_PRESS_FREEDOM_RAW_COLUMN_RANK,
    RSF_PRESS_FREEDOM_RAW_COLUMN_SCORE,
)

# ---------------------------------------------------------------------------
# Canonical RSF constants
# ---------------------------------------------------------------------------

# Canonical slug. The data-lake folder is also
# ``rsf_press_freedom/`` (the slug is the folder name;
# RSF is unlike ``pts`` / ``political_terror_scale``
# where the slug differs from the folder). The
# descriptor's ``source_id.slug`` is ``"rsf_press_freedom"``
# to match the legacy Stage 2 dispatch key + the
# attribution key.
RSF_PRESS_FREEDOM_SOURCE_KEY: str = "rsf_press_freedom"

# Canonical metadata + per-year CSV file name pattern.
# ``metadata.json`` is always at the bundle root; the
# per-year CSVs follow ``rsf_press_freedom_<year>.csv``
# (the live RSF download pattern
# ``https://rsf.org/sites/default/files/import_classement/{year}.csv``).
# The unified adapter uses the same per-year CSV naming
# for the canonical 2002-2026 raw files and resolves
# per-year files dynamically for the request scope.
RSF_PRESS_FREEDOM_METADATA_NAME: str = "metadata.json"
RSF_PRESS_FREEDOM_CSV_NAME_PATTERN: str = (
    "rsf_press_freedom_{year}.csv"
)

# Canonical default version -- the exact string the
# staged
# ``data/raw/rsf_press_freedom/metadata.json`` carries
# under ``source_version`` ("annual CSV series
# 2002-2026, acquired 2026-06-18"). The unified adapter
# uses the canonical stamp ``"RSF Press Freedom Index
# 2026"`` to match the live 2026 RSF release + the
# canonical attribution block in
# ``docs/sources/attributions.md`` (``RSF World Press
# Freedom Index (Reporters Without Borders 2026).``) +
# the legacy ``RSF_PRESS_FREEDOM_ATTRIBUTION`` constant.
# The staged metadata carries a more verbose
# ``source_version`` stamp (the "annual CSV series
# 2002-2026, acquired 2026-06-18" string); the unified
# adapter's canonical version is the brief
# ``"RSF Press Freedom Index 2026"`` stamp.
RSF_PRESS_FREEDOM_DEFAULT_VERSION: str = (
    "RSF Press Freedom Index 2026"
)

# Coverage envelope. The RSF World Press Freedom Index
# is annual, 2002-present (per
# ``docs/sources/registry.md`` ``rsf_press_freedom`` row
# + the bundle metadata's ``coverage.downloaded_years``
# annotation). The descriptor uses this literal
# envelope so the runner can refuse to dispatch
# out-of-coverage year requests (SRC-COV-002 /
# SRC-COV-003). Note: the direct ``2011.csv`` is
# absent; year=2011 requests fail readiness with a
# structured ``rsf_year_2011_absent`` warning (NOT a
# generic ``year_absent`` so the operator can
# distinguish the documented 2011 caveat from a
# generic out-of-coverage year).
RSF_PRESS_FREEDOM_COVERAGE_START_YEAR: int = 2002
RSF_PRESS_FREEDOM_COVERAGE_END_YEAR: int = 2026

# Year that is absent from the direct-CSV pattern.
# RSF publishes a combined 2011/2012 edition
# represented by the 2012 file (its ``Year (N)`` column
# reads ``"2011-12"``). Year=2011 requests fail
# readiness with a structured
# ``rsf_year_2011_absent`` warning so the operator can
# distinguish the documented 2011 caveat from a generic
# out-of-coverage year (SRC-COV-002 / SRC-COV-003).
RSF_PRESS_FREEDOM_MISSING_DIRECT_YEAR: int = 2011

# Years available from the canonical direct-CSV pattern
# (2002-2010 + 2012-2026; the 2011 file is absent). The
# readiness gate uses this constant to validate the
# staged metadata's ``local_files`` annotation for
# year-scoped requests and to drive the per-year
# CSV-presence check.
RSF_PRESS_FREEDOM_AVAILABLE_YEARS: tuple[int, ...] = (
    2002, 2003, 2004, 2005, 2006, 2007, 2008, 2009, 2010,
    # 2011 absent; the 2012 file represents the combined
    # 2011/2012 edition.
    2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019,
    2020, 2021,
    2022, 2023, 2024, 2025, 2026,
)

# RSF homepage / canonical page. The staged bundle's
# ``canonical_page`` field carries the same URL.
RSF_PRESS_FREEDOM_HOMEPAGE_URL: str = "https://rsf.org/en/index"

# Attribution key + canonical text. The text is
# byte-identical to the legacy
# ``RSF_PRESS_FREEDOM_ATTRIBUTION`` constant in
# ``src/leaders_db/ingest/rsf_press_freedom_io.py`` and
# to the ``rsf_press_freedom`` section in
# ``docs/sources/attributions.md`` (Always-On Rule #15).
# The
# :func:`test_rsf_press_freedom_attribution_text_matches_attributions_doc`
# drift guard enforces byte-identity.
RSF_PRESS_FREEDOM_ATTRIBUTION_KEY: str = "rsf_press_freedom"
RSF_PRESS_FREEDOM_ATTRIBUTION_TEXT: str = (
    "RSF World Press Freedom Index (Reporters Without "
    "Borders 2026)."
)

# Single observation family: RSF is the canonical
# press/media-freedom sub-signal for the political-
# freedom rating category. The unified descriptor
# advertises this single family so downstream query
# code can filter by ``observation_family ==
# "political_freedom_country_year"`` without consulting
# the per-source catalog. The RSF catalog at
# ``src/leaders_db/ingest/catalogs/rsf_press_freedom.csv``
# declares ``category=political_freedom`` for all 7
# catalog indicators. RSF is explicitly NOT a full
# political-freedom replacement -- it is a press/media-
# freedom sub-signal, complementing V-Dem / Polity V /
# Freedom House.
RSF_PRESS_FREEDOM_OBSERVATION_FAMILY: str = (
    "political_freedom_country_year"
)
RSF_PRESS_FREEDOM_SUPPORTED_FAMILIES: tuple[str, ...] = (
    RSF_PRESS_FREEDOM_OBSERVATION_FAMILY,
)

# The 7 RSF indicator ``variable_name`` values from the
# canonical catalog at
# ``src/leaders_db/ingest/catalogs/rsf_press_freedom.csv``
# live in :mod:`._indicator_constants` (re-exported below
# for the canonical module-level re-export contract).
# The 2 base ``raw_column`` names live alongside them.

# Structured warning code used to surface a request for
# the documented missing year (2011). Distinct from
# the generic ``YEAR_ABSENT`` so the operator can
# distinguish the documented 2011 caveat (RSF publishes
# a combined 2011/2012 edition represented by the 2012
# file) from a generic out-of-coverage year.
RSF_PRESS_FREEDOM_YEAR_2011_ABSENT_CODE: str = (
    "rsf_year_2011_absent"
)

# Verbose acquisition-date stamp the staged metadata
# carries under ``source_version``. The unified
# adapter also accepts the brief canonical stamp
# ``"RSF Press Freedom Index 2026"`` so future
# metadata rewrites that adopt the brief stamp still
# pass readiness. The authoritative definition of
# the bundle / canonical version stamps lives in
# :mod:`._metadata_version_validators` (where the
# metadata-version validator consumes them); this
# module re-exports the constant for the canonical
# module-level re-export contract.
RSF_PRESS_FREEDOM_BUNDLE_VERSION_STAMP: str = (
    "annual CSV series 2002-2026, acquired 2026-06-18"
)

# Brief canonical version stamp the unified adapter
# hardcodes as the request-scoped
# ``source_version``. The authoritative definition
# lives in :mod:`._metadata_version_validators`; this
# module re-exports the constant for the canonical
# module-level re-export contract.
RSF_PRESS_FREEDOM_CANONICAL_VERSION_STAMP: str = (
    "RSF Press Freedom Index 2026"
)

# Structured warning code used to surface a per-year
# CSV SHA-256 that is well-formed but does not match
# the staged file. Mirrors the CPI / UCDP /
# V-Dem ``*_checksum_mismatch`` pattern.
RSF_PRESS_FREEDOM_CHECKSUM_MISMATCH: str = (
    "rsf_press_freedom_checksum_mismatch"
)

# Structured warning code used to surface a bundle
# ``source_version`` stamp that does not match the
# canonical stamp. Distinct from
# ``UNSUPPORTED_VERSION`` because the bundle-stamped
# field is a verbose acquisition stamp ("annual CSV
# series 2002-2026, acquired 2026-06-18") while the
# request-scoped stamp is always the brief canonical
# stamp ("RSF Press Freedom Index 2026").
RSF_PRESS_FREEDOM_METADATA_VERSION_MISMATCH: str = (
    "rsf_press_freedom_metadata_version_mismatch"
)


# Asset id pattern used for the per-year RSF CSVs
# across all observation locators in a single run.
# Matches the WGI / WDI / V-Dem / UCDP / CPI / PTS
# convention (one logical asset per raw file) so audit
# code can group observations by asset. The asset id
# embeds the request-scoped year so per-year CSV reads
# in a single run surface distinct raw assets per year.
def _csv_asset_id_for_year(year: int) -> str:
    """Return the per-year raw asset id.

    The unified RSF adapter reads ONE per-year CSV per
    request year, so the asset id embeds the year so
    audit code can group observations by per-year
    asset. ``csv_name`` below resolves to
    ``rsf_press_freedom_<year>.csv``.
    """
    return (
        f"{RSF_PRESS_FREEDOM_SOURCE_KEY}:"
        f"{RSF_PRESS_FREEDOM_CSV_NAME_PATTERN.format(year=year)}"
    )


__all__ = [
    "RSF_PRESS_FREEDOM_ATTRIBUTION_KEY",
    "RSF_PRESS_FREEDOM_ATTRIBUTION_TEXT",
    "RSF_PRESS_FREEDOM_AVAILABLE_YEARS",
    "RSF_PRESS_FREEDOM_BASE_RAW_COLUMNS",
    "RSF_PRESS_FREEDOM_CHECKSUM_MISMATCH",
    "RSF_PRESS_FREEDOM_COVERAGE_END_YEAR",
    "RSF_PRESS_FREEDOM_COVERAGE_START_YEAR",
    "RSF_PRESS_FREEDOM_CSV_NAME_PATTERN",
    "RSF_PRESS_FREEDOM_DEFAULT_VERSION",
    "RSF_PRESS_FREEDOM_HOMEPAGE_URL",
    "RSF_PRESS_FREEDOM_INDICATOR_ECONOMIC_CONTEXT",
    "RSF_PRESS_FREEDOM_INDICATOR_LEGAL_CONTEXT",
    "RSF_PRESS_FREEDOM_INDICATOR_NAMES",
    "RSF_PRESS_FREEDOM_INDICATOR_POLITICAL_CONTEXT",
    "RSF_PRESS_FREEDOM_INDICATOR_RANK",
    "RSF_PRESS_FREEDOM_INDICATOR_SAFETY",
    "RSF_PRESS_FREEDOM_INDICATOR_SCORE",
    "RSF_PRESS_FREEDOM_INDICATOR_SOCIAL_CONTEXT",
    "RSF_PRESS_FREEDOM_METADATA_NAME",
    "RSF_PRESS_FREEDOM_METADATA_VERSION_MISMATCH",
    "RSF_PRESS_FREEDOM_MISSING_DIRECT_YEAR",
    "RSF_PRESS_FREEDOM_OBSERVATION_FAMILY",
    "RSF_PRESS_FREEDOM_RAW_COLUMN_RANK",
    "RSF_PRESS_FREEDOM_RAW_COLUMN_SCORE",
    "RSF_PRESS_FREEDOM_SOURCE_KEY",
    "RSF_PRESS_FREEDOM_SUPPORTED_FAMILIES",
    "RSF_PRESS_FREEDOM_YEAR_2011_ABSENT_CODE",
    "_csv_asset_id_for_year",
]
