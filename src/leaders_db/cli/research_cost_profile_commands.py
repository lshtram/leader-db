"""CLI commands for deterministic research cost profiling."""

from __future__ import annotations

from pathlib import Path

import typer

from leaders_db.research.cost_profile import build_cost_profile, compare_cost_profiles

cost_profile_app = typer.Typer(help="Profile and compare trusted research model usage.")


def register_cost_profile_commands(research_app: typer.Typer) -> None:
    """Register the isolated cost-profile command group."""

    research_app.add_typer(cost_profile_app, name="cost-profile")


@cost_profile_app.command("build")
def build_cmd(
    run_root: Path = typer.Argument(..., exists=True, file_okay=False),
    output_dir: Path = typer.Option(..., "--output-dir"),
    rules: Path = typer.Option(
        Path("configs/research-cost-profile-stages.yaml"), "--rules", exists=True
    ),
) -> None:
    """Build a canonical profile from one immutable ruler run."""

    typer.echo(build_cost_profile(run_root, output_dir, rules))


@cost_profile_app.command("compare")
def compare_cmd(
    baseline: Path = typer.Argument(..., exists=True, dir_okay=False),
    candidate: Path = typer.Argument(..., exists=True, dir_okay=False),
    output: Path = typer.Option(..., "--output"),
) -> None:
    """Compare two canonical profiles using identical definitions."""

    typer.echo(compare_cost_profiles(baseline, candidate, output))


__all__ = ["register_cost_profile_commands"]
