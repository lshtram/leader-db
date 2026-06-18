"""`.env` loader.

Centralizes the project's environment-variable loading so the rest of the
package does not depend on a global side effect. The loader is idempotent
and safe to call from CLI commands and library code alike.

Secrets must never be committed. The ``.env.example`` file in the project
root enumerates the supported variables; ``.env`` itself is gitignored.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import dotenv_values, load_dotenv

# Track whether we already loaded so re-entry doesn't double-up.
_LOADED: bool = False


def load_env(env_file: Path | str | None = None, override: bool = False) -> bool:
    """Load environment variables from ``.env`` if present.

    Parameters
    ----------
    env_file:
        Optional explicit path. Defaults to ``<project-root>/.env``.
    override:
        When ``True``, values in ``.env`` override the current process
        environment. Defaults to ``False`` so the real environment wins.

    Returns
    -------
    bool
        ``True`` if a file was loaded, ``False`` if no ``.env`` was found.
    """
    global _LOADED

    if env_file is None:
        project_root = _project_root()
        env_file = project_root / ".env"

    env_path = Path(env_file)
    if not env_path.is_file():
        return False

    load_dotenv(env_path, override=override)
    _LOADED = True
    return True


def env_value(key: str, default: str | None = None) -> str | None:
    """Return the current value of an environment variable.

    Convenience wrapper that triggers ``load_env`` once on first use.
    """
    if not _LOADED:
        load_env()
    import os

    return os.environ.get(key, default)


def env_dict(env_file: Path | str | None = None) -> dict[str, str]:
    """Return the variables in ``.env`` (without loading them into the process).

    Useful for inspecting the file in tests or for the source-vetting phase
    to confirm a source's credentials are present without leaking them into
    log output.
    """
    if env_file is None:
        env_file = _project_root() / ".env"

    env_path = Path(env_file)
    if not env_path.is_file():
        return {}
    return {k: str(v) for k, v in dotenv_values(env_path).items() if v is not None}


def _project_root() -> Path:
    """Locate the project root.

    Resolution order: an explicit ``LEADERSDB_PROJECT_ROOT`` environment
    variable, then a parent-of-this-file search for ``pyproject.toml``.
    """
    import os

    override = os.environ.get("LEADERSDB_PROJECT_ROOT")
    if override:
        return Path(override).resolve()

    here = Path(__file__).resolve()
    for parent in (here, *here.parents):
        if (parent / "pyproject.toml").is_file():
            return parent
    # Last resort: current working directory.
    return Path.cwd()
