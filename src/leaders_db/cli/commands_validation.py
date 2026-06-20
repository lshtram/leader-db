"""Stage 12 / Stage 14 / Stage 15 stub commands.

Stage 12 (``compare-vs-client``) compares system output against the
client matrix. Stage 14 (``build-review-queue``) builds the
manual-review queue with §14 priority ordering. Stage 15
(``summary-report``) produces the summary report and validation
CSVs. All three are Phase E stubs in the prototype — they print
the canonical "not implemented yet" message and reference the
module to implement.

The three commands share this submodule because all three are
stub-only, single-line :func:`_not_implemented_yet` calls; pairing
them keeps the file size well under the 400-line convention while
the future Stage 12 / 14 / 15 implementations can be split into
separate submodules without changing the command names or import
paths.
"""

from __future__ import annotations

from pathlib import Path

import typer

from ..config import default_config_path
from ._app import app
from ._helpers import _not_implemented_yet, _safe_load_config


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


__all__ = ["build_review_queue", "compare_vs_client", "summary_report"]
