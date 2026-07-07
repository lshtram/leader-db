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
from .commands_chronicle import run_country_year_chronicle_cmd
from .commands_evidence import evidence_app, evidence_summarize_ruler_period_cmd
from .commands_facts import facts_app, facts_publish_concepts_cmd
from .commands_identity import (
    identity_adjudication_coverage_cmd,
    identity_app,
    identity_build_adjudications_cmd,
    identity_build_ruler_years_cmd,
    identity_ruler_coverage_cmd,
)
from .commands_research import (
    research_app,
    research_build_country_year_fact_answers_cmd,
    research_build_local_prior_cmd,
    research_build_local_prior_slice_cmd,
    research_list_answers_cmd,
    research_persist_8b_evaluations_cmd,
)
from .commands_scope import (
    scope_app,
    scope_build_country_years_cmd,
    scope_country_year_coverage_cmd,
)
from .commands_scoring_category import _run_score_category_all_countries
from .commands_scoring_other import compute_confidence, score_all

# Importing the command submodules triggers their ``@app.command``
# decorators, which register every Stage 0–15 command on :data:`app`.
# Keep the imports grouped by stage so the surface area is obvious.
from .commands_setup import init_data_lake, init_db
from .commands_sources import (
    sources_app,
    sources_check_ready_cmd,
    sources_describe_cmd,
    sources_ingest_cmd,
    sources_list_cmd,
    sources_query_cmd,
)
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
from .commands_viz import (
    viz_build_growth_tables_cmd,
    viz_build_superset_db_cmd,
    viz_metrics_cmd,
    viz_query_cmd,
    viz_run_investigation_slice_cmd,
)

__all__ = [
    "_run_score_category_all_countries",
    "app",
    "build_review_queue",
    "check_source_availability",
    "compare_vs_client",
    "compute_confidence",
    "evidence_app",
    "evidence_summarize_ruler_period_cmd",
    "extract_indicators",
    "facts_app",
    "facts_publish_concepts_cmd",
    "identity_adjudication_coverage_cmd",
    "identity_app",
    "identity_build_adjudications_cmd",
    "identity_build_ruler_years_cmd",
    "identity_ruler_coverage_cmd",
    "ingest_client_matrix",
    "ingest_source",
    "init_data_lake",
    "init_db",
    "main_callback",
    "match_countries",
    "research_app",
    "research_build_country_year_fact_answers_cmd",
    "research_build_local_prior_cmd",
    "research_build_local_prior_slice_cmd",
    "research_list_answers_cmd",
    "research_persist_8b_evaluations_cmd",
    "resolve_leaders",
    "run_country_year_chronicle_cmd",
    "run_vertical_slice_2023",
    "scope_app",
    "scope_build_country_years_cmd",
    "scope_country_year_coverage_cmd",
    "score_all",
    "sources_app",
    "sources_check_ready_cmd",
    "sources_describe_cmd",
    "sources_ingest_cmd",
    "sources_list_cmd",
    "sources_query_cmd",
    "summary_report",
    "viz_build_growth_tables_cmd",
    "viz_build_superset_db_cmd",
    "viz_metrics_cmd",
    "viz_query_cmd",
    "viz_run_investigation_slice_cmd",
]
