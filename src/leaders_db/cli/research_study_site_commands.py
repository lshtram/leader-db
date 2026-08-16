"""CLI commands for the public ruler-study microsite."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import typer

from ..research.study_site_render import build_study_site


def register_study_site_commands(research_app: typer.Typer) -> None:
    research_app.command("build-study-site")(research_build_study_site_cmd)
    research_app.command("check-study-site")(research_check_study_site_cmd)


def research_build_study_site_cmd(
    run_dir: Path = typer.Option(..., exists=True, file_okay=False),
    output_dir: Path = typer.Option(..., file_okay=False),
) -> None:
    """Build a validated public static site from one approved production run."""

    project_root = Path.cwd().resolve()
    manifest = build_study_site(
        project_root=project_root,
        run_dir=run_dir.resolve(),
        output_dir=output_dir.resolve(),
    )
    typer.echo(manifest)


def research_check_study_site_cmd(
    site_dir: Path = typer.Option(..., exists=True, file_okay=False),
) -> None:
    """Verify every file recorded in a generated site manifest."""

    manifest_path = site_dir / "study-site-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    root = site_dir.resolve()
    recorded: set[str] = set()
    for item in manifest["files"]:
        relative = str(item["path"])
        if relative in recorded:
            raise typer.BadParameter(f"duplicate generated file: {relative}")
        recorded.add(relative)
        path = (root / relative).resolve()
        if not path.is_relative_to(root):
            raise typer.BadParameter(f"generated file escapes site directory: {relative}")
        if not path.is_file():
            raise typer.BadParameter(f"missing generated file: {relative}")
        if path.stat().st_size != item["bytes"]:
            raise typer.BadParameter(f"generated file size mismatch: {relative}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != item["sha256"]:
            raise typer.BadParameter(f"generated file hash mismatch: {relative}")
    typer.echo(f"validated {len(manifest['files'])} generated files")


__all__ = ["register_study_site_commands"]
