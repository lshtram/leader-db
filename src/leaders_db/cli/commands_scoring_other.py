"""Stage 9 / Stage 10 / Stage 11 stub commands (other than ``score-category``).

``score-all`` scores every category configured in
``scoring.categories`` for one year. ``compute-confidence`` is the
Stage 11 command that computes per-item confidence using the fixed
``0.35·agreement + 0.25·authority + 0.25·specificity + 0.15·temporal_fit``
formula implemented in :mod:`leaders_db.score.confidence`. Both are
Phase E stubs in the prototype — they print the canonical "not
implemented yet" message and reference the module to implement.

The :func:`score_category` Typer command and its
``--all-countries`` helper live in
:mod:`leaders_db.cli.commands_scoring_category` (the production
seam path). This submodule is the stub-only sibling.
"""

from __future__ import annotations

from pathlib import Path

import typer

from ..config import default_config_path
from ._app import app
from ._helpers import _not_implemented_yet, _safe_load_config


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


__all__ = ["compute_confidence", "score_all"]
