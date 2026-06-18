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
        "system. See `docs/top-level-requirements.md` §8 for the full pipeline."
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
    cfg = _safe_load_config(config)
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
    config: Path = typer.Option(default_config_path(), "--config", "-c"),
) -> None:
    """Stage 2: ingest one external source into ``data/processed/<source>/``.

    The dispatch lives in :data:`leaders_db.ingest.STAGE2_ADAPTERS`. Adding
    a new source is a two-line change: implement the adapter module, then
    add an entry to the table.

    Sources without an entry fall through to the standard "not implemented
    yet" message so the CLI surface stays enumerable in ``--help``.
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

    # Use the config's target year if the user did not pass --year.
    effective_year = year if year is not None else cfg.project.target_year
    typer.echo(f"[Stage 2] ingest source: {source} (year={effective_year})")

    # Adapters accept ``year`` as a kwarg when they support filtering;
    # they all do. Pass it through unconditionally.
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
    cfg = _safe_load_config(config)
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
    cfg = _safe_load_config(config)
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
    cfg = _safe_load_config(config)
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
    config: Path = typer.Option(default_config_path(), "--config", "-c"),
) -> None:
    """Stage 9–10: score one category for one year."""
    cfg = _safe_load_config(config)
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
    cfg = _safe_load_config(config)
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
    cfg = _safe_load_config(config)
    typer.echo(f"[Stage 12] compare vs client for year {year}")
    _not_implemented_yet("validate/comparison.py", "Phase E.")


@app.command("build-review-queue")
def build_review_queue(
    year: int = typer.Option(..., "--year", "-y"),
    config: Path = typer.Option(default_config_path(), "--config", "-c"),
) -> None:
    """Stage 14: build the manual-review queue with §14 priority ordering."""
    cfg = _safe_load_config(config)
    typer.echo(f"[Stage 14] build manual-review queue for year {year}")
    _not_implemented_yet("validate/manual_review_queue.py", "Phase E.")


@app.command("summary-report")
def summary_report(
    year: int = typer.Option(..., "--year", "-y"),
    config: Path = typer.Option(default_config_path(), "--config", "-c"),
) -> None:
    """Stage 15: produce the summary report and validation CSVs."""
    cfg = _safe_load_config(config)
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
    """
    cfg = _safe_load_config(config)
    iso3_scope = tuple(c.strip().upper() for c in countries.split(",") if c.strip())
    category_scope = tuple(c.strip() for c in categories.split(",") if c.strip())

    typer.echo(
        f"[vertical_slice_2023] target_year={cfg.project.target_year} "
        f"countries={iso3_scope} categories={category_scope} "
        f"run_adapters={run_adapters}"
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
    )

    typer.echo("Done. Summary:")
    typer.echo(f"  client_rows_parsed:    {result.client_rows_parsed}")
    typer.echo(f"  countries_seeded:      {result.countries_seeded}")
    typer.echo(f"  observations_linked:   {result.observations_linked}")
    typer.echo(f"  ruler_years_written:   {result.ruler_years_written}")
    typer.echo(f"  score_rows_written:    {result.score_rows_written}")
    typer.echo(f"  validation_rows_written: {result.validation_rows_written}")
    typer.echo(f"  sources_used:          {', '.join(result.sources_used) or '(none)'}")
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


def _not_implemented_yet(module: str, note: str = "") -> None:
    """Consistent 'stub' message for unimplemented stages."""
    msg = f"[stub] {module}: not implemented yet."
    if note:
        msg += f" {note}"
    typer.echo(msg)


if __name__ == "__main__":  # pragma: no cover
    app()
