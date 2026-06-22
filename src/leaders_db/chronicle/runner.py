"""Runner for the Country-Year Chronicle slice.

The runner is the public Python entry point for the slice. It:

1. Loads the V-Dem, WDI, SIPRI, Maddison, Archigos, REIGN, SUN
   curated, and CShapes sources from the local data lake via
   :mod:`leaders_db.chronicle._source_orchestration`.
2. Builds the per-row data via :func:`build_chronicle_rows`.
3. Writes the CSV via :func:`csv_writer.write_chronicle_csv`.
4. (Increment 5, optional) Writes the condensed CSV via
   :func:`condensed_writer.write_condensed_csv`.

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

Increment 5 added the all-country condensed export. The runner
now accepts an optional ``country_scope`` mapping; when supplied
the per-row identity / flag / area helpers use the scope entry's
``start_year`` / ``end_year`` / ``country_name`` for countries
that are not in the pilot :data:`COUNTRY_METADATA`. The detailed
CSV / SQLite behavior is preserved when the caller does NOT pass
a scope. A condensed CSV (Increment 5 column contract) is written
alongside the detailed CSV whenever ``condensed_output_path`` is
provided (or when the CLI's default opt-in resolves a path).

Module size. The Increment 5 extensions pushed this file over
the documented 440-line carve-out threshold. The source-loading
and sources-used-detection helpers were extracted to
:mod:`._source_orchestration` so the runner stays focused on the
CLI seam + path discovery + output selection.
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from pathlib import Path

from ._source_orchestration import (
    detect_sources_used,
    load_all_sources,
)
from .condensed_writer import write_condensed_csv
from .constants import (
    CHRONICLE_OUTPUT_DIR_NAME,
    COUNTRY_METADATA,
    DEFAULT_COUNTRIES,
    DEFAULT_END_YEAR,
    DEFAULT_OUTPUT_BASENAME,
    DEFAULT_START_YEAR,
)
from .country_scope import CountryScopeEntry
from .csv_writer import write_chronicle_csv
from .row_builder import build_chronicle_rows
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
        condensed_output_path: Optional resolved path to the
            condensed CSV artifact (Increment 5). ``None`` when
            the caller did not pass ``condensed_output_path``
            and the CLI default did not opt in.
        condensed_rows_written: Number of data rows in the
            condensed CSV (equals ``rows_written`` for in-window
            rows; out-of-window rows have only identity columns
            populated, so the condensed file can carry more
            rows than the detailed file when the all-country
            scope is used). ``0`` when no condensed CSV was
            written.
    """

    rows_written: int
    output_path: Path
    iso3_scope: tuple[str, ...]
    start_year: int
    end_year: int
    sources_used: tuple[str, ...]
    allow_regime_proxy: bool
    sqlite_output_path: Path | None = None
    condensed_output_path: Path | None = None
    condensed_rows_written: int = 0

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
            WIKIDATA_RECENT_RULERS_ATTRIBUTION,
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
            elif tag == "wikidata_recent_rulers":
                parts.append(WIKIDATA_RECENT_RULERS_ATTRIBUTION)
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


def default_wdi_cache_dir() -> Path:
    """Return the canonical WDI v2 coverage-cache directory.

    The directory is a snapshot of the WDI v2 API responses saved
    by an out-of-band fetch (one JSON file per indicator +
    window, e.g. ``NY.GDP.MKTP.KD_1960_2024.json``). The Chronicle
    WDI loader reads it as exact country-year observations in
    addition to the processed parquet, lifting recent-year
    coverage from 2022-only to 1960-2024.
    """
    from ..paths import raw_dir

    return raw_dir("world_bank_wdi") / "coverage_cache"


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
    wdi_cache_dir: Path | None = None,
    sipri_parquet_path: Path | None = None,
    maddison_xlsx_path: Path | None = None,
    archigos_dta_path: Path | None = None,
    reign_csv_path: Path | None = None,
    sun_csv_path: Path | None = None,
    cshapes_csv_path: Path | None = None,
    sqlite_output_path: Path | None = None,
    allow_regime_proxy: bool = True,
    country_scope: dict[str, CountryScopeEntry] | None = None,
    condensed_output_path: Path | None = None,
    wikidata_recent_cache_dir: Path | None = None,
    wikidata_recent_force_refresh: bool = False,
    wikidata_recent_timeout: float = 60.0,
    wikidata_recent_disabled: bool = False,
) -> ChronicleResult:
    """Run the Country-Year Chronicle slice end-to-end.

    Parameters
    ----------
    output_path:
        Destination CSV path. The parent directory is created if
        missing.
    iso3_scope:
        ISO3 keys to include. Defaults to the Increment 0 pilot set
        (``USA, GBR, FRA, IND, RUS, SUN, CHN``). The runner validates
        that every key is in either the pilot :data:`COUNTRY_METADATA`
        or the caller-supplied ``country_scope`` so a typo in the CLI
        cannot silently drop a country.
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
    country_scope:
        Optional Increment 5 all-country scope. When provided the
        row builder uses the per-country scope entry's
        ``country_name`` / ``start_year`` / ``end_year`` for
        countries that are not in the pilot
        :data:`COUNTRY_METADATA`. The scope is also used by the
        condensed writer to compute the ``existence_status`` per
        row. When ``None`` (default) the runner falls back to
        the pilot metadata only and skips the condensed CSV (the
        condensed writer needs a scope to compute
        ``existence_status``).
    condensed_output_path:
        Optional condensed CSV artifact path (Increment 5). When
        provided the runner writes a condensed CSV alongside the
        detailed CSV using the ``country_scope`` mapping. The
        default CLI opt-in resolves to
        ``<project_root>/data/outputs/country-year-chronicle/condensed.csv``;
        callers that want to opt out should pass an explicit
        sentinel (today the CLI exposes ``--no-condensed-output``).

    Returns
    -------
    ChronicleResult
        Summary of the run, including the resolved output path and the
        sources that contributed rows with non-empty values. When
        ``sqlite_output_path`` is provided, ``sqlite_output_path``
        on the result carries the resolved path (or ``None`` if
        the SQLite write was skipped). When ``condensed_output_path``
        is provided, ``condensed_output_path`` /
        ``condensed_rows_written`` carry the resolved path /
        row count.
    """
    # Validate scope early: any unknown ISO3 is a hard error so the
    # caller is told immediately instead of silently dropping it.
    # We accept iso3s that are in the pilot COUNTRY_METADATA OR in
    # the caller-supplied country_scope (Increment 5 all-country
    # path). When neither is provided we fall back to the pilot
    # metadata only, which preserves the Increment 1-4 contract.
    accepted_scope: set[str] = set(COUNTRY_METADATA)
    if country_scope is not None:
        accepted_scope |= set(country_scope)
    unknown = [iso3 for iso3 in iso3_scope if iso3 not in accepted_scope]
    if unknown:
        if country_scope is None:
            raise ValueError(
                f"Unknown ISO3 keys (not in COUNTRY_METADATA): {sorted(unknown)}"
            )
        raise ValueError(
            "Unknown ISO3 keys (not in country_scope or COUNTRY_METADATA): "
            f"{sorted(unknown)}"
        )

    # Resolve default paths. We resolve them once so the orchestrator
    # body below can pass named keyword arguments to ``load_all_sources``.
    from ._area_source import default_cshapes_csv_path
    from ._ruler_loader import (
        default_archigos_dta_path,
        default_reign_csv_path,
    )
    from ._sun_ruler_loader import default_sun_csv_path

    resolved_paths = {
        "vdem_csv_path": vdem_csv_path or default_vdem_csv_path(),
        "wdi_parquet_path": wdi_parquet_path or default_wdi_parquet_path(),
        "wdi_cache_dir": wdi_cache_dir or default_wdi_cache_dir(),
        "sipri_parquet_path": sipri_parquet_path or default_sipri_parquet_path(),
        "maddison_xlsx_path": maddison_xlsx_path or default_maddison_xlsx_path(),
        "archigos_dta_path": archigos_dta_path or default_archigos_dta_path(),
        "reign_csv_path": reign_csv_path or default_reign_csv_path(),
        "sun_csv_path": sun_csv_path or default_sun_csv_path(),
        "cshapes_csv_path": cshapes_csv_path or default_cshapes_csv_path(),
    }

    # Compute the Wikidata recent-rulers year window. The fallback
    # fires only for years past REIGN coverage (2022+) so historical
    # years do not trigger an unnecessary SPARQL fetch. Pass an
    # empty tuple when the caller disabled the fallback.
    if wikidata_recent_disabled:
        wikidata_recent_years: tuple[int, ...] = ()
    else:
        from .source_constants import REIGN_COVERAGE_END_YEAR

        wikidata_recent_years = tuple(
            y for y in range(start_year, end_year + 1)
            if y > REIGN_COVERAGE_END_YEAR
        )

    # Load sources.
    loaded = load_all_sources(
        iso3_scope=iso3_scope,
        wikidata_recent_years=wikidata_recent_years,
        wikidata_recent_cache_dir=wikidata_recent_cache_dir,
        wikidata_recent_force_refresh=wikidata_recent_force_refresh,
        wikidata_recent_timeout=wikidata_recent_timeout,
        **resolved_paths,
    )

    # Build rows.
    rows = build_chronicle_rows(
        iso3_scope=iso3_scope,
        start_year=start_year,
        end_year=end_year,
        vdem=loaded.vdem,
        wdi=loaded.wdi,
        sipri=loaded.sipri,
        maddison=loaded.maddison,
        ruler_resolver=loaded.ruler_resolver,
        cshapes=loaded.cshapes,
        allow_regime_proxy=allow_regime_proxy,
        country_scope=country_scope,
    )

    # Determine which sources contributed. We mark a source as used
    # when the rows contain at least one non-empty value that came
    # from that source (e.g. a V-Dem-derived regime bucket, a WDI
    # population, a SIPRI milex value, a Maddison gdppc, an Archigos
    # leader name, a REIGN leader name, a CShapes area, a SUN
    # curated ruler).
    sources_used = detect_sources_used(
        rows,
        vdem_has_data=not loaded.vdem.frame.empty,
        maddison_has_data=not loaded.maddison.frame.empty,
        ruler_resolver=loaded.ruler_resolver,
        cshapes_has_data=loaded.cshapes is not None and not loaded.cshapes.frame.empty,
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

    # Optional condensed CSV (Increment 5). The runner skips the
    # condensed write when the caller did not supply a path AND
    # did not supply a country scope; both are required for the
    # condensed writer to produce sensible output.
    resolved_condensed: Path | None = None
    condensed_rows_written = 0
    if condensed_output_path is not None:
        if country_scope is None:
            raise ValueError(
                "condensed_output_path was provided but country_scope is "
                "None; the condensed writer needs a scope to compute "
                "existence_status. Pass country_scope=... or omit "
                "condensed_output_path."
            )
        resolved_condensed = write_condensed_csv(
            output_path=condensed_output_path,
            detailed_rows=rows,
            country_scope=country_scope,
        )
        # Re-read the condensed file to report the row count.
        with resolved_condensed.open(newline="", encoding="utf-8") as _fh:
            _reader = csv.DictReader(_fh)
            condensed_rows_written = sum(1 for _ in _reader)

    return ChronicleResult(
        rows_written=len(rows),
        output_path=output_path,
        iso3_scope=iso3_scope,
        start_year=start_year,
        end_year=end_year,
        sources_used=sources_used,
        allow_regime_proxy=allow_regime_proxy,
        sqlite_output_path=resolved_sqlite,
        condensed_output_path=resolved_condensed,
        condensed_rows_written=condensed_rows_written,
    )


__all__ = [
    "ChronicleResult",
    "default_maddison_xlsx_path",
    "default_output_path",
    "default_sipri_parquet_path",
    "default_vdem_csv_path",
    "default_wdi_parquet_path",
    "run_country_year_chronicle",
]
