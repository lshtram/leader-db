"""Per-source constants for the Country-Year Chronicle slice.

This module owns the per-source constants that the row builder,
the source loaders, and the CSV writer share:

- attribution text strings (per ``docs/source-attributions.md``);
- canonical source key tags used in the per-field ``*_source``
  columns;
- per-source confidence values (direct + proxy / multi-leader
  variants).

The module is intentionally small so the slice's most-edited
constants (country metadata, CSV column order, regime/system
mappings) stay in :mod:`leaders_db.chronicle.constants` where the
existing tests already import them.
"""

from __future__ import annotations

from typing import Final

# ---------------------------------------------------------------------------
# Source attribution strings (per docs/source-attributions.md).
# These are byte-identical substrings of the doc; the test
# ``test_chronicle_attribution_matches_attributions_doc`` enforces it.
# ---------------------------------------------------------------------------

VDEM_ATTRIBUTION: Final[str] = (
    "V-Dem v16 (Coppedge et al. 2026)."
)

WDI_ATTRIBUTION: Final[str] = (
    "World Bank WDI (World Bank 2024)."
)

SIPRI_MILEX_ATTRIBUTION: Final[str] = (
    "SIPRI milex (Stockholm International Peace Research Institute 2026)."
)

#: Maddison Project attribution text. Must be byte-identical to
#: ``docs/source-attributions.md`` §1 ``maddison_project`` (the
#: "Attribution text in reports" line). Drift-guarded by
#: :func:`test_maddison_chronicle_attribution_matches_attributions_doc`.
MADDISON_PROJECT_ATTRIBUTION: Final[str] = (
    "Bolt, Jutta and Jan Luiten van Zanden (2024), "
    "'Maddison style estimates of the evolution of the world economy: "
    "A new 2023 update', Journal of Economic Surveys, 1-41. "
    "DOI: 10.1111/joes.12618. Licensed under CC BY 4.0 "
    "(https://creativecommons.org/licenses/by/4.0/)."
)

ARCHIGOS_ATTRIBUTION: Final[str] = (
    "Archigos v4.1 (Goemans, Gleditsch, and Chiozza 2009)."
)

#: REIGN attribution text. Must be byte-identical to
#: ``docs/source-attributions.md`` §1 ``reign`` (the
#: "Attribution text in reports" line). Drift-guarded by
#: :func:`test_reign_chronicle_attribution_matches_attributions_doc`.
REIGN_ATTRIBUTION: Final[str] = (
    "REIGN dataset (Bell 2016), snapshot of August 2021."
)

#: CShapes 2.0 attribution text. Must be byte-identical to
#: ``docs/source-attributions.md`` §1 ``cshapes`` (the
#: "Attribution text in reports" line). Drift-guarded by
#: :func:`test_cshapes_chronicle_attribution_matches_attributions_doc`.
CSHAPES_ATTRIBUTION: Final[str] = (
    "CShapes 2.0 (Schvitz et al. 2022), ETH Zurich ICR."
)

#: Soviet leaders (curated, Wikipedia-anchored) attribution text.
#: Must be byte-identical to ``docs/source-attributions.md`` §1
#: ``soviet_leaders_curated``. Drift-guarded by
#: :func:`test_soviet_leaders_curated_attribution_matches_attributions_doc`.
SOVIET_LEADERS_CURATED_ATTRIBUTION: Final[str] = (
    "Soviet leaders (curated subset, Wikipedia 'List of leaders of the "
    "Soviet Union'), as of 2026-06-21."
)

#: Archigos v4.1 country code (COW) -> ISO3 mapping for the
#: pilot countries. Used by the ruler resolver to map raw
#: Archigos / REIGN ``ccode`` cells into the project's ISO3
#: identities. Adding a country means a new COW->ISO3 entry.
ARCHIGOS_COW_TO_ISO3: Final[dict[int, str]] = {
    2: "USA",
    200: "GBR",
    220: "FRA",
    750: "IND",
    365: "RUS",
    710: "CHN",
}

#: REIGN uses the same COW country codes as Archigos. Kept as a
#: separate name for readability at the call site.
REIGN_COW_TO_ISO3: Final[dict[int, str]] = ARCHIGOS_COW_TO_ISO3.copy()

#: Archigos coverage end-year. The .dta file's last spell ends
#: 2015-12-31 (per the bundle metadata).
ARCHIGOS_COVERAGE_END_YEAR: Final[int] = 2015

#: REIGN coverage end-year. The CSV's last month is 2021-08.
REIGN_COVERAGE_END_YEAR: Final[int] = 2021

#: REIGN coverage start-year.
REIGN_COVERAGE_START_YEAR: Final[int] = 1950

#: CShapes 2.0 coverage end-year. The bundle's last country-period
#: row ends at 2019-12-31 (per the metadata). The Chronicle row
#: builder attaches the ``area_proxy_year_used`` flag when extending
#: past this year so the audit trail is explicit.
CSHAPES_COVERAGE_END_YEAR: Final[int] = 2019

#: CShapes 2.0 coverage start-year. Per the bundle metadata and the
#: CShapes 2.0 documentation (Schvitz et al. 2022), the dataset
#: covers the international system 1886-2019 (the CShapes-Europe
#: extension covers 1816+, but the standard bundle starts at 1886).
CSHAPES_COVERAGE_START_YEAR: Final[int] = 1886

#: CShapes 2.0 Gleditsch-Ward state code -> ISO3 mapping for the
#: pilot countries. Used by the CShapes source loader to map raw
#: ``gwcode`` cells into the project's ISO3 identities. Adding a
#: country means a new GW->ISO3 entry.
#:
#: Notes on the SUN/RUS row: CShapes 2.0 carries a single GW code
#: 365 record that spans Russian Empire + USSR + Russian Federation
#: (1886-2019). The Chronicle uses that record for both SUN (during
#: 1922-1991) and RUS (during 1992-2026); the per-year dispatch is
#: handled by :data:`CSHAPES_GW_YEAR_TO_ISO3`, which encodes the
#: ``(gwcode, start_year, end_year) -> ISO3`` mapping.
CSHAPES_GW_TO_ISO3: Final[dict[int, str]] = {
    2: "USA",
    200: "GBR",
    220: "FRA",
    365: "RUS",  # see CSHAPES_GW_YEAR_TO_ISO3 for SUN/RUS dispatch
    710: "CHN",
    750: "IND",
}

#: Per-year dispatch table for CShapes GW codes that map to multiple
#: ISO3 identities. Today the only such case is GW 365, which covers
#: the consolidated Russian Empire + USSR + Russian Federation
#: record in CShapes 2.0. The Chronicle treats SUN (1922-1991) and
#: RUS (1992-) as separate identities and uses this table to pick
#: the right ISO3 for a given year.
#:
#: Note on 1991: RUS's COUNTRY_METADATA start_year is 1991 (the
#: Russian SFSR declared sovereignty in 1990 and the CIS was formed
#: 1991-12-08), while SUN's end_year is 1991 (formal dissolution
#: 1991-12-26). The dispatch lets RUS read GW 365 from 1991
#: onward so the RUS 1991 row has area; the SUN dispatch
#: deliberately excludes 1992+ so post-dissolution years belong to
#: RUS. This means SUN 1991 and RUS 1991 both read the GW 365
#: 1991-only row (last year of the consolidated record). Adding a
#: new split-identity source means a new entry here.
CSHAPES_GW_YEAR_TO_ISO3: Final[tuple[tuple[int, int, int, str], ...]] = (
    # GW 365 split: SUN during 1922-1991; RUS from 1991 onward.
    (365, 1922, 1991, "SUN"),
    (365, 1991, 9999, "RUS"),
)

#: Maddison Project Database 2023 proxy year constants. The 2023
#: release ends at 2022; when the user asks for year >= 2023 the
#: helper uses 2022 as a 1-year-gap proxy and tags the row with
#: ``proxy_year_used``.
MADDISON_PROXY_YEAR: Final[int] = 2022
MADDISON_PROXY_REQUESTED_YEAR: Final[int] = 2023

# ---------------------------------------------------------------------------
# Canonical source key tags used in the per-field source columns.
# ---------------------------------------------------------------------------

SOURCE_TAG_VDEM: Final[str] = "vdem"
SOURCE_TAG_WDI: Final[str] = "wdi"
SOURCE_TAG_SIPRI: Final[str] = "sipri_milex"
SOURCE_TAG_MADDISON: Final[str] = "maddison_project"
SOURCE_TAG_ARCHIGOS: Final[str] = "archigos"
SOURCE_TAG_REIGN: Final[str] = "reign"
SOURCE_TAG_CSHAPES: Final[str] = "cshapes"
SOURCE_TAG_SOVIET_LEADERS_CURATED: Final[str] = "soviet_leaders_curated"
SOURCE_TAG_CURATED: Final[str] = "cyc_curated"
SOURCE_TAG_NONE: Final[str] = ""

# ---------------------------------------------------------------------------
# Per-source confidence values (0-100, used in the row's
# ``row_confidence`` aggregate + per-field ``*_confidence`` columns
# when applicable).
# ---------------------------------------------------------------------------

#: V-Dem regime values are scored at this confidence when they come
#: directly from the raw V-Dem CSV for the exact requested year.
VDEM_DIRECT_CONFIDENCE: Final[int] = 80

#: V-Dem regime values copied from ``DEFAULT_PROXY_YEAR`` because the
#: requested year is beyond V-Dem coverage are scored at this lower
#: confidence.
VDEM_PROXY_CONFIDENCE: Final[int] = 60

#: WDI values copied from the processed parquet for the exact year are
#: scored at this confidence.
WDI_DIRECT_CONFIDENCE: Final[int] = 80

#: SIPRI milex values from the processed parquet for the exact year are
#: scored at this confidence.
SIPRI_DIRECT_CONFIDENCE: Final[int] = 80

#: Maddison Project values copied from the exact requested year (when
#: Maddison has a direct hit) are scored at this confidence. Maddison
#: is the canonical historical real-economy source for the prototype
#: and the long-run-comparable 2011 international dollar units are
#: preferred over WDI constant-USD when both are available.
MADDISON_DIRECT_CONFIDENCE: Final[int] = 75

#: Maddison Project values proxied from the most recent year (the
#: 2023 release ends at 2022, so a 2023 target-year request is
#: proxied to 2022) are scored at this lower confidence. The
#: proxy_year_used flag is added to the row so the audit trail is
#: explicit.
MADDISON_PROXY_CONFIDENCE: Final[int] = 55

#: Archigos leader-name values for the exact requested year are
#: scored at this confidence (single-leader direct hit).
ARCHIGOS_DIRECT_CONFIDENCE: Final[int] = 70

#: REIGN leader-name values for the exact requested year are scored
#: at this confidence when there is one clear leader for the year
#: (leader covers the whole year in the leader-month frame). When
#: multiple leaders share the year, the helper picks the leader with
#: the most months and applies :data:`REIGN_MULTI_LEADER_CONFIDENCE`
#: instead.
REIGN_DIRECT_CONFIDENCE: Final[int] = 65

#: REIGN leader values for years with multiple leaders (the helper
#: picks the leader with the most months and emits the
#: ``multiple_rulers`` flag).
REIGN_MULTI_LEADER_CONFIDENCE: Final[int] = 50

#: CShapes 2.0 area values for the exact CShapes coverage year
#: (1886-2019 for the bundled CSV).
CSHAPES_DIRECT_CONFIDENCE: Final[int] = 80

#: CShapes 2.0 area values copied from the most recent CShapes
#: year because the requested year is beyond CShapes coverage
#: (2020+). The proxy flag is added to the row so the audit trail
#: is explicit.
CSHAPES_PROXY_CONFIDENCE: Final[int] = 60

#: Soviet leaders (curated) confidence for years with a single
#: leader in the curated spell table (the typical case for most
#: SUN years).
SOVIET_LEADERS_DIRECT_CONFIDENCE: Final[int] = 70

#: Soviet leaders (curated) confidence for years with multiple
#: leaders (e.g. 1924 Lenin->Stalin, 1953 Stalin->Malenkov->
#: Khrushchev, 1985 Chernenko->Gorbachev). The resolver picks the
#: leader with the most days in the year and emits the
#: ``multiple_rulers`` flag.
SOVIET_LEADERS_MULTI_LEADER_CONFIDENCE: Final[int] = 50


__all__ = [
    "ARCHIGOS_ATTRIBUTION",
    "ARCHIGOS_COVERAGE_END_YEAR",
    "ARCHIGOS_COW_TO_ISO3",
    "ARCHIGOS_DIRECT_CONFIDENCE",
    "CSHAPES_ATTRIBUTION",
    "CSHAPES_COVERAGE_END_YEAR",
    "CSHAPES_COVERAGE_START_YEAR",
    "CSHAPES_DIRECT_CONFIDENCE",
    "CSHAPES_GW_TO_ISO3",
    "CSHAPES_GW_YEAR_TO_ISO3",
    "CSHAPES_PROXY_CONFIDENCE",
    "MADDISON_DIRECT_CONFIDENCE",
    "MADDISON_PROJECT_ATTRIBUTION",
    "MADDISON_PROXY_CONFIDENCE",
    "MADDISON_PROXY_REQUESTED_YEAR",
    "MADDISON_PROXY_YEAR",
    "REIGN_ATTRIBUTION",
    "REIGN_COVERAGE_END_YEAR",
    "REIGN_COVERAGE_START_YEAR",
    "REIGN_COW_TO_ISO3",
    "REIGN_DIRECT_CONFIDENCE",
    "REIGN_MULTI_LEADER_CONFIDENCE",
    "SIPRI_DIRECT_CONFIDENCE",
    "SIPRI_MILEX_ATTRIBUTION",
    "SOURCE_TAG_ARCHIGOS",
    "SOURCE_TAG_CSHAPES",
    "SOURCE_TAG_CURATED",
    "SOURCE_TAG_MADDISON",
    "SOURCE_TAG_NONE",
    "SOURCE_TAG_REIGN",
    "SOURCE_TAG_SIPRI",
    "SOURCE_TAG_SOVIET_LEADERS_CURATED",
    "SOURCE_TAG_VDEM",
    "SOURCE_TAG_WDI",
    "SOVIET_LEADERS_CURATED_ATTRIBUTION",
    "SOVIET_LEADERS_DIRECT_CONFIDENCE",
    "SOVIET_LEADERS_MULTI_LEADER_CONFIDENCE",
    "VDEM_ATTRIBUTION",
    "VDEM_DIRECT_CONFIDENCE",
    "VDEM_PROXY_CONFIDENCE",
    "WDI_ATTRIBUTION",
    "WDI_DIRECT_CONFIDENCE",
]
