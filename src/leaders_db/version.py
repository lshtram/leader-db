"""Re-export the package version for explicit imports.

Keeping the version in a dedicated module avoids an import cycle with
``__init__.py`` and lets tools like ``setuptools_scm`` override it later.
"""

from __future__ import annotations

__version__: str = "0.1.0"
