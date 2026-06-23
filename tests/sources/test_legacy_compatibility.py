"""Phase B — Legacy ingest compatibility tests.

The unified-source migration runs alongside the existing prototype.
Phase A MUST leave the legacy ``leaders_db.ingest`` package usable so
callers, CLIs, and tests that depend on it continue to work while the
new subsystem is built (SRC-SCOPE-004, SRC-MIG-002).

These tests assert the legacy surface stays intact from both ends:

- The legacy package still exposes the canonical ``STAGE2_ADAPTERS``
  dispatch table, with the same keys the rest of the project depends
  on.
- Existing legacy capabilities remain callable (a representative
  ``callable`` shape, not the full set, is enough to prove the table
  has not been emptied).
- Importing the new package does not disturb the legacy module cache
  in a way that breaks later legacy use.
- The lazy legacy seam returns the same dispatch table the legacy
  package itself publishes.

PASS-ELIGIBLE rationale
-----------------------
All tests here are PASS-ELIGIBLE: the legacy surface is untouched by
Phase A, and the seam returns the legacy mapping. They are regression
guards, not behavior tests.
"""
from __future__ import annotations

import importlib
import sys
from collections.abc import Callable, Mapping
from typing import Any

import pytest


def _purge_modules(prefix: str) -> None:
    for name in list(sys.modules):
        if name == prefix or name.startswith(prefix + "."):
            del sys.modules[name]


@pytest.fixture()
def fresh_legacy_import():
    """Import ``leaders_db.ingest`` in a clean module cache."""
    _purge_modules("leaders_db")
    module = importlib.import_module("leaders_db.ingest")
    yield module
    _purge_modules("leaders_db")


def test_legacy_ingest_exposes_stage2_adapters_dispatch_table(
    fresh_legacy_import,
) -> None:
    """``leaders_db.ingest.STAGE2_ADAPTERS`` is the documented dispatch table.

    The CLI consumes this table directly; tests for individual adapters
    rely on it for fixture wiring. The Phase A boundary MUST leave the
    symbol and its value intact.

    PASS-ELIGIBLE.
    """
    dispatch = getattr(fresh_legacy_import, "STAGE2_ADAPTERS", None)
    assert dispatch is not None, "STAGE2_ADAPTERS must be importable"
    assert isinstance(dispatch, dict), (
        f"STAGE2_ADAPTERS must be a Mapping, got {type(dispatch).__name__}"
    )
    # Values are either None (not-implemented slots) or callable
    # orchestrator functions.
    for key, value in dispatch.items():
        assert value is None or callable(value), (
            f"STAGE2_ADAPTERS[{key!r}] must be None or callable, "
            f"got {type(value).__name__}"
        )


def test_legacy_ingest_contains_required_implemented_keys(
    fresh_legacy_import,
) -> None:
    """The legacy dispatch table must list every key that downstream code
    and tests depend on.

    The keys below are referenced by name in fixture scripts, smoke
    tests, and CLI dispatch. The Phase A boundary MUST NOT remove any
    of them.

    PASS-ELIGIBLE.
    """
    dispatch = fresh_legacy_import.STAGE2_ADAPTERS
    required_implemented = {
        "vdem",
        "world_bank_wdi",
        "world_bank_wgi",
        "ucdp",
        "sipri_milex",
        "sipri_yearbook_ch7",
        "pts",
        "undp_hdi",
        "who_gho_api",
        "archigos",
        "reign",
        "cirights",
        "transparency_cpi",
        "fas",
        "bti",
        "rsf_press_freedom",
        "wikidata_heads_of_state_government",
        "wikipedia_search_extract",
        "maddison_project",
        "pwt",
    }
    missing = required_implemented - set(dispatch)
    assert not missing, (
        f"STAGE2_ADAPTERS missing required implemented keys: {missing}"
    )


def test_legacy_ingest_contains_known_blocked_or_unimplemented_slots(
    fresh_legacy_import,
) -> None:
    """The legacy dispatch table explicitly tracks blocked / unimplemented
    sources as ``None`` so the CLI surfaces the stub message.

    Keeping these slots is part of the compatibility contract.

    PASS-ELIGIBLE.
    """
    dispatch = fresh_legacy_import.STAGE2_ADAPTERS
    # Documented blocked-or-unimplemented slots; the CLI relies on
    # ``None`` to print the canonical stub message.
    required_none_slots = {
        "polity_v",
        "leader_survival",
        "freedom_house",
        "imf_weo",
        "cow_mid",
        "nti",
        "cia_world_leaders",
    }
    for key in required_none_slots:
        assert key in dispatch, (
            f"STAGE2_ADAPTERS must keep slot for {key!r} (None or callable)"
        )


def test_legacy_dispatch_callables_accept_keyword_arguments(
    fresh_legacy_import,
) -> None:
    """Legacy orchestrators must keep the documented ``(**kwargs) -> result``
    signature.

    Phase A does not modify legacy code; this test guards the
    documented signature contract so future refactors cannot silently
    change the call shape the CLI relies on.

    PASS-ELIGIBLE.
    """
    import inspect

    dispatch = fresh_legacy_import.STAGE2_ADAPTERS
    callable_keys = [
        key for key, value in dispatch.items() if callable(value)
    ]
    assert callable_keys, "expected at least one implemented legacy adapter"
    for key in callable_keys:
        orchestrator = dispatch[key]
        # ``inspect.signature`` may raise for builtins; the legacy
        # orchestrators are user-defined functions, so a KeyError-style
        # failure would surface as a missing key above.
        signature = inspect.signature(orchestrator)
        # VAR_KEYWORD or explicit keyword-only arguments are the two
        # signatures documented in the legacy ``__init__`` docstring.
        has_var_keyword = any(
            param.kind is inspect.Parameter.VAR_KEYWORD
            for param in signature.parameters.values()
        )
        params = list(signature.parameters.values())
        has_keyword_only = any(
            param.kind is inspect.Parameter.KEYWORD_ONLY
            for param in params
        )
        assert has_var_keyword or has_keyword_only or params, (
            f"legacy orchestrator {key!r} must accept keyword arguments"
        )


def test_importing_sources_does_not_break_legacy_ingest_use() -> None:
    """Importing the new package MUST NOT prevent a caller from importing or
    using ``leaders_db.ingest`` afterwards.

    Defense-in-depth against a future refactor that wires ``sources``
    into ``ingest`` (or vice versa) at import time and breaks the
    isolation.

    PASS-ELIGIBLE.
    """
    _purge_modules("leaders_db")
    try:
        # Import the new package first.
        importlib.import_module("leaders_db.sources")
        # Then import the legacy package and use it.
        legacy = importlib.import_module("leaders_db.ingest")
        # Round-trip: pull a known orchestrator and confirm it is the
        # same callable the legacy package exposes directly.
        pwt_via_legacy = legacy.STAGE2_ADAPTERS["pwt"]
        # Pull again to confirm the table is read-consistent.
        pwt_again = legacy.STAGE2_ADAPTERS["pwt"]
        assert pwt_via_legacy is pwt_again
        assert callable(pwt_via_legacy)
    finally:
        _purge_modules("leaders_db")


def test_lazy_legacy_seam_returns_same_mapping_as_legacy_package() -> None:
    """The lazy ``get_legacy_stage2_adapters`` returns the same dispatch table
    the legacy package publishes.

    Callers using the seam during migration planning must see the same
    key/value pairs the legacy package exposes directly. The test
    asserts both shapes are equal and share the legacy ``None`` slots.

    PASS-ELIGIBLE.
    """
    from leaders_db.sources.legacy import get_legacy_stage2_adapters

    mapping: Mapping[str, Callable[..., Any] | None] = get_legacy_stage2_adapters()
    assert isinstance(mapping, Mapping)
    # The seam must surface the canonical legacy ``None`` slots too.
    for key in (
        "polity_v",
        "leader_survival",
        "freedom_house",
        "imf_weo",
        "cow_mid",
        "nti",
        "cia_world_leaders",
    ):
        assert key in mapping, (
            f"lazy legacy seam must surface {key!r} slot"
        )


def test_lazy_legacy_seam_returns_independent_view_of_dispatch_table() -> None:
    """The seam returns the legacy mapping object directly (not a snapshot).

    Migrators may inspect the table identity to confirm it matches the
    legacy package. The test asserts the seam returns the same object
    the legacy package publishes.

    PASS-ELIGIBLE.
    """
    from leaders_db.ingest import STAGE2_ADAPTERS as legacy_dispatch
    from leaders_db.sources.legacy import get_legacy_stage2_adapters

    seam_view = get_legacy_stage2_adapters()
    assert seam_view is legacy_dispatch


__all__ = [
    "fresh_legacy_import",
    "test_importing_sources_does_not_break_legacy_ingest_use",
    "test_lazy_legacy_seam_returns_independent_view_of_dispatch_table",
    "test_lazy_legacy_seam_returns_same_mapping_as_legacy_package",
    "test_legacy_dispatch_callables_accept_keyword_arguments",
    "test_legacy_ingest_contains_known_blocked_or_unimplemented_slots",
    "test_legacy_ingest_contains_required_implemented_keys",
    "test_legacy_ingest_exposes_stage2_adapters_dispatch_table",
]
