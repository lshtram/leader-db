"""Research answer persistence CLI command registration."""

from __future__ import annotations

import typer

from ._app import app
from .research_answer_commands import (
    register_answer_commands,
    research_build_country_year_fact_answers_cmd,
    research_list_answers_cmd,
)
from .research_cited_commands import (
    register_cited_commands,
    research_cited_evaluation_schema_cmd,
    research_cited_evaluation_template_cmd,
    research_persist_8b_evaluations_cmd,
    research_persist_cited_evaluations_cmd,
)
from .research_cost_profile_commands import register_cost_profile_commands
from .research_job_commands import jobs_app, register_job_commands
from .research_judgment_review_commands import register_judgment_review_commands
from .research_local_prior_commands import (
    register_local_prior_commands,
    research_build_local_prior_cmd,
    research_build_local_prior_slice_cmd,
    research_local_evidence_cmd,
)
from .research_parallel_commands import (
    register_parallel_commands,
    research_parallel_search_cmd,
)
from .research_readiness_commands import (
    register_readiness_commands,
    research_readiness_cmd,
)
from .research_study_site_commands import register_study_site_commands
from .research_watchdog_commands import (
    register_watchdog_commands,
    research_validate_shard_output_cmd,
)
from .research_worker_commands import register_worker_commands

research_app = typer.Typer(
    help="Persist and inspect research-question answers.",
    no_args_is_help=True,
)
app.add_typer(research_app, name="research")

register_answer_commands(research_app)
register_cited_commands(research_app)
register_cost_profile_commands(research_app)
register_local_prior_commands(research_app)
register_parallel_commands(research_app)
register_watchdog_commands(research_app)
register_readiness_commands(research_app)
register_job_commands(research_app)
register_worker_commands(jobs_app)
register_judgment_review_commands(jobs_app)
register_study_site_commands(research_app)

__all__ = [
    "research_app",
    "research_build_country_year_fact_answers_cmd",
    "research_build_local_prior_cmd",
    "research_build_local_prior_slice_cmd",
    "research_cited_evaluation_schema_cmd",
    "research_cited_evaluation_template_cmd",
    "research_list_answers_cmd",
    "research_local_evidence_cmd",
    "research_parallel_search_cmd",
    "research_persist_8b_evaluations_cmd",
    "research_persist_cited_evaluations_cmd",
    "research_readiness_cmd",
    "research_validate_shard_output_cmd",
]
