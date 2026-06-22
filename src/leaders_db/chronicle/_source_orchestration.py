"""Source orchestration for the Country-Year Chronicle runner.

This module owns the source-loading and sources-used-detection
helpers used by :mod:`leaders_db.chronicle.runner`. It is split
out of ``runner.py`` so the runner itself stays focused on the
orchestration boundary (CLI seam + path discovery + output
selection) and remains within the documented 400-line convention
after the Increment 5 all-country + condensed-export extensions.

Public helpers:

- :func:`load_all_sources` — load the V-Dem / WDI / SIPRI /
  Maddison / Archigos / REIGN / SUN curated / CShapes slices
  for the requested ISO3 set, returning a
  :class:`LoadedSources` bundle.
- :func:`detect_sources_used` — scan the detailed rows and
  return the sorted list of source tags that contributed a
  non-empty value to any row (this drives the attribution
  block in the CSV / SQLite).

Path defaults (the canonical data-lake paths) stay in
:mod:`leaders_db.chronicle.runner` because they are the public
Python seam callers use to resolve the runner's default paths
without invoking the full orchestrator.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from ._area_source import load_cshapes_source
from .ruler_resolver import (
    RulerResolver,
    load_ruler_resolver,
)
from .sources import (
    load_maddison_source,
    load_sipri_source,
    load_vdem_source,
    load_wdi_source,
)

if TYPE_CHECKING:
    from ._area_source import CShapesSource
    from .sources import MaddisonSource, SipriSource, VDemSource, WdiSource


@dataclass(frozen=True)
class LoadedSources:
    """Bundle of the source loaders consumed by the row builder.

    The bundle keeps the call sites short: the orchestrator passes
    a single :class:`LoadedSources` into
    :func:`build_chronicle_rows` instead of unpacking 6+ source
    objects at the call site.
    """

    vdem: VDemSource
    wdi: WdiSource
    sipri: SipriSource
    maddison: MaddisonSource
    ruler_resolver: RulerResolver
    cshapes: CShapesSource | None


def load_all_sources(
    *,
    iso3_scope: tuple[str, ...],
    vdem_csv_path: Path,
    wdi_parquet_path: Path,
    sipri_parquet_path: Path,
    maddison_xlsx_path: Path,
    archigos_dta_path: Path,
    reign_csv_path: Path,
    sun_csv_path: Path,
    cshapes_csv_path: Path,
    wdi_cache_dir: Path | None = None,
    wikidata_recent_years: tuple[int, ...] = (),
    wikidata_recent_cache_dir: Path | None = None,
    wikidata_recent_force_refresh: bool = False,
    wikidata_recent_timeout: float = 60.0,
) -> LoadedSources:
    """Load every chronicle source for the requested ``iso3_scope``.

    Parameters
    ----------
    iso3_scope:
        ISO3 keys the row builder will iterate over. Source loaders
        narrow their in-memory frame to this scope so per-row
        lookups are O(1) in a dict.
    vdem_csv_path, wdi_parquet_path, sipri_parquet_path,
    maddison_xlsx_path, archigos_dta_path, reign_csv_path,
    sun_csv_path, cshapes_csv_path:
        Resolved source paths. Callers should pass either the
        canonical defaults from :mod:`leaders_db.chronicle.runner`
        or an override from the CLI / Python API.
    wdi_cache_dir:
        Optional WDI v2 coverage-cache directory
        (``data/raw/world_bank_wdi/coverage_cache/``). When the
        directory exists the WDI loader merges its rows with the
        processed parquet (cache wins on ``(iso3, year)``
        collisions). When the directory is missing or
        unrecognizable, the loader falls back to the parquet
        only. Bounded to 1960-2024; never contributes 2025/2026
        rows.
    wikidata_recent_years:
        Calendar years the resolver should consult the Wikidata
        recent-rulers fallback for (2022-2026 today). Empty
        disables the fallback entirely.
    wikidata_recent_cache_dir:
        Override the SPARQL JSON cache directory.
    wikidata_recent_force_refresh:
        When ``True``, re-download every requested year even when
        a cache file exists.
    wikidata_recent_timeout:
        Per-request HTTP timeout in seconds.
    """
    vdem = load_vdem_source(raw_csv_path=vdem_csv_path, iso3_scope=iso3_scope)
    wdi = load_wdi_source(
        parquet_path=wdi_parquet_path,
        iso3_scope=iso3_scope,
        cache_dir=wdi_cache_dir,
    )
    sipri = load_sipri_source(
        parquet_path=sipri_parquet_path, iso3_scope=iso3_scope
    )
    maddison = load_maddison_source(
        xlsx_path=maddison_xlsx_path, iso3_scope=iso3_scope
    )
    ruler_resolver = load_ruler_resolver(
        archigos_dta_path=archigos_dta_path,
        reign_csv_path=reign_csv_path,
        sun_csv_path=sun_csv_path,
        iso3_scope=iso3_scope,
        wikidata_recent_years=wikidata_recent_years,
        wikidata_recent_cache_dir=wikidata_recent_cache_dir,
        wikidata_recent_force_refresh=wikidata_recent_force_refresh,
        wikidata_recent_timeout=wikidata_recent_timeout,
    )
    cshapes = load_cshapes_source(csv_path=cshapes_csv_path, iso3_scope=iso3_scope)
    return LoadedSources(
        vdem=vdem,
        wdi=wdi,
        sipri=sipri,
        maddison=maddison,
        ruler_resolver=ruler_resolver,
        cshapes=cshapes,
    )


def detect_sources_used(
    rows: list[dict[str, str]],
    *,
    vdem_has_data: bool,
    maddison_has_data: bool,
    ruler_resolver: RulerResolver,
    cshapes_has_data: bool,
) -> list[str]:
    """Return the sorted list of source tags that contributed data.

    V-Dem is included when the source V-Dem frame had any rows.
    WDI / Maddison are included when any row's ``population`` or
    ``gdp`` field is non-empty (and the source tag in the
    per-row ``population_source`` / ``gdp_source`` matches).
    SIPRI is included when any row's ``military_spend`` field is
    non-empty. Archigos / REIGN / SUN curated are included when
    the resolver actually returned a ruler name (i.e. the source
    frame had records). CShapes is included when the source
    frame had any rows for the requested ISO3 set.
    """
    used: set[str] = set()
    if vdem_has_data:
        used.add("vdem")
    if maddison_has_data:
        used.add("maddison_project")
    if not ruler_resolver.archigos_frame.empty:
        used.add("archigos")
    if not ruler_resolver.reign_frame.empty:
        used.add("reign")
    if not ruler_resolver.sun_frame.empty:
        used.add("soviet_leaders_curated")
    if cshapes_has_data:
        used.add("cshapes")
    for row in rows:
        pop_src = row.get("population_source", "")
        gdp_src = row.get("gdp_source", "")
        if pop_src == "maddison_project" or gdp_src == "maddison_project":
            used.add("maddison_project")
        if pop_src == "wdi" or gdp_src == "wdi":
            used.add("wdi")
        if row.get("military_spend"):
            used.add("sipri_milex")
        if row.get("ruler_source") == "archigos":
            used.add("archigos")
        if row.get("ruler_source") == "reign":
            used.add("reign")
        if row.get("ruler_source") == "soviet_leaders_curated":
            used.add("soviet_leaders_curated")
        if row.get("ruler_source") == "wikidata_recent_rulers":
            used.add("wikidata_recent_rulers")
        if row.get("ruler_source") == "colonial_rule_placeholder":
            used.add("colonial_rule_placeholder")
        if row.get("area_source") == "cshapes":
            used.add("cshapes")
        # A row with a V-Dem-derived regime bucket (anything other
        # than empty source) also implies V-Dem was used, even if
        # the raw frame was empty (the row builder can fall back to
        # the polyarchy path).
        if row.get("political_regime_source") == "vdem":
            used.add("vdem")
    return sorted(used)


__all__ = [
    "LoadedSources",
    "detect_sources_used",
    "load_all_sources",
]
