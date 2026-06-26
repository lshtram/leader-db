"""Unified-source adapter namespace.

Clean source adapters live in explicit sibling subpackages. Importing this
parent package does not auto-register any adapter; callers must opt in through
each adapter subpackage's factory / registration helper.

Future source migrations should add sibling subpackages here while preserving
the passive parent-package import boundary.
"""

from __future__ import annotations

__all__: list[str] = []
