"""Country-Year Chronicle (CYC) experimental vertical slice.

This package implements Increment 1 of the country-year profile backbone
described in :file:`docs/country-year-chronicle-workplan.md` and the
findings in :file:`docs/country-year-chronicle-increment-0.md`.

Increment 1 is **experimental** and **read-only**: it builds a deterministic
CSV (one row per requested country identity per year) without touching the
client matrix, without calling an LLM, and without persisting to the main
prototype database. The data sources it can read are:

- **V-Dem** (``v2x_regime`` / ``v2x_polyarchy`` / ``v2x_libdem``) for
  political-regime buckets — preferred over the processed parquet because
  Increment 1 needs the full 1789-2025 historical range, not just 2022.
- **World Bank WDI** for population / GDP / GDP per capita (1960+ where
  the processed parquet has a row; otherwise the value is empty and the
  row carries ``missing_population`` / ``missing_gdp`` flags).
- **SIPRI milex** for military spend (only when the processed parquet
  covers the requested year and the country name resolves to an ISO3).

Everything else (rulers, area, controlled area) is left empty with the
canonical flags ``missing_ruler`` / ``missing_area`` /
``controlled_area_not_modeled``.

The public entry points are:

- :func:`runner.run_country_year_chronicle` — Python seam.
- :func:`cli.commands_chronicle.run_country_year_chronicle_cmd` — CLI
  wrapper invoked as ``leaders-db run-country-year-chronicle``.
"""

from __future__ import annotations

from .constants import (
    CHRONICLE_OUTPUT_DIR_NAME,
    DEFAULT_COUNTRIES,
    DEFAULT_END_YEAR,
    DEFAULT_OUTPUT_BASENAME,
    DEFAULT_PROXY_YEAR,
    DEFAULT_START_YEAR,
)
from .runner import (
    ChronicleResult,
    build_chronicle_rows,
    run_country_year_chronicle,
)
from .sources import (
    RegimeSource,
    SipriSource,
    VDemSource,
    WdiSource,
)

__all__ = [
    "CHRONICLE_OUTPUT_DIR_NAME",
    "DEFAULT_COUNTRIES",
    "DEFAULT_END_YEAR",
    "DEFAULT_OUTPUT_BASENAME",
    "DEFAULT_PROXY_YEAR",
    "DEFAULT_START_YEAR",
    "ChronicleResult",
    "RegimeSource",
    "SipriSource",
    "VDemSource",
    "WdiSource",
    "build_chronicle_rows",
    "run_country_year_chronicle",
]
