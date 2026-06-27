"""Polity V (Polity5 v2018) constants + canonical :class:`SourceDescriptor`.

This module owns the static metadata that does not change between
adapter instances: the canonical source constants (source key,
default version, attribution text, coverage envelope, observation
family, the 11 indicator names + raw-column names), and the
:func:`build_polity_v_descriptor` factory.

Split out of :mod:`leaders_db.sources.adapters.polity_v.adapter` so
the adapter class module stays focused on the lifecycle methods.
The constants are also re-exported from
:mod:`leaders_db.sources.adapters.polity_v` (the package root) so
callers can ``from leaders_db.sources.adapters.polity_v import
POLITY_V_SOURCE_KEY`` without knowing which submodule the symbol
lives in.

Source-type semantics
---------------------

The descriptor advertises ``source_type="dataset"`` per
``docs/architecture/sources.md`` §5.2: Polity V's canonical access
path is a single SPSS ``.sav`` file
(``p5v2018.sav``, ~1.4 MB / 17574 rows / 37 columns) staged at
``data/raw/polity_v/p5v2018.sav``. There is no HTTP layer;
``requires_network=False``. The reader uses ``pyreadstat.read_sav``
to load the file; the rows are pivoted to a wide country-year frame
and emitted as :class:`NormalizedObservation` records.

The canonical default version ``"p5v2018"`` matches the canonical
Polity5 v2018 release stamp (``Polity5: Political Regime
Characteristics and Transitions, 1800-2018`` -- Marshall, Jaggers,
Gleditsch 2018). The bundle metadata's ``source_version`` field
must match this stamp byte-for-byte for readiness to pass.

Coverage envelope
-----------------

The canonical documented coverage is 1800-2018 (per
``docs/sources/attributions.md`` § ``polity_v``). The staged
``p5v2018.sav`` carries a small number of rows outside that
envelope (1776-1799 historical backfill and a few 2019-2020 strays);
the readiness gate + transform filter the frame to the canonical
1800-2018 envelope so the descriptor's coverage hint is the
authoritative public contract (the descriptor advertises
1800-2018; the transform emits zero rows for years outside the
envelope).

Observation-family shape
------------------------

Polity V is the second-largest political-freedom source in the
prototype (after V-Dem). The catalog indicators feed the
``political_freedom`` rating category per
``docs/sources/attributions.md`` § ``polity_v``:
``polity`` (regime type), ``polity2`` (revised regime type),
``democ`` (democracy sub-component), ``autoc`` (autocracy
sub-component), ``durable`` (regime durability years), ``xrreg``
(executive recruitment regulation), ``xrcomp`` (executive
recruitment competitiveness), ``xropen`` (executive recruitment
openness), ``xconst`` (executive constraints), ``parreg``
(participatory regulation), and ``parcomp`` (participatory
competition). The descriptor advertises a single observation
family (``political_freedom_country_year``) so downstream query
code can filter by family without consulting the per-source
catalog.

Attribution
-----------

The unified ``POLITY_V_ATTRIBUTION_TEXT`` constant is byte-identical
to the ``polity_v`` section in
``docs/sources/attributions.md`` (Always-On Rule #15). The
:func:`test_polity_v_attribution_text_matches_attributions_doc`
drift guard enforces byte-identity between the code constant and
the docs.

Special-code semantics
----------------------

Polity V component cells carry a documented set of special codes
(``-66`` / ``-77`` / ``-88``) plus the canonical valid range
``-10..+10`` for ``polity`` / ``polity2`` and ``0..10`` for the
sub-component ``democ`` / ``autoc``. The special codes are
meaningful (transitional / interrupted polity / foreign
occupation) but they are NOT numeric observations: the transform
emits ``value=None`` / ``value_type="missing"`` + the verbatim
raw cell text on ``extension.raw_value`` so audit code can
recover the original cell. Valid negative scores
(``-10..-1``) are preserved as numeric observations per the
Stage 5 rubric. See :mod:`._missing_values` for the coercion
matrix.
"""

from __future__ import annotations

from leaders_db.sources.contracts import (
    CoverageHint,
    SourceDescriptor,
    SourceId,
)

# ---------------------------------------------------------------------------
# Canonical Polity V constants
# ---------------------------------------------------------------------------

# Canonical slug. The data-lake folder is also ``polity_v/`` (the
# slug is the folder name; no source-key / folder-alias
# reconciliation is needed). The descriptor's ``source_id.slug``
# is ``"polity_v"`` to match the CLI dispatch key + the legacy
# ``STAGE2_ADAPTERS["polity_v"]`` slot + the attribution key.
POLITY_V_SOURCE_KEY: str = "polity_v"

# Canonical metadata + raw file names. ``metadata.json`` is always
# at the bundle root; the SPSS file is the canonical
# ``p5v2018.sav`` per the live download URL
# (``https://www.systemicpeace.org/inscr/p5v2018.sav``). The
# reader validates the file's presence + the metadata's
# ``local_files`` annotation before opening it.
POLITY_V_METADATA_NAME: str = "metadata.json"
POLITY_V_SAV_NAME: str = "p5v2018.sav"

# Canonical default version -- the exact string the staged
# ``data/raw/polity_v/metadata.json`` must carry under
# ``source_version``. Matches the canonical Polity5 v2018 release
# stamp (Marshall, Jaggers, Gleditsch 2018) and the
# ``docs/sources/attributions.md`` ``polity_v`` section.
POLITY_V_DEFAULT_VERSION: str = "p5v2018"

# Coverage envelope. The canonical documented coverage is
# 1800-2018 per ``docs/sources/attributions.md`` § ``polity_v``
# and the canonical citation block. The staged ``p5v2018.sav``
# carries a small number of rows outside that envelope
# (1776-1799 historical backfill + a few 2019-2020 strays); the
# readiness gate + transform filter the frame to the canonical
# 1800-2018 envelope. The descriptor advertises the canonical
# envelope so downstream query code can refuse to dispatch
# out-of-coverage year requests (SRC-COV-002 / SRC-COV-003).
POLITY_V_COVERAGE_START_YEAR: int = 1800
POLITY_V_COVERAGE_END_YEAR: int = 2018

# Polity V canonical page (the user-facing citation landing
# page, not the direct .sav download URL itself). Matches the
# documented URL in ``docs/sources/attributions.md`` §
# ``polity_v``.
POLITY_V_HOMEPAGE_URL: str = "https://www.systemicpeace.org/polityproject.html"

# Attribution key + canonical text. The text is byte-identical
# to the ``polity_v`` section in
# ``docs/sources/attributions.md`` (Always-On Rule #15). The
# :func:`test_polity_v_attribution_text_matches_attributions_doc`
# drift guard enforces byte-identity.
POLITY_V_ATTRIBUTION_KEY: str = "polity_v"
POLITY_V_ATTRIBUTION_TEXT: str = (
    "Polity V (Marshall, Jaggers, Gleditsch 2018)."
)

# Single observation family: Polity V feeds the political_freedom
# rating category per ``docs/sources/attributions.md`` §
# ``polity_v``. The descriptor advertises this single family so
# downstream query code can filter by ``observation_family ==
# "political_freedom_country_year"`` without consulting the
# per-source catalog. RSF is explicitly NOT a full
# political-freedom replacement -- the ``political_freedom_country_year``
# family is one of several Polity V feeds alongside V-Dem /
# Freedom House / BTI political-transformation / RSF press
# sub-signal / PTS domestic-violence.
POLITY_V_OBSERVATION_FAMILY: str = "political_freedom_country_year"
POLITY_V_SUPPORTED_FAMILIES: tuple[str, ...] = (
    POLITY_V_OBSERVATION_FAMILY,
)

# The 11 Polity V indicator ``variable_name`` values from the
# canonical catalog. Used by the descriptor's coverage notes (so
# the descriptor carries the indicator list without consulting
# the per-source catalog at descriptor-build time) and by the
# per-row emission loop + the public surface.
POLITY_V_INDICATOR_POLITY: str = "polity_v_polity"
POLITY_V_INDICATOR_POLITY2: str = "polity_v_polity2"
POLITY_V_INDICATOR_DEMOC: str = "polity_v_democ"
POLITY_V_INDICATOR_AUTOC: str = "polity_v_autoc"
POLITY_V_INDICATOR_DURABLE: str = "polity_v_durable"
POLITY_V_INDICATOR_XRREG: str = "polity_v_xrreg"
POLITY_V_INDICATOR_XRCOMP: str = "polity_v_xrcomp"
POLITY_V_INDICATOR_XROPEN: str = "polity_v_xropen"
POLITY_V_INDICATOR_XCONST: str = "polity_v_xconst"
POLITY_V_INDICATOR_PARREG: str = "polity_v_parreg"
POLITY_V_INDICATOR_PARCOMP: str = "polity_v_parcomp"
POLITY_V_INDICATOR_NAMES: tuple[str, ...] = (
    POLITY_V_INDICATOR_POLITY,
    POLITY_V_INDICATOR_POLITY2,
    POLITY_V_INDICATOR_DEMOC,
    POLITY_V_INDICATOR_AUTOC,
    POLITY_V_INDICATOR_DURABLE,
    POLITY_V_INDICATOR_XRREG,
    POLITY_V_INDICATOR_XRCOMP,
    POLITY_V_INDICATOR_XROPEN,
    POLITY_V_INDICATOR_XCONST,
    POLITY_V_INDICATOR_PARREG,
    POLITY_V_INDICATOR_PARCOMP,
)

# The 11 Polity V SPSS raw column names (case-sensitive, no
# whitespace). Used by the reader + transform to identify the
# indicator columns in the 37-column header. Matches the canonical
# ``p5v2018.sav`` header verbatim (verified live 2026-06-27 per
# the Polity V ingestion-plan section).
POLITY_V_RAW_COLUMN_POLITY: str = "polity"
POLITY_V_RAW_COLUMN_POLITY2: str = "polity2"
POLITY_V_RAW_COLUMN_DEMOC: str = "democ"
POLITY_V_RAW_COLUMN_AUTOC: str = "autoc"
POLITY_V_RAW_COLUMN_DURABLE: str = "durable"
POLITY_V_RAW_COLUMN_XRREG: str = "xrreg"
POLITY_V_RAW_COLUMN_XRCOMP: str = "xrcomp"
POLITY_V_RAW_COLUMN_XROPEN: str = "xropen"
POLITY_V_RAW_COLUMN_XCONST: str = "xconst"
POLITY_V_RAW_COLUMN_PARREG: str = "parreg"
POLITY_V_RAW_COLUMN_PARCOMP: str = "parcomp"
POLITY_V_RAW_COLUMNS: tuple[str, ...] = (
    POLITY_V_RAW_COLUMN_POLITY,
    POLITY_V_RAW_COLUMN_POLITY2,
    POLITY_V_RAW_COLUMN_DEMOC,
    POLITY_V_RAW_COLUMN_AUTOC,
    POLITY_V_RAW_COLUMN_DURABLE,
    POLITY_V_RAW_COLUMN_XRREG,
    POLITY_V_RAW_COLUMN_XRCOMP,
    POLITY_V_RAW_COLUMN_XROPEN,
    POLITY_V_RAW_COLUMN_XCONST,
    POLITY_V_RAW_COLUMN_PARREG,
    POLITY_V_RAW_COLUMN_PARCOMP,
)

# Identity columns carried on every row for source_row_reference
# + audit trail purposes. The transform does NOT use these for
# filtering (Stage 3 resolves the country code to ISO3 via the
# canonical country table); the columns are preserved as raw
# locator context for audit code.
POLITY_V_RAW_COLUMN_COUNTRY: str = "country"
POLITY_V_RAW_COLUMN_YEAR: str = "year"
POLITY_V_RAW_COLUMN_SCODE: str = "scode"
POLITY_V_RAW_COLUMN_CCODE: str = "ccode"

# Asset id used for the ``p5v2018.sav`` raw asset across all
# observation locators in a single run. Matches the PWT / WGI /
# WDI / V-Dem / UCDP / CPI convention (one logical asset per raw
# bundle) so audit code can group observations by asset.
POLITY_V_SAV_ASSET_ID: str = f"{POLITY_V_SOURCE_KEY}:{POLITY_V_SAV_NAME}"

# Valid range for the ``polity`` / ``polity2`` composite scores.
# Valid negative scores (``-10..-1``) ARE valid numeric
# observations; only the documented special codes (``-66``,
# ``-77``, ``-88``) are non-numeric. See
# :mod:`._missing_values` for the coercion matrix.
POLITY_V_POLITY_SCORE_MIN: int = -10
POLITY_V_POLITY_SCORE_MAX: int = 10

# Valid range for the sub-component scores (``democ`` / ``autoc``
# on a 0-10 scale; ``xrreg`` / ``xrcomp`` / ``xropen`` /
# ``xconst`` / ``parreg`` / ``parcomp`` on lower-bound scales;
# ``durable`` is INDICATOR-SPECIFIC and unbounded above -- see
# :data:`POLITY_V_DURABLE_MIN_VALUE`). The transform validates
# each cell against its indicator-specific valid range + the
# global special-code set.
POLITY_V_COMPONENT_SCORE_MIN: int = 0
POLITY_V_COMPONENT_SCORE_MAX: int = 10

# Documented valid range for the ``durable`` indicator (regime
# durability YEARS counter, per the Polity V codebook). The
# lower bound is 0 (no regime-durability yet); the upper bound
# is intentionally unset because long-running regimes produce
# values well above 10 (the live ``p5v2018.sav`` carries
# ``durable`` values up to 170). The transform treats
# ``durable`` as indicator-specific: special codes
# (``-66`` / ``-77`` / ``-88``) are excluded via the global
# special-code set; negative non-special values are excluded by
# the ``lower`` bound; positive values of any magnitude are
# preserved as numeric observations.
POLITY_V_DURABLE_MIN_VALUE: int = 0

# Documented Polity V special codes (meanings per the Polity V
# codebook). These are NOT numeric observations; the transform
# emits ``value=None`` / ``value_type="missing"`` + the verbatim
# raw cell text on ``extension.raw_value`` for every special-code
# cell. Valid negative scores (``-10..-1``) on ``polity`` /
# ``polity2`` are NOT special codes -- they are valid numeric
# observations and must be preserved as such.
POLITY_V_SPECIAL_CODES: frozenset[int] = frozenset({-66, -77, -88})

# Description of each special code (informational only; the
# transform does not branch on individual codes -- all special
# codes are treated uniformly as missing).
POLITY_V_SPECIAL_CODE_MEANINGS: dict[int, str] = {
    -66: "interregnum / anarchy",
    -77: "foreign occupation / interrupted polity",
    -88: "transition",
}


def build_polity_v_descriptor() -> SourceDescriptor:
    """Build the canonical Polity V :class:`SourceDescriptor`.

    The descriptor is the static metadata the registry exposes for
    source discovery (SRC-ID-003). The values mirror the canonical
    citation block in ``docs/sources/attributions.md`` (Rule #15).

    The descriptor advertises ``source_type="dataset"`` and
    ``requires_network=False`` so downstream query code and the
    runner can refuse to dispatch network I/O unconditionally for
    Polity V (the unified adapter is local-file only by design;
    see ``docs/architecture/sources.md`` §11 SRC-TYPE-001).
    """
    return SourceDescriptor(
        source_id=SourceId(slug=POLITY_V_SOURCE_KEY),
        display_name="Polity V (Polity5 v2018)",
        source_type="dataset",
        supported_observation_families=POLITY_V_SUPPORTED_FAMILIES,
        default_version=POLITY_V_DEFAULT_VERSION,
        homepage_url=POLITY_V_HOMEPAGE_URL,
        attribution_key=POLITY_V_ATTRIBUTION_KEY,
        coverage_hint=CoverageHint(
            start_year=POLITY_V_COVERAGE_START_YEAR,
            end_year=POLITY_V_COVERAGE_END_YEAR,
            countries=None,
            leaders=None,
            notes=(
                "Country-year political-regime / democracy / autocracy "
                "indicators; 167 countries, 1800-2018 (canonical documented "
                "coverage; the staged p5v2018.sav carries a small number "
                "of stray rows outside the envelope -- 1776-1799 historical "
                "backfill + a few 2019-2020 strays -- which the unified "
                "transform filters to the canonical 1800-2018 envelope). "
                "All 11 catalog indicators feed `political_freedom` "
                "alongside V-Dem / Freedom House / BTI political-"
                "transformation / RSF press sub-signal / PTS "
                "domestic-violence. Valid `polity` / `polity2` range is "
                "-10..+10 (valid negative scores are preserved as numeric "
                "observations); sub-component indicators (`democ` / "
                "`autoc` / `xrreg` / `xrcomp` / `xropen` / `xconst` / "
                "`parreg` / `parcomp`) use 0..10; the `durable` indicator "
                "(regime-durability YEARS counter) is INDICATOR-SPECIFIC "
                "with a valid range of >= 0 and NO upper cap "
                "(long-running regimes produce values up to 170 per the "
                "live p5v2018.sav). Documented special codes -66 / -77 / "
                "-88 (interregnum / foreign occupation / transition) are "
                "NOT numeric -- the unified transform emits "
                "`value=None`/`value_type='missing'` + the verbatim raw "
                "cell text on `extension.raw_value` for every special-"
                "code cell. The canonical SPSS file is staged at "
                "`data/raw/polity_v/p5v2018.sav` "
                "(~1.4 MB, 17574 rows x 37 columns, verified live "
                "2026-06-27; SHA-256 "
                "`c0405a807777610a65fe430e4b4828fda16717afc4b5d6e34bf56f1ca100f2f6`). "
                "Reader uses `pyreadstat.read_sav` for the SPSS "
                ".sav format; no HTTP layer "
                "(`requires_network=False`); free academic use; cite "
                "Marshall, Jaggers, Gleditsch 2018 verbatim per the "
                "canonical attribution block."
            ),
        ),
        requires_manual_approval=False,
        requires_network=False,
    )


__all__ = [
    "POLITY_V_ATTRIBUTION_KEY",
    "POLITY_V_ATTRIBUTION_TEXT",
    "POLITY_V_COMPONENT_SCORE_MAX",
    "POLITY_V_COMPONENT_SCORE_MIN",
    "POLITY_V_COVERAGE_END_YEAR",
    "POLITY_V_COVERAGE_START_YEAR",
    "POLITY_V_DEFAULT_VERSION",
    "POLITY_V_DURABLE_MIN_VALUE",
    "POLITY_V_HOMEPAGE_URL",
    "POLITY_V_INDICATOR_AUTOC",
    "POLITY_V_INDICATOR_DEMOC",
    "POLITY_V_INDICATOR_DURABLE",
    "POLITY_V_INDICATOR_NAMES",
    "POLITY_V_INDICATOR_PARCOMP",
    "POLITY_V_INDICATOR_PARREG",
    "POLITY_V_INDICATOR_POLITY",
    "POLITY_V_INDICATOR_POLITY2",
    "POLITY_V_INDICATOR_XCONST",
    "POLITY_V_INDICATOR_XRCOMP",
    "POLITY_V_INDICATOR_XROPEN",
    "POLITY_V_INDICATOR_XRREG",
    "POLITY_V_METADATA_NAME",
    "POLITY_V_OBSERVATION_FAMILY",
    "POLITY_V_POLITY_SCORE_MAX",
    "POLITY_V_POLITY_SCORE_MIN",
    "POLITY_V_RAW_COLUMNS",
    "POLITY_V_RAW_COLUMN_AUTOC",
    "POLITY_V_RAW_COLUMN_CCODE",
    "POLITY_V_RAW_COLUMN_COUNTRY",
    "POLITY_V_RAW_COLUMN_DEMOC",
    "POLITY_V_RAW_COLUMN_DURABLE",
    "POLITY_V_RAW_COLUMN_PARCOMP",
    "POLITY_V_RAW_COLUMN_PARREG",
    "POLITY_V_RAW_COLUMN_POLITY",
    "POLITY_V_RAW_COLUMN_POLITY2",
    "POLITY_V_RAW_COLUMN_SCODE",
    "POLITY_V_RAW_COLUMN_XCONST",
    "POLITY_V_RAW_COLUMN_XRCOMP",
    "POLITY_V_RAW_COLUMN_XROPEN",
    "POLITY_V_RAW_COLUMN_XRREG",
    "POLITY_V_RAW_COLUMN_YEAR",
    "POLITY_V_SAV_ASSET_ID",
    "POLITY_V_SAV_NAME",
    "POLITY_V_SOURCE_KEY",
    "POLITY_V_SPECIAL_CODES",
    "POLITY_V_SPECIAL_CODE_MEANINGS",
    "POLITY_V_SUPPORTED_FAMILIES",
    "build_polity_v_descriptor",
]
