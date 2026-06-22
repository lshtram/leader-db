"""Economy-fields population for the Country-Year Chronicle row builder.

This module replaces the WDI-only :func:`populate_wdi_fields` path with
a combined Maddison + WDI precedence:

- Maddison Project is the canonical historical real-economy source
  (2011 international dollars, long-run comparable units); per the
  Increment 2 contract it is preferred for years 1900-2022 when its
  data is present.
- WDI is the fallback for all years, and the preferred source for
  years beyond Maddison coverage (2023+ today). The Maddison 2023
  release ends at 2022, so any year >= 2023 falls through to WDI
  first, with Maddison 2022 only as a final proxy (and the
  ``proxy_year_used`` flag is added so the audit trail is explicit).

The function mutates the passed-in ``row`` in place and returns
``(has_population, has_gdp, economy_flags)`` so the caller can drive
the ``missing_population`` / ``missing_gdp`` / ``proxy_year_used``
flags without re-querying.

GDP / GDP-per-capita method vocabulary:

- ``maddison_direct``: GDP per capita taken directly from Maddison's
  ``gdppc`` column (2011 international dollars).
- ``wdi_direct``: GDP per capita taken directly from WDI's
  ``wdi_gdp_per_capita`` (current USD).
- ``derived_gdp_over_population``: GDP / population computed at row
  time (Maddison or WDI). The unit matches the GDP unit column.

The Maddison ``pop`` is in thousands; the helper multiplies by 1000
to lift it to absolute persons before writing the row, so the
``population`` column always carries an absolute-person count and a
downstream consumer does not have to special-case Maddison vs WDI.
"""

from __future__ import annotations

from dataclasses import dataclass

from ._formatters import coerce_float, coerce_int
from .constants import (
    EXISTS_STATUS_EXISTS,
    EXISTS_STATUS_NOT_FORMED,
    EXISTS_STATUS_SPLIT,
    FLAG_POPULATION_INTERPOLATED,
    FLAG_POPULATION_PROXY_YEAR_USED,
    MADDISON_PROXY_REQUESTED_YEAR,
    MADDISON_PROXY_YEAR,
    SOURCE_NA,
    SOURCE_TAG_MADDISON,
    SOURCE_TAG_VDEM,
    SOURCE_TAG_WDI,
)
from .sources import MaddisonSource, VDemSource, WdiSource


def populate_economy_fields(  # noqa: PLR0915
    row: dict[str, str],
    *,
    iso3: str,
    year: int,
    wdi: WdiSource,
    maddison: MaddisonSource | None,
    vdem: VDemSource | None = None,
) -> tuple[bool, bool, tuple[str, ...]]:
    """Populate the population / GDP / GDP-per-capita columns.

    Returns ``(has_population, has_gdp, economy_flags)``.

    The ``economy_flags`` tuple carries the data-quality flags that
    the economy-fields layer is responsible for. Currently it is
    always empty (the placeholder for future Maddison-vs-WDI
    conflict flags), but the channel exists so the caller does not
    need a separate ``assemble_flags`` update when the helper
    decides to emit one.
    """
    maddison_gdppc: float | None = None
    maddison_pop: float | None = None
    maddison_gdp: float | None = None
    maddison_year_used: int | None = None
    maddison_is_proxy = False

    if maddison is not None:
        gdppc, pop_thousands, derived, year_used, is_proxy = maddison.lookup(
            iso3, year,
        )
        maddison_gdppc = gdppc
        maddison_pop = (
            None if pop_thousands is None else pop_thousands * 1000.0
        )
        maddison_gdp = derived
        maddison_year_used = year_used if (
            gdppc is not None or pop_thousands is not None or derived is not None
        ) else None
        maddison_is_proxy = is_proxy

    wdi_values = wdi.lookup(iso3, year)
    wdi_population = wdi_values.get("population")
    wdi_gdp_constant = wdi_values.get("gdp_constant_2015_usd")
    wdi_gdp_current = wdi_values.get("gdp_current_usd")
    wdi_gdp_per_capita = wdi_values.get("gdp_per_capita")
    wdi_has_gdp = wdi_gdp_constant is not None or wdi_gdp_current is not None
    vdem_population = None if vdem is None else vdem.population_lookup(iso3, year)
    vdem_gdp = None if vdem is None else vdem.gdp_lookup(iso3, year)
    economy_flags: tuple[str, ...] = ()

    # Decide which source wins for population.
    # Precedence: Maddison (1900-2022 direct, 2023 -> 2022 proxy)
    #             > WDI (2023+ direct)
    population_value: float | None = None
    population_source = SOURCE_NA
    population_year_used = ""

    if year <= MADDISON_PROXY_REQUESTED_YEAR - 1 and maddison_pop is not None:
        # Direct Maddison hit for a pre-2023 year.
        population_value = maddison_pop
        population_source = SOURCE_TAG_MADDISON
        population_year_used = str(year)
    elif (
        year > MADDISON_PROXY_REQUESTED_YEAR
        and wdi_population is not None
    ):
        # Year > 2023 (i.e. 2024+): prefer WDI (the canonical
        # recent source). WDI must supply the value; Maddison is
        # NOT a proxy here because Maddison's 2023 release ends at
        # 2022 and reusing 2022 for 2024 would be an undocumented
        # multi-year stale-data contract.
        population_value = wdi_population
        population_source = SOURCE_TAG_WDI
        population_year_used = str(year)
    elif (
        year == MADDISON_PROXY_REQUESTED_YEAR
        and wdi_population is not None
    ):
        # Year 2023: prefer WDI when present (canonical recent source).
        population_value = wdi_population
        population_source = SOURCE_TAG_WDI
        population_year_used = str(year)
    elif (
        year == MADDISON_PROXY_REQUESTED_YEAR
        and wdi_population is None
        and maddison_pop is not None
        and maddison_is_proxy
    ):
        # Year 2023 with no WDI row yet — fall back to Maddison
        # 2022 1-year-gap proxy. Row builder must add
        # proxy_year_used flag.
        population_value = maddison_pop
        population_source = SOURCE_TAG_MADDISON
        population_year_used = str(MADDISON_PROXY_YEAR)
    elif (
        year > MADDISON_PROXY_REQUESTED_YEAR
        and wdi_population is None
    ):
        # Year 2024+ with no WDI row: leave population blank with
        # missing_population flag. Silently reusing Maddison 2022
        # for 2024/2025/2026 would be an undocumented multi-year
        # stale proxy; we explicitly do NOT do that.
        population_value = None
        population_source = SOURCE_NA
        population_year_used = ""
    elif maddison_pop is not None:
        # Defensive: Maddison populated but year handling did not
        # match one of the cases above (should not happen in
        # practice; the lookup returns the right effective year).
        population_value = maddison_pop
        population_source = SOURCE_TAG_MADDISON
        population_year_used = str(maddison_year_used or year)
    elif wdi_population is not None:
        population_value = wdi_population
        population_source = SOURCE_TAG_WDI
        population_year_used = str(year)

    if population_value is None and vdem_population is not None:
        # Conservative coverage fallback for population only. V-Dem is
        # already loaded for regime/ruler bridging and carries population
        # fields with documented or empirically validated units. Non-exact
        # V-Dem fills are surfaced in data_quality_flags below.
        population_value = vdem_population.value
        population_source = SOURCE_TAG_VDEM
        population_year_used = str(vdem_population.source_year_used)
        if vdem_population.method == "interpolated":
            economy_flags = (*economy_flags, FLAG_POPULATION_INTERPOLATED)
        elif vdem_population.method == "proxy":
            economy_flags = (*economy_flags, FLAG_POPULATION_PROXY_YEAR_USED)

    has_population = population_value is not None
    row["population"] = coerce_float(population_value, decimals=0)
    if has_population:
        row["population_source"] = population_source
        row["population_source_year_used"] = coerce_int(
            int(population_year_used) if population_year_used else year,
        )
    else:
        row["population_source"] = SOURCE_NA
        row["population_source_year_used"] = ""

    # Decide which source wins for GDP.
    gdp_value: float | None = None
    gdp_unit = ""
    gdp_source = SOURCE_NA
    gdp_year_used = ""

    if year <= MADDISON_PROXY_REQUESTED_YEAR - 1 and maddison_gdp is not None:
        gdp_value = maddison_gdp
        gdp_unit = "2011_intl_dollars"
        gdp_source = SOURCE_TAG_MADDISON
        gdp_year_used = str(year)
    elif (
        year > MADDISON_PROXY_REQUESTED_YEAR
        and wdi_has_gdp
    ):
        # Year 2024+: prefer WDI when present. Maddison is NOT a
        # proxy here because reusing the 2022 Maddison value for
        # 2024/2025/2026 would be an undocumented multi-year
        # stale-data contract.
        if wdi_gdp_constant is not None:
            gdp_value = wdi_gdp_constant
            gdp_unit = "constant_2015_usd"
        else:
            gdp_value = wdi_gdp_current
            gdp_unit = "current_usd"
        gdp_source = SOURCE_TAG_WDI
        gdp_year_used = str(year)
    elif (
        year == MADDISON_PROXY_REQUESTED_YEAR
        and wdi_has_gdp
    ):
        # Year 2023: prefer WDI when present (canonical recent source).
        if wdi_gdp_constant is not None:
            gdp_value = wdi_gdp_constant
            gdp_unit = "constant_2015_usd"
        else:
            gdp_value = wdi_gdp_current
            gdp_unit = "current_usd"
        gdp_source = SOURCE_TAG_WDI
        gdp_year_used = str(year)
    elif (
        year == MADDISON_PROXY_REQUESTED_YEAR
        and not wdi_has_gdp
        and maddison_gdp is not None
        and maddison_is_proxy
    ):
        # Year 2023 with no WDI row yet — fall back to Maddison
        # 2022 1-year-gap proxy.
        gdp_value = maddison_gdp
        gdp_unit = "2011_intl_dollars"
        gdp_source = SOURCE_TAG_MADDISON
        gdp_year_used = str(MADDISON_PROXY_YEAR)
    elif (
        year > MADDISON_PROXY_REQUESTED_YEAR
        and not wdi_has_gdp
    ):
        # Year 2024+ with no WDI row: leave GDP blank with
        # missing_gdp flag. Silently reusing Maddison 2022 for
        # 2024/2025/2026 is explicitly NOT done.
        gdp_value = None
        gdp_unit = ""
        gdp_source = SOURCE_NA
        gdp_year_used = ""
    elif maddison_gdp is not None:
        gdp_value = maddison_gdp
        gdp_unit = "2011_intl_dollars"
        gdp_source = SOURCE_TAG_MADDISON
        gdp_year_used = str(maddison_year_used or year)
    elif wdi_has_gdp:
        if wdi_gdp_constant is not None:
            gdp_value = wdi_gdp_constant
            gdp_unit = "constant_2015_usd"
        else:
            gdp_value = wdi_gdp_current
            gdp_unit = "current_usd"
        gdp_source = SOURCE_TAG_WDI
        gdp_year_used = str(year)

    if gdp_value is None and vdem_gdp is not None:
        # V-Dem GDP is a Fariss et al. latent-variable estimate, not a
        # Maddison/WDI currency-denominated GDP. It is useful for coverage
        # but gets an explicit unit label so consumers do not compare it as
        # dollars.
        gdp_value = vdem_gdp.gdp
        gdp_unit = "vdem_latent_gdp_units"
        gdp_source = SOURCE_TAG_VDEM
        gdp_year_used = str(vdem_gdp.source_year_used)

    has_gdp = gdp_value is not None
    row["gdp"] = coerce_float(gdp_value, decimals=0)
    row["gdp_unit"] = gdp_unit
    if has_gdp:
        row["gdp_source"] = gdp_source
        row["gdp_source_year_used"] = coerce_int(
            int(gdp_year_used) if gdp_year_used else year,
        )
    else:
        row["gdp_source"] = SOURCE_NA
        row["gdp_source_year_used"] = ""

    # GDP per capita: prefer Maddison's direct ``gdppc`` (2011
    # international dollars) when it is available; fall back to WDI's
    # direct per-capita; fall back to derived GDP / population.
    # The Maddison proxy branch is restricted to year == 2023 (the
    # documented 1-year-gap proxy); for 2024+ the Maddison 2022 row
    # is NOT reused as a multi-year stale proxy, so this branch
    # only fires when the proxy actually filled the GDP/pop fields
    # above (i.e. when ``gdp_source == SOURCE_TAG_MADDISON`` and
    # ``year == MADDISON_PROXY_REQUESTED_YEAR``).
    per_cap_value: float | None = None
    per_cap_unit = ""
    per_cap_method = ""

    if (
        maddison_gdppc is not None
        and maddison_pop is not None
        and year <= MADDISON_PROXY_REQUESTED_YEAR - 1
    ):
        per_cap_value = maddison_gdppc
        per_cap_unit = "2011_intl_dollars"
        per_cap_method = "maddison_direct"
    elif (
        maddison_gdppc is not None
        and maddison_pop is not None
        and year == MADDISON_PROXY_REQUESTED_YEAR
        and maddison_is_proxy
        and wdi_gdp_per_capita is None
        and gdp_source == SOURCE_TAG_MADDISON
        and population_source == SOURCE_TAG_MADDISON
    ):
        per_cap_value = maddison_gdppc
        per_cap_unit = "2011_intl_dollars"
        per_cap_method = "maddison_direct_proxy"
    elif wdi_gdp_per_capita is not None:
        per_cap_value = wdi_gdp_per_capita
        per_cap_unit = "current_usd"
        per_cap_method = "wdi_direct"
    elif vdem_gdp is not None and gdp_source == SOURCE_TAG_VDEM:
        per_cap_value = vdem_gdp.gdppc
        per_cap_unit = "vdem_latent_gdppc_units"
        per_cap_method = "vdem_latent_direct"
    elif (
        gdp_value is not None
        and has_population
        and population_value is not None
        and gdp_source == population_source
        and gdp_source in {SOURCE_TAG_MADDISON, SOURCE_TAG_WDI}
    ):
        per_cap_value = gdp_value / population_value
        per_cap_unit = gdp_unit
        per_cap_method = "derived_gdp_over_population"

    row["gdp_per_capita"] = coerce_float(per_cap_value, decimals=2)
    row["gdp_per_capita_unit"] = per_cap_unit
    row["gdp_per_capita_method"] = per_cap_method

    return has_population, has_gdp, economy_flags


# Re-export the helper at the public name so the row builder
# imports a single function. The WDI-only helper stays in
# ``_wdi_fields.py`` for any caller that wants the original
# WDI-only path; the row builder now uses this module instead.
__all__ = [
    "RelevantGdpCoverage",
    "populate_economy_fields",
    "populate_economy_with_proxy",
    "relevant_gdp_coverage",
]


def populate_economy_with_proxy(
    row: dict[str, str],
    *,
    iso3: str,
    year: int,
    wdi: WdiSource,
    maddison: MaddisonSource | None,
    vdem: VDemSource | None = None,
) -> tuple[bool, bool, bool, tuple[str, ...]]:
    """Populate economy fields and surface the Maddison proxy flag.

    Returns ``(has_population, has_gdp, maddison_is_proxy, economy_flags)``. The
    proxy flag is plumbed out so the caller can add
    ``proxy_year_used`` to ``data_quality_flags`` whenever the
    Maddison 2022 1-year-gap proxy actually fired (year == 2023
    with WDI absent). For 2024+ the Maddison 2022 row is NOT
    reused as a multi-year stale proxy, so this flag never fires
    for those years.
    """
    has_population, has_gdp, economy_flags = populate_economy_fields(
        row,
        iso3=iso3,
        year=year,
        wdi=wdi,
        maddison=maddison,
        vdem=vdem,
    )
    maddison_is_proxy = (
        year == MADDISON_PROXY_REQUESTED_YEAR
        and maddison is not None
        and (
            row.get("population_source") == SOURCE_TAG_MADDISON
            or row.get("gdp_source") == SOURCE_TAG_MADDISON
        )
    )
    return has_population, has_gdp, maddison_is_proxy, economy_flags


# ---------------------------------------------------------------------------
# Coverage metric helper
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RelevantGdpCoverage:
    """Relevant-denominator GDP coverage summary for a row list.

    The relevant denominator for the Increment 5 + 6 GDP
    coverage metric is **only** the rows whose
    ``existence_status == "exists"``. Rows that are
    ``not_formed`` (the country did not exist yet) or
    ``split_or_dissolved`` (the country has been dissolved)
    carry no GDP-relevant evidence and must NOT enter the
    denominator. This helper applies that contract so the
    coverage report can be reproduced byte-for-byte.
    """

    exists_total: int
    exists_with_gdp: int
    not_formed_excluded: int
    split_or_dissolved_excluded: int

    @property
    def coverage_fraction(self) -> float:
        """Return the coverage as a fraction in ``[0, 1]``."""
        if self.exists_total == 0:
            return 0.0
        return self.exists_with_gdp / self.exists_total


def relevant_gdp_coverage(
    rows: list[dict[str, str]],
) -> RelevantGdpCoverage:
    """Compute the Increment 5 + 6 GDP coverage summary.

    Parameters
    ----------
    rows:
        Condensed rows carrying ``existence_status`` and
        ``gdp`` (the two fields the metric reads). The
        function tolerates missing or empty ``gdp`` values
        (treated as "not covered") and missing
        ``existence_status`` (treated as not-existing
        exclusions).
    """
    exists_total = 0
    exists_with_gdp = 0
    not_formed_excluded = 0
    split_or_dissolved_excluded = 0
    for row in rows:
        status = (row.get("existence_status") or "").strip()
        if status == EXISTS_STATUS_EXISTS:
            exists_total += 1
            if (row.get("gdp") or "").strip():
                exists_with_gdp += 1
        elif status == EXISTS_STATUS_NOT_FORMED:
            not_formed_excluded += 1
        elif status == EXISTS_STATUS_SPLIT:
            split_or_dissolved_excluded += 1
    return RelevantGdpCoverage(
        exists_total=exists_total,
        exists_with_gdp=exists_with_gdp,
        not_formed_excluded=not_formed_excluded,
        split_or_dissolved_excluded=split_or_dissolved_excluded,
    )
