"""Stage 0 and Stage 1 stub commands.

Stage 0 (``check-source-availability``) probes every priority source
for download availability and writes a per-source report. Stage 1
(``ingest-client-matrix``) loads the client's existing matrix as the
validation reference dataset. Both are Phase B / Phase C stubs in the
prototype — they print the canonical "not implemented yet" message
and reference the module to implement.

The two commands share this submodule because both are stub-only,
single-line :func:`_not_implemented_yet` calls; pairing them keeps
the file size well under the 400-line convention while the future
Stage 0 / Stage 1 implementations can be split into separate
submodules without changing the command names or import paths.
"""

from __future__ import annotations

from pathlib import Path

import typer

from ..config import default_config_path
from ..ingest.source_availability import check_all_sources, write_source_readiness_report
from ..paths import data_dir
from ._app import app
from ._helpers import _not_implemented_yet, _safe_load_config


@app.command("check-source-availability")
def check_source_availability(
    config: Path = typer.Option(default_config_path(), "--config", "-c"),
    output_dir: Path = typer.Option(data_dir() / "outputs", "--output-dir"),
) -> None:
    """Stage 0: probe every priority source for download availability.

    Writes ``source_availability_report.csv`` and ``.md`` under ``output_dir``.
    """
    cfg = _safe_load_config(config)
    rows = check_all_sources(cfg.project.target_year)
    paths = write_source_readiness_report(
        rows, output_dir, target_year=cfg.project.target_year
    )
    available = sum(row.available for row in rows)
    typer.echo(
        f"[Stage 0] audited {len(rows)} sources for target year "
        f"{cfg.project.target_year}; {available} are researcher-available"
    )
    for path in paths:
        typer.echo(str(path))


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


__all__ = ["check_source_availability", "ingest_client_matrix"]
