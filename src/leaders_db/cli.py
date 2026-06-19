"""Typer CLI surface — exposes every Stage 0–15 command.

The CLI is the only entry point a human runs; the package functions in the
other modules accept a :class:`leaders_db.config.RunConfig` so the same
production path can be driven by tests or other tooling.

During Phase A (infrastructure) most commands are stubs that print a
"not implemented yet" message and reference the stage and module to
implement. They exist so the surface is enumerable in ``leaders-db --help``
and so per-stage implementation can land without touching the CLI.
"""

from __future__ import annotations

from pathlib import Path

import typer

from .config import RunConfig, default_config_path, load_config
from .paths import (
    PRIORITY_SOURCES,
    catalog_dir,
    data_dir,
    ensure_data_lake_readme,
    ensure_priority_folders,
)
from .version import __version__

app = typer.Typer(
    name="leaders-db",
    help=(
        "Leaders Database prototype — AI-agent data collection and validation "
        "system. See `docs/req/top-level-requirements.md` §8 for the full pipeline."
    ),
    no_args_is_help=True,
    add_completion=False,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"leaders-db {__version__}")
        raise typer.Exit()


@app.callback()
def main_callback(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Print the package version and exit.",
    ),
) -> None:
    """Global CLI options."""


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------


@app.command("init-data-lake")
def init_data_lake() -> None:
    """Create ``data/`` skeleton folders and the priority source folders."""
    ensure_data_lake_readme()
    created = ensure_priority_folders()
    cwd = Path.cwd()
    if created:
        typer.echo(f"Created {len(created)} folder(s):")
        for p in created:
            try:
                display = p.relative_to(cwd)
            except ValueError:
                display = p
            typer.echo(f"  - {display}")
    else:
        typer.echo("Data lake already initialized.")
    typer.echo(f"Priority sources: {len(PRIORITY_SOURCES)}")


@app.command("init-db")
def init_db(
    config: Path = typer.Option(
        default_config_path(),
        "--config",
        "-c",
        help="Run config YAML. Used to resolve the database URL.",
        exists=False,
    ),
) -> None:
    """Apply the canonical DDL migration to the configured database."""
    cfg = _safe_load_config(config)
    typer.echo(f"Database URL: {cfg.database.url}")
    catalog_dir().mkdir(parents=True, exist_ok=True)
    # Implementation lives in leaders_db.db.engine; see Phase A finish-line
    # task list in docs/workplan.md.
    from .db.engine import init_database  # local import to keep CLI lean

    init_database(cfg.database.url)
    typer.echo("Database initialized.")


# ---------------------------------------------------------------------------
# Stage 0 — source availability
# ---------------------------------------------------------------------------


@app.command("check-source-availability")
def check_source_availability(
    config: Path = typer.Option(default_config_path(), "--config", "-c"),
    output_dir: Path = typer.Option(data_dir() / "outputs", "--output-dir"),
) -> None:
    """Stage 0: probe every priority source for download availability.

    Writes ``source_availability_report.csv`` and ``.md`` under ``output_dir``.
    """
    cfg = _safe_load_config(config)
    typer.echo(
        f"[Stage 0] source availability probe for {len(PRIORITY_SOURCES)} sources "
        f"(target year {cfg.project.target_year})"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    _not_implemented_yet(
        "ingest/source_availability.py",
        "Phase B (source vetting) precedes this — see docs/workplan.md.",
    )


# ---------------------------------------------------------------------------
# Stage 1 — ingest client matrix
# ---------------------------------------------------------------------------


@app.command("ingest-client-matrix")
def ingest_client_matrix(
    year: int = typer.Option(..., "--year", "-y", help="Target year, e.g. 2023"),
    config: Path = typer.Option(default_config_path(), "--config", "-c"),
) -> None:
    """Stage 1: load the client's existing matrix as the reference dataset."""
    _safe_load_config(config)
    typer.echo(f"[Stage 1] ingest client matrix for year {year}")
    _not_implemented_yet(
        "ingest/client_matrix.py",
        "Phase C (data acquisition). Read data/raw/client_existing/metadata.json "
        "first; that bundle was staged during Phase A.",
    )


# ---------------------------------------------------------------------------
# Stage 2 — ingest external sources
# ---------------------------------------------------------------------------


@app.command("ingest-source")
def ingest_source(
    source: str = typer.Option(..., "--source", "-s", help="Source key, e.g. vdem"),
    year: int = typer.Option(
        None, "--year", "-y", help="Filter to a single year (default: all years in the source)"
    ),
    query: list[str] | None = typer.Option(
        None,
        "--query",
        "-q",
        help=(
            "Wikipedia Action API query / topic. Repeat the flag for "
            "multiple queries (e.g. --query 'Joe Biden' --query 'AMLO'). "
            "Required when --source is 'wikipedia_search_extract' "
            "(the adapter does not browse; queries are the deterministic "
            "input contract per AGENTS.md). Ignored for every other source."
        ),
    ),
    config: Path = typer.Option(default_config_path(), "--config", "-c"),
) -> None:
    """Stage 2: ingest one external source into ``data/processed/<source>/``.

    The dispatch lives in :data:`leaders_db.ingest.STAGE2_ADAPTERS`. Adding
    a new source is a two-line change: implement the adapter module, then
    add an entry to the table.

    Sources without an entry fall through to the standard "not implemented
    yet" message so the CLI surface stays enumerable in ``--help``.

    Most adapters accept ``year=`` and ignore it if the source is a
    single-snapshot (FAS) or all-years (WDI). The Wikipedia Action API
    adapter is the exception: its input contract is a list of
    ``queries=`` (the orchestrator never browses). Pass one or more
    ``--query`` values when ``--source wikipedia_search_extract``; if
    none are given, the CLI fails fast with a clear Typer error rather
    than surfacing the opaque ``TypeError`` from passing ``year=`` to a
    queries-only adapter.
    """
    from .ingest import STAGE2_ADAPTERS

    # Validate against the dispatch table's keys, not PRIORITY_SOURCES.
    # PRIORITY_SOURCES is the data-lake folder list (used by
    # ``init-data-lake`` to create ``data/raw/<source>/``); the CLI
    # accepts the *source key* (which may differ from the folder name
    # -- e.g. ``pts`` vs ``political_terror_scale`` for PTS).
    if source not in STAGE2_ADAPTERS:
        raise typer.BadParameter(
            f"unknown source '{source}'. Known: "
            f"{', '.join(sorted(STAGE2_ADAPTERS.keys()))}"
        )
    cfg = _safe_load_config(config)

    adapter = STAGE2_ADAPTERS.get(source)
    if adapter is None:
        typer.echo(f"[Stage 2] ingest source: {source}")
        _not_implemented_yet(
            f"ingest/{source}.py",
            "Phase C. Source must have a vetted_ok / vetted_with_caveats verdict "
            "from Phase B before this is implemented, AND the adapter must be "
            "added to STAGE2_ADAPTERS in leaders_db.ingest.",
        )
        return

    # Wikipedia Action API is the only adapter whose CLI input contract
    # is "explicit queries" (the helper does NOT browse). Fail with a
    # clear, actionable Typer error rather than letting the
    # ``adapter(year=...)`` call surface a TypeError. Other adapters
    # take ``year=`` and ignore unknown kwargs (or accept them silently
    # via **kwargs); this branch keeps them on the unchanged path.
    if source == "wikipedia_search_extract":
        if not query:
            raise typer.BadParameter(
                "--source wikipedia_search_extract requires one or more "
                "--query values (e.g. --query 'Joe Biden'). "
                "The adapter does not browse; queries are the "
                "deterministic input contract."
            )
        typer.echo(
            f"[Stage 2] ingest source: {source} "
            f"(queries={list(query)})"
        )
        result = adapter(queries=list(query))
    else:
        # Use the config's target year if the user did not pass --year.
        effective_year = (
            year if year is not None else cfg.project.target_year
        )
        typer.echo(
            f"[Stage 2] ingest source: {source} (year={effective_year})"
        )
        # Adapters accept ``year`` as a kwarg when they support
        # filtering; they all do. Pass it through unconditionally.
        result = adapter(year=effective_year)

    # Print the adapter's result summary. Adapters return a Pydantic
    # ``IngestResult`` (or equivalent) that carries the attribution
    # (Rule #15) so the CLI surfaces it to the user.
    typer.echo("Done. Summary:")
    for field in (
        "source_id",
        "parquet_path",
        "observation_rows",
        "countries",
        "years",
        "indicators",
    ):
        if hasattr(result, field):
            typer.echo(f"  {field}: {getattr(result, field)}")

    # Rule #15: every public output that touches a source must include
    # the source's attribution. The ``IngestResult`` carries it as a
    # ``.attribution`` property; the CLI surfaces it to the user.
    attribution_text = getattr(result, "attribution", None)
    if attribution_text:
        typer.echo("Attribution:")
        for line in attribution_text.splitlines():
            typer.echo(f"  {line}")


# ---------------------------------------------------------------------------
# Stage 3 — country matching
# ---------------------------------------------------------------------------


@app.command("match-countries")
def match_countries(
    config: Path = typer.Option(default_config_path(), "--config", "-c"),
) -> None:
    """Stage 3: build the country-matching layer (ISO3 primary, alias table)."""
    _safe_load_config(config)
    typer.echo("[Stage 3] match countries")
    _not_implemented_yet("resolve/country_match.py", "Phase E.")


# ---------------------------------------------------------------------------
# Stage 4 — leader resolution
# ---------------------------------------------------------------------------


@app.command("resolve-leaders")
def resolve_leaders(
    year: int = typer.Option(..., "--year", "-y"),
    config: Path = typer.Option(default_config_path(), "--config", "-c"),
) -> None:
    """Stage 4: resolve the actual ruler per country-year for the target year."""
    _safe_load_config(config)
    typer.echo(f"[Stage 4] resolve leaders for year {year}")
    _not_implemented_yet("resolve/leader_resolver.py", "Phase E.")


# ---------------------------------------------------------------------------
# Stage 5 — indicator extraction
# ---------------------------------------------------------------------------


@app.command("extract-indicators")
def extract_indicators(
    year: int = typer.Option(..., "--year", "-y"),
    config: Path = typer.Option(default_config_path(), "--config", "-c"),
) -> None:
    """Stage 5: extract per-category indicator bundles per ruler-year."""
    _safe_load_config(config)
    typer.echo(f"[Stage 5] extract indicators for year {year}")
    _not_implemented_yet("resolve/indicators.py", "Phase E.")


# ---------------------------------------------------------------------------
# Stages 9–11 — scoring + confidence
# ---------------------------------------------------------------------------


@app.command("score-category")
def score_category(
    year: int = typer.Option(..., "--year", "-y"),
    category: str = typer.Option(
        ..., "--category", help="One of: political_freedom, economic_wellbeing, ..."
    ),
    country: str | None = typer.Option(
        None,
        "--country",
        "--country-iso3",
        help=(
            "Optional ISO3 of a single country (e.g. MEX). When supplied "
            "(together with --category social_wellbeing) the command "
            "runs the Stage 9 production seam against the configured "
            "DB and prints a concise score summary. Unsupported "
            "categories fail with a clear error listing the supported "
            "set; omit --country to keep the batch not-implemented "
            "placeholder (Phase E)."
        ),
    ),
    config: Path = typer.Option(default_config_path(), "--config", "-c"),
) -> None:
    """Stage 9–10: score one category for one year.

    With ``--country <ISO3>`` the command runs the **narrow single-
    country read-only Stage 9 seam** (only ``social_wellbeing`` is
    wired as a deterministic scorer today). It opens a session on
    the configured DB, builds the Stage 5 evidence bundle for the
    requested (country, year, category), and prints a concise result
    summary (country/year/category/score or insufficient-data,
    human_review_required, flags, observed/expected counts). No
    ``ruler_scores`` row is persisted in this step — that wiring is
    a follow-on once the Stage 4 leader resolver lands.

    Without ``--country`` the command prints the existing batch
    "not implemented yet" placeholder; full multi-country / multi-
    year scoring is a Phase E item.
    """
    cfg = _safe_load_config(config)

    # Single-country production path. Only the registered categories
    # in ``leaders_db.score.dispatch`` are accepted; unsupported
    # categories fail fast with a typer.BadParameter listing the
    # supported set so the user can pick the right category without
    # reading the package source.
    if country is not None:
        from .db.session import session_scope
        from .score.dispatch import supported_score_categories
        from .score.stage9 import score_category_for_country

        iso3 = country.strip().upper()
        supported = supported_score_categories()
        if category not in supported:
            raise typer.BadParameter(
                f"unsupported category {category!r}. Supported categories: "
                f"[{', '.join(supported)}]."
            )

        typer.echo(
            f"[Stage 9] score category {category!r} for country "
            f"{iso3} year {year}"
        )

        try:
            with session_scope(cfg.database.url) as session:
                result = score_category_for_country(
                    session,
                    country_iso3=iso3,
                    year=year,
                    category_key=category,
                )
        except ValueError as exc:
            # Surface the underlying ``ValueError`` (unknown country /
            # unknown category) as a typer.BadParameter so the user
            # sees a clear error rather than a Python traceback. The
            # dispatcher's error message already lists the supported
            # categories for the unsupported-category case; for the
            # unknown-country case the bundle builder names the
            # missing ISO3.
            raise typer.BadParameter(str(exc)) from exc

        typer.echo(f"  country:           {result.iso3}")
        typer.echo(f"  category:          {result.category_key}")
        typer.echo(f"  year:              {result.year}")
        if result.is_insufficient_data:
            typer.echo("  score:             insufficient_data")
        else:
            assert result.system_proposed_score_1_10 is not None
            assert result.normalized_score_0_1 is not None
            typer.echo(
                f"  score:             {result.system_proposed_score_1_10}/10 "
                f"(normalized={result.normalized_score_0_1:.4f})"
            )
        if result.missingness is not None:
            typer.echo(
                f"  observed/expected: "
                f"{result.missingness.total_observed}/"
                f"{result.missingness.total_expected}"
            )
        typer.echo(f"  human_review:      {result.human_review_required}")
        if result.review_flags:
            flags_str = ", ".join(flag.value for flag in result.review_flags)
            typer.echo(f"  review_flags:      {flags_str}")
        typer.echo(
            f"  observation_refs:  {len(result.observation_refs)}"
        )
        return

    typer.echo(f"[Stage 9] score category {category!r} for year {year}")
    _not_implemented_yet(
        f"score/{category}.py",
        "Phase E. Each category lives in its own module per requirement §9.",
    )


@app.command("score-all")
def score_all(
    year: int = typer.Option(..., "--year", "-y"),
    config: Path = typer.Option(default_config_path(), "--config", "-c"),
) -> None:
    """Score every category configured in ``scoring.categories`` for one year."""
    cfg = _safe_load_config(config)
    typer.echo(
        f"[Stage 9] score all {len(cfg.scoring.categories)} categories for year {year}"
    )
    _not_implemented_yet("score/*", "Phase E.")


@app.command("compute-confidence")
def compute_confidence(
    year: int = typer.Option(..., "--year", "-y"),
    config: Path = typer.Option(default_config_path(), "--config", "-c"),
) -> None:
    """Stage 11: compute per-item confidence using the fixed formula.

    The formula is implemented in :mod:`leaders_db.score.confidence`; this
    command persists results to ``ruler_scores.confidence_score`` and
    ``validation_results``.
    """
    _safe_load_config(config)
    typer.echo(f"[Stage 11] compute confidence for year {year}")
    _not_implemented_yet(
        "score/confidence.py (formula is implemented; stage wiring is Phase E)",
        "The 0.35/0.25/0.25/0.15 formula is in place; wiring the stage run is Phase E.",
    )


# ---------------------------------------------------------------------------
# Stages 12–15 — comparison, manual review, summary
# ---------------------------------------------------------------------------


@app.command("compare-vs-client")
def compare_vs_client(
    year: int = typer.Option(..., "--year", "-y"),
    config: Path = typer.Option(default_config_path(), "--config", "-c"),
) -> None:
    """Stage 12: compare system output against the client matrix."""
    _safe_load_config(config)
    typer.echo(f"[Stage 12] compare vs client for year {year}")
    _not_implemented_yet("validate/comparison.py", "Phase E.")


@app.command("build-review-queue")
def build_review_queue(
    year: int = typer.Option(..., "--year", "-y"),
    config: Path = typer.Option(default_config_path(), "--config", "-c"),
) -> None:
    """Stage 14: build the manual-review queue with §14 priority ordering."""
    _safe_load_config(config)
    typer.echo(f"[Stage 14] build manual-review queue for year {year}")
    _not_implemented_yet("validate/manual_review_queue.py", "Phase E.")


@app.command("summary-report")
def summary_report(
    year: int = typer.Option(..., "--year", "-y"),
    config: Path = typer.Option(default_config_path(), "--config", "-c"),
) -> None:
    """Stage 15: produce the summary report and validation CSVs."""
    _safe_load_config(config)
    typer.echo(f"[Stage 15] summary report for year {year}")
    _not_implemented_yet("validate/summary_report.py", "Phase E.")


# ---------------------------------------------------------------------------
# Vertical slice 2023 (named experimental slice per
# docs/architecture/vertical-slice-2023.md).
# ---------------------------------------------------------------------------


@app.command("run-vertical-slice-2023")
def run_vertical_slice_2023(
    config: Path = typer.Option(default_config_path(), "--config", "-c"),
    countries: str = typer.Option(
        "MEX,NGA,USA",
        "--countries",
        help="Comma-separated ISO3 scope, e.g. MEX,NGA,USA.",
    ),
    categories: str = typer.Option(
        "social_wellbeing,integrity",
        "--categories",
        help="Comma-separated category keys to score.",
    ),
    years: str | None = typer.Option(
        None,
        "--years",
        help=(
            "Optional comma-separated year list for a multi-year "
            "source-only time-series CSV (e.g. 2020,2021,2022,2023). "
            "When set, the orchestrator additionally writes "
            "data/outputs/vertical_slice_2023/vertical_slice_timeseries.csv. "
            "DB writes remain 2023-only regardless."
        ),
    ),
    run_adapters: bool = typer.Option(
        True,
        "--run-adapters/--no-run-adapters",
        help=(
            "When set, the slice runs the UNDP HDI Stage 2 adapter "
            "(and WGI if its xlsx is locally available) before scoring. "
            "When --no-run-adapters is passed, the slice reads "
            "already-staged source_observations rows only."
        ),
    ),
    database_url: str | None = typer.Option(
        None,
        "--database-url",
        help="Override the SQLite URL (otherwise uses RunConfig.database.url).",
    ),
    client_xlsx: Path | None = typer.Option(
        None,
        "--client-xlsx",
        help=(
            "Override the client xlsx path "
            "(otherwise picks the first xlsx under data/raw/client_existing/)."
        ),
    ),
) -> None:
    """Run the 2023 vertical slice end-to-end.

    This is a named experimental slice per
    ``docs/architecture/vertical-slice-2023.md``. It is NOT the real
    Stage 3-15 pipeline — it scores MEX/NGA/USA on
    ``social_wellbeing`` and ``integrity`` with provisional formulas and
    writes the three output files under
    ``data/outputs/vertical_slice_2023/``.

    When ``--years`` is provided, an additional source-only multi-year
    time-series CSV is written. The DB (ruler_years / ruler_scores /
    validation_results) stays 2023-only.
    """
    cfg = _safe_load_config(config)
    iso3_scope = tuple(c.strip().upper() for c in countries.split(",") if c.strip())
    category_scope = tuple(c.strip() for c in categories.split(",") if c.strip())
    years_tuple: tuple[int, ...] = (
        _parse_years_flag(years) if years else ()
    )

    typer.echo(
        f"[vertical_slice_2023] target_year={cfg.project.target_year} "
        f"countries={iso3_scope} categories={category_scope} "
        f"run_adapters={run_adapters} "
        f"years={years_tuple or '(2023-only)'}"
    )

    # Local import keeps the CLI lean — only the slice command pays the
    # parser/import cost.
    from .vertical_slice.slice_2023 import run_vertical_slice_2023 as _run

    result = _run(
        cfg,
        countries=iso3_scope,
        categories=category_scope,
        run_adapters=run_adapters,
        database_url=database_url,
        client_xlsx=client_xlsx,
        years=years_tuple or None,
    )

    typer.echo("Done. Summary:")
    typer.echo(f"  client_rows_parsed:    {result.client_rows_parsed}")
    typer.echo(f"  countries_seeded:      {result.countries_seeded}")
    typer.echo(f"  observations_linked:   {result.observations_linked}")
    typer.echo(f"  ruler_years_written:   {result.ruler_years_written}")
    typer.echo(f"  score_rows_written:    {result.score_rows_written}")
    typer.echo(f"  validation_rows_written: {result.validation_rows_written}")
    typer.echo(f"  sources_used:          {', '.join(result.sources_used) or '(none)'}")
    if result.timeseries_years:
        typer.echo(
            f"  timeseries_years:      {result.timeseries_years} "
            f"(rows={result.timeseries_rows_written})"
        )
        typer.echo(f"  timeseries_csv_path:   {result.timeseries_csv_path}")
    if result.skipped:
        typer.echo("  skipped:")
        for iso3, cat, reason in result.skipped:
            typer.echo(f"    - {iso3} / {cat}: {reason}")
    typer.echo(f"  score_csv_path:    {result.score_csv_path}")
    typer.echo(f"  comparison_csv:    {result.comparison_csv_path}")
    typer.echo(f"  summary_md_path:   {result.summary_md_path}")
    typer.echo(
        "Caveat: this is a provisional, experimental vertical slice — "
        "not the final scoring."
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_load_config(path: Path) -> RunConfig:
    """Load a config, falling back to defaults if the file is missing."""
    if not path.exists():
        typer.echo(
            f"[info] config {path} not found; using RunConfig() defaults. "
            f"Run `cp .env.example .env` and create configs/prototype-2023.yaml "
            f"to override.",
            err=True,
        )
        return RunConfig()
    return load_config(path)


def _parse_years_flag(value: str) -> tuple[int, ...]:
    """Parse a ``--years`` value like ``"2020,2021,2022,2023"``.

    Duplicates are dropped, the order is preserved (the orchestrator
    sorts the tuple for stability), and an empty string after parsing
    is treated as "no years requested" (returns an empty tuple). A
    non-integer component raises :class:`typer.BadParameter` so the
    caller sees a clear, actionable error.
    """
    parts = [chunk.strip() for chunk in value.split(",")]
    parts = [chunk for chunk in parts if chunk]
    parsed: list[int] = []
    seen: set[int] = set()
    for chunk in parts:
        try:
            year = int(chunk)
        except ValueError as exc:
            raise typer.BadParameter(
                f"--years must be a comma-separated list of integers "
                f"(e.g. 2020,2021,2022,2023); got {chunk!r}"
            ) from exc
        if year in seen:
            continue
        seen.add(year)
        parsed.append(year)
    return tuple(parsed)


def _not_implemented_yet(module: str, note: str = "") -> None:
    """Consistent 'stub' message for unimplemented stages."""
    msg = f"[stub] {module}: not implemented yet."
    if note:
        msg += f" {note}"
    typer.echo(msg)


if __name__ == "__main__":  # pragma: no cover
    app()
