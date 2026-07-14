"""Research execution readiness CLI commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

import typer

from .research_common import fail

ReadinessModeOption = Literal["dossier_researcher", "chapter_judge"]


def register_readiness_commands(research_app: typer.Typer) -> None:
    research_app.command("readiness")(research_readiness_cmd)


def research_readiness_cmd(
    mode: ReadinessModeOption = typer.Option(..., "--mode"),
    year: int = typer.Option(..., "--year"),
    methodology_ids: list[str] | None = typer.Option(None, "--question-id"),
    chapter_id: str | None = typer.Option(None, "--chapter-id"),
    provider_profile: str = typer.Option(..., "--provider-profile"),
    reviewer_profile: str | None = typer.Option(None, "--reviewer-profile"),
    formatter_profile: str | None = typer.Option(None, "--formatter-profile"),
    output_dir: Path = typer.Option(..., "--output-dir"),
    db_url: str | None = typer.Option(None, "--db-url"),
    model_profiles_path: Path | None = typer.Option(
        None,
        "--model-profiles",
        exists=True,
        dir_okay=False,
        readable=True,
    ),
    research_workflow_path: Path | None = typer.Option(
        None,
        "--research-workflow",
        exists=True,
        dir_okay=False,
        readable=True,
    ),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Check whether a ruler-dossier or chapter-judge run is safe to launch."""

    from ..db.engine import build_engine
    from ..db.session import default_sqlite_url
    from ..paths import project_root
    from ..research.readiness import build_research_readiness_report

    selected_ids = tuple(
        dict.fromkeys(methodology_id.strip() for methodology_id in methodology_ids or ())
    )
    if mode == "chapter_judge":
        normalized_chapter = (chapter_id or "").strip().upper()
        if normalized_chapter not in {f"{index}B" for index in range(1, 9)}:
            fail(
                "chapter_judge readiness requires one --chapter-id from 1B to 8B",
                output_json=output_json,
            )
        if selected_ids:
            fail(
                "chapter_judge readiness derives its ten lenses; omit --question-id",
                output_json=output_json,
            )
        selected_ids = tuple(f"{normalized_chapter}.{index}" for index in range(1, 11))
    try:
        report = build_research_readiness_report(
            build_engine(db_url or default_sqlite_url()),
            project_root=project_root(),
            mode=mode,
            year=year,
            methodology_ids=selected_ids,
            provider_profile=provider_profile,
            reviewer_profile=reviewer_profile,
            formatter_profile=formatter_profile,
            output_dir=output_dir,
            model_profiles_path=model_profiles_path,
            research_workflow_path=research_workflow_path,
        )
    except (OSError, ValueError) as exc:
        fail(str(exc), output_json=output_json)

    payload = report.model_dump(mode="json")
    if output_json:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
    else:
        typer.echo(
            f"research_readiness: {'ready' if report.ready else 'blocked'}; "
            f"mode: {report.mode}; provider: {report.provider}; model: {report.model}; "
            f"eligible_rulers: {report.eligible_ruler_count}; "
            f"quarantined_rulers: {report.quarantined_ruler_count}"
        )
        for check in report.checks:
            typer.echo(f"[{check.status}] {check.check_id}: {check.message}")
    if not report.ready:
        raise typer.Exit(1)


__all__ = ["register_readiness_commands", "research_readiness_cmd"]
