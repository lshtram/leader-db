"""CLI wiring for independent chapter-judgment review."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from .research_common import fail


def register_judgment_review_commands(jobs_app: typer.Typer) -> None:
    """Register the bounded Sol judgment-review command."""

    jobs_app.command("review-chapter-judgments")(review_chapter_judgments_cmd)


def review_chapter_judgments_cmd(
    judgment_paths: list[Path] = typer.Option(..., "--judgment"),
    output_dir: Path = typer.Option(..., "--output-dir"),
    provider_profile: str = typer.Option(
        "openai-sol-supervisor", "--provider-profile"
    ),
    timeout_seconds: int = typer.Option(10_800, "--timeout-seconds", min=1),
    model_profiles_path: Path | None = typer.Option(None, "--model-profiles"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Review completed chapter scores with high-reasoning Sol and bounded edits."""

    from ..paths import project_root
    from ..research.chapter_judgment_review_runner import review_chapter_judgments

    project = project_root()
    try:
        result = review_chapter_judgments(
            project_root=project,
            judgment_paths=tuple(judgment_paths),
            output_dir=output_dir,
            profile_name=provider_profile,
            profiles_path=(
                model_profiles_path or project / "configs/research-models.yaml"
            ),
            timeout_seconds=timeout_seconds,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        fail(str(exc), output_json=output_json)
    typer.echo(
        json.dumps({"review_manifest": str(result)}, indent=2 if output_json else None)
    )


__all__ = ["register_judgment_review_commands", "review_chapter_judgments_cmd"]
