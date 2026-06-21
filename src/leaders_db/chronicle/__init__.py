"""Country-Year Chronicle (CYC) experimental vertical slice.

This package implements Increments 1 + 2 + 3 of the country-year
profile backbone described in
:file:`docs/country-year-chronicle-workplan.md` and the findings in
:file:`docs/country-year-chronicle-increment-0.md`.

The slice is **experimental** and **read-only**: it builds a
deterministic CSV (one row per requested country identity per
year) without touching the client matrix, without calling an LLM,
and without persisting to the main prototype database.

The data sources it can read are:

- **V-Dem** (``v2x_regime`` / ``v2x_polyarchy`` / ``v2x_libdem``)
  for political-regime buckets.
- **World Bank WDI** for population / GDP / GDP per capita (1960+
  where the processed parquet has a row).
- **SIPRI milex** for military spend (where the processed parquet
  covers the requested year and the country name resolves to an
  ISO3).
- **Maddison Project Database 2023** (Bolt and van Zanden 2024)
  for historical population / GDP / GDP per capita (1-2022; 2023
  proxied to 2022 per the 1-year-gap pattern). Maddison is the
  canonical historical real-economy source; the row builder
  prefers Maddison for 1900-2022 and WDI for 2023+ per the
  Increment 2 contract.
- **Archigos v4.1** for historical leader identities (through
  2015) and **REIGN 2021-8** for monthly leader records (1950-2021;
  the resolver picks the leader with the most months in the
  requested year).
- **Soviet leaders (curated, Wikipedia-anchored)** for SUN rulers
  1922-12-30 to 1991-12-25. The resolver picks the leader with the
  most days in the requested year; transition years (1924, 1953,
  1985) emit ``multiple_rulers``.
- **CShapes 2.0** (Schvitz et al. 2022) for country area (km^2)
  1886-2019 by Gleditsch-Ward code. The row builder picks the
  CShapes row whose ``gwsyear <= year <= gweyear``; years past
  CShapes coverage (2020+) copy the most recent row and emit
  ``area_proxy_year_used``. ``controlled_area_km2`` uses the
  conservative fallback (controlled = country) plus the
  ``controlled_area_country_only`` flag.

The public entry points are:

- :func:`runner.run_country_year_chronicle` — Python seam.
- :func:`cli.commands_chronicle.run_country_year_chronicle_cmd` — CLI
  wrapper invoked as ``leaders-db run-country-year-chronicle``.
"""

from __future__ import annotations

from ._area_source import (
    CShapesSource,
    default_cshapes_csv_path,
    load_cshapes_source,
)
from ._sun_ruler_loader import (
    default_sun_csv_path,
    load_sun_frame,
)
from .constants import (
    CHRONICLE_OUTPUT_DIR_NAME,
    DEFAULT_COUNTRIES,
    DEFAULT_END_YEAR,
    DEFAULT_OUTPUT_BASENAME,
    DEFAULT_PROXY_YEAR,
    DEFAULT_START_YEAR,
)
from .ruler_resolver import (
    RulerResolver,
    RulerResult,
    default_archigos_dta_path,
    default_reign_csv_path,
    load_ruler_resolver,
)
from .runner import (
    ChronicleResult,
    build_chronicle_rows,
    run_country_year_chronicle,
)
from .sources import (
    MaddisonSource,
    RegimeSource,
    SipriSource,
    VDemSource,
    WdiSource,
    load_maddison_source,
)

__all__ = [
    "CHRONICLE_OUTPUT_DIR_NAME",
    "DEFAULT_COUNTRIES",
    "DEFAULT_END_YEAR",
    "DEFAULT_OUTPUT_BASENAME",
    "DEFAULT_PROXY_YEAR",
    "DEFAULT_START_YEAR",
    "CShapesSource",
    "ChronicleResult",
    "MaddisonSource",
    "RegimeSource",
    "RulerResolver",
    "RulerResult",
    "SipriSource",
    "VDemSource",
    "WdiSource",
    "build_chronicle_rows",
    "default_archigos_dta_path",
    "default_cshapes_csv_path",
    "default_reign_csv_path",
    "default_sun_csv_path",
    "load_cshapes_source",
    "load_maddison_source",
    "load_ruler_resolver",
    "load_sun_frame",
    "run_country_year_chronicle",
]
