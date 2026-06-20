"""WDI field population for the Country-Year Chronicle row builder.

The WDI lookup returns a small ``dict`` (see :class:`WdiSource`).
Mapping that payload into the chronicle CSV row columns is its own
self-contained concern: column ordering, GDP unit preference
(constant-USD over current-USD), and the GDP-per-capita fallback
chain (direct → derived from GDP / population → empty). This module
owns that mapping so the row builder can stay focused on row
composition.

The function mutates the passed-in ``row`` in place and returns
``(has_population, has_gdp)`` so the caller can drive the
``missing_population`` / ``missing_gdp`` flags without re-querying.
"""

from __future__ import annotations

from ._formatters import coerce_float, coerce_int
from .constants import SOURCE_NA, SOURCE_TAG_WDI


def populate_wdi_fields(
    row: dict[str, str],
    wdi_values: dict[str, float | None],
    *,
    year: int,
) -> tuple[bool, bool]:
    """Populate the WDI population / GDP / GDP-per-capita columns.

    Returns ``(has_population, has_gdp)`` so the caller can compute
    flags and provenance without re-querying.
    """
    has_population = (
        "population" in wdi_values and wdi_values["population"] is not None
    )
    has_gdp = (
        "gdp_current_usd" in wdi_values and wdi_values["gdp_current_usd"] is not None
    ) or (
        "gdp_constant_2015_usd" in wdi_values
        and wdi_values["gdp_constant_2015_usd"] is not None
    )
    has_gdp_per_capita = (
        "gdp_per_capita" in wdi_values and wdi_values["gdp_per_capita"] is not None
    )

    row["population"] = coerce_float(wdi_values.get("population"), decimals=0)
    if has_population:
        row["population_source"] = SOURCE_TAG_WDI
        row["population_source_year_used"] = coerce_int(year)
    else:
        row["population_source"] = SOURCE_NA
        row["population_source_year_used"] = ""

    # Prefer constant-USD GDP when present (more comparable across the
    # long time-series); fall back to current-USD otherwise.
    gdp_value: float | None = None
    gdp_unit = ""
    if wdi_values.get("gdp_constant_2015_usd") is not None:
        gdp_value = wdi_values["gdp_constant_2015_usd"]
        gdp_unit = "constant_2015_usd"
    elif wdi_values.get("gdp_current_usd") is not None:
        gdp_value = wdi_values["gdp_current_usd"]
        gdp_unit = "current_usd"
    row["gdp"] = coerce_float(gdp_value, decimals=0)
    row["gdp_unit"] = gdp_unit
    if has_gdp:
        row["gdp_source"] = SOURCE_TAG_WDI
        row["gdp_source_year_used"] = coerce_int(year)
    else:
        row["gdp_source"] = SOURCE_NA
        row["gdp_source_year_used"] = ""

    # GDP per capita: prefer WDI's direct per-capita figure; fall back
    # to GDP / population. The method is recorded so a reader can tell
    # which one was used.
    if has_gdp_per_capita:
        per_cap = wdi_values["gdp_per_capita"]
        row["gdp_per_capita"] = coerce_float(per_cap, decimals=2)
        row["gdp_per_capita_unit"] = "current_usd"
        row["gdp_per_capita_method"] = "wdi_direct"
    elif gdp_value is not None and has_population:
        per_cap = gdp_value / wdi_values["population"]  # type: ignore[operator]
        row["gdp_per_capita"] = coerce_float(per_cap, decimals=2)
        row["gdp_per_capita_unit"] = gdp_unit
        row["gdp_per_capita_method"] = "derived_gdp_over_population"
    else:
        row["gdp_per_capita"] = ""
        row["gdp_per_capita_unit"] = ""
        row["gdp_per_capita_method"] = ""

    return has_population, has_gdp


__all__ = ["populate_wdi_fields"]
