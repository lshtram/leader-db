"""Typer application + global callback.

Owns the :data:`app` instance every command submodule registers
its commands against, the ``--version`` flag, and the
:class:`typer.Typer` configuration (no-args-is-help, no shell
completion).

The :data:`app` instance is re-exported from
:mod:`leaders_db.cli.__init__` so ``from leaders_db.cli import
app`` and the ``leaders-db = "leaders_db.cli:app"`` entry point
in ``pyproject.toml`` both resolve to the fully-populated app
without the per-stage command modules needing to be imported
by the entry point.
"""

from __future__ import annotations

import typer

from ..version import __version__

app = typer.Typer(
    name="leaders-db",
    help=(
        "Leaders Database prototype — AI-agent data collection and validation "
        "system. See `docs/requirements/top-level-requirements.md` §8 for the full pipeline."
    ),
    no_args_is_help=True,
    add_completion=False,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"leaders-db {__version__}")
        raise typer.Exit()


@app.callback()
def main_callback(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Print the package version and exit.",
    ),
) -> None:
    """Global CLI options."""


__all__ = ["app", "main_callback"]
