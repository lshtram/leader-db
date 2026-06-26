"""Unified-source BTI core constants (slug, version,
coverage envelope, attribution, observation
families, asset id).

This module owns the source-key + default-version +
coverage-envelope + attribution-text + observation-
family + asset-id constants for the unified-source
BTI adapter. Split out of :mod:`._descriptor` so the
descriptor module stays focused on the canonical
:func:`build_bti_descriptor` factory and respects the
documented 400-line convention.

The constants are also re-exported from
:mod:`._descriptor` (and from
:mod:`leaders_db.sources.adapters.bti`, the package
root) so callers can ``from
leaders_db.sources.adapters.bti import
BTI_ATTRIBUTION_TEXT`` without knowing which
submodule the symbol lives in.

Per-symbol docstrings are in :mod:`._descriptor`;
the canonical definitions live here for the
module-split.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Canonical BTI constants (source key, default
# version, coverage envelope, attribution,
# observation families, asset id)
# ---------------------------------------------------------------------------

# Canonical slug. The data-lake folder is also
# ``bti/`` (the slug is the folder name; no
# source-key / folder-alias reconciliation needed,
# unlike ``pts`` / ``political_terror_scale``).
# The descriptor's ``source_id.slug`` is ``"bti"``
# to match the legacy Stage 2 dispatch key + the
# attribution key.
BTI_SOURCE_KEY: str = "bti"

# Canonical metadata + xlsx file names.
# ``metadata.json`` is always at the bundle root;
# the xlsx is the cumulative
# ``BTI_2006-2026_Scores.xlsx`` (12 sheets, one
# BTI edition per sheet, 137-159 countries per
# edition, 123 columns).
BTI_METADATA_NAME: str = "metadata.json"
BTI_XLSX_NAME: str = "BTI_2006-2026_Scores.xlsx"

# Canonical default version -- the report-facing
# version stamp (the canonical "Attribution text
# in reports" line uses ``"BTI 2026 (Bertelsmann
# Stiftung 2026)."``). The staged bundle's
# ``data/raw/bti/metadata.json`` carries a verbose
# ``source_version`` stamp (``"BTI 2026 (covers
# 2024-2025); cumulative file covers 2006-2026
# (biennial, 12 editions)"``); the unified
# adapter's canonical report-facing stamp is the
# brief ``"BTI 2026"``.
BTI_DEFAULT_VERSION: str = "BTI 2026"

# Coverage envelope. BTI is biennial; the
# descriptor advertises the union of per-edition
# covered intervals: 2002-2003 via ``BTI 2006_old``
# (pre-methodology) through 2024-2025 via
# ``BTI 2026``. The literal envelope is 2002-2025
# so the runner can refuse to dispatch
# out-of-coverage year requests (SRC-COV-002 /
# SRC-COV-003).
BTI_COVERAGE_START_YEAR: int = 2002
BTI_COVERAGE_END_YEAR: int = 2025

# BTI homepage / canonical landing page. The
# staged bundle's ``source_url`` field carries the
# canonical downloads page; the descriptor uses
# the canonical BTI landing page (the user-facing
# citation landing page, not the direct downloads
# URL itself).
BTI_HOMEPAGE_URL: str = "https://bti-project.org/"

# Attribution key + canonical text. The text is
# byte-identical to the legacy ``BTI_ATTRIBUTION``
# constant in ``src/leaders_db/ingest/bti_io.py``
# (the short form ``"BTI 2026 (Bertelsmann
# Stiftung 2026)."``) and to the ``Attribution
# text in reports`` line in the ``bti`` section
# of ``docs/sources/attributions.md`` (Always-On
# Rule #15).
BTI_ATTRIBUTION_KEY: str = "bti"
BTI_ATTRIBUTION_TEXT: str = "BTI 2026 (Bertelsmann Stiftung 2026)."

# Observation families. BTI feeds three of the
# eight rating categories per the canonical BTI
# indicator catalog at
# ``src/leaders_db/ingest/catalogs/bti.csv``:
# ``effectiveness`` (2 indicators),
# ``political_freedom`` (7 indicators), and
# ``economic_wellbeing`` (3 indicators).
BTI_OBSERVATION_FAMILY_EFFECTIVENESS: str = (
    "effectiveness_country_year"
)
BTI_OBSERVATION_FAMILY_POLITICAL_FREEDOM: str = (
    "political_freedom_country_year"
)
BTI_OBSERVATION_FAMILY_ECONOMIC_WELLBEING: str = (
    "economic_wellbeing_country_year"
)

BTI_SUPPORTED_FAMILIES: tuple[str, ...] = (
    BTI_OBSERVATION_FAMILY_EFFECTIVENESS,
    BTI_OBSERVATION_FAMILY_POLITICAL_FREEDOM,
    BTI_OBSERVATION_FAMILY_ECONOMIC_WELLBEING,
)

# Asset id used for the BTI xlsx raw asset
# across all observation locators in a single run.
BTI_XLSX_ASSET_ID: str = f"{BTI_SOURCE_KEY}:{BTI_XLSX_NAME}"

# Structured warning code used to surface a
# bundle ``source_version`` stamp that does not
# match the canonical short stamp (``"BTI 2026"``).
# Distinct from ``UNSUPPORTED_VERSION`` because the
# bundle-stamped field is a verbose acquisition
# stamp while the request-scoped stamp is always
# the brief canonical stamp.
BTI_METADATA_VERSION_MISMATCH: str = (
    "bti_metadata_version_mismatch"
)

# Structured warning code used to surface a bundle
# ``checksum_sha256`` that does not match the
# staged xlsx. Defined canonically in
# :mod:`._checksum_validators` (the module that owns
# the checksum-shape + match logic).
# ``BTI_CHECKSUM_MISMATCH`` is re-exported from the
# canonical module below for the public surface.

# Module-local structured warning code used to
# reject an unsupported request source-version per
# SRC-REQ-009.
UNSUPPORTED_VERSION: str = "unsupported_version"


__all__ = [
    "BTI_ATTRIBUTION_KEY",
    "BTI_ATTRIBUTION_TEXT",
    "BTI_COVERAGE_END_YEAR",
    "BTI_COVERAGE_START_YEAR",
    "BTI_DEFAULT_VERSION",
    "BTI_HOMEPAGE_URL",
    "BTI_METADATA_NAME",
    "BTI_METADATA_VERSION_MISMATCH",
    "BTI_OBSERVATION_FAMILY_ECONOMIC_WELLBEING",
    "BTI_OBSERVATION_FAMILY_EFFECTIVENESS",
    "BTI_OBSERVATION_FAMILY_POLITICAL_FREEDOM",
    "BTI_SOURCE_KEY",
    "BTI_SUPPORTED_FAMILIES",
    "BTI_XLSX_ASSET_ID",
    "BTI_XLSX_NAME",
    "UNSUPPORTED_VERSION",
]
