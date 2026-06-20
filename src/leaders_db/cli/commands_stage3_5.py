"""Stage 3 / Stage 4 / Stage 5 stub commands.

Stage 3 (``match-countries``) builds the country-matching layer
(ISO3 primary, alias table). Stage 4 (``resolve-leaders``) resolves
the actual ruler per country-year for the target year. Stage 5
(``extract-indicators``) extracts per-category indicator bundles per
ruler-year. All three are Phase E stubs in the prototype — they
print the canonical "not implemented yet" message and reference the
module to implement.

The three commands share this submodule because all three are
stub-only, single-line :func:`_not_implemented_yet` calls; pairing
them keeps the file size well under the 400-line convention while
the future Stage 3 / 4 / 5 implementations can be split into
separate submodules without changing the command names or import
paths.
"""

from __future__ import annotations

from pathlib import Path

import typer

from ..config import default_config_path
from ._app import app
from ._helpers import _not_implemented_yet, _safe_load_config


@app.command("match-countries")
def match_countries(
    config: Path = typer.Option(default_config_path(), "--config", "-c"),
) -> None:
    """Stage 3: build the country-matching layer (ISO3 primary, alias table)."""
    _safe_load_config(config)
    typer.echo("[Stage 3] match countries")
    _not_implemented_yet("resolve/country_match.py", "Phase E.")


@app.command("resolve-leaders")
def resolve_leaders(
    year: int = typer.Option(..., "--year", "-y"),
    config: Path = typer.Option(default_config_path(), "--config", "-c"),
) -> None:
    """Stage 4: resolve the actual ruler per country-year for the target year."""
    _safe_load_config(config)
    typer.echo(f"[Stage 4] resolve leaders for year {year}")
    _not_implemented_yet("resolve/leader_resolver.py", "Phase E.")


@app.command("extract-indicators")
def extract_indicators(
    year: int = typer.Option(..., "--year", "-y"),
    config: Path = typer.Option(default_config_path(), "--config", "-c"),
) -> None:
    """Stage 5: extract per-category indicator bundles per ruler-year."""
    _safe_load_config(config)
    typer.echo(f"[Stage 5] extract indicators for year {year}")
    _not_implemented_yet("resolve/indicators.py", "Phase E.")


__all__ = ["extract_indicators", "match_countries", "resolve_leaders"]
