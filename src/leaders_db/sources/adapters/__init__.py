"""Unified-source adapter namespace.

The first real adapter now lives in the explicit
``leaders_db.sources.adapters.pwt`` subpackage. Importing this parent package
does not auto-register PWT or any future adapter; callers must opt in through
the adapter subpackage's factory / registration helper.

Future source migrations should add sibling subpackages here while preserving
the passive parent-package import boundary.
"""

from __future__ import annotations

__all__: list[str] = []
