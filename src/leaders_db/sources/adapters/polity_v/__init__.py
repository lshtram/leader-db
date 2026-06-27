"""Unified-source Polity V (Polity5 v2018) adapter.

This package hosts the first source from the
"databases not yet in legacy" list
(``docs/architecture/sources.md`` §7.2 ``polity_v`` row) rebuilt
under the clean ``leaders_db.sources`` interface. The adapter
implements the canonical ``SourceAdapter`` Protocol
(``descriptor`` + ``check_ready`` + ``read_raw`` + ``transform``)
and reads the staged ``p5v2018.sav`` directly via
``pyreadstat.read_sav`` (no legacy Stage 2 module to reuse --
Polity V is the first source with no legacy Stage 2
implementation per the workplan Done History).

The Polity V unified path is local-file only (no network). The
canonical bundle is ``data/raw/polity_v/p5v2018.sav`` plus the
user's runtime-local ``metadata.json`` (gitignored per
Always-On Rule #9). The adapter never invokes the network.

Source-key vs folder-alias reconciliation
-----------------------------------------

The canonical slug is ``polity_v`` (CLI dispatch key + adapter
key + attribution key). The data-lake folder is also
``polity_v/`` (the slug is the folder name; no source-key /
folder-alias reconciliation is needed). The descriptor's
``source_id.slug`` is ``"polity_v"``.

Public surface
--------------

- :data:`POLITY_V_SOURCE_KEY` /
  :data:`POLITY_V_DEFAULT_VERSION` /
  :data:`POLITY_V_SAV_NAME` /
  :data:`POLITY_V_METADATA_NAME` -- the canonical bundle file
  names + version stamp.
- :data:`POLITY_V_COVERAGE_START_YEAR` /
  :data:`POLITY_V_COVERAGE_END_YEAR` -- the canonical 1800-2018
  coverage envelope.
- :data:`POLITY_V_HOMEPAGE_URL` -- the canonical Polity V
  citation landing page.
- :data:`POLITY_V_ATTRIBUTION_KEY` /
  :data:`POLITY_V_ATTRIBUTION_TEXT` -- the canonical citation
  text (Rule #15; byte-identical to
  ``docs/sources/attributions.md`` § ``polity_v``).
- :data:`POLITY_V_OBSERVATION_FAMILY` /
  :data:`POLITY_V_SUPPORTED_FAMILIES` -- the single
  ``political_freedom_country_year`` observation family.
- :data:`POLITY_V_INDICATOR_NAMES` / :data:`POLITY_V_RAW_COLUMNS`
  -- the 11 catalog indicator ``variable_name`` + SPSS raw
  column names.
- :data:`POLITY_V_SPECIAL_CODES` /
  :data:`POLITY_V_SPECIAL_CODE_MEANINGS` -- the documented
  ``-66`` / ``-77`` / ``-88`` sentinel codes that are NOT
  numeric observations.
- :data:`POLITY_V_VALID_NEGATIVE_MIN` /
  :data:`POLITY_V_VALID_NEGATIVE_MAX` -- the documented valid
  negative range for ``polity`` / ``polity2`` (real political-
  freedom observations, NOT special codes).
- :func:`build_polity_v_descriptor` -- factory for the
  canonical :class:`SourceDescriptor`.
- :class:`PolityVAdapter` -- the unified :class:`SourceAdapter`
  implementation.
- :func:`create_polity_v_adapter` -- explicit factory. Callers
  wire it into an :class:`InMemorySourceRegistry` via
  :func:`register_polity_v` or directly. The package does NOT
  auto-register on import (the registry is passive by design --
  see ``docs/architecture/sources.md`` §10.1).
- :func:`register_polity_v` -- explicit registration helper for
  tests and future composition.
"""

from __future__ import annotations

from ._descriptor import (
    POLITY_V_ATTRIBUTION_KEY,
    POLITY_V_ATTRIBUTION_TEXT,
    POLITY_V_COMPONENT_SCORE_MAX,
    POLITY_V_COMPONENT_SCORE_MIN,
    POLITY_V_COVERAGE_END_YEAR,
    POLITY_V_COVERAGE_START_YEAR,
    POLITY_V_DEFAULT_VERSION,
    POLITY_V_DURABLE_MIN_VALUE,
    POLITY_V_HOMEPAGE_URL,
    POLITY_V_INDICATOR_NAMES,
    POLITY_V_METADATA_NAME,
    POLITY_V_OBSERVATION_FAMILY,
    POLITY_V_POLITY_SCORE_MAX,
    POLITY_V_POLITY_SCORE_MIN,
    POLITY_V_RAW_COLUMNS,
    POLITY_V_SAV_ASSET_ID,
    POLITY_V_SAV_NAME,
    POLITY_V_SOURCE_KEY,
    POLITY_V_SPECIAL_CODE_MEANINGS,
    POLITY_V_SPECIAL_CODES,
    POLITY_V_SUPPORTED_FAMILIES,
    build_polity_v_descriptor,
)
from ._missing_values import (
    POLITY_V_VALID_NEGATIVE_MAX,
    POLITY_V_VALID_NEGATIVE_MIN,
)
from ._raw_read import (
    POLITY_V_REQUIRED_IDENTITY_COLUMNS,
    PolityVSchemaError,
    read_polity_v_sav,
)
from ._readiness import (
    check_metadata_well_formed,
    check_source_version,
    collect_request_scoping_warnings,
)
from ._transform import emit_polity_v_observations
from .adapter import (
    POLITY_V_ADAPTER_FACTORY,
    PolityVAdapter,
    create_polity_v_adapter,
    register_polity_v,
)

__all__ = [
    "POLITY_V_ADAPTER_FACTORY",
    "POLITY_V_ATTRIBUTION_KEY",
    "POLITY_V_ATTRIBUTION_TEXT",
    "POLITY_V_COMPONENT_SCORE_MAX",
    "POLITY_V_COMPONENT_SCORE_MIN",
    "POLITY_V_COVERAGE_END_YEAR",
    "POLITY_V_COVERAGE_START_YEAR",
    "POLITY_V_DEFAULT_VERSION",
    "POLITY_V_DURABLE_MIN_VALUE",
    "POLITY_V_HOMEPAGE_URL",
    "POLITY_V_INDICATOR_NAMES",
    "POLITY_V_METADATA_NAME",
    "POLITY_V_OBSERVATION_FAMILY",
    "POLITY_V_POLITY_SCORE_MAX",
    "POLITY_V_POLITY_SCORE_MIN",
    "POLITY_V_RAW_COLUMNS",
    "POLITY_V_REQUIRED_IDENTITY_COLUMNS",
    "POLITY_V_SAV_ASSET_ID",
    "POLITY_V_SAV_NAME",
    "POLITY_V_SOURCE_KEY",
    "POLITY_V_SPECIAL_CODES",
    "POLITY_V_SPECIAL_CODE_MEANINGS",
    "POLITY_V_SUPPORTED_FAMILIES",
    "POLITY_V_VALID_NEGATIVE_MAX",
    "POLITY_V_VALID_NEGATIVE_MIN",
    "PolityVAdapter",
    "PolityVSchemaError",
    "build_polity_v_descriptor",
    "check_metadata_well_formed",
    "check_source_version",
    "collect_request_scoping_warnings",
    "create_polity_v_adapter",
    "emit_polity_v_observations",
    "read_polity_v_sav",
    "register_polity_v",
]
