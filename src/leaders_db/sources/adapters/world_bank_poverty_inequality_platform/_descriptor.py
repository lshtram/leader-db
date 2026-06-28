"""Descriptor factory for the clean World Bank Poverty and Inequality
Platform (PIP) adapter.

This module owns the canonical :class:`SourceDescriptor` for
the World Bank PIP source. The descriptor advertises the static
source metadata the registry exposes for source discovery
(SRC-ID-003): the canonical slug
``world_bank_poverty_inequality_platform``, the canonical PIP
homepage URL, the canonical coverage envelope, the canonical
PIP version stamp, the single
``poverty_inequality_country_year`` observation family, the
cache-only network policy, and the explicit caveat that
PIP poverty / inequality estimates are SURVEY- and PPP-specific
and SHOULD NOT be silently mixed across PIP version stamps or
PPP bases without explicit metadata propagation.

Coverage envelope
-----------------

PIP coverage is version-stamped and PPP / survey / welfare-type
specific. The descriptor advertises a conservative broad envelope
(``start_year=1960`` / ``end_year=2024``) and the canonical
PIP version stamp ``"World Bank PIP, version 20260324_2021"``
so downstream query code can refuse to dispatch out-of-coverage
year requests. The readiness gate surfaces a structured
``YEAR_ABSENT`` warning on out-of-coverage year requests so the
runner never silently proxies an out-of-coverage year to the
nearest in-coverage year (SRC-COV-002 / SRC-COV-003). The
prototype's target year 2023 falls INSIDE the canonical envelope
(1960-2024) so 2023 is in-coverage.

Source-type semantics
---------------------

The descriptor advertises ``source_type="api"`` because the
canonical PIP dataset is delivered through a documented backend
API at ``https://pip.worldbank.org/api`` (CSV / JSON endpoints),
even though the unified adapter in this slice is offline /
cache-only. ``requires_network=False`` -- the unified adapter
never invokes the network; the readiness gate blocks
``cache_policy="refresh"`` / ``"no_cache"`` with a structured
``world_bank_poverty_inequality_platform_unsupported_cache_policy``
error so the runner refuses to dispatch ``read_raw`` /
``transform`` rather than silently surfacing an HTTP-fetched
payload.

Observation-family shape
------------------------

The descriptor advertises a single observation family
(``poverty_inequality_country_year``) so downstream query code
can filter by family without consulting the per-source catalog.
The catalog carries 3 source-native numeric indicators (one
per indicator cell typically exposed by the canonical PIP CSV /
JSON export):

- ``world_bank_poverty_inequality_platform_poverty_headcount_ratio``
  -- the poverty headcount ratio at the row's poverty line.
- ``world_bank_poverty_inequality_platform_poverty_gap`` -- the
  poverty gap at the row's poverty line.
- ``world_bank_poverty_inequality_platform_gini_index`` -- the
  Gini index of the row's distribution.

The catalog deliberately does NOT include a default PPP factor
or survey-year indicator beyond what the source-native CSV /
JSON explicitly exposes; the transform never invents a value
from missing source-native data.

Caveat
------

PIP poverty / inequality estimates are SURVEY- and PPP-specific
and SHOULD NOT be silently mixed across PIP version stamps
(e.g. ``20260324_2021`` vs ``20260324_2017``) or PPP bases
(2021 PPP vs 2017 PPP) without explicit metadata propagation.
The descriptor's ``coverage_hint.notes`` carries the explicit
caveat. Downstream scorers MUST NOT silently treat a PIP
poverty / inequality cell as comparable across version stamps
or PPP bases without explicit metadata propagation; the adapter
preserves the source-native PPP version + reporting level +
welfare type + poverty line on the audit-trail extension payload
so downstream code can recover the verbatim provenance.

Attribution text
----------------

The unified
:data:`WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_ATTRIBUTION_TEXT`
constant is byte-identical to the
``world_bank_poverty_inequality_platform`` section in
``docs/sources/attributions.md`` (Always-On Rule #15). The
:func:`test_world_bank_poverty_inequality_platform_attribution_text_matches_attributions_doc`
drift guard enforces byte-identity. The text is intentionally
distinct from the ``world_bank_wdi`` and ``world_bank_wgi``
attribution strings -- PIP is a separate World Bank sub-dataset
with its own citation block.
"""

from __future__ import annotations

from leaders_db.sources.contracts import (
    CoverageHint,
    SourceDescriptor,
    SourceId,
)

from ._constants import (
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_ATTRIBUTION_KEY,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_COVERAGE_END_YEAR,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_COVERAGE_START_YEAR,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_CSV_NAME,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_VERSION,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_HOMEPAGE_URL,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_INDICATOR_CODES,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_JSON_NAME,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_SOURCE_KEY,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_SUPPORTED_FAMILIES,
)


def build_world_bank_poverty_inequality_platform_descriptor() -> (
    SourceDescriptor
):
    """Build the canonical World Bank PIP :class:`SourceDescriptor`.

    The descriptor is the static metadata the registry exposes
    for source discovery (SRC-ID-003). The values mirror the
    canonical citation block in
    ``docs/sources/attributions.md``
    (``world_bank_poverty_inequality_platform`` section;
    Rule #15).

    The descriptor advertises ``source_type="api"`` and
    ``requires_network=False`` so downstream query code and the
    runner can refuse to dispatch network I/O unconditionally
    for World Bank PIP (the unified adapter is cache-only in
    this slice; the cache-policy gate blocks unsupported
    policies with a structured
    ``world_bank_poverty_inequality_platform_unsupported_cache_policy``
    error).
    """
    return SourceDescriptor(
        source_id=SourceId(
            slug=WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_SOURCE_KEY,
        ),
        display_name=(
            "World Bank Poverty and Inequality Platform "
            "(World Bank Group, version 20260324_2021)"
        ),
        source_type="api",
        supported_observation_families=(
            WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_SUPPORTED_FAMILIES
        ),
        default_version=WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_VERSION,
        homepage_url=WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_HOMEPAGE_URL,
        attribution_key=WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_ATTRIBUTION_KEY,
        coverage_hint=CoverageHint(
            start_year=WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_COVERAGE_START_YEAR,
            end_year=WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_COVERAGE_END_YEAR,
            countries=None,
            leaders=None,
            notes=(
                "World Bank Poverty and Inequality Platform (PIP) "
                "country-year poverty / inequality / distribution "
                "observations: poverty headcount ratio, poverty gap, "
                "Gini index per (country_code, country_name, year, "
                "reporting_level, welfare_type, poverty_line) row. "
                "Broad coverage envelope 1960-2024 (canonical PIP "
                "probe stamp is 2021 for the 20260324_2021 PIP "
                "version, with a few extrapolation cells into 2024 "
                "for a handful of countries). The clean adapter "
                f"reads a single cached CSV (`{WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_CSV_NAME}`) "
                f"or cached JSON (`{WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_JSON_NAME}`) "
                "export from `data/raw/world_bank_poverty_inequality_platform/` "
                "plus a runtime-local `metadata.json` (gitignored "
                "per Always-On Rule #9). The descriptor advertises "
                "ONE observation family (`poverty_inequality_country_year`) "
                "and the canonical 3-indicator catalog "
                "(`world_bank_poverty_inequality_platform_poverty_headcount_ratio`, "
                "`world_bank_poverty_inequality_platform_poverty_gap`, "
                "`world_bank_poverty_inequality_platform_gini_index`). "
                "**Important caveat:** PIP poverty / inequality "
                "estimates are SURVEY- and PPP-specific and SHOULD "
                "NOT be silently mixed across PIP version stamps "
                "(e.g. 20260324_2021 vs 20260324_2017) or PPP bases "
                "(2021 PPP vs 2017 PPP) without explicit metadata "
                "propagation; the adapter preserves the source-native "
                "PPP version + reporting level + welfare type + "
                "poverty line on the audit-trail extension payload "
                "so downstream code can recover the verbatim "
                "provenance. The descriptor advertises the canonical "
                "PIP version stamp on `default_version` and propagates "
                "the version + PPP version onto every emitted "
                "observation's extension payload; downstream scorers "
                "MUST NOT silently treat a PIP cell as comparable "
                "across version stamps or PPP bases without explicit "
                "metadata propagation. The cached CSV / JSON row "
                "schema is the canonical 11-column contract "
                "(country_code / country_name / year / reporting_level / "
                "welfare_type / poverty_line / headcount / poverty_gap / "
                "gini / version_id / ppp_version); missing required "
                "columns fail readiness with "
                "a structured "
                "`world_bank_poverty_inequality_platform_schema_error` "
                "error BEFORE the transform layer consumes the frame. "
                "The unified adapter preserves the source-native "
                "country code + display name verbatim (the PIP "
                "country_code is the World Bank's own reporting "
                "identifier -- a 3-character code that LOOKS LIKE "
                "ISO3 but is NOT a canonical ISO3 mapping; the "
                "adapter does NOT assume it is ISO3 even when it "
                "resembles one; `country_code` is left as `None` "
                "and the source-native identifier is preserved on "
                "`extension['world_bank_poverty_inequality_platform_country_code_raw']`). "
                "Blank / non-numeric cells are emitted as "
                "`value=None` / `value_type='missing'` plus the "
                "verbatim raw cell text on `extension.raw_value` -- "
                "the transform never invents a value from missing "
                "source-native data. The canonical PIP home page is "
                f"`{WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_HOMEPAGE_URL}`; "
                "the canonical PIP API is "
                "`https://pip.worldbank.org/api`. The unified adapter "
                "never invokes the network in this slice; live fetch "
                "is intentionally NOT supported. "
                "`cache_policy='refresh'` / `'no_cache'` fails "
                "readiness with a structured "
                "`world_bank_poverty_inequality_platform_unsupported_cache_policy` "
                "error BEFORE `read_raw` / `transform` are called. "
                "The canonical attribution text is "
                "`World Bank (2025) Poverty and Inequality Platform "
                "(version {version_ID}) [Data set] World Bank Group, "
                "www.pip.worldbank.org.` (byte-identical to the "
                "`world_bank_poverty_inequality_platform` section in "
                "`docs/sources/attributions.md` per Always-On Rule "
                "#15); the {version_ID} placeholder is interpolated "
                "at observation emission time from the bundle's "
                "canonical PIP version stamp."
            ),
        ),
        requires_manual_approval=False,
        requires_network=False,
    )


__all__ = [
    "build_world_bank_poverty_inequality_platform_descriptor",
]


# Re-export the indicator-codes tuple so downstream consumers can
# import the canonical catalog via the descriptor module without
# reaching into ``_constants``.
WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DESCRIPTOR_INDICATOR_CODES = (
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_INDICATOR_CODES
)
