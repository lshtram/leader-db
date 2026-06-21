"""Runner for the Country-Year Chronicle slice.

The runner is the public Python entry point for the slice. It:

1. Loads the V-Dem, WDI, SIPRI, Maddison, Archigos, REIGN, SUN
   curated, and CShapes sources from the local data lake.
2. Builds the per-row data via :func:`build_chronicle_rows`.
3. Writes the CSV via :func:`csv_writer.write_chronicle_csv`.

The function is the Python seam the CLI calls. Tests call it
directly to drive the slice end-to-end without a CLI.

Increment 2 added Maddison (historical real economy, 1-2022, 2023
proxied to 2022), Archigos (historical leader spells, through
2015), and REIGN (monthly leader records, 1950-2021) on top of the
Increment 1 WDI / V-Dem / SIPRI trio.

Increment 3 added CShapes 2.0 (country area, 1886-2019) and the
curated Soviet-leaders spell list (SUN rulers, 1922-12-30 to
1991-12-25). The runner is the single place that decides which
sources are loaded for a given CLI invocation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from ._area_source import (
    default_cshapes_csv_path,
    load_cshapes_source,
)
from .constants import (
    CHRONICLE_OUTPUT_DIR_NAME,
    COUNTRY_METADATA,
    DEFAULT_COUNTRIES,
    DEFAULT_END_YEAR,
    DEFAULT_OUTPUT_BASENAME,
    DEFAULT_START_YEAR,
)
from .csv_writer import write_chronicle_csv
from .row_builder import build_chronicle_rows
from .ruler_resolver import (
    default_archigos_dta_path,
    default_reign_csv_path,
    default_sun_csv_path,
    load_ruler_resolver,
)
from .sources import (
    load_maddison_source,
    load_sipri_source,
    load_vdem_source,
    load_wdi_source,
)
from .sqlite_writer import write_chronicle_sqlite

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChronicleResult:
    """Summary of a single ``run_country_year_chronicle`` call.

    Attributes:
        rows_written: Number of CSV data rows (excluding the
            attribution comment lines and the header).
        output_path: Resolved absolute path to the written CSV.
        iso3_scope: ISO3 keys included, in run order.
        start_year, end_year: Inclusive year window.
        sources_used: Sorted tuple of short source tags that
            contributed to the output.
        allow_regime_proxy: Echo of the caller's flag.
        sqlite_output_path: Optional resolved path to the SQLite
            artifact. ``None`` when the caller did not pass
            ``sqlite_output_path`` and the CLI default did not
            opt in.
    """

    rows_written: int
    output_path: Path
    iso3_scope: tuple[str, ...]
    start_year: int
    end_year: int
    sources_used: tuple[str, ...]
    allow_regime_proxy: bool
    sqlite_output_path: Path | None = None

    @property
    def attribution_block(self) -> str:
        """Return the canonical attribution block as a single string.

        The block includes the short tags used in the CSV comment
        lines. Useful for tests that want to assert the block was
        written verbatim.
        """
        from .source_constants import (
            ARCHIGOS_ATTRIBUTION,
            CSHAPES_ATTRIBUTION,
            MADDISON_PROJECT_ATTRIBUTION,
            REIGN_ATTRIBUTION,
            SIPRI_MILEX_ATTRIBUTION,
            SOVIET_LEADERS_CURATED_ATTRIBUTION,
            VDEM_ATTRIBUTION,
            WDI_ATTRIBUTION,
        )

        parts: list[str] = []
        for tag in self.sources_used:
            if tag == "vdem":
                parts.append(VDEM_ATTRIBUTION)
            elif tag == "wdi":
                parts.append(WDI_ATTRIBUTION)
            elif tag == "sipri_milex":
                parts.append(SIPRI_MILEX_ATTRIBUTION)
            elif tag == "maddison_project":
                parts.append(MADDISON_PROJECT_ATTRIBUTION)
            elif tag == "archigos":
                parts.append(ARCHIGOS_ATTRIBUTION)
            elif tag == "reign":
                parts.append(REIGN_ATTRIBUTION)
            elif tag == "cshapes":
                parts.append(CSHAPES_ATTRIBUTION)
            elif tag == "soviet_leaders_curated":
                parts.append(SOVIET_LEADERS_CURATED_ATTRIBUTION)
        return " | ".join(parts)


# ---------------------------------------------------------------------------
# Path defaults
# ---------------------------------------------------------------------------


def default_vdem_csv_path() -> Path:
    """Return the canonical raw V-Dem CSV path inside the data lake."""
    from ..paths import raw_dir

    return raw_dir("vdem") / "V-Dem-CY-Full+Others-v16.csv"


def default_wdi_parquet_path() -> Path:
    """Return the canonical processed WDI parquet path."""
    from ..paths import processed_dir

    return processed_dir("world_bank_wdi") / "wdi_country_year.parquet"


def default_sipri_parquet_path() -> Path:
    """Return the canonical processed SIPRI milex parquet path."""
    from ..paths import processed_dir

    return processed_dir("sipri_milex") / "sipri_milex_country_year.parquet"


def default_maddison_xlsx_path() -> Path:
    """Return the canonical Maddison raw xlsx path inside the data lake."""
    from ..paths import raw_dir

    return raw_dir("maddison_project") / "mpd2023.xlsx"


def default_output_path(
    *, project_root: Path | None = None, basename: str | None = None
) -> Path:
    """Return the canonical output CSV path for the slice.

    Resolves to ``<project_root>/data/outputs/country-year-chronicle/<basename>``.
    """
    from ..paths import project_root as _project_root

    root = project_root if project_root is not None else _project_root()
    base = basename or DEFAULT_OUTPUT_BASENAME
    return root / "data" / "outputs" / CHRONICLE_OUTPUT_DIR_NAME / base


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def run_country_year_chronicle(
    *,
    output_path: Path,
    iso3_scope: tuple[str, ...] = DEFAULT_COUNTRIES,
    start_year: int = DEFAULT_START_YEAR,
    end_year: int = DEFAULT_END_YEAR,
    vdem_csv_path: Path | None = None,
    wdi_parquet_path: Path | None = None,
    sipri_parquet_path: Path | None = None,
    maddison_xlsx_path: Path | None = None,
    archigos_dta_path: Path | None = None,
    reign_csv_path: Path | None = None,
    sun_csv_path: Path | None = None,
    cshapes_csv_path: Path | None = None,
    sqlite_output_path: Path | None = None,
    allow_regime_proxy: bool = True,
) -> ChronicleResult:
    """Run the Country-Year Chronicle slice end-to-end.

    Parameters
    ----------
    output_path:
        Destination CSV path. The parent directory is created if
        missing.
    iso3_scope:
        ISO3 keys to include. Defaults to the Increment 0 pilot set
        (``USA, GBR, FRA, IND, RUS, SUN, CHN``).
    start_year, end_year:
        Inclusive year window. The runner emits one row per
        ``(iso3, year)`` pair regardless of whether any source has
        data for that pair.
    vdem_csv_path, wdi_parquet_path, sipri_parquet_path,
    maddison_xlsx_path, archigos_dta_path, reign_csv_path,
    sun_csv_path, cshapes_csv_path:
        Override paths for the source loaders. Defaults are resolved
        through :func:`leaders_db.paths`.
    sqlite_output_path:
        Optional SQLite artifact path. When provided (or when the
        default resolves to an existing sibling), the runner writes
        a SQLite database alongside the CSV with the same row
        contents (plus a ``source_attributions`` sidecar table).
        Defaults to ``None``; when ``None`` the runner does NOT
        write a SQLite file (the CSV behavior is preserved).
        Pass an explicit ``Path`` to opt in.
    allow_regime_proxy:
        Forwarded to :func:`build_chronicle_rows`. Defaults to True.

    Returns
    -------
    ChronicleResult
        Summary of the run, including the resolved output path and the
        sources that contributed rows with non-empty values. When
        ``sqlite_output_path`` is provided, ``sqlite_output_path``
        on the result carries the resolved path (or ``None`` if
        the SQLite write was skipped).
    """
    # Validate scope early: any unknown ISO3 is a hard error so the
    # caller is told immediately instead of silently dropping it.
    unknown = [iso3 for iso3 in iso3_scope if iso3 not in COUNTRY_METADATA]
    if unknown:
        raise ValueError(
            f"Unknown ISO3 keys (not in COUNTRY_METADATA): {sorted(unknown)}"
        )

    vdem_csv_path = vdem_csv_path or default_vdem_csv_path()
    wdi_parquet_path = wdi_parquet_path or default_wdi_parquet_path()
    sipri_parquet_path = (
        sipri_parquet_path or default_sipri_parquet_path()
    )
    maddison_xlsx_path = (
        maddison_xlsx_path or default_maddison_xlsx_path()
    )
    archigos_dta_path = (
        archigos_dta_path or default_archigos_dta_path()
    )
    reign_csv_path = reign_csv_path or default_reign_csv_path()
    sun_csv_path = sun_csv_path or default_sun_csv_path()
    cshapes_csv_path = cshapes_csv_path or default_cshapes_csv_path()

    # Load sources.
    vdem = load_vdem_source(raw_csv_path=vdem_csv_path, iso3_scope=iso3_scope)
    wdi = load_wdi_source(parquet_path=wdi_parquet_path, iso3_scope=iso3_scope)
    sipri = load_sipri_source(parquet_path=sipri_parquet_path, iso3_scope=iso3_scope)
    maddison = load_maddison_source(
        xlsx_path=maddison_xlsx_path,
        iso3_scope=iso3_scope,
    )
    ruler_resolver = load_ruler_resolver(
        archigos_dta_path=archigos_dta_path,
        reign_csv_path=reign_csv_path,
        sun_csv_path=sun_csv_path,
        iso3_scope=iso3_scope,
    )
    cshapes = load_cshapes_source(
        csv_path=cshapes_csv_path,
        iso3_scope=iso3_scope,
    )

    # Build rows.
    rows = build_chronicle_rows(
        iso3_scope=iso3_scope,
        start_year=start_year,
        end_year=end_year,
        vdem=vdem,
        wdi=wdi,
        sipri=sipri,
        maddison=maddison,
        ruler_resolver=ruler_resolver,
        cshapes=cshapes,
        allow_regime_proxy=allow_regime_proxy,
    )

    # Determine which sources contributed. We mark a source as used
    # when the rows contain at least one non-empty value that came
    # from that source (e.g. a V-Dem-derived regime bucket, a WDI
    # population, a SIPRI milex value, a Maddison gdppc, an Archigos
    # leader name, a REIGN leader name, a CShapes area, a SUN
    # curated ruler).
    sources_used = _detect_sources_used(
        rows,
        vdem_has_data=not vdem.frame.empty,
        maddison_has_data=not maddison.frame.empty,
        ruler_resolver=ruler_resolver,
        cshapes_has_data=not cshapes.frame.empty,
    )

    # Write CSV.
    output_path = write_chronicle_csv(
        output_path=output_path,
        rows=rows,
        sources_used=sources_used,
        extra_attribution_lines=(
            f"ISO3 scope: {', '.join(iso3_scope)}",
            f"Year window: {start_year}-{end_year} (inclusive)",
            f"Rows: {len(rows)}",
        ),
    )

    # Optional SQLite artifact. The CSV behavior is preserved
    # when ``sqlite_output_path`` is ``None``. When the caller
    # passes a path explicitly (or when the runner's default is
    # non-None in future invocations), we write the SQLite file
    # alongside the CSV with the same row contents and a
    # ``source_attributions`` sidecar table.
    resolved_sqlite: Path | None = None
    if sqlite_output_path is not None:
        resolved_sqlite = write_chronicle_sqlite(
            output_path=sqlite_output_path,
            rows=rows,
            sources_used=sources_used,
        )

    return ChronicleResult(
        rows_written=len(rows),
        output_path=output_path,
        iso3_scope=iso3_scope,
        start_year=start_year,
        end_year=end_year,
        sources_used=sources_used,
        allow_regime_proxy=allow_regime_proxy,
        sqlite_output_path=resolved_sqlite,
    )


def _detect_sources_used(
    rows: list[dict[str, str]],
    *,
    vdem_has_data: bool,
    maddison_has_data: bool,
    ruler_resolver,
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
    "ChronicleResult",
    "default_archigos_dta_path",
    "default_cshapes_csv_path",
    "default_maddison_xlsx_path",
    "default_output_path",
    "default_reign_csv_path",
    "default_sipri_parquet_path",
    "default_sun_csv_path",
    "default_vdem_csv_path",
    "default_wdi_parquet_path",
    "run_country_year_chronicle",
]
