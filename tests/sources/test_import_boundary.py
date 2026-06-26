"""Phase B — Import boundary contract tests.

These tests prove the documented package-isolation rules for the new
``leaders_db.sources`` subsystem:

- Importing ``leaders_db.sources`` MUST NOT import ``leaders_db.ingest``
  at any depth. (SRC-MIG-007, SRC-TEST-009)
- Importing the public ``leaders_db.sources`` surface exposes the
  declared Phase A contracts (contracts, registry, runner, query).
- Importing submodules (e.g. ``leaders_db.sources.legacy``) MUST NOT
  import legacy ingest as a side effect. (SRC-MIG-008)
- The legacy ``leaders_db.ingest`` package remains importable on its
  own after the new package is in place. (SRC-SCOPE-004, SRC-MIG-002)

These tests are intentionally written as pure import-and-inspect probes.
They do not exercise production behavior; they assert the static
package boundary that protects the migration.

PASS-ELIGIBLE rationale
-----------------------
All tests in this file are PASS-ELIGIBLE against the Phase A stub:
the stubs already avoid importing legacy modules at import time, and
the legacy package remains importable. These are static boundary
guards, not behavior tests; they encode the migration invariant and
must keep passing once Phase C/D add real adapter code.
"""
from __future__ import annotations

import importlib
import sys
from types import ModuleType

import pytest


def _purge_modules(prefix: str) -> None:
    """Remove every cached module that starts with ``prefix``.

    Used to simulate a fresh interpreter around a single import call so
    side-effect modules do not leak from earlier tests. We deliberately
    keep helpers small and do not touch ``sys.modules`` outside the
    test boundary.
    """
    for name in list(sys.modules):
        if name == prefix or name.startswith(prefix + "."):
            del sys.modules[name]


def _drop_parent_attr(parent_name: str, attr_name: str) -> None:
    parent = sys.modules.get(parent_name)
    if isinstance(parent, ModuleType) and hasattr(parent, attr_name):
        delattr(parent, attr_name)


def _purge_source_boundary_modules() -> None:
    """Remove only source-boundary modules from the cache.

    Several legacy tests configure SQLAlchemy mappers. Removing the whole
    ``leaders_db`` package after that point can orphan mapper class-registry
    entries while leaving configured mapper objects alive, which breaks later
    legacy DB tests. The import-boundary assertions only need fresh
    ``leaders_db.sources`` / ``leaders_db.ingest`` modules, so keep unrelated
    package modules (especially ``leaders_db.db``) intact.
    """
    _purge_modules("leaders_db.sources")
    _purge_modules("leaders_db.ingest")
    _drop_parent_attr("leaders_db", "sources")
    _drop_parent_attr("leaders_db", "ingest")


@pytest.fixture()
def fresh_sources_import():
    """Import ``leaders_db.sources`` in an isolated module cache.

    The fixture drops every ``leaders_db`` / ``leaders_db.sources`` /
    ``leaders_db.ingest`` entry from ``sys.modules`` so the test can
    assert that the package import does not pull legacy ingest in as a
    side effect. The fixture itself does the import; tests use the
    module object via the ``module`` attribute.
    """
    _purge_source_boundary_modules()
    module = importlib.import_module("leaders_db.sources")
    yield module
    # Cleanup: drop the modules again so the next test starts clean.
    _purge_source_boundary_modules()


def test_sources_package_import_does_not_import_legacy_ingest(
    fresh_sources_import,
) -> None:
    """``import leaders_db.sources`` MUST NOT import ``leaders_db.ingest``.

    Phase A decision: the new package boundary keeps legacy ingest
    isolated (SRC-MIG-007, docs/architecture/sources.md §10.1). The
    test inspects ``sys.modules`` after a fresh package import and
    asserts that no module named ``leaders_db.ingest`` (nor any of its
    submodules) is present.

    PASS-ELIGIBLE: the Phase A stub package keeps this invariant.
    """
    leaked = sorted(
        name for name in sys.modules
        if name == "leaders_db.ingest" or name.startswith("leaders_db.ingest.")
    )
    assert leaked == [], (
        "importing leaders_db.sources must not import leaders_db.ingest "
        f"(leaked modules: {leaked})"
    )


def test_sources_package_exposes_declared_public_api(
    fresh_sources_import,
) -> None:
    """The package surface lists every contract, registry, runner, query name.

    The Phase A ``__init__`` re-exports the documented contracts. The
    test asserts the public API is importable via the package root so
    callers can write ``from leaders_db.sources import SourceId`` etc.
    without knowing which submodule the symbol lives in.

    PASS-ELIGIBLE: the package ``__init__`` already re-exports these.
    """
    module = fresh_sources_import
    expected_names = {
        # Contracts
        "CachePolicy",
        "CoverageHint",
        "EvidenceQuery",
        "NormalizedObservation",
        "RawAsset",
        "RawLocator",
        "RawReadResult",
        "ReadinessResult",
        "SourceAdapter",
        "SourceAttribution",
        "SourceDescriptor",
        "SourceId",
        "SourceIngestRequest",
        "SourceIngestResult",
        "SourceManifest",
        "SourceWarning",
        "TransformLocator",
        "ValidationResult",
        # Query
        "EvidenceRepository",
        # Registry
        "InMemorySourceRegistry",
        "SourceRegistry",
        # Runner
        "SourceIngestRunner",
    }
    missing = expected_names - set(dir(module))
    assert not missing, f"missing public names on leaders_db.sources: {missing}"


def test_sources_legacy_module_does_not_import_ingest_at_import_time() -> None:
    """``import leaders_db.sources.legacy`` MUST NOT import legacy ingest.

    The legacy seam is the only place where the new package is allowed
    to touch legacy code, and the import must be lazy (SRC-MIG-008,
    docs/architecture/sources.md §10.1). The test inspects the module
    cache immediately after the import to prove that legacy ingest is
    not loaded as a side effect.

    PASS-ELIGIBLE: the Phase A seam has no eager ingest imports.
    """
    _purge_source_boundary_modules()
    try:
        importlib.import_module("leaders_db.sources.legacy")
        leaked = sorted(
            name for name in sys.modules
            if name == "leaders_db.ingest" or name.startswith("leaders_db.ingest.")
        )
        assert leaked == [], (
            "leaders_db.sources.legacy must not import leaders_db.ingest "
            f"at import time (leaked modules: {leaked})"
        )
    finally:
        _purge_source_boundary_modules()


def test_sources_submodules_do_not_import_legacy_ingest() -> None:
    """Submodule imports (contracts, registry, runner, query, warnings) keep the
    legacy boundary.

    Defense in depth: even if a future contributor adds a new submodule
    that re-exports public names, every submodule under
    ``leaders_db.sources`` must keep the package-isolation rule. The
    test iterates the canonical submodules and asserts none of them
    pulls in legacy ingest.

    PASS-ELIGIBLE: Phase A has no eager ingest imports in any submodule.
    """
    submodules = (
        "leaders_db.sources.contracts",
        "leaders_db.sources.registry",
        "leaders_db.sources.runner",
        "leaders_db.sources.query",
        "leaders_db.sources.warnings",
        "leaders_db.sources.provenance",
        "leaders_db.sources.manifests",
        "leaders_db.sources.concepts",
        "leaders_db.sources.concepts._api",
        "leaders_db.sources.concepts._catalog",
        "leaders_db.sources.concepts._dataclasses",
        "leaders_db.sources.concepts._derived",
        "leaders_db.sources.concepts._derived_reasons",
        "leaders_db.sources.concepts._direct",
        "leaders_db.sources.adapters",
        "leaders_db.sources.adapters.pwt",
        "leaders_db.sources.adapters.maddison_project",
        "leaders_db.sources.adapters.world_bank_wdi",
        "leaders_db.sources.adapters.world_bank_wgi",
        "leaders_db.sources.adapters.vdem",
        "leaders_db.sources.adapters.ucdp",
        "leaders_db.sources.adapters.transparency_cpi",
        "leaders_db.sources.adapters.pts",
        "leaders_db.sources.adapters.rsf_press_freedom",
        "leaders_db.sources.adapters.bti",
        "leaders_db.sources.adapters.freedom_house",
        "leaders_db.sources.adapters.archigos",
        "leaders_db.sources.adapters.reign",
    )
    _purge_source_boundary_modules()
    try:
        for name in submodules:
            importlib.import_module(name)
            leaked = sorted(
                mod for mod in sys.modules
                if mod == "leaders_db.ingest"
                or mod.startswith("leaders_db.ingest.")
            )
            assert leaked == [], (
                f"importing {name} must not import leaders_db.ingest "
                f"(leaked modules: {leaked})"
            )
    finally:
        _purge_source_boundary_modules()


def test_legacy_ingest_remains_importable_independently() -> None:
    """``leaders_db.ingest`` remains importable on its own after the new
    package is in place (SRC-SCOPE-004, SRC-MIG-002).

    The Phase A boundary must not break legacy imports. The test
    imports ``leaders_db.ingest`` directly and confirms the canonical
    Stage 2 dispatch table is accessible.

    Implementation note: the test does NOT re-purge on exit so
    SQLAlchemy's mapper state stays intact for subsequent tests.
    The legacy adapter modules with DB-layer imports
    (``leaders_db.ingest.bti_db`` etc.) trigger SQLAlchemy mapper
    configuration on import; purging the ``leaders_db`` package
    cache and then reloading ``db.models`` re-registers the mapper
    and the ``Country`` forward reference in ``SourceObservation``
    can fail to resolve on the second pass. The legacy module is
    re-imported here so subsequent legacy tests can use it
    without breaking the SQLAlchemy mapper state.
    """
    _purge_source_boundary_modules()
    legacy_ingest = importlib.import_module("leaders_db.ingest")
    # NOTE: do NOT re-purge in ``finally`` -- see the
    # implementation note above. The legacy module is re-imported
    # here so subsequent tests can use it without breaking the
    # SQLAlchemy mapper state.

    # The dispatch table is the canonical Phase A evidence that the
    # legacy surface is intact.
    assert hasattr(legacy_ingest, "STAGE2_ADAPTERS"), (
        "leaders_db.ingest must still expose STAGE2_ADAPTERS"
    )
    dispatch = legacy_ingest.STAGE2_ADAPTERS
    # Spot-check a few known implemented adapters to confirm the table
    # is populated. This guards against a future refactor accidentally
    # emptying it.
    assert "vdem" in dispatch
    assert "world_bank_wdi" in dispatch
    assert callable(dispatch["vdem"])


__all__ = [
    "fresh_sources_import",
    "test_legacy_ingest_remains_importable_independently",
    "test_sources_legacy_module_does_not_import_ingest_at_import_time",
    "test_sources_package_exposes_declared_public_api",
    "test_sources_package_import_does_not_import_legacy_ingest",
    "test_sources_submodules_do_not_import_legacy_ingest",
]
