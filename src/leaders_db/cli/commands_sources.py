"""Clean source-registry inspection CLI commands."""

from __future__ import annotations

import json
from dataclasses import asdict

import typer

from ..sources import SourceDescriptor, SourceId, build_default_source_registry
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


__all__ = ["sources_app", "sources_describe_cmd", "sources_list_cmd"]
