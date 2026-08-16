"""Research CLI commands for acquiring, reading, and packaging a corpus."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from .research_common import fail


def acquire_catalog_cmd(
    catalogue: Path = typer.Option(..., "--catalogue"),
    output_dir: Path = typer.Option(..., "--output-dir"),
    workers: int = typer.Option(8, "--workers", min=1, max=32),
    timeout_seconds: float = typer.Option(25, "--timeout-seconds", min=2),
    max_source_bytes: int = typer.Option(30_000_000, "--max-source-bytes", min=100_000),
    max_transient_attempts: int = typer.Option(3, "--max-transient-attempts", min=1, max=5),
    respect_robots_txt: bool = typer.Option(True, "--respect-robots-txt/--ignore-robots-txt"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Acquire or explicitly disposition every candidate in a source catalogue."""

    from ..research.catalog_acquisition import CatalogAcquisitionConfig, acquire_catalogue

    try:
        manifest = acquire_catalogue(
            catalogue,
            output_dir,
            config=CatalogAcquisitionConfig(
                workers=workers,
                timeout_seconds=timeout_seconds,
                max_source_bytes=max_source_bytes,
                max_transient_attempts=max_transient_attempts,
                respect_robots_txt=respect_robots_txt,
            ),
        )
    except (OSError, ValueError) as exc:
        fail(str(exc), output_json=output_json)
    _emit({"manifest": str(manifest)}, output_json=output_json)


def plan_corpus_reading_cmd(
    catalogue: Path = typer.Option(..., "--catalogue"),
    acquisition_manifest: Path = typer.Option(..., "--acquisition-manifest"),
    output: Path = typer.Option(..., "--output"),
    ruler_name: str = typer.Option(..., "--ruler-name"),
    period_start_year: int = typer.Option(..., "--period-start-year"),
    period_end_year: int = typer.Option(..., "--period-end-year"),
    target_batch_tokens: int = typer.Option(220_000, "--target-batch-tokens"),
    maximum_batch_tokens: int = typer.Option(280_000, "--maximum-batch-tokens"),
    maximum_documents_per_batch: int = typer.Option(12, "--maximum-documents-per-batch"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Deduplicate acquired content and queue every representative for reading."""

    from ..research.corpus_reading_plan import ReadingPlanConfig, build_corpus_reading_plan

    path = build_corpus_reading_plan(
        catalogue,
        acquisition_manifest,
        output,
        ruler_name=ruler_name,
        period_start_year=period_start_year,
        period_end_year=period_end_year,
        config=ReadingPlanConfig(
            target_batch_tokens=target_batch_tokens,
            maximum_batch_tokens=maximum_batch_tokens,
            maximum_documents_per_batch=maximum_documents_per_batch,
        ),
    )
    _emit({"reading_plan": str(path)}, output_json=output_json)


def repair_corpus_reading_plan_cmd(
    plan: Path = typer.Option(..., "--plan"),
    acquisition_dir: Path = typer.Option(..., "--acquisition-dir"),
    batch_ids: list[str] = typer.Option(..., "--batch-id"),
    output: Path = typer.Option(..., "--output"),
    maximum_document_characters: int = typer.Option(
        850_000, "--maximum-document-characters", min=50_000
    ),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Split only transport-oversized reading batches."""

    from ..research.corpus_reading_plan import build_transport_repair_plan

    path = build_transport_repair_plan(
        plan,
        acquisition_dir,
        output,
        batch_ids=tuple(batch_ids),
        maximum_document_characters=maximum_document_characters,
    )
    _emit({"repair_plan": str(path)}, output_json=output_json)


def run_corpus_reading_cmd(
    acquisition_dir: Path = typer.Option(..., "--acquisition-dir"),
    plan: Path = typer.Option(..., "--plan"),
    output_dir: Path = typer.Option(..., "--output-dir"),
    provider_profile: str = typer.Option("openai-luna-candidate", "--provider-profile"),
    parallel_batches: int = typer.Option(3, "--parallel-batches", min=1, max=8),
    model_profiles_path: Path | None = typer.Option(None, "--model-profiles"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Read, code-bind, and freshly verify all queued corpus batches."""

    from ..paths import project_root
    from ..research.corpus_reader_runner import run_corpus_reading

    project = project_root()
    path = run_corpus_reading(
        project_root=project,
        acquisition_dir=acquisition_dir,
        plan_path=plan,
        output_dir=output_dir,
        profile_name=provider_profile,
        profiles_path=model_profiles_path or project / "configs/research-models.yaml",
        parallel_batches=parallel_batches,
    )
    _emit({"reading_manifest": str(path)}, output_json=output_json)


def build_corpus_judge_package_cmd(
    reading_dir: Path = typer.Option(..., "--reading-dir"),
    output: Path = typer.Option(..., "--output"),
    mapping_review: Path | None = typer.Option(None, "--mapping-review"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Build the verified, clustered, question-indexed judge evidence package."""

    from ..research.corpus_judge_package import build_corpus_judge_package

    path = build_corpus_judge_package(reading_dir, output, mapping_review_path=mapping_review)
    _emit({"judge_package": str(path)}, output_json=output_json)


def build_approved_ruler_package_cmd(
    dossier: Path = typer.Option(..., "--dossier"),
    corpus_package: Path = typer.Option(..., "--corpus-package"),
    reading_plan: Path = typer.Option(..., "--reading-plan"),
    reading_manifest: Path = typer.Option(..., "--reading-manifest"),
    selection_manifest: Path = typer.Option(..., "--selection-manifest"),
    production_run: Path = typer.Option(..., "--production-run", exists=True, dir_okay=False),
    output: Path = typer.Option(..., "--output"),
    output_json: bool = typer.Option(False, "--json"),
) -> None:
    """Bind a complete, independently reviewed ruler package for judging."""

    from ..paths import project_root
    from ..research.approved_ruler_package import build_approved_ruler_package

    path = build_approved_ruler_package(
        project_root=project_root(),
        dossier_path=dossier,
        corpus_package_path=corpus_package,
        reading_plan_path=reading_plan,
        reading_manifest_path=reading_manifest,
        selection_manifest_path=selection_manifest,
        production_run_manifest_path=production_run,
        output_path=output,
    )
    _emit({"approved_ruler_package": str(path)}, output_json=output_json)


def _emit(payload: dict[str, object], *, output_json: bool) -> None:
    typer.echo(json.dumps(payload, indent=2 if output_json else None, sort_keys=True, default=str))
