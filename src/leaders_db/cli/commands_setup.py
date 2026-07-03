"""Setup commands — ``init-data-lake`` and ``init-db``.

Both commands are the Phase A finish-line hooks: the data-lake
scaffolding (folder creation + priority source folders) and the
DDL migration apply. They live in their own submodule so the
two commands can be audited side-by-side without the rest of the
CLI surface around them.
"""

from __future__ import annotations

from pathlib import Path

import typer

from ..config import RunConfig, default_config_path
from ..paths import (
    PRIORITY_SOURCES,
    catalog_dir,
    ensure_data_lake_readme,
    ensure_priority_folders,
)
from ._app import app
from ._helpers import _safe_load_config


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
    """Apply all checked-in migrations to the configured database."""
    cfg = _safe_load_config(config)
    catalog_dir().mkdir(parents=True, exist_ok=True)
    # Implementation lives in leaders_db.db.engine; see Phase A finish-line
    # task list in docs/workplan.md.
    from ..db.engine import init_database  # local import to keep CLI lean
    from ..db.session import default_sqlite_url

    db_url = (
        default_sqlite_url()
        if cfg.database.url == RunConfig().database.url
        else cfg.database.url
    )

    typer.echo(f"Database URL: {db_url}")
    init_database(db_url)
    typer.echo("Database initialized.")


__all__ = ["init_data_lake", "init_db"]
