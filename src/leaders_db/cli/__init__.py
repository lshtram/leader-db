"""Typer CLI surface — exposes every Stage 0–15 command.

The CLI is the only entry point a human runs; the package functions in the
other modules accept a :class:`leaders_db.config.RunConfig` so the same
production path can be driven by tests or other tooling.

The surface is split across focused submodules (one per pipeline stage)
so no single file carries the full command catalogue. Each submodule
imports :data:`app` from :mod:`leaders_db.cli._app` and registers its
commands via :meth:`app.command` decorators. Importing
:mod:`leaders_db.cli` (this package) triggers registration of every
command, so ``from leaders_db.cli import app`` resolves to the fully-
populated Typer app — preserving the entry-point contract used by
``pyproject.toml`` and by every test that drives the CLI through
``typer.testing.CliRunner``.

During Phase A (infrastructure) most commands are stubs that print a
"not implemented yet" message and reference the stage and module to
implement. They exist so the surface is enumerable in ``leaders-db --help``
and so per-stage implementation can land without touching the CLI.
"""

from __future__ import annotations

from ._app import app, main_callback
from .commands_scoring_category import _run_score_category_all_countries
from .commands_scoring_other import compute_confidence, score_all

# Importing the command submodules triggers their ``@app.command``
# decorators, which register every Stage 0–15 command on :data:`app`.
# Keep the imports grouped by stage so the surface area is obvious.
from .commands_setup import init_data_lake, init_db
from .commands_stage0_1 import check_source_availability, ingest_client_matrix
from .commands_stage2 import ingest_source
from .commands_stage3_5 import (
    extract_indicators,
    match_countries,
    resolve_leaders,
)
from .commands_validation import (
    build_review_queue,
    compare_vs_client,
    summary_report,
)
from .commands_vertical_slice import run_vertical_slice_2023

__all__ = [
    "_run_score_category_all_countries",
    "app",
    "build_review_queue",
    "check_source_availability",
    "compare_vs_client",
    "compute_confidence",
    "extract_indicators",
    "ingest_client_matrix",
    "ingest_source",
    "init_data_lake",
    "init_db",
    "main_callback",
    "match_countries",
    "resolve_leaders",
    "run_vertical_slice_2023",
    "score_all",
    "summary_report",
]
