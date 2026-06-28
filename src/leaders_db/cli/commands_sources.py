"""Clean source-registry inspection CLI commands."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import cast

import typer

from ..sources import (
    CachePolicy,
    OutputFormat,
    SourceDescriptor,
    SourceId,
    SourceIngestRequest,
    SourceIngestResult,
    SourceIngestRunner,
    SourceWarning,
    build_default_source_registry,
)
from ._app import app

sources_app = typer.Typer(help="Inspect clean source adapters.", no_args_is_help=True)
app.add_typer(sources_app, name="sources")


@sources_app.command("list")
def sources_list_cmd(
    output: str = typer.Option(
        "table",
        "--output",
        "-o",
        help="Output format: table or json.",
    ),
) -> None:
    """List source IDs registered in the clean source registry."""
    registry = build_default_source_registry()
    descriptors = registry.list_descriptors()

    if output == "json":
        payload = [_descriptor_payload(descriptor) for descriptor in descriptors]
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    if output != "table":
        raise typer.BadParameter("--output must be 'table' or 'json'")

    for descriptor in descriptors:
        typer.echo(
            f"{descriptor.source_id.slug}\t"
            f"{descriptor.display_name}\t"
            f"{descriptor.source_type}\t"
            f"{descriptor.default_version or '-'}\t"
            f"{', '.join(descriptor.supported_observation_families)}"
        )


@sources_app.command("describe")
def sources_describe_cmd(
    source: str = typer.Argument(..., help="Clean source ID to describe."),
    output: str = typer.Option(
        "table",
        "--output",
        "-o",
        help="Output format: table or json.",
    ),
) -> None:
    """Describe one source from the clean source registry."""
    registry = build_default_source_registry()
    try:
        descriptor = registry.get_descriptor(SourceId(slug=source))
    except KeyError as exc:
        raise typer.BadParameter(
            f"unknown source {source!r}; run `leaders-db sources list` for valid IDs"
        ) from exc

    if output == "json":
        typer.echo(json.dumps(_descriptor_payload(descriptor), indent=2, sort_keys=True))
        return
    if output != "table":
        raise typer.BadParameter("--output must be 'table' or 'json'")

    payload = _descriptor_payload(descriptor)
    typer.echo(f"source_id: {payload['source_id']}")
    typer.echo(f"display_name: {payload['display_name']}")
    typer.echo(f"source_type: {payload['source_type']}")
    typer.echo(f"default_version: {payload['default_version'] or '-'}")
    typer.echo(f"homepage_url: {payload['homepage_url'] or '-'}")
    typer.echo(f"attribution_key: {payload['attribution_key']}")
    typer.echo(f"families: {', '.join(payload['supported_observation_families'])}")
    typer.echo(f"coverage: {json.dumps(payload['coverage_hint'], sort_keys=True)}")
    typer.echo(f"requires_manual_approval: {payload['requires_manual_approval']}")
    typer.echo(f"requires_network: {payload['requires_network']}")


@sources_app.command("check-ready")
def sources_check_ready_cmd(
    source: str = typer.Argument(..., help="Clean source ID to check."),
    years: list[int] | None = typer.Option(
        None,
        "--year",
        help="Restrict readiness check to a year. May be passed multiple times.",
    ),
    countries: list[str] | None = typer.Option(
        None,
        "--country",
        help="Restrict readiness check to an ISO country code. May be passed multiple times.",
    ),
    leaders: list[str] | None = typer.Option(
        None,
        "--leader",
        help="Restrict readiness check to a leader ID. May be passed multiple times.",
    ),
    raw_root: Path = typer.Option(Path("data/raw"), "--raw-root"),
    processed_root: Path = typer.Option(Path("data/processed"), "--processed-root"),
    metadata_root: Path = typer.Option(Path("data/metadata"), "--metadata-root"),
    cache_policy: str = typer.Option(
        "prefer_cache",
        "--cache-policy",
        help="Cache policy: offline_only, prefer_cache, refresh, or no_cache.",
    ),
    output: str = typer.Option(
        "table",
        "--output",
        "-o",
        help="Output format: table or json.",
    ),
) -> None:
    """Check whether one clean source adapter is ready to run."""
    if output not in {"table", "json"}:
        raise typer.BadParameter("--output must be 'table' or 'json'")
    if cache_policy not in {"offline_only", "prefer_cache", "refresh", "no_cache"}:
        raise typer.BadParameter(
            "--cache-policy must be one of: offline_only, prefer_cache, refresh, no_cache"
        )

    registry = build_default_source_registry()
    source_id = SourceId(slug=source)
    try:
        adapter = SourceIngestRunner(registry).registry.get_adapter(source_id)
    except KeyError as exc:
        raise typer.BadParameter(
            f"unknown source {source!r}; run `leaders-db sources list` for valid IDs"
        ) from exc

    request = SourceIngestRequest(
        source_id=source_id,
        years=tuple(years) if years else None,
        countries=tuple(countries) if countries else None,
        leaders=tuple(leaders) if leaders else None,
        raw_root=raw_root,
        processed_root=processed_root,
        metadata_root=metadata_root,
        cache_policy=cast(CachePolicy, cache_policy),
        dry_run=True,
    )
    readiness = adapter.check_ready(request)

    if output == "json":
        typer.echo(
            json.dumps(
                {
                    "source_id": source,
                    "ready": readiness.ready,
                    "warnings": [_warning_payload(warning) for warning in readiness.warnings],
                    "errors": [_warning_payload(error) for error in readiness.errors],
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        typer.echo(f"source_id: {source}")
        typer.echo(f"ready: {readiness.ready}")
        _echo_findings("warning", readiness.warnings)
        _echo_findings("error", readiness.errors)

    if not readiness.ready:
        raise typer.Exit(1)


@sources_app.command("ingest")
def sources_ingest_cmd(
    source: str = typer.Argument(..., help="Clean source ID to ingest."),
    years: list[int] | None = typer.Option(
        None,
        "--year",
        help="Restrict ingest to a year. May be passed multiple times.",
    ),
    countries: list[str] | None = typer.Option(
        None,
        "--country",
        help="Restrict ingest to an ISO country code. May be passed multiple times.",
    ),
    leaders: list[str] | None = typer.Option(
        None,
        "--leader",
        help="Restrict ingest to a leader ID. May be passed multiple times.",
    ),
    raw_root: Path = typer.Option(Path("data/raw"), "--raw-root"),
    processed_root: Path = typer.Option(Path("data/processed"), "--processed-root"),
    metadata_root: Path = typer.Option(Path("data/metadata"), "--metadata-root"),
    cache_policy: str = typer.Option(
        "prefer_cache",
        "--cache-policy",
        help="Cache policy: offline_only, prefer_cache, refresh, or no_cache.",
    ),
    overwrite: bool = typer.Option(False, "--overwrite", help="Allow overwriting outputs."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Run without mutating outputs."),
    output_formats: list[str] | None = typer.Option(
        None,
        "--output-format",
        help="Processed output format: parquet or csv. May be passed multiple times.",
    ),
    output: str = typer.Option(
        "table",
        "--output",
        "-o",
        help="Output format: table or json.",
    ),
) -> None:
    """Ingest one clean source through the shared source runner lifecycle."""
    if output not in {"table", "json"}:
        raise typer.BadParameter("--output must be 'table' or 'json'")
    if cache_policy not in {"offline_only", "prefer_cache", "refresh", "no_cache"}:
        raise typer.BadParameter(
            "--cache-policy must be one of: offline_only, prefer_cache, refresh, no_cache"
        )
    formats = tuple(output_formats) if output_formats else ("parquet",)
    unsupported_formats = sorted(set(formats) - {"parquet", "csv"})
    if unsupported_formats:
        raise typer.BadParameter("--output-format must be 'parquet' or 'csv'")

    registry = build_default_source_registry()
    source_id = SourceId(slug=source)
    request = SourceIngestRequest(
        source_id=source_id,
        years=tuple(years) if years else None,
        countries=tuple(countries) if countries else None,
        leaders=tuple(leaders) if leaders else None,
        raw_root=raw_root,
        processed_root=processed_root,
        metadata_root=metadata_root,
        dry_run=dry_run,
        overwrite=overwrite,
        cache_policy=cast(CachePolicy, cache_policy),
        output_formats=cast(tuple[OutputFormat, ...], formats),
    )

    try:
        result = SourceIngestRunner(registry).run(request)
    except KeyError as exc:
        raise typer.BadParameter(
            f"unknown source {source!r}; run `leaders-db sources list` for valid IDs"
        ) from exc
    except RuntimeError as exc:
        _echo_ingest_failure(source, str(exc), output=output)
        raise typer.Exit(1) from exc

    if output == "json":
        typer.echo(json.dumps(_ingest_result_payload(result), indent=2, sort_keys=True))
        return

    payload = _ingest_result_payload(result)
    typer.echo(f"source_id: {payload['source_id']}")
    typer.echo(f"ready: {payload['ready']}")
    typer.echo(f"validation_valid: {payload['validation_valid']}")
    typer.echo(f"observation_count: {payload['observation_count']}")
    typer.echo(f"manifest_run_id: {payload['manifest_run_id'] or '-'}")
    typer.echo(f"manifest_idempotency_key: {payload['manifest_idempotency_key'] or '-'}")
    _echo_findings("warning", result.warnings)
    _echo_findings("validation_error", result.validation.errors)

    if not result.validation.valid:
        raise typer.Exit(1)


def _descriptor_payload(descriptor: SourceDescriptor) -> dict[str, object]:
    """Return a JSON-friendly descriptor payload for CLI output."""
    return {
        "source_id": descriptor.source_id.slug,
        "display_name": descriptor.display_name,
        "source_type": descriptor.source_type,
        "supported_observation_families": descriptor.supported_observation_families,
        "default_version": descriptor.default_version,
        "homepage_url": descriptor.homepage_url,
        "attribution_key": descriptor.attribution_key,
        "coverage_hint": asdict(descriptor.coverage_hint),
        "requires_manual_approval": descriptor.requires_manual_approval,
        "requires_network": descriptor.requires_network,
    }


def _warning_payload(warning: SourceWarning) -> dict[str, object]:
    return {
        "code": warning.code,
        "message": warning.message,
        "severity": warning.severity,
        "source_id": warning.source_id.slug if warning.source_id else None,
        "context": dict(warning.context),
    }


def _ingest_result_payload(result: SourceIngestResult) -> dict[str, object]:
    manifest = result.manifest
    return {
        "source_id": result.source_id.slug,
        "ready": result.readiness.ready,
        "validation_valid": result.validation.valid,
        "observation_count": len(result.observations),
        "manifest_run_id": manifest.run_id if manifest else None,
        "manifest_idempotency_key": manifest.idempotency_key if manifest else None,
        "warnings": [_warning_payload(warning) for warning in result.warnings],
        "validation_errors": [_warning_payload(error) for error in result.validation.errors],
    }


def _echo_ingest_failure(source: str, message: str, *, output: str) -> None:
    if output == "json":
        typer.echo(
            json.dumps(
                {
                    "source_id": source,
                    "ready": False,
                    "validation_valid": False,
                    "observation_count": 0,
                    "manifest_run_id": None,
                    "manifest_idempotency_key": None,
                    "warnings": [],
                    "validation_errors": [
                        {
                            "code": "INGEST_FAILED",
                            "message": message,
                            "severity": "error",
                            "source_id": source,
                            "context": {},
                        }
                    ],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return

    typer.echo(f"source_id: {source}")
    typer.echo("ready: False")
    typer.echo("validation_valid: False")
    typer.echo("observation_count: 0")
    typer.echo("manifest_run_id: -")
    typer.echo(f"errors:\n  - [error] INGEST_FAILED: {message}")


def _echo_findings(label: str, warnings: tuple[SourceWarning, ...]) -> None:
    if not warnings:
        typer.echo(f"{label}s: -")
        return
    typer.echo(f"{label}s:")
    for warning in warnings:
        typer.echo(f"  - [{warning.severity}] {warning.code}: {warning.message}")


__all__ = [
    "sources_app",
    "sources_check_ready_cmd",
    "sources_describe_cmd",
    "sources_ingest_cmd",
    "sources_list_cmd",
]
