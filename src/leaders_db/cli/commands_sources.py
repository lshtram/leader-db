"""Clean source-registry inspection CLI commands."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import cast

import typer

from ..sources import (
    CachePolicy,
    SourceDescriptor,
    SourceId,
    SourceIngestRequest,
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
    "sources_list_cmd",
]
