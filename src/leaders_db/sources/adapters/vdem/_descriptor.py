"""V-Dem (Varieties of Democracy) constants + canonical :class:`SourceDescriptor`.

This module owns the static metadata that does not change between
adapter instances: the canonical source constants (source key,
default version, attribution text, homepage URL, observation
families, coverage envelope), and the
:func:`build_vdem_descriptor` factory.

Split out of
:mod:`leaders_db.sources.adapters.vdem.adapter` so the adapter class
module stays focused on the lifecycle methods. The constants are
also re-exported from :mod:`leaders_db.sources.adapters.vdem` (the
package root) so callers can ``from
leaders_db.sources.adapters.vdem import VDEM_SOURCE_KEY`` without
knowing which submodule the symbol lives in.

Source-type semantics
---------------------

The descriptor advertises ``source_type="dataset"`` per
``docs/architecture/sources.md`` §5.2: V-Dem's canonical access path
is a single CSV file (``V-Dem-CY-Full+Others-v16.csv``,
~388MB / 28093 rows / 4618 columns). There is no HTTP layer;
``requires_network=False``.

The canonical default version ``"v16"`` matches the staged
bundle's ``data/raw/vdem/metadata.json`` ``source_version`` field
byte-for-byte so the readiness gate can validate the staged
metadata against the canonical version stamp. The descriptor
advertises ``coverage_hint.start_year=1789`` and
``end_year=2025`` (the documented V-Dem CY coverage envelope)
accordingly.

Observation-family shape
------------------------

V-Dem covers political-freedom, governance, integrity (corruption),
domestic-violence (repression), and social-wellbeing
country-year indicators (per
``docs/architecture/sources.md`` §7.5 the canonical
``vdem_governance`` and ``vdem_corruption`` aliases are
observation-family / catalog subsets under ``vdem``, not separate
adapters). The unified descriptor advertises all five
observation families explicitly so downstream query code can
filter by them without consulting the per-source catalog. The
single legacy CSV is the raw artifact for every family.

Attribution
-----------

The unified ``VDEM_ATTRIBUTION_TEXT`` constant is byte-identical
to the legacy ``VDEM_ATTRIBUTION`` constant in
``src/leaders_db/ingest/vdem_io.py`` (which itself is a substring
of ``docs/sources/attributions.md`` V-Dem section). The
:func:`test_vdem_attribution_text_matches_attributions_doc` drift
guard enforces byte-identity between the code constant and the
docs (Always-On Rule #15).
"""

from __future__ import annotations

from leaders_db.sources.contracts import (
    CoverageHint,
    SourceDescriptor,
    SourceId,
)

# ---------------------------------------------------------------------------
# Canonical V-Dem constants
# ---------------------------------------------------------------------------

VDEM_SOURCE_KEY: str = "vdem"

# Canonical metadata + CSV file names. ``metadata.json`` is
# always at the bundle root; the CSV is
# ``V-Dem-CY-Full+Others-v16.csv`` per the live V-Dem download
# URL and the legacy Stage 2 adapter's filename convention.
# The CSV is the only raw artifact the unified adapter reads;
# the original ``V-Dem-CY-FullOthers-v16_csv.zip`` is staged
# alongside the CSV and the readiness gate verifies its
# checksum separately so the readiness contract does not
# confuse the two artifacts.
VDEM_METADATA_NAME: str = "metadata.json"
VDEM_CSV_NAME: str = "V-Dem-CY-Full+Others-v16.csv"
VDEM_ZIP_NAME: str = "V-Dem-CY-FullOthers-v16_csv.zip"

# Canonical default version -- the exact string the staged
# ``data/raw/vdem/metadata.json`` carries under
# ``source_version``. The unified adapter uses this string as
# the canonical version stamp; the bundle's
# ``metadata.json['source_version']`` must match it
# byte-for-byte for readiness to pass.
VDEM_DEFAULT_VERSION: str = "v16"

# Coverage envelope. V-Dem CY v16 covers 1789-2025 per the
# canonical codebook. The descriptor uses this literal envelope
# so the runner can refuse to dispatch out-of-coverage year
# requests (SRC-COV-002 / SRC-COV-003).
VDEM_COVERAGE_START_YEAR: int = 1789
VDEM_COVERAGE_END_YEAR: int = 2025

# V-Dem homepage / canonical DOI. The staged bundle's
# ``source_url`` field carries the canonical V-Dem data
# landing page; the descriptor uses the DOI for the homepage
# URL because that is the canonical user-facing citation.
VDEM_HOMEPAGE_URL: str = "https://doi.org/10.23696/vdemds26"

# Attribution key + canonical text. The text is byte-identical
# to the legacy ``VDEM_ATTRIBUTION`` constant in
# ``src/leaders_db/ingest/vdem_io.py`` and to the
# ``vdem`` section in ``docs/sources/attributions.md``
# (Always-On Rule #15). The
# ``test_vdem_attribution_text_matches_attributions_doc`` drift
# guard enforces byte-identity.
VDEM_ATTRIBUTION_KEY: str = "vdem"
VDEM_ATTRIBUTION_TEXT: str = (
    "Coppedge, Michael, John Gerring, Carl Henrik Knutsen, Staffan I. "
    "Lindberg, Jan Teorell, David Altman, Fabio Angiolillo, Michael "
    "Bernhard, Agnes Cornell, M. Steven Fish, Linnea Fox, Lisa "
    "Gastaldi, Haakon Gjerløw, Adam Glynn, Ana Good God, Allen Hicken, "
    "Katrin Kinzelbach, Joshua Krusell, Kyle L. Marquardt, Kelly "
    "McMann, Valeriya Mechkova, Juraj Medzihorsky, Anja Neundorf, "
    "Pamela Paxton, Daniel Pemstein, Josefine Pernes, Johannes von "
    "Römer, Brigitte Seim, Rachel Sigman, Svend-Erik Skaaning, "
    "Jeffrey Staton, Aksel Sundström, Marcus Tannenberg, Eitan "
    "Tzelgov, Yi-ting Wang, Tore Wig, Steven Wilson and Daniel "
    "Ziblatt. 2026. \"V-Dem [Country-Year/Country-Date] Dataset v16\" "
    "Varieties of Democracy (V-Dem) Project. "
    "https://doi.org/10.23696/vdemds26."
)

# Observation families. V-Dem feeds five of the eight rating
# categories via the unified-source catalog at
# ``src/leaders_db/ingest/catalogs/vdem.csv``: political_freedom,
# integrity, effectiveness, domestic_violence, social_wellbeing.
# The descriptor advertises each as a distinct observation
# family so downstream query code can filter by them without
# consulting the per-source catalog. The canonical aliases
# ``vdem_governance`` and ``vdem_corruption`` documented in
# ``docs/architecture/sources.md`` §7.5 are subsets of these
# families (governance == effectiveness + political_freedom;
# corruption == integrity) and are NOT separate families in the
# unified descriptor.
VDEM_OBSERVATION_FAMILY_POLITICAL_FREEDOM: str = "political_country_year"
VDEM_OBSERVATION_FAMILY_GOVERNANCE: str = "governance_country_year"
VDEM_OBSERVATION_FAMILY_CORRUPTION: str = "corruption_country_year"
VDEM_OBSERVATION_FAMILY_REPRESSION: str = "repression_country_year"
VDEM_OBSERVATION_FAMILY_SOCIAL: str = "social_country_year"

VDEM_SUPPORTED_FAMILIES: tuple[str, ...] = (
    VDEM_OBSERVATION_FAMILY_POLITICAL_FREEDOM,
    VDEM_OBSERVATION_FAMILY_GOVERNANCE,
    VDEM_OBSERVATION_FAMILY_CORRUPTION,
    VDEM_OBSERVATION_FAMILY_REPRESSION,
    VDEM_OBSERVATION_FAMILY_SOCIAL,
)


# Asset id used for the V-Dem CSV raw asset across all
# observation locators in a single run. Matches the WGI / WDI
# convention (one logical asset per raw bundle) so audit code
# can group observations by asset.
VDEM_CSV_ASSET_ID: str = f"{VDEM_SOURCE_KEY}:{VDEM_CSV_NAME}"


def build_vdem_descriptor() -> SourceDescriptor:
    """Build the canonical V-Dem :class:`SourceDescriptor`.

    The descriptor is the static metadata the registry exposes
    for source discovery (SRC-ID-003). The values mirror the
    canonical catalog and citation block in
    ``docs/sources/attributions.md`` (Rule #15).

    The descriptor advertises ``source_type="dataset"`` and
    ``requires_network=False`` so downstream query code and
    the runner can refuse to dispatch network I/O
    unconditionally for V-Dem (the unified adapter is
    local-file only by design; see
    ``docs/architecture/sources.md`` §11 SRC-TYPE-001).
    """
    return SourceDescriptor(
        source_id=SourceId(slug=VDEM_SOURCE_KEY),
        display_name="Varieties of Democracy (V-Dem) v16",
        source_type="dataset",
        supported_observation_families=VDEM_SUPPORTED_FAMILIES,
        default_version=VDEM_DEFAULT_VERSION,
        homepage_url=VDEM_HOMEPAGE_URL,
        attribution_key=VDEM_ATTRIBUTION_KEY,
        coverage_hint=CoverageHint(
            start_year=VDEM_COVERAGE_START_YEAR,
            end_year=VDEM_COVERAGE_END_YEAR,
            countries=None,
            leaders=None,
            notes=(
                "Country-year political / governance / corruption / "
                "repression / social-wellbeing indicators; 202 "
                "countries, 1789-2025. Five observation families "
                "(political_country_year, governance_country_year, "
                "corruption_country_year, repression_country_year, "
                "social_country_year) cover the 22 catalog "
                "indicators in "
                "src/leaders_db/ingest/catalogs/vdem.csv. The "
                "CSV is the only raw artifact the unified adapter "
                "reads (no HTTP layer); the bundle's zip "
                "checksum is verified but the zip itself is not "
                "extracted by the unified path. Free academic "
                "license; cite Coppedge et al. 2026 (DOI "
                "10.23696/vdemds26)."
            ),
        ),
        requires_manual_approval=False,
        requires_network=False,
    )


__all__ = [
    "VDEM_ATTRIBUTION_KEY",
    "VDEM_ATTRIBUTION_TEXT",
    "VDEM_COVERAGE_END_YEAR",
    "VDEM_COVERAGE_START_YEAR",
    "VDEM_CSV_ASSET_ID",
    "VDEM_CSV_NAME",
    "VDEM_DEFAULT_VERSION",
    "VDEM_HOMEPAGE_URL",
    "VDEM_METADATA_NAME",
    "VDEM_OBSERVATION_FAMILY_CORRUPTION",
    "VDEM_OBSERVATION_FAMILY_GOVERNANCE",
    "VDEM_OBSERVATION_FAMILY_POLITICAL_FREEDOM",
    "VDEM_OBSERVATION_FAMILY_REPRESSION",
    "VDEM_OBSERVATION_FAMILY_SOCIAL",
    "VDEM_SOURCE_KEY",
    "VDEM_SUPPORTED_FAMILIES",
    "VDEM_ZIP_NAME",
    "build_vdem_descriptor",
]
