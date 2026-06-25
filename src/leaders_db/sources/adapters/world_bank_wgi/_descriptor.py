"""World Bank WGI constants + canonical :class:`SourceDescriptor`.

This module owns the static metadata that does not change between
adapter instances: the canonical source constants (source key,
default version, attribution text, homepage URL, observation
families, coverage envelope), and the
:func:`build_world_bank_wgi_descriptor` factory.

Split out of
:mod:`leaders_db.sources.adapters.world_bank_wgi.adapter` so the
adapter class module stays focused on the lifecycle methods.
The constants are also re-exported from
:mod:`leaders_db.sources.adapters.world_bank_wgi` (the package
root) so callers can ``from
leaders_db.sources.adapters.world_bank_wgi import
WORLD_BANK_WGI_SOURCE_KEY`` without knowing which submodule the
symbol lives in.

Source-type semantics
---------------------

The descriptor advertises ``source_type="dataset"`` per
``docs/architecture/sources.md`` §5.2: WGI's canonical access path
is a single xlsx file (one workbook, 6 indicator sheets). There is
no HTTP layer; ``requires_network=False``.

The canonical default version ``"Worldwide Governance Indicators
2023 Update (data through 2022)"`` matches the staged bundle's
``data/raw/world_bank_wgi/metadata.json`` ``version`` field
byte-for-byte so the readiness gate can validate the staged
metadata against the canonical version stamp. The "2023" in the
version refers to the World Bank's release year, not the latest
data year -- the data ends at 2022 per the canonical xlsx. The
descriptor advertises ``coverage_hint.end_year=2022`` accordingly.

Observation-family shape
------------------------

WGI covers governance / institutional quality country-year
indicators (per ``docs/architecture/sources.md`` §5.7.5 the
"governance_country_year" family covers governance / effectiveness
indicators; we use this single family for the unified descriptor
so downstream query code can filter by it without consulting the
per-source catalog). The 6 WGI indicators (Voice and
Accountability, Political Stability, Government Effectiveness,
Regulatory Quality, Rule of Law, Control of Corruption) all live
in this family; ``Control of Corruption`` is also documented in
``docs/architecture/sources.md`` §7.3 as the
``world_bank_wgi_corruption`` subset for the integrity category
but stays a single observation family in the unified descriptor.
"""

from __future__ import annotations

from leaders_db.sources.contracts import (
    CoverageHint,
    SourceDescriptor,
    SourceId,
)

# ---------------------------------------------------------------------------
# Canonical World Bank WGI constants
# ---------------------------------------------------------------------------

WORLD_BANK_WGI_SOURCE_KEY: str = "world_bank_wgi"

# Canonical metadata + xlsx file names. ``metadata.json`` is
# always at the bundle root; the xlsx is ``wgidataset.xlsx`` per
# the live World Bank download URL and the legacy Stage 2
# adapter's filename convention.
WORLD_BANK_WGI_METADATA_NAME: str = "metadata.json"
WORLD_BANK_WGI_XLSX_NAME: str = "wgidataset.xlsx"

# Canonical default version -- the exact string the staged
# ``data/raw/world_bank_wgi/metadata.json`` carries under
# ``version``. The unified adapter uses this string as the
# canonical version stamp; the bundle's
# ``metadata.json['version']`` (and the legacy
# ``metadata.json['source_version']`` alias) must match it
# byte-for-byte for readiness to pass.
WORLD_BANK_WGI_DEFAULT_VERSION: str = (
    "Worldwide Governance Indicators 2023 Update (data through 2022)"
)

# Coverage envelope. WGI's full availability window starts at
# 1996 (the first year with WGI data) and reaches 2022 in the
# current "2023 Update" release. The descriptor uses the literal
# 1996-2022 envelope so the runner can refuse to dispatch
# out-of-coverage year requests (SRC-COV-002 / SRC-COV-003).
WORLD_BANK_WGI_COVERAGE_START_YEAR: int = 1996
WORLD_BANK_WGI_COVERAGE_END_YEAR: int = 2022

# WGI homepage / canonical page. The staged bundle's
# ``canonical_page`` field carries the same URL; the staged
# ``source_url`` field carries the canonical xlsx download URL.
# The descriptor uses the canonical governance page (not the
# xlsx download URL) because that is the canonical user-facing
# landing page.
WORLD_BANK_WGI_HOMEPAGE_URL: str = "https://info.worldbank.org/governance/wgi/"

# Attribution key + canonical text. The text is byte-identical
# to the legacy ``WGI_ATTRIBUTION`` constant in
# ``src/leaders_db/ingest/wgi_io.py`` and to the
# ``world_bank_wgi`` section in
# ``docs/sources/attributions.md`` (Always-On Rule #15). The
# ``test_world_bank_wgi_attribution_text_matches_attributions_doc``
# drift guard enforces byte-identity.
WORLD_BANK_WGI_ATTRIBUTION_KEY: str = "world_bank_wgi"
WORLD_BANK_WGI_ATTRIBUTION_TEXT: str = (
    "World Bank. 2023. Worldwide Governance Indicators. "
    "Washington, D.C.: The World Bank. https://info.worldbank.org/governance/wgi/ "
    "Licensed under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/)."
)

# Single observation family: WGI covers governance /
# institutional-quality country-year indicators (6 indicators in
# total, all per the unified ``governance_country_year`` family).
# The legacy catalog at
# ``src/leaders_db/ingest/catalogs/wgi.csv`` partitions the 6
# indicators across two rating categories (``effectiveness`` for
# 5 indicators + ``integrity`` for ``Control of Corruption``),
# but both rating categories map to the same observation family
# at the descriptor level so downstream query code can filter by
# ``observation_family == "governance_country_year"`` without
# consulting the per-source catalog.
WORLD_BANK_WGI_OBSERVATION_FAMILY: str = "governance_country_year"
WORLD_BANK_WGI_SUPPORTED_FAMILIES: tuple[str, ...] = (
    WORLD_BANK_WGI_OBSERVATION_FAMILY,
)


def build_world_bank_wgi_descriptor() -> SourceDescriptor:
    """Build the canonical World Bank WGI :class:`SourceDescriptor`.

    The descriptor is the static metadata the registry exposes for
    source discovery (SRC-ID-003). The values mirror the
    canonical catalog and citation block in
    ``docs/sources/attributions.md`` (Rule #15).

    The descriptor advertises ``source_type="dataset"`` and
    ``requires_network=False`` so downstream query code and the
    runner can refuse to dispatch network I/O unconditionally for
    WGI (the unified adapter is local-file only by design; see
    ``docs/architecture/sources.md`` §11 SRC-TYPE-001).
    """
    return SourceDescriptor(
        source_id=SourceId(slug=WORLD_BANK_WGI_SOURCE_KEY),
        display_name="World Bank Worldwide Governance Indicators",
        source_type="dataset",
        supported_observation_families=WORLD_BANK_WGI_SUPPORTED_FAMILIES,
        default_version=WORLD_BANK_WGI_DEFAULT_VERSION,
        homepage_url=WORLD_BANK_WGI_HOMEPAGE_URL,
        attribution_key=WORLD_BANK_WGI_ATTRIBUTION_KEY,
        coverage_hint=CoverageHint(
            start_year=WORLD_BANK_WGI_COVERAGE_START_YEAR,
            end_year=WORLD_BANK_WGI_COVERAGE_END_YEAR,
            countries=None,
            leaders=None,
            notes=(
                "Country-year governance indicators; 214 countries, "
                "1996-2022 (biennial 1996-2002, annual 2003-2022). "
                "Six aggregate indicators: Voice and Accountability, "
                "Political Stability, Government Effectiveness, "
                "Regulatory Quality, Rule of Law, Control of "
                "Corruption. Estimate column only (other per-year "
                "statistics -- StdErr, NumSrc, Rank, Lower, Upper "
                "-- are deferred). CC BY 4.0; the data is "
                "downloaded once a year as a single xlsx."
            ),
        ),
        requires_manual_approval=False,
        requires_network=False,
    )


__all__ = [
    "WORLD_BANK_WGI_ATTRIBUTION_KEY",
    "WORLD_BANK_WGI_ATTRIBUTION_TEXT",
    "WORLD_BANK_WGI_COVERAGE_END_YEAR",
    "WORLD_BANK_WGI_COVERAGE_START_YEAR",
    "WORLD_BANK_WGI_DEFAULT_VERSION",
    "WORLD_BANK_WGI_HOMEPAGE_URL",
    "WORLD_BANK_WGI_METADATA_NAME",
    "WORLD_BANK_WGI_OBSERVATION_FAMILY",
    "WORLD_BANK_WGI_SOURCE_KEY",
    "WORLD_BANK_WGI_SUPPORTED_FAMILIES",
    "WORLD_BANK_WGI_XLSX_NAME",
    "build_world_bank_wgi_descriptor",
]
