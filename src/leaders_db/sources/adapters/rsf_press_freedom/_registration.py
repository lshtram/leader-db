"""Unified-source Reporters Without Borders (RSF)
registration helpers + protocol conformance guard.

Split out of
:mod:`leaders_db.sources.adapters.rsf_press_freedom.adapter`
so the adapter class module stays focused on the
lifecycle methods. This module owns:

- :func:`create_rsf_press_freedom_adapter` -- the
  explicit factory callers use to wire RSF into a
  :class:`SourceRegistry`.
- :func:`register_rsf_press_freedom` -- the explicit
  registration helper for tests and future
  composition.
- :data:`RSF_PRESS_FREEDOM_ADAPTER_FACTORY` -- the
  module-level factory alias for symmetry with the
  legacy ``STAGE2_ADAPTERS`` keying convention.
- :func:`_ensure_protocol_conformance` -- defense in
  depth that catches missing ``descriptor`` /
  ``check_ready`` / ``read_raw`` / ``transform`` at
  module import time via the runtime-checkable
  ``SourceAdapter`` Protocol.
"""

from __future__ import annotations

from typing import Any

from leaders_db.sources.contracts import SourceAdapter

from .adapter import RSFPressFreedomAdapter


def create_rsf_press_freedom_adapter() -> RSFPressFreedomAdapter:
    """Return a fresh :class:`RSFPressFreedomAdapter`.

    The explicit seam callers use to wire RSF into a
    :class:`SourceRegistry`. The package does NOT
    auto-register on import (the registry is passive
    -- ``docs/architecture/sources.md`` §10.1).
    """
    return RSFPressFreedomAdapter()


def register_rsf_press_freedom(
    registry: Any,
) -> RSFPressFreedomAdapter:
    """Register the RSF adapter against ``registry``.

    Returns the registered adapter. Raises
    :class:`ValueError` on duplicate-slug registration
    per ``docs/requirements/sources.md`` §9 SRC-REG-004.
    """
    adapter = create_rsf_press_freedom_adapter()
    registry.register(adapter)
    return adapter


# Module-level factory alias for symmetry with the
# legacy ``STAGE2_ADAPTERS`` keying convention.
# ``create_rsf_press_freedom_adapter()`` is the
# preferred form.
RSF_PRESS_FREEDOM_ADAPTER_FACTORY = (
    create_rsf_press_freedom_adapter
)


# ---------------------------------------------------------------------------
# Protocol conformance guard
# ---------------------------------------------------------------------------


def _ensure_protocol_conformance() -> None:
    """Raise at import time if the adapter does not
    satisfy the protocol.

    Defense in depth: ``isinstance`` against the
    runtime-checkable ``SourceAdapter`` Protocol
    catches missing ``descriptor`` / ``check_ready`` /
    ``read_raw`` / ``transform`` at module import
    time.
    """
    if not isinstance(
        RSFPressFreedomAdapter(), SourceAdapter,
    ):
        raise TypeError(
            "RSFPressFreedomAdapter does not satisfy "
            "the SourceAdapter Protocol; check the "
            "descriptor attribute and the "
            "check_ready / read_raw / transform method "
            "shapes."
        )


_ensure_protocol_conformance()


__all__ = [
    "RSF_PRESS_FREEDOM_ADAPTER_FACTORY",
    "create_rsf_press_freedom_adapter",
    "register_rsf_press_freedom",
]
