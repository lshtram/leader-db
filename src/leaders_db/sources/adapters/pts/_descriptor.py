"""Political Terror Scale (PTS) constants + canonical
:class:`SourceDescriptor`.

This module owns the static metadata that does not change
between adapter instances: the canonical source constants
(source key, default version, attribution text, homepage
URL, observation families, coverage envelope, the 3
indicator names), and the
:func:`build_pts_descriptor` factory.

Split out of
:mod:`leaders_db.sources.adapters.pts.adapter` so the
adapter class module stays focused on the lifecycle
methods. The constants are also re-exported from
:mod:`leaders_db.sources.adapters.pts` (the package root)
so callers can ``from
leaders_db.sources.adapters.pts import PTS_SOURCE_KEY``
without knowing which submodule the symbol lives in.

Source-type semantics
---------------------

The descriptor advertises ``source_type="dataset"`` per
``docs/architecture/sources.md`` §5.2: the canonical PTS
access path is a single staged xlsx (``PTS-2025.xlsx``)
containing one sheet (``PTS-2025``) with the long-format
country-year rows (10,531 data rows x 14 columns). There is
no HTTP layer; ``requires_network=False``. The xlsx is
opened with ``openpyxl.read_only=True`` and walked in a
single linear pass before the §6 sentinel matrix is applied
and the long-to-wide pivot happens.

The canonical default version ``"PTS-2025"`` matches the
staged bundle's ``data/raw/political_terror_scale/metadata.json``
``version`` field (the bundle uses ``version: "2025"`` to
denote the staged release year; the unified adapter uses
the canonical stamp ``"PTS-2025"`` to match the
filename + the design doc §2 canonical version stamp +
the legacy ``register_pts_source`` upsert key in
``src/leaders_db/ingest/pts_db.py``) so the readiness gate
can validate the staged metadata against the canonical
version stamp. The descriptor advertises the
``coverage_hint`` envelope 1976-2024 (the documented PTS
annual coverage envelope; the live xlsx contains 49
distinct years from 1976 through 2024) so the runner can
refuse to dispatch out-of-coverage year requests
(SRC-COV-002 / SRC-COV-003).

Observation-family shape
------------------------

PTS feeds the ``domestic_violence`` rating category per
``docs/architecture/pts.md`` §1 + §3 and the source-vetting
report §3.8. The three PTS scores
(``pts_amnesty_score`` / ``pts_human_rights_watch_score`` /
``pts_state_dept_score``) are the canonical 3-way expert-
coded cross-validation for state-perpetrated political
terror: each country-year is scored independently by
Amnesty International, Human Rights Watch, and the US State
Department on the 1-5 ordinal scale (higher = more terror).
The descriptor advertises a single observation family
(``domestic_violence_country_year``) plus the 3 named
indicator constants so downstream query code can filter by
the family without consulting the per-source catalog.

Source key vs folder alias
--------------------------

The data-lake folder is ``political_terror_scale/`` (the
human-readable bundle name; preserves the live download
filename and the staged metadata shape). The canonical
clean-source slug is ``pts`` (matches the CLI dispatch
key, the legacy ``STAGE2_ADAPTERS['pts']`` upsert, the
indicator catalog filename, and the attribution key in
``docs/sources/attributions.md``). The
``political_terror_scale`` folder alias is preserved only
as a disk-folder name; the descriptor's
``source_id.slug`` is ``"pts"``. This reconciliation is
documented in
``docs/architecture/sources.md`` §7.5 (the row entry for
``political_terror_scale`` in the documented-aliases
table; the chosen representation is ``pts`` source_id +
``political_terror_scale`` folder alias) and propagated
through the public API (``PTS_SOURCE_KEY = "pts"``).

Attribution
-----------

The unified ``PTS_ATTRIBUTION_TEXT`` constant is
byte-identical to the legacy ``PTS_ATTRIBUTION`` constant
in ``src/leaders_db/ingest/pts_io.py`` (which itself is a
substring of ``docs/sources/attributions.md`` ``pts``
section). The
:func:`test_pts_attribution_text_matches_attributions_doc`
drift guard enforces byte-identity between the code
constant and the docs (Always-On Rule #15).

NA_Status sentinel matrix
-------------------------

The PTS xlsx carries TWO independent signals per
indicator cell:

- ``PTS_X`` -- int 1-5 or str ``'NA'``.
- ``NA_Status_X`` -- int 0 / 66 / 77 / 88 / 99 (the 5
  known provenance codes).

The precedence rule (per design doc §6) is **NA_Status
takes precedence**: a cell is "valid data" iff
``NA_Status_X == 0`` AND ``PTS_X`` is an int in 1-5. The
4-case sentinel matrix + the §6.5 defensive check (an
unknown ``NA_Status`` code triggers a warning and is
treated as missing) live in
:mod:`._missing_values`; the readiness gate does NOT
short-circuit on the sentinel matrix (the matrix is a
per-row data-coercion contract, not a bundle-level
readiness gate).
"""

from __future__ import annotations

from leaders_db.sources.contracts import (
    CoverageHint,
    SourceDescriptor,
    SourceId,
)

# ---------------------------------------------------------------------------
# Canonical PTS constants
# ---------------------------------------------------------------------------

# Canonical slug. The data-lake folder is
# ``political_terror_scale/`` (the human-readable bundle
# name); the canonical slug is ``pts`` (the dispatch key
# + attribution key). Reconciliation documented in
# ``docs/architecture/sources.md`` §7.5.
PTS_SOURCE_KEY: str = "pts"

# Canonical metadata + xlsx file names. ``metadata.json``
# is always at the bundle root; the xlsx is the canonical
# ``PTS-2025.xlsx`` per the live download URL and the
# legacy Stage 2 adapter's filename convention. The xlsx
# contains the single sheet ``PTS-2025`` with 14 columns
# and 10,531 country-year rows.
PTS_METADATA_NAME: str = "metadata.json"
PTS_XLSX_NAME: str = "PTS-2025.xlsx"

# Canonical default version -- the exact string the
# staged
# ``data/raw/political_terror_scale/metadata.json``
# carries under ``version`` field. The unified adapter
# uses the canonical stamp ``"PTS-2025"`` (matches the
# xlsx filename and the legacy upsert key in
# ``src/leaders_db/ingest/pts_db.py``). The bundle's
# ``metadata.json['version']`` must match this stamp
# byte-for-byte for readiness to pass.
PTS_DEFAULT_VERSION: str = "PTS-2025"

# Coverage envelope. The Political Terror Scale is
# annual, 1976-present per the canonical staged bundle
# metadata (``coverage_start_year: 1976`` /
# ``coverage_end_year: 2024``) + the live xlsx (49
# distinct years from 1976 through 2024; verified
# 2026-06-18 per ``docs/architecture/pts.md`` §1). The
# descriptor uses this literal envelope so the runner
# can refuse to dispatch out-of-coverage year requests
# (SRC-COV-002 / SRC-COV-003).
PTS_COVERAGE_START_YEAR: int = 1976
PTS_COVERAGE_END_YEAR: int = 2024

# PTS homepage / canonical page. The staged bundle's
# ``source_url`` field carries the canonical xlsx
# download URL; the descriptor uses the canonical PTS
# landing page (the user-facing citation page, not the
# direct xlsx download URL itself).
PTS_HOMEPAGE_URL: str = "https://www.politicalterrorscale.org/"

# Attribution key + canonical text. The text is
# byte-identical to the legacy ``PTS_ATTRIBUTION``
# constant in ``src/leaders_db/ingest/pts_io.py`` and to
# the ``pts`` section in
# ``docs/sources/attributions.md`` (Always-On Rule #15).
# The
# :func:`test_pts_attribution_text_matches_attributions_doc`
# drift guard enforces byte-identity.
PTS_ATTRIBUTION_KEY: str = "pts"
PTS_ATTRIBUTION_TEXT: str = (
    "Wood, Reed M., Mark Gibney, and others. "
    "*The Political Terror Scale (PTS)*. "
    "https://www.politicalterrorscale.org/"
)

# Single observation family: PTS feeds the
# ``domestic_violence`` category per design doc §1 + §3
# (alongside UCDP's 2 one-sided violence indicators and
# V-Dem's 3 repression indicators). The descriptor
# advertises this single family so downstream query
# code can filter by
# ``observation_family == "domestic_violence_country_year"``
# without consulting the per-source catalog. The PTS
# catalog at
# ``src/leaders_db/ingest/catalogs/pts.csv`` declares
# ``rating_category=domestic_violence`` for all 3
# catalog indicators.
PTS_OBSERVATION_FAMILY: str = "domestic_violence_country_year"
PTS_SUPPORTED_FAMILIES: tuple[str, ...] = (
    PTS_OBSERVATION_FAMILY,
)

# The 3 PTS indicator ``variable_name`` values from the
# catalog. Used by the descriptor's coverage notes (so
# the descriptor carries the indicator list without
# consulting the per-source catalog at descriptor-build
# time) and by the per-row emission loop + the public
# surface. These match the catalog
# ``src/leaders_db/ingest/catalogs/pts.csv`` byte-for-byte.
PTS_INDICATOR_AMNESTY: str = "pts_amnesty_score"
PTS_INDICATOR_HUMAN_RIGHTS_WATCH: str = (
    "pts_human_rights_watch_score"
)
PTS_INDICATOR_STATE_DEPT: str = "pts_state_dept_score"
PTS_INDICATOR_NAMES: tuple[str, ...] = (
    PTS_INDICATOR_AMNESTY,
    PTS_INDICATOR_HUMAN_RIGHTS_WATCH,
    PTS_INDICATOR_STATE_DEPT,
)

# The 3 PTS xlsx raw column names (case-sensitive, no
# whitespace). Used by the xlsx reader to identify the
# indicator columns in the 14-column header. Matches
# the canonical xlsx header verbatim (verified live
# 2026-06-18 per ``docs/architecture/pts.md`` §2).
PTS_RAW_COLUMN_AMNESTY: str = "PTS_A"
PTS_RAW_COLUMN_HUMAN_RIGHTS_WATCH: str = "PTS_H"
PTS_RAW_COLUMN_STATE_DEPT: str = "PTS_S"
PTS_RAW_COLUMNS: tuple[str, ...] = (
    PTS_RAW_COLUMN_AMNESTY,
    PTS_RAW_COLUMN_HUMAN_RIGHTS_WATCH,
    PTS_RAW_COLUMN_STATE_DEPT,
)

# Asset id used for the PTS xlsx raw asset across all
# observation locators in a single run. Matches the
# WGI / WDI / V-Dem / UCDP / CPI convention (one
# logical asset per raw bundle) so audit code can
# group observations by asset. The xlsx is staged
# once per run, so a single asset id covers all
# observations emitted in that run.
PTS_XLSX_ASSET_ID: str = f"{PTS_SOURCE_KEY}:{PTS_XLSX_NAME}"

# The expected single-sheet name in the xlsx. Verified
# live 2026-06-18 per ``docs/architecture/pts.md`` §2
# (the canonical sheet is named ``PTS-2025``). The
# xlsx reader asserts this name on open and raises a
# structured error if the sheet name has drifted.
PTS_SHEET_NAME: str = "PTS-2025"


def build_pts_descriptor() -> SourceDescriptor:
    """Build the canonical PTS :class:`SourceDescriptor`.

    The descriptor is the static metadata the registry
    exposes for source discovery (SRC-ID-003). The values
    mirror the canonical catalog and citation block in
    ``docs/sources/attributions.md`` (Rule #15).

    The descriptor advertises ``source_type="dataset"`` and
    ``requires_network=False`` so downstream query code
    and the runner can refuse to dispatch network I/O
    unconditionally for PTS (the unified adapter is
    local-file only by design; see
    ``docs/architecture/sources.md`` §11 SRC-TYPE-001).
    """
    return SourceDescriptor(
        source_id=SourceId(slug=PTS_SOURCE_KEY),
        display_name=(
            "Political Terror Scale (PTS) 2025"
        ),
        source_type="dataset",
        supported_observation_families=PTS_SUPPORTED_FAMILIES,
        default_version=PTS_DEFAULT_VERSION,
        homepage_url=PTS_HOMEPAGE_URL,
        attribution_key=PTS_ATTRIBUTION_KEY,
        coverage_hint=CoverageHint(
            start_year=PTS_COVERAGE_START_YEAR,
            end_year=PTS_COVERAGE_END_YEAR,
            countries=None,
            leaders=None,
            notes=(
                "Country-year expert-coded political terror "
                "indicator; 3 parallel ordinal scores (1-5; "
                "higher = more terror) per country-year from "
                "Amnesty International, Human Rights Watch, "
                "and the US State Department. The canonical "
                "xlsx is staged at "
                "`data/raw/political_terror_scale/PTS-2025.xlsx` "
                "(single sheet `PTS-2025`, 14 columns, "
                "~10,531 country-year rows; verified live "
                "2026-06-18 per docs/architecture/pts.md §2). "
                "All 3 indicators feed `domestic_violence` "
                "alongside UCDP one-sided (2) and V-Dem "
                "repression (3). Each cell carries a paired "
                "NA_Status sentinel (0/66/77/88/99) where 0 "
                "is the only value that admits the published "
                "score; the §6 4-case precedence rule (NA_Status "
                "takes precedence) governs emission. The raw "
                "1-5 ordinal value is preserved verbatim on "
                "`source_observations.normalized_value`; the "
                "Stage 5 score module inverts the direction "
                "(higher = worse). Free academic use with "
                "attribution; cite Wood, Gibney, et al."
            ),
        ),
        requires_manual_approval=False,
        requires_network=False,
    )


__all__ = [
    "PTS_ATTRIBUTION_KEY",
    "PTS_ATTRIBUTION_TEXT",
    "PTS_COVERAGE_END_YEAR",
    "PTS_COVERAGE_START_YEAR",
    "PTS_DEFAULT_VERSION",
    "PTS_HOMEPAGE_URL",
    "PTS_INDICATOR_AMNESTY",
    "PTS_INDICATOR_HUMAN_RIGHTS_WATCH",
    "PTS_INDICATOR_NAMES",
    "PTS_INDICATOR_STATE_DEPT",
    "PTS_METADATA_NAME",
    "PTS_OBSERVATION_FAMILY",
    "PTS_RAW_COLUMNS",
    "PTS_RAW_COLUMN_AMNESTY",
    "PTS_RAW_COLUMN_HUMAN_RIGHTS_WATCH",
    "PTS_RAW_COLUMN_STATE_DEPT",
    "PTS_SHEET_NAME",
    "PTS_SOURCE_KEY",
    "PTS_SUPPORTED_FAMILIES",
    "PTS_XLSX_ASSET_ID",
    "PTS_XLSX_NAME",
    "build_pts_descriptor",
]
