"""Transparency International CPI constants + canonical
:class:`SourceDescriptor`.

This module owns the static metadata that does not change
between adapter instances: the canonical source constants
(source key, default version, attribution text, homepage
URL, observation families, coverage envelope), and the
:func:`build_transparency_cpi_descriptor` factory.

Split out of
:mod:`leaders_db.sources.adapters.transparency_cpi.adapter`
so the adapter class module stays focused on the lifecycle
methods. The constants are also re-exported from
:mod:`leaders_db.sources.adapters.transparency_cpi` (the
package root) so callers can ``from
leaders_db.sources.adapters.transparency_cpi import
TRANSPARENCY_CPI_SOURCE_KEY`` without knowing which
submodule the symbol lives in.

Source-type semantics
---------------------

The descriptor advertises ``source_type="dataset"`` per
``docs/architecture/sources.md`` §5.2: the canonical
Transparency International CPI access path is a single
per-year CSV (the OCHA Humanitarian Data Exchange (HDX)
mirror at
``data.humdata.org/dataset/<uuid>/resource/<ruuid>/download/global_cpi_<year>.csv``).
The canonical CSV for the prototype's 2023 target year is
``data/raw/transparency_cpi/transparency_cpi_2023.csv`` (180
countries, the verbatim HDX-mirrored Transparency
International release; the canonical TI xlsx download is
CDN-gated per docs/sources/vetting/report.md §3.6). There
is no HTTP layer in the unified adapter;
``requires_network=False``.

The canonical default version ``"CPI 2023"`` matches the
staged bundle's
``data/raw/transparency_cpi/metadata.json``
``source_version`` field byte-for-byte so the readiness
gate can validate the staged metadata against the
canonical version stamp. The descriptor advertises the
``coverage_hint`` envelope 1995-2023 (the documented TI CPI
annual coverage envelope) so the runner can refuse to
dispatch out-of-coverage year requests (SRC-COV-002 /
SRC-COV-003).

Observation-family shape
------------------------

Transparency International CPI feeds the
``integrity_country_year`` observation family (per
``docs/architecture/sources.md`` §5.2 + §7.1 priority 6;
CPI is the canonical perception-based corruption /
integrity sub-signal). The descriptor advertises this
single family explicitly so downstream query code can
filter by it without consulting the per-source catalog.
The CPI 2023 dataset (via HDX) has 180 country rows with
nine recorded columns: ``country``, ``iso3``, ``region``,
``year``, ``score`` (the headline CPI score, integer
0-100), ``rank``, ``sources``, ``standardError``,
``lowerCi``, ``upperCi``. The unified adapter narrows the
raw CSV to the single catalog indicator (``cpi_score``)
and carries the audit-trail fields
(``rank`` / ``sources`` / ``standard_error`` /
``lower_ci`` / ``upper_ci``) on every observation's
``extension`` so downstream scorers can recover the input
audit trail without re-reading the legacy catalog or the
legacy CSV.

Attribution
-----------

The unified ``TRANSPARENCY_CPI_ATTRIBUTION_TEXT`` constant
is byte-identical to the legacy
``TRANSPARENCY_CPI_ATTRIBUTION`` constant in
``src/leaders_db/ingest/transparency_cpi_io.py`` (which
itself is a substring of
``docs/sources/attributions.md`` ``transparency_cpi``
section, lines 81-87). The
:func:`test_transparency_cpi_attribution_text_matches_attributions_doc`
drift guard enforces byte-identity between the code
constant and the docs (Always-On Rule #15). The
attribution text deliberately distinguishes the
publisher (Transparency International) from the HDX
mirror that preserves the verbatim TI release -- the
report-facing attribution block names Transparency
International CPI 2023 (the canonical publisher name),
NOT the OCHA HDX mirror (which is the durable CSV
provenance path documented separately in the bundle
metadata's ``hdx_mirror_url`` field). Mirroring vs.
publisher attribution is documented in
``docs/sources/attributions.md`` §
``transparency_cpi`` and is enforced by this drift
guard.
"""

from __future__ import annotations

from leaders_db.sources.contracts import (
    CoverageHint,
    SourceDescriptor,
    SourceId,
)

# ---------------------------------------------------------------------------
# Canonical Transparency International CPI constants
# ---------------------------------------------------------------------------

TRANSPARENCY_CPI_SOURCE_KEY: str = "transparency_cpi"

# Canonical metadata + CSV file names. ``metadata.json`` is
# always at the bundle root; the per-year CSV is
# ``transparency_cpi_<year>.csv`` per the legacy Stage 2
# adapter's filename convention and the HDX mirror URL
# pattern (``global_cpi_<year>.csv``). The unified adapter
# uses the same per-year CSV naming for the canonical
# 2023 raw file
# (``data/raw/transparency_cpi/transparency_cpi_2023.csv``)
# and resolves per-year files dynamically for the request
# scope.
TRANSPARENCY_CPI_METADATA_NAME: str = "metadata.json"
TRANSPARENCY_CPI_CSV_NAME_TEMPLATE: str = (
    "transparency_cpi_{year}.csv"
)

# Canonical default version -- the exact string the staged
# ``data/raw/transparency_cpi/metadata.json`` carries under
# ``source_version`` ("CPI 2023"). The unified adapter
# uses this string as the canonical version stamp; the
# bundle's ``metadata.json['source_version']`` must match
# it byte-for-byte for readiness to pass.
TRANSPARENCY_CPI_DEFAULT_VERSION: str = "CPI 2023"

# Coverage envelope. The Transparency International CPI
# is annual, 1995-present (per docs/sources/registry.md
# ``transparency_cpi`` row + the bundle metadata's
# ``years_available: "1995-2023+"`` annotation). The
# descriptor uses this literal envelope so the runner can
# refuse to dispatch out-of-coverage year requests
# (SRC-COV-002 / SRC-COV-003).
TRANSPARENCY_CPI_COVERAGE_START_YEAR: int = 1995
TRANSPARENCY_CPI_COVERAGE_END_YEAR: int = 2023

# Transparency International CPI homepage / canonical page.
# The staged bundle's ``source_url`` field carries the
# same URL; the staged ``hdx_mirror_url`` field carries
# the canonical HDX CSV mirror URL (the durable per-year
# CSV provenance documented separately). The descriptor
# uses the canonical TI landing page because that is the
# canonical user-facing citation; the HDX mirror URL is
# carried on the metadata field ``hdx_mirror_url`` and on
# the raw asset's URL when present.
TRANSPARENCY_CPI_HOMEPAGE_URL: str = "https://www.transparency.org/en/cpi/2023"

# Attribution key + canonical text. The text is
# byte-identical to the legacy
# ``TRANSPARENCY_CPI_ATTRIBUTION`` constant in
# ``src/leaders_db/ingest/transparency_cpi_io.py`` and to
# the ``transparency_cpi`` section in
# ``docs/sources/attributions.md`` (Always-On Rule #15).
# The ``test_transparency_cpi_attribution_text_matches_attributions_doc``
# drift guard enforces byte-identity. The text is the
# report-facing publisher attribution (Transparency
# International), not the HDX mirror name (the HDX mirror
# is the durable CSV provenance path documented in
# ``docs/sources/attributions.md`` §``transparency_cpi``).
TRANSPARENCY_CPI_ATTRIBUTION_KEY: str = "transparency_cpi"
TRANSPARENCY_CPI_ATTRIBUTION_TEXT: str = (
    "Transparency International CPI 2023."
)

# Single observation family: CPI is the canonical
# perception-based corruption / integrity sub-signal for
# the prototype. The unified descriptor advertises this
# single family so downstream query code can filter by
# ``observation_family == "integrity_country_year"``
# without consulting the per-source catalog. The CPI
# catalog at
# ``src/leaders_db/ingest/catalogs/transparency_cpi.csv``
# declares ``rating_category=integrity`` for the single
# catalog indicator ``cpi_score``.
TRANSPARENCY_CPI_OBSERVATION_FAMILY: str = "integrity_country_year"
TRANSPARENCY_CPI_SUPPORTED_FAMILIES: tuple[str, ...] = (
    TRANSPARENCY_CPI_OBSERVATION_FAMILY,
)

# Asset id used for the Transparency International CPI CSV
# raw asset across all observation locators in a single
# run. Matches the WGI / WDI / V-Dem convention (one
# logical asset per raw bundle) so audit code can group
# observations by asset. The asset id embeds the
# request-scoped year so per-year CSV reads in a single
# run surface distinct raw assets per year.
def _csv_asset_id_for_year(year: int) -> str:
    """Return the per-year raw asset id.

    The legacy Stage 2 adapter reads ONE per-year CSV per
    call, so the unified adapter mirrors that contract by
    carrying the year in the asset id. ``csv_name`` below
    resolves to ``transparency_cpi_<year>.csv``.
    """
    return (
        f"{TRANSPARENCY_CPI_SOURCE_KEY}:"
        f"{TRANSPARENCY_CPI_CSV_NAME_TEMPLATE.format(year=year)}"
    )


# Default per-year CSV filename for the prototype's 2023
# target year. The descriptor's canonical filename
# matches the staged bundle's
# ``transparency_cpi_2023.csv`` exactly.
TRANSPARENCY_CPI_DEFAULT_CSV_NAME: str = (
    TRANSPARENCY_CPI_CSV_NAME_TEMPLATE.format(year=2023)
)


def build_transparency_cpi_descriptor() -> SourceDescriptor:
    """Build the canonical Transparency International CPI
    :class:`SourceDescriptor`.

    The descriptor is the static metadata the registry
    exposes for source discovery (SRC-ID-003). The values
    mirror the canonical catalog and citation block in
    ``docs/sources/attributions.md`` (Rule #15).

    The descriptor advertises ``source_type="dataset"`` and
    ``requires_network=False`` so downstream query code and
    the runner can refuse to dispatch network I/O
    unconditionally for CPI (the unified adapter is
    local-file only by design; see
    ``docs/architecture/sources.md`` §11 SRC-TYPE-001).
    """
    return SourceDescriptor(
        source_id=SourceId(slug=TRANSPARENCY_CPI_SOURCE_KEY),
        display_name=(
            "Transparency International Corruption Perceptions "
            "Index (CPI) 2023"
        ),
        source_type="dataset",
        supported_observation_families=TRANSPARENCY_CPI_SUPPORTED_FAMILIES,
        default_version=TRANSPARENCY_CPI_DEFAULT_VERSION,
        homepage_url=TRANSPARENCY_CPI_HOMEPAGE_URL,
        attribution_key=TRANSPARENCY_CPI_ATTRIBUTION_KEY,
        coverage_hint=CoverageHint(
            start_year=TRANSPARENCY_CPI_COVERAGE_START_YEAR,
            end_year=TRANSPARENCY_CPI_COVERAGE_END_YEAR,
            countries=None,
            leaders=None,
            notes=(
                "Country-year corruption-perception indicator; "
                "180 countries + territories, 1995-present (annual). "
                "Single catalog indicator `cpi_score` (integer 0-100; "
                "higher_is_better=True). Audit-trail fields "
                "(rank, sources, standard_error, lower_ci, upper_ci) "
                "are carried on every observation's `extension` "
                "so downstream scorers can recover the input audit "
                "trail without re-reading the legacy CSV. The "
                "canonical CSV for the prototype's 2023 target year "
                "is staged at "
                "`data/raw/transparency_cpi/transparency_cpi_2023.csv` "
                "(HDX-mirrored verbatim Transparency International "
                "release; the canonical TI xlsx download is CDN-gated "
                "per docs/sources/vetting/report.md §3.6). Free for "
                "non-commercial use with attribution; cite "
                "Transparency International 2023."
            ),
        ),
        requires_manual_approval=False,
        requires_network=False,
    )


__all__ = [
    "TRANSPARENCY_CPI_ATTRIBUTION_KEY",
    "TRANSPARENCY_CPI_ATTRIBUTION_TEXT",
    "TRANSPARENCY_CPI_COVERAGE_END_YEAR",
    "TRANSPARENCY_CPI_COVERAGE_START_YEAR",
    "TRANSPARENCY_CPI_CSV_NAME_TEMPLATE",
    "TRANSPARENCY_CPI_DEFAULT_CSV_NAME",
    "TRANSPARENCY_CPI_DEFAULT_VERSION",
    "TRANSPARENCY_CPI_HOMEPAGE_URL",
    "TRANSPARENCY_CPI_METADATA_NAME",
    "TRANSPARENCY_CPI_OBSERVATION_FAMILY",
    "TRANSPARENCY_CPI_SOURCE_KEY",
    "TRANSPARENCY_CPI_SUPPORTED_FAMILIES",
    "_csv_asset_id_for_year",
    "build_transparency_cpi_descriptor",
]
