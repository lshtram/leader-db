"""Phase C / D slice -- semantic indicator concept catalog.

The concept catalog in ``leaders_db.sources.concepts`` exposes stable
cross-source concept keys (``gdp_per_capita``, ``population``,
``gdp_total``) above :class:`NormalizedObservation` and below
scoring / research code. The catalog covers WDI, Maddison, and PWT
for the three stable concepts. Tests cover:

- :func:`list_concepts` exposes the three stable keys, no legacy
  ``leaders_db.ingest`` import.
- :func:`resolve_concept` global and source-specific behavior;
  unknown concept raises :class:`UnknownConceptError`; unsupported
  source raises :class:`UnsupportedConceptSourceError`;
  ``client_existing`` is unsupported for every concept.
- :func:`extract_concept` direct extraction from synthetic
  observations preserves indicator code, input observation id,
  raw locator, transform locator, and source version for WDI and
  Maddison.
- :func:`extract_concept` derivation for PWT GDP-per-capita emits
  one row per valid (country, year) scope with both input
  observation ids, both locators, both source indicator codes,
  the ``derived_concept`` quality flag, and the recipe key in the
  extension payload.
- PWT derivation refuses to emit a row when the denominator is
  missing, non-numeric, zero, ambiguous (multiple numerators or
  denominators per scope), or mismatched on year.
- Direct mappings surface a structured ``missing_value`` warning
  on rows whose input observation has a missing / non-numeric
  value rather than silently dropping the row.
- The package imports never pull in ``leaders_db.ingest`` --
  verified by AST inspection of every concept subpackage source
  module + an addition to the canonical import-boundary submodule
  list in ``tests/sources/test_import_boundary.py``.
- The package does NOT call adapters, instantiate
  :class:`SourceIngestRunner`, or read raw files -- verified by
  monkeypatch sentinels and the AST / sys.modules assertions.
- Optional integration-style test: a real
  :class:`SourceIngestRunner.run` against staged WDI / Maddison /
  PWT fixtures feeds the catalog and produces matching concept rows.

PASS-ELIGIBLE rationale
-----------------------
The catalog is pure transformation over provided
:class:`NormalizedObservation` records. The tests in this file are
PASS-ELIGIBLE because the catalog implementation lands in the same
change set.
"""

from __future__ import annotations

import ast
import hashlib
import json
import shutil
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Test-local constants
# ---------------------------------------------------------------------------

CONCEPT_TEST_PACKAGE: str = "leaders_db.sources.concepts"
CONCEPT_TEST_STABLE_KEYS: tuple[str, ...] = (
    "gdp_per_capita",
    "population",
    "gdp_total",
    "hdi",
    "life_expectancy",
    "gni_per_capita",
    "expected_years_schooling",
    "mean_years_schooling",
    "under5_mortality",
    "bcg_immunization",
    "dtp3_immunization",
    "hepb3_immunization",
    "electoral_democracy",
    "liberal_democracy",
    "civil_liberties",
    "suffrage",
    "rule_of_law",
    "freedom_expression",
    "freedom_association",
    "press_freedom_score",
    "press_freedom_rank",
    "physical_integrity",
    "political_liberties",
    "private_civil_liberties",
    "civil_society_repression",
    "extrajudicial_killings",
    "cirights_physical_integrity",
    "cirights_torture",
    "cirights_disappearances",
    "cirights_killings",
    "cirights_political_imprisonment",
    "cirights_repression",
    "cirights_civil_political_rights",
    "pts_amnesty_score",
    "pts_human_rights_watch_score",
    "pts_state_dept_score",
    "state_based_conflict_events",
    "state_based_conflict_fatalities",
    "internationalized_conflict_events",
    "internationalized_conflict_fatalities",
    "one_sided_violence_events",
    "one_sided_violence_fatalities",
    "corruption_index",
    "cpi_score",
    "control_of_corruption",
    "executive_corruption",
    "public_corruption",
    "accountability",
    "voice_and_accountability",
    "wgi_rule_of_law",
    "government_effectiveness",
    "regulatory_quality",
    "bti_governance_index",
    "bti_status_index",
    "bti_democracy_status",
    "judicial_constraints",
    "legislative_constraints",
    "multiparty_institutions",
    "regime_type",
    "nuclear_total_inventory",
    "nuclear_military_stockpile",
    "nuclear_operational_strategic",
    "nuclear_operational_nonstrategic",
    "nuclear_reserve_nondeployed",
    "nuclear_deployed_warheads",
    "nuclear_retired_warheads",
    "military_spend_constant_usd",
    "military_spend_per_capita",
    "military_spend_share_gdp",
    "military_spend_share_govt",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_observation(
    *,
    source_slug: str,
    indicator_code: str,
    value: Any,
    year: int,
    country_code: str | None,
    country_name: str | None = None,
    source_version: str | None = "v1",
    observation_id: str | None = None,
    unit: str | None = None,
    quality_flags: tuple[str, ...] = (),
) -> Any:
    """Build a synthetic :class:`NormalizedObservation` for tests.

    All other fields (locators, extension, etc.) are filled with
    harmless placeholders so callers only have to specify the
    fields that matter for the catalog's behavior.
    """
    # NaN floats compare unequal to themselves; ``isinstance(int|float)``
    # plus the ``math.isfinite`` guard rejects NaN / inf cleanly
    # without the ``value == value`` self-compare idiom.
    import math

    from leaders_db.sources import (
        NormalizedObservation,
        RawLocator,
        SourceId,
        TransformLocator,
    )

    is_finite_numeric = (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )

    return NormalizedObservation(
        source_id=SourceId(slug=source_slug),
        observation_id=(
            observation_id
            if observation_id is not None
            else f"{source_slug}:{country_code or country_name}:{year}:{indicator_code}"
        ),
        observation_family="economic_country_year",
        indicator_code=indicator_code,
        value=value,
        value_type="numeric" if is_finite_numeric else "missing",
        year=year,
        country_code=country_code,
        country_name=country_name,
        leader_id=None,
        leader_name=None,
        unit=unit,
        scale=None,
        source_version=source_version,
        raw_locator=RawLocator(asset_id=f"{source_slug}:test"),
        transform_locator=TransformLocator(
            transform_name="test_transform",
        ),
        quality_flags=quality_flags,
        warnings=(),
        extension={},
    )


# ---------------------------------------------------------------------------
# list_concepts
# ---------------------------------------------------------------------------


def test_list_concepts_exposes_stable_keys() -> None:
    """``list_concepts()`` returns exactly the documented stable keys."""
    from leaders_db.sources.concepts import (
        CONCEPT_ACCOUNTABILITY,
        CONCEPT_BCG_IMMUNIZATION,
        CONCEPT_BTI_DEMOCRACY_STATUS,
        CONCEPT_BTI_GOVERNANCE_INDEX,
        CONCEPT_BTI_STATUS_INDEX,
        CONCEPT_CIRIGHTS_CIVIL_POLITICAL_RIGHTS,
        CONCEPT_CIRIGHTS_DISAPPEARANCES,
        CONCEPT_CIRIGHTS_KILLINGS,
        CONCEPT_CIRIGHTS_PHYSICAL_INTEGRITY,
        CONCEPT_CIRIGHTS_POLITICAL_IMPRISONMENT,
        CONCEPT_CIRIGHTS_REPRESSION,
        CONCEPT_CIRIGHTS_TORTURE,
        CONCEPT_CIVIL_LIBERTIES,
        CONCEPT_CIVIL_SOCIETY_REPRESSION,
        CONCEPT_CONTROL_OF_CORRUPTION,
        CONCEPT_CORRUPTION_INDEX,
        CONCEPT_CPI_SCORE,
        CONCEPT_DTP3_IMMUNIZATION,
        CONCEPT_EIU_CIVIL_LIBERTIES,
        CONCEPT_EIU_DEMOCRACY_OVERALL_SCORE,
        CONCEPT_EIU_ELECTORAL_PROCESS,
        CONCEPT_EIU_FUNCTIONING_GOVERNMENT,
        CONCEPT_EIU_POLITICAL_CULTURE,
        CONCEPT_EIU_POLITICAL_PARTICIPATION,
        CONCEPT_ELECTORAL_DEMOCRACY,
        CONCEPT_EXECUTIVE_CORRUPTION,
        CONCEPT_EXPECTED_YEARS_SCHOOLING,
        CONCEPT_EXTRAJUDICIAL_KILLINGS,
        CONCEPT_FREEDOM_ASSOCIATION,
        CONCEPT_FREEDOM_EXPRESSION,
        CONCEPT_GDP_PER_CAPITA,
        CONCEPT_GDP_TOTAL,
        CONCEPT_GNI_PER_CAPITA,
        CONCEPT_GOVERNMENT_EFFECTIVENESS,
        CONCEPT_HDI,
        CONCEPT_HEPB3_IMMUNIZATION,
        CONCEPT_INTERNATIONALIZED_CONFLICT_EVENTS,
        CONCEPT_INTERNATIONALIZED_CONFLICT_FATALITIES,
        CONCEPT_JUDICIAL_CONSTRAINTS,
        CONCEPT_LEGISLATIVE_CONSTRAINTS,
        CONCEPT_LIBERAL_DEMOCRACY,
        CONCEPT_LIFE_EXPECTANCY,
        CONCEPT_MEAN_YEARS_SCHOOLING,
        CONCEPT_MILITARY_SPEND_CONSTANT_USD,
        CONCEPT_MILITARY_SPEND_PER_CAPITA,
        CONCEPT_MILITARY_SPEND_SHARE_GDP,
        CONCEPT_MILITARY_SPEND_SHARE_GOVT,
        CONCEPT_MULTIPARTY_INSTITUTIONS,
        CONCEPT_NUCLEAR_DEPLOYED,
        CONCEPT_NUCLEAR_MILITARY_STOCKPILE,
        CONCEPT_NUCLEAR_OPERATIONAL_NONSTRATEGIC,
        CONCEPT_NUCLEAR_OPERATIONAL_STRATEGIC,
        CONCEPT_NUCLEAR_RESERVE_NONDEPLOYED,
        CONCEPT_NUCLEAR_RETIRED,
        CONCEPT_NUCLEAR_TOTAL_INVENTORY,
        CONCEPT_ONE_SIDED_VIOLENCE_EVENTS,
        CONCEPT_ONE_SIDED_VIOLENCE_FATALITIES,
        CONCEPT_PHYSICAL_INTEGRITY,
        CONCEPT_POLITICAL_LIBERTIES,
        CONCEPT_POLITY_AUTOCRACY_SCORE,
        CONCEPT_POLITY_COMPOSITE_SCORE,
        CONCEPT_POLITY_DEMOCRACY_SCORE,
        CONCEPT_POLITY_EXECUTIVE_CONSTRAINTS,
        CONCEPT_POLITY_REGIME_DURABILITY,
        CONCEPT_POPULATION,
        CONCEPT_PRESS_FREEDOM_RANK,
        CONCEPT_PRESS_FREEDOM_SCORE,
        CONCEPT_PRIVATE_CIVIL_LIBERTIES,
        CONCEPT_PTS_AMNESTY_SCORE,
        CONCEPT_PTS_HUMAN_RIGHTS_WATCH_SCORE,
        CONCEPT_PTS_STATE_DEPT_SCORE,
        CONCEPT_PUBLIC_CORRUPTION,
        CONCEPT_PWT_AVERAGE_ANNUAL_HOURS,
        CONCEPT_PWT_CAPITAL_STOCK_INDEX,
        CONCEPT_PWT_EMPLOYMENT,
        CONCEPT_PWT_HUMAN_CAPITAL,
        CONCEPT_PWT_REAL_CONSUMPTION,
        CONCEPT_PWT_REAL_DOMESTIC_ABSORPTION,
        CONCEPT_PWT_TFP_CONSTANT_PRICES,
        CONCEPT_REGIME_TYPE,
        CONCEPT_REGULATORY_QUALITY,
        CONCEPT_RULE_OF_LAW,
        CONCEPT_STATE_BASED_CONFLICT_EVENTS,
        CONCEPT_STATE_BASED_CONFLICT_FATALITIES,
        CONCEPT_SUFFRAGE,
        CONCEPT_UNDER5_MORTALITY,
        CONCEPT_VOICE_AND_ACCOUNTABILITY,
        CONCEPT_WDI_ADULT_LITERACY,
        CONCEPT_WDI_GINI_INDEX,
        CONCEPT_WDI_SECONDARY_ENROLLMENT,
        CONCEPT_WGI_RULE_OF_LAW,
        KNOWN_CONCEPT_KEYS,
        list_concepts,
    )

    descriptors = list_concepts()
    keys = tuple(d.concept_key for d in descriptors)
    assert keys == (
        CONCEPT_GDP_PER_CAPITA,
        CONCEPT_POPULATION,
        CONCEPT_GDP_TOTAL,
        CONCEPT_POLITY_COMPOSITE_SCORE,
        CONCEPT_POLITY_DEMOCRACY_SCORE,
        CONCEPT_POLITY_AUTOCRACY_SCORE,
        CONCEPT_POLITY_EXECUTIVE_CONSTRAINTS,
        CONCEPT_POLITY_REGIME_DURABILITY,
        CONCEPT_EIU_DEMOCRACY_OVERALL_SCORE,
        CONCEPT_EIU_ELECTORAL_PROCESS,
        CONCEPT_EIU_FUNCTIONING_GOVERNMENT,
        CONCEPT_EIU_POLITICAL_PARTICIPATION,
        CONCEPT_EIU_POLITICAL_CULTURE,
        CONCEPT_EIU_CIVIL_LIBERTIES,
        CONCEPT_PWT_EMPLOYMENT,
        CONCEPT_PWT_AVERAGE_ANNUAL_HOURS,
        CONCEPT_PWT_HUMAN_CAPITAL,
        CONCEPT_PWT_REAL_CONSUMPTION,
        CONCEPT_PWT_REAL_DOMESTIC_ABSORPTION,
        CONCEPT_PWT_CAPITAL_STOCK_INDEX,
        CONCEPT_PWT_TFP_CONSTANT_PRICES,
        CONCEPT_WDI_GINI_INDEX,
        CONCEPT_WDI_ADULT_LITERACY,
        CONCEPT_WDI_SECONDARY_ENROLLMENT,
        CONCEPT_HDI,
        CONCEPT_LIFE_EXPECTANCY,
        CONCEPT_GNI_PER_CAPITA,
        CONCEPT_EXPECTED_YEARS_SCHOOLING,
        CONCEPT_MEAN_YEARS_SCHOOLING,
        CONCEPT_UNDER5_MORTALITY,
        CONCEPT_BCG_IMMUNIZATION,
        CONCEPT_DTP3_IMMUNIZATION,
        CONCEPT_HEPB3_IMMUNIZATION,
        CONCEPT_ELECTORAL_DEMOCRACY,
        CONCEPT_LIBERAL_DEMOCRACY,
        CONCEPT_CIVIL_LIBERTIES,
        CONCEPT_SUFFRAGE,
        CONCEPT_RULE_OF_LAW,
        CONCEPT_FREEDOM_EXPRESSION,
        CONCEPT_FREEDOM_ASSOCIATION,
        CONCEPT_PRESS_FREEDOM_SCORE,
        CONCEPT_PRESS_FREEDOM_RANK,
        CONCEPT_PHYSICAL_INTEGRITY,
        CONCEPT_POLITICAL_LIBERTIES,
        CONCEPT_PRIVATE_CIVIL_LIBERTIES,
        CONCEPT_CIVIL_SOCIETY_REPRESSION,
        CONCEPT_EXTRAJUDICIAL_KILLINGS,
        CONCEPT_CIRIGHTS_PHYSICAL_INTEGRITY,
        CONCEPT_CIRIGHTS_TORTURE,
        CONCEPT_CIRIGHTS_DISAPPEARANCES,
        CONCEPT_CIRIGHTS_KILLINGS,
        CONCEPT_CIRIGHTS_POLITICAL_IMPRISONMENT,
        CONCEPT_CIRIGHTS_REPRESSION,
        CONCEPT_CIRIGHTS_CIVIL_POLITICAL_RIGHTS,
        CONCEPT_PTS_AMNESTY_SCORE,
        CONCEPT_PTS_HUMAN_RIGHTS_WATCH_SCORE,
        CONCEPT_PTS_STATE_DEPT_SCORE,
        CONCEPT_STATE_BASED_CONFLICT_EVENTS,
        CONCEPT_STATE_BASED_CONFLICT_FATALITIES,
        CONCEPT_INTERNATIONALIZED_CONFLICT_EVENTS,
        CONCEPT_INTERNATIONALIZED_CONFLICT_FATALITIES,
        CONCEPT_ONE_SIDED_VIOLENCE_EVENTS,
        CONCEPT_ONE_SIDED_VIOLENCE_FATALITIES,
        CONCEPT_CORRUPTION_INDEX,
        CONCEPT_CPI_SCORE,
        CONCEPT_CONTROL_OF_CORRUPTION,
        CONCEPT_EXECUTIVE_CORRUPTION,
        CONCEPT_PUBLIC_CORRUPTION,
        CONCEPT_ACCOUNTABILITY,
        CONCEPT_VOICE_AND_ACCOUNTABILITY,
        CONCEPT_WGI_RULE_OF_LAW,
        CONCEPT_GOVERNMENT_EFFECTIVENESS,
        CONCEPT_REGULATORY_QUALITY,
        CONCEPT_BTI_GOVERNANCE_INDEX,
        CONCEPT_BTI_STATUS_INDEX,
        CONCEPT_BTI_DEMOCRACY_STATUS,
        CONCEPT_JUDICIAL_CONSTRAINTS,
        CONCEPT_LEGISLATIVE_CONSTRAINTS,
        CONCEPT_MULTIPARTY_INSTITUTIONS,
        CONCEPT_REGIME_TYPE,
        CONCEPT_NUCLEAR_TOTAL_INVENTORY,
        CONCEPT_NUCLEAR_MILITARY_STOCKPILE,
        CONCEPT_NUCLEAR_OPERATIONAL_STRATEGIC,
        CONCEPT_NUCLEAR_OPERATIONAL_NONSTRATEGIC,
        CONCEPT_NUCLEAR_RESERVE_NONDEPLOYED,
        CONCEPT_NUCLEAR_DEPLOYED,
        CONCEPT_NUCLEAR_RETIRED,
        CONCEPT_MILITARY_SPEND_CONSTANT_USD,
        CONCEPT_MILITARY_SPEND_PER_CAPITA,
        CONCEPT_MILITARY_SPEND_SHARE_GDP,
        CONCEPT_MILITARY_SPEND_SHARE_GOVT,
    )
    assert keys == KNOWN_CONCEPT_KEYS

    # Every descriptor carries a non-empty display_name +
    # description so callers have something to render in
    # documentation / UI surfaces.
    for descriptor in descriptors:
        assert descriptor.concept_key
        assert descriptor.display_name
        assert descriptor.description


def test_concepts_package_import_does_not_import_legacy_ingest() -> None:
    """``import leaders_db.sources.concepts`` MUST NOT import legacy ingest.

    The concept catalog is part of the clean source subsystem
    boundary (SRC-MIG-007 + docs/architecture/sources.md §10.1).
    A fresh-interpreter import of the package must not pull
    ``leaders_db.ingest`` into ``sys.modules`` as a side effect.

    The assertion inspects ``sys.modules`` after a controlled
    ``importlib.import_module`` call preceded by a
    ``sys.modules`` purge of every cached ``leaders_db.*`` entry.
    """
    import importlib
    import sys

    from leaders_db.sources import concepts as concepts_pkg

    _purge_source_boundary_modules(sys.modules)
    try:
        importlib.import_module(CONCEPT_TEST_PACKAGE)
        leaked = sorted(
            name
            for name in sys.modules
            if name == "leaders_db.ingest" or name.startswith("leaders_db.ingest.")
        )
        assert leaked == [], (
            f"importing {CONCEPT_TEST_PACKAGE} must not import "
            f"leaders_db.ingest (leaked modules: {leaked})"
        )
    finally:
        _purge_source_boundary_modules(sys.modules)

    # Sanity: the package object is importable on its own.
    assert concepts_pkg.__name__ == CONCEPT_TEST_PACKAGE


def test_polity_executive_constraints_keeps_source_native_semantics() -> None:
    from leaders_db.sources.concepts import (
        CONCEPT_POLITY_EXECUTIVE_CONSTRAINTS,
        POLITY_V_EXECUTIVE_CONSTRAINTS_INDICATOR_CODE,
        extract_concept,
    )

    source = _make_observation(
        source_slug="polity_v",
        indicator_code=POLITY_V_EXECUTIVE_CONSTRAINTS_INDICATOR_CODE,
        value=4,
        year=2018,
        country_code="RUS",
        unit="ordinal_score",
    )
    rows = extract_concept((source,), CONCEPT_POLITY_EXECUTIVE_CONSTRAINTS)

    assert len(rows) == 1
    assert rows[0].concept_key == "polity_executive_constraints"
    assert rows[0].source_indicator_codes == (POLITY_V_EXECUTIVE_CONSTRAINTS_INDICATOR_CODE,)
    assert rows[0].value == 4


def test_eiu_component_is_a_direct_source_native_concept() -> None:
    from leaders_db.sources.concepts import (
        CONCEPT_EIU_CIVIL_LIBERTIES,
        EIU_CIVIL_LIBERTIES_INDICATOR_CODE,
        extract_concept,
    )

    source = _make_observation(
        source_slug="eiu_democracy_index",
        indicator_code=EIU_CIVIL_LIBERTIES_INDICATOR_CODE,
        value=2.35,
        year=2022,
        country_code=None,
        country_name="Russia",
        unit="index_score",
    )
    rows = extract_concept((source,), CONCEPT_EIU_CIVIL_LIBERTIES)

    assert len(rows) == 1
    assert rows[0].mapping_type == "direct"
    assert rows[0].source_indicator_codes == (EIU_CIVIL_LIBERTIES_INDICATOR_CODE,)
    assert rows[0].value == 2.35


def test_pwt_employment_keeps_count_semantics() -> None:
    from leaders_db.sources.concepts import (
        CONCEPT_PWT_EMPLOYMENT,
        PWT_EMPLOYMENT_INDICATOR_CODE,
        extract_concept,
        resolve_concept,
    )

    source = _make_observation(
        source_slug="pwt",
        indicator_code=PWT_EMPLOYMENT_INDICATOR_CODE,
        value=71.67,
        year=2019,
        country_code="RUS",
        unit="million_persons_engaged",
    )
    rows = extract_concept((source,), CONCEPT_PWT_EMPLOYMENT)

    assert len(rows) == 1
    assert rows[0].unit == "million_persons_engaged"
    assert "unemployment-rate proxy" in (resolve_concept(CONCEPT_PWT_EMPLOYMENT)[0].notes or "")


def test_wdi_gini_concept_keeps_source_native_scale() -> None:
    from leaders_db.sources.concepts import (
        CONCEPT_WDI_GINI_INDEX,
        WDI_GINI_INDEX_INDICATOR_CODE,
        extract_concept,
    )

    source = _make_observation(
        source_slug="world_bank_wdi",
        indicator_code=WDI_GINI_INDEX_INDICATOR_CODE,
        value=33.9,
        year=2022,
        country_code="RUS",
        unit="index points (0-100)",
    )
    rows = extract_concept((source,), CONCEPT_WDI_GINI_INDEX)

    assert len(rows) == 1
    assert rows[0].value == 33.9
    assert rows[0].unit == "index points (0-100)"


def _purge_source_boundary_modules(modules: dict[str, object]) -> None:
    for name in list(modules):
        if (
            name == "leaders_db.sources"
            or name.startswith("leaders_db.sources.")
            or name == "leaders_db.ingest"
            or name.startswith("leaders_db.ingest.")
        ):
            del modules[name]
    parent = modules.get("leaders_db")
    if parent is not None:
        for attr in ("sources", "ingest"):
            if hasattr(parent, attr):
                delattr(parent, attr)


def test_concepts_module_does_not_import_legacy_ingest_at_import() -> None:
    """Every ``leaders_db.sources.concepts._*`` module's source file
    has NO eager top-level ``leaders_db.ingest`` imports.

    Defense in depth: even if a future contributor adds a new
    helper module that re-exports public names, every submodule
    under the package must keep the package-isolation rule. The
    AST check is non-destructive -- it only walks the source code
    -- and the deliberate ``PLC0415`` ruff ignore in
    ``pyproject.toml`` keeps the lazy-imports contract enforceable
    without forcing module-level eager imports.
    """
    submodules = (
        ("leaders_db.sources.concepts", "__init__.py"),
        ("leaders_db.sources.concepts._api", "_api.py"),
        ("leaders_db.sources.concepts._catalog", "_catalog.py"),
        ("leaders_db.sources.concepts._dataclasses", "_dataclasses.py"),
        ("leaders_db.sources.concepts._derived", "_derived.py"),
        ("leaders_db.sources.concepts._derived_reasons", "_derived_reasons.py"),
        ("leaders_db.sources.concepts._direct", "_direct.py"),
    )
    repo_root = Path(__file__).resolve().parents[2]
    package_root = repo_root / "src" / "leaders_db" / "sources" / "concepts"

    for _submodule_name, file_name in submodules:
        path = package_root / file_name
        assert path.exists(), f"missing submodule source: {path}"
        tree = ast.parse(path.read_text(encoding="utf-8"))

        legacy_top_level: list[str] = []
        for node in tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("leaders_db.ingest"):
                        legacy_top_level.append(f"import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module.startswith("leaders_db.ingest"):
                    legacy_top_level.append(
                        f"from {module} import ...",
                    )

        assert legacy_top_level == [], (
            f"{path} has eager top-level legacy ingest imports; "
            f"the new concept catalog must import legacy code "
            f"lazily (or not at all) per SRC-MIG-007. Found: "
            f"{legacy_top_level}"
        )


# ---------------------------------------------------------------------------
# resolve_concept: global + source-specific behavior + error paths
# ---------------------------------------------------------------------------


def test_resolve_concept_global_returns_all_source_mappings() -> None:
    """``resolve_concept(concept_key)`` returns one mapping per supported source.

    For ``gdp_per_capita``, the canonical sources are WDI, Maddison,
    and PWT. The function returns one :class:`ConceptMapping` per
    source; the WDI mapping lists two indicator codes (current USD
    and PPP constant 2017), the PWT mapping is ``derived``, and
    Maddison is ``direct``.
    """
    from leaders_db.sources.concepts import (
        CONCEPT_GDP_PER_CAPITA,
        MADDISON_PROJECT_SOURCE_KEY,
        PWT_SOURCE_KEY,
        WDI_SOURCE_KEY,
        resolve_concept,
    )

    mappings = resolve_concept(CONCEPT_GDP_PER_CAPITA)
    slugs = {m.source_id.slug for m in mappings}
    assert slugs == {WDI_SOURCE_KEY, MADDISON_PROJECT_SOURCE_KEY, PWT_SOURCE_KEY}

    # WDI mapping is direct + carries two indicator codes.
    wdi_mapping = next(m for m in mappings if m.source_id.slug == WDI_SOURCE_KEY)
    assert wdi_mapping.mapping_type == "direct"
    assert len(wdi_mapping.indicator_codes) == 2

    # PWT mapping is derived + carries the documented recipe key.
    pwt_mapping = next(m for m in mappings if m.source_id.slug == PWT_SOURCE_KEY)
    assert pwt_mapping.mapping_type == "derived"
    assert pwt_mapping.recipe_key is not None


def test_resolve_concept_source_specific_narrows_to_single_mapping() -> None:
    """``resolve_concept(key, source_id=...)`` narrows to one source.

    Accepts a :class:`SourceId`, a source-slug string, or
    ``None``; the result is the single mapping for the requested
    source. The Maddison ``gdp_total`` mapping is direct (the
    indicator is already derived by the Stage 2 reader).
    """
    from leaders_db.sources import SourceId
    from leaders_db.sources.concepts import (
        CONCEPT_GDP_TOTAL,
        MADDISON_PROJECT_SOURCE_KEY,
        resolve_concept,
    )

    by_str = resolve_concept(
        CONCEPT_GDP_TOTAL,
        source_id=MADDISON_PROJECT_SOURCE_KEY,
    )
    by_id = resolve_concept(
        CONCEPT_GDP_TOTAL,
        source_id=SourceId(slug=MADDISON_PROJECT_SOURCE_KEY),
    )
    assert len(by_str) == 1
    assert by_str == by_id
    assert by_str[0].source_id.slug == MADDISON_PROJECT_SOURCE_KEY
    assert by_str[0].mapping_type == "direct"


def test_resolve_concept_includes_freedom_house_political_rights() -> None:
    """Freedom House political-rights rows map to political liberties."""
    from leaders_db.sources.concepts import (
        CONCEPT_POLITICAL_LIBERTIES,
        FREEDOM_HOUSE_POLITICAL_RIGHTS_INDICATOR_CODE,
        FREEDOM_HOUSE_SOURCE_KEY,
        resolve_concept,
    )

    mappings = resolve_concept(
        CONCEPT_POLITICAL_LIBERTIES,
        source_id=FREEDOM_HOUSE_SOURCE_KEY,
    )

    assert len(mappings) == 1
    assert mappings[0].mapping_type == "direct"
    assert mappings[0].indicator_codes == (FREEDOM_HOUSE_POLITICAL_RIGHTS_INDICATOR_CODE,)


def test_resolve_concept_unknown_concept_key_raises_actionable_error() -> None:
    """An unknown concept key raises :class:`UnknownConceptError` naming known keys."""
    from leaders_db.sources.concepts import (
        KNOWN_CONCEPT_KEYS,
        UnknownConceptError,
        resolve_concept,
    )

    with pytest.raises(UnknownConceptError) as exc_info:
        resolve_concept("not_a_real_concept")

    msg = str(exc_info.value)
    assert "not_a_real_concept" in msg
    for known_key in KNOWN_CONCEPT_KEYS:
        assert known_key in msg, (
            f"error message must list known keys for actionable debugging; got {msg!r}"
        )


def test_resolve_concept_unsupported_source_raises_actionable_error() -> None:
    """An unsupported concept/source pair raises :class:`UnsupportedConceptSourceError`."""
    from leaders_db.sources.concepts import (
        CONCEPT_GDP_PER_CAPITA,
        PWT_SOURCE_KEY,
        UnsupportedConceptSourceError,
        resolve_concept,
    )

    with pytest.raises(UnsupportedConceptSourceError) as exc_info:
        resolve_concept(CONCEPT_GDP_PER_CAPITA, source_id="maddison_project_xl")
    msg = str(exc_info.value)
    assert CONCEPT_GDP_PER_CAPITA in msg
    assert "maddison_project_xl" in msg
    # The error must list the supported sources so a developer can
    # pick a valid one or extend the catalog.
    assert PWT_SOURCE_KEY in msg


def test_resolve_concept_client_existing_is_unsupported_for_every_concept() -> None:
    """``client_existing`` has no concept mappings per SRC-CONCEPT-010.

    The client matrix is validation-only; resolving any concept
    for it raises :class:`UnsupportedConceptSourceError` with a
    clear message so a developer cannot accidentally treat client
    data as evidence for source agreement.
    """
    from leaders_db.sources.concepts import (
        CLIENT_EXISTING_SOURCE_KEY,
        CONCEPT_GDP_PER_CAPITA,
        CONCEPT_GDP_TOTAL,
        CONCEPT_POPULATION,
        UnsupportedConceptSourceError,
        resolve_concept,
    )

    for concept_key in (
        CONCEPT_GDP_PER_CAPITA,
        CONCEPT_POPULATION,
        CONCEPT_GDP_TOTAL,
    ):
        with pytest.raises(UnsupportedConceptSourceError) as exc_info:
            resolve_concept(concept_key, source_id=CLIENT_EXISTING_SOURCE_KEY)
        msg = str(exc_info.value)
        assert concept_key in msg
        assert CLIENT_EXISTING_SOURCE_KEY in msg


# ---------------------------------------------------------------------------
# extract_concept: direct WDI / Maddison extraction
# ---------------------------------------------------------------------------


def test_extract_concept_wdi_direct_gdp_per_capita_emits_two_rows() -> None:
    """WDI ``gdp_per_capita`` has two indicator codes; extraction emits one
    :class:`ConceptObservation` per matching input observation.
    """
    from leaders_db.sources.concepts import (
        CONCEPT_GDP_PER_CAPITA,
        WDI_GDP_PER_CAPITA_INDICATOR_CODE,
        WDI_GDP_PER_CAPITA_PPP_CONSTANT_2017_INDICATOR_CODE,
        WDI_SOURCE_KEY,
        extract_concept,
    )

    observations = [
        _make_observation(
            source_slug=WDI_SOURCE_KEY,
            indicator_code=WDI_GDP_PER_CAPITA_INDICATOR_CODE,
            value=70_000.0,
            year=2023,
            country_code="USA",
        ),
        _make_observation(
            source_slug=WDI_SOURCE_KEY,
            indicator_code=WDI_GDP_PER_CAPITA_PPP_CONSTANT_2017_INDICATOR_CODE,
            value=75_000.0,
            year=2023,
            country_code="USA",
        ),
    ]
    rows = extract_concept(observations, CONCEPT_GDP_PER_CAPITA, WDI_SOURCE_KEY)

    assert len(rows) == 2, (
        "WDI gdp_per_capita has two source-indicator codes; "
        "extraction must emit one ConceptObservation per matching "
        "observation, so two matching observations produce two rows."
    )

    # Indicator codes preserved verbatim.
    emitted_codes = {row.source_indicator_codes[0] for row in rows}
    assert emitted_codes == {
        WDI_GDP_PER_CAPITA_INDICATOR_CODE,
        WDI_GDP_PER_CAPITA_PPP_CONSTANT_2017_INDICATOR_CODE,
    }

    # Values, country, year, source_version, mapping_type preserved.
    for row in rows:
        assert row.concept_key == CONCEPT_GDP_PER_CAPITA
        assert row.source_id.slug == WDI_SOURCE_KEY
        assert row.mapping_type == "direct"
        assert row.recipe_key is None
        assert row.country_code == "USA"
        assert row.year == 2023
        assert row.value in (70_000.0, 75_000.0)
        # Input observation id is preserved so audit can resolve
        # back to the canonical source record.
        assert len(row.input_observation_ids) == 1
        # Raw + transform locators are propagated.
        assert len(row.raw_locators) == 1
        assert len(row.transform_locators) == 1


def test_extract_concept_wdi_direct_population_preserves_indicator() -> None:
    """WDI ``population`` extraction preserves the source-specific indicator.

    The Maddison ``population`` is in thousands; the WDI
    ``population`` is in absolute persons. The catalog preserves
    both raw indicators verbatim -- callers must consult
    ``unit`` / ``extension`` for scale-specific metadata.
    """
    from leaders_db.sources.concepts import (
        CONCEPT_POPULATION,
        WDI_POPULATION_INDICATOR_CODE,
        WDI_SOURCE_KEY,
        extract_concept,
    )

    observations = [
        _make_observation(
            source_slug=WDI_SOURCE_KEY,
            indicator_code=WDI_POPULATION_INDICATOR_CODE,
            value=333_000_000.0,
            year=2023,
            country_code="USA",
        ),
    ]
    rows = extract_concept(
        observations,
        CONCEPT_POPULATION,
        WDI_SOURCE_KEY,
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.source_indicator_codes == (WDI_POPULATION_INDICATOR_CODE,)
    assert row.value == 333_000_000.0
    assert row.input_observation_ids[0].startswith(
        f"{WDI_SOURCE_KEY}:USA:2023:",
    )


def test_extract_concept_social_development_direct_mappings() -> None:
    """D10 social-development concepts alias UNDP/WHO observations directly."""
    from leaders_db.sources.concepts import (
        CONCEPT_DTP3_IMMUNIZATION,
        CONCEPT_HDI,
        UNDP_HDI_INDICATOR_CODE,
        UNDP_HDI_SOURCE_KEY,
        WHO_GHO_API_SOURCE_KEY,
        WHO_GHO_DTP3_IMMUNIZATION_INDICATOR_CODE,
        extract_concept,
    )

    observations = [
        _make_observation(
            source_slug=UNDP_HDI_SOURCE_KEY,
            indicator_code=UNDP_HDI_INDICATOR_CODE,
            value=0.92,
            year=2022,
            country_code="USA",
        ),
        _make_observation(
            source_slug=WHO_GHO_API_SOURCE_KEY,
            indicator_code=WHO_GHO_DTP3_IMMUNIZATION_INDICATOR_CODE,
            value=94.0,
            year=2022,
            country_code="USA",
        ),
    ]

    hdi_rows = extract_concept(observations, CONCEPT_HDI, UNDP_HDI_SOURCE_KEY)
    immunization_rows = extract_concept(
        observations,
        CONCEPT_DTP3_IMMUNIZATION,
        WHO_GHO_API_SOURCE_KEY,
    )

    assert hdi_rows[0].source_indicator_codes == (UNDP_HDI_INDICATOR_CODE,)
    assert hdi_rows[0].value == 0.92
    assert immunization_rows[0].source_indicator_codes == (
        WHO_GHO_DTP3_IMMUNIZATION_INDICATOR_CODE,
    )
    assert immunization_rows[0].value == 94.0


def test_extract_concept_political_freedom_direct_mappings() -> None:
    """D11 political-freedom concepts alias V-Dem, FH, and RSF observations."""
    from leaders_db.sources.concepts import (
        CONCEPT_CIVIL_LIBERTIES,
        CONCEPT_ELECTORAL_DEMOCRACY,
        CONCEPT_POLITICAL_LIBERTIES,
        CONCEPT_PRESS_FREEDOM_SCORE,
        FREEDOM_HOUSE_CIVIL_LIBERTIES_INDICATOR_CODE,
        FREEDOM_HOUSE_POLITICAL_RIGHTS_INDICATOR_CODE,
        FREEDOM_HOUSE_SOURCE_KEY,
        RSF_PRESS_FREEDOM_SCORE_INDICATOR_CODE,
        RSF_PRESS_FREEDOM_SOURCE_KEY,
        VDEM_ELECTORAL_DEMOCRACY_INDICATOR_CODE,
        VDEM_SOURCE_KEY,
        extract_concept,
    )

    observations = [
        _make_observation(
            source_slug=VDEM_SOURCE_KEY,
            indicator_code=VDEM_ELECTORAL_DEMOCRACY_INDICATOR_CODE,
            value=0.83,
            year=2020,
            country_code="USA",
        ),
        _make_observation(
            source_slug=FREEDOM_HOUSE_SOURCE_KEY,
            indicator_code=FREEDOM_HOUSE_POLITICAL_RIGHTS_INDICATOR_CODE,
            value=1,
            year=2020,
            country_code="USA",
        ),
        _make_observation(
            source_slug=FREEDOM_HOUSE_SOURCE_KEY,
            indicator_code=FREEDOM_HOUSE_CIVIL_LIBERTIES_INDICATOR_CODE,
            value=2,
            year=2020,
            country_code="USA",
        ),
        _make_observation(
            source_slug=RSF_PRESS_FREEDOM_SOURCE_KEY,
            indicator_code=RSF_PRESS_FREEDOM_SCORE_INDICATOR_CODE,
            value=72.4,
            year=2020,
            country_code="USA",
        ),
    ]

    democracy_rows = extract_concept(
        observations,
        CONCEPT_ELECTORAL_DEMOCRACY,
        VDEM_SOURCE_KEY,
    )
    political_rights_rows = extract_concept(
        observations,
        CONCEPT_POLITICAL_LIBERTIES,
        FREEDOM_HOUSE_SOURCE_KEY,
    )
    civil_liberties_rows = extract_concept(
        observations,
        CONCEPT_CIVIL_LIBERTIES,
        FREEDOM_HOUSE_SOURCE_KEY,
    )
    press_rows = extract_concept(
        observations,
        CONCEPT_PRESS_FREEDOM_SCORE,
        RSF_PRESS_FREEDOM_SOURCE_KEY,
    )

    assert democracy_rows[0].source_indicator_codes == (VDEM_ELECTORAL_DEMOCRACY_INDICATOR_CODE,)
    assert democracy_rows[0].value == 0.83
    assert political_rights_rows[0].source_indicator_codes == (
        FREEDOM_HOUSE_POLITICAL_RIGHTS_INDICATOR_CODE,
    )
    assert political_rights_rows[0].value == 1
    assert civil_liberties_rows[0].source_indicator_codes == (
        FREEDOM_HOUSE_CIVIL_LIBERTIES_INDICATOR_CODE,
    )
    assert civil_liberties_rows[0].value == 2
    assert press_rows[0].source_indicator_codes == (RSF_PRESS_FREEDOM_SCORE_INDICATOR_CODE,)
    assert press_rows[0].value == 72.4


def test_extract_concept_domestic_safety_direct_mappings() -> None:
    """D12 domestic-safety concepts alias V-Dem, UCDP, CIRIGHTS, and PTS."""
    from leaders_db.sources.concepts import (
        CIRIGHTS_PHYSICAL_INTEGRITY_INDICATOR_CODE,
        CIRIGHTS_SOURCE_KEY,
        CONCEPT_CIRIGHTS_PHYSICAL_INTEGRITY,
        CONCEPT_ONE_SIDED_VIOLENCE_FATALITIES,
        CONCEPT_PHYSICAL_INTEGRITY,
        CONCEPT_PTS_AMNESTY_SCORE,
        PTS_AMNESTY_SCORE_INDICATOR_CODE,
        PTS_SOURCE_KEY,
        UCDP_ONE_SIDED_FATALITIES_INDICATOR_CODE,
        UCDP_SOURCE_KEY,
        VDEM_PHYSICAL_INTEGRITY_INDICATOR_CODE,
        VDEM_SOURCE_KEY,
        extract_concept,
    )

    observations = [
        _make_observation(
            source_slug=VDEM_SOURCE_KEY,
            indicator_code=VDEM_PHYSICAL_INTEGRITY_INDICATOR_CODE,
            value=0.71,
            year=2020,
            country_code="USA",
        ),
        _make_observation(
            source_slug=UCDP_SOURCE_KEY,
            indicator_code=UCDP_ONE_SIDED_FATALITIES_INDICATOR_CODE,
            value=4,
            year=2020,
            country_code="USA",
        ),
        _make_observation(
            source_slug=CIRIGHTS_SOURCE_KEY,
            indicator_code=CIRIGHTS_PHYSICAL_INTEGRITY_INDICATOR_CODE,
            value=6,
            year=2020,
            country_code=None,
            country_name="United States",
        ),
        _make_observation(
            source_slug=PTS_SOURCE_KEY,
            indicator_code=PTS_AMNESTY_SCORE_INDICATOR_CODE,
            value=2,
            year=2020,
            country_code="USA",
            unit="ordinal_score",
        ),
    ]

    physical_rows = extract_concept(observations, CONCEPT_PHYSICAL_INTEGRITY, VDEM_SOURCE_KEY)
    fatality_rows = extract_concept(
        observations,
        CONCEPT_ONE_SIDED_VIOLENCE_FATALITIES,
        UCDP_SOURCE_KEY,
    )
    cirights_rows = extract_concept(
        observations,
        CONCEPT_CIRIGHTS_PHYSICAL_INTEGRITY,
        CIRIGHTS_SOURCE_KEY,
    )
    pts_rows = extract_concept(observations, CONCEPT_PTS_AMNESTY_SCORE, PTS_SOURCE_KEY)

    assert physical_rows[0].source_indicator_codes == (VDEM_PHYSICAL_INTEGRITY_INDICATOR_CODE,)
    assert physical_rows[0].value == 0.71
    assert fatality_rows[0].source_indicator_codes == (UCDP_ONE_SIDED_FATALITIES_INDICATOR_CODE,)
    assert fatality_rows[0].value == 4
    assert cirights_rows[0].source_indicator_codes == (CIRIGHTS_PHYSICAL_INTEGRITY_INDICATOR_CODE,)
    assert cirights_rows[0].value == 6
    assert pts_rows[0].source_indicator_codes == (PTS_AMNESTY_SCORE_INDICATOR_CODE,)
    assert pts_rows[0].value == 2


def test_extract_concept_corruption_and_governance_direct_mappings() -> None:
    """D15/D16 concepts alias V-Dem, CPI, and WGI observations."""
    from leaders_db.sources.concepts import (
        BTI_DEMOCRACY_STATUS_INDICATOR_CODE,
        BTI_GOVERNANCE_INDEX_INDICATOR_CODE,
        BTI_SOURCE_KEY,
        BTI_STATUS_INDEX_INDICATOR_CODE,
        CONCEPT_ACCOUNTABILITY,
        CONCEPT_BTI_DEMOCRACY_STATUS,
        CONCEPT_BTI_GOVERNANCE_INDEX,
        CONCEPT_BTI_STATUS_INDEX,
        CONCEPT_CONTROL_OF_CORRUPTION,
        CONCEPT_CORRUPTION_INDEX,
        CONCEPT_CPI_SCORE,
        CONCEPT_GOVERNMENT_EFFECTIVENESS,
        CONCEPT_REGULATORY_QUALITY,
        CONCEPT_VOICE_AND_ACCOUNTABILITY,
        CONCEPT_WGI_RULE_OF_LAW,
        TRANSPARENCY_CPI_SCORE_INDICATOR_CODE,
        TRANSPARENCY_CPI_SOURCE_KEY,
        VDEM_ACCOUNTABILITY_INDICATOR_CODE,
        VDEM_CORRUPTION_INDEX_INDICATOR_CODE,
        VDEM_SOURCE_KEY,
        WGI_CONTROL_OF_CORRUPTION_INDICATOR_CODE,
        WGI_GOVERNMENT_EFFECTIVENESS_INDICATOR_CODE,
        WGI_REGULATORY_QUALITY_INDICATOR_CODE,
        WGI_RULE_OF_LAW_INDICATOR_CODE,
        WGI_SOURCE_KEY,
        WGI_VOICE_AND_ACCOUNTABILITY_INDICATOR_CODE,
        extract_concept,
    )

    observations = [
        _make_observation(
            source_slug=VDEM_SOURCE_KEY,
            indicator_code=VDEM_CORRUPTION_INDEX_INDICATOR_CODE,
            value=0.22,
            year=2020,
            country_code="USA",
        ),
        _make_observation(
            source_slug=VDEM_SOURCE_KEY,
            indicator_code=VDEM_ACCOUNTABILITY_INDICATOR_CODE,
            value=0.76,
            year=2020,
            country_code="USA",
        ),
        _make_observation(
            source_slug=TRANSPARENCY_CPI_SOURCE_KEY,
            indicator_code=TRANSPARENCY_CPI_SCORE_INDICATOR_CODE,
            value=69.0,
            year=2023,
            country_code="USA",
        ),
        _make_observation(
            source_slug=WGI_SOURCE_KEY,
            indicator_code=WGI_CONTROL_OF_CORRUPTION_INDICATOR_CODE,
            value=1.12,
            year=2022,
            country_code="USA",
        ),
        _make_observation(
            source_slug=WGI_SOURCE_KEY,
            indicator_code=WGI_VOICE_AND_ACCOUNTABILITY_INDICATOR_CODE,
            value=0.84,
            year=2022,
            country_code="USA",
        ),
        _make_observation(
            source_slug=WGI_SOURCE_KEY,
            indicator_code=WGI_GOVERNMENT_EFFECTIVENESS_INDICATOR_CODE,
            value=1.31,
            year=2022,
            country_code="USA",
        ),
        _make_observation(
            source_slug=WGI_SOURCE_KEY,
            indicator_code=WGI_RULE_OF_LAW_INDICATOR_CODE,
            value=1.02,
            year=2022,
            country_code="USA",
        ),
        _make_observation(
            source_slug=WGI_SOURCE_KEY,
            indicator_code=WGI_REGULATORY_QUALITY_INDICATOR_CODE,
            value=1.48,
            year=2022,
            country_code="USA",
        ),
        _make_observation(
            source_slug=BTI_SOURCE_KEY,
            indicator_code=BTI_GOVERNANCE_INDEX_INDICATOR_CODE,
            value=7.2,
            year=2023,
            country_name="United States",
            country_code=None,
        ),
        _make_observation(
            source_slug=BTI_SOURCE_KEY,
            indicator_code=BTI_STATUS_INDEX_INDICATOR_CODE,
            value=8.1,
            year=2023,
            country_name="United States",
            country_code=None,
        ),
        _make_observation(
            source_slug=BTI_SOURCE_KEY,
            indicator_code=BTI_DEMOCRACY_STATUS_INDICATOR_CODE,
            value=9.0,
            year=2023,
            country_name="United States",
            country_code=None,
        ),
    ]

    corruption_rows = extract_concept(observations, CONCEPT_CORRUPTION_INDEX, VDEM_SOURCE_KEY)
    accountability_rows = extract_concept(observations, CONCEPT_ACCOUNTABILITY, VDEM_SOURCE_KEY)
    cpi_rows = extract_concept(observations, CONCEPT_CPI_SCORE, TRANSPARENCY_CPI_SOURCE_KEY)
    wgi_corruption_rows = extract_concept(
        observations,
        CONCEPT_CONTROL_OF_CORRUPTION,
        WGI_SOURCE_KEY,
    )
    wgi_accountability_rows = extract_concept(
        observations,
        CONCEPT_VOICE_AND_ACCOUNTABILITY,
        WGI_SOURCE_KEY,
    )
    wgi_rule_of_law_rows = extract_concept(
        observations,
        CONCEPT_WGI_RULE_OF_LAW,
        WGI_SOURCE_KEY,
    )
    wgi_effectiveness_rows = extract_concept(
        observations,
        CONCEPT_GOVERNMENT_EFFECTIVENESS,
        WGI_SOURCE_KEY,
    )
    wgi_regulatory_rows = extract_concept(
        observations,
        CONCEPT_REGULATORY_QUALITY,
        WGI_SOURCE_KEY,
    )
    bti_governance_rows = extract_concept(
        observations,
        CONCEPT_BTI_GOVERNANCE_INDEX,
        BTI_SOURCE_KEY,
    )
    bti_status_rows = extract_concept(
        observations,
        CONCEPT_BTI_STATUS_INDEX,
        BTI_SOURCE_KEY,
    )
    bti_democracy_rows = extract_concept(
        observations,
        CONCEPT_BTI_DEMOCRACY_STATUS,
        BTI_SOURCE_KEY,
    )

    assert corruption_rows[0].source_indicator_codes == (VDEM_CORRUPTION_INDEX_INDICATOR_CODE,)
    assert corruption_rows[0].value == 0.22
    assert accountability_rows[0].source_indicator_codes == (VDEM_ACCOUNTABILITY_INDICATOR_CODE,)
    assert accountability_rows[0].value == 0.76
    assert cpi_rows[0].source_indicator_codes == (TRANSPARENCY_CPI_SCORE_INDICATOR_CODE,)
    assert cpi_rows[0].value == 69.0
    assert wgi_corruption_rows[0].source_indicator_codes == (
        WGI_CONTROL_OF_CORRUPTION_INDICATOR_CODE,
    )
    assert wgi_corruption_rows[0].value == 1.12
    assert wgi_accountability_rows[0].source_indicator_codes == (
        WGI_VOICE_AND_ACCOUNTABILITY_INDICATOR_CODE,
    )
    assert wgi_accountability_rows[0].value == 0.84
    assert wgi_rule_of_law_rows[0].source_indicator_codes == (WGI_RULE_OF_LAW_INDICATOR_CODE,)
    assert wgi_rule_of_law_rows[0].value == 1.02
    assert wgi_effectiveness_rows[0].source_indicator_codes == (
        WGI_GOVERNMENT_EFFECTIVENESS_INDICATOR_CODE,
    )
    assert wgi_effectiveness_rows[0].value == 1.31
    assert wgi_regulatory_rows[0].source_indicator_codes == (WGI_REGULATORY_QUALITY_INDICATOR_CODE,)
    assert wgi_regulatory_rows[0].value == 1.48
    assert bti_governance_rows[0].source_indicator_codes == (BTI_GOVERNANCE_INDEX_INDICATOR_CODE,)
    assert bti_governance_rows[0].value == 7.2
    assert bti_status_rows[0].source_indicator_codes == (BTI_STATUS_INDEX_INDICATOR_CODE,)
    assert bti_status_rows[0].value == 8.1
    assert bti_democracy_rows[0].source_indicator_codes == (BTI_DEMOCRACY_STATUS_INDICATOR_CODE,)
    assert bti_democracy_rows[0].value == 9.0


def test_extract_concept_nuclear_risk_direct_mappings() -> None:
    """D17 concepts alias FAS nuclear status-table observations."""
    from leaders_db.sources.concepts import (
        CONCEPT_NUCLEAR_TOTAL_INVENTORY,
        FAS_SOURCE_KEY,
        FAS_TOTAL_INVENTORY_INDICATOR_CODE,
        extract_concept,
    )

    observations = [
        _make_observation(
            source_slug=FAS_SOURCE_KEY,
            indicator_code=FAS_TOTAL_INVENTORY_INDICATOR_CODE,
            value=5244,
            year=2014,
            country_code=None,
            country_name="United States",
        ),
    ]

    rows = extract_concept(observations, CONCEPT_NUCLEAR_TOTAL_INVENTORY, FAS_SOURCE_KEY)

    assert len(rows) == 1
    assert rows[0].country_code is None
    assert rows[0].country_name == "United States"
    assert rows[0].source_indicator_codes == (FAS_TOTAL_INVENTORY_INDICATOR_CODE,)
    assert rows[0].value == 5244


def test_extract_concept_sipri_yearbook_nuclear_mappings() -> None:
    from leaders_db.sources.concepts import (
        CONCEPT_NUCLEAR_DEPLOYED,
        CONCEPT_NUCLEAR_TOTAL_INVENTORY,
        SIPRI_YEARBOOK_CH7_DEPLOYED_INDICATOR_CODE,
        SIPRI_YEARBOOK_CH7_SOURCE_KEY,
        SIPRI_YEARBOOK_CH7_TOTAL_INVENTORY_INDICATOR_CODE,
        extract_concept,
    )

    observations = [
        _make_observation(
            source_slug=SIPRI_YEARBOOK_CH7_SOURCE_KEY,
            indicator_code=indicator,
            value=value,
            year=2024,
            country_code=None,
            country_name="Russia",
        )
        for indicator, value in (
            (SIPRI_YEARBOOK_CH7_TOTAL_INVENTORY_INDICATOR_CODE, 5580),
            (SIPRI_YEARBOOK_CH7_DEPLOYED_INDICATOR_CODE, 1710),
        )
    ]

    total = extract_concept(observations, CONCEPT_NUCLEAR_TOTAL_INVENTORY)
    deployed = extract_concept(observations, CONCEPT_NUCLEAR_DEPLOYED)

    assert [(row.value, row.source_id.slug) for row in total] == [
        (5580, SIPRI_YEARBOOK_CH7_SOURCE_KEY)
    ]
    assert [row.value for row in deployed] == [1710]


def test_extract_concept_maddison_direct_gdp_per_capita_preserves_indicator() -> None:
    """Maddison ``gdp_per_capita`` extraction preserves the indicator code."""
    from leaders_db.sources.concepts import (
        CONCEPT_GDP_PER_CAPITA,
        MADDISON_PROJECT_GDP_PER_CAPITA_INDICATOR_CODE,
        MADDISON_PROJECT_SOURCE_KEY,
        extract_concept,
    )

    observations = [
        _make_observation(
            source_slug=MADDISON_PROJECT_SOURCE_KEY,
            indicator_code=MADDISON_PROJECT_GDP_PER_CAPITA_INDICATOR_CODE,
            value=60_000.0,
            year=2022,
            country_code="USA",
        ),
    ]
    rows = extract_concept(
        observations,
        CONCEPT_GDP_PER_CAPITA,
        MADDISON_PROJECT_SOURCE_KEY,
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.source_indicator_codes == (MADDISON_PROJECT_GDP_PER_CAPITA_INDICATOR_CODE,)
    assert row.value == 60_000.0
    assert row.year == 2022


def test_extract_concept_unknown_indicator_does_not_match() -> None:
    """An observation with an indicator code not in the mapping is ignored.

    The catalog filters by ``indicator_code`` membership in the
    mapping's ``indicator_codes`` tuple; unrelated indicators must
    not leak into the concept stream.
    """
    from leaders_db.sources.concepts import (
        CONCEPT_POPULATION,
        WDI_SOURCE_KEY,
        extract_concept,
    )

    observations = [
        _make_observation(
            source_slug=WDI_SOURCE_KEY,
            indicator_code="wdi_gini_index",  # not a population mapping
            value=0.4,
            year=2023,
            country_code="USA",
        ),
    ]
    rows = extract_concept(
        observations,
        CONCEPT_POPULATION,
        WDI_SOURCE_KEY,
    )
    assert rows == ()


def test_extract_concept_direct_missing_value_surfaces_warning() -> None:
    """Direct mappings surface a structured ``missing_value`` warning on
    rows whose input observation has a missing / non-numeric value.

    The catalog must NOT silently drop the row: downstream code
    needs the observation id / locator so it can debug the upstream
    issue.
    """
    from leaders_db.sources import SourceWarning
    from leaders_db.sources.concepts import (
        CONCEPT_GDP_PER_CAPITA,
        WDI_GDP_PER_CAPITA_INDICATOR_CODE,
        WDI_SOURCE_KEY,
        extract_concept,
    )

    observations = [
        _make_observation(
            source_slug=WDI_SOURCE_KEY,
            indicator_code=WDI_GDP_PER_CAPITA_INDICATOR_CODE,
            value=None,
            year=2023,
            country_code="USA",
        ),
    ]
    rows = extract_concept(
        observations,
        CONCEPT_GDP_PER_CAPITA,
        WDI_SOURCE_KEY,
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.value is None
    assert row.value_type == "missing"
    assert len(row.warnings) == 1
    warning = row.warnings[0]
    assert isinstance(warning, SourceWarning)
    assert warning.code == "missing_value"
    assert WDI_SOURCE_KEY in warning.message
    assert WDI_GDP_PER_CAPITA_INDICATOR_CODE in warning.message


# ---------------------------------------------------------------------------
# extract_concept: derived PWT GDP per capita
# ---------------------------------------------------------------------------


def test_extract_concept_pwt_derived_gdp_per_capita_computes_ratio() -> None:
    """PWT ``gdp_per_capita = pwt_real_gdp_output_side / pwt_population``.

    The two inputs share the same (source_id, source_version,
    country_code, year) scope. The derived row carries both input
    observation ids, both source indicator codes, the
    ``derived_concept`` quality flag, and the recipe key.
    """
    from leaders_db.sources.concepts import (
        CONCEPT_GDP_PER_CAPITA,
        PWT_GDP_PER_CAPITA_RECIPE_KEY,
        PWT_POPULATION_INDICATOR_CODE,
        PWT_REAL_GDP_OUTPUT_SIDE_INDICATOR_CODE,
        PWT_SOURCE_KEY,
        extract_concept,
    )

    # rgdpo = 20_000_000 million_2017_USD; pop = 329_500 thousands.
    # Ratio = 20e6 / 329.5e3 = 60.698... thousand USD per person.
    expected_ratio = 20_000_000.0 / 329_500.0

    observations = [
        _make_observation(
            source_slug=PWT_SOURCE_KEY,
            indicator_code=PWT_REAL_GDP_OUTPUT_SIDE_INDICATOR_CODE,
            value=20_000_000.0,
            year=2019,
            country_code="USA",
            source_version="10.01",
        ),
        _make_observation(
            source_slug=PWT_SOURCE_KEY,
            indicator_code=PWT_POPULATION_INDICATOR_CODE,
            value=329_500.0,
            year=2019,
            country_code="USA",
            source_version="10.01",
        ),
    ]
    rows = extract_concept(
        observations,
        CONCEPT_GDP_PER_CAPITA,
        PWT_SOURCE_KEY,
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.value == pytest.approx(expected_ratio)
    assert row.value_type == "numeric"
    assert row.mapping_type == "derived"
    assert row.recipe_key == PWT_GDP_PER_CAPITA_RECIPE_KEY
    assert row.quality_flags == ("derived_concept",)
    # Both input observation ids must be present (order is
    # numerator then denominator).
    assert len(row.input_observation_ids) == 2
    assert row.source_indicator_codes == (
        PWT_REAL_GDP_OUTPUT_SIDE_INDICATOR_CODE,
        PWT_POPULATION_INDICATOR_CODE,
    )
    # Both locators propagated.
    assert len(row.raw_locators) == 2
    assert len(row.transform_locators) == 2
    # Recipe key is in the extension payload for audit.
    assert row.extension["recipe_key"] == PWT_GDP_PER_CAPITA_RECIPE_KEY
    assert row.extension["numerator_indicator_code"] == PWT_REAL_GDP_OUTPUT_SIDE_INDICATOR_CODE
    assert row.extension["denominator_indicator_code"] == PWT_POPULATION_INDICATOR_CODE


def test_extract_concept_pwt_derived_missing_denominator_emits_no_row() -> None:
    """PWT derived GDP-per-capita with a missing denominator emits zero rows.

    The slice refuses to silently guess; the next caller can fix
    the upstream gap or rerun with a narrower filter.
    """
    from leaders_db.sources.concepts import (
        CONCEPT_GDP_PER_CAPITA,
        PWT_REAL_GDP_OUTPUT_SIDE_INDICATOR_CODE,
        PWT_SOURCE_KEY,
        extract_concept,
    )

    observations = [
        _make_observation(
            source_slug=PWT_SOURCE_KEY,
            indicator_code=PWT_REAL_GDP_OUTPUT_SIDE_INDICATOR_CODE,
            value=20_000_000.0,
            year=2019,
            country_code="USA",
        ),
    ]
    rows = extract_concept(
        observations,
        CONCEPT_GDP_PER_CAPITA,
        PWT_SOURCE_KEY,
    )
    assert rows == (), (
        "PWT gdp_per_capita with a missing denominator must "
        "return no row rather than guessing a value."
    )


def test_extract_concept_pwt_derived_zero_denominator_emits_no_row() -> None:
    """A zero denominator emits zero rows (division would be undefined)."""
    from leaders_db.sources.concepts import (
        CONCEPT_GDP_PER_CAPITA,
        PWT_POPULATION_INDICATOR_CODE,
        PWT_REAL_GDP_OUTPUT_SIDE_INDICATOR_CODE,
        PWT_SOURCE_KEY,
        extract_concept,
    )

    observations = [
        _make_observation(
            source_slug=PWT_SOURCE_KEY,
            indicator_code=PWT_REAL_GDP_OUTPUT_SIDE_INDICATOR_CODE,
            value=20_000_000.0,
            year=2019,
            country_code="USA",
        ),
        _make_observation(
            source_slug=PWT_SOURCE_KEY,
            indicator_code=PWT_POPULATION_INDICATOR_CODE,
            value=0.0,
            year=2019,
            country_code="USA",
        ),
    ]
    rows = extract_concept(
        observations,
        CONCEPT_GDP_PER_CAPITA,
        PWT_SOURCE_KEY,
    )
    assert rows == ()


def test_extract_concept_pwt_derived_nan_denominator_emits_no_row() -> None:
    """A NaN denominator emits zero rows (division would be undefined)."""
    from leaders_db.sources.concepts import (
        CONCEPT_GDP_PER_CAPITA,
        PWT_POPULATION_INDICATOR_CODE,
        PWT_REAL_GDP_OUTPUT_SIDE_INDICATOR_CODE,
        PWT_SOURCE_KEY,
        extract_concept,
    )

    observations = [
        _make_observation(
            source_slug=PWT_SOURCE_KEY,
            indicator_code=PWT_REAL_GDP_OUTPUT_SIDE_INDICATOR_CODE,
            value=20_000_000.0,
            year=2019,
            country_code="USA",
        ),
        _make_observation(
            source_slug=PWT_SOURCE_KEY,
            indicator_code=PWT_POPULATION_INDICATOR_CODE,
            value=float("nan"),
            year=2019,
            country_code="USA",
        ),
    ]
    rows = extract_concept(
        observations,
        CONCEPT_GDP_PER_CAPITA,
        PWT_SOURCE_KEY,
    )
    assert rows == ()


def test_extract_concept_pwt_derived_ambiguous_pair_emits_no_row() -> None:
    """Two numerator observations for the same scope -> ambiguous, no row.

    The slice refuses to guess which pair to use. Downstream code
    can rerun with a narrower filter to disambiguate.
    """
    from leaders_db.sources.concepts import (
        CONCEPT_GDP_PER_CAPITA,
        PWT_POPULATION_INDICATOR_CODE,
        PWT_REAL_GDP_OUTPUT_SIDE_INDICATOR_CODE,
        PWT_SOURCE_KEY,
        extract_concept,
    )

    observations = [
        _make_observation(
            source_slug=PWT_SOURCE_KEY,
            indicator_code=PWT_REAL_GDP_OUTPUT_SIDE_INDICATOR_CODE,
            value=20_000_000.0,
            year=2019,
            country_code="USA",
        ),
        _make_observation(
            source_slug=PWT_SOURCE_KEY,
            indicator_code=PWT_REAL_GDP_OUTPUT_SIDE_INDICATOR_CODE,
            value=21_000_000.0,
            year=2019,
            country_code="USA",
        ),
        _make_observation(
            source_slug=PWT_SOURCE_KEY,
            indicator_code=PWT_POPULATION_INDICATOR_CODE,
            value=329_500.0,
            year=2019,
            country_code="USA",
        ),
    ]
    rows = extract_concept(
        observations,
        CONCEPT_GDP_PER_CAPITA,
        PWT_SOURCE_KEY,
    )
    assert rows == (), (
        "An ambiguous pair (two numerators for one scope) must "
        "emit zero rows; the catalog refuses to guess."
    )


def test_extract_concept_pwt_derived_year_mismatch_emits_no_row() -> None:
    """Numerator + denominator with different years -> no derived row.

    The pair must share the same (source_id, source_version,
    country_code, year, leader scope) tuple; mismatched year means
    the ratio is meaningless and the slice refuses to guess.
    """
    from leaders_db.sources.concepts import (
        CONCEPT_GDP_PER_CAPITA,
        PWT_POPULATION_INDICATOR_CODE,
        PWT_REAL_GDP_OUTPUT_SIDE_INDICATOR_CODE,
        PWT_SOURCE_KEY,
        extract_concept,
    )

    observations = [
        _make_observation(
            source_slug=PWT_SOURCE_KEY,
            indicator_code=PWT_REAL_GDP_OUTPUT_SIDE_INDICATOR_CODE,
            value=20_000_000.0,
            year=2019,
            country_code="USA",
        ),
        _make_observation(
            source_slug=PWT_SOURCE_KEY,
            indicator_code=PWT_POPULATION_INDICATOR_CODE,
            value=329_500.0,
            year=2018,
            country_code="USA",
        ),
    ]
    rows = extract_concept(
        observations,
        CONCEPT_GDP_PER_CAPITA,
        PWT_SOURCE_KEY,
    )
    assert rows == ()


# ---------------------------------------------------------------------------
# Concept extraction isolation: no adapters / runners / raw files
# ---------------------------------------------------------------------------


def test_extract_concept_does_not_call_adapters_or_runners(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``extract_concept`` must never import or invoke a source adapter.

    The catalog is a pure transformation over the provided
    observation sequence; it must not pull in
    :class:`SourceIngestRunner`, instantiate adapters, or read raw
    files. The test monkeypatches the canonical
    ``SourceIngestRunner`` and asserts no call is made.
    """
    from leaders_db.sources import SourceIngestRunner
    from leaders_db.sources.concepts import (
        CONCEPT_GDP_PER_CAPITA,
        PWT_POPULATION_INDICATOR_CODE,
        PWT_REAL_GDP_OUTPUT_SIDE_INDICATOR_CODE,
        PWT_SOURCE_KEY,
        extract_concept,
    )

    calls: list[str] = []
    original_init = SourceIngestRunner.__init__

    def _spy_init(self: Any, *args: Any, **kwargs: Any) -> None:
        calls.append("runner_init")
        return original_init(self, *args, **kwargs)

    monkeypatch.setattr(SourceIngestRunner, "__init__", _spy_init)

    observations = [
        _make_observation(
            source_slug=PWT_SOURCE_KEY,
            indicator_code=PWT_REAL_GDP_OUTPUT_SIDE_INDICATOR_CODE,
            value=20_000_000.0,
            year=2019,
            country_code="USA",
        ),
        _make_observation(
            source_slug=PWT_SOURCE_KEY,
            indicator_code=PWT_POPULATION_INDICATOR_CODE,
            value=329_500.0,
            year=2019,
            country_code="USA",
        ),
    ]
    rows = extract_concept(
        observations,
        CONCEPT_GDP_PER_CAPITA,
        PWT_SOURCE_KEY,
    )
    assert len(rows) == 1
    assert calls == [], f"extract_concept must not instantiate SourceIngestRunner; saw {calls!r}"


def test_extract_concept_does_not_read_raw_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The catalog never opens raw files in the data lake.

    Even when the observation id ``path`` field points at a raw
    file path, ``extract_concept`` must not call ``Path.read_*``.
    The test places a sentinel file and monkeypatches ``Path.open``
    to record every call; the assertion is that no call hits the
    sentinel.
    """
    from leaders_db.sources.concepts import (
        CONCEPT_POPULATION,
        WDI_POPULATION_INDICATOR_CODE,
        WDI_SOURCE_KEY,
        extract_concept,
    )

    sentinel_path = tmp_path / "raw.csv"
    sentinel_path.write_text("never,read\n", encoding="utf-8")

    from leaders_db.sources import NormalizedObservation
    from leaders_db.sources.contracts import (
        RawLocator,
        SourceId,
        TransformLocator,
    )

    observations: list[NormalizedObservation] = [
        NormalizedObservation(
            source_id=SourceId(slug=WDI_SOURCE_KEY),
            observation_id="wdi:USA:2023:wdi_population",
            observation_family="economic_country_year",
            indicator_code=WDI_POPULATION_INDICATOR_CODE,
            value=333_000_000.0,
            value_type="numeric",
            year=2023,
            country_code="USA",
            country_name=None,
            leader_id=None,
            leader_name=None,
            unit=None,
            scale=None,
            source_version="v1",
            raw_locator=RawLocator(
                asset_id="wdi:test",
                path=str(sentinel_path),
            ),
            transform_locator=TransformLocator(),
            quality_flags=(),
            warnings=(),
            extension={},
        ),
    ]

    opened: list[str] = []
    original_open = Path.open

    def _spy_open(self: Path, *args: Any, **kwargs: Any) -> Any:
        opened.append(str(self))
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", _spy_open)

    rows = extract_concept(
        observations,
        CONCEPT_POPULATION,
        WDI_SOURCE_KEY,
    )
    assert len(rows) == 1
    assert opened == [], f"extract_concept must not open raw files; saw opens={opened!r}"


# ---------------------------------------------------------------------------
# extract_concept: derived PWT GDP per capita (year-scoped grouping)
# ---------------------------------------------------------------------------


def test_extract_concept_pwt_derived_multi_year_same_country_emits_two_rows() -> None:
    """The PWT derivation scope key includes ``year`` -- a single country
    with valid 2018 AND 2019 inputs emits two derived rows, one per
    (country, year) scope, rather than collapsing into one ambiguous
    multi-year bucket.

    This is the multi-year test that pins the
    ``_group_key(scope_key includes year)`` invariant. Both year
    scopes are valid (one numerator + one denominator each,
    matched ``source_version``, finite values) so each emits one
    derived row carrying the matching year and a distinct ratio.
    """
    from leaders_db.sources.concepts import (
        CONCEPT_GDP_PER_CAPITA,
        PWT_GDP_PER_CAPITA_RECIPE_KEY,
        PWT_POPULATION_INDICATOR_CODE,
        PWT_REAL_GDP_OUTPUT_SIDE_INDICATOR_CODE,
        PWT_SOURCE_KEY,
        extract_concept,
    )

    observations = [
        _make_observation(
            source_slug=PWT_SOURCE_KEY,
            indicator_code=PWT_REAL_GDP_OUTPUT_SIDE_INDICATOR_CODE,
            value=18_000_000.0,
            year=2018,
            country_code="USA",
            source_version="10.01",
        ),
        _make_observation(
            source_slug=PWT_SOURCE_KEY,
            indicator_code=PWT_POPULATION_INDICATOR_CODE,
            value=328_000.0,
            year=2018,
            country_code="USA",
            source_version="10.01",
        ),
        _make_observation(
            source_slug=PWT_SOURCE_KEY,
            indicator_code=PWT_REAL_GDP_OUTPUT_SIDE_INDICATOR_CODE,
            value=20_000_000.0,
            year=2019,
            country_code="USA",
            source_version="10.01",
        ),
        _make_observation(
            source_slug=PWT_SOURCE_KEY,
            indicator_code=PWT_POPULATION_INDICATOR_CODE,
            value=329_500.0,
            year=2019,
            country_code="USA",
            source_version="10.01",
        ),
    ]
    rows = extract_concept(
        observations,
        CONCEPT_GDP_PER_CAPITA,
        PWT_SOURCE_KEY,
    )

    by_year = {row.year: row for row in rows}
    assert set(by_year.keys()) == {2018, 2019}, (
        "PWT derivation must group inputs by year; a single "
        "country with valid 2018 AND 2019 inputs must emit TWO "
        f"derived rows; got years={sorted(by_year.keys())!r}"
    )
    # Year 2018 row: 18_000_000 / 328_000
    assert by_year[2018].value == pytest.approx(
        18_000_000.0 / 328_000.0,
    )
    assert by_year[2018].year == 2018
    assert by_year[2018].country_code == "USA"
    assert by_year[2018].recipe_key == PWT_GDP_PER_CAPITA_RECIPE_KEY
    # Year 2019 row: 20_000_000 / 329_500
    assert by_year[2019].value == pytest.approx(
        20_000_000.0 / 329_500.0,
    )
    assert by_year[2019].year == 2019
    assert by_year[2019].country_code == "USA"


def test_extract_concept_pwt_derived_missing_source_version_emits_no_row() -> None:
    """PWT derivation requires both inputs to have a non-empty
    ``source_version`` -- missing source_version surfaces a
    structured warning and emits no row, to keep provenance strong.

    The convenience :func:`extract_concept` returns an empty tuple;
    the diagnostic :func:`extract_concept_result` returns the
    matching :class:`SourceWarning` records.
    """
    from leaders_db.sources.concepts import (
        CONCEPT_GDP_PER_CAPITA,
        CONCEPT_WARNING_MISSING_SOURCE_VERSION,
        PWT_POPULATION_INDICATOR_CODE,
        PWT_REAL_GDP_OUTPUT_SIDE_INDICATOR_CODE,
        PWT_SOURCE_KEY,
        extract_concept,
        extract_concept_result,
    )

    observations = [
        _make_observation(
            source_slug=PWT_SOURCE_KEY,
            indicator_code=PWT_REAL_GDP_OUTPUT_SIDE_INDICATOR_CODE,
            value=20_000_000.0,
            year=2019,
            country_code="USA",
            source_version=None,
        ),
        _make_observation(
            source_slug=PWT_SOURCE_KEY,
            indicator_code=PWT_POPULATION_INDICATOR_CODE,
            value=329_500.0,
            year=2019,
            country_code="USA",
            source_version="10.01",
        ),
    ]
    rows = extract_concept(
        observations,
        CONCEPT_GDP_PER_CAPITA,
        PWT_SOURCE_KEY,
    )
    assert rows == ()

    result = extract_concept_result(
        observations,
        CONCEPT_GDP_PER_CAPITA,
        PWT_SOURCE_KEY,
    )
    assert result.observations == ()
    codes = tuple(w.code for w in result.warnings)
    assert CONCEPT_WARNING_MISSING_SOURCE_VERSION in codes


def test_extract_concept_pwt_derived_mismatched_source_version_emits_no_row() -> None:
    """PWT derivation requires both inputs to share the same
    ``source_version`` stamp -- mismatched source_versions surface
    a structured warning and emit no row (mixing incompatible
    provenance would compromise the audit trail)."""
    from leaders_db.sources.concepts import (
        CONCEPT_GDP_PER_CAPITA,
        CONCEPT_WARNING_MISSING_SOURCE_VERSION,
        PWT_POPULATION_INDICATOR_CODE,
        PWT_REAL_GDP_OUTPUT_SIDE_INDICATOR_CODE,
        PWT_SOURCE_KEY,
        extract_concept,
        extract_concept_result,
    )

    observations = [
        _make_observation(
            source_slug=PWT_SOURCE_KEY,
            indicator_code=PWT_REAL_GDP_OUTPUT_SIDE_INDICATOR_CODE,
            value=20_000_000.0,
            year=2019,
            country_code="USA",
            source_version="10.01",
        ),
        _make_observation(
            source_slug=PWT_SOURCE_KEY,
            indicator_code=PWT_POPULATION_INDICATOR_CODE,
            value=329_500.0,
            year=2019,
            country_code="USA",
            source_version="10.00",
        ),
    ]
    rows = extract_concept(
        observations,
        CONCEPT_GDP_PER_CAPITA,
        PWT_SOURCE_KEY,
    )
    assert rows == ()

    result = extract_concept_result(
        observations,
        CONCEPT_GDP_PER_CAPITA,
        PWT_SOURCE_KEY,
    )
    assert result.observations == ()
    codes = tuple(w.code for w in result.warnings)
    assert CONCEPT_WARNING_MISSING_SOURCE_VERSION in codes


# ---------------------------------------------------------------------------
# extract_concept_result: diagnostic helper surfaces every drop reason
# ---------------------------------------------------------------------------


def test_extract_concept_result_emits_empty_warnings_for_valid_pwt_pair() -> None:
    """A valid PWT pair emits zero warnings and one observation."""
    from leaders_db.sources.concepts import (
        CONCEPT_GDP_PER_CAPITA,
        PWT_POPULATION_INDICATOR_CODE,
        PWT_REAL_GDP_OUTPUT_SIDE_INDICATOR_CODE,
        PWT_SOURCE_KEY,
        extract_concept_result,
    )

    observations = [
        _make_observation(
            source_slug=PWT_SOURCE_KEY,
            indicator_code=PWT_REAL_GDP_OUTPUT_SIDE_INDICATOR_CODE,
            value=20_000_000.0,
            year=2019,
            country_code="USA",
            source_version="10.01",
        ),
        _make_observation(
            source_slug=PWT_SOURCE_KEY,
            indicator_code=PWT_POPULATION_INDICATOR_CODE,
            value=329_500.0,
            year=2019,
            country_code="USA",
            source_version="10.01",
        ),
    ]
    result = extract_concept_result(
        observations,
        CONCEPT_GDP_PER_CAPITA,
        PWT_SOURCE_KEY,
    )
    assert len(result.observations) == 1
    assert result.warnings == ()


def test_extract_concept_result_pwt_missing_numerator_warning() -> None:
    """Missing numerator for a valid (country, year) scope surfaces a
    structured ``concept_missing_numerator`` warning."""
    from leaders_db.sources.concepts import (
        CONCEPT_GDP_PER_CAPITA,
        CONCEPT_WARNING_MISSING_NUMERATOR,
        PWT_POPULATION_INDICATOR_CODE,
        PWT_SOURCE_KEY,
        extract_concept_result,
    )

    observations = [
        _make_observation(
            source_slug=PWT_SOURCE_KEY,
            indicator_code=PWT_POPULATION_INDICATOR_CODE,
            value=329_500.0,
            year=2019,
            country_code="USA",
            source_version="10.01",
        ),
    ]
    result = extract_concept_result(
        observations,
        CONCEPT_GDP_PER_CAPITA,
        PWT_SOURCE_KEY,
    )
    assert result.observations == ()
    codes = tuple(w.code for w in result.warnings)
    assert CONCEPT_WARNING_MISSING_NUMERATOR in codes


def test_extract_concept_result_pwt_missing_denominator_warning() -> None:
    """Missing denominator for a valid (country, year) scope surfaces a
    structured ``concept_missing_denominator`` warning."""
    from leaders_db.sources.concepts import (
        CONCEPT_GDP_PER_CAPITA,
        CONCEPT_WARNING_MISSING_DENOMINATOR,
        PWT_REAL_GDP_OUTPUT_SIDE_INDICATOR_CODE,
        PWT_SOURCE_KEY,
        extract_concept_result,
    )

    observations = [
        _make_observation(
            source_slug=PWT_SOURCE_KEY,
            indicator_code=PWT_REAL_GDP_OUTPUT_SIDE_INDICATOR_CODE,
            value=20_000_000.0,
            year=2019,
            country_code="USA",
            source_version="10.01",
        ),
    ]
    result = extract_concept_result(
        observations,
        CONCEPT_GDP_PER_CAPITA,
        PWT_SOURCE_KEY,
    )
    assert result.observations == ()
    codes = tuple(w.code for w in result.warnings)
    assert CONCEPT_WARNING_MISSING_DENOMINATOR in codes


def test_extract_concept_result_pwt_non_numeric_input_warning() -> None:
    """Non-numeric / NaN / inf inputs surface a structured
    ``concept_non_numeric_numerator`` or
    ``concept_non_numeric_denominator`` warning."""
    from leaders_db.sources.concepts import (
        CONCEPT_GDP_PER_CAPITA,
        CONCEPT_WARNING_NON_NUMERIC_NUMERATOR,
        PWT_POPULATION_INDICATOR_CODE,
        PWT_REAL_GDP_OUTPUT_SIDE_INDICATOR_CODE,
        PWT_SOURCE_KEY,
        extract_concept_result,
    )

    observations = [
        _make_observation(
            source_slug=PWT_SOURCE_KEY,
            indicator_code=PWT_REAL_GDP_OUTPUT_SIDE_INDICATOR_CODE,
            value=float("nan"),
            year=2019,
            country_code="USA",
            source_version="10.01",
        ),
        _make_observation(
            source_slug=PWT_SOURCE_KEY,
            indicator_code=PWT_POPULATION_INDICATOR_CODE,
            value=329_500.0,
            year=2019,
            country_code="USA",
            source_version="10.01",
        ),
    ]
    result = extract_concept_result(
        observations,
        CONCEPT_GDP_PER_CAPITA,
        PWT_SOURCE_KEY,
    )
    assert result.observations == ()
    codes = tuple(w.code for w in result.warnings)
    assert CONCEPT_WARNING_NON_NUMERIC_NUMERATOR in codes


def test_extract_concept_result_pwt_zero_denominator_warning() -> None:
    """Zero denominator surfaces a structured ``concept_zero_denominator``
    warning rather than emitting an undefined ratio."""
    from leaders_db.sources.concepts import (
        CONCEPT_GDP_PER_CAPITA,
        CONCEPT_WARNING_ZERO_DENOMINATOR,
        PWT_POPULATION_INDICATOR_CODE,
        PWT_REAL_GDP_OUTPUT_SIDE_INDICATOR_CODE,
        PWT_SOURCE_KEY,
        extract_concept_result,
    )

    observations = [
        _make_observation(
            source_slug=PWT_SOURCE_KEY,
            indicator_code=PWT_REAL_GDP_OUTPUT_SIDE_INDICATOR_CODE,
            value=20_000_000.0,
            year=2019,
            country_code="USA",
            source_version="10.01",
        ),
        _make_observation(
            source_slug=PWT_SOURCE_KEY,
            indicator_code=PWT_POPULATION_INDICATOR_CODE,
            value=0.0,
            year=2019,
            country_code="USA",
            source_version="10.01",
        ),
    ]
    result = extract_concept_result(
        observations,
        CONCEPT_GDP_PER_CAPITA,
        PWT_SOURCE_KEY,
    )
    assert result.observations == ()
    codes = tuple(w.code for w in result.warnings)
    assert CONCEPT_WARNING_ZERO_DENOMINATOR in codes


def test_extract_concept_result_pwt_ambiguous_pair_warning() -> None:
    """Multiple numerators or denominators for one scope surface a
    structured ``concept_ambiguous_pair`` warning."""
    from leaders_db.sources.concepts import (
        CONCEPT_GDP_PER_CAPITA,
        CONCEPT_WARNING_AMBIGUOUS_PAIR,
        PWT_POPULATION_INDICATOR_CODE,
        PWT_REAL_GDP_OUTPUT_SIDE_INDICATOR_CODE,
        PWT_SOURCE_KEY,
        extract_concept_result,
    )

    observations = [
        _make_observation(
            source_slug=PWT_SOURCE_KEY,
            indicator_code=PWT_REAL_GDP_OUTPUT_SIDE_INDICATOR_CODE,
            value=20_000_000.0,
            year=2019,
            country_code="USA",
            source_version="10.01",
        ),
        _make_observation(
            source_slug=PWT_SOURCE_KEY,
            indicator_code=PWT_REAL_GDP_OUTPUT_SIDE_INDICATOR_CODE,
            value=21_000_000.0,
            year=2019,
            country_code="USA",
            source_version="10.01",
        ),
        _make_observation(
            source_slug=PWT_SOURCE_KEY,
            indicator_code=PWT_POPULATION_INDICATOR_CODE,
            value=329_500.0,
            year=2019,
            country_code="USA",
            source_version="10.01",
        ),
    ]
    result = extract_concept_result(
        observations,
        CONCEPT_GDP_PER_CAPITA,
        PWT_SOURCE_KEY,
    )
    assert result.observations == ()
    codes = tuple(w.code for w in result.warnings)
    assert CONCEPT_WARNING_AMBIGUOUS_PAIR in codes


def test_extract_concept_result_pwt_mismatched_year_warnings() -> None:
    """Mismatched numerator / denominator years surface TWO structured
    warnings -- a ``concept_missing_denominator`` for the numerator's
    scope and a ``concept_missing_numerator`` for the denominator's
    scope. With year-scoped grouping each year becomes its own
    scope, so the year mismatch manifests as one missing side per
    scope rather than a single ``pair_year_mismatch`` warning."""
    from leaders_db.sources.concepts import (
        CONCEPT_GDP_PER_CAPITA,
        CONCEPT_WARNING_MISSING_DENOMINATOR,
        CONCEPT_WARNING_MISSING_NUMERATOR,
        PWT_POPULATION_INDICATOR_CODE,
        PWT_REAL_GDP_OUTPUT_SIDE_INDICATOR_CODE,
        PWT_SOURCE_KEY,
        extract_concept_result,
    )

    observations = [
        _make_observation(
            source_slug=PWT_SOURCE_KEY,
            indicator_code=PWT_REAL_GDP_OUTPUT_SIDE_INDICATOR_CODE,
            value=20_000_000.0,
            year=2019,
            country_code="USA",
            source_version="10.01",
        ),
        _make_observation(
            source_slug=PWT_SOURCE_KEY,
            indicator_code=PWT_POPULATION_INDICATOR_CODE,
            value=329_500.0,
            year=2018,
            country_code="USA",
            source_version="10.01",
        ),
    ]
    result = extract_concept_result(
        observations,
        CONCEPT_GDP_PER_CAPITA,
        PWT_SOURCE_KEY,
    )
    assert result.observations == ()
    codes = tuple(w.code for w in result.warnings)
    assert CONCEPT_WARNING_MISSING_NUMERATOR in codes
    assert CONCEPT_WARNING_MISSING_DENOMINATOR in codes


def test_extract_concept_result_direct_missing_value_warning() -> None:
    """The diagnostic helper also surfaces per-row direct-mapping
    warnings -- a missing / non-numeric value produces a
    ``missing_value`` warning attached to the emitted row and
    collected on the diagnostic helper's ``warnings`` tuple."""
    from leaders_db.sources.concepts import (
        CONCEPT_GDP_PER_CAPITA,
        WDI_GDP_PER_CAPITA_INDICATOR_CODE,
        WDI_SOURCE_KEY,
        extract_concept_result,
    )

    observations = [
        _make_observation(
            source_slug=WDI_SOURCE_KEY,
            indicator_code=WDI_GDP_PER_CAPITA_INDICATOR_CODE,
            value=None,
            year=2023,
            country_code="USA",
        ),
        _make_observation(
            source_slug=WDI_SOURCE_KEY,
            indicator_code=WDI_GDP_PER_CAPITA_INDICATOR_CODE,
            value=70_000.0,
            year=2023,
            country_code="USA",
        ),
    ]
    result = extract_concept_result(
        observations,
        CONCEPT_GDP_PER_CAPITA,
        WDI_SOURCE_KEY,
    )
    assert len(result.observations) == 2
    codes = tuple(w.code for w in result.warnings)
    assert "missing_value" in codes


# ---------------------------------------------------------------------------
# Optional integration-style test against real SourceIngestRunner output
# ---------------------------------------------------------------------------


def _stage_pwt_bundle_for_concept_test(raw_root: Path) -> Path:
    """Stage the canonical PWT fixture bundle for the concept integration test."""
    bundle_dir = raw_root / "pwt"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    fixtures = Path(__file__).resolve().parents[1] / "fixtures" / "pwt"
    shutil.copy2(fixtures / "sample.xlsx", bundle_dir / "pwt1001.xlsx")
    sha = hashlib.sha256(
        (bundle_dir / "pwt1001.xlsx").read_bytes(),
    ).hexdigest()
    payload = {
        "source_name": "Penn World Table",
        "source_version": "10.01",
        "download_date": "2026-06-22",
        "coverage": "country-year economic accounts",
        "years_available": "1950-2019",
        "license_note": (
            "Creative Commons Attribution 4.0 International "
            "(CC BY 4.0); cite Feenstra, Inklaar, Timmer 2015."
        ),
        "local_files": ["pwt1001.xlsx"],
        "ingestion_status": "downloaded",
        "source_url": ("https://www.rug.nl/ggdc/productivity/pwt/pwt-releases/pwt1001"),
        "checksum_sha256": sha,
    }
    (bundle_dir / "metadata.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )
    return bundle_dir


def _stage_maddison_bundle_for_concept_test(raw_root: Path) -> Path:
    """Stage the canonical Maddison fixture bundle for the concept integration test."""
    bundle_dir = raw_root / "maddison_project"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    fixtures = Path(__file__).resolve().parents[1] / "fixtures" / "maddison_project"
    shutil.copy2(fixtures / "sample.xlsx", bundle_dir / "mpd2023.xlsx")
    sha = hashlib.sha256(
        (bundle_dir / "mpd2023.xlsx").read_bytes(),
    ).hexdigest()
    payload = {
        "source_name": "Maddison Project Database 2023",
        "source_version": "2023",
        "download_date": "2026-06-24",
        "coverage": "country-year (1-2022)",
        "years_available": "1-2022",
        "license_note": "CC BY 4.0",
        "local_files": ["mpd2023.xlsx"],
        "ingestion_status": "downloaded",
        "source_url": "https://dataverse.nl/api/access/datafile/421302",
        "checksum_sha256": {"mpd2023.xlsx": sha},
    }
    (bundle_dir / "metadata.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )
    return bundle_dir


def _stage_wdi_bundle_for_concept_test(raw_root: Path) -> Path:
    """Stage the canonical WDI fixture bundle for the concept integration test."""
    bundle_dir = raw_root / "world_bank_wdi"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    fixtures_cache = Path(__file__).resolve().parents[1] / "fixtures" / "world_bank_wdi" / "cache"
    for year in ("2022", "2023"):
        src_year_dir = fixtures_cache / year
        if src_year_dir.exists():
            shutil.copytree(src_year_dir, bundle_dir / "cache" / year)
    payload = {
        "source_name": "World Bank WDI",
        "source_version": ("World Bank API v2; cached indicator responses"),
        "download_date": "2026-06-24",
        "coverage": "1960-present",
        "years_available": "1960-2023+",
        "license_note": "CC BY 4.0",
        "local_files": ["cache/"],
        "ingestion_status": "downloaded",
        "source_url": "https://api.worldbank.org/v2/",
        "checksum_sha256": None,
        "checksum_note": (
            "API-backed source with per-response JSON cache "
            "files under cache/<year>/<indicator>.json; checksums "
            "are managed per cached response."
        ),
        "attribution": "World Bank WDI (World Bank 2024).",
    }
    (bundle_dir / "metadata.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )
    return bundle_dir


def test_concepts_extract_gdp_per_capita_from_real_runner_output(
    tmp_path: Path,
) -> None:
    """Integration-style test: run the real :class:`SourceIngestRunner`
    against staged WDI / Maddison / PWT bundles and feed the
    emitted observations through :func:`extract_concept`.

    The integration proves:

    - The catalog consumes real :class:`NormalizedObservation`
      records end-to-end (WDI direct, Maddison direct, PWT
      derived).
    - The catalog's output is observable alongside the runner's
      structured observations without any rewiring.

    The test asserts the structural properties of the extracted
    rows (mapping_type, quality_flags, country coverage) rather
    than the specific country order, because the fixture
    ordering is implementation-defined.
    """
    from leaders_db.sources import (
        InMemorySourceRegistry,
        SourceId,
        SourceIngestRequest,
        SourceIngestRunner,
    )
    from leaders_db.sources.adapters.maddison_project import (
        create_maddison_project_adapter,
    )
    from leaders_db.sources.adapters.pwt import create_pwt_adapter
    from leaders_db.sources.adapters.world_bank_wdi import (
        create_world_bank_wdi_adapter,
    )
    from leaders_db.sources.concepts import (
        CONCEPT_GDP_PER_CAPITA,
        MADDISON_PROJECT_SOURCE_KEY,
        PWT_SOURCE_KEY,
        WDI_SOURCE_KEY,
        extract_concept,
    )

    raw_root = tmp_path / "raw"
    _stage_wdi_bundle_for_concept_test(raw_root)
    _stage_maddison_bundle_for_concept_test(raw_root)
    _stage_pwt_bundle_for_concept_test(raw_root)

    registry = InMemorySourceRegistry()
    registry.register(create_world_bank_wdi_adapter())
    registry.register(create_maddison_project_adapter())
    registry.register(create_pwt_adapter())
    runner = SourceIngestRunner(registry=registry)

    def _collect(source_slug: str, years: Sequence[int]) -> Iterable[Any]:
        request = SourceIngestRequest(
            source_id=SourceId(slug=source_slug),
            raw_root=raw_root,
            years=tuple(years),
        )
        result = runner.run(request)
        return result.observations

    # WDI: extract 2023 GDP per capita. The fixture has multiple
    # countries, so the catalog emits multiple direct rows. Each
    # row must carry the documented mapping_type and a year that
    # matches the request scope.
    wdi_observations = list(_collect(WDI_SOURCE_KEY, [2023]))
    wdi_rows = extract_concept(
        tuple(wdi_observations),
        CONCEPT_GDP_PER_CAPITA,
        WDI_SOURCE_KEY,
    )
    assert wdi_rows, "WDI direct extraction must produce at least one row"
    countries = {row.country_code for row in wdi_rows}
    assert "USA" in countries, f"WDI fixture must include USA; got countries={countries}"
    for row in wdi_rows:
        assert row.year == 2023
        assert row.mapping_type == "direct"
        assert row.recipe_key is None

    # Maddison: extract 2022 GDP per capita. The fixture has 4
    # countries (IND, MEX, SWE, USA); USA must be present in the
    # result.
    maddison_observations = list(_collect(MADDISON_PROJECT_SOURCE_KEY, [2022]))
    maddison_rows = extract_concept(
        tuple(maddison_observations),
        CONCEPT_GDP_PER_CAPITA,
        MADDISON_PROJECT_SOURCE_KEY,
    )
    assert maddison_rows, "Maddison direct extraction must produce at least one row"
    maddison_countries = {row.country_code for row in maddison_rows}
    assert "USA" in maddison_countries, (
        f"Maddison fixture must include USA; got countries={maddison_countries}"
    )
    for row in maddison_rows:
        assert row.year == 2022
        assert row.mapping_type == "direct"

    # PWT: extract 2019 GDP per capita (derived). The PWT fixture
    # has 3 countries (USA, MEX, SWE); the derived rows only
    # appear for scopes where both rgdpo and pop are non-null in
    # 2019. The structural assertions are order-independent.
    pwt_observations = list(_collect(PWT_SOURCE_KEY, [2019]))
    pwt_rows = extract_concept(
        tuple(pwt_observations),
        CONCEPT_GDP_PER_CAPITA,
        PWT_SOURCE_KEY,
    )
    assert pwt_rows, "PWT derived extraction must produce at least one row"
    pwt_countries = {row.country_code for row in pwt_rows}
    assert "USA" in pwt_countries, f"PWT fixture must include USA; got countries={pwt_countries}"
    for row in pwt_rows:
        assert row.mapping_type == "derived"
        assert "derived_concept" in row.quality_flags
        assert row.recipe_key is not None
        # Both input observation ids must be present for a derived
        # row so audit code can re-trace the derivation.
        assert len(row.input_observation_ids) == 2


__all__ = [
    "CONCEPT_TEST_PACKAGE",
    "CONCEPT_TEST_STABLE_KEYS",
    "test_concepts_module_does_not_import_legacy_ingest_at_import",
    "test_concepts_package_import_does_not_import_legacy_ingest",
    "test_extract_concept_direct_missing_value_surfaces_warning",
    "test_extract_concept_does_not_call_adapters_or_runners",
    "test_extract_concept_does_not_read_raw_files",
    "test_extract_concept_maddison_direct_gdp_per_capita_preserves_indicator",
    "test_extract_concept_pwt_derived_ambiguous_pair_emits_no_row",
    "test_extract_concept_pwt_derived_gdp_per_capita_computes_ratio",
    "test_extract_concept_pwt_derived_mismatched_source_version_emits_no_row",
    "test_extract_concept_pwt_derived_missing_denominator_emits_no_row",
    "test_extract_concept_pwt_derived_missing_source_version_emits_no_row",
    "test_extract_concept_pwt_derived_multi_year_same_country_emits_two_rows",
    "test_extract_concept_pwt_derived_nan_denominator_emits_no_row",
    "test_extract_concept_pwt_derived_year_mismatch_emits_no_row",
    "test_extract_concept_pwt_derived_zero_denominator_emits_no_row",
    "test_extract_concept_result_direct_missing_value_warning",
    "test_extract_concept_result_emits_empty_warnings_for_valid_pwt_pair",
    "test_extract_concept_result_pwt_ambiguous_pair_warning",
    "test_extract_concept_result_pwt_mismatched_year_warnings",
    "test_extract_concept_result_pwt_missing_denominator_warning",
    "test_extract_concept_result_pwt_missing_numerator_warning",
    "test_extract_concept_result_pwt_non_numeric_input_warning",
    "test_extract_concept_result_pwt_zero_denominator_warning",
    "test_extract_concept_unknown_indicator_does_not_match",
    "test_extract_concept_wdi_direct_gdp_per_capita_emits_two_rows",
    "test_extract_concept_wdi_direct_population_preserves_indicator",
    "test_list_concepts_exposes_stable_keys",
    "test_resolve_concept_client_existing_is_unsupported_for_every_concept",
    "test_resolve_concept_global_returns_all_source_mappings",
    "test_resolve_concept_source_specific_narrows_to_single_mapping",
    "test_resolve_concept_unknown_concept_key_raises_actionable_error",
    "test_resolve_concept_unsupported_source_raises_actionable_error",
]
