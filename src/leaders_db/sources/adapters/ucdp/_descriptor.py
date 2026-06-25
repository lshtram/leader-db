"""UCDP (Uppsala Conflict Data Program) constants + canonical
:class:`SourceDescriptor`.

This module owns the static metadata that does not change between
adapter instances: the canonical source constants (source key,
default version, attribution text, homepage URL, observation
families, coverage envelope), and the
:func:`build_ucdp_descriptor` factory.

Split out of
:mod:`leaders_db.sources.adapters.ucdp.adapter` so the adapter
class module stays focused on the lifecycle methods. The
constants are also re-exported from
:mod:`leaders_db.sources.adapters.ucdp` (the package root) so
callers can ``from leaders_db.sources.adapters.ucdp import
UCDP_SOURCE_KEY`` without knowing which submodule the symbol
lives in.

Source-type semantics
---------------------

The descriptor advertises ``source_type="dataset"`` per
``docs/architecture/sources.md`` §5.2: UCDP's canonical access
path is a single staged zip (``ged231-csv.zip``) containing one
CSV with the event-level rows (316,818 events in v23.1). There
is no HTTP layer; ``requires_network=False``.

The canonical default version ``"GED 23.1"`` matches the
staged bundle's ``data/raw/ucdp/metadata.json``
``source_version`` field byte-for-byte so the readiness gate
can validate the staged metadata against the canonical version
stamp. The "23.1" in the version refers to UCDP's release year
(2023); the data ends at 2022 per the documented UCDP GED
23.1 release. The descriptor advertises
``coverage_hint.end_year=2022`` accordingly.

Observation-family shape
------------------------

UCDP feeds two of the eight rating categories (per
``docs/architecture/sources.md`` §7.1 priority 11):

- ``international_peace`` -- the four state-based indicators
  (``ucdp_state_based_events``, ``ucdp_state_based_fatalities``,
  ``ucdp_intl_events``, ``ucdp_intl_fatalities``) for
  state-based conflict events and the cross-border
  internationalized subset.
- ``domestic_violence`` -- the two one-sided indicators
  (``ucdp_onesided_events``, ``ucdp_onesided_fatalities``) for
  state-perpetrated violence against civilians.

The unified descriptor advertises BOTH observation families
explicitly so downstream query code can filter by them
without consulting the per-source catalog. The single
legacy event-level CSV (streamed through a zip) is the raw
artifact for every family. The aggregation is event -> country-year
under the legacy long-to-wide pivot; the unified transform
emits one observation per ``(country_id, year, variable_name)``
triple (the canonical UCDP catalog has 6 indicator rows).

Attribution
-----------

The unified ``UCDP_ATTRIBUTION_TEXT`` constant is byte-identical
to the legacy ``UCDP_ATTRIBUTION`` constant in
``src/leaders_db/ingest/ucdp_io.py`` (which itself is a
substring of ``docs/sources/attributions.md`` UCDP section).
The
:func:`test_ucdp_attribution_text_matches_attributions_doc`
drift guard enforces byte-identity between the code constant
and the docs (Always-On Rule #15).
"""

from __future__ import annotations

from leaders_db.sources.contracts import (
    CoverageHint,
    SourceDescriptor,
    SourceId,
)

# ---------------------------------------------------------------------------
# Canonical UCDP constants
# ---------------------------------------------------------------------------

UCDP_SOURCE_KEY: str = "ucdp"

# Canonical metadata + zip file names. ``metadata.json`` is
# always at the bundle root; the zip is ``ged231-csv.zip`` per
# the live UCDP download URL and the legacy Stage 2 adapter's
# filename convention. The zip contains the canonical CSV
# ``GEDEvent_v23_1.csv`` (218 MB uncompressed) with the
# event-level rows.
UCDP_METADATA_NAME: str = "metadata.json"
UCDP_ZIP_NAME: str = "ged231-csv.zip"

# Canonical default version -- the exact string the staged
# ``data/raw/ucdp/metadata.json`` carries under
# ``source_version``. The unified adapter uses this string as
# the canonical version stamp; the bundle's
# ``metadata.json['source_version']`` must match it
# byte-for-byte for readiness to pass.
UCDP_DEFAULT_VERSION: str = "GED 23.1"

# Coverage envelope. UCDP GED 23.1 covers 1989-2022 per the
# canonical UCDP codebook. The descriptor uses this literal
# envelope so the runner can refuse to dispatch out-of-coverage
# year requests (SRC-COV-002 / SRC-COV-003).
UCDP_COVERAGE_START_YEAR: int = 1989
UCDP_COVERAGE_END_YEAR: int = 2022

# UCDP homepage / canonical page. The staged bundle's
# ``source_url`` field carries the canonical UCDP data
# download URL; the descriptor uses the canonical UCDP
# downloads landing page because that is the canonical
# user-facing landing page (not the zip download URL itself).
UCDP_HOMEPAGE_URL: str = "https://ucdp.uu.se/downloads/"

# Attribution key + canonical text. The text is byte-identical
# to the legacy ``UCDP_ATTRIBUTION`` constant in
# ``src/leaders_db/ingest/ucdp_io.py`` and to the
# ``ucdp`` section in ``docs/sources/attributions.md``
# (Always-On Rule #15). The
# ``test_ucdp_attribution_text_matches_attributions_doc``
# drift guard enforces byte-identity.
UCDP_ATTRIBUTION_KEY: str = "ucdp"
UCDP_ATTRIBUTION_TEXT: str = (
    "Davies, Shawn, Garounis, Nicholas, Sollenberg, Ralph, and Allansson, "
    "Marie (2023). UCDP Georeferenced Event Dataset (GED) 23.1. Uppsala "
    "Conflict Data Program. https://ucdp.uu.se/downloads/"
)

# Observation families. UCDP feeds two of the eight rating
# categories via the unified-source catalog at
# ``src/leaders_db/ingest/catalogs/ucdp.csv``:
# ``international_peace`` (4 state-based indicators) and
# ``domestic_violence`` (2 one-sided indicators). The
# descriptor advertises each as a distinct observation family
# so downstream query code can filter by them without
# consulting the per-source catalog.
UCDP_OBSERVATION_FAMILY_INTERNATIONAL_PEACE: str = (
    "international_peace_country_year"
)
UCDP_OBSERVATION_FAMILY_DOMESTIC_VIOLENCE: str = (
    "domestic_violence_country_year"
)

UCDP_SUPPORTED_FAMILIES: tuple[str, ...] = (
    UCDP_OBSERVATION_FAMILY_INTERNATIONAL_PEACE,
    UCDP_OBSERVATION_FAMILY_DOMESTIC_VIOLENCE,
)

# Asset id used for the UCDP zip raw asset across all
# observation locators in a single run. Matches the WGI / WDI
# / V-Dem convention (one logical asset per raw bundle) so
# audit code can group observations by asset.
UCDP_ZIP_ASSET_ID: str = f"{UCDP_SOURCE_KEY}:{UCDP_ZIP_NAME}"


def build_ucdp_descriptor() -> SourceDescriptor:
    """Build the canonical UCDP :class:`SourceDescriptor`.

    The descriptor is the static metadata the registry exposes
    for source discovery (SRC-ID-003). The values mirror the
    canonical catalog and citation block in
    ``docs/sources/attributions.md`` (Rule #15).

    The descriptor advertises ``source_type="dataset"`` and
    ``requires_network=False`` so downstream query code and the
    runner can refuse to dispatch network I/O unconditionally
    for UCDP (the unified adapter is local-file only by design;
    see ``docs/architecture/sources.md`` §11 SRC-TYPE-001).
    """
    return SourceDescriptor(
        source_id=SourceId(slug=UCDP_SOURCE_KEY),
        display_name=(
            "Uppsala Conflict Data Program Georeferenced Event "
            "Dataset (GED) 23.1"
        ),
        source_type="dataset",
        supported_observation_families=UCDP_SUPPORTED_FAMILIES,
        default_version=UCDP_DEFAULT_VERSION,
        homepage_url=UCDP_HOMEPAGE_URL,
        attribution_key=UCDP_ATTRIBUTION_KEY,
        coverage_hint=CoverageHint(
            start_year=UCDP_COVERAGE_START_YEAR,
            end_year=UCDP_COVERAGE_END_YEAR,
            countries=None,
            leaders=None,
            notes=(
                "Event-level organized violence aggregated by the "
                "unified adapter to country-year. The UCDP GED "
                "23.1 dataset ships as a 25.4 MB zip with one "
                "218 MB CSV containing 316,818 event-level rows "
                "covering 1989-2022. The unified adapter "
                "aggregates events to (country_id, year) by "
                "type_of_violence (1 = state-based, 3 = "
                "one-sided) and the cross-border filter "
                "(type=1 AND gwnob.notna() for the internationalized "
                "subset). Two observation families "
                "(international_peace_country_year, "
                "domestic_violence_country_year) cover the 6 "
                "catalog indicators in "
                "src/leaders_db/ingest/catalogs/ucdp.csv. "
                "country_id is UCDP's own integer id (NOT "
                "ISO3); Stage 3 country match resolves it to "
                "ISO3. Free academic license; cite Davies et "
                "al. 2023."
            ),
        ),
        requires_manual_approval=False,
        requires_network=False,
    )


__all__ = [
    "UCDP_ATTRIBUTION_KEY",
    "UCDP_ATTRIBUTION_TEXT",
    "UCDP_COVERAGE_END_YEAR",
    "UCDP_COVERAGE_START_YEAR",
    "UCDP_DEFAULT_VERSION",
    "UCDP_HOMEPAGE_URL",
    "UCDP_METADATA_NAME",
    "UCDP_OBSERVATION_FAMILY_DOMESTIC_VIOLENCE",
    "UCDP_OBSERVATION_FAMILY_INTERNATIONAL_PEACE",
    "UCDP_SOURCE_KEY",
    "UCDP_SUPPORTED_FAMILIES",
    "UCDP_ZIP_ASSET_ID",
    "UCDP_ZIP_NAME",
    "build_ucdp_descriptor",
]
