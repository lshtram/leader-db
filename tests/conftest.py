"""Pytest configuration and shared fixtures.

The prototype uses an isolated, per-test SQLite database so tests cannot
pollute the canonical ``data/catalog/leaders_db.sqlite``. The DB URL is
exposed as the ``DATABASE_URL`` fixture; tests should request it via
parameterization rather than hard-coding.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def project_root() -> Path:
    """Return the project root directory."""
    from leaders_db.paths import project_root as _project_root

    return _project_root()


@pytest.fixture()
def isolated_data_lake(monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Redirect the data lake to a temp dir for the duration of one test.

    The fixture overrides ``LEADERSDB_PROJECT_ROOT`` so all
    ``leaders_db.paths`` helpers point at a freshly-created temp tree.
    """
    with tempfile.TemporaryDirectory(prefix="leaders-db-tests-") as tmp:
        tmp_path = Path(tmp)
        # Mirror the data-lake skeleton so path helpers do not raise.
        for sub in (
            "data/raw",
            "data/processed",
            "data/interim",
            "data/outputs",
            "data/logs",
            "data/metadata",
            "data/catalog",
        ):
            (tmp_path / sub).mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv("LEADERSDB_PROJECT_ROOT", str(tmp_path))
        # Reload cached paths so the override takes effect.
        from leaders_db import env as _env
        from leaders_db import paths as _paths

        _env._LOADED = False
        # Drop the resolved root from paths so the next call re-resolves.
        if hasattr(_paths, "_project_root_cached"):
            delattr(_paths, "_project_root_cached")
        yield tmp_path


@pytest.fixture()
def database_url(isolated_data_lake: Path) -> str:
    """Return a SQLite URL pointing at the isolated data lake.

    The URL matches :func:`leaders_db.db.session.default_sqlite_url` so
    code that calls ``session_scope()`` with no args (resolving through
    the ``LEADERSDB_PROJECT_ROOT`` env var) and code that calls
    ``init_database(database_url)`` operate on the same SQLite file.
    Without this alignment, the test DB and the orchestrator's
    resolved DB would be different files and migrations would not
    apply where the orchestrator looks.
    """
    # Importing the function (not just the module) so the resolved path
    # uses the env-var override set by ``isolated_data_lake``.
    from leaders_db.db.session import default_sqlite_url

    return default_sqlite_url()


@pytest.fixture()
def client_bundle_dir(isolated_data_lake: Path) -> Path:
    """Create an empty ``data/raw/client_existing/`` folder and return it."""
    target = isolated_data_lake / "data" / "raw" / "client_existing"
    target.mkdir(parents=True, exist_ok=True)
    return target


@pytest.fixture(autouse=True)
def _ensure_no_real_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent tests from accidentally loading a project-root ``.env``."""
    # ``python-dotenv`` only loads when explicitly invoked, but guard the
    # process environment anyway so a leaked CI variable cannot affect a
    # test. Tests that need env values should set them via monkeypatch.
    for key in list(os.environ):
        if key.startswith("LEADERSDB_"):
            monkeypatch.delenv(key, raising=False)


def copy_fixture(src: Path, dst: Path) -> Path:
    """Copy ``src`` (relative to the tests/fixtures dir) to ``dst``."""
    fixtures = Path(__file__).resolve().parent / "fixtures"
    src_path = fixtures / src
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    return Path(shutil.copy2(src_path, dst))


__all__ = [
    "client_bundle_dir",
    "copy_fixture",
    "database_url",
    "isolated_data_lake",
    "project_root",
]
